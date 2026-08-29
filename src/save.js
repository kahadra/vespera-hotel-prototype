import { endlessAuditTarget, endlessRiskTier } from "./endless.js";
import {
  campaignOperationDescriptor,
  campaignOperationId,
  campaignResultIdentity,
  validateCampaignProgressConfig,
  validateCampaignProgressState,
} from "./campaign-progress.js";

export const RUN_SAVE_SCHEMA_VERSION = 5;
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

function isDenseArray(value) {
  if (!Array.isArray(value)) return false;
  for (let index = 0; index < value.length; index += 1) {
    if (!Object.prototype.hasOwnProperty.call(value, index)) return false;
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

function descriptorFromOperationRecord(config, record) {
  return {
    type: "CAMPAIGN_OPERATION",
    stageNumber: record.resultIdentity.stageNumber,
    operationKind: record.resultIdentity.operationKind,
    templateIndex: record.resultIdentity.templateIndex,
    recoveryBoundaryStageNumber: record.recoveryBoundaryStageNumber,
    templatePolicyId: config.scenario_template_policy_id,
    templateProductionReady: config.scenario_templates_production_ready,
  };
}

function validFormalResult(config, runSeed, result, operationRecord) {
  if (!result || typeof result !== "object" || Array.isArray(result)) return false;
  const descriptor = descriptorFromOperationRecord(config, operationRecord);
  let expectedOperationId;
  let expectedResultIdentity;
  try {
    expectedOperationId = campaignOperationId(config, runSeed, descriptor);
    expectedResultIdentity = campaignResultIdentity(config, descriptor);
  } catch {
    return false;
  }
  return result.campaignOperationId === expectedOperationId
    && sameJson(result.campaignResultIdentity, expectedResultIdentity)
    && sameJson(result.campaignResultIdentity, operationRecord.resultIdentity)
    && result.campaignRecoveryBoundaryStageNumber === operationRecord.recoveryBoundaryStageNumber
    && operationRecord.resultIdentity.templateIndex >= 0
    && operationRecord.resultIdentity.templateIndex < config.scenario_template_count;
}

function formalPhasePosition(state) {
  if (FORMAL_PRE_OPERATION_PHASES.has(state.phase)) return "PRE";
  if (FORMAL_POST_OPERATION_PHASES.has(state.phase)) return "POST";
  if (state.phase === "STORY") {
    return state.campaignProgress.completedStageCount === 0 ? "PRELUDE" : "POST";
  }
  if (["TUTORIAL", "RELIC_OFFER"].includes(state.phase)) return "PRELUDE";
  return null;
}

function validFormalCampaignState(data, state) {
  const config = formalCampaignProgressConfig(data);
  if (!config || !Number.isInteger(state.runSeed) || state.runSeed < 0 || state.runSeed > 0xFFFFFFFF) {
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
    (record, index) => validFormalResult(config, state.runSeed, state.nightResults[index], record),
  )) return false;

  const position = formalPhasePosition(state);
  if (!position) return false;
  if (position === "PRELUDE") {
    if (progress.completedStageCount !== 0 || progress.status !== "ACTIVE") return false;
    if (state.phase === "RELIC_OFFER" && state.pendingDisplayRelicOffer === null) return false;
  }

  let authorityDescriptor;
  try {
    authorityDescriptor = position === "POST"
      ? descriptorFromOperationRecord(config, progress.operationRecords.at(-1))
      : campaignOperationDescriptor(config, progress);
    campaignOperationId(config, state.runSeed, authorityDescriptor);
  } catch {
    return false;
  }
  if (position === "POST" && progress.completedStageCount === 0) return false;
  if (position === "PRE" && progress.status !== "ACTIVE") return false;
  if (state.phase === "UPGRADE" && progress.status !== "ACTIVE") return false;
  return state.currentNightIndex === authorityDescriptor.templateIndex
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
    && Array.isArray(state.ownedDisplayRelicIds ?? [])
    && (state.ownedDisplayRelicIds ?? []).every((id) => Boolean(data.indexes.displayRelics?.[id]))
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

function normalizeRunSave(data, save) {
  if (isFormalCampaign(data)) {
    if (save?.schema_version !== RUN_SAVE_SCHEMA_VERSION) return null;
    return clone(save);
  }
  if (![3, 4, RUN_SAVE_SCHEMA_VERSION].includes(save?.schema_version)) return null;
  const normalized = clone(save);
  normalized.schema_version = RUN_SAVE_SCHEMA_VERSION;
  normalized.profile_id = typeof save.profile_id === "string" ? save.profile_id : "default";
  normalized.state.profileId = typeof save.state?.profileId === "string"
    ? save.state.profileId
    : normalized.profile_id;
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
  return Boolean(config)
    && save.stage_authority_id === config.id
    && save.state.profileId === save.profile_id
    && validFormalStageCheckpoint(data, save.state, save.stage_checkpoint ?? null);
}

export function createRunSave(data, state, stageCheckpoint = null) {
  if (!SAVABLE_PHASES.has(state.phase)) return null;
  const config = formalCampaignProgressConfig(data);
  const save = {
    schema_version: RUN_SAVE_SCHEMA_VERSION,
    data_schema_version: data.schema_version,
    mode_id: data.prototype_mode.type,
    ...(isFormalCampaign(data) ? { stage_authority_id: config?.id ?? null } : {}),
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
