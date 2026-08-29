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
              const config = {
                id: 'FORMAL_CAMPAIGN_FINANCE_TEST',
                version: 1,
                contract_status: 'PROVISIONAL',
                total_stages: 70,
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
              const dayResult = (state, overrides = {}) => ({
                stageNumber: state.nextStageNumber,
                income: 3,
                upkeep: 1,
                reactivation: 0,
                ...overrides,
              });
              const closeDay = (source, repayment = 0, resultOverrides = {}) => {
                const committed = commitCampaignDayResult(
                  config,
                  source,
                  dayResult(source, resultOverrides),
                );
                return settleCampaignDay(config, committed, { manualRepayment: repayment });
              };
              const advanceTo = (source, target, repayments = {}) => {
                let state = source;
                while (state.completedStageCount < target) {
                  const stage = state.nextStageNumber;
                  state = closeDay(state, repayments[String(stage)] ?? 0);
                }
                return state;
              };

              const initial = createCampaignFinanceState(config);
              const initialSnapshot = JSON.stringify(initial);
              const day1Input = dayResult(initial, { income: 9, upkeep: 2, reactivation: 4 });
              const day1InputSnapshot = JSON.stringify(day1Input);
              const day1Committed = commitCampaignDayResult(config, initial, day1Input);
              const day1CommittedSnapshot = JSON.stringify(day1Committed);
              const day1Settled = settleCampaignDay(
                config,
                day1Committed,
                { manualRepayment: 0 },
              );
              const immutableInputs = {
                initialUnchanged: JSON.stringify(initial) === initialSnapshot,
                dayInputUnchanged: JSON.stringify(day1Input) === day1InputSnapshot,
                committedUnchanged: JSON.stringify(day1Committed) === day1CommittedSnapshot,
              };

              const day2Settled = closeDay(day1Settled);
              const detachedCopy = clone(day2Settled);
              detachedCopy.ledger[0].income = 999;
              immutableInputs.oldLedgerDetached = day1Settled.ledger[0].income === 9;

              let mixedRun = advanceTo(day2Settled, 6);
              const day7Committed = commitCampaignDayResult(
                config,
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
                config,
                day7Committed,
                { manualRepayment: 10 },
              );
              const day7Checkpoint = clone(mixedRun.ledger.at(-1).checkpoint);

              mixedRun = advanceTo(mixedRun, 14);
              const day14Checkpoint = clone(mixedRun.ledger.at(-1).checkpoint);
              mixedRun = advanceTo(mixedRun, 56, {
                '28': 30,
                '42': 20,
                '56': 40,
              });
              const day56Entry = clone(mixedRun.ledger[55]);
              const passedEvidence = campaignDebtGateEvidence(config, mixedRun);
              const day57Committed = commitCampaignDayResult(
                config,
                mixedRun,
                dayResult(mixedRun, { income: 5, upkeep: 2, reactivation: 1 }),
              );
              const postDebtBeforeSettlement = clone(day57Committed.pendingDayResult);
              mixedRun = settleCampaignDay(
                config,
                day57Committed,
                { manualRepayment: 0 },
              );
              const day57Entry = clone(mixedRun.ledger[56]);
              mixedRun = advanceTo(mixedRun, 70);

              let failedRun = createCampaignFinanceState(config);
              failedRun = advanceTo(failedRun, 56);
              const failedEvidence = campaignDebtGateEvidence(config, failedRun);

              const zeroConfig = {
                ...clone(config),
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
                const committed = commitCampaignDayResult(zeroConfig, zeroRun, {
                  stageNumber: zeroRun.nextStageNumber,
                  income: 0,
                  upkeep: 0,
                  reactivation: 0,
                });
                zeroRun = settleCampaignDay(zeroConfig, committed, { manualRepayment: 0 });
              }
              const zeroEvidence = campaignDebtGateEvidence(zeroConfig, zeroRun);

              const invalid = {};
              const invalidConfig = (name, mutate) => {
                const candidate = clone(config);
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
              invalid.negativeIncome = rejects(() => commitCampaignDayResult(
                config,
                initial,
                dayResult(initial, { income: -1 }),
              ));
              invalid.unsafeIncome = rejects(() => commitCampaignDayResult(
                config,
                initial,
                dayResult(initial, { income: Number.MAX_SAFE_INTEGER }),
              ));
              invalid.negativeUpkeep = rejects(() => commitCampaignDayResult(
                config,
                initial,
                dayResult(initial, { upkeep: -1 }),
              ));
              invalid.negativeReactivation = rejects(() => commitCampaignDayResult(
                config,
                initial,
                dayResult(initial, { reactivation: -1 }),
              ));
              invalid.operatingShortfall = rejects(() => commitCampaignDayResult(
                config,
                initial,
                dayResult(initial, { income: 0, upkeep: 51, reactivation: 0 }),
              ));
              invalid.wrongStage = rejects(() => commitCampaignDayResult(
                config,
                initial,
                dayResult(initial, { stageNumber: 2 }),
              ));
              invalid.extraResultField = rejects(() => commitCampaignDayResult(
                config,
                initial,
                { ...dayResult(initial), extra: true },
              ));
              invalid.settleBeforeCommit = rejects(() => settleCampaignDay(
                config,
                initial,
                { manualRepayment: 0 },
              ));
              invalid.commitTwice = rejects(() => commitCampaignDayResult(
                config,
                day1Committed,
                dayResult(day1Committed, { stageNumber: 1 }),
              ));
              invalid.negativeRepayment = rejects(() => settleCampaignDay(
                config,
                day1Committed,
                { manualRepayment: -1 },
              ));
              invalid.repaymentPastDebt = rejects(() => settleCampaignDay(
                config,
                day1Committed,
                { manualRepayment: 101 },
              ));
              invalid.repaymentPastCash = rejects(() => settleCampaignDay(
                config,
                day1Committed,
                { manualRepayment: day1Committed.cash + 1 },
              ));
              invalid.extraSettlementField = rejects(() => settleCampaignDay(
                config,
                day1Committed,
                { manualRepayment: 0, extra: true },
              ));
              invalid.gateBeforeDeadline = rejects(() => campaignDebtGateEvidence(
                config,
                day1Settled,
              ));
              invalid.day57Repayment = rejects(() => settleCampaignDay(
                config,
                day57Committed,
                { manualRepayment: 1 },
              ));
              invalid.day57AfterMissedDeadline = rejects(() => commitCampaignDayResult(
                config,
                failedRun,
                { stageNumber: 57, income: 100, upkeep: 0, reactivation: 0 },
              ));
              invalid.sparseLedger = rejects(() => {
                const candidate = clone(day1Settled);
                candidate.ledger = new Array(1);
                validateCampaignFinanceState(config, candidate);
              });
              invalid.tamperedCashConservation = rejects(() => {
                const candidate = clone(day1Settled);
                candidate.ledger[0].cashConservation.delta = 1;
                validateCampaignFinanceState(config, candidate);
              });
              invalid.tamperedDebtConservation = rejects(() => {
                const candidate = clone(day1Settled);
                candidate.ledger[0].closingDebt = 99;
                validateCampaignFinanceState(config, candidate);
              });
              invalid.tamperedCheckpointOrder = rejects(() => {
                const candidate = clone(mixedRun);
                candidate.ledger[6].checkpoint.outcome = 'RECOVERY_REQUIRED';
                validateCampaignFinanceState(config, candidate);
              });
              invalid.retroactiveDeadlineFlag = rejects(() => {
                const candidate = clone(failedRun);
                candidate.debtClearedAtDeadline = true;
                candidate.status = 'ACTIVE';
                candidate.phase = 'AWAITING_RESULT';
                candidate.nextStageNumber = 57;
                validateCampaignFinanceState(config, candidate);
              });

              return {
                configValid: validateCampaignFinanceConfig(config),
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
                day56Entry,
                passedEvidence,
                postDebtBeforeSettlement,
                day57Entry,
                finalState: {
                  completedStageCount: mixedRun.completedStageCount,
                  status: mixedRun.status,
                  phase: mixedRun.phase,
                  nextStageNumber: mixedRun.nextStageNumber,
                  remainingDebt: mixedRun.remainingDebt,
                  ledgerCount: mixedRun.ledger.length,
                  valid: validateCampaignFinanceState(config, mixedRun),
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
        assert contracts["initial"]["balanceVerdict"] == "NOT_EVALUATED"
        assert all(contracts["immutableInputs"].values()), contracts["immutableInputs"]

        committed = contracts["day1Committed"]
        assert committed["phase"] == "RESULT_COMMITTED", committed
        assert committed["ledgerCount"] == 0, committed
        assert committed["cash"] == 53, committed
        assert committed["remainingDebt"] == 100, committed
        assert committed["pending"]["cashAfterOperations"] == 53, committed
        day1 = contracts["day1Entry"]
        assert day1["settlementSequence"] == (
            "RESULT_COMMIT_THEN_OPTIONAL_REPAYMENT_THEN_CHECKPOINT"
        )
        assert day1["income"] == 9 and day1["upkeep"] == 2
        assert day1["reactivation"] == 4 and day1["manualRepayment"] == 0
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

        assert contracts["postDebtBeforeSettlement"]["stageNumber"] == 57
        assert contracts["postDebtBeforeSettlement"]["openingDebt"] == 0
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
