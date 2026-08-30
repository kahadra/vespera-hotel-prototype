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
                CAMPAIGN_FINANCE_OPERATION_KINDS,
                CAMPAIGN_FINANCE_SCHEMA_VERSION,
                CAMPAIGN_FINANCE_SETTLEMENT_SEQUENCE,
                validateCampaignFinanceConfig,
                validateCampaignFinanceState,
                createCampaignFinanceState,
                commitCampaignDayResult,
                settleCampaignDay,
                campaignRepaymentForecast,
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
              const initialForecast = campaignRepaymentForecast(baseConfig, initial);
              const detachedForecast = campaignRepaymentForecast(baseConfig, initial);
              detachedForecast.remainingAmount = 999;
              const forecastDetached = campaignRepaymentForecast(
                baseConfig,
                initial,
              ).remainingAmount === 10;
              const day1Input = dayResult(initial, {
                income: 12,
                upkeep: 2,
                reactivation: 4,
                roomService: 3,
              });
              const day1InputSnapshot = JSON.stringify(day1Input);
              const day1Committed = commitCampaignDayResult(baseConfig, initial, day1Input);
              const day1ForecastWithoutProposal = campaignRepaymentForecast(
                baseConfig,
                day1Committed,
              );
              const day1ForecastWithProposal = campaignRepaymentForecast(
                baseConfig,
                day1Committed,
                4,
              );
              const day1CommittedSnapshot = JSON.stringify(day1Committed);
              const day1Settled = settleCampaignDay(
                baseConfig,
                day1Committed,
                { manualRepayment: 0 },
              );
              const shortfallInput = dayResult(day1Settled, {
                income: 2,
                upkeep: 30,
                reactivation: 10,
                roomService: 16,
              });
              const shortfallSourceSnapshot = JSON.stringify(day1Settled);
              const shortfallInputSnapshot = JSON.stringify(shortfallInput);
              const shortfallRun = commitCampaignDayResult(
                baseConfig,
                day1Settled,
                shortfallInput,
              );
              const shortfallForecast = campaignRepaymentForecast(
                baseConfig,
                shortfallRun,
              );
              const immutableInputs = {
                initialUnchanged: JSON.stringify(initial) === initialSnapshot,
                dayInputUnchanged: JSON.stringify(day1Input) === day1InputSnapshot,
                committedUnchanged: JSON.stringify(day1Committed) === day1CommittedSnapshot,
                shortfallSourceUnchanged:
                  JSON.stringify(day1Settled) === shortfallSourceSnapshot,
                shortfallInputUnchanged:
                  JSON.stringify(shortfallInput) === shortfallInputSnapshot,
              };

              const day2Settled = closeDay(baseConfig, day1Settled);
              const detachedCopy = clone(day2Settled);
              detachedCopy.ledger[0].income = 999;
              immutableInputs.oldLedgerDetached = day1Settled.ledger[0].income === 12;

              const explicitRepayments = {
                '2': 3,
                '4': 7,
                '9': 5,
                '14': 5,
                '18': 10,
                '28': 10,
                '35': 10,
                '42': 10,
                '49': 15,
                '56': 25,
              };
              let mixedRun = closeDay(baseConfig, day1Settled, explicitRepayments['2']);
              mixedRun = advanceTo(baseConfig, mixedRun, 6, explicitRepayments);
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
              const metAtBoundaryForecast = campaignRepaymentForecast(
                baseConfig,
                day7Committed,
              );
              mixedRun = settleCampaignDay(
                baseConfig,
                day7Committed,
                { manualRepayment: explicitRepayments['7'] ?? 0 },
              );
              const day7Checkpoint = clone(mixedRun.ledger.at(-1).checkpoint);
              const afterDay7Forecast = campaignRepaymentForecast(baseConfig, mixedRun);

              mixedRun = advanceTo(baseConfig, mixedRun, 14, explicitRepayments);
              const day14Checkpoint = clone(mixedRun.ledger.at(-1).checkpoint);
              mixedRun = advanceTo(baseConfig, mixedRun, 56, explicitRepayments);
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

              let hurdleBoundaryState = createCampaignFinanceState(baseConfig);
              hurdleBoundaryState = advanceTo(baseConfig, hurdleBoundaryState, 6);
              const hurdleBoundaryCommitted = commitCampaignDayResult(
                baseConfig,
                hurdleBoundaryState,
                dayResult(hurdleBoundaryState),
              );
              const hurdleBoundaryForecast = campaignRepaymentForecast(
                baseConfig,
                hurdleBoundaryCommitted,
                9,
              );
              const hurdleBoundaryMetForecast = campaignRepaymentForecast(
                baseConfig,
                hurdleBoundaryCommitted,
                10,
              );
              let hurdleMissRun = settleCampaignDay(
                baseConfig,
                hurdleBoundaryCommitted,
                { manualRepayment: 0 },
              );
              const hurdleMissCheckpoint = clone(hurdleMissRun.ledger.at(-1).checkpoint);

              let overTargetState = createCampaignFinanceState(baseConfig);
              overTargetState = advanceTo(baseConfig, overTargetState, 6);
              overTargetState = closeDay(baseConfig, overTargetState, 25);
              const overTargetForecast = campaignRepaymentForecast(
                baseConfig,
                overTargetState,
              );

              let debtBoundState = createCampaignFinanceState(baseConfig);
              debtBoundState = advanceTo(baseConfig, debtBoundState, 42, {
                '7': 10,
                '14': 10,
                '28': 20,
                '42': 55,
              });
              const debtBoundCommitted = commitCampaignDayResult(
                baseConfig,
                debtBoundState,
                dayResult(debtBoundState),
              );

              let deadlineMissRun = createCampaignFinanceState(baseConfig);
              deadlineMissRun = advanceTo(baseConfig, deadlineMissRun, 56, {
                '7': 10,
                '14': 10,
                '28': 20,
                '42': 20,
              });
              const failedEvidence = campaignDebtGateEvidence(baseConfig, deadlineMissRun);
              const closedHurdleForecast = campaignRepaymentForecast(
                baseConfig,
                hurdleMissRun,
              );
              const closedDeadlineForecast = campaignRepaymentForecast(
                baseConfig,
                deadlineMissRun,
              );
              const completedBaseForecast = campaignRepaymentForecast(
                baseConfig,
                baseCompleteState,
              );
              const postDeadlineForecast = campaignRepaymentForecast(
                extendedConfig,
                day57Committed,
              );

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
              const invalidOperatingFailure = (name, mutate) => {
                const candidate = clone(shortfallRun);
                mutate(candidate);
                invalid[name] = rejects(() => validateCampaignFinanceState(
                  baseConfig,
                  candidate,
                ));
              };
              invalidOperatingFailure('failureSchemaVersion', value => {
                value.schemaVersion = 2;
              });
              invalidOperatingFailure('failureMissingEvidence', value => {
                value.operatingFailure = null;
              });
              invalidOperatingFailure('failurePendingResult', value => {
                value.pendingDayResult = clone(day1Committed.pendingDayResult);
              });
              invalidOperatingFailure('failureWrongPhase', value => {
                value.phase = 'AWAITING_RESULT';
              });
              invalidOperatingFailure('failureWrongStatus', value => {
                value.status = 'ACTIVE';
              });
              invalidOperatingFailure('failureNextStage', value => {
                value.nextStageNumber = 2;
              });
              invalidOperatingFailure('failureAppliedCash', value => {
                value.cash = value.operatingFailure.availableCash;
              });
              invalidOperatingFailure('failureChangedDebt', value => {
                value.remainingDebt -= 1;
                value.cumulativeRepayment += 1;
              });
              invalidOperatingFailure('failureAppliedStage', value => {
                value.completedStageCount += 1;
              });
              invalidOperatingFailure('failureWrongType', value => {
                value.operatingFailure.type = 'UNKNOWN_FAILURE';
              });
              invalidOperatingFailure('failureExtraEvidenceField', value => {
                value.operatingFailure.extra = true;
              });
              invalidOperatingFailure('failureWrongStage', value => {
                value.operatingFailure.stageNumber = 3;
              });
              invalidOperatingFailure('failureEmptyOperationId', value => {
                value.operatingFailure.campaignOperationId = '   ';
              });
              invalidOperatingFailure('failureDuplicateOperationId', value => {
                value.operatingFailure.campaignOperationId = 'FINANCE-OP-1';
              });
              invalidOperatingFailure('failureIdentityStage', value => {
                value.operatingFailure.campaignResultIdentity.stageNumber = 3;
              });
              invalidOperatingFailure('failureIdentityKind', value => {
                value.operatingFailure.campaignResultIdentity.operationKind = 'RECOVERY';
              });
              invalidOperatingFailure('failureOpeningCash', value => {
                value.operatingFailure.openingCash += 1;
              });
              invalidOperatingFailure('failureIncome', value => {
                value.operatingFailure.income += 1;
              });
              invalidOperatingFailure('failureAvailableCash', value => {
                value.operatingFailure.availableCash += 1;
              });
              invalidOperatingFailure('failureUpkeep', value => {
                value.operatingFailure.upkeep += 1;
              });
              invalidOperatingFailure('failureReactivation', value => {
                value.operatingFailure.reactivation += 1;
              });
              invalidOperatingFailure('failureRoomService', value => {
                value.operatingFailure.roomService += 1;
              });
              invalidOperatingFailure('failureOperatingOutflow', value => {
                value.operatingFailure.operatingOutflow += 1;
              });
              invalidOperatingFailure('failureShortfallAmount', value => {
                value.operatingFailure.shortfallAmount += 1;
              });
              invalid.commitAfterOperatingFailure = rejects(() => commitCampaignDayResult(
                baseConfig,
                shortfallRun,
                dayResult(shortfallRun, { stageNumber: 2 }),
              ));
              invalid.settleAfterOperatingFailure = rejects(() => settleCampaignDay(
                baseConfig,
                shortfallRun,
                { manualRepayment: 0 },
              ));
              invalid.forecastProposalAfterOperatingFailure = rejects(
                () => campaignRepaymentForecast(baseConfig, shortfallRun, 1),
              );
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
              invalid.forecastNonzeroBeforeResult = rejects(() => campaignRepaymentForecast(
                baseConfig,
                initial,
                1,
              ));
              invalid.forecastNegativeProposal = rejects(() => campaignRepaymentForecast(
                baseConfig,
                day1Committed,
                -1,
              ));
              invalid.forecastUnsafeProposal = rejects(() => campaignRepaymentForecast(
                baseConfig,
                day1Committed,
                Number.MAX_SAFE_INTEGER,
              ));
              invalid.forecastPastCash = rejects(() => campaignRepaymentForecast(
                baseConfig,
                day1Committed,
                day1Committed.cash + 1,
              ));
              invalid.forecastPastDebt = rejects(() => campaignRepaymentForecast(
                baseConfig,
                debtBoundCommitted,
                6,
              ));
              invalid.forecastProposalAfterHurdleMiss = rejects(
                () => campaignRepaymentForecast(baseConfig, hurdleMissRun, 1),
              );
              invalid.forecastProposalAfterDeadline = rejects(
                () => campaignRepaymentForecast(extendedConfig, day57Committed, 1),
              );
              invalid.forecastTamperedState = rejects(() => {
                const candidate = clone(day1Committed);
                candidate.cash += 1;
                campaignRepaymentForecast(baseConfig, candidate);
              });
              invalid.gateBeforeDeadline = rejects(() => campaignDebtGateEvidence(
                baseConfig,
                day1Settled,
              ));
              invalid.day57Repayment = rejects(() => settleCampaignDay(
                extendedConfig,
                day57Committed,
                { manualRepayment: 1 },
              ));
              invalid.day8AfterMissedHurdle = rejects(() => commitCampaignDayResult(
                baseConfig,
                hurdleMissRun,
                dayResult(hurdleMissRun, { stageNumber: 8, income: 100 }),
              ));
              invalid.day57AfterMissedDeadline = rejects(() => commitCampaignDayResult(
                baseConfig,
                deadlineMissRun,
                dayResult(deadlineMissRun, { stageNumber: 57, income: 100 }),
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
                candidate.ledger[6].checkpoint.outcome = 'CHAPTER_HURDLE_MISSED';
                validateCampaignFinanceState(extendedConfig, candidate);
              });
              invalid.checkpointExtraField = rejects(() => {
                const candidate = clone(mixedRun);
                candidate.ledger[6].checkpoint.extra = true;
                validateCampaignFinanceState(extendedConfig, candidate);
              });
              invalid.appendAfterMissedHurdle = rejects(() => {
                const candidate = clone(hurdleMissRun);
                const copiedDay8 = clone(mixedRun.ledger[7]);
                candidate.ledger.push(copiedDay8);
                candidate.completedStageCount = 8;
                candidate.cash = copiedDay8.closingCash;
                candidate.remainingDebt = copiedDay8.closingDebt;
                candidate.cumulativeRepayment = copiedDay8.cumulativeRepayment;
                candidate.phase = 'AWAITING_RESULT';
                candidate.status = 'ACTIVE';
                candidate.nextStageNumber = 9;
                validateCampaignFinanceState(baseConfig, candidate);
              });
              invalid.retroactiveDeadlineFlag = rejects(() => {
                const candidate = clone(deadlineMissRun);
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
                deadlineMissRun,
                failedEvidence,
              ));
              invalid.unlockMissedHurdle = rejects(() => unlockCampaignFinanceTrueExtension(
                baseConfig,
                extendedConfig,
                hurdleMissRun,
                passedEvidence,
              ));
              invalid.unlockOperatingFailure = rejects(() => unlockCampaignFinanceTrueExtension(
                baseConfig,
                extendedConfig,
                shortfallRun,
                passedEvidence,
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
                forecasts: {
                  initial: initialForecast,
                  detached: forecastDetached,
                  day1WithoutProposal: day1ForecastWithoutProposal,
                  day1WithProposal: day1ForecastWithProposal,
                  metAtBoundary: metAtBoundaryForecast,
                  afterDay7: afterDay7Forecast,
                  hurdleBoundary: hurdleBoundaryForecast,
                  hurdleBoundaryMet: hurdleBoundaryMetForecast,
                  overTarget: overTargetForecast,
                  closedHurdle: closedHurdleForecast,
                  closedDeadline: closedDeadlineForecast,
                  completedBase: completedBaseForecast,
                  postDeadline: postDeadlineForecast,
                },
                immutableInputs,
                day1Committed: {
                  phase: day1Committed.phase,
                  ledgerCount: day1Committed.ledger.length,
                  cash: day1Committed.cash,
                  remainingDebt: day1Committed.remainingDebt,
                  pending: day1Committed.pendingDayResult,
                },
                day1Entry: day1Settled.ledger[0],
                operatingShortfall: {
                  state: shortfallRun,
                  forecast: shortfallForecast,
                  sourceLedgerPreserved: JSON.stringify(shortfallRun.ledger)
                    === JSON.stringify(day1Settled.ledger),
                },
                preRepaymentAtSeven,
                day7Checkpoint,
                day14Checkpoint,
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
                hurdleMissState: {
                  completedStageCount: hurdleMissRun.completedStageCount,
                  status: hurdleMissRun.status,
                  phase: hurdleMissRun.phase,
                  nextStageNumber: hurdleMissRun.nextStageNumber,
                  remainingDebt: hurdleMissRun.remainingDebt,
                  checkpoint: hurdleMissCheckpoint,
                  valid: validateCampaignFinanceState(baseConfig, hurdleMissRun),
                },
                deadlineMissState: {
                  completedStageCount: deadlineMissRun.completedStageCount,
                  status: deadlineMissRun.status,
                  phase: deadlineMissRun.phase,
                  nextStageNumber: deadlineMissRun.nextStageNumber,
                  remainingDebt: deadlineMissRun.remainingDebt,
                  valid: validateCampaignFinanceState(baseConfig, deadlineMissRun),
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
                  financeSchemaVersion: CAMPAIGN_FINANCE_SCHEMA_VERSION,
                  operationKinds: CAMPAIGN_FINANCE_OPERATION_KINDS,
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
        assert contracts["initial"]["schemaVersion"] == 3, contracts["initial"]
        assert contracts["initial"]["balanceVerdict"] == "NOT_EVALUATED"
        forecasts = contracts["forecasts"]
        forecast_keys = {
            "nextCheckpointStage",
            "targetCumulativeRepayment",
            "projectedCumulativeRepayment",
            "remainingAmount",
            "remainingRepaymentOpportunities",
            "requiredAverageRepayment",
        }
        assert set(forecasts["initial"]) == forecast_keys, forecasts["initial"]
        assert forecasts["initial"] == {
            "nextCheckpointStage": 7,
            "targetCumulativeRepayment": 10,
            "projectedCumulativeRepayment": 0,
            "remainingAmount": 10,
            "remainingRepaymentOpportunities": 7,
            "requiredAverageRepayment": 2,
        }, forecasts["initial"]
        assert forecasts["detached"] is True, forecasts
        assert forecasts["day1WithoutProposal"] == forecasts["initial"], forecasts
        assert forecasts["day1WithProposal"] == {
            "nextCheckpointStage": 7,
            "targetCumulativeRepayment": 10,
            "projectedCumulativeRepayment": 4,
            "remainingAmount": 6,
            "remainingRepaymentOpportunities": 7,
            "requiredAverageRepayment": 1,
        }, forecasts["day1WithProposal"]
        assert forecasts["metAtBoundary"] == {
            "nextCheckpointStage": 7,
            "targetCumulativeRepayment": 10,
            "projectedCumulativeRepayment": 10,
            "remainingAmount": 0,
            "remainingRepaymentOpportunities": 1,
            "requiredAverageRepayment": 0,
        }, forecasts["metAtBoundary"]
        assert forecasts["afterDay7"] == {
            "nextCheckpointStage": 14,
            "targetCumulativeRepayment": 20,
            "projectedCumulativeRepayment": 10,
            "remainingAmount": 10,
            "remainingRepaymentOpportunities": 7,
            "requiredAverageRepayment": 2,
        }, forecasts["afterDay7"]
        assert forecasts["hurdleBoundary"] == {
            "nextCheckpointStage": 7,
            "targetCumulativeRepayment": 10,
            "projectedCumulativeRepayment": 9,
            "remainingAmount": 1,
            "remainingRepaymentOpportunities": 1,
            "requiredAverageRepayment": 1,
        }, forecasts["hurdleBoundary"]
        assert forecasts["hurdleBoundaryMet"]["remainingAmount"] == 0, forecasts
        assert forecasts["hurdleBoundaryMet"]["requiredAverageRepayment"] == 0, forecasts
        assert forecasts["overTarget"] == {
            "nextCheckpointStage": 14,
            "targetCumulativeRepayment": 20,
            "projectedCumulativeRepayment": 25,
            "remainingAmount": 0,
            "remainingRepaymentOpportunities": 7,
            "requiredAverageRepayment": 0,
        }, forecasts["overTarget"]
        assert forecasts["closedHurdle"] is None, forecasts
        assert forecasts["closedDeadline"] is None, forecasts
        assert forecasts["completedBase"] is None, forecasts
        assert forecasts["postDeadline"] is None, forecasts
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

        shortfall = contracts["operatingShortfall"]
        failed_state = shortfall["state"]
        assert failed_state["schemaVersion"] == 3, failed_state
        assert failed_state["phase"] == "CLOSED", failed_state
        assert failed_state["status"] == "OPERATING_CASH_SHORTFALL", failed_state
        assert failed_state["nextStageNumber"] is None, failed_state
        assert failed_state["completedStageCount"] == 1, failed_state
        assert failed_state["cash"] == 53, failed_state
        assert failed_state["remainingDebt"] == 100, failed_state
        assert failed_state["cumulativeRepayment"] == 0, failed_state
        assert len(failed_state["ledger"]) == 1, failed_state
        assert failed_state["pendingDayResult"] is None, failed_state
        assert failed_state["operatingFailure"] == {
            "type": "CAMPAIGN_OPERATING_CASH_SHORTFALL",
            "stageNumber": 2,
            "campaignOperationId": "FINANCE-OP-2",
            "campaignResultIdentity": {
                "stageNumber": 2,
                "operationKind": "NORMAL",
                "templateIndex": 1,
            },
            "openingCash": 53,
            "income": 2,
            "availableCash": 55,
            "upkeep": 30,
            "reactivation": 10,
            "roomService": 16,
            "operatingOutflow": 56,
            "shortfallAmount": 1,
        }, failed_state
        assert shortfall["forecast"] is None, shortfall
        assert shortfall["sourceLedgerPreserved"] is True, shortfall

        assert contracts["preRepaymentAtSeven"] == {
            "ledgerCount": 6,
            "cumulativeRepayment": 10,
            "remainingDebt": 90,
            "cashAfterOperations": 55,
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
            "debtDeadlineExtended": False,
        }, contracts["day7Checkpoint"]
        day14 = contracts["day14Checkpoint"]
        assert day14["outcome"] == "MET", day14
        assert day14["cumulativeRepayment"] == 20, day14
        assert day14["shortfallAmount"] == 0, day14
        assert set(day14) == {
            "type",
            "stageNumber",
            "kind",
            "targetAmount",
            "cumulativeRepayment",
            "remainingDebt",
            "shortfallAmount",
            "outcome",
            "debtDeadlineExtended",
        }, day14

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

        hurdle_miss = contracts["hurdleMissState"]
        assert hurdle_miss["completedStageCount"] == 7, hurdle_miss
        assert hurdle_miss["status"] == "CHAPTER_HURDLE_MISSED", hurdle_miss
        assert (
            hurdle_miss["phase"] == "CLOSED"
            and hurdle_miss["nextStageNumber"] is None
        ), hurdle_miss
        assert hurdle_miss["remainingDebt"] == 100, hurdle_miss
        assert hurdle_miss["valid"] is True, hurdle_miss
        assert hurdle_miss["checkpoint"] == {
            "type": "CAMPAIGN_DEBT_CHECKPOINT",
            "stageNumber": 7,
            "kind": "CUMULATIVE_MINIMUM",
            "targetAmount": 10,
            "cumulativeRepayment": 0,
            "remainingDebt": 100,
            "shortfallAmount": 10,
            "outcome": "CHAPTER_HURDLE_MISSED",
            "debtDeadlineExtended": False,
        }, hurdle_miss

        failed = contracts["deadlineMissState"]
        assert failed["completedStageCount"] == 56, failed
        assert failed["status"] == "DEBT_DEADLINE_MISSED", failed
        assert failed["phase"] == "CLOSED" and failed["nextStageNumber"] is None, failed
        assert failed["remainingDebt"] == 40, failed
        assert failed["valid"] is True, failed
        failed_evidence = contracts["failedEvidence"]
        assert failed_evidence["passed"] is False, failed_evidence
        assert failed_evidence["checkpointOutcome"] == "DEBT_DEADLINE_MISSED"
        assert failed_evidence["remainingDebtAtBoundary"] == 40
        assert failed_evidence["debtGraceAfterBoundary"] is False
        assert contracts["zeroConfig"] == {
            "passed": True,
            "outcome": "DEBT_CLEARED",
            "status": "COMPLETE",
            "remainingDebt": 0,
        }, contracts["zeroConfig"]

        assert all(contracts["conservation"].values()), contracts["conservation"]
        assert contracts["constants"] == {
            "financeSchemaVersion": 3,
            "operationKinds": ["NORMAL"],
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
            "finance_schema_version": contracts["constants"]["financeSchemaVersion"],
            "settlement_sequence": contracts["constants"]["settlementSequence"],
            "checkpoint_stages": [7, 14, 28, 42, 56],
            "forecast_initial_average": forecasts["initial"][
                "requiredAverageRepayment"
            ],
            "forecast_boundary_opportunities": forecasts["hurdleBoundary"][
                "remainingRepaymentOpportunities"
            ],
            "forecast_closed_null": all(
                forecasts[key] is None
                for key in (
                    "closedHurdle",
                    "closedDeadline",
                    "completedBase",
                    "postDeadline",
                )
            ),
            "chapter_hurdle_miss_outcome": contracts["hurdleMissState"]["status"],
            "operating_shortfall_outcome": contracts["operatingShortfall"]["state"]["status"],
            "operating_shortfall_amount": contracts["operatingShortfall"]["state"]["operatingFailure"]["shortfallAmount"],
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
