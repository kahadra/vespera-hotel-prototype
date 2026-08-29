from __future__ import annotations

import argparse
import json
import urllib.parse

from smoke_browser import CdpClient, debugger_target, wait_for


def campaign_url(base_url: str) -> str:
    parsed = urllib.parse.urlparse(base_url)
    query = urllib.parse.parse_qs(parsed.query)
    query["mode"] = ["campaign"]
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query, doseq=True)))


def run(base_url: str, debug_port: int, seed: int):
    target = debugger_target(debug_port)
    client = CdpClient(target["webSocketDebuggerUrl"])
    try:
        client.command("Runtime.enable")
        client.command("Log.enable")
        client.command("Page.enable")
        client.command("Page.navigate", {"url": campaign_url(base_url)})
        wait_for(client, "Boolean(window.__vesperaController)")

        contracts = client.evaluate(
            f"""
            (async () => {{
              const [dataModule, stateModule, saveModule, progressModule] = await Promise.all([
                import('./src/data.js'),
                import('./src/state.js'),
                import('./src/save.js'),
                import('./src/campaign-progress.js'),
              ]);
              const {{ loadGameData, createIndexes }} = dataModule;
              const {{ GameController }} = stateModule;
              const {{
                ACTIVE_RUN_STORAGE_KEY,
                ACTIVE_RUN_STORAGE_PREFIX,
                activeRunStorageKey,
                createRunSave,
                readActiveRunSave,
              }} = saveModule;
              const {{ FORMAL_CAMPAIGN_PROGRESS_CONFIG }} = progressModule;

              const clone = value => JSON.parse(JSON.stringify(value));
              const assert = (condition, message) => {{
                if (!condition) throw new Error(`Formal runtime test: ${{message}}`);
              }};
              const rejected = callback => {{
                try {{
                  return callback() === false;
                }} catch {{
                  return true;
                }}
              }};
              const memoryStorage = (initial = {{}}) => {{
                const values = new Map(
                  Object.entries(initial).map(([key, value]) => [String(key), String(value)]),
                );
                return {{
                  get length() {{ return values.size; }},
                  key: index => [...values.keys()][index] ?? null,
                  getItem: key => values.has(String(key)) ? values.get(String(key)) : null,
                  setItem: (key, value) => values.set(String(key), String(value)),
                  removeItem: key => values.delete(String(key)),
                  clear: () => values.clear(),
                  keys: () => [...values.keys()],
                  entries: () => Object.fromEntries(values),
                }};
              }};

              // FORMAL_CAMPAIGN remains an in-memory test fixture. No URL mode or
              // loadGameData branch is added for it by this test.
              const campaignData = await loadGameData({{ mode: 'campaign' }});
              const formalData = clone(campaignData);
              formalData.prototype_mode = {{
                ...formalData.prototype_mode,
                type: 'FORMAL_CAMPAIGN',
                total_nights: 56,
              }};
              formalData.campaign = {{
                ...formalData.campaign,
                formal_progress: clone(FORMAL_CAMPAIGN_PROGRESS_CONFIG),
              }};
              formalData.run_completion = clone(formalData.run_completion);
              formalData.run_completion.record_namespace = 'vespera.campaign.formal.runtime-test.v1';
              for (const ending of formalData.run_completion.ending_rules) {{
                for (const condition of ending.conditions ?? []) {{
                  if (condition.metric === 'completed_nights') condition.value = 56;
                }}
              }}
              formalData.indexes = createIndexes(formalData);

              assert(formalData.scenarios.length === 5, 'fixture must retain five templates');
              assert(
                formalData.campaign.formal_progress.scenario_template_count
                  === formalData.scenarios.length,
                'formal progress template count must match the fixture',
              );

              const formalKey = activeRunStorageKey(formalData);
              const preservedKeys = {{
                [ACTIVE_RUN_STORAGE_KEY]: 'legacy-active-run-sentinel',
                [`${{ACTIVE_RUN_STORAGE_PREFIX}}.campaign`]: 'campaign-active-run-sentinel',
                [`${{ACTIVE_RUN_STORAGE_PREFIX}}.showcase`]: 'showcase-active-run-sentinel',
                [`${{ACTIVE_RUN_STORAGE_PREFIX}}.endless`]: 'endless-active-run-sentinel',
              }};
              const storage = memoryStorage(preservedKeys);

              const syntheticResult = stageNumber => ({{
                valid: true,
                placementScore: 0,
                reputationDelta: 0,
                baseFees: 1,
                tips: 0,
                income: 1,
                grade: 'FORMAL_RUNTIME_TEST',
                acceptedGuestIds: [],
                rejectedGuestIds: [],
                canceledGuestIds: [],
                placements: {{}},
                guestScores: {{}},
                guestReviews: [],
                emergencyReport: null,
                testStageNumber: stageNumber,
              }});

              const boot = controller => {{
                assert(controller.start() === true, 'start must enter formal new game');
                assert(controller.state.phase === 'NEW_GAME', 'formal start must use campaign setup');
                assert(controller.confirmNewGame() === true, 'formal prologue must open');
                assert(controller.continueStory() === true, 'formal prologue must continue');
                if (controller.state.phase === 'RELIC_OFFER') {{
                  assert(controller.skipDisplayRelicOffer() === true, 'formal relic offer must skip');
                }}
                assert(controller.state.phase === 'DAY_OPENING', 'formal day 1 must open');
                assert(controller.state.campaignProgress.currentStageNumber === 1,
                  'formal progress must own stage 1');
              }};

              const playToReview = (controller, expectedStage) => {{
                assert(controller.state.phase === 'DAY_OPENING',
                  `stage ${{expectedStage}} must start at DAY_OPENING`);
                assert(controller.state.campaignProgress.currentStageNumber === expectedStage,
                  `stage authority drift before ${{expectedStage}}`);
                assert(controller.startDayBusiness() === true,
                  `stage ${{expectedStage}} must begin business`);
                controller.completeNight(syntheticResult(expectedStage));
                assert(controller.state.phase === 'RESULT',
                  `stage ${{expectedStage}} must reach RESULT`);
                assert(controller.openResultReview() === true,
                  `stage ${{expectedStage}} must reach RESULT_REVIEW`);
                const result = controller.state.nightResults.at(-1);
                assert(result.testStageNumber === expectedStage,
                  `stage ${{expectedStage}} result must append at the tail`);
                assert(typeof result.campaignOperationId === 'string',
                  `stage ${{expectedStage}} must carry campaignOperationId`);
                assert(result.campaignResultIdentity?.stageNumber === expectedStage,
                  `stage ${{expectedStage}} must carry its append identity`);
                return clone(result);
              }};

              const acceptAndOpenNext = (controller, expectFinal = false) => {{
                assert(controller.acceptSecretaryReport() === true,
                  'secretary report must be accepted');
                if (expectFinal) {{
                  assert(controller.state.phase === 'FINAL', 'completed extent must reach FINAL');
                  return;
                }}
                if (controller.state.phase === 'STORY') {{
                  assert(controller.continueStory() === true, 'scheduled story must continue');
                }}
                assert(controller.state.phase === 'UPGRADE',
                  `next transition must enter UPGRADE, got ${{controller.state.phase}}`);
                assert(controller.finishUpgrade() === true, 'upgrade phase must finish');
                assert(controller.state.phase === 'DAY_OPENING', 'next day must open');
              }};

              let base = new GameController(formalData, {{ seed: {seed}, storage }});
              boot(base);
              for (let stage = 1; stage <= 5; stage += 1) {{
                playToReview(base, stage);
                acceptAndOpenNext(base);
              }}

              const prefixBeforeSix = clone(base.state.nightResults);
              const firstResultBeforeSix = clone(base.state.nightResults[0]);
              const sixBeforeSave = playToReview(base, 6);
              assert(base.state.nightResults.length === 6, 'stage 6 must append a sixth result');
              assert(base.state.nightResults[0].testStageNumber === 1,
                'stage 6 must not overwrite stage 1');
              assert(base.state.nightResults[5].testStageNumber === 6,
                'stage 6 must occupy result index 5');
              assert(JSON.stringify(base.state.nightResults.slice(0, 5))
                === JSON.stringify(prefixBeforeSix), 'stage 6 must preserve the first five results');
              assert(base.saveCheckpoint(), 'RESULT_REVIEW save must succeed');
              const cleanStageSixSave = JSON.parse(storage.getItem(formalKey));
              assert(cleanStageSixSave.state.nightResults.length === 6,
                'saved state must include stage 6');
              assert(cleanStageSixSave.stage_checkpoint.nightResults.length === 5,
                'stage checkpoint must preserve the stage 6 prefix');

              base = new GameController(formalData, {{ seed: {seed} + 99, storage }});
              assert(base.hasCheckpoint() === true, 'formal save must be discoverable');
              assert(base.resumeRun() === true, 'formal save must resume');
              assert(base.state.phase === 'RESULT_REVIEW', 'resume must restore RESULT_REVIEW');
              assert(base.state.nightResults.length === 6, 'resume must restore six results');
              assert(base.retryCurrentStage() === true, 'stage 6 retry must restore checkpoint');
              assert(base.state.phase === 'DAY_OPENING', 'retry must return to day opening');
              assert(base.state.nightResults.length === 5, 'retry must truncate result 6');
              assert(base.state.campaignProgress.completedStageCount === 5,
                'retry must restore completed stage authority to 5');
              assert(JSON.stringify(base.state.nightResults) === JSON.stringify(prefixBeforeSix),
                'retry must preserve the first five results exactly');
              const sixAfterRetry = playToReview(base, 6);
              assert(base.state.nightResults.length === 6, 'replayed stage 6 must append again');
              assert(sixAfterRetry.campaignOperationId === sixBeforeSave.campaignOperationId,
                'replayed stage 6 must retain its deterministic operation ID');
              assert(JSON.stringify(base.state.nightResults.slice(0, 5))
                === JSON.stringify(prefixBeforeSix), 'replayed stage 6 must preserve its prefix');
              assert(JSON.stringify(base.state.nightResults[0]) === JSON.stringify(firstResultBeforeSix),
                'replayed stage 6 must not mutate stage 1');
              acceptAndOpenNext(base);

              const seven = playToReview(base, 7);
              assert(seven.campaignResultIdentity.operationKind === 'NORMAL',
                'boundary stage 7 must first complete as NORMAL');
              assert(base.queueFormalCampaignRecovery(7) === true,
                'boundary stage 7 must queue recovery');
              assert(base.state.campaignProgress.pendingRecoveryBoundaryStageNumber === 7,
                'stage 7 recovery must remain pending until the next operation');
              acceptAndOpenNext(base);

              const eight = playToReview(base, 8);
              assert(eight.campaignResultIdentity.operationKind === 'RECOVERY',
                'stage 8 must consume queued recovery');
              assert(eight.campaignRecoveryBoundaryStageNumber === 7,
                'stage 8 must retain recovery boundary 7');
              acceptAndOpenNext(base);

              const nine = playToReview(base, 9);
              assert(nine.campaignResultIdentity.operationKind === 'NORMAL',
                'stage 9 must return to NORMAL');
              assert(nine.campaignRecoveryBoundaryStageNumber === null,
                'stage 9 must not inherit recovery metadata');
              assert(base.saveCheckpoint(), 'stage 9 review save must succeed');
              const cleanStageNineSave = JSON.parse(storage.getItem(formalKey));

              const corruptedSaveRejected = mutate => {{
                const candidate = clone(cleanStageNineSave);
                mutate(candidate);
                const isolated = memoryStorage({{ [formalKey]: JSON.stringify(candidate) }});
                return readActiveRunSave(formalData, isolated) === null;
              }};
              const corruptions = {{
                legacySchemaVersion: corruptedSaveRejected(save => {{
                  save.schema_version = 4;
                }}),
                wrongStageAuthority: corruptedSaveRejected(save => {{
                  save.stage_authority_id = 'WRONG_STAGE_AUTHORITY';
                }}),
                wrongOperationId: corruptedSaveRejected(save => {{
                  save.state.nightResults[0].campaignOperationId = 'WRONG_OPERATION_ID';
                }}),
                wrongConfigId: corruptedSaveRejected(save => {{
                  save.state.campaignProgress.configId = 'WRONG_CONFIG_ID';
                }}),
                resultGap: corruptedSaveRejected(save => {{
                  save.state.campaignProgress.operationRecords.splice(4, 1);
                }}),
                sparseNightResults: corruptedSaveRejected(save => {{
                  save.state.nightResults = new Array(
                    save.state.campaignProgress.completedStageCount,
                  );
                }}),
                sparseOperationRecords: corruptedSaveRejected(save => {{
                  save.state.campaignProgress.operationRecords = new Array(
                    save.state.campaignProgress.completedStageCount,
                  );
                }}),
                duplicateStage: corruptedSaveRejected(save => {{
                  save.state.campaignProgress.operationRecords[5]
                    .resultIdentity.stageNumber = 5;
                }}),
                stageCapMismatch: corruptedSaveRejected(save => {{
                  save.state.campaignProgress.stageLimit = 70;
                }}),
                configVersionMismatch: corruptedSaveRejected(save => {{
                  save.state.campaignProgress.configVersion += 1;
                }}),
                checkpointPrefixMismatch: corruptedSaveRejected(save => {{
                  const checkpointProgress = save.stage_checkpoint.campaignProgress;
                  checkpointProgress.operationRecords[7].resultIdentity.operationKind = 'NORMAL';
                  checkpointProgress.operationRecords[7].recoveryBoundaryStageNumber = null;
                  const checkpointResult = save.stage_checkpoint.nightResults[7];
                  checkpointResult.campaignResultIdentity.operationKind = 'NORMAL';
                  checkpointResult.campaignRecoveryBoundaryStageNumber = null;
                }}),
              }};
              assert(Object.values(corruptions).every(Boolean),
                `all corrupted formal saves must be rejected: ${{JSON.stringify(corruptions)}}`);

              acceptAndOpenNext(base);
              for (let stage = 10; stage <= 56; stage += 1) {{
                playToReview(base, stage);
                acceptAndOpenNext(base, stage === 56);
              }}
              const baseIds = base.state.nightResults.map(result => result.campaignOperationId);
              const baseTemplates = base.state.nightResults.map(
                result => result.campaignResultIdentity.templateIndex,
              );
              assert(base.state.nightResults.length === 56, 'base run must retain 56 results');
              assert(base.state.campaignProgress.completedStageCount === 56,
                'base progress must complete 56 stages');
              assert(base.state.campaignProgress.status === 'BASE_COMPLETE',
                'base progress must complete without true unlock');
              assert(new Set(baseTemplates).size === 5,
                'base run must exercise all five scenario templates');
              assert(baseTemplates.every(index => Number.isInteger(index) && index >= 0 && index < 5),
                'all base template indexes must remain in range');
              assert(baseTemplates.slice(0, 10).join(',') === '0,1,2,3,4,0,1,2,3,4',
                'formal template selection must cycle deterministically');
              assert(base.state.runRecord.metrics.completed_nights === 56,
                'base FINAL must report 56 completed nights');
              assert(base.state.runRecord.metrics.expected_nights === 56,
                'base FINAL must expect 56 nights');
              assert(base.state.runRecord.schema_version === 4,
                'base FINAL must use run record schema 4');
              assert(base.state.runRecord.progression_authority
                === FORMAL_CAMPAIGN_PROGRESS_CONFIG.id,
              'base FINAL must retain formal progression authority');
              assert(base.state.runRecord.campaign_stage_limit === 56,
                'base FINAL must retain the base stage limit');
              assert(base.state.runRecord.true_extension_unlocked === false,
                'base FINAL must record a locked true extension');
              assert(base.state.runRecord.last_operation_id === baseIds.at(-1),
                'base FINAL must retain the final operation ID');
              assert(base.state.runRecord.metrics.campaign_completed_stages === 56,
                'base FINAL must retain 56 campaign stages');
              assert(base.state.runRecord.metrics.recovery_operations === 1,
                'base FINAL must retain one recovery operation');
              assert(base.state.runRecord.record_id.startsWith(
                `${{formalData.run_completion.record_namespace}}:`,
              ), 'base run record must use the formal namespace');

              const preservedAfterBase = Object.fromEntries(
                Object.keys(preservedKeys).map(key => [key, storage.getItem(key)]),
              );
              assert(JSON.stringify(preservedAfterBase) === JSON.stringify(preservedKeys),
                'formal saves must not modify legacy or other mode active-run keys');
              assert(formalKey.endsWith('.formal_campaign'),
                'formal active run must use the .formal_campaign key');
              assert(!storage.keys().some(key => key === formalKey),
                'formal active save must clear after base FINAL');

              const trueStorage = memoryStorage();
              let trueRun = new GameController(formalData, {{ seed: {seed}, storage: trueStorage }});
              boot(trueRun);
              for (let stage = 1; stage <= 55; stage += 1) {{
                playToReview(trueRun, stage);
                acceptAndOpenNext(trueRun);
              }}
              playToReview(trueRun, 56);
              const beforeInvalidGate = JSON.stringify(trueRun.state.campaignProgress);
              const invalidGateRejected = rejected(() => trueRun.unlockFormalCampaignTrueExtension({{
                gateId: 'WRONG_TRUE_GATE',
                passed: true,
                boundaryStageNumber: 56,
              }}));
              assert(invalidGateRejected, 'wrong true gate must be rejected');
              assert(JSON.stringify(trueRun.state.campaignProgress) === beforeInvalidGate,
                'rejected true gate must not mutate progress');
              const gateEvidence = {{
                gateId: FORMAL_CAMPAIGN_PROGRESS_CONFIG.true_entry_gate_id,
                passed: true,
                boundaryStageNumber: 56,
              }};
              assert(trueRun.unlockFormalCampaignTrueExtension(gateEvidence) === true,
                'exact true gate evidence must unlock the extension');
              assert(trueRun.state.campaignProgress.currentStageNumber === 57,
                'true unlock must expose stage 57');
              assert(trueRun.state.campaignProgress.stageLimit === 70,
                'true unlock must extend the cap to 70');
              const trueBoundarySavePreview = createRunSave(
                formalData,
                trueRun.state,
                trueRun.stageCheckpoint,
              );
              assert(trueBoundarySavePreview !== null,
                `unlocked day 56 review must remain savable: ${{JSON.stringify({{
                  livePhase: trueRun.state.phase,
                  liveCompleted: trueRun.state.campaignProgress.completedStageCount,
                  liveCurrent: trueRun.state.campaignProgress.currentStageNumber,
                  liveLimit: trueRun.state.campaignProgress.stageLimit,
                  liveTemplate: trueRun.state.currentNightIndex,
                  checkpointPhase: trueRun.stageCheckpoint?.phase,
                  checkpointCompleted:
                    trueRun.stageCheckpoint?.campaignProgress?.completedStageCount,
                  checkpointCurrent:
                    trueRun.stageCheckpoint?.campaignProgress?.currentStageNumber,
                  checkpointLimit: trueRun.stageCheckpoint?.campaignProgress?.stageLimit,
                  checkpointTemplate: trueRun.stageCheckpoint?.currentNightIndex,
                  liveResults: trueRun.state.nightResults.length,
                  checkpointResults: trueRun.stageCheckpoint?.nightResults?.length,
                }})}}`);
              assert(Boolean(trueRun.saveCheckpoint()),
                'unlocked day 56 review save write must succeed');
              trueRun = new GameController(
                formalData,
                {{ seed: {seed} + 1000, storage: trueStorage }},
              );
              assert(trueRun.resumeRun() === true,
                'unlocked day 56 review must resume');
              assert(trueRun.state.phase === 'RESULT_REVIEW',
                'true boundary resume must restore the review phase');
              assert(trueRun.state.campaignProgress.trueExtensionUnlocked === true,
                'true boundary resume must retain the extension gate');
              assert(trueRun.state.campaignProgress.currentStageNumber === 57,
                'true boundary resume must retain stage 57 authority');
              acceptAndOpenNext(trueRun);
              for (let stage = 57; stage <= 70; stage += 1) {{
                playToReview(trueRun, stage);
                acceptAndOpenNext(trueRun, stage === 70);
              }}
              const trueIds = trueRun.state.nightResults.map(
                result => result.campaignOperationId,
              );
              assert(trueRun.state.nightResults.length === 70,
                'true run must retain 70 results');
              assert(trueRun.state.campaignProgress.completedStageCount === 70,
                'true progress must complete 70 stages');
              assert(trueRun.state.campaignProgress.status === 'TRUE_COMPLETE',
                'true progress must end as TRUE_COMPLETE');
              assert(JSON.stringify(trueIds.slice(0, 56)) === JSON.stringify(baseIds),
                'true run must preserve the same-seed base operation ID prefix');
              assert(trueRun.state.runRecord.metrics.completed_nights === 70,
                'true FINAL must report 70 completed nights');
              assert(trueRun.state.runRecord.metrics.expected_nights === 70,
                'true FINAL must expect 70 nights after unlock');
              assert(trueRun.state.runRecord.schema_version === 4,
                'true FINAL must use run record schema 4');
              assert(trueRun.state.runRecord.progression_authority
                === FORMAL_CAMPAIGN_PROGRESS_CONFIG.id,
              'true FINAL must retain formal progression authority');
              assert(trueRun.state.runRecord.campaign_stage_limit === 70,
                'true FINAL must retain the extended stage limit');
              assert(trueRun.state.runRecord.true_extension_unlocked === true,
                'true FINAL must record the unlocked extension');
              assert(trueRun.state.runRecord.last_operation_id === trueIds.at(-1),
                'true FINAL must retain the final operation ID');
              assert(trueRun.state.runRecord.metrics.campaign_completed_stages === 70,
                'true FINAL must retain 70 campaign stages');
              assert(trueRun.state.runRecord.metrics.recovery_operations === 0,
                'true FINAL fixture must retain zero recovery operations');

              return {{
                dataMode: formalData.prototype_mode.type,
                formalKey,
                preservedKeys: preservedAfterBase,
                base: {{
                  phase: base.state.phase,
                  completed: base.state.campaignProgress.completedStageCount,
                  status: base.state.campaignProgress.status,
                  resultCount: base.state.nightResults.length,
                  expectedNights: base.state.runRecord.metrics.expected_nights,
                  templateCycle: baseTemplates.slice(0, 10),
                  operationIdPrefix: baseIds.slice(0, 3),
                }},
                retry: {{
                  beforeSaveId: sixBeforeSave.campaignOperationId,
                  afterRetryId: sixAfterRetry.campaignOperationId,
                  prefixLength: prefixBeforeSix.length,
                }},
                recovery: {{
                  boundaryKind: seven.campaignResultIdentity.operationKind,
                  recoveryKind: eight.campaignResultIdentity.operationKind,
                  recoveryBoundary: eight.campaignRecoveryBoundaryStageNumber,
                  followingKind: nine.campaignResultIdentity.operationKind,
                }},
                trueRun: {{
                  phase: trueRun.state.phase,
                  completed: trueRun.state.campaignProgress.completedStageCount,
                  status: trueRun.state.campaignProgress.status,
                  resultCount: trueRun.state.nightResults.length,
                  expectedNights: trueRun.state.runRecord.metrics.expected_nights,
                  invalidGateRejected,
                  prefixPreserved: JSON.stringify(trueIds.slice(0, 56))
                    === JSON.stringify(baseIds),
                }},
                corruptions,
              }};
            }})()
            """
        )

        assert contracts["dataMode"] == "FORMAL_CAMPAIGN", contracts
        assert contracts["formalKey"].endswith(".formal_campaign"), contracts
        assert contracts["base"] == {
            "phase": "FINAL",
            "completed": 56,
            "status": "BASE_COMPLETE",
            "resultCount": 56,
            "expectedNights": 56,
            "templateCycle": [0, 1, 2, 3, 4, 0, 1, 2, 3, 4],
            "operationIdPrefix": [
                f"FORMAL_CAMPAIGN_PROGRESS@1:{seed}:1",
                f"FORMAL_CAMPAIGN_PROGRESS@1:{seed}:2",
                f"FORMAL_CAMPAIGN_PROGRESS@1:{seed}:3",
            ],
        }, contracts["base"]
        assert contracts["retry"] == {
            "beforeSaveId": f"FORMAL_CAMPAIGN_PROGRESS@1:{seed}:6",
            "afterRetryId": f"FORMAL_CAMPAIGN_PROGRESS@1:{seed}:6",
            "prefixLength": 5,
        }, contracts["retry"]
        assert contracts["recovery"] == {
            "boundaryKind": "NORMAL",
            "recoveryKind": "RECOVERY",
            "recoveryBoundary": 7,
            "followingKind": "NORMAL",
        }, contracts["recovery"]
        assert contracts["trueRun"] == {
            "phase": "FINAL",
            "completed": 70,
            "status": "TRUE_COMPLETE",
            "resultCount": 70,
            "expectedNights": 70,
            "invalidGateRejected": True,
            "prefixPreserved": True,
        }, contracts["trueRun"]
        assert all(contracts["corruptions"].values()), contracts["corruptions"]

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
            "mode": contracts["dataMode"],
            "base_completed": contracts["base"]["completed"],
            "true_completed": contracts["trueRun"]["completed"],
            "retry_operation_id": contracts["retry"]["afterRetryId"],
            "recovery": contracts["recovery"],
            "template_cycle": contracts["base"]["templateCycle"][:5],
            "save_key": contracts["formalKey"],
            "corrupted_saves_rejected": len(contracts["corruptions"]),
            "true_prefix_preserved": contracts["trueRun"]["prefixPreserved"],
        }
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description="Validate formal campaign GameController runtime.")
    parser.add_argument("--url", default="http://127.0.0.1:8770/index.html")
    parser.add_argument("--debug-port", type=int, default=9233)
    parser.add_argument("--seed", type=int, default=6429)
    args = parser.parse_args()
    print(json.dumps(run(args.url, args.debug_port, args.seed), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
