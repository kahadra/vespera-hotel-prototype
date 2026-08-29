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
            r"""
            (async () => {
              const finance = await import('./src/campaign-finance.js');
              const {
                CAMPAIGN_FINANCE_BALANCE_VERDICT,
                CAMPAIGN_FINANCE_DEBT_GATE_ID,
                CAMPAIGN_FINANCE_SETTLEMENT_SEQUENCE,
                validateCampaignFinanceConfig,
                validateCampaignFinanceState,
                createCampaignFinanceState,
                commitCampaignDayResult,
                settleCampaignDay,
                campaignDebtGateEvidence,
                unlockCampaignFinanceTrueExtension,
              } = finance;

              const clone = value => JSON.parse(JSON.stringify(value));
              const rejects = callback => {
                try {
                  callback();
                  return false;
                } catch {
                  return true;
                }
              };
              const baseConfig = {
                id: 'FORMAL_CAMPAIGN_FINANCE_BASE_TEST',
                version: 1,
                contract_status: 'PROVISIONAL',
                total_stages: 56,
                debt_deadline_stage: 56,
                debt_gate_id: CAMPAIGN_FINANCE_DEBT_GATE_ID,
                starting_cash: 50,
                principal: 100,
                chapter_cumulative_targets: {
                  '7': 10,
                  '14': 20,
                  '28': 40,
                  '42': 60,
                  '56': 100,
                },
              };
              const extendedConfig = {
                ...clone(baseConfig),
                id: 'FORMAL_CAMPAIGN_FINANCE_TRUE_TEST',
                total_stages: 70,
              };
              const dayResult = (state, overrides = {}) => ({
                stageNumber: overrides.stageNumber ?? state.nextStageNumber,
                campaignOperationId: overrides.campaignOperationId
                  ?? `FINANCE-OP-${overrides.stageNumber ?? state.nextStageNumber}`,
                campaignResultIdentity: overrides.campaignResultIdentity ?? {
                  stageNumber: overrides.stageNumber ?? state.nextStageNumber,
                  operationKind: overrides.operationKind ?? 'NORMAL',
                  templateIndex: overrides.templateIndex
                    ?? ((overrides.stageNumber ?? state.nextStageNumber) - 1) % 5,
                },
                income: 3,
                upkeep: 1,
                reactivation: 0,
                roomService: 0,
                ...Object.fromEntries(Object.entries(overrides).filter(
                  ([key]) => !['operationKind', 'templateIndex'].includes(key),
                )),
              });
              const closeDay = (
                activeConfig,
                source,
                repayment = 0,
                resultOverrides = {},
              ) => {
                const committed = commitCampaignDayResult(
                  activeConfig,
                  source,
                  dayResult(source, resultOverrides),
                );
                return settleCampaignDay(
                  activeConfig,
                  committed,
                  { manualRepayment: repayment },
                );
              };
              const advanceTo = (activeConfig, source, target, repayments = {}) => {
                let state = source;
                while (state.completedStageCount < target) {
                  const stage = state.nextStageNumber;
                  state = closeDay(
                    activeConfig,
                    state,
                    repayments[String(stage)] ?? 0,
                  );
                }
                return state;
              };

              const initial = createCampaignFinanceState(baseConfig);
              const initialSnapshot = JSON.stringify(initial);
              const day1Input = dayResult(initial, {
                income: 12,
                upkeep: 2,
                reactivation: 4,
                roomService: 3,
              });
              const day1InputSnapshot = JSON.stringify(day1Input);
              const day1Committed = commitCampaignDayResult(baseConfig, initial, day1Input);
              const day1CommittedSnapshot = JSON.stringify(day1Committed);
              const day1Settled = settleCampaignDay(
                baseConfig,
                day1Committed,
                { manualRepayment: 0 },
              );
              const immutableInputs = {
                initialUnchanged: JSON.stringify(initial) === initialSnapshot,
                dayInputUnchanged: JSON.stringify(day1Input) === day1InputSnapshot,
                committedUnchanged: JSON.stringify(day1Committed) === day1CommittedSnapshot,
              };

              const day2Settled = closeDay(baseConfig, day1Settled);
              const detachedCopy = clone(day2Settled);
              detachedCopy.ledger[0].income = 999;
              immutableInputs.oldLedgerDetached = day1Settled.ledger[0].income === 12;

              let mixedRun = advanceTo(baseConfig, day2Settled, 6);
              const day7Committed = commitCampaignDayResult(
                baseConfig,
                mixedRun,
                dayResult(mixedRun),
              );
              const preRepaymentAtSeven = {
                ledgerCount: day7Committed.ledger.length,
                cumulativeRepayment: day7Committed.cumulativeRepayment,
                remainingDebt: day7Committed.remainingDebt,
                cashAfterOperations: day7Committed.cash,
              };
              mixedRun = settleCampaignDay(
                baseConfig,
                day7Committed,
                { manualRepayment: 10 },
              );
              const day7Checkpoint = clone(mixedRun.ledger.at(-1).checkpoint);

              mixedRun = advanceTo(baseConfig, mixedRun, 14);
              const day14Checkpoint = clone(mixedRun.ledger.at(-1).checkpoint);
              mixedRun = closeDay(
                baseConfig,
                mixedRun,
                0,
                { operationKind: 'RECOVERY' },
              );
              const recoveryOperationEntry = clone(mixedRun.ledger.at(-1));
              mixedRun = advanceTo(baseConfig, mixedRun, 56, {
                '28': 30,
                '42': 20,
                '56': 40,
              });
              const day56Entry = clone(mixedRun.ledger[55]);
              const passedEvidence = campaignDebtGateEvidence(baseConfig, mixedRun);
              const baseCompleteState = mixedRun;
              const basePrefixSnapshot = JSON.stringify(mixedRun.ledger);
              const baseCompleteSnapshot = JSON.stringify(mixedRun);
              mixedRun = unlockCampaignFinanceTrueExtension(
                baseConfig,
                extendedConfig,
                mixedRun,
                passedEvidence,
              );
              const extensionStart = {
                configId: mixedRun.configId,
                totalStages: mixedRun.totalStages,
                completedStageCount: mixedRun.completedStageCount,
                nextStageNumber: mixedRun.nextStageNumber,
                phase: mixedRun.phase,
                status: mixedRun.status,
                prefixPreserved: JSON.stringify(mixedRun.ledger) === basePrefixSnapshot,
                baseInputUnchanged: JSON.stringify(baseCompleteState) === baseCompleteSnapshot,
              };
              const day57Committed = commitCampaignDayResult(
                extendedConfig,
                mixedRun,
                dayResult(mixedRun, {
                  income: 8,
                  upkeep: 2,
                  reactivation: 1,
                  roomService: 2,
                }),
              );
              const postDebtBeforeSettlement = clone(day57Committed.pendingDayResult);
              mixedRun = settleCampaignDay(
                extendedConfig,
                day57Committed,
                { manualRepayment: 0 },
              );
              const day57Entry = clone(mixedRun.ledger[56]);
              mixedRun = advanceTo(extendedConfig, mixedRun, 70);

              let failedRun = createCampaignFinanceState(baseConfig);
              failedRun = advanceTo(baseConfig, failedRun, 56);
              const failedEvidence = campaignDebtGateEvidence(baseConfig, failedRun);

              const zeroConfig = {
                ...clone(baseConfig),
                id: 'ZERO_PRINCIPAL_FINANCE_TEST',
                total_stages: 56,
                starting_cash: 0,
                principal: 0,
                chapter_cumulative_targets: {
                  '7': 0,
                  '14': 0,
                  '28': 0,
                  '42': 0,
                  '56': 0,
                },
              };
              let zeroRun = createCampaignFinanceState(zeroConfig);
              while (zeroRun.completedStageCount < 56) {
                const committed = commitCampaignDayResult(
                  zeroConfig,
                  zeroRun,
                  dayResult(zeroRun, {
                    income: 0,
                    upkeep: 0,
                    reactivation: 0,
                    roomService: 0,
                  }),
                );
                zeroRun = settleCampaignDay(zeroConfig, committed, { manualRepayment: 0 });
              }
              const zeroEvidence = campaignDebtGateEvidence(zeroConfig, zeroRun);

              const invalid = {};
              const invalidConfig = (name, mutate) => {
                const candidate = clone(baseConfig);
                mutate(candidate);
                invalid[name] = rejects(() => validateCampaignFinanceConfig(candidate));
              };
              invalidConfig('negativeStartingCash', value => { value.starting_cash = -1; });
              invalidConfig('unsafePrincipal', value => {
                value.principal = Number.MAX_SAFE_INTEGER + 1;
                value.chapter_cumulative_targets['56'] = value.principal;
              });
              invalidConfig('wrongContractStatus', value => { value.contract_status = 'FINAL'; });
              invalidConfig('unsupportedStageLimit', value => { value.total_stages = 69; });
              invalidConfig('wrongDeadline', value => { value.debt_deadline_stage = 57; });
              invalidConfig('wrongGate', value => { value.debt_gate_id = 'WRONG'; });
              invalidConfig('missingCheckpoint', value => {
                delete value.chapter_cumulative_targets['42'];
              });
              invalidConfig('extraCheckpoint', value => {
                value.chapter_cumulative_targets['21'] = 30;
              });
              invalidConfig('decreasingCheckpoint', value => {
                value.chapter_cumulative_targets['28'] = 19;
              });
              invalidConfig('finalTargetNotPrincipal', value => {
                value.chapter_cumulative_targets['56'] = 99;
              });
              invalidConfig('extraConfigField', value => { value.balance = 'FINAL'; });
              invalid.createExtendedDirectly = rejects(() => createCampaignFinanceState(
                extendedConfig,
              ));
              invalid.emptyOperationId = rejects(() => commitCampaignDayResult(
                baseConfig,
                initial,
                dayResult(initial, { campaignOperationId: '   ' }),
              ));
              invalid.identityStageMismatch = rejects(() => commitCampaignDayResult(
                baseConfig,
                initial,
                dayResult(initial, {
                  campaignResultIdentity: {
                    stageNumber: 2,
                    operationKind: 'NORMAL',
                    templateIndex: 0,
                  },
                }),
              ));
              invalid.identityUnknownKind = rejects(() => commitCampaignDayResult(
                baseConfig,
                initial,
                dayResult(initial, {
                  campaignResultIdentity: {
                    stageNumber: 1,
                    operationKind: 'BONUS',
                    templateIndex: 0,
                  },
                }),
              ));
              invalid.identityUnsafeTemplate = rejects(() => commitCampaignDayResult(
                baseConfig,
                initial,
                dayResult(initial, {
                  campaignResultIdentity: {
                    stageNumber: 1,
                    operationKind: 'NORMAL',
                    templateIndex: Number.MAX_SAFE_INTEGER + 1,
                  },
                }),
              ));
              invalid.identityExtraField = rejects(() => commitCampaignDayResult(
                baseConfig,
                initial,
                dayResult(initial, {
                  campaignResultIdentity: {
                    stageNumber: 1,
                    operationKind: 'NORMAL',
                    templateIndex: 0,
                    extra: true,
                  },
                }),
              ));
              invalid.duplicateOperationId = rejects(() => commitCampaignDayResult(
                baseConfig,
                day1Settled,
                dayResult(day1Settled, {
                  campaignOperationId: day1Settled.ledger[0].campaignOperationId,
                }),
              ));
              invalid.negativeIncome = rejects(() => commitCampaignDayResult(
                baseConfig,
                initial,
                dayResult(initial, { income: -1 }),
              ));
              invalid.unsafeIncome = rejects(() => commitCampaignDayResult(
                baseConfig,
                initial,
                dayResult(initial, { income: Number.MAX_SAFE_INTEGER }),
              ));
              invalid.negativeUpkeep = rejects(() => commitCampaignDayResult(
                baseConfig,
                initial,
                dayResult(initial, { upkeep: -1 }),
              ));
              invalid.negativeReactivation = rejects(() => commitCampaignDayResult(
                baseConfig,
                initial,
                dayResult(initial, { reactivation: -1 }),
              ));
              invalid.negativeRoomService = rejects(() => commitCampaignDayResult(
                baseConfig,
                initial,
                dayResult(initial, { roomService: -1 }),
              ));
              invalid.operatingShortfall = rejects(() => commitCampaignDayResult(
                baseConfig,
                initial,
                dayResult(initial, {
                  income: 0,
                  upkeep: 30,
                  reactivation: 10,
                  roomService: 11,
                }),
              ));
              invalid.wrongStage = rejects(() => commitCampaignDayResult(
                baseConfig,
                initial,
                dayResult(initial, { stageNumber: 2 }),
              ));
              invalid.extraResultField = rejects(() => commitCampaignDayResult(
                baseConfig,
                initial,
                { ...dayResult(initial), extra: true },
              ));
              invalid.missingRoomService = rejects(() => {
                const candidate = dayResult(initial);
                delete candidate.roomService;
                commitCampaignDayResult(baseConfig, initial, candidate);
              });
              invalid.settleBeforeCommit = rejects(() => settleCampaignDay(
                baseConfig,
                initial,
                { manualRepayment: 0 },
              ));
              invalid.commitTwice = rejects(() => commitCampaignDayResult(
                baseConfig,
                day1Committed,
                dayResult(day1Committed, { stageNumber: 1 }),
              ));
              invalid.negativeRepayment = rejects(() => settleCampaignDay(
                baseConfig,
                day1Committed,
                { manualRepayment: -1 },
              ));
              invalid.repaymentPastDebt = rejects(() => settleCampaignDay(
                baseConfig,
                day1Committed,
                { manualRepayment: 101 },
              ));
              invalid.repaymentPastCash = rejects(() => settleCampaignDay(
                baseConfig,
                day1Committed,
                { manualRepayment: day1Committed.cash + 1 },
              ));
              invalid.extraSettlementField = rejects(() => settleCampaignDay(
                baseConfig,
                day1Committed,
                { manualRepayment: 0, extra: true },
              ));
              invalid.gateBeforeDeadline = rejects(() => campaignDebtGateEvidence(
                baseConfig,
                day1Settled,
              ));
              invalid.day57Repayment = rejects(() => settleCampaignDay(
                extendedConfig,
                day57Committed,
                { manualRepayment: 1 },
              ));
              invalid.day57AfterMissedDeadline = rejects(() => commitCampaignDayResult(
                baseConfig,
                failedRun,
                dayResult(failedRun, { stageNumber: 57, income: 100 }),
              ));
              invalid.sparseLedger = rejects(() => {
                const candidate = clone(day1Settled);
                candidate.ledger = new Array(1);
                validateCampaignFinanceState(baseConfig, candidate);
              });
              invalid.tamperedCashConservation = rejects(() => {
                const candidate = clone(day1Settled);
                candidate.ledger[0].cashConservation.delta = 1;
                validateCampaignFinanceState(baseConfig, candidate);
              });
              invalid.tamperedDebtConservation = rejects(() => {
                const candidate = clone(day1Settled);
                candidate.ledger[0].closingDebt = 99;
                validateCampaignFinanceState(baseConfig, candidate);
              });
              invalid.tamperedOperationId = rejects(() => {
                const candidate = clone(day1Settled);
                candidate.ledger[0].campaignOperationId = '';
                validateCampaignFinanceState(baseConfig, candidate);
              });
              invalid.tamperedResultIdentity = rejects(() => {
                const candidate = clone(day1Settled);
                candidate.ledger[0].campaignResultIdentity.stageNumber = 2;
                validateCampaignFinanceState(baseConfig, candidate);
              });
              invalid.tamperedRoomServiceConservation = rejects(() => {
                const candidate = clone(day1Settled);
                candidate.ledger[0].roomService += 1;
                validateCampaignFinanceState(baseConfig, candidate);
              });
              invalid.tamperedCheckpointOrder = rejects(() => {
                const candidate = clone(mixedRun);
                candidate.ledger[6].checkpoint.outcome = 'RECOVERY_REQUIRED';
                validateCampaignFinanceState(extendedConfig, candidate);
              });
              invalid.retroactiveDeadlineFlag = rejects(() => {
                const candidate = clone(failedRun);
                candidate.debtClearedAtDeadline = true;
                candidate.status = 'ACTIVE';
                candidate.phase = 'AWAITING_RESULT';
                candidate.nextStageNumber = 57;
                validateCampaignFinanceState(baseConfig, candidate);
              });
              invalid.unlockEarly = rejects(() => unlockCampaignFinanceTrueExtension(
                baseConfig,
                extendedConfig,
                day1Settled,
                passedEvidence,
              ));
              invalid.unlockFailedDebt = rejects(() => unlockCampaignFinanceTrueExtension(
                baseConfig,
                extendedConfig,
                failedRun,
                failedEvidence,
              ));
              invalid.unlockWrongEvidence = rejects(() => unlockCampaignFinanceTrueExtension(
                baseConfig,
                extendedConfig,
                baseCompleteState,
                { ...passedEvidence, remainingDebtAtBoundary: 1 },
              ));
              invalid.unlockFailedEvidenceFlag = rejects(() => unlockCampaignFinanceTrueExtension(
                baseConfig,
                extendedConfig,
                baseCompleteState,
                { ...passedEvidence, passed: false },
              ));
              invalid.unlockSameId = rejects(() => unlockCampaignFinanceTrueExtension(
                baseConfig,
                { ...clone(extendedConfig), id: baseConfig.id },
                baseCompleteState,
                passedEvidence,
              ));
              invalid.unlockVersionDrift = rejects(() => unlockCampaignFinanceTrueExtension(
                baseConfig,
                { ...clone(extendedConfig), version: 2 },
                baseCompleteState,
                passedEvidence,
              ));
              invalid.unlockCashDrift = rejects(() => unlockCampaignFinanceTrueExtension(
                baseConfig,
                { ...clone(extendedConfig), starting_cash: 51 },
                baseCompleteState,
                passedEvidence,
              ));
              invalid.unlockTargetDrift = rejects(() => {
                const candidate = clone(extendedConfig);
                candidate.chapter_cumulative_targets['42'] = 61;
                unlockCampaignFinanceTrueExtension(
                  baseConfig,
                  candidate,
                  baseCompleteState,
                  passedEvidence,
                );
              });
              invalid.unlockTwice = rejects(() => unlockCampaignFinanceTrueExtension(
                baseConfig,
                extendedConfig,
                mixedRun,
                passedEvidence,
              ));

              return {
                configValid: validateCampaignFinanceConfig(baseConfig)
                  && validateCampaignFinanceConfig(extendedConfig),
                initial,
                immutableInputs,
                day1Committed: {
                  phase: day1Committed.phase,
                  ledgerCount: day1Committed.ledger.length,
                  cash: day1Committed.cash,
                  remainingDebt: day1Committed.remainingDebt,
                  pending: day1Committed.pendingDayResult,
                },
                day1Entry: day1Settled.ledger[0],
                preRepaymentAtSeven,
                day7Checkpoint,
                day14Checkpoint,
                recoveryOperationEntry,
                day56Entry,
                passedEvidence,
                extensionStart,
                postDebtBeforeSettlement,
                day57Entry,
                finalState: {
                  completedStageCount: mixedRun.completedStageCount,
                  status: mixedRun.status,
                  phase: mixedRun.phase,
                  nextStageNumber: mixedRun.nextStageNumber,
                  remainingDebt: mixedRun.remainingDebt,
                  ledgerCount: mixedRun.ledger.length,
                  configId: mixedRun.configId,
                  valid: validateCampaignFinanceState(extendedConfig, mixedRun),
                },
                failedState: {
                  completedStageCount: failedRun.completedStageCount,
                  status: failedRun.status,
                  phase: failedRun.phase,
                  nextStageNumber: failedRun.nextStageNumber,
                  remainingDebt: failedRun.remainingDebt,
                },
                failedEvidence,
                zeroConfig: {
                  passed: zeroEvidence.passed,
                  outcome: zeroEvidence.checkpointOutcome,
                  status: zeroRun.status,
                  remainingDebt: zeroRun.remainingDebt,
                },
                conservation: {
                  everyCashDeltaZero: mixedRun.ledger.every(
                    entry => entry.cashConservation.delta === 0,
                  ),
                  everyDebtDeltaZero: mixedRun.ledger.every(
                    entry => entry.debtConservation.delta === 0,
                  ),
                },
                constants: {
                  balanceVerdict: CAMPAIGN_FINANCE_BALANCE_VERDICT,
                  settlementSequence: CAMPAIGN_FINANCE_SETTLEMENT_SEQUENCE,
                },
                invalid,
              };
            })()
            """
        )

        assert contracts["configValid"] is True, contracts
        assert contracts["initial"]["cash"] == 50, contracts["initial"]
        assert contracts["initial"]["remainingDebt"] == 100, contracts["initial"]
        assert contracts["initial"]["totalStages"] == 56, contracts["initial"]
        assert contracts["initial"]["balanceVerdict"] == "NOT_EVALUATED"
        assert all(contracts["immutableInputs"].values()), contracts["immutableInputs"]

        committed = contracts["day1Committed"]
        assert committed["phase"] == "RESULT_COMMITTED", committed
        assert committed["ledgerCount"] == 0, committed
        assert committed["cash"] == 53, committed
        assert committed["remainingDebt"] == 100, committed
        assert committed["pending"]["cashAfterOperations"] == 53, committed
        assert committed["pending"]["campaignOperationId"] == "FINANCE-OP-1"
        assert committed["pending"]["campaignResultIdentity"] == {
            "stageNumber": 1,
            "operationKind": "NORMAL",
            "templateIndex": 0,
        }, committed
        day1 = contracts["day1Entry"]
        assert day1["settlementSequence"] == (
            "RESULT_COMMIT_THEN_OPTIONAL_REPAYMENT_THEN_CHECKPOINT"
        )
        assert day1["campaignOperationId"] == "FINANCE-OP-1"
        assert day1["campaignResultIdentity"] == {
            "stageNumber": 1,
            "operationKind": "NORMAL",
            "templateIndex": 0,
        }, day1
        assert day1["income"] == 12 and day1["upkeep"] == 2
        assert day1["reactivation"] == 4 and day1["roomService"] == 3
        assert day1["manualRepayment"] == 0
        assert day1["cashConservation"]["delta"] == 0
        assert day1["debtConservation"]["delta"] == 0

        assert contracts["preRepaymentAtSeven"] == {
            "ledgerCount": 6,
            "cumulativeRepayment": 0,
            "remainingDebt": 100,
            "cashAfterOperations": 65,
        }, contracts["preRepaymentAtSeven"]
        assert contracts["day7Checkpoint"] == {
            "type": "CAMPAIGN_DEBT_CHECKPOINT",
            "stageNumber": 7,
            "kind": "CUMULATIVE_MINIMUM",
            "targetAmount": 10,
            "cumulativeRepayment": 10,
            "remainingDebt": 90,
            "shortfallAmount": 0,
            "outcome": "MET",
            "recoveryRequirement": None,
            "debtDeadlineExtended": False,
        }, contracts["day7Checkpoint"]
        recovery = contracts["day14Checkpoint"]
        assert recovery["outcome"] == "RECOVERY_REQUIRED", recovery
        assert recovery["shortfallAmount"] == 10, recovery
        assert recovery["debtDeadlineExtended"] is False, recovery
        assert recovery["recoveryRequirement"] == {
            "type": "CAMPAIGN_FINANCE_RECOVERY_REQUIREMENT",
            "required": True,
            "boundaryStageNumber": 14,
            "shortfallAmount": 10,
            "deadlineExtensionAllowed": False,
            "penaltyPolicyStatus": "TBD",
        }, recovery
        assert contracts["recoveryOperationEntry"]["campaignResultIdentity"] == {
            "stageNumber": 15,
            "operationKind": "RECOVERY",
            "templateIndex": 4,
        }, contracts["recoveryOperationEntry"]
        assert contracts["recoveryOperationEntry"]["campaignOperationId"] == "FINANCE-OP-15"

        day56 = contracts["day56Entry"]
        assert day56["checkpoint"]["outcome"] == "DEBT_CLEARED", day56
        assert day56["checkpoint"]["remainingDebt"] == 0, day56
        assert day56["checkpoint"]["debtDeadlineExtended"] is False, day56
        passed = contracts["passedEvidence"]
        assert passed["gateId"] == "BASE_DEBT_CLEARED_AT_STAGE_56", passed
        assert passed["passed"] is True, passed
        assert passed["boundaryStageNumber"] == 56, passed
        assert passed["remainingDebtAtBoundary"] == 0, passed
        assert passed["debtGraceAfterBoundary"] is False, passed
        assert contracts["extensionStart"] == {
            "configId": "FORMAL_CAMPAIGN_FINANCE_TRUE_TEST",
            "totalStages": 70,
            "completedStageCount": 56,
            "nextStageNumber": 57,
            "phase": "AWAITING_RESULT",
            "status": "ACTIVE",
            "prefixPreserved": True,
            "baseInputUnchanged": True,
        }, contracts["extensionStart"]

        assert contracts["postDebtBeforeSettlement"]["stageNumber"] == 57
        assert contracts["postDebtBeforeSettlement"]["openingDebt"] == 0
        assert contracts["postDebtBeforeSettlement"]["campaignOperationId"] == "FINANCE-OP-57"
        assert contracts["postDebtBeforeSettlement"]["roomService"] == 2
        day57 = contracts["day57Entry"]
        assert day57["openingDebt"] == 0 and day57["closingDebt"] == 0, day57
        assert day57["manualRepayment"] == 0, day57
        assert day57["checkpoint"] is None, day57
        assert contracts["finalState"] == {
            "completedStageCount": 70,
            "status": "COMPLETE",
            "phase": "CLOSED",
            "nextStageNumber": None,
            "remainingDebt": 0,
            "ledgerCount": 70,
            "configId": "FORMAL_CAMPAIGN_FINANCE_TRUE_TEST",
            "valid": True,
        }, contracts["finalState"]

        failed = contracts["failedState"]
        assert failed["completedStageCount"] == 56, failed
        assert failed["status"] == "DEBT_DEADLINE_MISSED", failed
        assert failed["phase"] == "CLOSED" and failed["nextStageNumber"] is None, failed
        assert failed["remainingDebt"] == 100, failed
        failed_evidence = contracts["failedEvidence"]
        assert failed_evidence["passed"] is False, failed_evidence
        assert failed_evidence["checkpointOutcome"] == "DEBT_DEADLINE_MISSED"
        assert failed_evidence["remainingDebtAtBoundary"] == 100
        assert failed_evidence["debtGraceAfterBoundary"] is False
        assert contracts["zeroConfig"] == {
            "passed": True,
            "outcome": "DEBT_CLEARED",
            "status": "COMPLETE",
            "remainingDebt": 0,
        }, contracts["zeroConfig"]

        assert all(contracts["conservation"].values()), contracts["conservation"]
        assert contracts["constants"] == {
            "balanceVerdict": "NOT_EVALUATED",
            "settlementSequence": (
                "RESULT_COMMIT_THEN_OPTIONAL_REPAYMENT_THEN_CHECKPOINT"
            ),
        }, contracts["constants"]
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
            "mode": "CAMPAIGN_FINANCE_CONTRACT",
            "balance_verdict": contracts["constants"]["balanceVerdict"],
            "settlement_sequence": contracts["constants"]["settlementSequence"],
            "checkpoint_stages": [7, 14, 28, 42, 56],
            "recovery_outcome": contracts["day14Checkpoint"]["outcome"],
            "recovery_penalty_status": contracts["day14Checkpoint"][
                "recoveryRequirement"
            ]["penaltyPolicyStatus"],
            "day_56_gate": contracts["passedEvidence"]["passed"],
            "true_extension_prefix": contracts["extensionStart"]["prefixPreserved"],
            "day_57_debt_grace": contracts["passedEvidence"]["debtGraceAfterBoundary"],
            "completed_stages": contracts["finalState"]["completedStageCount"],
            "cash_conservation": contracts["conservation"]["everyCashDeltaZero"],
            "debt_conservation": contracts["conservation"]["everyDebtDeltaZero"],
            "invalid_cases": len(contracts["invalid"]),
        }
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description="Validate provisional campaign finance ledger.")
    parser.add_argument("--url", default="http://127.0.0.1:8774/index.html")
    parser.add_argument("--debug-port", type=int, default=9237)
    args = parser.parse_args()
    print(json.dumps(run(args.url, args.debug_port), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
