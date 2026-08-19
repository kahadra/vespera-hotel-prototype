from __future__ import annotations

import argparse
import base64
import json
import time
from pathlib import Path

from smoke_browser import CdpClient, capture, debugger_target, wait_for


ROOT = Path(__file__).resolve().parents[1]


def export(url: str, port: int, output_dir: Path, record: bool, record_start: float):
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    target = debugger_target(port)
    client = CdpClient(target["webSocketDebuggerUrl"])
    try:
        client.command("Runtime.enable")
        client.command("Page.enable")
        client.command("Log.enable")
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

        previews = []
        for second, name in ((0, "intro"), (18, "core-loop"), (80, "facility"), (118, "night2"), (145, "outro")):
            client.evaluate(f"playhead = {second}; playing = false; render(); true")
            path = output_dir / f"preview-{name}.png"
            capture(client, path)
            previews.append(str(path))

        audits = []
        audit_dir = ROOT / "submission_video" / "box_audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        scene_specs = client.evaluate(
            "scenes.map((scene, index) => ({index, duration: scene.duration, image: scene.image || scene.type, hasBoxes: Boolean(scene.boxes?.length)}))"
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
            if not 149 <= metadata["duration"] <= 152:
                raise AssertionError(f"Unexpected video duration: {metadata}")
        else:
            video = None
            metadata = None

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
    args = parser.parse_args()
    print(json.dumps(export(args.url, args.debug_port, args.output_dir, args.record, args.record_start), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
