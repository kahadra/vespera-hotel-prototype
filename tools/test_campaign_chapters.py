from __future__ import annotations

import argparse
import json

from smoke_browser import CdpClient, debugger_target, wait_for


def run(base_url: str, debug_port: int):
    target = debugger_target(debug_port)
    client = CdpClient(target["webSocketDebuggerUrl"])
    try:
        client.command("Runtime.enable")
        client.command("Log.enable")
        client.command("Page.enable")
        client.command("Page.navigate", {"url": base_url})
        wait_for(client, "document.readyState === 'complete'")

        contracts = client.evaluate(
            """
            (async () => {
              const {
                validateCampaignChapterSchedule,
                validateCampaignChapterPrefix,
                compileCampaignChapters,
                campaignChapterForStage,
              } = await import('./src/campaign-chapters.js');
              const { loadGameData, createCampaignGreyboxData } = await import('./src/data.js');

              const source = await loadGameData();
              const data = createCampaignGreyboxData(source);
              const calendars = data.campaign.calendar;
              const schedules = data.campaign.chapters;
              const options = {
                calendarValidationOptions: {
                  rankIds: data.campaign.formal_rank_ids,
                  speciesIds: data.campaign.formal_species.map(species => species.id),
                },
              };
              const base = compileCampaignChapters(
                schedules.base_year,
                calendars.base_year,
                options,
              );
              const extended = compileCampaignChapters(
                schedules.true_extension,
                calendars.true_extension,
                options,
              );
              const sampleStages = [1, 7, 8, 14, 15, 28, 29, 42, 43, 56, 57, 70];
              const samples = Object.fromEntries(sampleStages.map(stage => {
                const schedule = stage <= 56 ? schedules.base_year : schedules.true_extension;
                const calendar = stage <= 56 ? calendars.base_year : calendars.true_extension;
                return [stage, campaignChapterForStage(schedule, calendar, stage, options)];
              }));
              const prefixPreserved = validateCampaignChapterPrefix(
                schedules.base_year,
                schedules.true_extension,
                calendars.base_year,
                calendars.true_extension,
                options,
              );
              const rejects = callback => {
                try {
                  callback();
                  return false;
                } catch {
                  return true;
                }
              };
              const clone = value => JSON.parse(JSON.stringify(value));
              const invalid = {};
              const invalidCase = (name, mutate) => {
                const schedule = clone(schedules.base_year);
                mutate(schedule);
                invalid[name] = rejects(() => validateCampaignChapterSchedule(
                  schedule,
                  calendars.base_year,
                  options,
                ));
              };
              invalidCase('wrongCalendarId', schedule => { schedule.calendar_id = 'WRONG'; });
              invalidCase('wrongTotal', schedule => { schedule.total_stages = 55; });
              invalidCase('gap', schedule => { schedule.chapters[1].start_stage = 9; });
              invalidCase('overlap', schedule => { schedule.chapters[1].start_stage = 7; });
              invalidCase('wrongSeason', schedule => { schedule.chapters[2].season_id = 'SPRING'; });
              invalidCase('duplicateId', schedule => { schedule.chapters[1].id = schedule.chapters[0].id; });
              invalidCase('nonSequentialNumber', schedule => { schedule.chapters[1].number = 3; });
              invalidCase('finalRecovery', schedule => {
                schedule.chapters[4].debt_settlement.recovery_eligible = true;
              });
              invalidCase('noneWithTarget', schedule => {
                schedule.chapters[0].debt_settlement = {
                  kind: 'NONE',
                  target_id: 'BAD',
                  recovery_eligible: false,
                };
              });
              invalidCase('missingCoverage', schedule => { schedule.chapters.pop(); });
              invalidCase('badEnd', schedule => { schedule.chapters[0].end_stage = 0; });
              invalid.outOfRangeStage = rejects(() => campaignChapterForStage(
                schedules.base_year,
                calendars.base_year,
                57,
                options,
              ));
              const driftedExtended = clone(schedules.true_extension);
              driftedExtended.chapters[0].label = 'Drifted';
              invalid.prefixDrift = rejects(() => validateCampaignChapterPrefix(
                schedules.base_year,
                driftedExtended,
                calendars.base_year,
                calendars.true_extension,
                options,
              ));

              return {
                status: schedules.status,
                manualExtraPaymentPhase: schedules.manual_extra_payment_phase,
                baseMeta: {
                  type: base.type,
                  id: base.id,
                  version: base.version,
                  calendarId: base.calendarId,
                  totalStages: base.totalStages,
                },
                extendedMeta: {
                  type: extended.type,
                  id: extended.id,
                  version: extended.version,
                  calendarId: extended.calendarId,
                  totalStages: extended.totalStages,
                },
                baseChapters: base.chapters,
                extendedChapters: extended.chapters,
                samples,
                prefixPreserved,
                baseValid: validateCampaignChapterSchedule(
                  schedules.base_year,
                  calendars.base_year,
                  options,
                ),
                extendedValid: validateCampaignChapterSchedule(
                  schedules.true_extension,
                  calendars.true_extension,
                  options,
                ),
                deterministic: JSON.stringify(base) === JSON.stringify(
                  compileCampaignChapters(schedules.base_year, calendars.base_year, options),
                ),
                invalid,
              };
            })()
            """
        )

        assert contracts["status"] == "PROVISIONAL", contracts
        assert contracts["manualExtraPaymentPhase"] == "RESULT_REVIEW", contracts
        assert contracts["baseMeta"] == {
            "type": "COMPILED_CAMPAIGN_CHAPTER_SCHEDULE",
            "id": "CAMPAIGN_BASE_CHAPTERS",
            "version": 1,
            "calendarId": "CAMPAIGN_BASE_YEAR",
            "totalStages": 56,
        }, contracts
        assert contracts["extendedMeta"] == {
            "type": "COMPILED_CAMPAIGN_CHAPTER_SCHEDULE",
            "id": "CAMPAIGN_TRUE_CHAPTERS",
            "version": 1,
            "calendarId": "CAMPAIGN_TRUE_EXTENSION",
            "totalStages": 70,
        }, contracts

        base = contracts["baseChapters"]
        assert [(item["number"], item["startStage"], item["endStage"], item["seasonId"])
                for item in base] == [
            (1, 1, 7, "SPRING"),
            (2, 8, 14, "SPRING"),
            (3, 15, 28, "SUMMER"),
            (4, 29, 42, "AUTUMN"),
            (5, 43, 56, "WINTER"),
        ], base
        assert [item["debtSettlement"]["kind"] for item in base] == [
            "CUMULATIVE_MINIMUM",
            "CUMULATIVE_MINIMUM",
            "CUMULATIVE_MINIMUM",
            "CUMULATIVE_MINIMUM",
            "FINAL_CLEARANCE",
        ], base
        assert all(item["hidden"] is False for item in base), base
        assert [item["debtSettlement"]["recoveryEligible"] for item in base] == [
            True, True, True, True, False
        ], base

        extended = contracts["extendedChapters"]
        assert extended[:5] == base, extended
        assert extended[5] == {
            "id": "CHAPTER_6_TRUE_EXTENSION",
            "number": 6,
            "label": "추가 계절",
            "startStage": 57,
            "endStage": 70,
            "stageCount": 14,
            "seasonId": "TRUE_EXTENSION_SEASON",
            "hidden": True,
            "entryGateId": "BASE_DEBT_CLEARED_AT_STAGE_56",
            "debtSettlement": {
                "kind": "NONE",
                "targetId": None,
                "recoveryEligible": False,
            },
        }, extended[5]

        samples = contracts["samples"]
        assert samples["1"]["isChapterStart"] is True
        assert samples["1"]["isChapterEnd"] is False
        assert samples["7"]["isChapterEnd"] is True
        assert samples["7"]["debtSettlement"]["kind"] == "CUMULATIVE_MINIMUM"
        assert samples["8"]["chapter"]["number"] == 2
        assert samples["8"]["chapter"]["day"] == 1
        assert samples["14"]["isChapterEnd"] is True
        assert samples["15"]["chapter"]["number"] == 3
        assert samples["29"]["chapter"]["number"] == 4
        assert samples["43"]["chapter"]["number"] == 5
        assert samples["56"]["debtSettlement"]["kind"] == "FINAL_CLEARANCE"
        assert samples["57"]["chapter"]["number"] == 6
        assert samples["57"]["chapter"]["hidden"] is True
        assert samples["57"]["entryGateId"] == "BASE_DEBT_CLEARED_AT_STAGE_56"
        assert samples["70"]["debtSettlement"]["kind"] == "NONE"

        assert contracts["baseValid"] is True
        assert contracts["extendedValid"] is True
        assert contracts["prefixPreserved"] is True
        assert contracts["deterministic"] is True
        assert all(contracts["invalid"].values()), contracts["invalid"]

        exception_events = [
            event
            for event in client.events
            if event.get("method") in {"Runtime.exceptionThrown", "Log.entryAdded"}
            and (
                event.get("method") == "Runtime.exceptionThrown"
                or event.get("params", {}).get("entry", {}).get("level") == "error"
            )
        ]
        assert not exception_events, exception_events

        return {
            "status": "PASS",
            "mode": "CAMPAIGN_CHAPTER_CONTRACT",
            "base_boundaries": [[item["startStage"], item["endStage"]] for item in base],
            "true_boundary": [extended[5]["startStage"], extended[5]["endStage"]],
            "manual_extra_payment_phase": contracts["manualExtraPaymentPhase"],
            "day_56_gate": samples["56"]["debtSettlement"]["kind"],
            "day_57_gate": samples["57"]["entryGateId"],
            "invalid_cases": len(contracts["invalid"]),
            "prefix_preserved": contracts["prefixPreserved"],
        }
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description="Validate the provisional campaign chapter contract.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--debug-port", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.url, args.debug_port), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
