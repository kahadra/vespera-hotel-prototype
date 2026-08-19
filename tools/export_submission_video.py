from __future__ import annotations

import argparse
import base64
import json
import time
from pathlib import Path

from smoke_browser import CdpClient, capture, debugger_target, wait_for


ROOT = Path(__file__).resolve().parents[1]


def validate_video_playback(
    client: CdpClient,
    video: Path,
    output_dir: Path,
    expected_duration: float = 150,
):
    metadata = client.evaluate(
        f"""
        (async () => {{
          const video = document.createElement('video');
          video.preload = 'auto';
          video.src = '/submission_video/output/{video.name}?check=' + Date.now();
          await new Promise((resolve, reject) => {{
            video.addEventListener('loadedmetadata', resolve, {{once: true}});
            video.addEventListener('error', reject, {{once: true}});
          }});
          if (!Number.isFinite(video.duration)) {{
            video.currentTime = 1e101;
            await new Promise(resolve => video.addEventListener('timeupdate', resolve, {{once: true}}));
          }}
          return {{duration: video.duration, width: video.videoWidth, height: video.videoHeight}};
        }})()
        """
    )
    if metadata["width"] != 1280 or metadata["height"] != 720:
        raise AssertionError(f"Unexpected video dimensions: {metadata}")
    if not expected_duration - 1 <= metadata["duration"] <= expected_duration + 2:
        raise AssertionError(f"Unexpected video duration: {metadata}")

    client.evaluate(
        f"""
        (async () => {{
          const video = document.createElement('video');
          video.id = 'validation-video';
          video.preload = 'auto';
          video.muted = true;
          video.playsInline = true;
          video.style.cssText = 'display:block;width:1280px;height:720px;object-fit:contain;background:#000';
          video.src = '/submission_video/output/{video.name}?playback=' + Date.now();
          document.body.replaceChildren(video);
          document.body.style.cssText = 'margin:0;padding:0;width:1280px;height:720px;overflow:hidden;background:#000';
          await new Promise((resolve, reject) => {{
            video.addEventListener('loadedmetadata', resolve, {{once: true}});
            video.addEventListener('error', reject, {{once: true}});
          }});
          if (!Number.isFinite(video.duration)) {{
            video.currentTime = 1e101;
            await new Promise(resolve => video.addEventListener('timeupdate', resolve, {{once: true}}));
          }}
          window.__validationVideo = video;
          return true;
        }})()
        """
    )

    validation_specs = (
        (
            (1, "smoke-start"),
            (expected_duration / 2, "smoke-middle"),
            (max(0.25, expected_duration - 0.5), "smoke-end"),
        )
        if expected_duration < 20
        else (
            (10, "playback"),
            (76, "reservation-capacity"),
            (107, "ssr-invitation"),
            (116, "night5"),
            (146, "outro"),
        )
    )
    validation_frames = []
    continuous_playback = True
    validation_rate = 1 if expected_duration < 20 else 4
    if continuous_playback:
        client.evaluate(
            f"window.__validationVideo.currentTime = 0; window.__validationVideo.playbackRate = {validation_rate}; window.__validationVideo.play(); true"
        )
    for second, name in validation_specs:
        if continuous_playback:
            deadline = time.time() + expected_duration / validation_rate + 3
            while time.time() < deadline:
                current_time = client.evaluate("window.__validationVideo.currentTime")
                if current_time >= second:
                    break
                time.sleep(0.05)
            else:
                raise TimeoutError(f"Video playback did not reach {second} seconds")
        else:
            client.evaluate(
                f"""
                (async () => {{
                  const video = window.__validationVideo;
                  const target = Math.min({second}, Math.max(0, video.duration - 0.25));
                  await new Promise((resolve, reject) => {{
                    video.addEventListener('seeked', resolve, {{once: true}});
                    video.addEventListener('error', reject, {{once: true}});
                    video.currentTime = target;
                  }});
                  await video.play();
                  await Promise.race([
                    new Promise(resolve => {{
                      if (video.requestVideoFrameCallback) video.requestVideoFrameCallback(() => resolve());
                      else requestAnimationFrame(() => requestAnimationFrame(resolve));
                    }}),
                    new Promise(resolve => setTimeout(resolve, 1000)),
                  ]);
                  video.pause();
                  return {{currentTime: video.currentTime, width: video.videoWidth, height: video.videoHeight}};
                }})()
                """
            )
        frame_second = int(round(second))
        frame = output_dir / (
            "validation-video-playback.png"
            if second == 10
            else f"validation-video-{frame_second:03d}-{name}.png"
        )
        capture(client, frame)
        validation_frames.append(str(frame))
    if continuous_playback:
        client.evaluate("window.__validationVideo.pause(); true")

    return metadata, Path(validation_frames[0]), validation_frames


def export(
    url: str,
    port: int,
    output_dir: Path,
    record: bool,
    record_start: float,
    validate_existing: bool = False,
    record_limit: float | None = None,
):
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if record or validate_existing:
        for stale_validation in output_dir.glob("validation-video-*.png"):
            stale_validation.unlink()
    target = debugger_target(port)
    client = CdpClient(target["webSocketDebuggerUrl"])
    try:
        client.command("Runtime.enable")
        client.command("Page.enable")
        client.command("Log.enable")
        client.command("Network.enable")
        client.command("Network.setCacheDisabled", {"cacheDisabled": True})
        client.command(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1280, "height": 720, "deviceScaleFactor": 1, "mobile": False},
        )
        client.command("Page.navigate", {"url": url})
        wait_for(client, "document.readyState === 'complete'")
        wait_for(client, "document.querySelector('#loading')?.classList.contains('hidden')")

        duration = client.evaluate("TOTAL")
        if duration != 150:
            raise AssertionError(f"Expected a 150-second timeline, got {duration}")

        for stale_preview in output_dir.glob("preview-*.png"):
            stale_preview.unlink()
        previews = []
        for second, name in (
            (10, "progression-notice"),
            (27, "tutorial"),
            (52, "night1"),
            (76, "reservation-capacity"),
            (96, "night4-synergy"),
            (107, "ssr-invitation"),
            (130, "final"),
            (146, "outro"),
        ):
            client.evaluate(f"playhead = {second}; playing = false; render(); true")
            path = output_dir / f"preview-{name}.png"
            capture(client, path)
            previews.append(str(path))

        audits = []
        audit_dir = ROOT / "submission_video" / "box_audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        for stale_audit in audit_dir.glob("scene-*.png"):
            stale_audit.unlink()
        scene_specs = client.evaluate(
            "scenes.map((scene, index) => ({index, duration: scene.duration, image: scene.image || scene.type, hasBoxes: resolveSceneTarget(scene).boxes.length > 0}))"
        )
        scene_start = 0
        for scene in scene_specs:
            if scene["hasBoxes"]:
                client.evaluate(
                    f"playhead = {scene_start + scene['duration'] * 0.5}; playing = false; render(); true"
                )
                path = audit_dir / f"scene-{scene['index'] + 1:02d}-{scene['image']}.png"
                capture(client, path)
                audits.append(str(path))
            scene_start += scene["duration"]

        if record:
            client.evaluate(f"window.automatedExport = true; recordVideo({record_start}); true")
            if record_limit is not None:
                limit_deadline = time.time() + max(0.25, record_limit)
                while time.time() < limit_deadline:
                    time.sleep(min(0.25, max(0.01, limit_deadline - time.time())))
                client.evaluate(
                    "playing = false; if (mediaRecorder?.state === 'recording') mediaRecorder.stop(); true"
                )
            else:
                deadline = time.time() + 175
                while time.time() < deadline:
                    state = client.evaluate("mediaRecorder?.state || 'starting'")
                    if state == "inactive":
                        break
                    time.sleep(2)
                else:
                    raise TimeoutError("Video recording did not finish within 175 seconds")

            deadline = time.time() + 20
            while time.time() < deadline and not client.evaluate("window.recordedReady === true"):
                time.sleep(0.1)
            if not client.evaluate("window.recordedReady === true"):
                raise AssertionError("The browser did not finalize the recorded video blob")

            video = output_dir / "vespera-hotel-play-demo.webm"
            video_size = client.evaluate("window.recordedBytes.length")
            chunk_size = 256 * 1024
            with video.open("wb") as output:
                for start in range(0, video_size, chunk_size):
                    end = min(start + chunk_size, video_size)
                    encoded = client.evaluate(
                        f"""
                        (() => {{
                          const bytes = window.recordedBytes.subarray({start}, {end});
                          let binary = '';
                          for (let offset = 0; offset < bytes.length; offset += 32768) {{
                            binary += String.fromCharCode(...bytes.subarray(offset, offset + 32768));
                          }}
                          return btoa(binary);
                        }})()
                        """
                    )
                    output.write(base64.b64decode(encoded))
            if not video.exists() or video.stat().st_size != video_size:
                raise AssertionError("The recorded WebM was not downloaded correctly")
            expected_recording_duration = max(
                0.25,
                duration - max(0, min(float(record_start), duration)),
            )
            if record_limit is not None:
                expected_recording_duration = min(
                    expected_recording_duration,
                    max(0.25, float(record_limit)),
                )
            metadata, validation_frame, validation_frames = validate_video_playback(
                client, video, output_dir, expected_recording_duration
            )
        elif validate_existing:
            video = output_dir / "vespera-hotel-play-demo.webm"
            if not video.exists():
                raise FileNotFoundError(f"Existing video not found: {video}")
            metadata, validation_frame, validation_frames = validate_video_playback(
                client, video, output_dir
            )
        else:
            video = None
            metadata = None
            validation_frame = None
            validation_frames = []

        errors = [
            event for event in client.events
            if event.get("method") == "Runtime.exceptionThrown"
            or (
                event.get("method") == "Log.entryAdded"
                and event.get("params", {}).get("entry", {}).get("level") == "error"
            )
        ]
        if errors:
            raise AssertionError(f"Browser errors detected: {errors}")

        return {
            "status": "PASS",
            "duration_seconds": duration,
            "previews": previews,
            "box_audits": audits,
            "video": str(video) if video else None,
            "video_bytes": video.stat().st_size if video else None,
            "video_metadata": metadata,
            "validation_frame": str(validation_frame) if validation_frame else None,
            "validation_frames": validation_frames,
        }
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765/submission_video/")
    parser.add_argument("--debug-port", type=int, default=9223)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "submission_video" / "output")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--record-start", type=float, default=0)
    parser.add_argument("--record-limit", type=float)
    parser.add_argument("--validate-existing", action="store_true")
    args = parser.parse_args()
    print(json.dumps(
        export(
            args.url,
            args.debug_port,
            args.output_dir,
            args.record,
            args.record_start,
            args.validate_existing,
            args.record_limit,
        ),
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
