import { endlessAuditTarget, endlessRiskTier } from "./endless.js";
import {
  campaignOperationDescriptor,
  campaignOperationId,
  campaignResultIdentity,
  validateCampaignProgressConfig,
  validateCampaignProgressState,
} from "./campaign-progress.js";
import {
  campaignPlanOperationIdentity,
  resolveCampaignOperation,
  validateCampaignOperationPlanProgressAlignment,
} from "./campaign-operation-plan.js";
import {
  CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE,
  validateCampaignFinanceConfig,
  validateCampaignFinanceState,
} from "./campaign-finance.js";
import { displayRelicEffectValue } from "./relics.js";
import { createBoardState } from "./rules.js";

export const RUN_SAVE_SCHEMA_VERSION = 8;
export const PROFILE_SCHEMA_VERSION = 1;
export const ACTIVE_RUN_STORAGE_KEY = "vespera.hotel.active-run.v1";
export const ACTIVE_RUN_STORAGE_PREFIX = "vespera.hotel.active-run.v2";
export const PROFILE_STORAGE_KEY = "vespera.hotel.profile.v1";

const SAVABLE_PHASES = new Set([
  "TUTORIAL",
  "STORY",
  "RELIC_OFFER",
  "ENDLESS_BRIEFING",
  "ENDLESS_AUDIT",
  "DAY_OPENING",
  "RESERVATION",
  "PLACEMENT",
  "RESULT",
  "RESULT_REVIEW",
  "UPGRADE",
]);

const FORMAL_PRE_OPERATION_PHASES = new Set([
  "DAY_OPENING",
  "RESERVATION",
  "PLACEMENT",
]);

const FORMAL_POST_OPERATION_PHASES = new Set([
  "RESULT",
  "RESULT_REVIEW",
  "UPGRADE",
]);

const FORMAL_FINANCE_PENDING_PHASES = new Set([
  "RESULT",
  "RESULT_REVIEW",
]);

const FORMAL_FINANCE_SETTLED_POST_PHASES = new Set([
  "STORY",
  "UPGRADE",
]);

const FORMAL_CHECKPOINT_PHASES = new Set([
  "DAY_OPENING",
  "RESERVATION",
  "PLACEMENT",
]);

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function uniqueStrings(values) {
  return [...new Set((values ?? []).filter((value) => typeof value === "string" && value.length > 0))];
}

function finiteOrNull(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function sameJson(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function exactKeys(value, expectedKeys) {
  if (!isPlainObject(value)) return false;
  const actual = Object.keys(value).sort();
  const expected = [...expectedKeys].sort();
  return actual.length === expected.length
    && actual.every((key, index) => key === expected[index]);
}

function nonNegativeSafeInteger(value) {
  return Number.isSafeInteger(value) && value >= 0;
}

function positiveSafeInteger(value) {
  return Number.isSafeInteger(value) && value > 0;
}

function isDenseArray(value) {
  if (!Array.isArray(value)) return false;
  for (let index = 0; index < value.length; index += 1) {
    if (!Object.prototype.hasOwnProperty.call(value, index)) return false;
  }
  return true;
}

function denseUniqueStrings(value) {
  return isDenseArray(value)
    && value.every((item) => typeof item === "string" && item.length > 0)
    && new Set(value).size === value.length;
}

function validLastRoomWear(data, lastRoomWear) {
  return isDenseArray(lastRoomWear)
    && lastRoomWear.every((entry) => exactKeys(
      entry,
      ["guestId", "roomId", "cleanlinessLoss", "cleanliness"],
    )
      && Boolean(data.indexes.guests[entry.guestId])
      && Boolean(data.indexes.rooms[entry.roomId])
      && Number.isFinite(entry.cleanlinessLoss)
      && entry.cleanlinessLoss >= 0
      && Number.isFinite(entry.cleanliness)
      && entry.cleanliness >= 0
      && entry.cleanliness <= 100);
}

function validStayoverCleaningState(data, state) {
  const request = state.pendingStayoverCleaningRequest;
  const declinedRoomIds = state.declinedStayoverCleaningRoomIds;
  const resolvedGuestIds = state.stayoverCleaningRequestGuestIds;
  const requestConfig = data.balance?.stayover_cleaning_request;
  const baseServiceCost = data.balance?.room_service_cost ?? 8;
  const serviceReduction = displayRelicEffectValue(
    data,
    state.ownedDisplayRelicIds ?? [],
    "ROOM_SERVICE_COST_REDUCTION",
  );
  const expectedServiceCost = Math.max(0, baseServiceCost - serviceReduction);
  const stayoverRoomIds = new Set(
    Object.values(state.stayovers ?? {}).map((entry) => entry?.roomId),
  );
  if (typeof state.stayoverCleaningRequestChecked !== "boolean"
    || !denseUniqueStrings(declinedRoomIds)
    || !declinedRoomIds.every((roomId) => Boolean(data.indexes.rooms[roomId]))
    || !declinedRoomIds.every((roomId) => stayoverRoomIds.has(roomId))
    || !denseUniqueStrings(resolvedGuestIds)
    || !resolvedGuestIds.every((guestId) => Boolean(data.indexes.guests[guestId]))
    || !resolvedGuestIds.every((guestId) => Boolean(state.stayovers?.[guestId]))) {
    return false;
  }
  if (request === null) return true;
  if (!exactKeys(request, [
    "requestId",
    "guestId",
    "roomId",
    "cleanliness",
    "serviceCost",
    "acceptReputation",
    "rejectReputation",
  ])
    || typeof request.requestId !== "string"
    || request.requestId.length === 0
    || !data.indexes.guests[request.guestId]
    || !data.indexes.rooms[request.roomId]
    || !Number.isFinite(request.cleanliness)
    || request.cleanliness < 0
    || request.cleanliness >= 100
    || !nonNegativeSafeInteger(request.serviceCost)
    || request.serviceCost !== expectedServiceCost
    || !Number.isSafeInteger(request.acceptReputation)
    || request.acceptReputation < 0
    || request.acceptReputation !== Number(requestConfig?.accept_reputation)
    || !Number.isSafeInteger(request.rejectReputation)
    || request.rejectReputation > 0
    || request.rejectReputation !== Number(requestConfig?.reject_reputation)
    || state.stayoverCleaningRequestChecked !== true
    || declinedRoomIds.includes(request.roomId)
    || resolvedGuestIds.includes(request.guestId)
    || state.roomConditions?.[request.roomId]?.cleanliness !== request.cleanliness
    || state.stayovers?.[request.guestId]?.roomId !== request.roomId) {
    return false;
  }
  return true;
}

function isFormalCampaign(data) {
  return data?.prototype_mode?.type === "FORMAL_CAMPAIGN";
}

function formalCampaignProgressConfig(data) {
  if (!isFormalCampaign(data)) return null;
  const config = data?.campaign?.formal_progress;
  try {
    validateCampaignProgressConfig(config);
  } catch {
    return null;
  }
  if (config.scenario_template_count !== data?.scenarios?.length) return null;
  return config;
}

function formalCampaignOperationPlan(data) {
  if (!isFormalCampaign(data)) return null;
  const plan = data?.campaign?.operation_plan;
  const progressConfig = data?.campaign?.formal_progress;
  try {
    validateCampaignOperationPlanProgressAlignment(plan, progressConfig, data.scenarios);
  } catch {
    return null;
  }
  return plan;
}

function formalCampaignFinanceConfigs(data) {
  if (!isFormalCampaign(data)) return null;
  const authority = data?.campaign?.formal_finance;
  if (!isPlainObject(authority) || !isPlainObject(authority.runtime_policy)) return null;
  const base = authority.base_year;
  const extended = authority.true_extension;
  try {
    validateCampaignFinanceConfig(base);
    validateCampaignFinanceConfig(extended);
  } catch {
    return null;
  }

  const progressConfig = formalCampaignProgressConfig(data);
  if (!progressConfig
    || base.total_stages !== progressConfig.base_stage_limit
    || extended.total_stages !== progressConfig.true_stage_limit
    || base.debt_gate_id !== progressConfig.true_entry_gate_id
    || base.id === extended.id
    || base.version !== extended.version) return null;
  for (const key of [
    "contract_status",
    "debt_deadline_stage",
    "debt_gate_id",
    "starting_cash",
    "principal",
  ]) {
    if (base[key] !== extended[key]) return null;
  }
  if (!sameJson(base.chapter_cumulative_targets, extended.chapter_cumulative_targets)) return null;
  const runtimePolicy = authority.runtime_policy;
  if (!exactKeys(runtimePolicy, [
    "id",
    "version",
    "status",
    "balance_verdict",
    "base_daily_upkeep",
    "upkeep_per_owned_upgrade",
  ])
    || typeof runtimePolicy.id !== "string"
    || runtimePolicy.id.trim().length === 0
    || !Number.isSafeInteger(runtimePolicy.version)
    || runtimePolicy.version < 1
    || runtimePolicy.status !== "PROVISIONAL"
    || runtimePolicy.balance_verdict !== "NOT_EVALUATED"
    || !nonNegativeSafeInteger(runtimePolicy.base_daily_upkeep)
    || !nonNegativeSafeInteger(runtimePolicy.upkeep_per_owned_upgrade)) return null;
  return {
    base,
    extended,
    runtimePolicy,
  };
}

function formalCampaignFinanceConfig(data, state) {
  const configs = formalCampaignFinanceConfigs(data);
  if (!configs || !state?.campaignProgress) return null;
  return state.campaignProgress.trueExtensionUnlocked === true
    ? configs.extended
    : configs.base;
}

function descriptorFromOperationRecord(config, record) {
  return {
    type: "CAMPAIGN_OPERATION",
    stageNumber: record.resultIdentity.stageNumber,
    operationKind: record.resultIdentity.operationKind,
    templateIndex: record.resultIdentity.templateIndex,
    templatePolicyId: config.scenario_template_policy_id,
    templateProductionReady: config.scenario_templates_production_ready,
  };
}

function validFormalResult(data, config, plan, runSeed, result, operationRecord) {
  if (!result || typeof result !== "object" || Array.isArray(result)) return false;
  const descriptor = descriptorFromOperationRecord(config, operationRecord);
  let expectedOperationId;
  let expectedResultIdentity;
  let expectedPlanIdentity;
  try {
    expectedOperationId = campaignOperationId(config, runSeed, descriptor);
    expectedResultIdentity = campaignResultIdentity(config, descriptor);
    const scenarioIds = data.scenarios.map((scenario) => scenario.id);
    const planOperation = resolveCampaignOperation(
      plan,
      operationRecord.resultIdentity.stageNumber,
      scenarioIds,
    );
    expectedPlanIdentity = campaignPlanOperationIdentity(plan, planOperation, scenarioIds);
  } catch {
    return false;
  }
  return result.campaignOperationId === expectedOperationId
    && sameJson(result.campaignResultIdentity, expectedResultIdentity)
    && sameJson(result.campaignResultIdentity, operationRecord.resultIdentity)
    && sameJson(result.campaignPlanIdentity, expectedPlanIdentity)
    && operationRecord.resultIdentity.templateIndex >= 0
    && operationRecord.resultIdentity.templateIndex < config.scenario_template_count;
}

function validFinanceOperationIdentity(financeRecord, result, operationRecord) {
  return Boolean(financeRecord && result && operationRecord)
    && financeRecord.campaignOperationId === result.campaignOperationId
    && sameJson(financeRecord.campaignResultIdentity, result.campaignResultIdentity)
    && sameJson(financeRecord.campaignResultIdentity, operationRecord.resultIdentity)
    && financeRecord.income === result.income;
}

function validFormalFinanceState(data, state, progress) {
  const config = formalCampaignFinanceConfig(data, state);
  if (!config) return false;
  try {
    validateCampaignFinanceState(config, state.campaignFinance);
  } catch {
    return false;
  }

  const finance = state.campaignFinance;
  const expenses = state.campaignPendingExpenses;
  const repayment = state.campaignSelectedRepayment;
  if (!exactKeys(expenses, ["reactivation", "roomService"])
    || !nonNegativeSafeInteger(expenses.reactivation)
    || !nonNegativeSafeInteger(expenses.roomService)
    || !nonNegativeSafeInteger(repayment)
    || !nonNegativeSafeInteger(state.gold)
    || finance.status !== "ACTIVE"
    || finance.totalStages !== progress.stageLimit) return false;

  const pendingPhase = FORMAL_FINANCE_PENDING_PHASES.has(state.phase);
  const settledPhase = FORMAL_PRE_OPERATION_PHASES.has(state.phase)
    || FORMAL_FINANCE_SETTLED_POST_PHASES.has(state.phase)
    || state.phase === "TUTORIAL"
    || state.phase === "RELIC_OFFER";
  if (!pendingPhase && !settledPhase) return false;
  if (pendingPhase) {
    if (progress.completedStageCount < 1
      || finance.completedStageCount !== progress.completedStageCount - 1
      || finance.pendingDayResult === null) return false;
    const latestIndex = progress.completedStageCount - 1;
    if (!validFinanceOperationIdentity(
      finance.pendingDayResult,
      state.nightResults[latestIndex],
      progress.operationRecords[latestIndex],
    )) return false;
  } else if (finance.completedStageCount !== progress.completedStageCount
    || finance.pendingDayResult !== null) return false;

  if (!finance.ledger.every((entry, index) => validFinanceOperationIdentity(
    entry,
    state.nightResults[index],
    progress.operationRecords[index],
  ))) return false;

  if (finance.pendingDayResult === null) {
    const accountedCash = state.gold + expenses.reactivation + expenses.roomService;
    if (!Number.isSafeInteger(accountedCash) || accountedCash !== finance.cash) return false;
  } else if (expenses.reactivation !== 0
    || expenses.roomService !== 0
    || state.gold !== finance.cash) return false;

  if (repayment > 0 && state.phase !== "RESULT_REVIEW") return false;
  if (state.phase !== "RESULT_REVIEW" && repayment !== 0) return false;
  if (repayment > finance.cash || repayment > finance.remainingDebt) return false;
  if (finance.pendingDayResult?.stageNumber > CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE
    && repayment !== 0) return false;

  if (progress.trueExtensionUnlocked) {
    const deadlineEntry = finance.ledger[CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE - 1];
    if (finance.completedStageCount < CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE
      || finance.remainingDebt !== 0
      || finance.debtClearedAtDeadline !== true
      || deadlineEntry?.stageNumber !== CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE
      || deadlineEntry.closingDebt !== 0
      || deadlineEntry.checkpoint?.outcome !== "DEBT_CLEARED") return false;
  }
  return true;
}

function formalPhasePosition(state) {
  if (FORMAL_PRE_OPERATION_PHASES.has(state.phase)) return "PRE";
  if (FORMAL_POST_OPERATION_PHASES.has(state.phase)) return "POST";
  if (state.phase === "STORY") {
    return state.campaignProgress.completedStageCount === 0 ? "PRELUDE" : "POST";
  }
  if (state.phase === "RELIC_OFFER") {
    return state.campaignProgress.completedStageCount === 0 ? "PRELUDE" : "POST";
  }
  if (state.phase === "TUTORIAL") return "PRELUDE";
  return null;
}

function validFormalCampaignState(data, state) {
  const config = formalCampaignProgressConfig(data);
  const plan = formalCampaignOperationPlan(data);
  if (!config || !plan
    || !Number.isInteger(state.runSeed) || state.runSeed < 0 || state.runSeed > 0xFFFFFFFF) {
    return false;
  }
  try {
    validateCampaignProgressState(config, state.campaignProgress);
  } catch {
    return false;
  }
  const progress = state.campaignProgress;
  if (!isDenseArray(state.nightResults)) return false;
  if (state.nightResults.length !== progress.completedStageCount) return false;
  if (!progress.operationRecords.every(
    (record, index) => validFormalResult(
      data,
      config,
      plan,
      state.runSeed,
      state.nightResults[index],
      record,
    ),
  )) return false;
  if (!validFormalFinanceState(data, state, progress)) return false;

  const position = formalPhasePosition(state);
  if (!position) return false;
  if (position === "PRELUDE") {
    if (progress.completedStageCount !== 0 || progress.status !== "ACTIVE") return false;
    if (state.phase === "RELIC_OFFER" && state.pendingDisplayRelicOffer === null) return false;
  }

  let authorityDescriptor;
  let planOperation;
  try {
    authorityDescriptor = position === "POST"
      ? descriptorFromOperationRecord(config, progress.operationRecords.at(-1))
      : campaignOperationDescriptor(config, progress);
    campaignOperationId(config, state.runSeed, authorityDescriptor);
    planOperation = resolveCampaignOperation(
      plan,
      authorityDescriptor.stageNumber,
      data.scenarios.map((scenario) => scenario.id),
    );
  } catch {
    return false;
  }
  if (position === "POST" && progress.completedStageCount === 0) return false;
  if (position === "PRE" && progress.status !== "ACTIVE") return false;
  if (state.phase === "UPGRADE" && progress.status !== "ACTIVE") return false;
  const planScenarioIndex = data.scenarios.findIndex(
    (scenario) => scenario.id === planOperation.scenario_id,
  );
  return planScenarioIndex >= 0
    && data.scenarios[authorityDescriptor.templateIndex]?.id === planOperation.scenario_id
    && state.currentNightIndex === planScenarioIndex
    && state.currentNightIndex >= 0
    && state.currentNightIndex < data.scenarios.length;
}

export function activeRunStorageKey(data) {
  const modeId = String(data?.prototype_mode?.type ?? "UNKNOWN").toLowerCase();
  return `${ACTIVE_RUN_STORAGE_PREFIX}.${modeId}`;
}

export function createDefaultProfile(now = new Date().toISOString()) {
  return {
    schema_version: PROFILE_SCHEMA_VERSION,
    profile_id: "default",
    created_at: now,
    updated_at: now,
    handbook: {
      discovered_hidden_preference_ids: [],
      seen_rank_ids: ["N"],
      seen_species_ids: [],
      encountered_guest_ids: [],
    },
    unlocked_content_ids: [],
    display_relics: {
      unlocked_pool_ids: [],
      seen_ids: [],
      acquired_ids: [],
      triggered_ids: [],
    },
    endless: {
      best_survived_nights: 0,
      best_cleared_seasons: 0,
      best_audit_score: null,
      best_run_fame: 0,
    },
  };
}

function normalizeProfile(profile) {
  const fallback = createDefaultProfile(profile?.created_at);
  return {
    ...fallback,
    ...profile,
    schema_version: PROFILE_SCHEMA_VERSION,
    profile_id: typeof profile?.profile_id === "string" ? profile.profile_id : "default",
    handbook: {
      discovered_hidden_preference_ids: uniqueStrings(profile?.handbook?.discovered_hidden_preference_ids),
      seen_rank_ids: uniqueStrings(["N", ...(profile?.handbook?.seen_rank_ids ?? [])]),
      seen_species_ids: uniqueStrings(profile?.handbook?.seen_species_ids),
      encountered_guest_ids: uniqueStrings(profile?.handbook?.encountered_guest_ids),
    },
    unlocked_content_ids: uniqueStrings(profile?.unlocked_content_ids),
    display_relics: {
      unlocked_pool_ids: uniqueStrings(profile?.display_relics?.unlocked_pool_ids),
      seen_ids: uniqueStrings(profile?.display_relics?.seen_ids),
      acquired_ids: uniqueStrings(profile?.display_relics?.acquired_ids),
      triggered_ids: uniqueStrings(profile?.display_relics?.triggered_ids),
    },
    endless: {
      best_survived_nights: Math.max(0, Number(profile?.endless?.best_survived_nights ?? 0)),
      best_cleared_seasons: Math.max(0, Number(profile?.endless?.best_cleared_seasons ?? 0)),
      best_audit_score: finiteOrNull(profile?.endless?.best_audit_score),
      best_run_fame: Math.max(0, Number(profile?.endless?.best_run_fame ?? 0)),
    },
  };
}

export function readProfile(storage = globalThis.localStorage) {
  if (!storage) return createDefaultProfile();
  try {
    const parsed = JSON.parse(storage.getItem(PROFILE_STORAGE_KEY) ?? "null");
    if (parsed?.schema_version !== PROFILE_SCHEMA_VERSION) return createDefaultProfile();
    return normalizeProfile(parsed);
  } catch {
    return createDefaultProfile();
  }
}

export function writeProfile(profile, storage = globalThis.localStorage) {
  const normalized = normalizeProfile({
    ...profile,
    updated_at: new Date().toISOString(),
  });
  if (!storage) return normalized;
  try {
    storage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(normalized));
  } catch {
    // Storage can be unavailable in privacy-restricted browser contexts.
  }
  return normalized;
}

function validEndlessAuditReport(data, report) {
  return report
    && typeof report.auditId === "string"
    && report.policyId === data.endless?.audit?.policy_id
    && report.provisional === true
    && Number.isInteger(report.seasonNumber)
    && report.seasonNumber >= 1
    && Number.isInteger(report.riskTier)
    && report.riskTier >= 1
    && Number.isInteger(report.operations)
    && report.operations === data.endless.season_length
    && Number.isFinite(report.score)
    && Number.isFinite(report.target)
    && Number.isFinite(report.margin)
    && Math.abs(report.margin - (report.score - report.target)) < 1e-9
    && typeof report.passed === "boolean"
    && Array.isArray(report.evidence)
    && report.evidence.length === report.operations;
}

function validEndlessState(data, state) {
  if (data.prototype_mode?.type !== "ENDLESS") return true;
  const history = state.endlessAuditHistory;
  const inAudit = state.phase === "ENDLESS_AUDIT";
  const expectedPassedCount = state.endlessSeasonIndex + (
    inAudit && state.endlessAuditReport?.passed === true ? 1 : 0
  );
  const expectedAuditCount = state.endlessSeasonIndex + (inAudit ? 1 : 0);
  const lifetime = state.endlessLifetimeMetrics;
  const currentReportMatchesHistory = !inAudit || (
    history.length > 0
    && JSON.stringify(history.at(-1)) === JSON.stringify(state.endlessAuditReport)
  );
  return Number.isInteger(state.endlessSeasonIndex)
    && state.endlessSeasonIndex >= 0
    && Number.isInteger(state.endlessSeasonNightIndex)
    && state.endlessSeasonNightIndex >= 0
    && state.endlessSeasonNightIndex < data.endless.season_length
    && Number.isInteger(state.endlessOverallNightIndex)
    && state.endlessOverallNightIndex === state.endlessCompletedOperations
    && Number.isInteger(state.endlessCompletedOperations)
    && state.endlessCompletedOperations >= 0
    && Number.isInteger(state.endlessResultHistoryOmittedCount)
    && state.endlessResultHistoryOmittedCount >= 0
    && state.endlessResultHistoryOmittedCount + state.nightResults.length === state.endlessCompletedOperations
    && state.nightResults.length <= data.endless.result_history_limit
    && Number.isInteger(state.endlessSeasonStartResultIndex)
    && state.endlessSeasonStartResultIndex >= 0
    && state.endlessSeasonStartResultIndex <= state.nightResults.length
    && state.endlessAuditTarget === endlessAuditTarget(data, state.endlessSeasonIndex)
    && state.endlessRiskTier === endlessRiskTier(data, state.endlessSeasonIndex)
    && Number.isInteger(state.endlessAuditPassedCount)
    && state.endlessAuditPassedCount === expectedPassedCount
    && Number.isFinite(state.endlessRunFame)
    && state.endlessRunFame >= 0
    && (state.endlessBestAuditScore === null || Number.isFinite(state.endlessBestAuditScore))
    && lifetime
    && Number.isFinite(lifetime.totalIncome)
    && Number.isFinite(lifetime.reputationDelta)
    && Number.isInteger(lifetime.acceptedGuests)
    && lifetime.acceptedGuests >= 0
    && Number.isInteger(lifetime.rejectedGuests)
    && lifetime.rejectedGuests >= 0
    && Number.isInteger(lifetime.canceledGuests)
    && lifetime.canceledGuests >= 0
    && Number.isInteger(lifetime.emergencyNights)
    && lifetime.emergencyNights >= 0
    && Array.isArray(history)
    && history.length <= data.endless.audit_history_limit
    && Number.isInteger(state.endlessAuditHistoryOmittedCount)
    && state.endlessAuditHistoryOmittedCount >= 0
    && state.endlessAuditHistoryOmittedCount + history.length === expectedAuditCount
    && history.every((report) => validEndlessAuditReport(data, report))
    && (inAudit ? validEndlessAuditReport(data, state.endlessAuditReport) : state.endlessAuditReport === null)
    && currentReportMatchesHistory
    && typeof state.endlessClosed === "boolean"
    && (state.endlessClosureReason === null || typeof state.endlessClosureReason === "string");
}

function facilityUpgradeFor(data, upgradeId) {
  const upgrade = data.indexes.upgrades[upgradeId];
  return upgrade?.kind === "FACILITY" ? upgrade : null;
}

function unlockedRoomIdsFor(data, ownedUpgradeIds) {
  const unlocked = new Set(
    data.rooms.filter((room) => room.built_from_start !== false).map((room) => room.id),
  );
  for (const upgradeId of ownedUpgradeIds) {
    const upgrade = data.indexes.upgrades[upgradeId];
    for (const roomId of upgrade?.room_unlocks ?? []) unlocked.add(roomId);
  }
  return unlocked;
}

function naturallyAdjacentRooms(left, right) {
  if (!left || !right || left.id === right.id) return false;
  const horizontal = left.floor === right.floor && Math.abs(left.wing - right.wing) === 1;
  const vertical = left.wing === right.wing && Math.abs(left.floor - right.floor) === 1;
  return horizontal || vertical;
}

function validFacilityRoomSelection(data, state, upgrade, roomIds, partial) {
  const installation = upgrade?.installation;
  if (!isPlainObject(installation)
    || !positiveSafeInteger(installation.target_count)
    || !["ANY", "VERTICAL_ADJACENT", "NON_ADJACENT"].includes(installation.relation)
    || typeof installation.reserves_target !== "boolean"
    || !isDenseArray(installation.required_attributes)
    || !installation.required_attributes.every(
      (attribute) => typeof attribute === "string" && attribute.length > 0,
    )
    || !isDenseArray(roomIds)
    || !roomIds.every((roomId) => typeof roomId === "string" && roomId.length > 0)
    || new Set(roomIds).size !== roomIds.length
    || (partial
      ? roomIds.length > installation.target_count
      : roomIds.length !== installation.target_count)) return false;

  const unlockedRoomIds = unlockedRoomIdsFor(data, state.ownedUpgradeIds);
  const rooms = roomIds.map((roomId) => data.indexes.rooms[roomId]);
  if (rooms.some((room, index) => !room || !unlockedRoomIds.has(roomIds[index]))) return false;
  if (rooms.some((room) => installation.required_attributes.some(
    (attribute) => !(room.attributes ?? []).includes(attribute),
  ))) return false;

  if (roomIds.length < installation.target_count || installation.relation === "ANY") return true;
  if (installation.target_count !== 2) return false;
  if (installation.relation === "VERTICAL_ADJACENT") {
    return rooms[0].wing === rooms[1].wing
      && Math.abs(rooms[0].floor - rooms[1].floor) === 1;
  }
  return !naturallyAdjacentRooms(rooms[0], rooms[1]);
}

function reservedFacilityTargetsConflict(entries) {
  for (let leftIndex = 0; leftIndex < entries.length; leftIndex += 1) {
    const left = entries[leftIndex];
    if (left.installation.reserves_target !== true) continue;
    const leftRooms = new Set(left.roomIds);
    for (let rightIndex = leftIndex + 1; rightIndex < entries.length; rightIndex += 1) {
      const right = entries[rightIndex];
      if (right.installation.reserves_target !== true) continue;
      if (right.roomIds.some((roomId) => leftRooms.has(roomId))) return true;
    }
  }
  return false;
}

function validFacilityInstallationState(data, state) {
  if (!isPlainObject(state.facilityPlacements)) return false;
  const ownedFacilityIds = state.ownedUpgradeIds.filter(
    (upgradeId) => Boolean(facilityUpgradeFor(data, upgradeId)),
  );
  if (!exactKeys(state.facilityPlacements, ownedFacilityIds)) return false;

  const installedEntries = [];
  for (const upgradeId of ownedFacilityIds) {
    const upgrade = facilityUpgradeFor(data, upgradeId);
    const placement = state.facilityPlacements[upgradeId];
    if (!exactKeys(placement, ["roomIds"])
      || !validFacilityRoomSelection(data, state, upgrade, placement.roomIds, false)) return false;
    installedEntries.push({
      upgradeId,
      roomIds: placement.roomIds,
      installation: upgrade.installation,
    });
  }
  if (reservedFacilityTargetsConflict(installedEntries)) return false;

  const pending = state.pendingFacilityInstallation;
  if (pending === null) return true;
  if (state.phase !== "UPGRADE"
    || !exactKeys(pending, ["upgradeId", "roomIds"])
    || !Array.isArray(state.currentUpgradeOfferIds)
    || !state.currentUpgradeOfferIds.includes(pending.upgradeId)
    || state.ownedUpgradeIds.includes(pending.upgradeId)) return false;
  const pendingUpgrade = facilityUpgradeFor(data, pending.upgradeId);
  if (!pendingUpgrade
    || !validFacilityRoomSelection(data, state, pendingUpgrade, pending.roomIds, true)) return false;
  return !reservedFacilityTargetsConflict([
    ...installedEntries,
    {
      upgradeId: pending.upgradeId,
      roomIds: pending.roomIds,
      installation: pendingUpgrade.installation,
    },
  ]);
}

function validState(data, state) {
  return state
    && SAVABLE_PHASES.has(state.phase)
    && Number.isInteger(state.runSeed)
    && Number.isInteger(state.currentNightIndex)
    && state.currentNightIndex >= 0
    && state.currentNightIndex < data.scenarios.length
    && Array.isArray(state.nightResults)
    && Array.isArray(state.ownedUpgradeIds)
    && state.ownedUpgradeIds.every((id) => Boolean(data.indexes.upgrades[id]))
    && validFacilityInstallationState(data, state)
    && Array.isArray(state.ownedDisplayRelicIds ?? [])
    && (state.ownedDisplayRelicIds ?? []).every((id) => Boolean(data.indexes.displayRelics?.[id]))
    && nonNegativeSafeInteger(state.foresightRetryCount)
    && denseUniqueStrings(state.foresightDiscoveryIds)
    && validRoomConditionMap(data, state.roomConditions)
    && validLastRoomWear(data, state.lastRoomWear)
    && validStayoverCleaningState(data, state)
    && (state.phase !== "RELIC_OFFER"
      || (Array.isArray(state.pendingDisplayRelicOffer?.relicIds)
        && state.pendingDisplayRelicOffer.relicIds.length > 0
        && state.pendingDisplayRelicOffer.relicIds.every((id) => Boolean(data.indexes.displayRelics?.[id]))))
    && (!isFormalCampaign(data) || validFormalCampaignState(data, state))
    && validEndlessState(data, state)
    && Object.keys(state.placements ?? {}).every(
      (guestId) => Boolean(data.indexes.guests[guestId]) && Boolean(data.indexes.rooms[state.placements[guestId]]),
    );
}

function createSnapshot(state) {
  if (!state) return null;
  const snapshot = clone(state);
  snapshot.handbookOpen = false;
  snapshot.reservationBoardOpen = false;
  snapshot.runRecord = null;
  return snapshot;
}

function validStageCheckpoint(data, checkpoint) {
  return checkpoint === null
    || (validState(data, checkpoint) && FORMAL_CHECKPOINT_PHASES.has(checkpoint.phase));
}

function formalOperationIdentity(config, runSeed, progress) {
  try {
    const descriptor = campaignOperationDescriptor(config, progress);
    return {
      id: campaignOperationId(config, runSeed, descriptor),
      resultIdentity: campaignResultIdentity(config, descriptor),
    };
  } catch {
    return null;
  }
}

function formalRecordIdentity(config, runSeed, record) {
  try {
    const descriptor = descriptorFromOperationRecord(config, record);
    return {
      id: campaignOperationId(config, runSeed, descriptor),
      resultIdentity: campaignResultIdentity(config, descriptor),
    };
  } catch {
    return null;
  }
}

function validFormalCheckpointFinancePrefix(state, checkpoint, position, expectedLength) {
  const liveFinance = state.campaignFinance;
  const checkpointFinance = checkpoint.campaignFinance;
  if (!isPlainObject(liveFinance)
    || !isPlainObject(checkpointFinance)
    || !isDenseArray(liveFinance.ledger)
    || !isDenseArray(checkpointFinance.ledger)
    || !exactKeys(checkpoint.campaignPendingExpenses, ["reactivation", "roomService"])
    || !exactKeys(state.campaignPendingExpenses, ["reactivation", "roomService"])
    || checkpointFinance.completedStageCount !== expectedLength
    || checkpointFinance.pendingDayResult !== null
    || !sameJson(checkpointFinance.ledger, liveFinance.ledger.slice(0, expectedLength))) {
    return false;
  }

  if (position === "PRE") {
    return sameJson(checkpointFinance, liveFinance)
      && sameJson(checkpoint.campaignPendingExpenses, state.campaignPendingExpenses)
      && checkpoint.campaignSelectedRepayment === state.campaignSelectedRepayment
      && checkpoint.gold === state.gold;
  }

  const openingRecord = FORMAL_FINANCE_PENDING_PHASES.has(state.phase)
    ? liveFinance.pendingDayResult
    : liveFinance.ledger[expectedLength];
  if (!openingRecord) return false;
  const cumulativeBefore = Object.prototype.hasOwnProperty.call(
    openingRecord,
    "cumulativeRepaymentBefore",
  )
    ? openingRecord.cumulativeRepaymentBefore
    : openingRecord.cumulativeRepayment - openingRecord.manualRepayment;
  return checkpointFinance.cash === openingRecord.openingCash
    && checkpointFinance.remainingDebt === openingRecord.openingDebt
    && checkpointFinance.cumulativeRepayment === cumulativeBefore
    && checkpoint.campaignPendingExpenses.reactivation === openingRecord.reactivation
    && checkpoint.campaignPendingExpenses.roomService === openingRecord.roomService
    && checkpoint.campaignSelectedRepayment === 0
    && checkpoint.gold + openingRecord.reactivation + openingRecord.roomService
      === openingRecord.openingCash;
}

function arrayIsExactPrefix(prefix, values) {
  return Array.isArray(prefix)
    && Array.isArray(values)
    && prefix.length <= values.length
    && sameJson(prefix, values.slice(0, prefix.length));
}

function upgradeCostTotal(data, upgradeIds) {
  let total = 0;
  for (const upgradeId of upgradeIds) {
    const cost = data.indexes.upgrades[upgradeId]?.cost;
    if (!nonNegativeSafeInteger(cost) || !Number.isSafeInteger(total + cost)) return null;
    total += cost;
  }
  return total;
}

function validFormalCheckpointImmutableState(data, state, checkpoint) {
  if (!sameJson(checkpoint.ownedDisplayRelicIds, state.ownedDisplayRelicIds)
    || checkpoint.playerGenderId !== state.playerGenderId
    || checkpoint.relationshipGenderPreset !== state.relationshipGenderPreset
    || !sameJson(
      checkpoint.relationshipPresentationIds,
      state.relationshipPresentationIds,
    )
    || checkpoint.secretaryPresentationId !== state.secretaryPresentationId) {
    return false;
  }

  // UPGRADE legitimately appends purchases after the day-opening checkpoint.
  // Every other savable formal phase must retain the exact opening inventory.
  if (state.phase !== "UPGRADE") {
    return sameJson(checkpoint.ownedUpgradeIds, state.ownedUpgradeIds);
  }
  if (!arrayIsExactPrefix(checkpoint.ownedUpgradeIds, state.ownedUpgradeIds)) return false;
  const purchasedIds = state.ownedUpgradeIds.slice(checkpoint.ownedUpgradeIds.length);
  const purchaseCost = upgradeCostTotal(data, purchasedIds);
  return purchaseCost !== null
    && sameJson(purchasedIds, state.renovationPurchaseIds)
    && purchaseCost === state.campaignPendingExpenses.reactivation;
}

function validRoomConditionMap(data, roomConditions) {
  const roomIds = data.rooms.map((room) => room.id);
  if (!exactKeys(roomConditions, roomIds)) return false;
  return roomIds.every((roomId) => {
    const condition = roomConditions[roomId];
    return exactKeys(condition, ["cleanliness"])
      && Number.isFinite(condition.cleanliness)
      && condition.cleanliness >= 0
      && condition.cleanliness <= 100;
  });
}

function clampRoomCondition(value) {
  return Math.max(0, Math.min(100, value));
}

function reconstructFormalPostNightState(data, checkpoint, result) {
  if (!denseUniqueStrings(result?.acceptedGuestIds)
    || !isPlainObject(result?.placements)
    || !isPlainObject(checkpoint.stayovers)) return null;
  const roomConditions = clone(checkpoint.roomConditions);
  const stayovers = {};
  const wearScale = data.balance?.wear_scale ?? 1;
  if (!Number.isFinite(wearScale) || wearScale < 0) return null;

  for (const guestId of result.acceptedGuestIds) {
    const guest = data.indexes.guests[guestId];
    const roomId = result.placements[guestId];
    const condition = roomConditions[roomId];
    if (!guest || !data.indexes.rooms[roomId] || !condition) return null;
    const cleanlinessLoss = guest.room_wear?.cleanliness
      ?? (guest.cleanliness_impact ?? 1) * wearScale;
    if (!Number.isFinite(cleanlinessLoss)
      || cleanlinessLoss < 0) return null;
    condition.cleanliness = clampRoomCondition(condition.cleanliness - cleanlinessLoss);

    const existing = checkpoint.stayovers[guestId];
    if (existing) {
      if (!exactKeys(existing, ["roomId", "remainingNights"])
        || existing.roomId !== roomId
        || !Number.isSafeInteger(existing.remainingNights)
        || existing.remainingNights < 1) return null;
      if (existing.remainingNights > 1) {
        stayovers[guestId] = {
          roomId,
          remainingNights: existing.remainingNights - 1,
        };
      }
    } else if ((guest.stay_nights ?? 1) > 1) {
      stayovers[guestId] = {
        roomId,
        remainingNights: guest.stay_nights - 1,
      };
    }
  }
  return { roomConditions, stayovers };
}

function validFormalCheckpointRoomState(data, state, checkpoint, position) {
  if (!validRoomConditionMap(data, state.roomConditions)
    || !validRoomConditionMap(data, checkpoint.roomConditions)) return false;
  if (position === "PRE") {
    return sameJson(checkpoint.roomConditions, state.roomConditions)
      && sameJson(checkpoint.stayovers, state.stayovers);
  }

  const expected = reconstructFormalPostNightState(
    data,
    checkpoint,
    state.nightResults.at(-1),
  );
  if (!expected || !sameJson(expected.stayovers, state.stayovers)) return false;
  if (state.phase !== "UPGRADE") {
    return state.campaignPendingExpenses.roomService === 0
      && sameJson(expected.roomConditions, state.roomConditions);
  }

  let board;
  try {
    board = createBoardState(data, {
      ownedFacilityIds: state.ownedUpgradeIds,
      roomConditions: {},
      protectedRoomIds: [],
    });
  } catch {
    return false;
  }
  let servicedRoomCount = 0;
  for (const room of data.rooms) {
    const before = expected.roomConditions[room.id];
    const live = state.roomConditions[room.id];
    if (sameJson(before, live)) continue;
    const restored = live.cleanliness === 100;
    const neededService = before.cleanliness !== 100;
    if (!restored
      || !neededService
      || board.blockedRooms.has(room.id)) return false;
    servicedRoomCount += 1;
  }

  const baseCost = data.balance?.room_service_cost ?? 8;
  const reduction = displayRelicEffectValue(
    data,
    state.ownedDisplayRelicIds,
    "ROOM_SERVICE_COST_REDUCTION",
  );
  const serviceCost = Math.max(0, baseCost - reduction);
  const totalServiceCost = servicedRoomCount * serviceCost;
  return nonNegativeSafeInteger(serviceCost)
    && Number.isSafeInteger(totalServiceCost)
    && totalServiceCost === state.campaignPendingExpenses.roomService;
}

function validFormalStageCheckpoint(data, state, checkpoint) {
  const config = formalCampaignProgressConfig(data);
  if (!config) return false;
  const position = formalPhasePosition(state);
  const isPrelude = position === "PRELUDE";
  if (isPrelude) return checkpoint === null;
  if (!checkpoint || !validStageCheckpoint(data, checkpoint)) return false;
  if (checkpoint.profileId !== state.profileId || checkpoint.runSeed !== state.runSeed) return false;
  if (formalPhasePosition(checkpoint) !== "PRE") return false;

  const liveResults = state.nightResults;
  const checkpointResults = checkpoint.nightResults;
  const expectedCheckpointLength = position === "PRE"
    ? liveResults.length
    : liveResults.length - 1;
  if (expectedCheckpointLength < 0 || checkpointResults.length !== expectedCheckpointLength) return false;
  if (!sameJson(checkpointResults, liveResults.slice(0, expectedCheckpointLength))) return false;
  if (checkpoint.campaignProgress.completedStageCount !== expectedCheckpointLength) return false;
  if (!sameJson(
    checkpoint.campaignProgress.operationRecords,
    state.campaignProgress.operationRecords.slice(0, expectedCheckpointLength),
  )) return false;
  if (!validFormalCheckpointImmutableState(data, state, checkpoint)) return false;
  if (!validFormalCheckpointRoomState(data, state, checkpoint, position)) return false;
  if (!validFormalCheckpointFinancePrefix(
    state,
    checkpoint,
    position,
    expectedCheckpointLength,
  )) return false;

  const checkpointIdentity = formalOperationIdentity(
    config,
    checkpoint.runSeed,
    checkpoint.campaignProgress,
  );
  const liveIdentity = position === "PRE"
    ? formalOperationIdentity(config, state.runSeed, state.campaignProgress)
    : formalRecordIdentity(config, state.runSeed, state.campaignProgress.operationRecords.at(-1));
  if (!checkpointIdentity || !liveIdentity) return false;
  if (checkpointIdentity.id !== liveIdentity.id
    || !sameJson(checkpointIdentity.resultIdentity, liveIdentity.resultIdentity)) return false;
  if (checkpoint.currentNightIndex !== state.currentNightIndex) return false;

  return position !== "PRE" || sameJson(checkpoint.campaignProgress, state.campaignProgress);
}

function migrateRoomConditionsToSchema7(data, roomConditions) {
  if (!isPlainObject(roomConditions)) return roomConditions;
  return Object.fromEntries(data.rooms.map((room) => [
    room.id,
    { cleanliness: roomConditions[room.id]?.cleanliness },
  ]));
}

function migrateLastRoomWearToSchema7(lastRoomWear) {
  if (!Array.isArray(lastRoomWear)) return lastRoomWear;
  return lastRoomWear.map((entry) => {
    if (!isPlainObject(entry)) return entry;
    const {
      durability: _durability,
      durabilityLoss: _durabilityLoss,
      ...cleanlinessWear
    } = entry;
    return cleanlinessWear;
  });
}

function migrateStateToSchema7(data, state) {
  if (!isPlainObject(state)) return state;
  state.roomConditions = migrateRoomConditionsToSchema7(data, state.roomConditions);
  state.lastRoomWear = migrateLastRoomWearToSchema7(state.lastRoomWear);
  state.pendingStayoverCleaningRequest = null;
  state.stayoverCleaningRequestChecked = false;
  state.declinedStayoverCleaningRoomIds = [];
  state.stayoverCleaningRequestGuestIds = [];
  return state;
}

function migrateIntroducedEndlessRoomsToSchema8(data, state) {
  if (!isPlainObject(state)
    || data.prototype_mode?.type !== "ENDLESS"
    || !isPlainObject(state.roomConditions)) return state;
  for (const room of data.rooms) {
    if (room.introduced_in_save_schema !== 8) continue;
    if (!Object.prototype.hasOwnProperty.call(state.roomConditions, room.id)) {
      state.roomConditions[room.id] = { cleanliness: 100 };
    }
  }
  return state;
}

function migrateStateToSchema8(data, state, sourceSchemaVersion) {
  if (!isPlainObject(state)) return state;
  migrateIntroducedEndlessRoomsToSchema8(data, state);
  if (sourceSchemaVersion < 7) migrateStateToSchema7(data, state);
  state.facilityPlacements = Object.fromEntries(
    (state.ownedUpgradeIds ?? [])
      .map((upgradeId) => [upgradeId, facilityUpgradeFor(data, upgradeId)])
      .filter(([, upgrade]) => Boolean(upgrade))
      .map(([upgradeId, upgrade]) => [
        upgradeId,
        { roomIds: [...(upgrade.installation?.legacy_room_ids ?? [])] },
      ]),
  );
  state.pendingFacilityInstallation = null;
  return state;
}

function normalizeRunSave(data, save) {
  if (save?.schema_version === RUN_SAVE_SCHEMA_VERSION) return clone(save);
  const sourceSchemaVersion = save?.schema_version;
  const supportedLegacySchemas = isFormalCampaign(data)
    ? [6, 7]
    : [3, 4, 5, 6, 7];
  if (!supportedLegacySchemas.includes(sourceSchemaVersion)) return null;
  const normalized = clone(save);
  normalized.schema_version = RUN_SAVE_SCHEMA_VERSION;
  normalized.data_schema_version = data.schema_version;
  normalized.profile_id = typeof save.profile_id === "string" ? save.profile_id : "default";
  normalized.state = migrateStateToSchema8(data, normalized.state, sourceSchemaVersion);
  if (!isPlainObject(normalized.state)) return null;
  normalized.state.profileId = typeof save.state?.profileId === "string"
    ? save.state.profileId
    : normalized.profile_id;
  if (normalized.stage_checkpoint !== null && normalized.stage_checkpoint !== undefined) {
    normalized.stage_checkpoint = migrateStateToSchema8(
      data,
      normalized.stage_checkpoint,
      sourceSchemaVersion,
    );
  }
  return normalized;
}

function validRunSave(data, save) {
  const generallyValid = save
    && save.schema_version === RUN_SAVE_SCHEMA_VERSION
    && save.data_schema_version === data.schema_version
    && save.mode_id === data.prototype_mode.type
    && typeof save.profile_id === "string"
    && validState(data, save.state)
    && validStageCheckpoint(data, save.stage_checkpoint ?? null);
  if (!generallyValid || !isFormalCampaign(data)) return Boolean(generallyValid);
  const config = formalCampaignProgressConfig(data);
  const plan = formalCampaignOperationPlan(data);
  const financeConfig = formalCampaignFinanceConfig(data, save.state);
  return Boolean(config)
    && save.stage_authority_id === config.id
    && Boolean(plan)
    && save.operation_plan_authority_id === plan.plan_id
    && save.operation_plan_authority_version === plan.plan_version
    && Boolean(financeConfig)
    && save.finance_authority_id === financeConfig.id
    && save.state.profileId === save.profile_id
    && validFormalStageCheckpoint(data, save.state, save.stage_checkpoint ?? null);
}

export function createRunSave(data, state, stageCheckpoint = null) {
  if (!SAVABLE_PHASES.has(state.phase)) return null;
  const config = formalCampaignProgressConfig(data);
  const plan = formalCampaignOperationPlan(data);
  const financeConfig = formalCampaignFinanceConfig(data, state);
  const save = {
    schema_version: RUN_SAVE_SCHEMA_VERSION,
    data_schema_version: data.schema_version,
    mode_id: data.prototype_mode.type,
    ...(isFormalCampaign(data) ? {
      stage_authority_id: config?.id ?? null,
      operation_plan_authority_id: plan?.plan_id ?? null,
      operation_plan_authority_version: plan?.plan_version ?? null,
      finance_authority_id: financeConfig?.id ?? null,
    } : {}),
    profile_id: state.profileId ?? "default",
    saved_at: new Date().toISOString(),
    state: createSnapshot(state),
    stage_checkpoint: createSnapshot(stageCheckpoint),
  };
  return isFormalCampaign(data) && !validRunSave(data, save) ? null : save;
}

export function readActiveRunSave(data, storage = globalThis.localStorage) {
  if (!storage) return null;
  const keys = [activeRunStorageKey(data)];
  if (data.prototype_mode.type === "SHOWCASE") keys.push(ACTIVE_RUN_STORAGE_KEY);
  for (const key of keys) {
    try {
      const parsed = JSON.parse(storage.getItem(key) ?? "null");
      const normalized = normalizeRunSave(data, parsed);
      if (validRunSave(data, normalized)) return normalized;
    } catch {
      // Try the next compatible key.
    }
  }
  return null;
}

export function writeActiveRunSave(data, state, stageCheckpoint = null, storage = globalThis.localStorage) {
  const save = createRunSave(data, state, stageCheckpoint);
  if (!save || !storage) return save;
  try {
    storage.setItem(activeRunStorageKey(data), JSON.stringify(save));
    return save;
  } catch {
    return null;
  }
}

export function clearActiveRunSave(dataOrStorage, storage = globalThis.localStorage) {
  const hasData = Boolean(dataOrStorage?.prototype_mode);
  const data = hasData ? dataOrStorage : null;
  const targetStorage = hasData ? storage : (dataOrStorage ?? globalThis.localStorage);
  if (!targetStorage) return;
  const keys = data ? [activeRunStorageKey(data)] : [ACTIVE_RUN_STORAGE_KEY];
  if (!data || data.prototype_mode.type === "SHOWCASE") keys.push(ACTIVE_RUN_STORAGE_KEY);
  try {
    uniqueStrings(keys).forEach((key) => targetStorage.removeItem(key));
  } catch {
    // Storage can be unavailable in privacy-restricted browser contexts.
  }
}
