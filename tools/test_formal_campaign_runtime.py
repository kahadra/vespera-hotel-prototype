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

        script = r"""
        (async () => {
          const [
            dataModule,
            stateModule,
            saveModule,
            progressModule,
            runModule,
            renderModule,
            inputModule,
          ] = await Promise.all([
            import('./src/data.js'),
            import('./src/state.js'),
            import('./src/save.js'),
            import('./src/campaign-progress.js'),
            import('./src/run.js'),
            import('./src/render.js'),
            import('./src/input.js'),
          ]);
          const { loadGameData, createIndexes } = dataModule;
          const { GameController } = stateModule;
          const {
            ACTIVE_RUN_STORAGE_KEY,
            ACTIVE_RUN_STORAGE_PREFIX,
            RUN_SAVE_SCHEMA_VERSION,
            activeRunStorageKey,
            createRunSave,
            readActiveRunSave,
          } = saveModule;
          const { FORMAL_CAMPAIGN_PROGRESS_CONFIG } = progressModule;
          const { RUN_RECORD_STORAGE_KEY, readRunRecords } = runModule;
          const { renderApp } = renderModule;
          const { setupInput } = inputModule;
          const seed = __SEED__;

          const clone = value => JSON.parse(JSON.stringify(value));
          const same = (left, right) => JSON.stringify(left) === JSON.stringify(right);
          const assert = (condition, message) => {
            if (!condition) throw new Error(`Formal runtime test: ${message}`);
          };
          const throws = callback => {
            try {
              callback();
              return false;
            } catch {
              return true;
            }
          };
          const memoryStorage = (initial = {}) => {
            const values = new Map(
              Object.entries(initial).map(([key, value]) => [String(key), String(value)]),
            );
            return {
              get length() { return values.size; },
              key: index => [...values.keys()][index] ?? null,
              getItem: key => values.has(String(key)) ? values.get(String(key)) : null,
              setItem: (key, value) => values.set(String(key), String(value)),
              removeItem: key => values.delete(String(key)),
              clear: () => values.clear(),
              keys: () => [...values.keys()],
              entries: () => Object.fromEntries(values),
            };
          };

          // This deterministic fixture validates authority and conservation only.
          // PROVISIONAL / NOT_EVALUATED deliberately prevents it from becoming
          // evidence that the production economy is balanced.
          const campaignData = await loadGameData({ mode: 'campaign' });
          const formalData = clone(campaignData);
          formalData.prototype_mode = {
            ...formalData.prototype_mode,
            type: 'FORMAL_CAMPAIGN',
            total_nights: 56,
          };
          formalData.campaign = {
            ...formalData.campaign,
            formal_progress: clone(FORMAL_CAMPAIGN_PROGRESS_CONFIG),
          };
          const financeShared = {
            version: 1,
            contract_status: 'PROVISIONAL',
            debt_deadline_stage: 56,
            debt_gate_id: FORMAL_CAMPAIGN_PROGRESS_CONFIG.true_entry_gate_id,
            starting_cash: 10,
            principal: 200,
            chapter_cumulative_targets: {
              7: 28,
              14: 50,
              28: 100,
              42: 150,
              56: 200,
            },
          };
          formalData.campaign.formal_finance = {
            base_year: {
              ...clone(financeShared),
              id: 'FORMAL_CAMPAIGN_FINANCE_RUNTIME_TEST_BASE',
              total_stages: 56,
            },
            true_extension: {
              ...clone(financeShared),
              id: 'FORMAL_CAMPAIGN_FINANCE_RUNTIME_TEST_TRUE',
              total_stages: 70,
            },
            runtime_policy: {
              id: 'FORMAL_CAMPAIGN_FINANCE_RUNTIME_POLICY_TEST',
              version: 1,
              status: 'PROVISIONAL',
              balance_verdict: 'NOT_EVALUATED',
              base_daily_upkeep: 2,
              upkeep_per_owned_upgrade: 1,
            },
          };
          formalData.run_completion = clone(formalData.run_completion);
          formalData.run_completion.record_namespace =
            'vespera.campaign.formal.runtime-test.v2';
          for (const ending of formalData.run_completion.ending_rules) {
            for (const condition of ending.conditions ?? []) {
              if (condition.metric !== 'completed_nights') continue;
              if (ending.ending_tier === 'BAD') condition.value = 1;
              else if (['TRUE', 'TRUE_HAREM'].includes(ending.ending_tier)) {
                condition.value = 70;
              } else condition.value = 56;
            }
          }
          formalData.indexes = createIndexes(formalData);

          assert(RUN_SAVE_SCHEMA_VERSION === 7, 'formal saves must use schema 7');
          assert(formalData.scenarios.length === 5, 'fixture must retain five templates');
          assert(
            formalData.campaign.formal_progress.scenario_template_count
              === formalData.scenarios.length,
            'formal progress template count must match the fixture',
          );
          assert(formalData.campaign.formal_finance.runtime_policy.status === 'PROVISIONAL',
            'fixture finance must remain PROVISIONAL');
          assert(
            formalData.campaign.formal_finance.runtime_policy.balance_verdict
              === 'NOT_EVALUATED',
            'fixture finance must remain NOT_EVALUATED',
          );
          assert(typeof progressModule.queueCampaignRecovery === 'undefined',
            'recovery progress API must be absent');

          const authorityDrifts = {
            chapterBoundary: (() => {
              const drift = clone(formalData);
              for (const schedule of [
                drift.campaign.chapters.base_year,
                drift.campaign.chapters.true_extension,
              ]) {
                schedule.chapters[0].end_stage = 6;
                schedule.chapters[1].start_stage = 7;
              }
              drift.indexes = createIndexes(drift);
              return throws(() => new GameController(
                drift,
                { seed: seed + 10, storage: memoryStorage() },
              ));
            })(),
            settlementKind: (() => {
              const drift = clone(formalData);
              for (const schedule of [
                drift.campaign.chapters.base_year,
                drift.campaign.chapters.true_extension,
              ]) {
                schedule.chapters[0].debt_settlement.kind = 'FINAL_CLEARANCE';
              }
              drift.indexes = createIndexes(drift);
              return throws(() => new GameController(
                drift,
                { seed: seed + 11, storage: memoryStorage() },
              ));
            })(),
            hiddenEntryGate: (() => {
              const drift = clone(formalData);
              drift.campaign.chapters.true_extension.chapters[5].entry_gate_id =
                'WRONG_TRUE_ENTRY_GATE';
              drift.indexes = createIndexes(drift);
              return throws(() => new GameController(
                drift,
                { seed: seed + 12, storage: memoryStorage() },
              ));
            })(),
          };
          assert(Object.values(authorityDrifts).every(Boolean),
            `chapter-finance authority drift must be rejected: ${JSON.stringify(authorityDrifts)}`);

          const formalKey = activeRunStorageKey(formalData);
          const preservedKeys = {
            [ACTIVE_RUN_STORAGE_KEY]: 'legacy-active-run-sentinel',
            [`${ACTIVE_RUN_STORAGE_PREFIX}.campaign`]: 'campaign-active-run-sentinel',
            [`${ACTIVE_RUN_STORAGE_PREFIX}.showcase`]: 'showcase-active-run-sentinel',
            [`${ACTIVE_RUN_STORAGE_PREFIX}.endless`]: 'endless-active-run-sentinel',
          };
          const storage = memoryStorage(preservedKeys);

          const syntheticResult = (stageNumber, income = 6, overrides = {}) => ({
            valid: true,
            placementScore: 0,
            reputationDelta: 0,
            baseFees: income,
            tips: 0,
            income,
            grade: 'FORMAL_RUNTIME_TEST',
            acceptedGuestIds: [],
            rejectedGuestIds: [],
            canceledGuestIds: [],
            placements: {},
            guestScores: {},
            guestReviews: [],
            emergencyReport: null,
            testStageNumber: stageNumber,
            ...clone(overrides),
          });

          const boot = (data, runSeed, runStorage = memoryStorage()) => {
            const controller = new GameController(data, { seed: runSeed, storage: runStorage });
            assert(controller.start() === true, 'start must enter formal new game');
            assert(controller.state.phase === 'NEW_GAME', 'formal start must use campaign setup');
            assert(controller.confirmNewGame() === true, 'formal prologue must open');
            assert(controller.continueStory() === true, 'formal prologue must continue');
            if (controller.state.phase === 'RELIC_OFFER') {
              assert(controller.skipDisplayRelicOffer() === true,
                'formal relic offer must be skippable');
            }
            assert(controller.state.phase === 'DAY_OPENING', 'formal day 1 must open');
            assert(controller.state.gold === 10, 'formal run must begin with 10 cash');
            assert(controller.state.campaignFinance.remainingDebt === 200,
              'formal run must begin with principal 200');
            assert(controller.state.campaignProgress.currentStageNumber === 1,
              'formal progress must own stage 1');
            assert(typeof controller.queueFormalCampaignRecovery === 'undefined',
              'controller recovery API must be absent');
            return controller;
          };

          const playToReview = (controller, expectedStage, income = 6, overrides = {}) => {
            assert(controller.state.phase === 'DAY_OPENING',
              `stage ${expectedStage} must start at DAY_OPENING`);
            assert(controller.state.campaignProgress.currentStageNumber === expectedStage,
              `stage authority drift before ${expectedStage}`);
            assert(controller.startDayBusiness() === true,
              `stage ${expectedStage} must begin business`);
            controller.completeNight(syntheticResult(expectedStage, income, overrides));
            assert(controller.state.phase === 'RESULT',
              `stage ${expectedStage} must reach RESULT`);
            assert(controller.openResultReview() === true,
              `stage ${expectedStage} must reach RESULT_REVIEW`);
            const result = controller.state.nightResults.at(-1);
            assert(result.testStageNumber === expectedStage,
              `stage ${expectedStage} result must append at the tail`);
            assert(typeof result.campaignOperationId === 'string',
              `stage ${expectedStage} must carry campaignOperationId`);
            assert(result.campaignResultIdentity?.stageNumber === expectedStage,
              `stage ${expectedStage} must carry its append identity`);
            assert(result.campaignResultIdentity?.operationKind === 'NORMAL',
              `stage ${expectedStage} must remain a NORMAL operation`);
            assert(!('campaignRecoveryBoundaryStageNumber' in result),
              `stage ${expectedStage} must not carry recovery metadata`);
            return clone(result);
          };

          const acceptReview = (controller, amount = 0) => {
            assert(controller.state.phase === 'RESULT_REVIEW',
              'repayment selection requires RESULT_REVIEW');
            const before = {
              gold: controller.state.gold,
              cash: controller.state.campaignFinance.cash,
              remainingDebt: controller.state.campaignFinance.remainingDebt,
              cumulativeRepayment: controller.state.campaignFinance.cumulativeRepayment,
              ledgerLength: controller.state.campaignFinance.ledger.length,
            };
            assert(controller.setFormalCampaignRepayment(amount) === true,
              `repayment ${amount} must be selectable`);
            assert(controller.state.campaignSelectedRepayment === amount,
              'selected repayment must remain explicit until acceptance');
            assert(controller.state.gold === before.gold
              && controller.state.campaignFinance.cash === before.cash
              && controller.state.campaignFinance.remainingDebt === before.remainingDebt
              && controller.state.campaignFinance.cumulativeRepayment
                === before.cumulativeRepayment
              && controller.state.campaignFinance.ledger.length === before.ledgerLength,
            'selecting repayment must not mutate cash, debt, or ledger');
            assert(controller.acceptSecretaryReport() === true,
              'secretary report must be accepted');
            const entry = controller.state.campaignFinance.ledger.at(-1);
            assert(entry.manualRepayment === amount,
              `settled ledger must record repayment ${amount}`);
            assert(controller.state.campaignSelectedRepayment === 0,
              'accepted repayment selection must reset');
            assert(controller.state.gold === controller.state.campaignFinance.cash,
              'settlement must synchronize live gold and finance cash');
            return clone(entry);
          };

          const openNextDay = controller => {
            if (controller.state.phase === 'STORY') {
              assert(controller.continueStory() === true, 'scheduled story must continue');
            }
            assert(controller.state.phase === 'UPGRADE',
              `next transition must enter UPGRADE, got ${controller.state.phase}`);
            assert(controller.finishUpgrade() === true, 'upgrade phase must finish');
            assert(controller.state.phase === 'DAY_OPENING', 'next day must open');
          };

          const paymentFor = (stage, finalPayment = 50) => ({
            7: 28,
            14: 22,
            28: 50,
            42: 50,
            56: finalPayment,
          })[stage] ?? 0;

          const playSettled = (controller, stage, amount = 0, expectFinal = false) => {
            playToReview(controller, stage);
            const entry = acceptReview(controller, amount);
            if (expectFinal) {
              assert(controller.state.phase === 'FINAL',
                `stage ${stage} must close the run`);
            } else openNextDay(controller);
            return entry;
          };

          // Base run: RESULT_REVIEW save/resume, retry prefix, corrupted saves,
          // then the exact 56-day ledger and repayment schedule.
          let base = boot(formalData, seed, storage);
          const openingForecast = base.formalCampaignRepaymentForecast();
          assert(same(openingForecast, {
            nextCheckpointStage: 7,
            targetCumulativeRepayment: 28,
            projectedCumulativeRepayment: 0,
            remainingAmount: 28,
            remainingRepaymentOpportunities: 7,
            requiredAverageRepayment: 4,
          }), `day 1 opening forecast drifted: ${JSON.stringify(openingForecast)}`);
          playToReview(base, 1);
          const dayOneCash = base.state.campaignFinance.cash;
          const dayOneDebt = base.state.campaignFinance.remainingDebt;
          assert(base.setFormalCampaignRepayment(28) === false,
            'day 1 must reject repayment above its 14G available cash');
          assert(base.setFormalCampaignRepayment(14) === true,
            'day 1 must accept its maximum available repayment');
          const selectedForecast = base.formalCampaignRepaymentForecast();
          assert(same(selectedForecast, {
            nextCheckpointStage: 7,
            targetCumulativeRepayment: 28,
            projectedCumulativeRepayment: 14,
            remainingAmount: 14,
            remainingRepaymentOpportunities: 7,
            requiredAverageRepayment: 2,
          }), `selected day 1 forecast drifted: ${JSON.stringify(selectedForecast)}`);
          assert(base.state.campaignFinance.cash === dayOneCash
            && base.state.campaignFinance.remainingDebt === dayOneDebt,
          'forecast selection must not mutate cash or debt before acceptance');
          assert(base.setFormalCampaignRepayment(0) === true,
            'day 1 fixture repayment must reset to zero before settlement');
          acceptReview(base, 0);
          openNextDay(base);
          for (let stage = 2; stage <= 5; stage += 1) playSettled(base, stage);

          const prefixBeforeSix = clone(base.state.nightResults);
          const financePrefixBeforeSix = clone(base.state.campaignFinance.ledger);
          const sixBeforeSave = playToReview(base, 6);
          assert(base.setFormalCampaignRepayment(1) === true,
            'stage 6 selected repayment must be savable');
          const selectedOperatingForecast = base.formalCampaignOperatingForecast();
          assert(selectedOperatingForecast.cashOnHand
              === base.state.gold - base.state.campaignSelectedRepayment
            && selectedOperatingForecast.minimumIncomeRequired === Math.max(
              0,
              selectedOperatingForecast.nextUpkeep - selectedOperatingForecast.cashOnHand,
            ),
          'RESULT_REVIEW operating forecast must project the selected repayment');
          const forecastApp = document.createElement('div');
          const rerenderForecast = () => renderApp(forecastApp, base);
          setupInput(forecastApp, base, rerenderForecast);
          rerenderForecast();
          const repaymentInput = forecastApp.querySelector('[data-formal-repayment-input]');
          const forecastPanel = forecastApp.querySelector('[data-formal-operating-forecast]');
          const acceptButtonBeforeChange = forecastApp.querySelector(
            '[data-action="accept-secretary-report"]',
          );
          assert(repaymentInput?.value === '1'
            && forecastPanel?.textContent.includes(`${selectedOperatingForecast.nextUpkeep}G`)
            && forecastPanel?.textContent.includes(`${selectedOperatingForecast.cashOnHand}G`),
          'RESULT_REVIEW must render repayment input and operating forecast');
          repaymentInput.value = '2';
          repaymentInput.dispatchEvent(new Event('change', { bubbles: true }));
          assert(base.state.campaignSelectedRepayment === 2
            && forecastApp.querySelector('[data-formal-repayment-input]')?.value === '2'
            && forecastApp.querySelector('[data-action="accept-secretary-report"]')
              === acceptButtonBeforeChange
            && forecastApp.querySelector('[data-formal-operating-forecast]')
              ?.textContent.includes(`${base.state.gold - 2}G`),
          'repayment input must update its forecast without replacing the pending click target');
          assert(base.setFormalCampaignRepayment(1) === true,
            'stage 6 selected repayment must reset after the input regression');
          const preSaveCash = base.state.campaignFinance.cash;
          const preSaveDebt = base.state.campaignFinance.remainingDebt;
          assert(base.saveCheckpoint(), 'RESULT_REVIEW save must succeed');
          const cleanStageSixSave = JSON.parse(storage.getItem(formalKey));
          assert(cleanStageSixSave.schema_version === 7, 'formal save must use schema 7');
          assert(cleanStageSixSave.state.campaignSelectedRepayment === 1,
            'RESULT_REVIEW save must include selected repayment');
          assert(cleanStageSixSave.state.campaignFinance.ledger.length === 5,
            'stage 6 review save must retain five settled ledger entries');
          assert(cleanStageSixSave.state.campaignFinance.pendingDayResult.stageNumber === 6,
            'stage 6 review save must retain its pending finance result');

          base = new GameController(formalData, { seed: seed + 99, storage });
          assert(base.hasCheckpoint() === true, 'formal save must be discoverable');
          assert(base.resumeRun() === true, 'formal save must resume');
          assert(base.state.phase === 'RESULT_REVIEW', 'resume must restore RESULT_REVIEW');
          assert(base.state.campaignSelectedRepayment === 1,
            'resume must restore the selected repayment');
          assert(base.state.campaignFinance.cash === preSaveCash
            && base.state.campaignFinance.remainingDebt === preSaveDebt,
          'resume must not prematurely apply the selected repayment');
          assert(base.retryCurrentStage() === true, 'stage 6 retry must restore checkpoint');
          assert(base.state.phase === 'DAY_OPENING', 'retry must return to day opening');
          assert(base.state.nightResults.length === 5, 'retry must truncate result 6');
          assert(base.state.campaignFinance.ledger.length === 5,
            'retry must restore the five-entry finance prefix');
          assert(base.state.campaignFinance.pendingDayResult === null,
            'retry must discard the pending day result');
          assert(base.state.campaignSelectedRepayment === 0,
            'retry must discard the unobserved repayment selection');
          assert(same(base.state.nightResults, prefixBeforeSix),
            'retry must preserve the result prefix exactly');
          assert(same(base.state.campaignFinance.ledger, financePrefixBeforeSix),
            'retry must preserve the finance prefix exactly');
          const sixAfterRetry = playToReview(base, 6);
          assert(sixAfterRetry.campaignOperationId === sixBeforeSave.campaignOperationId,
            'replayed stage 6 must retain its deterministic operation ID');
          assert(base.state.nightResults.filter(
            result => result.campaignOperationId === sixAfterRetry.campaignOperationId,
          ).length === 1, 'replayed stage 6 must not duplicate its operation ID');
          acceptReview(base, 0);
          openNextDay(base);

          playSettled(base, 7, 28);
          playSettled(base, 8, 0);
          const nine = playToReview(base, 9);
          assert(base.saveCheckpoint(), 'stage 9 review save must succeed');
          const cleanStageNineSave = JSON.parse(storage.getItem(formalKey));

          const corruptedSaveRejected = mutate => {
            const candidate = clone(cleanStageNineSave);
            mutate(candidate);
            const isolated = memoryStorage({ [formalKey]: JSON.stringify(candidate) });
            return readActiveRunSave(formalData, isolated) === null;
          };
          const corruptions = {
            legacySchemaVersion: corruptedSaveRejected(save => {
              save.schema_version = 5;
            }),
            wrongStageAuthority: corruptedSaveRejected(save => {
              save.stage_authority_id = 'WRONG_STAGE_AUTHORITY';
            }),
            wrongFinanceAuthority: corruptedSaveRejected(save => {
              save.finance_authority_id = 'WRONG_FINANCE_AUTHORITY';
            }),
            wrongProgressConfigId: corruptedSaveRejected(save => {
              save.state.campaignProgress.configId = 'WRONG_PROGRESS_CONFIG';
            }),
            wrongFinanceConfigId: corruptedSaveRejected(save => {
              save.state.campaignFinance.configId = 'WRONG_FINANCE_CONFIG';
            }),
            wrongResultOperationId: corruptedSaveRejected(save => {
              save.state.nightResults[0].campaignOperationId = 'WRONG_OPERATION_ID';
            }),
            resultFinanceIncomeMismatch: corruptedSaveRejected(save => {
              save.state.nightResults[0].income += 1;
              save.stage_checkpoint.nightResults[0].income += 1;
            }),
            wrongPendingFinanceIdentity: corruptedSaveRejected(save => {
              save.state.campaignFinance.pendingDayResult.campaignOperationId =
                'WRONG_PENDING_ID';
            }),
            wrongLedgerFinanceIdentity: corruptedSaveRejected(save => {
              save.state.campaignFinance.ledger[0].campaignResultIdentity.templateIndex += 1;
            }),
            financeLedgerGap: corruptedSaveRejected(save => {
              save.state.campaignFinance.ledger.splice(4, 1);
            }),
            resultRecordGap: corruptedSaveRejected(save => {
              save.state.campaignProgress.operationRecords.splice(4, 1);
            }),
            sparseNightResults: corruptedSaveRejected(save => {
              save.state.nightResults = new Array(
                save.state.campaignProgress.completedStageCount,
              );
            }),
            sparseOperationRecords: corruptedSaveRejected(save => {
              save.state.campaignProgress.operationRecords = new Array(
                save.state.campaignProgress.completedStageCount,
              );
            }),
            sparseFinanceLedger: corruptedSaveRejected(save => {
              save.state.campaignFinance.ledger = new Array(
                save.state.campaignFinance.completedStageCount,
              );
            }),
            wrongLiveGold: corruptedSaveRejected(save => {
              save.state.gold += 1;
            }),
            pendingExpenseDuringReview: corruptedSaveRejected(save => {
              save.state.campaignPendingExpenses.reactivation = 1;
            }),
            invalidSelectedRepayment: corruptedSaveRejected(save => {
              save.state.campaignSelectedRepayment = save.state.campaignFinance.cash + 1;
            }),
            negativeForesightRetryCount: corruptedSaveRejected(save => {
              save.state.foresightRetryCount = -1;
            }),
            stringForesightRetryCount: corruptedSaveRejected(save => {
              save.state.foresightRetryCount = '1';
            }),
            malformedForesightDiscoveryIds: corruptedSaveRejected(save => {
              save.state.foresightDiscoveryIds = ['VALID_ID', null];
            }),
            checkpointFinancePrefix: corruptedSaveRejected(save => {
              save.stage_checkpoint.campaignFinance.ledger[0].closingCash += 1;
            }),
            checkpointProgressPrefix: corruptedSaveRejected(save => {
              save.stage_checkpoint.campaignProgress.operationRecords[0]
                .resultIdentity.templateIndex += 1;
            }),
            checkpointUpgradeInjection: corruptedSaveRejected(save => {
              save.stage_checkpoint.ownedUpgradeIds.push('SOUNDPROOFING');
            }),
          };
          assert(Object.values(corruptions).every(Boolean),
            `all corrupted formal saves must be rejected: ${JSON.stringify(corruptions)}`);

          assert(nine.campaignResultIdentity.operationKind === 'NORMAL',
            'post-boundary operations must remain NORMAL');
          acceptReview(base, 0);
          openNextDay(base);
          for (let stage = 10; stage <= 55; stage += 1) {
            playSettled(base, stage, paymentFor(stage));
          }
          playToReview(base, 56);
          assert(base.formalCampaignOperatingForecast() === null,
            'base day 56 review must not forecast an unconfirmed next operation');
          acceptReview(base, paymentFor(56));

          const baseIds = base.state.nightResults.map(result => result.campaignOperationId);
          const baseTemplates = base.state.nightResults.map(
            result => result.campaignResultIdentity.templateIndex,
          );
          const baseMetrics = base.state.runRecord.metrics;
          assert(base.state.phase === 'FINAL', 'base run must finish');
          assert(base.state.campaignProgress.completedStageCount === 56,
            'base progress must complete 56 stages');
          assert(base.state.campaignProgress.status === 'BASE_COMPLETE',
            'base progress must end as BASE_COMPLETE');
          assert(base.state.campaignFinance.cash === 34,
            'base ledger must close with 34 cash');
          assert(base.state.campaignFinance.remainingDebt === 0,
            'base ledger must clear all debt');
          assert(base.state.campaignFinance.ledger.length === 56,
            'base ledger must contain 56 entries');
          assert(base.state.runRecord.schema_version === 6,
            'base FINAL must use run record schema 6');
          assert(baseMetrics.campaign_completed_stages === 56
            && baseMetrics.campaign_starting_cash === 10
            && baseMetrics.campaign_original_principal === 200
            && baseMetrics.campaign_total_income === 336
            && baseMetrics.campaign_total_upkeep === 112
            && baseMetrics.campaign_total_reactivation_spend === 0
            && baseMetrics.campaign_total_room_service_spend === 0
            && baseMetrics.campaign_total_repayment === 200
            && baseMetrics.campaign_remaining_debt === 0
            && baseMetrics.campaign_day_56_debt_cleared === 1
            && baseMetrics.campaign_finance_ledger_entries === 56,
          `base run finance metrics drifted: ${JSON.stringify(baseMetrics)}`);
          assert(!('recovery_operations' in baseMetrics),
            'run metrics must not retain recovery operations');
          assert(!('pendingRecoveryBoundaryStageNumber' in base.state.campaignProgress),
            'progress state must not retain recovery state');
          assert(base.state.campaignProgress.operationRecords.every(
            record => Object.keys(record).length === 1
              && record.resultIdentity.operationKind === 'NORMAL',
          ), 'all base progress records must be NORMAL-only exact records');
          assert(new Set(baseTemplates).size === 5,
            'base run must exercise all five scenario templates');
          assert(baseTemplates.slice(0, 10).join(',') === '0,1,2,3,4,0,1,2,3,4',
            'formal template selection must cycle deterministically');
          assert(base.state.runRecord.day_56_debt_gate_evidence?.passed === true,
            'base record must preserve day 56 debt-clear evidence');

          const preservedAfterBase = Object.fromEntries(
            Object.keys(preservedKeys).map(key => [key, storage.getItem(key)]),
          );
          assert(same(preservedAfterBase, preservedKeys),
            'formal saves must not modify other mode keys');
          assert(formalKey.endsWith('.formal_campaign'),
            'formal active run must use the .formal_campaign key');
          assert(!storage.keys().some(key => key === formalKey),
            'formal active save must clear after base FINAL');

          // An upkeep shortfall is an immediate, data-driven operational ending.
          // Real preparation purchases remain part of the last DAY_OPENING
          // checkpoint, while the attempted guest operation and its relic trigger
          // are rolled back instead of becoming a partially settled day.
          const shortfallData = clone(formalData);
          shortfallData.campaign.formal_finance.runtime_policy.base_daily_upkeep = 17;
          const shortfallUpgrade = shortfallData.upgrades.find(
            upgrade => upgrade.id === 'SOUNDPROOFING',
          );
          shortfallUpgrade.cost = 5;
          shortfallUpgrade.unlock_stage = 1;
          shortfallData.indexes = createIndexes(shortfallData);
          assert(shortfallData.run_completion.ending_rules.some(
            ending => ending.id === 'BAD_MAINTENANCE_SHORTFALL'
              && ending.conditions?.some(
                condition => condition.metric === 'campaign_operating_cash_shortfall',
              ),
          ), 'operating shortfall ending must be declared by run-completion data');
          const shortfallStorage = memoryStorage();
          const shortfallSeed = seed + 550;

          // Keep the zero-completion terminal edge explicit: a campaign can
          // fail on its very first operation without appending progress,
          // results, or a finance ledger row.
          const dayOneFailureStorage = memoryStorage();
          const dayOneFailureSeed = shortfallSeed - 1;
          const dayOneFailureRun = boot(
            shortfallData,
            dayOneFailureSeed,
            dayOneFailureStorage,
          );
          assert(dayOneFailureRun.saveCheckpoint()
            && dayOneFailureStorage.getItem(formalKey) !== null,
          'day 1 failure fixture must begin from a persisted active save');
          assert(dayOneFailureRun.startDayBusiness() === true,
            'day 1 failure fixture must begin business');
          dayOneFailureRun.completeNight(syntheticResult(1, 0));
          const expectedDayOneFailure = {
            type: 'CAMPAIGN_OPERATING_CASH_SHORTFALL',
            stageNumber: 1,
            campaignOperationId:
              `FORMAL_CAMPAIGN_PROGRESS@1:${dayOneFailureSeed}:1`,
            campaignResultIdentity: {
              stageNumber: 1,
              operationKind: 'NORMAL',
              templateIndex: 0,
            },
            openingCash: 10,
            income: 0,
            availableCash: 10,
            upkeep: 17,
            reactivation: 0,
            roomService: 0,
            operatingOutflow: 17,
            shortfallAmount: 7,
          };
          assert(dayOneFailureRun.state.phase === 'FINAL'
            && dayOneFailureRun.state.runRecord.ending_id
              === 'BAD_MAINTENANCE_SHORTFALL',
          'day 1 shortfall must immediately resolve the maintenance ending');
          assert(dayOneFailureRun.state.campaignProgress.completedStageCount === 0
            && dayOneFailureRun.state.campaignFinance.completedStageCount === 0
            && dayOneFailureRun.state.campaignFinance.ledger.length === 0
            && dayOneFailureRun.state.nightResults.length === 0,
          'day 1 shortfall must remain a zero-completion terminal run');
          assert(dayOneFailureRun.state.gold === 10
            && dayOneFailureRun.state.campaignFinance.cash === 10
            && dayOneFailureRun.state.campaignFinance.remainingDebt === 200,
          'day 1 shortfall must preserve opening cash and debt without a ledger row');
          assert(same(
            dayOneFailureRun.state.runRecord.operating_failure_evidence,
            expectedDayOneFailure,
          ), 'day 1 failure evidence drifted');
          assert(dayOneFailureRun.state.runRecord.metrics.completed_nights === 0
            && dayOneFailureRun.state.runRecord.metrics.campaign_completed_stages === 0
            && dayOneFailureRun.state.runRecord.metrics.campaign_finance_ledger_entries === 0,
          'day 1 failure record must preserve zero completed operations');
          assert(dayOneFailureStorage.getItem(formalKey) === null
            && dayOneFailureRun.hasCheckpoint() === false,
          'day 1 terminal failure must clear its active save and checkpoint');
          const storedDayOneFailureRecords = readRunRecords(dayOneFailureStorage);
          assert(storedDayOneFailureRecords.length === 1
            && storedDayOneFailureRecords[0].schema_version === 6
            && storedDayOneFailureRecords[0].ending_id
              === 'BAD_MAINTENANCE_SHORTFALL'
            && same(
              storedDayOneFailureRecords[0].operating_failure_evidence,
              expectedDayOneFailure,
            )
            && storedDayOneFailureRecords[0].metrics.completed_nights === 0
            && storedDayOneFailureRecords[0].metrics.campaign_completed_stages === 0
            && storedDayOneFailureRecords[0].metrics.campaign_finance_ledger_entries === 0,
          'day 1 schema 6 failure record must reread exact zero-completion evidence');

          const shortfallRun = boot(shortfallData, shortfallSeed, shortfallStorage);
          const operatingForecast = shortfallRun.formalCampaignOperatingForecast();
          assert(same(operatingForecast, {
            nextUpkeep: 17,
            cashOnHand: 10,
            pendingExpense: 0,
            minimumIncomeRequired: 7,
          }), `day 1 operating forecast drifted: ${JSON.stringify(operatingForecast)}`);
          playToReview(shortfallRun, 1, 20, {
            acceptedGuestIds: ['G01_LUNE'],
            placements: { G01_LUNE: 'F1-A' },
          });
          acceptReview(shortfallRun, 0);
          assert(shortfallRun.state.phase === 'UPGRADE'
            && shortfallRun.state.gold === 13,
          'shortfall fixture must reach a funded stage 1 preparation');
          shortfallRun.state.currentUpgradeOfferIds = [shortfallUpgrade.id];
          assert(shortfallRun.buyUpgrade(shortfallUpgrade.id) === true,
            'shortfall fixture must pay a real 5G reactivation');
          assert(shortfallRun.serviceRoom('F1-A') === true,
            'shortfall fixture must pay a real 8G room service cost');
          const rollbackRelic = shortfallData.display_relics.find(
            relic => relic.effect_id === 'NO_CANCELLATION_GOLD_BONUS',
          );
          const rollbackRelicId = rollbackRelic.id;
          shortfallRun.state.ownedDisplayRelicIds.push(rollbackRelicId);
          shortfallRun.state.displayRelicTriggerCounts[rollbackRelicId] = 0;
          assert(same(shortfallRun.formalCampaignOperatingForecast(), {
            nextUpkeep: 18,
            cashOnHand: 0,
            pendingExpense: 13,
            minimumIncomeRequired: 18,
          }), 'paid preparation expenses must be visible before day 2');
          const upgradeForecastApp = document.createElement('div');
          renderApp(upgradeForecastApp, shortfallRun);
          assert(upgradeForecastApp.querySelector('[data-formal-operating-forecast]')
            ?.textContent.includes('최소 필요 수입18G'),
          'UPGRADE must render the operating forecast before day 2');
          assert(shortfallRun.finishUpgrade() === true,
            'shortfall fixture must open day 2 after paid preparation');
          const openingForecastApp = document.createElement('div');
          renderApp(openingForecastApp, shortfallRun);
          assert(openingForecastApp.querySelector('[data-formal-operating-forecast]')
            ?.textContent.includes('최소 필요 수입18G'),
          'DAY_OPENING must render the same operating forecast');
          assert(shortfallRun.saveCheckpoint(),
            'day 2 opening must persist paid preparation before the failure');
          assert(shortfallStorage.getItem(formalKey) !== null,
            'operating failure fixture must begin with a persisted active save');
          const openingRollbackState = clone(shortfallRun.stageCheckpoint);
          assert(shortfallRun.startDayBusiness() === true,
            'operating failure fixture must begin day 2 business');
          const shortfallBefore = {
            gold: openingRollbackState.gold,
            financeCash: openingRollbackState.campaignFinance.cash,
            remainingDebt: openingRollbackState.campaignFinance.remainingDebt,
            cumulativeRepayment: openingRollbackState.campaignFinance.cumulativeRepayment,
            ledger: clone(openingRollbackState.campaignFinance.ledger),
            progress: clone(openingRollbackState.campaignProgress),
            nightResults: clone(openingRollbackState.nightResults),
            hotelReputation: openingRollbackState.hotelReputation,
            guestHistory: clone(openingRollbackState.guestHistory),
            expectationReputationByGuest: clone(
              openingRollbackState.expectationReputationByGuest,
            ),
            stayovers: clone(openingRollbackState.stayovers),
            roomConditions: clone(openingRollbackState.roomConditions),
            lastRoomWear: clone(openingRollbackState.lastRoomWear),
            pendingExpenses: clone(openingRollbackState.campaignPendingExpenses),
            ownedUpgradeIds: clone(openingRollbackState.ownedUpgradeIds),
            displayRelicTriggerCounts: clone(openingRollbackState.displayRelicTriggerCounts),
          };
          shortfallRun.completeNight(syntheticResult(2, 6, {
            reputationDelta: 99,
            acceptedGuestIds: ['G01_LUNE'],
            placements: { G01_LUNE: 'F1-A' },
          }));
          const expectedOperatingFailure = {
            type: 'CAMPAIGN_OPERATING_CASH_SHORTFALL',
            stageNumber: 2,
            campaignOperationId:
              `FORMAL_CAMPAIGN_PROGRESS@1:${shortfallSeed}:2`,
            campaignResultIdentity: {
              stageNumber: 2,
              operationKind: 'NORMAL',
              templateIndex: 1,
            },
            openingCash: 13,
            income: 9,
            availableCash: 22,
            upkeep: 18,
            reactivation: 5,
            roomService: 8,
            operatingOutflow: 31,
            shortfallAmount: 9,
          };
          const shortfallFinance = shortfallRun.state.campaignFinance;
          const shortfallRecord = shortfallRun.state.runRecord;
          const shortfallMetrics = shortfallRecord.metrics;
          assert(shortfallRun.state.phase === 'FINAL',
            'day 2 operating shortfall must immediately enter FINAL');
          assert(shortfallRecord.ending_id === 'BAD_MAINTENANCE_SHORTFALL',
            'operating shortfall must resolve its data-driven bad ending');
          assert(shortfallRecord.schema_version === 6,
            'operating shortfall run record must use schema 6');
          assert(shortfallFinance.schemaVersion === 3
            && shortfallFinance.phase === 'CLOSED'
            && shortfallFinance.status === 'OPERATING_CASH_SHORTFALL'
            && shortfallFinance.nextStageNumber === null
            && shortfallFinance.pendingDayResult === null,
          'operating shortfall must close finance under schema 3');
          assert(same(shortfallFinance.operatingFailure, expectedOperatingFailure),
            `operating failure evidence drifted: ${JSON.stringify(shortfallFinance.operatingFailure)}`);
          assert(same(shortfallRecord.operating_failure_evidence, expectedOperatingFailure),
            'run record must preserve exact operating failure evidence');
          assert(shortfallRun.state.gold === shortfallBefore.gold
            && shortfallFinance.cash === shortfallBefore.financeCash
            && shortfallFinance.remainingDebt === shortfallBefore.remainingDebt
            && shortfallFinance.cumulativeRepayment === shortfallBefore.cumulativeRepayment
            && same(shortfallFinance.ledger, shortfallBefore.ledger)
            && shortfallFinance.completedStageCount === 1,
          'failed operation must not apply attempted income, upkeep, debt, or a ledger row');
          const rollbackChecks = {
            progress: same(shortfallRun.state.campaignProgress, shortfallBefore.progress),
            nightResults: same(shortfallRun.state.nightResults, shortfallBefore.nightResults),
            reputation:
              shortfallRun.state.hotelReputation === shortfallBefore.hotelReputation,
            guestHistory: same(shortfallRun.state.guestHistory, shortfallBefore.guestHistory),
            expectation: same(
              shortfallRun.state.expectationReputationByGuest,
              shortfallBefore.expectationReputationByGuest,
            ),
            stayovers: same(shortfallRun.state.stayovers, shortfallBefore.stayovers),
            roomConditions: same(
              shortfallRun.state.roomConditions,
              shortfallBefore.roomConditions,
            ),
            lastRoomWear: same(shortfallRun.state.lastRoomWear, shortfallBefore.lastRoomWear),
            pendingExpenses: same(
              shortfallRun.state.campaignPendingExpenses,
              shortfallBefore.pendingExpenses,
            ),
            ownedUpgradeIds: same(
              shortfallRun.state.ownedUpgradeIds,
              shortfallBefore.ownedUpgradeIds,
            ),
            displayRelicTriggerCounts: same(
              shortfallRun.state.displayRelicTriggerCounts,
              shortfallBefore.displayRelicTriggerCounts,
            ),
          };
          assert(Object.values(rollbackChecks).every(Boolean),
            `failed day rollback drifted: ${JSON.stringify(rollbackChecks)}`);
          assert(shortfallMetrics.completed_nights === 1
            && shortfallMetrics.total_income === 20
            && shortfallMetrics.reputation_delta === 0
            && shortfallMetrics.campaign_completed_stages === 1
            && shortfallMetrics.campaign_finance_ledger_entries === 1
            && shortfallMetrics.campaign_total_income === 20
            && shortfallMetrics.campaign_total_upkeep === 17
            && shortfallMetrics.campaign_total_reactivation_spend === 5
            && shortfallMetrics.campaign_total_room_service_spend === 8
            && shortfallMetrics.campaign_remaining_debt === 200
            && shortfallMetrics.campaign_operating_cash_shortfall === 1
            && shortfallMetrics.campaign_operating_failure_stage === 2
            && shortfallMetrics.campaign_operating_failure_income === 9
            && shortfallMetrics.campaign_operating_failure_available_cash === 22
            && shortfallMetrics.campaign_operating_failure_upkeep === 18
            && shortfallMetrics.campaign_operating_failure_reactivation === 5
            && shortfallMetrics.campaign_operating_failure_room_service === 8
            && shortfallMetrics.campaign_operating_failure_outflow === 31
            && shortfallMetrics.campaign_operating_failure_shortfall === 9,
          `operating failure metrics drifted: ${JSON.stringify(shortfallMetrics)}`);
          assert(shortfallMetrics.campaign_starting_cash
              + shortfallMetrics.campaign_total_income
              - shortfallMetrics.campaign_total_upkeep
              - shortfallMetrics.campaign_total_reactivation_spend
              - shortfallMetrics.campaign_total_room_service_spend
              - shortfallMetrics.campaign_total_repayment
              === shortfallMetrics.final_gold,
          'operating failure metrics must conserve actual cash including paid preparation');
          assert(shortfallRun.formalCampaignOperatingForecast() === null,
            'operating forecast must close with campaign finance');
          assert(shortfallStorage.getItem(formalKey) === null
            && shortfallRun.hasCheckpoint() === false,
          'operating failure FINAL must clear its active save and checkpoint');
          assert(!(shortfallRun.profile.display_relics?.triggered_ids ?? [])
            .includes(rollbackRelicId),
          'rolled-back result relic trigger must not enter the profile');

          const storedShortfallRecords = readRunRecords(shortfallStorage);
          assert(storedShortfallRecords.length === 1
            && storedShortfallRecords[0].schema_version === 6
            && same(
              storedShortfallRecords[0].operating_failure_evidence,
              expectedOperatingFailure,
            ),
          'stored run schema 6 must reread exact operating failure evidence');

          const legacyV5 = clone(base.state.runRecord);
          legacyV5.schema_version = 5;
          delete legacyV5.operating_failure_evidence;
          const migratedV5 = readRunRecords(memoryStorage({
            [RUN_RECORD_STORAGE_KEY]: JSON.stringify([legacyV5]),
          }));
          assert(migratedV5.length === 1
            && migratedV5[0].schema_version === 6
            && migratedV5[0].operating_failure_evidence === null
            && migratedV5[0].record_id === legacyV5.record_id
            && migratedV5[0].ending_id === legacyV5.ending_id
            && same(migratedV5[0].metrics, legacyV5.metrics),
          'run schema 5 records must remain readable through schema 6 migration');

          // Every intermediate chapter target is a hard boundary. Reach each
          // boundary after meeting all prior targets, then miss by exactly one.
          const hurdleRuns = {};
          const expectedDebtAfterMiss = { 7: 173, 14: 151, 28: 101, 42: 51 };
          for (const boundary of [7, 14, 28, 42]) {
            const run = boot(formalData, seed + 200 + boundary, memoryStorage());
            for (let stage = 1; stage <= boundary; stage += 1) {
              const amount = stage === boundary
                ? paymentFor(stage) - 1
                : paymentFor(stage);
              playSettled(run, stage, amount, stage === boundary);
            }
            assert(run.state.phase === 'FINAL'
              && run.state.nightResults.length === boundary
              && run.state.chapterHurdleFailures === 1,
            `day ${boundary} shortfall must immediately end the run`);
            assert(run.state.campaignFinance.phase === 'CLOSED'
              && run.state.campaignFinance.status === 'CHAPTER_HURDLE_MISSED'
              && run.state.campaignFinance.remainingDebt
                === expectedDebtAfterMiss[boundary],
            `day ${boundary} shortfall must close finance as CHAPTER_HURDLE_MISSED`);
            assert(run.state.runRecord.ending_id === 'BAD_CHAPTER_HURDLE',
              `day ${boundary} shortfall must resolve the chapter-hurdle bad ending`);
            assert(run.startDayBusiness() === false,
              `day ${boundary + 1} cannot open after a hurdle failure`);
            hurdleRuns[boundary] = run;
          }
          const hurdle = hurdleRuns[7];

          // Meeting intermediate targets but leaving one debt at day 56 also closes.
          const deadline = boot(formalData, seed + 300, memoryStorage());
          for (let stage = 1; stage <= 56; stage += 1) {
            playSettled(deadline, stage, paymentFor(stage, 49), stage === 56);
          }
          assert(deadline.state.phase === 'FINAL'
            && deadline.state.campaignFinance.status === 'DEBT_DEADLINE_MISSED'
            && deadline.state.campaignFinance.remainingDebt === 1,
          'day 56 debt remainder must close as DEBT_DEADLINE_MISSED');
          assert(deadline.state.chapterHurdleFailures === 1,
            'day 56 debt miss must count as one hurdle failure');
          assert(deadline.state.campaignProgress.trueExtensionUnlocked === false
            && deadline.state.runRecord.campaign_stage_limit === 56,
          'day 56 debt miss must not unlock the extension');
          assert(deadline.state.runRecord.day_56_debt_gate_evidence?.passed === false,
            'day 56 debt miss must preserve failed gate evidence');

          // True run: same 56-day prefix, internally derived gate, boundary saves,
          // then 14 debt-free extension days.
          const trueStorage = memoryStorage();
          let trueRun = boot(formalData, seed, trueStorage);
          for (let stage = 1; stage <= 55; stage += 1) {
            playSettled(trueRun, stage, paymentFor(stage));
          }
          playToReview(trueRun, 56);
          trueRun.state.truthEvidenceCount =
            formalData.campaign.ending_thresholds.truth_evidence;
          trueRun.state.peaceAllianceComplete = true;
          const progressBeforeExternalUnlock = clone(trueRun.state.campaignProgress);
          assert(trueRun.unlockFormalCampaignTrueExtension({
            gateId: FORMAL_CAMPAIGN_PROGRESS_CONFIG.true_entry_gate_id,
            passed: true,
            boundaryStageNumber: 56,
          }) === false, 'external true-extension injection must be disabled');
          assert(same(trueRun.state.campaignProgress, progressBeforeExternalUnlock),
            'disabled external unlock must not mutate progress');
          assert(trueRun.setFormalCampaignRepayment(50) === true,
            'day 56 final repayment must be selectable');
          assert(trueRun.state.campaignFinance.remainingDebt === 50,
            'day 56 selection must not clear debt before acceptance');
          assert(trueRun.saveCheckpoint(), 'day 56 RESULT_REVIEW save must succeed');
          const trueBoundarySave = JSON.parse(trueStorage.getItem(formalKey));
          assert(trueBoundarySave.schema_version === 7
            && trueBoundarySave.state.campaignSelectedRepayment === 50
            && trueBoundarySave.state.campaignFinance.ledger.length === 55,
          'day 56 boundary save must preserve the pending settlement');

          trueRun = new GameController(formalData, { seed: seed + 1000, storage: trueStorage });
          assert(trueRun.resumeRun() === true,
            'day 56 RESULT_REVIEW save must resume');
          assert(trueRun.state.phase === 'RESULT_REVIEW'
            && trueRun.state.campaignSelectedRepayment === 50
            && trueRun.state.campaignFinance.remainingDebt === 50,
          'day 56 resume must restore the uncommitted repayment');
          acceptReview(trueRun, 50);
          assert(trueRun.state.phase === 'UPGRADE',
            'derived true gate must continue to the upgrade phase');
          assert(trueRun.state.campaignProgress.trueExtensionUnlocked === true
            && trueRun.state.campaignProgress.stageLimit === 70
            && trueRun.state.campaignProgress.currentStageNumber === 57,
          'derived true gate must expose stage 57');
          assert(trueRun.state.campaignFinance.configId
            === formalData.campaign.formal_finance.true_extension.id,
          'derived true gate must switch to the extended finance authority');
          assert(trueRun.formalCampaignOperatingForecast() !== null,
            'unlocked stage 57 preparation must resume the operating forecast');
          assert(createRunSave(formalData, trueRun.state, trueRun.stageCheckpoint) !== null,
            'unlocked UPGRADE boundary must remain savable');
          assert(trueRun.saveCheckpoint(), 'unlocked UPGRADE save must write');
          trueRun = new GameController(
            formalData,
            { seed: seed + 1001, storage: trueStorage },
          );
          assert(trueRun.resumeRun() === true,
            'unlocked UPGRADE boundary must resume');
          assert(trueRun.state.phase === 'UPGRADE'
            && trueRun.state.campaignProgress.currentStageNumber === 57,
          'unlocked boundary resume must retain stage 57 authority');
          assert(trueRun.finishUpgrade() === true
            && trueRun.state.phase === 'DAY_OPENING'
            && trueRun.state.campaignProgress.currentStageNumber === 57,
          'day 57 must open after the boundary resume');

          playToReview(trueRun, 57);
          assert(trueRun.setFormalCampaignRepayment(1) === false,
            'nonzero repayment must be rejected after day 56');
          acceptReview(trueRun, 0);
          openNextDay(trueRun);
          for (let stage = 58; stage <= 69; stage += 1) {
            playSettled(trueRun, stage, 0);
          }
          playToReview(trueRun, 70);
          assert(trueRun.formalCampaignOperatingForecast() === null,
            'true day 70 review must not forecast a nonexistent next operation');
          acceptReview(trueRun, 0);
          const trueIds = trueRun.state.nightResults.map(
            result => result.campaignOperationId,
          );
          const trueMetrics = trueRun.state.runRecord.metrics;
          assert(trueRun.state.phase === 'FINAL'
            && trueRun.state.campaignProgress.status === 'TRUE_COMPLETE'
            && trueRun.state.nightResults.length === 70,
          'true run must finish all 70 days');
          assert(same(trueIds.slice(0, 56), baseIds),
            'true run must preserve the same-seed base operation ID prefix');
          assert(trueRun.state.campaignFinance.cash === 90
            && trueRun.state.campaignFinance.remainingDebt === 0
            && trueRun.state.campaignFinance.ledger.length === 70,
          'true ledger must close at cash 90, debt 0, and 70 entries');
          assert(trueRun.state.runRecord.schema_version === 6,
            'true FINAL must use run record schema 6');
          assert(trueMetrics.campaign_completed_stages === 70
            && trueMetrics.campaign_starting_cash === 10
            && trueMetrics.campaign_original_principal === 200
            && trueMetrics.campaign_total_income === 420
            && trueMetrics.campaign_total_upkeep === 140
            && trueMetrics.campaign_total_reactivation_spend === 0
            && trueMetrics.campaign_total_room_service_spend === 0
            && trueMetrics.campaign_total_repayment === 200
            && trueMetrics.campaign_remaining_debt === 0
            && trueMetrics.campaign_day_56_debt_cleared === 1
            && trueMetrics.campaign_finance_ledger_entries === 70,
          `true run finance metrics drifted: ${JSON.stringify(trueMetrics)}`);
          assert(!('recovery_operations' in trueMetrics),
            'true metrics must not retain recovery operations');

          // Upgrade reactivation and room service are paid live, then attributed
          // to the following formal ledger entry with one extra upkeep unit.
          const expenseData = clone(formalData);
          const expenseUpgrade = expenseData.upgrades.find(
            upgrade => upgrade.id === 'SOUNDPROOFING',
          );
          expenseUpgrade.cost = 5;
          expenseUpgrade.unlock_stage = 1;
          expenseData.indexes = createIndexes(expenseData);
          const expenseStorage = memoryStorage();
          let expenseRun = boot(expenseData, seed + 400, expenseStorage);
          playToReview(expenseRun, 1, 6, {
            acceptedGuestIds: ['G01_LUNE'],
            placements: { G01_LUNE: 'F1-A' },
          });
          assert(same(
            expenseRun.state.roomConditions['F1-A'],
            { cleanliness: 92 },
          ), 'stage 1 guest stay must produce real cleanliness 92 room wear');
          acceptReview(expenseRun, 0);
          assert(expenseRun.state.phase === 'UPGRADE',
            'expense fixture must reach stage 1 upgrade');
          expenseRun.state.currentUpgradeOfferIds = [expenseUpgrade.id];
          assert(expenseRun.buyUpgrade(expenseUpgrade.id) === true,
            '5G upgrade must be purchasable');
          assert(expenseRun.serviceRoom('F1-A') === true,
            '8G room service must be purchasable');
          assert(same(
            expenseRun.state.roomConditions['F1-A'],
            { cleanliness: 100 },
          ), 'room service must restore actual guest cleanliness wear');
          assert(expenseRun.state.gold === 1
            && expenseRun.state.campaignFinance.cash === 14
            && expenseRun.state.campaignPendingExpenses.reactivation === 5
            && expenseRun.state.campaignPendingExpenses.roomService === 8,
          'live expenses must conserve finance cash before the next result');
          assert(expenseRun.saveCheckpoint(),
            'UPGRADE save with paid reactivation and service expenses must succeed');
          const cleanExpenseSave = JSON.parse(expenseStorage.getItem(formalKey));
          const freeUpgradeSave = clone(cleanExpenseSave);
          freeUpgradeSave.state.ownedUpgradeIds.push('BLACKOUT_CURTAINS');
          freeUpgradeSave.state.renovationPurchaseIds.push('BLACKOUT_CURTAINS');
          assert(readActiveRunSave(
            expenseData,
            memoryStorage({ [formalKey]: JSON.stringify(freeUpgradeSave) }),
          ) === null, 'UPGRADE save must reject an unpaid inventory suffix');
          const freeServiceSave = clone(cleanExpenseSave);
          freeServiceSave.state.gold +=
            freeServiceSave.state.campaignPendingExpenses.roomService;
          freeServiceSave.state.campaignPendingExpenses.roomService = 0;
          assert(readActiveRunSave(
            expenseData,
            memoryStorage({ [formalKey]: JSON.stringify(freeServiceSave) }),
          ) === null, 'UPGRADE save must reject refunded room service with retained repair');
          const invalidRoomConditionSave = clone(cleanExpenseSave);
          invalidRoomConditionSave.state.roomConditions['F1-A'].cleanliness = 101;
          assert(readActiveRunSave(
            expenseData,
            memoryStorage({ [formalKey]: JSON.stringify(invalidRoomConditionSave) }),
          ) === null, 'UPGRADE save must reject out-of-range room condition');
          const extraRoomSave = clone(cleanExpenseSave);
          extraRoomSave.state.roomConditions['NOT_A_ROOM'] = {
            cleanliness: 100,
          };
          assert(readActiveRunSave(
            expenseData,
            memoryStorage({ [formalKey]: JSON.stringify(extraRoomSave) }),
          ) === null, 'UPGRADE save must reject an unknown room condition key');
          expenseRun = new GameController(
            expenseData,
            { seed: seed + 401, storage: expenseStorage },
          );
          assert(expenseRun.resumeRun() === true
            && expenseRun.state.phase === 'UPGRADE'
            && same(expenseRun.state.ownedUpgradeIds, [expenseUpgrade.id])
            && same(expenseRun.state.renovationPurchaseIds, [expenseUpgrade.id])
            && expenseRun.state.campaignPendingExpenses.reactivation === 5
            && expenseRun.state.campaignPendingExpenses.roomService === 8
            && expenseRun.state.gold === 1,
          'UPGRADE resume must preserve exactly the paid inventory and expenses');
          assert(expenseRun.finishUpgrade() === true, 'expense run must open stage 2');
          playToReview(expenseRun, 2);
          const expenseEntry = acceptReview(expenseRun, 0);
          assert(expenseEntry.reactivation === 5
            && expenseEntry.roomService === 8
            && expenseEntry.upkeep === 3,
          `stage 2 ledger must attribute expenses and upkeep: ${JSON.stringify(expenseEntry)}`);
          assert(expenseRun.state.campaignPendingExpenses.reactivation === 0
            && expenseRun.state.campaignPendingExpenses.roomService === 0,
          'committed expenses must clear their live accumulator');

          // A campaign relic choice can occur after progress has begun. Its
          // pending offer must survive a formal save without being mistaken for
          // the prelude relic offer.
          const relicStorage = memoryStorage();
          let relicRun = boot(formalData, seed + 450, relicStorage);
          playToReview(relicRun, 1);
          acceptReview(relicRun, 0);
          assert(relicRun.state.phase === 'UPGRADE'
            && relicRun.state.campaignProgress.completedStageCount === 1,
          'mid-campaign relic fixture must begin from settled day 1 UPGRADE');
          assert(relicRun.prepareDisplayRelicOffer(
            { id: 'FORMAL_MID_CAMPAIGN_RELIC_TEST', pool_ids: ['COMMON'], offer_size: 1 },
            { action: 'OPEN_UPGRADE' },
          ) === true, 'mid-campaign relic offer must open');
          const pendingMidRelic = clone(relicRun.state.pendingDisplayRelicOffer);
          assert(relicRun.state.phase === 'RELIC_OFFER'
            && pendingMidRelic?.relicIds.length === 1,
          'mid-campaign RELIC_OFFER must retain one candidate');
          assert(relicRun.saveCheckpoint(),
            'completed-stage RELIC_OFFER save must succeed');
          relicRun = new GameController(
            formalData,
            { seed: seed + 451, storage: relicStorage },
          );
          assert(relicRun.resumeRun() === true
            && relicRun.state.phase === 'RELIC_OFFER'
            && relicRun.state.campaignProgress.completedStageCount === 1
            && same(relicRun.state.pendingDisplayRelicOffer, pendingMidRelic),
          'completed-stage RELIC_OFFER resume must preserve its pending offer');
          assert(relicRun.skipDisplayRelicOffer() === true
            && relicRun.state.phase === 'UPGRADE',
          'resumed mid-campaign relic offer must return to UPGRADE');

          // Invalid income must roll back every formal state mutation atomically.
          const atomicRun = boot(formalData, seed + 500, memoryStorage());
          assert(atomicRun.startDayBusiness() === true,
            'atomic fixture must begin stage 1 business');
          const atomicStateBefore = clone(atomicRun.state);
          const atomicCheckpointBefore = clone(atomicRun.stageCheckpoint);
          assert(throws(() => atomicRun.completeNight(syntheticResult(1, -1))),
            'negative income must be rejected');
          assert(same(atomicRun.state, atomicStateBefore)
            && same(atomicRun.stageCheckpoint, atomicCheckpointBefore),
          'rejected completeNight must roll back state and checkpoint atomically');

          return {
            dataMode: formalData.prototype_mode.type,
            formalKey,
            preservedKeys: preservedAfterBase,
            base: {
              phase: base.state.phase,
              completed: base.state.campaignProgress.completedStageCount,
              status: base.state.campaignProgress.status,
              cash: base.state.campaignFinance.cash,
              debt: base.state.campaignFinance.remainingDebt,
              ledger: base.state.campaignFinance.ledger.length,
              runSchema: base.state.runRecord.schema_version,
              templateCycle: baseTemplates.slice(0, 10),
              operationIdPrefix: baseIds.slice(0, 3),
            },
            retry: {
              beforeSaveId: sixBeforeSave.campaignOperationId,
              afterRetryId: sixAfterRetry.campaignOperationId,
              prefixLength: prefixBeforeSix.length,
            },
            forecast: {
              opening: openingForecast,
              selected: selectedForecast,
              rejectedOverCash: true,
            },
            operatingShortfall: {
              phase: shortfallRun.state.phase,
              ending: shortfallRecord.ending_id,
              financeSchema: shortfallFinance.schemaVersion,
              financeStatus: shortfallFinance.status,
              completed: shortfallRun.state.campaignProgress.completedStageCount,
              cash: shortfallFinance.cash,
              liveCash: shortfallRun.state.gold,
              debt: shortfallFinance.remainingDebt,
              ledger: shortfallFinance.ledger.length,
              pendingExpense: clone(shortfallRun.state.campaignPendingExpenses),
              preparationPersisted: same(
                shortfallRun.state.ownedUpgradeIds,
                openingRollbackState.ownedUpgradeIds,
              ) && same(
                shortfallRun.state.roomConditions,
                openingRollbackState.roomConditions,
              ),
              failure: clone(shortfallFinance.operatingFailure),
              forecast: operatingForecast,
              forecastAfterClosure: shortfallRun.formalCampaignOperatingForecast(),
              activeSaveCleared: shortfallStorage.getItem(formalKey) === null,
              runSchema: shortfallRecord.schema_version,
            },
            hurdle: {
              phase: hurdle.state.phase,
              status: hurdle.state.campaignFinance.status,
              completed: hurdle.state.nightResults.length,
              debt: hurdle.state.campaignFinance.remainingDebt,
              verifiedBoundaries: Object.keys(hurdleRuns).map(Number),
            },
            deadline: {
              phase: deadline.state.phase,
              status: deadline.state.campaignFinance.status,
              debt: deadline.state.campaignFinance.remainingDebt,
              extension: deadline.state.campaignProgress.trueExtensionUnlocked,
            },
            trueRun: {
              phase: trueRun.state.phase,
              completed: trueRun.state.campaignProgress.completedStageCount,
              status: trueRun.state.campaignProgress.status,
              cash: trueRun.state.campaignFinance.cash,
              debt: trueRun.state.campaignFinance.remainingDebt,
              ledger: trueRun.state.campaignFinance.ledger.length,
              prefixPreserved: same(trueIds.slice(0, 56), baseIds),
            },
            expense: {
              reactivation: expenseEntry.reactivation,
              roomService: expenseEntry.roomService,
              upkeep: expenseEntry.upkeep,
              freeUpgradeRejected: true,
              freeServiceRejected: true,
              realWear: { cleanliness: 92 },
            },
            corruptions,
            authorityDrifts,
            midRelic: {
              completed: relicRun.state.campaignProgress.completedStageCount,
              candidateCount: pendingMidRelic.relicIds.length,
              resumedToUpgrade: relicRun.state.phase === 'UPGRADE',
            },
            atomicRollback: same(atomicRun.state, atomicStateBefore),
          };
        })()
        """.replace("__SEED__", str(seed))
        contracts = client.evaluate(script)

        assert contracts["dataMode"] == "FORMAL_CAMPAIGN", contracts
        assert contracts["formalKey"].endswith(".formal_campaign"), contracts
        assert contracts["base"] == {
            "phase": "FINAL",
            "completed": 56,
            "status": "BASE_COMPLETE",
            "cash": 34,
            "debt": 0,
            "ledger": 56,
            "runSchema": 6,
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
        assert contracts["forecast"] == {
            "opening": {
                "nextCheckpointStage": 7,
                "targetCumulativeRepayment": 28,
                "projectedCumulativeRepayment": 0,
                "remainingAmount": 28,
                "remainingRepaymentOpportunities": 7,
                "requiredAverageRepayment": 4,
            },
            "selected": {
                "nextCheckpointStage": 7,
                "targetCumulativeRepayment": 28,
                "projectedCumulativeRepayment": 14,
                "remainingAmount": 14,
                "remainingRepaymentOpportunities": 7,
                "requiredAverageRepayment": 2,
            },
            "rejectedOverCash": True,
        }, contracts["forecast"]
        assert contracts["operatingShortfall"] == {
            "phase": "FINAL",
            "ending": "BAD_MAINTENANCE_SHORTFALL",
            "financeSchema": 3,
            "financeStatus": "OPERATING_CASH_SHORTFALL",
            "completed": 1,
            "cash": 13,
            "liveCash": 0,
            "debt": 200,
            "ledger": 1,
            "pendingExpense": {
                "reactivation": 5,
                "roomService": 8,
            },
            "preparationPersisted": True,
            "failure": {
                "type": "CAMPAIGN_OPERATING_CASH_SHORTFALL",
                "stageNumber": 2,
                "campaignOperationId": (
                    f"FORMAL_CAMPAIGN_PROGRESS@1:{seed + 550}:2"
                ),
                "campaignResultIdentity": {
                    "stageNumber": 2,
                    "operationKind": "NORMAL",
                    "templateIndex": 1,
                },
                "openingCash": 13,
                "income": 9,
                "availableCash": 22,
                "upkeep": 18,
                "reactivation": 5,
                "roomService": 8,
                "operatingOutflow": 31,
                "shortfallAmount": 9,
            },
            "forecast": {
                "nextUpkeep": 17,
                "cashOnHand": 10,
                "pendingExpense": 0,
                "minimumIncomeRequired": 7,
            },
            "forecastAfterClosure": None,
            "activeSaveCleared": True,
            "runSchema": 6,
        }, contracts["operatingShortfall"]
        assert contracts["hurdle"] == {
            "phase": "FINAL",
            "status": "CHAPTER_HURDLE_MISSED",
            "completed": 7,
            "debt": 173,
            "verifiedBoundaries": [7, 14, 28, 42],
        }, contracts["hurdle"]
        assert contracts["deadline"] == {
            "phase": "FINAL",
            "status": "DEBT_DEADLINE_MISSED",
            "debt": 1,
            "extension": False,
        }, contracts["deadline"]
        assert contracts["trueRun"] == {
            "phase": "FINAL",
            "completed": 70,
            "status": "TRUE_COMPLETE",
            "cash": 90,
            "debt": 0,
            "ledger": 70,
            "prefixPreserved": True,
        }, contracts["trueRun"]
        assert contracts["expense"] == {
            "reactivation": 5,
            "roomService": 8,
            "upkeep": 3,
            "freeUpgradeRejected": True,
            "freeServiceRejected": True,
            "realWear": {"cleanliness": 92},
        }, contracts["expense"]
        assert all(contracts["corruptions"].values()), contracts["corruptions"]
        assert all(contracts["authorityDrifts"].values()), contracts["authorityDrifts"]
        assert contracts["midRelic"] == {
            "completed": 1,
            "candidateCount": 1,
            "resumedToUpgrade": True,
        }, contracts["midRelic"]
        assert contracts["atomicRollback"] is True, contracts

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
            "base_cash": contracts["base"]["cash"],
            "true_completed": contracts["trueRun"]["completed"],
            "true_cash": contracts["trueRun"]["cash"],
            "retry_operation_id": contracts["retry"]["afterRetryId"],
            "day_one_forecast": contracts["forecast"],
            "operating_shortfall": contracts["operatingShortfall"],
            "chapter_hurdle_status": contracts["hurdle"]["status"],
            "chapter_hurdles_verified": contracts["hurdle"]["verifiedBoundaries"],
            "debt_deadline_status": contracts["deadline"]["status"],
            "expense_ledger": contracts["expense"],
            "template_cycle": contracts["base"]["templateCycle"][:5],
            "save_key": contracts["formalKey"],
            "corrupted_saves_rejected": len(contracts["corruptions"]),
            "authority_drifts_rejected": len(contracts["authorityDrifts"]),
            "mid_campaign_relic_resume": contracts["midRelic"]["resumedToUpgrade"],
            "true_prefix_preserved": contracts["trueRun"]["prefixPreserved"],
            "fixture_balance_verdict": "NOT_EVALUATED",
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
