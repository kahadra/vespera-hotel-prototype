export const RUN_SAVE_SCHEMA_VERSION = 4;
export const PROFILE_SCHEMA_VERSION = 1;
export const ACTIVE_RUN_STORAGE_KEY = "vespera.hotel.active-run.v1";
export const ACTIVE_RUN_STORAGE_PREFIX = "vespera.hotel.active-run.v2";
export const PROFILE_STORAGE_KEY = "vespera.hotel.profile.v1";

const SAVABLE_PHASES = new Set([
  "TUTORIAL",
  "STORY",
  "DAY_OPENING",
  "RESERVATION",
  "PLACEMENT",
  "RESULT",
  "RESULT_REVIEW",
  "UPGRADE",
]);

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function uniqueStrings(values) {
  return [...new Set((values ?? []).filter((value) => typeof value === "string" && value.length > 0))];
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
    || (validState(data, checkpoint) && ["DAY_OPENING", "RESERVATION", "PLACEMENT"].includes(checkpoint.phase));
}

function normalizeRunSave(data, save) {
  if (![3, RUN_SAVE_SCHEMA_VERSION].includes(save?.schema_version)) return null;
  const normalized = clone(save);
  normalized.schema_version = RUN_SAVE_SCHEMA_VERSION;
  normalized.profile_id = typeof save.profile_id === "string" ? save.profile_id : "default";
  normalized.state.profileId = typeof save.state?.profileId === "string"
    ? save.state.profileId
    : normalized.profile_id;
  return normalized;
}

function validRunSave(data, save) {
  return save
    && save.schema_version === RUN_SAVE_SCHEMA_VERSION
    && save.data_schema_version === data.schema_version
    && save.mode_id === data.prototype_mode.type
    && typeof save.profile_id === "string"
    && validState(data, save.state)
    && validStageCheckpoint(data, save.stage_checkpoint ?? null);
}

export function createRunSave(data, state, stageCheckpoint = null) {
  if (!SAVABLE_PHASES.has(state.phase)) return null;
  return {
    schema_version: RUN_SAVE_SCHEMA_VERSION,
    data_schema_version: data.schema_version,
    mode_id: data.prototype_mode.type,
    profile_id: state.profileId ?? "default",
    saved_at: new Date().toISOString(),
    state: createSnapshot(state),
    stage_checkpoint: createSnapshot(stageCheckpoint),
  };
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
