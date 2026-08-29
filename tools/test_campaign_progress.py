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
              const progressModule = await import('./src/campaign-progress.js');
              const {
                CAMPAIGN_PROGRESS_SCHEMA_VERSION,
                CAMPAIGN_OPERATION_KINDS,
                FORMAL_CAMPAIGN_PROGRESS_CONFIG,
                validateCampaignProgressConfig,
                validateCampaignProgressState,
                createCampaignProgress,
                campaignScenarioTemplateIndex,
                campaignOperationDescriptor,
                campaignOperationId,
                campaignResultIdentity,
                completeCampaignOperation,
                unlockTrueCampaignExtension,
                compileCampaignGreyboxOperationPlan,
                validateCampaignProgressPrefix,
              } = progressModule;

              const config = JSON.parse(JSON.stringify(FORMAL_CAMPAIGN_PROGRESS_CONFIG));
              const clone = value => JSON.parse(JSON.stringify(value));
              const rejects = callback => {
                try {
                  callback();
                  return false;
                } catch {
                  return true;
                }
              };
              const advanceTo = (source, target) => {
                let progress = source;
                while (progress.completedStageCount < target) {
                  progress = completeCampaignOperation(
                    config,
                    progress,
                    campaignOperationDescriptor(config, progress),
                  );
                }
                return progress;
              };

              const initial = createCampaignProgress(config);
              const firstOperation = campaignOperationDescriptor(config, initial);
              const firstOperationId = campaignOperationId(config, 4242, firstOperation);
              const firstIdentity = campaignResultIdentity(config, firstOperation);
              const initialSnapshot = JSON.stringify(initial);
              const afterFirst = completeCampaignOperation(config, initial, firstOperation);
              const chapterBoundaryRecords = [7, 14, 28, 42, 56].map(boundary => {
                const progress = advanceTo(createCampaignProgress(config), boundary);
                return {
                  boundary,
                  currentStageNumber: progress.currentStageNumber,
                  record: clone(progress.operationRecords.at(-1)),
                };
              });

              const baseProgress = advanceTo(createCampaignProgress(config), 56);
              const gateEvidence = {
                gateId: config.true_entry_gate_id,
                passed: true,
                boundaryStageNumber: 56,
              };
              const trueStart = unlockTrueCampaignExtension(config, baseProgress, gateEvidence);
              const day57Operation = campaignOperationDescriptor(config, trueStart);
              const trueComplete = advanceTo(trueStart, 70);

              const basePlan = compileCampaignGreyboxOperationPlan(
                config,
                { includeTrueExtension: false },
              );
              const truePlan = compileCampaignGreyboxOperationPlan(
                config,
                { includeTrueExtension: true },
              );
              const threeTemplateConfig = {
                ...clone(config),
                id: 'FORMAL_CAMPAIGN_PROGRESS_THREE_TEMPLATES',
                scenario_template_count: 3,
              };
              const threeTemplatePlan = compileCampaignGreyboxOperationPlan(
                threeTemplateConfig,
                { includeTrueExtension: true },
              );

              const invalid = {};
              const invalidConfig = (name, mutate) => {
                const candidate = clone(config);
                mutate(candidate);
                invalid[name] = rejects(() => validateCampaignProgressConfig(candidate));
              };
              invalidConfig('unsafeVersion', value => { value.version = Number.MAX_SAFE_INTEGER + 1; });
              invalidConfig('wrongBaseLimit', value => { value.base_stage_limit = 55; });
              invalidConfig('wrongTrueLimit', value => { value.true_stage_limit = 71; });
              invalidConfig('wrongGate', value => { value.true_entry_gate_id = 'WRONG'; });
              invalidConfig('wrongTemplatePolicy', value => {
                value.scenario_template_policy_id = 'PRODUCTION_MODULO';
              });
              invalidConfig('productionReadyModulo', value => {
                value.scenario_templates_production_ready = true;
              });
              invalidConfig('zeroTemplateCount', value => { value.scenario_template_count = 0; });
              invalidConfig('unsafeTemplateCount', value => {
                value.scenario_template_count = Number.MAX_SAFE_INTEGER + 1;
              });
              invalidConfig('offsetOutsideTemplates', value => { value.template_offset = 5; });
              invalidConfig('missingTemplateOffset', value => { delete value.template_offset; });
              invalidConfig('staleRecoveryBoundaries', value => {
                value.recovery_boundary_stages = [7, 14, 28, 42];
              });
              invalidConfig('extraConfigField', value => { value.extra = true; });

              invalid.templateStageZero = rejects(() => campaignScenarioTemplateIndex(config, 0));
              invalid.templateStagePastTrue = rejects(() => campaignScenarioTemplateIndex(config, 71));
              invalid.operationIdNegativeSeed = rejects(() => campaignOperationId(
                config,
                -1,
                firstOperation,
              ));
              invalid.operationIdUnsafeSeed = rejects(() => campaignOperationId(
                config,
                0x100000000,
                firstOperation,
              ));
              invalid.tamperedTemplate = rejects(() => completeCampaignOperation(
                config,
                initial,
                { ...firstOperation, templateIndex: 4 },
              ));
              invalid.extraOperationField = rejects(() => completeCampaignOperation(
                config,
                initial,
                { ...firstOperation, extra: true },
              ));
              invalid.staleRecoveryOperationField = rejects(() => completeCampaignOperation(
                config,
                initial,
                { ...firstOperation, recoveryBoundaryStageNumber: null },
              ));
              invalid.recoveryOperationKind = rejects(() => completeCampaignOperation(
                config,
                initial,
                { ...firstOperation, operationKind: 'RECOVERY' },
              ));
              invalid.staleOperation = rejects(() => completeCampaignOperation(
                config,
                afterFirst,
                firstOperation,
              ));
              invalid.operationAfterBaseComplete = rejects(() => campaignOperationDescriptor(
                config,
                baseProgress,
              ));
              invalid.unlockEarly = rejects(() => unlockTrueCampaignExtension(
                config,
                afterFirst,
                gateEvidence,
              ));
              invalid.unlockWrongGate = rejects(() => unlockTrueCampaignExtension(
                config,
                baseProgress,
                { ...gateEvidence, gateId: 'WRONG' },
              ));
              invalid.unlockFailedGate = rejects(() => unlockTrueCampaignExtension(
                config,
                baseProgress,
                { ...gateEvidence, passed: false },
              ));
              invalid.unlockWrongBoundary = rejects(() => unlockTrueCampaignExtension(
                config,
                baseProgress,
                { ...gateEvidence, boundaryStageNumber: 55 },
              ));
              invalid.unlockTwice = rejects(() => unlockTrueCampaignExtension(
                config,
                trueStart,
                gateEvidence,
              ));
              invalid.operationAfterTrueComplete = rejects(() => campaignOperationDescriptor(
                config,
                trueComplete,
              ));
              invalid.oldProgressSchema = rejects(() => {
                const candidate = clone(initial);
                candidate.schemaVersion = 1;
                validateCampaignProgressState(config, candidate);
              });
              invalid.stalePendingRecoveryState = rejects(() => {
                const candidate = clone(initial);
                candidate.pendingRecoveryBoundaryStageNumber = null;
                validateCampaignProgressState(config, candidate);
              });
              invalid.extraProgressField = rejects(() => {
                const candidate = clone(initial);
                candidate.extra = true;
                validateCampaignProgressState(config, candidate);
              });
              invalid.unsafeCompletedCount = rejects(() => {
                const candidate = clone(initial);
                candidate.completedStageCount = Number.MAX_SAFE_INTEGER + 1;
                validateCampaignProgressState(config, candidate);
              });
              invalid.missingResultRecord = rejects(() => {
                const candidate = clone(afterFirst);
                candidate.operationRecords = [];
                validateCampaignProgressState(config, candidate);
              });
              invalid.sparseResultRecord = rejects(() => {
                const candidate = clone(afterFirst);
                candidate.operationRecords = new Array(1);
                validateCampaignProgressState(config, candidate);
              });
              invalid.nonSequentialResultIdentity = rejects(() => {
                const candidate = clone(afterFirst);
                candidate.operationRecords[0].resultIdentity.stageNumber = 2;
                validateCampaignProgressState(config, candidate);
              });
              invalid.resultIdentityExtraField = rejects(() => {
                const candidate = clone(afterFirst);
                candidate.operationRecords[0].resultIdentity.extra = true;
                validateCampaignProgressState(config, candidate);
              });
              invalid.recoveryResultIdentity = rejects(() => {
                const candidate = clone(afterFirst);
                candidate.operationRecords[0].resultIdentity.operationKind = 'RECOVERY';
                validateCampaignProgressState(config, candidate);
              });
              invalid.staleRecoveryRecordField = rejects(() => {
                const candidate = clone(afterFirst);
                candidate.operationRecords[0].recoveryBoundaryStageNumber = null;
                validateCampaignProgressState(config, candidate);
              });
              invalid.planOptionNotBoolean = rejects(() => compileCampaignGreyboxOperationPlan(
                config,
                { includeTrueExtension: 'yes' },
              ));

              return {
                schemaVersion: CAMPAIGN_PROGRESS_SCHEMA_VERSION,
                operationKinds: [...CAMPAIGN_OPERATION_KINDS],
                configValid: validateCampaignProgressConfig(config),
                configKeys: Object.keys(config).sort(),
                queueRecoveryExportAbsent: !('queueCampaignRecovery' in progressModule),
                initial,
                firstOperation,
                firstOperationId,
                firstIdentity,
                inputUnchanged: initialSnapshot === JSON.stringify(initial),
                afterFirst,
                chapterBoundaryRecords,
                baseComplete: {
                  completedStageCount: baseProgress.completedStageCount,
                  currentStageNumber: baseProgress.currentStageNumber,
                  stageLimit: baseProgress.stageLimit,
                  trueExtensionUnlocked: baseProgress.trueExtensionUnlocked,
                  status: baseProgress.status,
                  recordCount: baseProgress.operationRecords.length,
                },
                trueStart: {
                  completedStageCount: trueStart.completedStageCount,
                  currentStageNumber: trueStart.currentStageNumber,
                  stageLimit: trueStart.stageLimit,
                  trueExtensionUnlocked: trueStart.trueExtensionUnlocked,
                  status: trueStart.status,
                  recordCount: trueStart.operationRecords.length,
                },
                day57Operation,
                trueComplete: {
                  completedStageCount: trueComplete.completedStageCount,
                  currentStageNumber: trueComplete.currentStageNumber,
                  stageLimit: trueComplete.stageLimit,
                  trueExtensionUnlocked: trueComplete.trueExtensionUnlocked,
                  status: trueComplete.status,
                  recordCount: trueComplete.operationRecords.length,
                  allNormal: trueComplete.operationRecords.every(
                    record => record.resultIdentity.operationKind === 'NORMAL'
                  ),
                  exactRecordShapes: trueComplete.operationRecords.every(
                    record => JSON.stringify(Object.keys(record)) === JSON.stringify(['resultIdentity'])
                  ),
                },
                plans: {
                  baseTotal: basePlan.totalStages,
                  trueTotal: truePlan.totalStages,
                  type: truePlan.type,
                  templatePolicyId: truePlan.templatePolicyId,
                  productionReady: truePlan.productionReady,
                  prefixEqual: JSON.stringify(truePlan.operations.slice(0, 56))
                    === JSON.stringify(basePlan.operations),
                  prefixValidated: validateCampaignProgressPrefix(config),
                  deterministic: JSON.stringify(truePlan)
                    === JSON.stringify(compileCampaignGreyboxOperationPlan(
                      config,
                      { includeTrueExtension: true },
                    )),
                  allNormal: truePlan.operations.every(operation => operation.operationKind === 'NORMAL'),
                  exactOperationShapes: truePlan.operations.every(operation => (
                    JSON.stringify(Object.keys(operation).sort()) === JSON.stringify([
                      'operationKind',
                      'stageNumber',
                      'templateIndex',
                      'templatePolicyId',
                      'templateProductionReady',
                      'type',
                    ])
                  )),
                  defaultTemplateIndices: truePlan.operations.slice(0, 12)
                    .map(operation => operation.templateIndex),
                  threeTemplateTotal: threeTemplatePlan.totalStages,
                  threeTemplateIndices: threeTemplatePlan.operations.slice(0, 9)
                    .map(operation => operation.templateIndex),
                },
                invalid,
              };
            })()
            """
        )

        assert contracts["schemaVersion"] == 2, contracts
        assert contracts["operationKinds"] == ["NORMAL"], contracts
        assert contracts["configValid"] is True, contracts
        assert "recovery_boundary_stages" not in contracts["configKeys"], contracts
        assert contracts["queueRecoveryExportAbsent"] is True, contracts
        assert contracts["initial"] == {
            "type": "CAMPAIGN_PROGRESS_STATE",
            "schemaVersion": 2,
            "configId": "FORMAL_CAMPAIGN_PROGRESS",
            "configVersion": 1,
            "completedStageCount": 0,
            "currentStageNumber": 1,
            "stageLimit": 56,
            "trueExtensionUnlocked": False,
            "status": "ACTIVE",
            "operationRecords": [],
        }, contracts["initial"]
        assert contracts["firstOperation"] == {
            "type": "CAMPAIGN_OPERATION",
            "stageNumber": 1,
            "operationKind": "NORMAL",
            "templateIndex": 0,
            "templatePolicyId": "GREYBOX_ONLY_STAGE_MODULO",
            "templateProductionReady": False,
        }, contracts["firstOperation"]
        assert contracts["firstOperationId"] == "FORMAL_CAMPAIGN_PROGRESS@1:4242:1"
        assert contracts["firstIdentity"] == {
            "stageNumber": 1,
            "operationKind": "NORMAL",
            "templateIndex": 0,
        }, contracts["firstIdentity"]
        assert contracts["inputUnchanged"] is True, contracts
        assert contracts["afterFirst"]["completedStageCount"] == 1, contracts
        assert contracts["afterFirst"]["currentStageNumber"] == 2, contracts

        expected_templates = {7: 1, 14: 3, 28: 2, 42: 1, 56: 0}
        assert contracts["chapterBoundaryRecords"] == [
            {
                "boundary": boundary,
                "currentStageNumber": boundary + 1 if boundary < 56 else None,
                "record": {
                    "resultIdentity": {
                        "stageNumber": boundary,
                        "operationKind": "NORMAL",
                        "templateIndex": expected_templates[boundary],
                    },
                },
            }
            for boundary in [7, 14, 28, 42, 56]
        ], contracts["chapterBoundaryRecords"]

        assert contracts["baseComplete"] == {
            "completedStageCount": 56,
            "currentStageNumber": None,
            "stageLimit": 56,
            "trueExtensionUnlocked": False,
            "status": "BASE_COMPLETE",
            "recordCount": 56,
        }, contracts["baseComplete"]
        assert contracts["trueStart"] == {
            "completedStageCount": 56,
            "currentStageNumber": 57,
            "stageLimit": 70,
            "trueExtensionUnlocked": True,
            "status": "ACTIVE",
            "recordCount": 56,
        }, contracts["trueStart"]
        assert contracts["day57Operation"] == {
            "type": "CAMPAIGN_OPERATION",
            "stageNumber": 57,
            "operationKind": "NORMAL",
            "templateIndex": 1,
            "templatePolicyId": "GREYBOX_ONLY_STAGE_MODULO",
            "templateProductionReady": False,
        }, contracts["day57Operation"]
        assert contracts["trueComplete"] == {
            "completedStageCount": 70,
            "currentStageNumber": None,
            "stageLimit": 70,
            "trueExtensionUnlocked": True,
            "status": "TRUE_COMPLETE",
            "recordCount": 70,
            "allNormal": True,
            "exactRecordShapes": True,
        }, contracts["trueComplete"]

        plans = contracts["plans"]
        assert plans["baseTotal"] == 56, plans
        assert plans["trueTotal"] == 70, plans
        assert plans["type"] == "COMPILED_CAMPAIGN_GREYBOX_OPERATION_PLAN", plans
        assert plans["templatePolicyId"] == "GREYBOX_ONLY_STAGE_MODULO", plans
        assert plans["productionReady"] is False, plans
        assert plans["prefixEqual"] is True, plans
        assert plans["prefixValidated"] is True, plans
        assert plans["deterministic"] is True, plans
        assert plans["allNormal"] is True, plans
        assert plans["exactOperationShapes"] is True, plans
        assert plans["defaultTemplateIndices"] == [0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1], plans
        assert plans["threeTemplateTotal"] == 70, plans
        assert plans["threeTemplateIndices"] == [0, 1, 2, 0, 1, 2, 0, 1, 2], plans
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
            "mode": "CAMPAIGN_PROGRESS_CONTRACT",
            "schema_version": contracts["schemaVersion"],
            "base_limit": contracts["baseComplete"]["stageLimit"],
            "true_limit": contracts["trueComplete"]["stageLimit"],
            "operation_kinds": contracts["operationKinds"],
            "true_gate_stage": contracts["trueStart"]["currentStageNumber"],
            "template_cycle": plans["defaultTemplateIndices"][:5],
            "template_policy": plans["templatePolicyId"],
            "production_ready": plans["productionReady"],
            "prefix_preserved": plans["prefixValidated"],
            "invalid_cases": len(contracts["invalid"]),
        }
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description="Validate formal campaign stage authority.")
    parser.add_argument("--url", default="http://127.0.0.1:8771/index.html")
    parser.add_argument("--debug-port", type=int, default=9234)
    args = parser.parse_args()
    print(json.dumps(run(args.url, args.debug_port), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
