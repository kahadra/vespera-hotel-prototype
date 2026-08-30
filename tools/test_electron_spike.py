from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from smoke_browser import CdpClient, debugger_target


ROOT = Path(__file__).resolve().parents[1]
APP_URL = "vespera://app/index.html"
SAVE_PREFIX = "vespera.hotel"
TEST_SEED = 424_242
CAMPAIGN_SEED = 525_252
ENDLESS_SEED = 626_262
MODE_TYPES = {
    "campaign": "CAMPAIGN",
    "endless": "ENDLESS",
    "showcase": "SHOWCASE",
}
MODE_CHECKPOINTS = {
    "campaign": (CAMPAIGN_SEED, "STORY"),
    "endless": (ENDLESS_SEED, "ENDLESS_BRIEFING"),
    "showcase": (TEST_SEED, "TUTORIAL"),
}
NO_SAVES = {mode_id: "NONE" for mode_id in MODE_TYPES}
ALL_SAVES = {mode_id: "AVAILABLE" for mode_id in MODE_TYPES}
CAMPAIGN_ENDLESS_SAVES = {
    "campaign": "AVAILABLE",
    "endless": "AVAILABLE",
    "showcase": "NONE",
}
ACTIVE_RUN_STORAGE_PREFIX = "vespera.hotel.active-run.v2"
RUN_RECORD_STORAGE_KEY = "vespera.hotel.run-records.v1"
ELECTRON_STARTUP_TIMEOUT_SECONDS = 45.0


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def wait_for(client: CdpClient, expression: str, timeout: float = 45.0):
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            if client.evaluate(expression):
                return
        except Exception as error:  # a navigation may replace the JS context
            last_error = error
        time.sleep(0.1)
    raise AssertionError(f"Timed out waiting for {expression}: {last_error}")


def remove_test_tree(temp_root: Path, workspace_temp: Path, timeout: float = 30.0):
    resolved_root = temp_root.resolve()
    resolved_parent = workspace_temp.resolve()
    if resolved_parent not in resolved_root.parents:
        raise RuntimeError(f"Refusing to clean unsafe Electron test directory: {resolved_root}")
    if not resolved_root.exists():
        return

    deadline = time.time() + timeout
    last_error: OSError | None = None
    while time.time() < deadline:
        try:
            shutil.rmtree(resolved_root)
            return
        except OSError as error:
            last_error = error
            time.sleep(0.2)
    raise RuntimeError(f"Could not clean Electron test directory: {resolved_root}") from last_error


def force_stop_owned_tree(process: subprocess.Popen):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=8)


class ElectronProcess:
    def __init__(
        self,
        *,
        kind: str,
        executable: Path,
        app_dir: Path,
        user_data: Path,
        log_path: Path,
        outer_size: tuple[int, int] | None = None,
    ):
        self.kind = kind
        self.port = free_port()
        self.client: CdpClient | None = None
        self.process: subprocess.Popen | None = None
        self.log_handle = None
        user_data.mkdir(parents=True, exist_ok=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        switches = [
            f"--remote-debugging-port={self.port}",
            "--remote-allow-origins=*",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-default-apps",
            "--disable-extensions",
            "--disable-sync",
            "--no-first-run",
        ]
        app_arguments = [
            "--vespera-test",
            f"--vespera-user-data-dir={user_data.resolve()}",
        ]
        if outer_size is not None:
            width, height = outer_size
            if not all(
                isinstance(value, int) and not isinstance(value, bool)
                for value in outer_size
            ):
                raise ValueError(
                    f"Electron test outer size must contain integers: {outer_size!r}"
                )
            app_arguments.append(f"--vespera-test-window-size={width}x{height}")
        command = [str(executable.resolve()), *switches]
        if kind == "dev":
            command.append(str(app_dir.resolve()))
        command.extend(app_arguments)
        environment = os.environ.copy()
        environment.pop("ELECTRON_RUN_AS_NODE", None)
        environment.pop("Electron_Run_As_Node", None)
        environment.pop("CHROME_CRASHPAD_PIPE_NAME", None)
        environment.pop("CHROME_CRASHPAD_SERVER_URL", None)
        environment["ELECTRON_ENABLE_LOGGING"] = "1"
        environment["ELECTRON_ENABLE_SECURITY_WARNINGS"] = "true"
        try:
            self.log_handle = log_path.open("w", encoding="utf-8")
            self.process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdout=self.log_handle,
                stderr=subprocess.STDOUT,
                env=environment,
            )
            target = debugger_target(
                self.port,
                timeout=ELECTRON_STARTUP_TIMEOUT_SECONDS,
                allowed_url_prefixes=("vespera://app/",),
            )
            self.client = CdpClient(target["webSocketDebuggerUrl"])
            self.client.command("Page.enable")
            self.client.command("Runtime.enable")
            self.client.command("Network.enable")
            wait_for(
                self.client,
                "document.readyState === 'complete' && Boolean(window.__vesperaModeHub)",
            )
        except BaseException as error:
            try:
                self.stop()
            except BaseException as cleanup_error:
                error.add_note(f"Electron cleanup also failed: {cleanup_error!r}")
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            exit_code = self.process.returncode if self.process is not None else None
            log = (
                log_path.read_text(encoding="utf-8", errors="replace")
                if log_path.is_file()
                else ""
            )
            raise RuntimeError(
                "Electron target did not become ready "
                f"(exit={exit_code}, reason={error!r})\n{log[-8000:]}"
            ) from error

    def stop(self):
        cleanup_error: BaseException | None = None
        client = getattr(self, "client", None)
        try:
            if client is not None:
                try:
                    client.ws.settimeout(3)
                    client.command("Browser.close")
                except Exception:
                    pass
                try:
                    client.close()
                except Exception:
                    pass
                self.client = None
            if self.process is not None and self.process.poll() is None:
                try:
                    self.process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    force_stop_owned_tree(self.process)
        except BaseException as error:
            cleanup_error = error
        finally:
            if self.log_handle is not None and not self.log_handle.closed:
                try:
                    self.log_handle.close()
                except BaseException as close_error:
                    if cleanup_error is None:
                        cleanup_error = close_error
                    else:
                        cleanup_error.add_note(
                            f"Electron log close also failed: {close_error!r}"
                        )
        if cleanup_error is not None:
            raise cleanup_error


def navigate(client: CdpClient, url: str):
    client.command("Page.navigate", {"url": url})
    wait_for(client, "document.readyState === 'complete' && Boolean(window.__vesperaController)")


def navigate_hub(client: CdpClient):
    client.command("Page.navigate", {"url": APP_URL})
    wait_for(client, "document.readyState === 'complete' && Boolean(window.__vesperaModeHub)")


def mode_url(mode_id: str, seed: int | None = None) -> str:
    assert mode_id in MODE_TYPES, mode_id
    url = f"{APP_URL}?mode={mode_id}"
    return f"{url}&seed={seed}" if seed is not None else url


def save_root(user_data: Path) -> Path:
    return user_data / "save-data" / "v1" / "profiles" / "local"


def active_run_path(user_data: Path, mode_id: str) -> Path:
    assert mode_id in MODE_TYPES, mode_id
    return save_root(user_data) / f"active-run.v2.{mode_id}.json"


def assert_mode_hub(
    client: CdpClient,
    expected_statuses: dict[str, str] | None = None,
) -> dict:
    hub = client.evaluate(
        """
        (() => ({
          href: location.href,
          search: location.search,
          controllerPresent: Boolean(window.__vesperaController),
          modes: window.__vesperaModeHub.modes.map((mode) => ({
            id: mode.id ?? null,
            modeId: mode.modeId ?? null,
            label: mode.label ?? null,
            description: mode.description ?? null,
            status: mode.status ?? null,
            savedAt: mode.savedAt ?? null,
            phase: mode.phase ?? null,
            runSeed: mode.runSeed ?? null,
            currentNightIndex: mode.currentNightIndex ?? null,
          })),
          hasOpen: typeof window.__vesperaModeHub.open === 'function',
        }))()
        """
    )
    assert hub["href"].startswith(APP_URL), hub
    assert hub["search"] == "", hub
    assert hub["controllerPresent"] is False, hub
    assert hub["hasOpen"] is True, hub
    modes = {mode["id"]: mode for mode in hub["modes"]}
    assert set(modes) == set(MODE_TYPES), modes
    for mode_id, mode in modes.items():
        assert mode["modeId"] == MODE_TYPES[mode_id], mode
        assert isinstance(mode["label"], str) and mode["label"].strip(), mode
        assert isinstance(mode["description"], str) and mode["description"].strip(), mode
        assert mode["status"] in {"AVAILABLE", "NONE", "INVALID"}, mode
    if expected_statuses is not None:
        assert set(expected_statuses) == set(MODE_TYPES), expected_statuses
        actual_statuses = {mode_id: modes[mode_id]["status"] for mode_id in MODE_TYPES}
        assert actual_statuses == expected_statuses, (actual_statuses, expected_statuses)
        for mode_id, expected_status in expected_statuses.items():
            mode = modes[mode_id]
            if expected_status == "AVAILABLE":
                seed, phase = MODE_CHECKPOINTS[mode_id]
                assert mode["runSeed"] == seed, mode
                assert mode["phase"] == phase, mode
                assert isinstance(mode["savedAt"], str) and mode["savedAt"], mode
                assert isinstance(mode["currentNightIndex"], int), mode
            elif expected_status == "NONE":
                assert mode["savedAt"] is None, mode
                assert mode["phase"] is None, mode
                assert mode["runSeed"] is None, mode
                assert mode["currentNightIndex"] is None, mode
    return hub


def mode_hub_layout_snapshot(client: CdpClient) -> dict:
    client.evaluate(
        "new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
    )
    return client.evaluate(
        """
        (() => {
          const buttons = [...document.querySelectorAll('[data-mode-id]')].map((button) => {
            const rect = button.getBoundingClientRect();
            return {
              modeId: button.dataset.modeId ?? null,
              left: Math.round(rect.left * 100) / 100,
              top: Math.round(rect.top * 100) / 100,
              right: Math.round(rect.right * 100) / 100,
              bottom: Math.round(rect.bottom * 100) / 100,
              width: Math.round(rect.width * 100) / 100,
              height: Math.round(rect.height * 100) / 100,
              tabIndex: button.tabIndex,
              disabled: button.disabled === true,
            };
          });
          return {
            outerWidth,
            outerHeight,
            viewportWidth: innerWidth,
            viewportHeight: innerHeight,
            scrollWidth: Math.max(
              document.documentElement.scrollWidth,
              document.body.scrollWidth
            ),
            scrollHeight: Math.max(
              document.documentElement.scrollHeight,
              document.body.scrollHeight
            ),
            buttons,
          };
        })()
        """
    )


def assert_visible_hub_layout(layout: dict) -> dict:
    width = layout["viewportWidth"]
    height = layout["viewportHeight"]
    assert width > 0 and height > 0, layout
    assert layout["scrollWidth"] <= width, layout
    assert layout["scrollHeight"] <= height, layout
    assert len(layout["buttons"]) == 3, layout
    assert {button["modeId"] for button in layout["buttons"]} == set(MODE_TYPES), layout
    for button in layout["buttons"]:
        assert button["width"] > 0 and button["height"] > 0, button
        assert button["left"] >= 0 and button["top"] >= 0, button
        assert button["right"] <= width and button["bottom"] <= height, button
        assert button["tabIndex"] >= 0 and button["disabled"] is False, button
    return {
        "contentViewport": {"width": width, "height": height},
        "scrollWidth": layout["scrollWidth"],
        "scrollHeight": layout["scrollHeight"],
        "maximumButtonBottom": max(button["bottom"] for button in layout["buttons"]),
        "keyboardFocusable": all(
            button["tabIndex"] >= 0 and button["disabled"] is False
            for button in layout["buttons"]
        ),
    }


def actual_browser_window_layout(
    client: CdpClient,
    expected_outer_size: tuple[int, int],
) -> dict:
    expected_width, expected_height = expected_outer_size
    layout = mode_hub_layout_snapshot(client)
    assert layout["outerWidth"] == expected_width, layout
    assert layout["outerHeight"] == expected_height, layout
    return {
        "status": "PASS",
        "measurement": "WINDOW_JS_OUTER_DIMENSIONS",
        "requestedOuterBounds": {
            "width": expected_width,
            "height": expected_height,
        },
        "observedOuterBounds": {
            "width": layout["outerWidth"],
            "height": layout["outerHeight"],
        },
        **assert_visible_hub_layout(layout),
    }


def assert_mode_hub_layout(
    client: CdpClient,
    expected_outer_size: tuple[int, int],
) -> dict:
    actual_window = actual_browser_window_layout(client, expected_outer_size)
    emulated_viewports: dict[str, dict] = {}
    try:
        for width, height in ((1280, 720), (960, 600)):
            client.command(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": width,
                    "height": height,
                    "deviceScaleFactor": 1,
                    "mobile": False,
                },
            )
            layout = mode_hub_layout_snapshot(client)
            assert layout["viewportWidth"] == width, layout
            assert layout["viewportHeight"] == height, layout
            emulated_viewports[f"{width}x{height}"] = {
                "measurement": "EMULATED_CONTENT_VIEWPORT",
                **assert_visible_hub_layout(layout),
            }
    finally:
        client.command("Emulation.clearDeviceMetricsOverride")
    return {
        "actualBrowserWindow960x600": actual_window,
        "emulatedContentViewports": emulated_viewports,
    }


def assert_opened_mode(client: CdpClient, mode_id: str):
    wait_for(client, "document.readyState === 'complete' && Boolean(window.__vesperaController)")
    opened_mode = client.evaluate(
        """
        ({
          requestedMode: new URL(location.href).searchParams.get('mode'),
          modeType: window.__vesperaController.data.prototype_mode.type,
          phase: window.__vesperaController.state.phase,
        })
        """
    )
    assert opened_mode == {
        "requestedMode": mode_id,
        "modeType": MODE_TYPES[mode_id],
        "phase": "TITLE",
    }, opened_mode


def open_mode(client: CdpClient, mode_id: str):
    assert mode_id in MODE_TYPES, mode_id
    opened = client.evaluate(
        f"window.__vesperaModeHub.open({json.dumps(mode_id)}); true"
    )
    assert opened is True
    assert_opened_mode(client, mode_id)


def open_mode_by_click(client: CdpClient, mode_id: str):
    assert mode_id in MODE_TYPES, mode_id
    client.click(f'[data-mode-id="{mode_id}"]')
    assert_opened_mode(client, mode_id)


def return_to_hub(
    client: CdpClient,
    expected_statuses: dict[str, str] | None = None,
):
    client.click('[data-action="return-mode-hub"]')
    wait_for(client, "document.readyState === 'complete' && Boolean(window.__vesperaModeHub)")
    return assert_mode_hub(client, expected_statuses)


def dispatch_key(client: CdpClient, *, key: str, code: str, windows_key_code: int):
    common = {
        "key": key,
        "code": code,
        "windowsVirtualKeyCode": windows_key_code,
        "nativeVirtualKeyCode": windows_key_code,
    }
    client.command("Input.dispatchKeyEvent", {"type": "rawKeyDown", **common})
    client.command("Input.dispatchKeyEvent", {"type": "keyUp", **common})


def dispatch_space_activation(client: CdpClient):
    common = {
        "key": " ",
        "code": "Space",
        "windowsVirtualKeyCode": 32,
        "nativeVirtualKeyCode": 32,
    }
    client.command(
        "Input.dispatchKeyEvent",
        {
            "type": "keyDown",
            "text": " ",
            "unmodifiedText": " ",
            **common,
        },
    )
    client.command("Input.dispatchKeyEvent", {"type": "keyUp", **common})


def assert_keyboard_mode_navigation(client: CdpClient) -> dict:
    assert_mode_hub(client, NO_SAVES)
    client.evaluate(
        """
        (() => {
          window.__vesperaKeyboardTelemetry = [];
          const record = (type, event) => {
            window.__vesperaKeyboardTelemetry.push({
              type,
              key: event.key ?? null,
              code: event.code ?? null,
              isTrusted: event.isTrusted === true,
              defaultPrevented: event.defaultPrevented === true,
              targetModeId: event.target?.closest?.('[data-mode-id]')?.dataset?.modeId ?? null,
              activeModeId: document.activeElement?.dataset?.modeId ?? null,
            });
          };
          for (const type of ['focusin', 'keydown', 'keypress', 'keyup', 'click']) {
            document.addEventListener(type, (event) => record(type, event), true);
          }
          return true;
        })()
        """
    )
    client.evaluate("document.activeElement?.blur(); true")
    focused_mode = None
    for _ in range(6):
        dispatch_key(client, key="Tab", code="Tab", windows_key_code=9)
        focused_mode = client.evaluate(
            "document.activeElement?.dataset?.modeId ?? null"
        )
        if focused_mode in MODE_TYPES:
            break
    assert focused_mode in MODE_TYPES, focused_mode
    focus_state = client.evaluate(
        """
        ({
          tagName: document.activeElement?.tagName ?? null,
          modeId: document.activeElement?.dataset?.modeId ?? null,
          focusVisible: document.activeElement?.matches(':focus') === true,
        })
        """
    )
    assert focus_state == {
        "tagName": "BUTTON",
        "modeId": focused_mode,
        "focusVisible": True,
    }, focus_state
    dispatch_space_activation(client)
    try:
        wait_for(
            client,
            "document.readyState === 'complete' && Boolean(window.__vesperaController)",
            timeout=10.0,
        )
    except AssertionError as error:
        telemetry = client.evaluate(
            """
            ({
              href: location.href,
              activeTagName: document.activeElement?.tagName ?? null,
              activeModeId: document.activeElement?.dataset?.modeId ?? null,
              events: window.__vesperaKeyboardTelemetry ?? [],
            })
            """
        )
        raise AssertionError(
            "Trusted CDP Space activation did not navigate the focused mode button: "
            f"{json.dumps(telemetry, ensure_ascii=False)}"
        ) from error
    assert_opened_mode(client, focused_mode)
    return_to_hub(client, NO_SAVES)
    return {
        "input": "CDP_TAB_SPACE",
        "activationKey": "Space",
        "focusedMode": focused_mode,
        "navigated": True,
    }


def local_resource_evidence(
    client: CdpClient,
    *,
    required_suffixes: tuple[str, ...],
) -> dict:
    performance_resources = client.evaluate(
        "performance.getEntriesByType('resource').map((entry) => entry.name)"
    )
    network_resources = [
        event.get("params", {}).get("request", {}).get("url", "")
        for event in client.events
        if event.get("method") == "Network.requestWillBeSent"
    ]
    resources = sorted(set(performance_resources + network_resources))
    assert resources, "Electron runtime did not load any local resources"
    assert all(resource.startswith("vespera://app/") for resource in resources), resources
    for suffix in required_suffixes:
        assert any(resource.split("?", 1)[0].endswith(suffix) for resource in resources), (
            suffix,
            resources,
        )
    external_requests = [
        request_url for request_url in network_resources
        if request_url.startswith(("http://", "https://", "ws://", "wss://"))
    ]
    assert not external_requests, external_requests
    return {
        "resourceCount": len(resources),
        "networkRequestCount": len(network_resources),
        "allLocal": True,
        "requiredSuffixes": list(required_suffixes),
    }


def assert_hub_offline_runtime(client: CdpClient) -> dict:
    offline_conditions = {
        "offline": True,
        "latency": 0,
        "downloadThroughput": 0,
        "uploadThroughput": 0,
    }
    online_conditions = {
        "offline": False,
        "latency": 0,
        "downloadThroughput": -1,
        "uploadThroughput": -1,
    }
    client.command("Network.emulateNetworkConditions", offline_conditions)
    try:
        client.events.clear()
        client.command("Page.reload", {"ignoreCache": True})
        wait_for(client, "document.readyState === 'complete' && Boolean(window.__vesperaModeHub)")
        hub_evidence = local_resource_evidence(
            client,
            required_suffixes=("/styles.css", "/src/main.js"),
        )
        assert_mode_hub(client, NO_SAVES)

        client.events.clear()
        open_mode_by_click(client, "showcase")
        assert client.evaluate(
            "window.__vesperaController.data.prototype_mode.type"
        ) == "SHOWCASE"
        mode_evidence = local_resource_evidence(
            client,
            required_suffixes=(
                "/styles.css",
                "/src/main.js",
                "/data/prototype_v1.json",
            ),
        )
        return_to_hub(client, NO_SAVES)
        return {
            "networkState": "OFFLINE_DURING_HUB_AND_MODE_LOAD",
            "clickDelegateMode": "showcase",
            "hub": hub_evidence,
            "mode": mode_evidence,
            "returnedToHubWhileOffline": True,
        }
    finally:
        client.command("Network.emulateNetworkConditions", online_conditions)


def assert_security_boundary(client: CdpClient):
    surface = client.evaluate(
        """
        ({
          nodeGlobals: [typeof window.require, typeof window.process, typeof window.module],
          desktopKeys: Object.keys(window.vesperaDesktop).sort(),
          storageKeys: Object.keys(window.vesperaDesktop.storage).sort(),
          storageReady: window.vesperaDesktop.storageReady,
          authority: window.vesperaDesktop.storageStatus().authority,
          csp: document.querySelector('meta[http-equiv="Content-Security-Policy"]')?.content ?? null,
          usesFileStorage: window.__vesperaController.recordStorage !== window.localStorage,
        })
        """
    )
    assert surface["nodeGlobals"] == ["undefined", "undefined", "undefined"], surface
    assert surface["desktopKeys"] == [
        "platform",
        "storage",
        "storageError",
        "storageReady",
        "storageStatus",
    ], surface
    assert surface["storageKeys"] == ["getItem", "removeItem", "setItem"], surface
    assert surface["storageReady"] is True and surface["authority"] == "FILE", surface
    assert surface["usesFileStorage"] is True, surface
    assert "script-src 'self'" in surface["csp"], surface

    denied = client.evaluate(
        """
        Promise.all([
          fetch('vespera://app/package.json').then((response) => response.status),
          fetch('vespera://app/desktop/main.cjs').then((response) => response.status),
          fetch('vespera://app/%2e%2e/package.json').then((response) => response.status),
        ])
        """
    )
    assert denied == [404, 404, 404], denied
    before = client.evaluate("location.href")
    client.evaluate("location.assign('data:text/html,<h1>blocked</h1>'); true")
    time.sleep(0.4)
    assert client.evaluate("location.href") == before
    assert client.evaluate("window.open('data:text/html,popup') === null") is True


def save_showcase_checkpoint(client: CdpClient) -> dict:
    navigate(client, mode_url("showcase", TEST_SEED))
    result = client.evaluate(
        """
        (() => {
          const controller = window.__vesperaController;
          const started = controller.start();
          const saved = controller.saveCheckpoint();
          return {
            started,
            saved: Boolean(saved),
            phase: controller.state.phase,
            seed: controller.state.runSeed,
            localKeys: Object.keys(localStorage).filter((key) => key.startsWith('vespera.hotel')),
            fileAuthority: controller.recordStorage !== localStorage,
          };
        })()
        """
    )
    assert result == {
        "started": True,
        "saved": True,
        "phase": "TUTORIAL",
        "seed": TEST_SEED,
        "localKeys": [],
        "fileAuthority": True,
    }, result
    return result


def save_mode_checkpoint(client: CdpClient, mode_id: str) -> dict:
    assert mode_id in {"campaign", "endless"}, mode_id
    seed, expected_phase = MODE_CHECKPOINTS[mode_id]
    navigate(client, mode_url(mode_id, seed))
    result = client.evaluate(
        f"""
        (() => {{
          const controller = window.__vesperaController;
          const started = controller.start();
          const advanced = {json.dumps(mode_id)} === 'campaign'
            ? controller.confirmNewGame()
            : null;
          const saved = controller.saveCheckpoint();
          return {{
            modeType: controller.data.prototype_mode.type,
            started,
            advanced,
            saved: Boolean(saved),
            phase: controller.state.phase,
            seed: controller.state.runSeed,
            localKeys: Object.keys(localStorage).filter((key) => key.startsWith('vespera.hotel')),
            fileAuthority: controller.recordStorage !== localStorage,
          }};
        }})()
        """
    )
    expected = {
        "modeType": MODE_TYPES[mode_id],
        "started": True,
        "advanced": True if mode_id == "campaign" else None,
        "saved": True,
        "phase": expected_phase,
        "seed": seed,
        "localKeys": [],
        "fileAuthority": True,
    }
    assert result == expected, result
    return result


def assert_save_files(user_data: Path):
    root = save_root(user_data)
    expected = [
        root / "profile.v1.json",
        root / "profile.v1.json.bak",
    ]
    for mode_id in MODE_TYPES:
        expected.extend(
            [
                root / f"active-run.v2.{mode_id}.json",
                root / f"active-run.v2.{mode_id}.json.bak",
            ]
        )
    for file_path in expected:
        assert file_path.is_file(), file_path
    active_files = {
        path.name
        for path in root.glob("active-run.v2.*.json")
        if not path.name.endswith(".bak")
    }
    assert active_files == {
        f"active-run.v2.{mode_id}.json" for mode_id in MODE_TYPES
    }, active_files
    for mode_id, (seed, phase) in MODE_CHECKPOINTS.items():
        envelope = json.loads(
            (root / f"active-run.v2.{mode_id}.json").read_text(encoding="utf-8")
        )
        assert envelope["file_schema_version"] == 1, envelope
        assert envelope["storage_key"] == f"vespera.hotel.active-run.v2.{mode_id}", envelope
        assert envelope["deleted"] is False, envelope
        payload = json.loads(envelope["payload"])
        assert payload["schema_version"] == 6, payload
        assert payload["mode_id"] == MODE_TYPES[mode_id], payload
        assert payload["state"]["runSeed"] == seed, payload
        assert payload["state"]["phase"] == phase, payload


def capture_active_artifact(client: CdpClient, user_data: Path, mode_id: str) -> dict:
    storage_key = f"{ACTIVE_RUN_STORAGE_PREFIX}.{mode_id}"
    payload = client.evaluate(
        f"window.vesperaDesktop.storage.getItem({json.dumps(storage_key)})"
    )
    assert isinstance(payload, str) and payload, (mode_id, payload)
    primary = active_run_path(user_data, mode_id)
    backup = Path(f"{primary}.bak")
    assert primary.is_file(), primary
    assert backup.is_file(), backup
    envelope = json.loads(primary.read_text(encoding="utf-8"))
    assert envelope["storage_key"] == storage_key, envelope
    assert envelope["deleted"] is False, envelope
    assert envelope["payload"] == payload, envelope
    parsed_payload = json.loads(payload)
    seed, phase = MODE_CHECKPOINTS[mode_id]
    assert parsed_payload["mode_id"] == MODE_TYPES[mode_id], parsed_payload
    assert parsed_payload["state"]["runSeed"] == seed, parsed_payload
    assert parsed_payload["state"]["phase"] == phase, parsed_payload
    return {
        "payload": payload,
        "primary_bytes": primary.read_bytes(),
        "backup_bytes": backup.read_bytes(),
    }


def assert_active_tombstone(user_data: Path, mode_id: str):
    storage_key = f"{ACTIVE_RUN_STORAGE_PREFIX}.{mode_id}"
    primary = active_run_path(user_data, mode_id)
    for file_path in (primary, Path(f"{primary}.bak")):
        assert file_path.is_file(), file_path
        envelope = json.loads(file_path.read_text(encoding="utf-8"))
        assert envelope["file_schema_version"] == 1, envelope
        assert envelope["storage_key"] == storage_key, envelope
        assert envelope["deleted"] is True, envelope
        assert envelope["payload"] is None, envelope


def assert_run_record_file(
    user_data: Path,
    *,
    mode_type: str,
    ending_id: str,
    outcome: str,
    seed: int,
) -> dict:
    record_path = save_root(user_data) / "run-records.v1.json"
    backup_path = Path(f"{record_path}.bak")
    for file_path in (record_path, backup_path):
        assert file_path.is_file(), file_path
    envelope = json.loads(record_path.read_text(encoding="utf-8"))
    assert envelope["file_schema_version"] == 1, envelope
    assert envelope["storage_key"] == RUN_RECORD_STORAGE_KEY, envelope
    assert envelope["deleted"] is False, envelope
    records = json.loads(envelope["payload"])
    assert len(records) == 1, records
    record = records[0]
    assert record["schema_version"] == 6, record
    assert record["mode_id"] == mode_type, record
    assert record["ending_id"] == ending_id, record
    assert record["outcome"] == outcome, record
    assert record["run_seed"] == seed, record
    return record


def assert_resume(client: CdpClient, mode_id: str):
    seed, phase = MODE_CHECKPOINTS[mode_id]
    resumed = client.evaluate(
        """
        (() => {
          const controller = window.__vesperaController;
          const before = controller.pendingCheckpoint?.state ?? null;
          const resumed = controller.resumeRun();
          return {
            modeType: controller.data.prototype_mode.type,
            pendingSeed: before?.runSeed ?? null,
            pendingPhase: before?.phase ?? null,
            resumed,
            liveSeed: controller.state.runSeed,
            livePhase: controller.state.phase,
            localKeys: Object.keys(localStorage).filter((key) => key.startsWith('vespera.hotel')),
          };
        })()
        """
    )
    assert resumed == {
        "modeType": MODE_TYPES[mode_id],
        "pendingSeed": seed,
        "pendingPhase": phase,
        "resumed": True,
        "liveSeed": seed,
        "livePhase": phase,
        "localKeys": [],
    }, resumed


def seed_campaign_and_endless(client: CdpClient):
    assert_mode_hub(client, NO_SAVES)
    save_mode_checkpoint(client, "campaign")
    save_mode_checkpoint(client, "endless")
    navigate_hub(client)
    assert_mode_hub(client, CAMPAIGN_ENDLESS_SAVES)


def complete_campaign_terminal_isolation(client: CdpClient, user_data: Path) -> dict:
    open_mode(client, "campaign")
    assert_resume(client, "campaign")
    endless_before = capture_active_artifact(client, user_data, "endless")
    result = client.evaluate(
        """
        (() => {
          const controller = window.__vesperaController;
          const record = controller.completeRun();
          return {
            phase: controller.state.phase,
            activeCleared: window.vesperaDesktop.storage.getItem(
              'vespera.hotel.active-run.v2.campaign'
            ) === null,
            archiveCount: JSON.parse(window.vesperaDesktop.storage.getItem(
              'vespera.hotel.run-records.v1'
            ) ?? '[]').length,
            record,
          };
        })()
        """
    )
    record = result["record"]
    assert result["phase"] == "FINAL", result
    assert result["activeCleared"] is True, result
    assert result["archiveCount"] == 1, result
    assert record["mode_id"] == "CAMPAIGN", record
    assert record["ending_id"] == "CAMPAIGN_INTERRUPTED", record
    assert record["outcome"] == "FAILURE", record
    assert record["run_seed"] == CAMPAIGN_SEED, record

    endless_after = capture_active_artifact(client, user_data, "endless")
    assert endless_after == endless_before, "Campaign terminalization changed endless save bytes"
    assert_active_tombstone(user_data, "campaign")
    file_record = assert_run_record_file(
        user_data,
        mode_type="CAMPAIGN",
        ending_id="CAMPAIGN_INTERRUPTED",
        outcome="FAILURE",
        seed=CAMPAIGN_SEED,
    )
    assert file_record["record_id"] == record["record_id"], (file_record, record)

    navigate_hub(client)
    assert_mode_hub(
        client,
        {"campaign": "NONE", "endless": "AVAILABLE", "showcase": "NONE"},
    )
    return record


def complete_endless_terminal_isolation(client: CdpClient, user_data: Path) -> dict:
    open_mode(client, "endless")
    assert_resume(client, "endless")
    campaign_before = capture_active_artifact(client, user_data, "campaign")
    result = client.evaluate(
        """
        (() => {
          const controller = window.__vesperaController;
          const syntheticResult = operation => ({
            valid: true,
            placementScore: 0,
            reputationDelta: -1,
            baseFees: 0,
            tips: 0,
            income: 0,
            grade: 'TERMINAL-ISOLATION',
            acceptedGuestIds: [],
            rejectedGuestIds: [],
            canceledGuestIds: [],
            placements: {},
            guestScores: {},
            guestReviews: [],
            emergencyReport: null,
            operation,
          });
          if (!controller.startEndlessSeason()) {
            throw new Error('Could not start terminal-isolation endless season');
          }
          if (controller.state.phase === 'RELIC_OFFER' && !controller.skipDisplayRelicOffer()) {
            throw new Error('Could not skip terminal-isolation relic offer');
          }
          for (let offset = 0; offset < controller.endlessSeasonLength; offset += 1) {
            controller.completeNight(syntheticResult(offset + 1));
            if (controller.state.phase !== 'RESULT') {
              throw new Error(`Operation ${offset + 1} did not reach RESULT`);
            }
            if (!controller.continueAfterResult()) {
              throw new Error(`Operation ${offset + 1} result did not continue`);
            }
            if (offset < controller.endlessSeasonLength - 1 && !controller.finishUpgrade()) {
              throw new Error(`Operation ${offset + 1} upgrade did not finish`);
            }
          }
          const audit = controller.state.endlessAuditReport;
          if (controller.state.phase !== 'ENDLESS_AUDIT' || audit?.passed !== false) {
            throw new Error('Terminal-isolation endless audit did not fail');
          }
          const closed = controller.closeEndlessRun();
          return {
            closed,
            auditPassed: audit.passed,
            completedOperations: controller.state.endlessCompletedOperations,
            phase: controller.state.phase,
            activeCleared: window.vesperaDesktop.storage.getItem(
              'vespera.hotel.active-run.v2.endless'
            ) === null,
            archiveCount: JSON.parse(window.vesperaDesktop.storage.getItem(
              'vespera.hotel.run-records.v1'
            ) ?? '[]').length,
            record: controller.state.runRecord,
          };
        })()
        """
    )
    record = result["record"]
    assert result["closed"] is True, result
    assert result["auditPassed"] is False, result
    assert result["completedOperations"] == 5, result
    assert result["phase"] == "FINAL", result
    assert result["activeCleared"] is True, result
    assert result["archiveCount"] == 1, result
    assert record["mode_id"] == "ENDLESS", record
    assert record["ending_id"] == "ENDLESS_HOTEL_CLOSED", record
    assert record["outcome"] == "FAILURE", record
    assert record["run_seed"] == ENDLESS_SEED, record
    assert record["endless_closure_reason"] == "AUDIT_TARGET_MISSED", record

    campaign_after = capture_active_artifact(client, user_data, "campaign")
    assert campaign_after == campaign_before, "Endless terminalization changed campaign save bytes"
    assert_active_tombstone(user_data, "endless")
    file_record = assert_run_record_file(
        user_data,
        mode_type="ENDLESS",
        ending_id="ENDLESS_HOTEL_CLOSED",
        outcome="FAILURE",
        seed=ENDLESS_SEED,
    )
    assert file_record["record_id"] == record["record_id"], (file_record, record)
    assert file_record["endless_closure_reason"] == "AUDIT_TARGET_MISSED", file_record

    navigate_hub(client)
    assert_mode_hub(
        client,
        {"campaign": "AVAILABLE", "endless": "NONE", "showcase": "NONE"},
    )
    return record


def run_terminal_isolation_case(
    *,
    kind: str,
    executable: Path,
    app_dir: Path,
    temp_root: Path,
    terminal_mode: str,
) -> dict:
    assert terminal_mode in {"campaign", "endless"}, terminal_mode
    unaffected_mode = "endless" if terminal_mode == "campaign" else "campaign"
    user_data = temp_root / f"{terminal_mode}-terminal-user-data"
    expected_statuses = {
        "campaign": "NONE" if terminal_mode == "campaign" else "AVAILABLE",
        "endless": "NONE" if terminal_mode == "endless" else "AVAILABLE",
        "showcase": "NONE",
    }
    expected_ending = (
        "CAMPAIGN_INTERRUPTED"
        if terminal_mode == "campaign"
        else "ENDLESS_HOTEL_CLOSED"
    )

    terminal = ElectronProcess(
        kind=kind,
        executable=executable,
        app_dir=app_dir,
        user_data=user_data,
        log_path=temp_root / f"{terminal_mode}-terminal.log",
    )
    print(f"electron-test {kind}: {terminal_mode} terminal isolation ready", flush=True)
    try:
        seed_campaign_and_endless(terminal.client)
        record = (
            complete_campaign_terminal_isolation(terminal.client, user_data)
            if terminal_mode == "campaign"
            else complete_endless_terminal_isolation(terminal.client, user_data)
        )
    finally:
        terminal.stop()
    time.sleep(1.0)

    assert_active_tombstone(user_data, terminal_mode)
    file_record = assert_run_record_file(
        user_data,
        mode_type=MODE_TYPES[terminal_mode],
        ending_id=expected_ending,
        outcome="FAILURE",
        seed=MODE_CHECKPOINTS[terminal_mode][0],
    )
    assert file_record["record_id"] == record["record_id"], (file_record, record)

    verifier = ElectronProcess(
        kind=kind,
        executable=executable,
        app_dir=app_dir,
        user_data=user_data,
        log_path=temp_root / f"{terminal_mode}-terminal-restart.log",
    )
    print(
        f"electron-test {kind}: {terminal_mode} terminal restart ready",
        flush=True,
    )
    try:
        assert_mode_hub(verifier.client, expected_statuses)
        open_mode(verifier.client, unaffected_mode)
        assert_resume(verifier.client, unaffected_mode)
    finally:
        verifier.stop()
    time.sleep(1.0)
    assert_active_tombstone(user_data, terminal_mode)
    assert_run_record_file(
        user_data,
        mode_type=MODE_TYPES[terminal_mode],
        ending_id=expected_ending,
        outcome="FAILURE",
        seed=MODE_CHECKPOINTS[terminal_mode][0],
    )
    return {
        "terminal_mode": terminal_mode,
        "ending_id": expected_ending,
        "unaffected_mode": unaffected_mode,
        "unaffected_resumed": True,
    }


def assert_record_write_failure_preserves_checkpoint(client: CdpClient):
    outcomes = client.evaluate(
        """
        (async () => {
          const [{ GameController }, { createCampaignGreyboxData }] = await Promise.all([
            import('./src/state.js'),
            import('./src/data.js'),
          ]);
          const data = createCampaignGreyboxData(window.__vesperaController.data);
          const activeKey = 'vespera.hotel.active-run.v2.campaign';
          const recordKey = 'vespera.hotel.run-records.v1';
          const probe = failureMode => {
            const values = new Map();
            const storage = {
              getItem: key => values.has(key) ? values.get(key) : null,
              setItem: (key, value) => values.set(key, value),
              removeItem: key => values.delete(key),
            };
            const controller = new GameController(data, { seed: 5151, storage });
            controller.start();
            controller.confirmNewGame();
            const save = controller.saveCheckpoint();
            const activeBefore = storage.getItem(activeKey);
            const originalSetItem = storage.setItem;
            storage.setItem = (key, value) => {
              if (key !== recordKey) return originalSetItem(key, value);
              if (failureMode === 'throw') throw new Error('injected write failure');
              return undefined;
            };
            let errorCode = null;
            try {
              controller.completeRun();
            } catch (error) {
              errorCode = error.code ?? null;
            }
            const reopened = new GameController(data, { seed: 9999, storage });
            const checkpointDetected = reopened.hasCheckpoint();
            const resumed = reopened.resumeRun();
            return {
              failureMode,
              saveCreated: Boolean(save),
              errorCode,
              activeExact: storage.getItem(activeKey) === activeBefore,
              archiveCount: JSON.parse(storage.getItem(recordKey) ?? '[]').length,
              runRecordDeferred: controller.state.runRecord === null,
              checkpointDetected,
              resumed,
              resumedPhase: reopened.state.phase,
              resumedSeed: reopened.state.runSeed,
            };
          };
          return [probe('throw'), probe('silent-noop')];
        })()
        """
    )
    for outcome in outcomes:
        assert outcome == {
            "failureMode": outcome["failureMode"],
            "saveCreated": True,
            "errorCode": "RUN_RECORD_WRITE_FAILED",
            "activeExact": True,
            "archiveCount": 0,
            "runRecordDeferred": True,
            "checkpointDetected": True,
            "resumed": True,
            "resumedPhase": "STORY",
            "resumedSeed": 5151,
        }, outcome


def run_spike(kind: str, executable: Path, app_dir: Path, temp_parent: Path):
    assert executable.is_file(), executable
    if kind == "dev":
        assert (app_dir / "package.json").is_file(), app_dir
    workspace_temp = temp_parent.resolve()
    workspace_temp.mkdir(parents=True, exist_ok=True)
    temp_root = (workspace_temp / f"{kind}-{os.getpid()}-{uuid.uuid4().hex[:10]}").resolve()
    if workspace_temp not in temp_root.parents:
        raise RuntimeError(f"Unsafe Electron test directory: {temp_root}")
    temp_root.mkdir(parents=True)
    run_error: BaseException | None = None
    try:
        user_data = temp_root / "user-data"
        isolated_user_data = temp_root / "isolated-user-data"

        write_diagnostics: dict | None = None
        hub_layout: dict | None = None
        offline_runtime: dict | None = None
        keyboard_navigation: dict | None = None
        first = ElectronProcess(
            kind=kind,
            executable=executable,
            app_dir=app_dir,
            user_data=user_data,
            log_path=temp_root / "first.log",
            outer_size=(960, 600),
        )
        print(f"electron-test {kind}: first instance ready", flush=True)
        try:
            assert first.client.evaluate("location.href").startswith(APP_URL)
            assert_mode_hub(first.client, NO_SAVES)
            offline_runtime = assert_hub_offline_runtime(first.client)
            keyboard_navigation = assert_keyboard_mode_navigation(first.client)
            hub_layout = assert_mode_hub_layout(first.client, (960, 600))

            open_mode(first.client, "showcase")
            assert_security_boundary(first.client)
            return_to_hub(first.client, NO_SAVES)
            save_showcase_checkpoint(first.client)
            assert_record_write_failure_preserves_checkpoint(first.client)

            showcase_only = {
                "campaign": "NONE",
                "endless": "NONE",
                "showcase": "AVAILABLE",
            }
            navigate_hub(first.client)
            assert_mode_hub(first.client, showcase_only)
            open_mode(first.client, "campaign")
            return_to_hub(first.client, showcase_only)
            save_mode_checkpoint(first.client, "campaign")

            campaign_and_showcase = {
                "campaign": "AVAILABLE",
                "endless": "NONE",
                "showcase": "AVAILABLE",
            }
            navigate_hub(first.client)
            assert_mode_hub(first.client, campaign_and_showcase)
            open_mode(first.client, "endless")
            return_to_hub(first.client, campaign_and_showcase)
            save_mode_checkpoint(first.client, "endless")
            navigate_hub(first.client)
            assert_mode_hub(first.client, ALL_SAVES)

            write_diagnostics = first.client.evaluate("window.vesperaDesktop.storageStatus()")
            assert write_diagnostics["mutationCount"] >= 6, write_diagnostics
            assert isinstance(write_diagnostics["writeP95Ms"], (int, float)), write_diagnostics
            assert write_diagnostics["lastErrorCode"] is None, write_diagnostics
            print(
                f"electron-test {kind}: hub/offline/security/mode-save checks passed",
                flush=True,
            )
        finally:
            first.stop()
        time.sleep(1.0)
        assert_save_files(user_data)

        second = ElectronProcess(
            kind=kind,
            executable=executable,
            app_dir=app_dir,
            user_data=user_data,
            log_path=temp_root / "second.log",
        )
        print(f"electron-test {kind}: restart instance ready", flush=True)
        try:
            assert_mode_hub(second.client, ALL_SAVES)
            for mode_id in ("campaign", "endless", "showcase"):
                open_mode(second.client, mode_id)
                return_to_hub(second.client, ALL_SAVES)
                open_mode(second.client, mode_id)
                assert_resume(second.client, mode_id)
                navigate_hub(second.client)
                assert_mode_hub(second.client, ALL_SAVES)
            diagnostics = second.client.evaluate("window.vesperaDesktop.storageStatus()")
            assert diagnostics["authority"] == "FILE"
            assert diagnostics["lastErrorCode"] is None
        finally:
            second.stop()
        time.sleep(1.0)
        assert_save_files(user_data)

        isolated = ElectronProcess(
            kind=kind,
            executable=executable,
            app_dir=app_dir,
            user_data=isolated_user_data,
            log_path=temp_root / "isolated.log",
        )
        print(f"electron-test {kind}: isolated instance ready", flush=True)
        try:
            assert_mode_hub(isolated.client, NO_SAVES)
            for mode_id in MODE_TYPES:
                open_mode(isolated.client, mode_id)
                assert isolated.client.evaluate(
                    "window.__vesperaController.pendingCheckpoint === null"
                ) is True
                return_to_hub(isolated.client, NO_SAVES)
        finally:
            isolated.stop()

        terminal_isolation_results = [
            run_terminal_isolation_case(
                kind=kind,
                executable=executable,
                app_dir=app_dir,
                temp_root=temp_root,
                terminal_mode=terminal_mode,
            )
            for terminal_mode in ("campaign", "endless")
        ]
    except BaseException as error:
        run_error = error
        raise
    finally:
        try:
            remove_test_tree(temp_root, workspace_temp)
        except BaseException as cleanup_error:
            if run_error is None:
                raise
            run_error.add_note(f"Electron workspace cleanup also failed: {cleanup_error!r}")

    print(
        json.dumps(
            {
                "status": "PASS",
                "kind": kind,
                "offline": offline_runtime,
                "mode_hub": True,
                "mode_hub_interactions": {
                    "mouseClickDelegate": offline_runtime["clickDelegateMode"],
                    "keyboard": keyboard_navigation,
                },
                "mode_hub_layout": hub_layout,
                "security_boundary": True,
                "file_save_restart": True,
                "mode_save_coexistence": True,
                "mode_resume": {
                    mode_id: {"seed": seed, "phase": phase}
                    for mode_id, (seed, phase) in MODE_CHECKPOINTS.items()
                },
                "return_to_hub_preserves_saves": True,
                "terminal_mode_isolation": terminal_isolation_results,
                "record_failure_checkpoint_preserved": True,
                "user_data_isolation": True,
                "storage_mutation_count": write_diagnostics["mutationCount"],
                "storage_write_p95_ms": write_diagnostics["writeP95Ms"],
                "storage_write_max_ms": write_diagnostics["writeMaxMs"],
            },
            ensure_ascii=False,
        )
    )


def main():
    parser = argparse.ArgumentParser(description="Validate the Vespera Electron spike")
    parser.add_argument("--kind", choices=("dev", "packaged"), required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--app-dir", type=Path, default=ROOT)
    parser.add_argument(
        "--temp-parent",
        type=Path,
        default=Path(tempfile.gettempdir()) / "vespera-electron-tests",
        help="Dedicated parent for disposable Electron profiles (defaults to the OS temp drive).",
    )
    args = parser.parse_args()
    run_spike(args.kind, args.executable, args.app_dir, args.temp_parent)


if __name__ == "__main__":
    main()
