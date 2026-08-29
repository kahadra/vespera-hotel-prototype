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
                FORMAL_CAMPAIGN_PROGRESS_CONFIG,
                validateCampaignProgressConfig,
                validateCampaignProgressState,
                createCampaignProgress,
                campaignScenarioTemplateIndex,
                campaignOperationDescriptor,
                campaignOperationId,
                campaignResultIdentity,
                completeCampaignOperation,
                queueCampaignRecovery,
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

              let recoveryProgress = advanceTo(createCampaignProgress(config), 7);
              const boundarySevenRecord = clone(recoveryProgress.operationRecords.at(-1));
              recoveryProgress = queueCampaignRecovery(config, recoveryProgress, 7);
              const recoveryOperation = campaignOperationDescriptor(config, recoveryProgress);
              recoveryProgress = completeCampaignOperation(config, recoveryProgress, recoveryOperation);
              const recoveryRecord = clone(recoveryProgress.operationRecords.at(-1));
              const afterRecoveryOperation = campaignOperationDescriptor(config, recoveryProgress);
              const recoveryBaseComplete = advanceTo(recoveryProgress, 56);
              const recoveryBoundaryMatrix = config.recovery_boundary_stages.map(boundary => {
                const atBoundary = advanceTo(createCampaignProgress(config), boundary);
                const queued = queueCampaignRecovery(config, atBoundary, boundary);
                const operation = campaignOperationDescriptor(config, queued);
                const completed = completeCampaignOperation(config, queued, operation);
                return {
                  boundary,
                  consumedStage: operation.stageNumber,
                  nextStage: completed.currentStageNumber,
                  preservedBoundary: completed.operationRecords.at(-1)
                    .recoveryBoundaryStageNumber,
                };
              });

              let baseProgress = advanceTo(createCampaignProgress(config), 55);
              const day56Operation = campaignOperationDescriptor(config, baseProgress);
              baseProgress = completeCampaignOperation(config, baseProgress, day56Operation);

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
              invalidConfig('recoveryBoundaryDrift', value => {
                value.recovery_boundary_stages = [7, 14, 28, 43];
              });

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
              invalid.queueBeforeBoundary = rejects(() => queueCampaignRecovery(config, initial, 7));
              const atSeven = advanceTo(createCampaignProgress(config), 7);
              invalid.queueWrongBoundary = rejects(() => queueCampaignRecovery(config, atSeven, 14));
              const queuedAtSeven = queueCampaignRecovery(config, atSeven, 7);
              invalid.queueTwice = rejects(() => queueCampaignRecovery(config, queuedAtSeven, 7));
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
              invalid.staleOperation = rejects(() => completeCampaignOperation(
                config,
                afterFirst,
                firstOperation,
              ));
              invalid.operationAfterBaseComplete = rejects(() => campaignOperationDescriptor(
                config,
                baseProgress,
              ));
              invalid.recoveryAtFinalBoundary = rejects(() => queueCampaignRecovery(
                config,
                baseProgress,
                56,
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
              invalid.lostRecoveryReference = rejects(() => {
                const candidate = clone(recoveryProgress);
                candidate.operationRecords[7].recoveryBoundaryStageNumber = null;
                validateCampaignProgressState(config, candidate);
              });
              invalid.recoveryRelabeledNormal = rejects(() => {
                const candidate = clone(recoveryProgress);
                candidate.operationRecords[7].resultIdentity.operationKind = 'NORMAL';
                validateCampaignProgressState(config, candidate);
              });
              invalid.planOptionNotBoolean = rejects(() => compileCampaignGreyboxOperationPlan(
                config,
                { includeTrueExtension: 'yes' },
              ));

              return {
                configValid: validateCampaignProgressConfig(config),
                initial,
                firstOperation,
                firstOperationId,
                firstIdentity,
                inputUnchanged: initialSnapshot === JSON.stringify(initial),
                afterFirst,
                boundarySevenRecord,
                recoveryOperation,
                recoveryRecord,
                afterRecoveryOperation,
                recoveryBaseComplete: {
                  completedStageCount: recoveryBaseComplete.completedStageCount,
                  status: recoveryBaseComplete.status,
                  recoveryRecords: recoveryBaseComplete.operationRecords.filter(
                    record => record.resultIdentity.operationKind === 'RECOVERY'
                  ),
                },
                recoveryBoundaryMatrix,
                day56Operation,
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

        assert contracts["configValid"] is True, contracts
        assert contracts["initial"] == {
            "type": "CAMPAIGN_PROGRESS_STATE",
            "schemaVersion": 1,
            "configId": "FORMAL_CAMPAIGN_PROGRESS",
            "configVersion": 1,
            "completedStageCount": 0,
            "currentStageNumber": 1,
            "stageLimit": 56,
            "trueExtensionUnlocked": False,
            "pendingRecoveryBoundaryStageNumber": None,
            "status": "ACTIVE",
            "operationRecords": [],
        }, contracts["initial"]
        assert contracts["firstOperation"] == {
            "type": "CAMPAIGN_OPERATION",
            "stageNumber": 1,
            "operationKind": "NORMAL",
            "templateIndex": 0,
            "recoveryBoundaryStageNumber": None,
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

        assert contracts["boundarySevenRecord"] == {
            "resultIdentity": {
                "stageNumber": 7,
                "operationKind": "NORMAL",
                "templateIndex": 1,
            },
            "recoveryBoundaryStageNumber": None,
        }, contracts["boundarySevenRecord"]
        assert contracts["recoveryOperation"] == {
            "type": "CAMPAIGN_OPERATION",
            "stageNumber": 8,
            "operationKind": "RECOVERY",
            "templateIndex": 2,
            "recoveryBoundaryStageNumber": 7,
            "templatePolicyId": "GREYBOX_ONLY_STAGE_MODULO",
            "templateProductionReady": False,
        }, contracts["recoveryOperation"]
        assert contracts["recoveryRecord"] == {
            "resultIdentity": {
                "stageNumber": 8,
                "operationKind": "RECOVERY",
                "templateIndex": 2,
            },
            "recoveryBoundaryStageNumber": 7,
        }, contracts["recoveryRecord"]
        assert contracts["afterRecoveryOperation"]["stageNumber"] == 9, contracts
        assert contracts["afterRecoveryOperation"]["operationKind"] == "NORMAL", contracts
        assert contracts["recoveryBaseComplete"] == {
            "completedStageCount": 56,
            "status": "BASE_COMPLETE",
            "recoveryRecords": [contracts["recoveryRecord"]],
        }, contracts["recoveryBaseComplete"]
        assert contracts["recoveryBoundaryMatrix"] == [
            {
                "boundary": boundary,
                "consumedStage": boundary + 1,
                "nextStage": boundary + 2,
                "preservedBoundary": boundary,
            }
            for boundary in [7, 14, 28, 42]
        ], contracts["recoveryBoundaryMatrix"]

        assert contracts["day56Operation"] == {
            "type": "CAMPAIGN_OPERATION",
            "stageNumber": 56,
            "operationKind": "NORMAL",
            "templateIndex": 0,
            "recoveryBoundaryStageNumber": None,
            "templatePolicyId": "GREYBOX_ONLY_STAGE_MODULO",
            "templateProductionReady": False,
        }, contracts["day56Operation"]
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
            "recoveryBoundaryStageNumber": None,
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
            "base_limit": contracts["baseComplete"]["stageLimit"],
            "true_limit": contracts["trueComplete"]["stageLimit"],
            "recovery": {
                "boundary_stage": contracts["recoveryOperation"]["recoveryBoundaryStageNumber"],
                "consumed_stage": contracts["recoveryOperation"]["stageNumber"],
                "next_stage": contracts["afterRecoveryOperation"]["stageNumber"],
            },
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
