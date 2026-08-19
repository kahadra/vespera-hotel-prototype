from __future__ import annotations

import argparse
import json
import time

from smoke_browser import CdpClient, debugger_target, place, require_text, wait_for


def state(client: CdpClient):
    return client.evaluate("JSON.parse(JSON.stringify(window.__vesperaController.state))")


def run(url: str, port: int):
    target = debugger_target(port)
    client = CdpClient(target["webSocketDebuggerUrl"])
    try:
        client.command("Runtime.enable")
        client.command("Page.enable")
        client.command("Page.navigate", {"url": url})
        wait_for(client, "document.readyState === 'complete'")
        wait_for(client, "Boolean(window.__vesperaController)")

        # The learning route is untimed and can advance by solving its two-guest puzzle.
        client.click('[data-action="start"]')
        tutorial = state(client)
        assert tutorial["phase"] == "TUTORIAL"
        assert tutorial["serviceTimerMs"] is None
        require_text(client, "시간 제한 없음")
        place(client, "G01_LUNE", "F3-B")
        place(client, "G02_MORROW", "F1-B")
        client.click('[data-action="finish-night"]')
        started = state(client)
        assert started["phase"] == "NIGHT1_PLACEMENT"
        assert 118_000 <= started["serviceTimerMs"] <= 120_000

        # The first placement is free; moving an assigned guest costs five seconds.
        place(client, "G01_LUNE", "F3-B")
        first = state(client)
        assert first["relocationCount"] == 0
        place(client, "G01_LUNE", "F2-B")
        moved = state(client)
        relocation_cost = first["serviceTimerMs"] - moved["serviceTimerMs"]
        assert moved["relocationCount"] == 1
        assert 4_800 <= relocation_cost <= 5_800, relocation_cost

        # The handbook is reference material, so reading it pauses the deadline.
        client.click('[data-action="open-handbook"]')
        paused_at = state(client)["serviceTimerMs"]
        time.sleep(1.1)
        paused_after = state(client)["serviceTimerMs"]
        assert abs(paused_at - paused_after) <= 50, (paused_at, paused_after)
        client.click('[data-action="close-handbook"]')

        # Let the real interval expire the last fraction of a second.
        client.evaluate("window.__vesperaController.state.serviceTimerMs = 100")
        wait_for(client, "window.__vesperaController.state.phase === 'NIGHT1_RESULT'", timeout=3)
        result_state = state(client)
        report = result_state["night1Result"]["emergencyReport"]
        assert report["timedOut"] is True
        assert result_state["night1Result"]["valid"] is True
        assert len(report["autoAssignedGuestIds"]) >= 1
        require_text(client, "마감 후 프런트 긴급 배정")
        require_text(client, "자동 배정")

        body = client.body_text()
        assert "최고 19" not in body
        assert "19 / 19" not in body

        # Synthetic impossible late reservation proves the fallback cancellation path.
        client.command("Page.navigate", {"url": url})
        wait_for(client, "Boolean(window.__vesperaController)")
        client.click('[data-action="skip-tutorial"]')
        client.evaluate(
            """
            (() => {
              const controller = window.__vesperaController;
              const impossible = {
                ...controller.data.indexes.guests.G01_LUNE,
                id: 'G_TEST_IMPOSSIBLE',
                name: 'Test Impossible',
                hard_constraints: ['noisy', 'quiet', 'sunny'].map(attribute => ({
                  type: 'ROOM_NOT_HAS', attribute,
                })),
              };
              controller.data.indexes.guests[impossible.id] = impossible;
              controller.state.acceptedGuestIds.push(impossible.id);
              controller.state.serviceTimerMs = 100;
              return true;
            })()
            """
        )
        wait_for(client, "window.__vesperaController.state.phase === 'NIGHT1_RESULT'", timeout=3)
        canceled_state = state(client)
        canceled = canceled_state["night1Result"]["canceledGuestIds"]
        assert canceled == ["G_TEST_IMPOSSIBLE"], canceled
        assert canceled_state["night1Result"]["reputationDelta"] == 1

        return {
            "status": "PASS",
            "tutorial": "untimed-complete",
            "first_service_seconds": 120,
            "relocation_cost_seconds": 5,
            "handbook_pauses_timer": True,
            "timeout_phase": result_state["phase"],
            "auto_assigned": report["autoAssignedGuestIds"],
            "force_canceled": canceled,
            "emergency_preference": result_state["night1Result"]["placementScore"],
        }
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--debug-port", type=int, default=9223)
    args = parser.parse_args()
    print(json.dumps(run(args.url, args.debug_port), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
