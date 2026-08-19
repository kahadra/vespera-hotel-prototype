from __future__ import annotations

import argparse
import base64
import json
import time
import urllib.request
from pathlib import Path

import websocket


ROOT = Path(__file__).resolve().parents[1]

ROUTES = {
    "SOUNDPROOFING": {
        "accepted_applicants": ["G02_MORROW", "G03_LADY_NOX", "G06_GARR"],
        "rejected_applicant": "G05_FEN",
        "placements": {
            "G01_LUNE": "F1-A",
            "G04_ARU": "F1-C",
            "G02_MORROW": "F1-B",
            "G03_LADY_NOX": "F3-B",
            "G06_GARR": "F2-A",
        },
        "preference": 26,
        "evaluation": 60,
    },
    "LOUNGE": {
        "accepted_applicants": ["G02_MORROW", "G03_LADY_NOX", "G06_GARR"],
        "rejected_applicant": "G05_FEN",
        "placements": {
            "G01_LUNE": "F1-A",
            "G04_ARU": "F1-C",
            "G02_MORROW": "F1-B",
            "G03_LADY_NOX": "F3-B",
            "G06_GARR": "F2-C",
        },
        "preference": 28,
        "evaluation": 63,
    },
    "SECRET_PASSAGE": {
        "accepted_applicants": ["G05_FEN", "G03_LADY_NOX", "G06_GARR"],
        "rejected_applicant": "G02_MORROW",
        "placements": {
            "G01_LUNE": "F3-B",
            "G04_ARU": "F1-B",
            "G05_FEN": "F3-C",
            "G03_LADY_NOX": "F2-A",
            "G06_GARR": "F2-C",
        },
        "preference": 28,
        "evaluation": 62,
    },
}


class CdpClient:
    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(
            ws_url,
            timeout=8,
            origin="http://127.0.0.1",
            suppress_origin=True,
        )
        self.next_id = 1
        self.events = []

    def close(self):
        self.ws.close()

    def command(self, method: str, params: dict | None = None):
        command_id = self.next_id
        self.next_id += 1
        self.ws.send(json.dumps({"id": command_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == command_id:
                if "error" in message:
                    raise RuntimeError(f"CDP {method} failed: {message['error']}")
                return message.get("result", {})
            self.events.append(message)

    def evaluate(self, expression: str):
        result = self.command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"])
        return result.get("result", {}).get("value")

    def click(self, selector: str):
        encoded = json.dumps(selector)
        clicked = self.evaluate(
            f"""
            (() => {{
              const element = document.querySelector({encoded});
              if (!element) return false;
              element.click();
              return true;
            }})()
            """
        )
        if not clicked:
            raise AssertionError(f"Element not found: {selector}")

    def body_text(self):
        return self.evaluate("document.body.innerText") or ""


def debugger_target(port: int, timeout: float = 10.0):
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/json"
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                targets = json.load(response)
            pages = [target for target in targets if target.get("type") == "page"]
            if pages:
                return pages[0]
        except Exception as error:  # browser may still be starting
            last_error = error
        time.sleep(0.15)
    raise RuntimeError(f"Could not find Edge debugging target: {last_error}")


def wait_for(client: CdpClient, expression: str, timeout: float = 10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if client.evaluate(expression):
            return
        time.sleep(0.1)
    raise AssertionError(f"Timed out waiting for: {expression}")


def place(client: CdpClient, guest_id: str, room_id: str):
    client.click(f'[data-guest-id="{guest_id}"]')
    client.click(f'[data-room-id="{room_id}"]')


def require_text(client: CdpClient, expected: str):
    text = client.body_text()
    if expected not in text:
        raise AssertionError(f"Expected text not found: {expected}\n--- BODY ---\n{text[:4000]}")


def capture(client: CdpClient, path: Path):
    image = client.command("Page.captureScreenshot", {"format": "png"})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(image["data"]))


def run(url: str, port: int, screenshot: Path, facility_id: str, width: int, height: int):
    route = ROUTES[facility_id]
    target = debugger_target(port)
    client = CdpClient(target["webSocketDebuggerUrl"])
    try:
        client.command("Runtime.enable")
        client.command("Page.enable")
        client.command("Log.enable")
        client.command(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
        )
        client.command("Page.navigate", {"url": url})
        wait_for(client, "document.readyState === 'complete'")
        wait_for(client, "Boolean(document.querySelector('[data-action=\"start\"]'))")
        require_text(client, "베스페라 호텔의")
        require_text(client, "종족별 숙박 조건")
        capture(client, screenshot.with_name(f"{screenshot.stem}-title.png"))

        client.click('[data-action="open-handbook"]')
        require_text(client, "호텔 공통 규정")
        client.click('[data-action="handbook-tab"][data-tab="species"]')
        require_text(client, "햇빛이 들지 않는 객실")
        client.click('[data-action="handbook-tab"][data-tab="rank"]')
        require_text(client, "아직 만나지 않은 등급")
        capture(client, screenshot.with_name(f"{screenshot.stem}-handbook-locked.png"))
        client.command("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape"})
        wait_for(client, "!document.querySelector('.handbook-overlay')")

        client.click('[data-action="start"]')
        require_text(client, "첫 손님을 맞이하세요")

        place(client, "G01_LUNE", "F3-B")
        place(client, "G02_MORROW", "F1-B")
        place(client, "G04_ARU", "F1-C")
        place(client, "G05_FEN", "F3-C")
        require_text(client, "19 / 19")
        capture(client, screenshot.with_name(f"{screenshot.stem}-night1.png"))
        client.click('[data-action="finish-night"]')
        require_text(client, "영업 평가")
        require_text(client, "35")

        client.click('[data-action="continue-shop"]')
        require_text(client, "다음 영업의 규칙을 고르세요")
        client.click(f'[data-action="buy-facility"][data-facility-id="{facility_id}"]')
        require_text(client, "누구를 맞이하시겠습니까?")
        client.click('[data-action="open-handbook"]')
        client.click('[data-action="handbook-tab"][data-tab="rank"]')
        require_text(client, "양옆 객실이 비어 있을 것")
        capture(client, screenshot.with_name(f"{screenshot.stem}-handbook-unlocked.png"))
        client.click('[data-action="close-handbook"]')

        client.click(
            f'[data-action="reject"][data-guest-id="{route["rejected_applicant"]}"]'
        )
        for guest_id in route["accepted_applicants"]:
            client.click(f'[data-action="accept"][data-guest-id="{guest_id}"]')
        capture(client, screenshot.with_name(f"{screenshot.stem}-reservation.png"))
        client.click('[data-action="confirm-reservation"]')
        require_text(client, "선택한 손님에게 객실을 주세요")

        for guest_id, room_id in route["placements"].items():
            place(client, guest_id, room_id)
        require_text(client, f'{route["preference"]} / {route["preference"]}')
        capture(client, screenshot.with_name(f"{screenshot.stem}-night2.png"))
        client.click('[data-action="finish-night"]')
        require_text(client, "두 번의 영업을 마쳤습니다")
        require_text(client, f'{route["evaluation"]} / {route["evaluation"]}')

        capture(client, screenshot)

        exception_events = [
            event
            for event in client.events
            if event.get("method") in {"Runtime.exceptionThrown", "Log.entryAdded"}
            and (
                event.get("method") == "Runtime.exceptionThrown"
                or event.get("params", {}).get("entry", {}).get("level") == "error"
            )
        ]
        if exception_events:
            raise AssertionError(f"Browser errors detected: {exception_events}")

        return {
            "status": "PASS",
            "night1_evaluation": 35,
            "facility": facility_id,
            "rejected": route["rejected_applicant"],
            "night2_preference": route["preference"],
            "night2_evaluation": route["evaluation"],
            "viewport": f"{width}x{height}",
            "screenshot": str(screenshot),
        }
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--debug-port", type=int, default=9223)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument(
        "--facility",
        choices=sorted(ROUTES),
        default="SECRET_PASSAGE",
    )
    parser.add_argument(
        "--screenshot",
        type=Path,
        default=ROOT / "artifacts" / "final.png",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            run(args.url, args.debug_port, args.screenshot, args.facility, args.width, args.height),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
