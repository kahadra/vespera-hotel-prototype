from __future__ import annotations

import argparse
import json
import urllib.parse

from smoke_browser import CdpClient, assert_action_screen_layout, debugger_target, wait_for


ACTIVE_RUN_KEYS = {
    "campaign": "vespera.hotel.active-run.v2.campaign",
    "endless": "vespera.hotel.active-run.v2.endless",
    "showcase": "vespera.hotel.active-run.v2.showcase",
}
PROFILE_KEY = "vespera.hotel.profile.v1"
RUN_RECORDS_KEY = "vespera.hotel.run-records.v1"


def endless_url(base_url: str, seed: int) -> str:
    parsed = urllib.parse.urlparse(base_url)
    query = urllib.parse.parse_qs(parsed.query)
    query["mode"] = ["endless"]
    query["seed"] = [str(seed)]
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query, doseq=True)))


def state(client: CdpClient):
    return client.evaluate("JSON.parse(JSON.stringify(window.__vesperaController.state))")


def render_live(client: CdpClient):
    return client.evaluate(
        "import('./src/render.js').then(({renderApp}) => { "
        "renderApp(document.querySelector('#app'), window.__vesperaController); return true; })"
    )


def synthetic_result(operation: int, reputation: int, income: int = 0):
    return {
        "valid": True,
        "placementScore": 0,
        "reputationDelta": reputation,
        "baseFees": income,
        "tips": 0,
        "income": income,
        "grade": "GREYBOX",
        "acceptedGuestIds": [],
        "rejectedGuestIds": [],
        "canceledGuestIds": [],
        "placements": {},
        "guestScores": {},
        "guestReviews": [],
        "emergencyReport": None,
        "testOperation": operation,
    }


def inject_result(client: CdpClient, operation: int, reputation: int, income: int = 0):
    result = synthetic_result(operation, reputation, income)
    completed = client.evaluate(
        "(() => { "
        f"window.__vesperaController.completeNight({json.dumps(result, ensure_ascii=False)}); "
        "return window.__vesperaController.state.phase === 'RESULT'; })()"
    )
    assert completed is True
    render_live(client)


def storage_presence(client: CdpClient):
    return client.evaluate(
        "({"
        + ",".join(
            f"{name}: Boolean(localStorage.getItem({json.dumps(key)}))"
            for name, key in ACTIVE_RUN_KEYS.items()
        )
        + "})"
    )


def complete_season(client: CdpClient, reputation: int, first_operation: int):
    season_number = state(client)["endlessSeasonIndex"] + 1
    for offset in range(5):
        operation = first_operation + offset
        before = state(client)
        assert before["phase"] in {"PLACEMENT", "RESERVATION"}, before
        assert before["endlessSeasonNightIndex"] == offset, before
        assert before["endlessSeasonIndex"] + 1 == season_number, before
        inject_result(client, operation, reputation)
        after_result = state(client)
        assert len(after_result["nightResults"]) == operation, after_result
        assert after_result["nightResults"][-1]["testOperation"] == operation, after_result
        client.click('[data-action="continue-result"]')
        after_continue = state(client)
        if offset < 4:
            assert after_continue["phase"] == "UPGRADE", after_continue
            client.click('[data-action="finish-upgrade"]')
        else:
            assert after_continue["phase"] == "ENDLESS_AUDIT", after_continue
    return state(client)["endlessAuditReport"]


def long_run_retention_contract(client: CdpClient, seasons: int = 40):
    return client.evaluate(
        f"""
        import('./src/state.js').then(({{GameController}}) => {{
          const values = new Map();
          const storage = {{
            getItem: key => values.has(key) ? values.get(key) : null,
            setItem: (key, value) => values.set(key, String(value)),
            removeItem: key => values.delete(key),
          }};
          const game = new GameController(window.__vesperaController.data, {{ seed: 9191, storage }});
          const result = operation => ({{
            valid: true,
            placementScore: 0,
            reputationDelta: 1,
            baseFees: 0,
            tips: 0,
            income: 0,
            grade: 'RETENTION',
            acceptedGuestIds: [],
            rejectedGuestIds: [],
            canceledGuestIds: [],
            placements: {{}},
            guestScores: {{}},
            guestReviews: [],
            emergencyReport: null,
            operation,
          }});
          game.start();
          for (let season = 0; season < {seasons}; season += 1) {{
            if (game.state.phase !== 'ENDLESS_BRIEFING') throw new Error('briefing transition failed');
            game.startEndlessSeason();
            if (game.state.phase === 'RELIC_OFFER') game.skipDisplayRelicOffer();
            for (let offset = 0; offset < game.endlessSeasonLength; offset += 1) {{
              game.completeNight(result(game.state.endlessCompletedOperations + 1));
              game.continueAfterResult();
              if (offset < game.endlessSeasonLength - 1) game.finishUpgrade();
            }}
            if (!game.state.endlessAuditReport?.passed) throw new Error('retention audit failed');
            if (season < {seasons} - 1) game.advanceEndlessSeason();
          }}
          const save = game.saveCheckpoint();
          return {{
            completed: game.state.endlessCompletedOperations,
            retainedResults: game.state.nightResults.length,
            omittedResults: game.state.endlessResultHistoryOmittedCount,
            retainedAudits: game.state.endlessAuditHistory.length,
            omittedAudits: game.state.endlessAuditHistoryOmittedCount,
            cleared: game.state.endlessAuditPassedCount,
            runFame: game.state.endlessRunFame,
            riskTier: game.state.endlessRiskTier,
            saved: Boolean(save),
            saveBytes: JSON.stringify(save).length,
          }};
        }})
        """
    )


def negative_best_audit_contract(client: CdpClient):
    return client.evaluate(
        """
        import('./src/state.js').then(({GameController}) => {
          const values = new Map();
          const storage = {
            getItem: key => values.has(key) ? values.get(key) : null,
            setItem: (key, value) => values.set(key, String(value)),
            removeItem: key => values.delete(key),
          };
          const game = new GameController(window.__vesperaController.data, { seed: 8181, storage });
          const result = operation => ({
            valid: true,
            placementScore: 0,
            reputationDelta: -1,
            baseFees: 0,
            tips: 0,
            income: 0,
            grade: 'NEGATIVE-BEST',
            acceptedGuestIds: [],
            rejectedGuestIds: [],
            canceledGuestIds: [],
            placements: {},
            guestScores: {},
            guestReviews: [],
            emergencyReport: null,
            operation,
          });
          game.start();
          game.startEndlessSeason();
          if (game.state.phase === 'RELIC_OFFER') game.skipDisplayRelicOffer();
          for (let offset = 0; offset < game.endlessSeasonLength; offset += 1) {
            game.completeNight(result(offset + 1));
            game.continueAfterResult();
            if (offset < game.endlessSeasonLength - 1) game.finishUpgrade();
          }
          if (game.state.endlessAuditReport?.passed) throw new Error('negative audit unexpectedly passed');
          game.closeEndlessRun();
          return {
            stateBest: game.state.endlessBestAuditScore,
            profileBest: game.profile.endless.best_audit_score,
            recordBest: game.state.runRecord.metrics.endless_best_audit_score,
          };
        })
        """
    )


def run(base_url: str, debug_port: int, seed: int):
    target = debugger_target(debug_port)
    client = CdpClient(target["webSocketDebuggerUrl"])
    url = endless_url(base_url, seed)
    try:
        client.command("Runtime.enable")
        client.command("Log.enable")
        client.command("Page.enable")
        client.command(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1280, "height": 720, "deviceScaleFactor": 1, "mobile": False},
        )
        client.command("Page.navigate", {"url": "about:blank"})
        wait_for(client, "document.readyState === 'complete'")
        client.command("Page.navigate", {"url": url})
        wait_for(client, "Boolean(window.__vesperaController)")
        client.evaluate("localStorage.clear(); true")
        client.command("Page.navigate", {"url": "about:blank"})
        wait_for(client, "document.readyState === 'complete'")
        client.command("Page.navigate", {"url": url})
        wait_for(client, "Boolean(window.__vesperaController)")

        initial = state(client)
        assert initial["phase"] == "TITLE", initial
        assert client.evaluate("window.__vesperaController.data.prototype_mode.type") == "ENDLESS"
        assert client.evaluate("document.querySelector('[data-screen=\"endless-title\"]') !== null") is True
        data_contract = client.evaluate(
            "({targets:[0,1,2,3].map(index => "
            "Math.min(window.__vesperaController.data.endless.audit.max_target, "
            "window.__vesperaController.data.endless.audit.initial_target + "
            "window.__vesperaController.data.endless.audit.target_step_per_cleared_season * index)),"
            "specialInvites:window.__vesperaController.data.scenarios.flatMap(item => item.special_invite_guest_ids ?? []),"
            "showcaseOnlyReferences:window.__vesperaController.data.scenarios.flatMap(item => "
            "[...(item.fixed_guests ?? []), ...(item.applicant_pool ?? [])]).filter(id => "
            "window.__vesperaController.data.indexes.guests[id]?.showcase_only === true)})"
        )
        assert data_contract == {
            "targets": [0, 2, 4, 4],
            "specialInvites": [],
            "showcaseOnlyReferences": [],
        }, data_contract

        client.click('[data-action="start"]')
        briefing = state(client)
        assert briefing["phase"] == "ENDLESS_BRIEFING", briefing
        assert briefing["endlessSeasonIndex"] == 0, briefing
        assert briefing["endlessAuditTarget"] == 0, briefing
        briefing_contract = client.evaluate(
            "(() => {"
            "const screen = document.querySelector('[data-screen=\"endless-briefing\"]');"
            "const cards = [...screen.querySelectorAll('.audit-contract-grid article')];"
            "return {"
            "screen: Boolean(screen),"
            "seasonLength: cards[0]?.innerText ?? '',"
            "auditTarget: cards[1]?.innerText ?? '',"
            "policy: screen.querySelector('.audit-policy-card')?.innerText ?? '',"
            "startAction: Boolean(screen.querySelector('[data-action=\"start-endless-season\"]'))"
            "};"
            "})()"
        )
        assert briefing_contract["screen"] is True, briefing_contract
        assert "5" in briefing_contract["seasonLength"], briefing_contract
        assert "0" in briefing_contract["auditTarget"], briefing_contract
        assert "PROVISIONAL" in briefing_contract["policy"], briefing_contract
        assert briefing_contract["startAction"] is True, briefing_contract
        briefing_layout = assert_action_screen_layout(
            client,
            720,
            "endless briefing",
            expected_phase="ENDLESS_BRIEFING",
            screen_selector='[data-screen="endless-briefing"]',
            action_selector='[data-action="start-endless-season"]',
        )

        client.click('[data-action="start-endless-season"]')
        relic_offer = state(client)
        assert relic_offer["phase"] == "RELIC_OFFER", relic_offer
        assert len(relic_offer["pendingDisplayRelicOffer"]["relicIds"]) == 3, relic_offer
        client.click('[data-action="skip-display-relic"]')
        skipped = state(client)
        assert skipped["phase"] in {"PLACEMENT", "RESERVATION"}, skipped
        assert skipped["ownedDisplayRelicIds"] == [], skipped
        assert skipped["displayRelicOfferIndex"] == 1, skipped

        # ENDLESS retry is a direct functional rewind. It must discard the
        # appended result and restore the pre-operation economy/progression.
        before_retry = state(client)
        inject_result(client, operation=1, reputation=1, income=7)
        result_before_retry = state(client)
        assert len(result_before_retry["nightResults"]) == 1, result_before_retry
        assert result_before_retry["gold"] == before_retry["gold"] + 7, result_before_retry
        assert result_before_retry["hotelReputation"] == before_retry["hotelReputation"] + 1
        client.click('[data-action="retry-stage"]')
        retried = state(client)
        assert retried["phase"] == before_retry["phase"], retried
        assert retried["nightResults"] == before_retry["nightResults"], retried
        assert retried["gold"] == before_retry["gold"], retried
        assert retried["hotelReputation"] == before_retry["hotelReputation"], retried
        assert retried["endlessOverallNightIndex"] == 0, retried
        assert retried["foresightRetryCount"] == 1, retried

        pass_report = complete_season(client, reputation=1, first_operation=1)
        passed_audit = state(client)
        assert pass_report == passed_audit["endlessAuditHistory"][0], passed_audit
        assert pass_report["passed"] is True, pass_report
        assert pass_report["operations"] == 5, pass_report
        assert pass_report["score"] == 5, pass_report
        assert pass_report["target"] == 0, pass_report
        assert passed_audit["endlessAuditPassedCount"] == 1, passed_audit
        assert passed_audit["endlessRunFame"] == 1, passed_audit
        audit_dom = client.evaluate(
            "(() => { const el = document.querySelector('[data-screen=\"endless-audit\"]'); "
            "return {score: el?.dataset.auditScore, target: el?.dataset.auditTarget, "
            "passed: el?.dataset.auditPassed, advance: Boolean(el?.querySelector('[data-action=\"advance-endless-season\"]'))}; })()"
        )
        assert audit_dom == {"score": "5", "target": "0", "passed": "true", "advance": True}, audit_dom
        passed_audit_layout = assert_action_screen_layout(
            client,
            720,
            "endless passed audit",
            expected_phase="ENDLESS_AUDIT",
            screen_selector='[data-screen="endless-audit"]',
            action_selector='[data-action="advance-endless-season"]',
        )

        saved_mode_keys = storage_presence(client)
        assert saved_mode_keys == {"campaign": False, "endless": True, "showcase": False}, saved_mode_keys
        saved_audit = client.evaluate(
            f"JSON.parse(localStorage.getItem({json.dumps(ACTIVE_RUN_KEYS['endless'])}))"
        )
        assert saved_audit["state"]["phase"] == "ENDLESS_AUDIT", saved_audit
        assert saved_audit["state"]["endlessAuditReport"] == pass_report, saved_audit

        # A real reload must return to TITLE, expose the checkpoint, and restore
        # the exact finalized audit evidence rather than recalculating it.
        client.command("Page.navigate", {"url": "about:blank"})
        wait_for(client, "document.readyState === 'complete'")
        client.command("Page.navigate", {"url": url})
        wait_for(client, "Boolean(window.__vesperaController)")
        assert state(client)["phase"] == "TITLE"
        assert client.evaluate("window.__vesperaController.hasCheckpoint()") is True
        client.click('[data-action="resume"]')
        resumed_audit = state(client)
        assert resumed_audit["phase"] == "ENDLESS_AUDIT", resumed_audit
        assert resumed_audit["endlessAuditReport"] == pass_report, resumed_audit
        assert resumed_audit["endlessAuditHistory"] == [pass_report], resumed_audit

        client.click('[data-action="advance-endless-season"]')
        season_two = state(client)
        assert season_two["phase"] == "ENDLESS_BRIEFING", season_two
        assert season_two["endlessSeasonIndex"] == 1, season_two
        assert season_two["endlessSeasonNightIndex"] == 0, season_two
        assert season_two["endlessSeasonStartResultIndex"] == 5, season_two
        assert season_two["endlessOverallNightIndex"] == 5, season_two
        assert len(season_two["nightResults"]) == 5, season_two
        assert season_two["endlessAuditPassedCount"] == 1, season_two
        assert season_two["endlessAuditTarget"] == 2, season_two
        assert season_two["endlessRiskTier"] == 2, season_two
        assert season_two["endlessRunFame"] == 1, season_two

        client.click('[data-action="start-endless-season"]')
        second_offer = state(client)
        assert second_offer["phase"] == "RELIC_OFFER", second_offer
        assert len(second_offer["pendingDisplayRelicOffer"]["relicIds"]) == 3, second_offer
        client.click('[data-action="skip-display-relic"]')
        assert state(client)["ownedDisplayRelicIds"] == []
        assert client.evaluate("window.__vesperaController.progressionStage") == 6

        fail_report = complete_season(client, reputation=-1, first_operation=6)
        failed_audit = state(client)
        assert fail_report["passed"] is False, fail_report
        assert fail_report["operations"] == 5, fail_report
        assert fail_report["score"] == -5, fail_report
        assert fail_report["target"] == 2, fail_report
        assert failed_audit["endlessAuditPassedCount"] == 1, failed_audit
        assert len(failed_audit["nightResults"]) == 10, failed_audit
        assert len(failed_audit["endlessAuditHistory"]) == 2, failed_audit
        assert client.evaluate(
            "document.querySelector('[data-screen=\"endless-audit\"]')?.dataset.auditPassed"
        ) == "false"
        failed_audit_layout = assert_action_screen_layout(
            client,
            720,
            "endless failed audit",
            expected_phase="ENDLESS_AUDIT",
            screen_selector='[data-screen="endless-audit"]',
            action_selector='[data-action="close-endless-run"]',
        )

        client.click('[data-action="close-endless-run"]')
        final = state(client)
        record = final["runRecord"]
        metrics = record["metrics"]
        assert final["phase"] == "FINAL", final
        assert final["endlessClosed"] is True, final
        assert final["endlessClosureReason"] == "AUDIT_TARGET_MISSED", final
        assert record["ending_id"] == "ENDLESS_HOTEL_CLOSED", record
        assert record["outcome"] == "FAILURE", record
        assert record["endless_closure_reason"] == "AUDIT_TARGET_MISSED", record
        assert len(record["endless_audit_history"]) == 2, record
        assert metrics["endless_survived_nights"] == 10, metrics
        assert metrics["endless_seasons_cleared"] == 1, metrics
        assert metrics["endless_last_audit_score"] == -5, metrics
        assert metrics["endless_last_audit_target"] == 2, metrics
        assert final["recordArchiveCount"] >= 1, final
        assert client.evaluate("document.querySelector('[data-screen=\"endless-closure\"]') !== null") is True
        final_layout = assert_action_screen_layout(
            client,
            720,
            "endless closure",
            expected_phase="FINAL",
            screen_selector='[data-screen="endless-closure"]',
            action_selector='[data-action="restart"]',
        )

        profile = client.evaluate(f"JSON.parse(localStorage.getItem({json.dumps(PROFILE_KEY)}))")
        assert profile["endless"] == {
            "best_survived_nights": 10,
            "best_cleared_seasons": 1,
            "best_audit_score": 5,
            "best_run_fame": 1,
        }, profile
        records = client.evaluate(f"JSON.parse(localStorage.getItem({json.dumps(RUN_RECORDS_KEY)}))")
        assert records[0]["record_id"] == record["record_id"], records
        assert storage_presence(client) == {"campaign": False, "endless": False, "showcase": False}

        negative_best = negative_best_audit_contract(client)
        assert negative_best == {
            "stateBest": -5,
            "profileBest": -5,
            "recordBest": -5,
        }, negative_best

        retention = long_run_retention_contract(client)
        assert retention["completed"] == 200, retention
        assert retention["retainedResults"] <= 20, retention
        assert retention["omittedResults"] + retention["retainedResults"] == 200, retention
        assert retention["retainedAudits"] <= 12, retention
        assert retention["omittedAudits"] + retention["retainedAudits"] == 40, retention
        assert retention["cleared"] == 40, retention
        assert retention["runFame"] == 40, retention
        assert retention["saved"] is True, retention

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
            "mode": "ENDLESS",
            "seed": seed,
            "briefing": {
                "season_length": 5,
                "published_target": briefing["endlessAuditTarget"],
                "policy_visible": True,
            },
            "display_relic_skipped": skipped["ownedDisplayRelicIds"] == [],
            "retry_rollback": {
                "results_after_retry": len(retried["nightResults"]),
                "retry_count": retried["foresightRetryCount"],
            },
            "pass_audit": {
                "score": pass_report["score"],
                "target": pass_report["target"],
                "operations": pass_report["operations"],
                "resumed_from_save": resumed_audit["endlessAuditReport"] == pass_report,
            },
            "season_two": {
                "cumulative_results_before_operations": len(season_two["nightResults"]),
                "target": season_two["endlessAuditTarget"],
                "risk_tier": season_two["endlessRiskTier"],
            },
            "failure_audit": {
                "score": fail_report["score"],
                "target": fail_report["target"],
                "ending_id": record["ending_id"],
                "survived_nights": metrics["endless_survived_nights"],
            },
            "profile_best": profile["endless"],
            "negative_only_best_audit": negative_best,
            "mode_save_isolation": saved_mode_keys,
            "long_run_retention": retention,
            "layout_1280x720": {
                "briefing_action_bottom": briefing_layout["action"]["bottom"],
                "passed_audit_action_bottom": passed_audit_layout["action"]["bottom"],
                "failed_audit_action_bottom": failed_audit_layout["action"]["bottom"],
                "final_action_bottom": final_layout["action"]["bottom"],
            },
        }
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8767/index.html")
    parser.add_argument("--debug-port", type=int, default=9230)
    parser.add_argument("--seed", type=int, default=5252)
    args = parser.parse_args()
    print(json.dumps(run(args.url, args.debug_port, args.seed), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
