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
                timeout=45.0,
                allowed_url_prefixes=("vespera://app/",),
            )
            self.client = CdpClient(target["webSocketDebuggerUrl"])
            self.client.command("Page.enable")
            self.client.command("Runtime.enable")
            self.client.command("Network.enable")
            wait_for(self.client, "Boolean(window.__vesperaController)")
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


def assert_offline_runtime(client: CdpClient):
    client.events.clear()
    client.command(
        "Network.emulateNetworkConditions",
        {
            "offline": True,
            "latency": 0,
            "downloadThroughput": 0,
            "uploadThroughput": 0,
        },
    )
    client.command("Page.reload", {"ignoreCache": True})
    wait_for(client, "document.readyState === 'complete' && Boolean(window.__vesperaController)")
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
    required_suffixes = (
        "/styles.css",
        "/src/main.js",
        "/data/prototype_v1.json",
    )
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
    client.command(
        "Network.emulateNetworkConditions",
        {
            "offline": False,
            "latency": 0,
            "downloadThroughput": -1,
            "uploadThroughput": -1,
        },
    )


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
    navigate(client, f"{APP_URL}?seed={TEST_SEED}")
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


def assert_save_files(user_data: Path):
    save_root = user_data / "save-data" / "v1" / "profiles" / "local"
    expected = [
        save_root / "profile.v1.json",
        save_root / "profile.v1.json.bak",
        save_root / "active-run.v2.showcase.json",
        save_root / "active-run.v2.showcase.json.bak",
    ]
    for file_path in expected:
        assert file_path.is_file(), file_path
    envelope = json.loads((save_root / "active-run.v2.showcase.json").read_text(encoding="utf-8"))
    assert envelope["file_schema_version"] == 1
    assert envelope["storage_key"] == "vespera.hotel.active-run.v2.showcase"
    assert envelope["deleted"] is False
    payload = json.loads(envelope["payload"])
    assert payload["schema_version"] == 6
    assert payload["state"]["runSeed"] == TEST_SEED
    assert payload["state"]["phase"] == "TUTORIAL"


def assert_resume(client: CdpClient):
    resumed = client.evaluate(
        """
        (() => {
          const controller = window.__vesperaController;
          const before = controller.pendingCheckpoint?.state ?? null;
          const resumed = controller.resumeRun();
          return {
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
        "pendingSeed": TEST_SEED,
        "pendingPhase": "TUTORIAL",
        "resumed": True,
        "liveSeed": TEST_SEED,
        "livePhase": "TUTORIAL",
        "localKeys": [],
    }, resumed


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
        first = ElectronProcess(
            kind=kind,
            executable=executable,
            app_dir=app_dir,
            user_data=user_data,
            log_path=temp_root / "first.log",
        )
        print(f"electron-test {kind}: first instance ready", flush=True)
        try:
            assert first.client.evaluate("location.href").startswith(APP_URL)
            assert_offline_runtime(first.client)
            assert_security_boundary(first.client)
            save_showcase_checkpoint(first.client)
            assert_record_write_failure_preserves_checkpoint(first.client)
            write_diagnostics = first.client.evaluate("window.vesperaDesktop.storageStatus()")
            assert write_diagnostics["mutationCount"] >= 2, write_diagnostics
            assert isinstance(write_diagnostics["writeP95Ms"], (int, float)), write_diagnostics
            assert write_diagnostics["lastErrorCode"] is None, write_diagnostics
            print(f"electron-test {kind}: offline/security/durability checks passed", flush=True)
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
            assert_resume(second.client)
            diagnostics = second.client.evaluate("window.vesperaDesktop.storageStatus()")
            assert diagnostics["authority"] == "FILE"
            assert diagnostics["lastErrorCode"] is None
        finally:
            second.stop()
        time.sleep(1.0)

        isolated = ElectronProcess(
            kind=kind,
            executable=executable,
            app_dir=app_dir,
            user_data=isolated_user_data,
            log_path=temp_root / "isolated.log",
        )
        print(f"electron-test {kind}: isolated instance ready", flush=True)
        try:
            assert isolated.client.evaluate(
                "window.__vesperaController.pendingCheckpoint === null"
            ) is True
        finally:
            isolated.stop()
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
                "offline": True,
                "security_boundary": True,
                "file_save_restart": True,
                "record_failure_checkpoint_preserved": True,
                "user_data_isolation": True,
                "seed": TEST_SEED,
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
