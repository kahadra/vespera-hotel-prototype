export const RUN_RECORD_SCHEMA_VERSION = 3;
export const RUN_RECORD_STORAGE_KEY = "vespera.hotel.run-records.v1";
export const RUN_RECORD_LIMIT = 20;

function sum(results, selector) {
  return results.reduce((total, result) => total + selector(result), 0);
}

export function summarizeRun(data, state) {
  const nightResults = state.nightResults.filter(Boolean);
  const isEndless = data.prototype_mode?.type === "ENDLESS";
  const lifetime = state.endlessLifetimeMetrics ?? {};
  const coreMetrics = isEndless
    ? {
      completed_nights: Number(state.endlessCompletedOperations ?? 0),
      total_income: Number(lifetime.totalIncome ?? 0),
      reputation_delta: Number(lifetime.reputationDelta ?? 0),
      accepted_guests: Number(lifetime.acceptedGuests ?? 0),
      rejected_guests: Number(lifetime.rejectedGuests ?? 0),
      canceled_guests: Number(lifetime.canceledGuests ?? 0),
      emergency_nights: Number(lifetime.emergencyNights ?? 0),
    }
    : {
      completed_nights: nightResults.length,
      total_income: sum(nightResults, (result) => result.income ?? 0),
      reputation_delta: sum(nightResults, (result) => result.reputationDelta ?? 0),
      accepted_guests: sum(nightResults, (result) => result.acceptedGuestIds?.length ?? 0),
      rejected_guests: sum(nightResults, (result) => result.rejectedGuestIds?.length ?? 0),
      canceled_guests: sum(nightResults, (result) => result.canceledGuestIds?.length ?? 0),
      emergency_nights: nightResults.filter((result) => result.emergencyReport?.timedOut).length,
    };
  const formalSpecies = data.campaign?.formal_species ?? [];
  const affinityById = state.speciesAffinityById ?? {};
  const affinityThreshold = data.campaign?.ending_thresholds?.species_affinity ?? 5;
  const affinities = formalSpecies.map((species) => ({
    ...species,
    affinity: Number(affinityById[species.id] ?? 0),
  }));
  const maximumAffinity = Math.max(0, ...affinities.map((item) => item.affinity));
  const leaders = maximumAffinity >= affinityThreshold
    ? affinities.filter((item) => item.affinity === maximumAffinity)
    : [];
  const triggered = new Set(state.speciesEndingTriggerIds ?? []);
  const committedId = state.speciesEndingCommitmentId ?? null;
  const dominantSpeciesId = committedId
    && leaders.some((item) => item.id === committedId)
    && triggered.has(committedId)
    ? committedId
    : leaders.length === 1 && triggered.has(leaders[0].id)
      ? leaders[0].id
      : null;
  const relationshipProgress = state.relationshipProgressByRole ?? {};
  const relationshipRoles = data.campaign?.relationship_roles ?? [];
  const readyRelationshipCount = relationshipRoles.filter(
    (role) => relationshipProgress[role.id]?.ending_ready === true,
  ).length;
  const dreamDemonAffinityThreshold = data.campaign?.ending_thresholds?.dream_demon_other_species_affinity ?? 3;
  const dreamDemonRequiredSpeciesCount = data.campaign?.ending_thresholds?.dream_demon_other_species_count ?? 2;
  const dreamDemonOtherSpeciesAllies = affinities.filter(
    (species) => species.id !== "DREAM_DEMON" && species.affinity >= dreamDemonAffinityThreshold,
  ).length;
  const campaignMetrics = {
    chapter_hurdle_failures: Number(state.chapterHurdleFailures ?? 0),
    truth_evidence: Number(state.truthEvidenceCount ?? 0),
    peace_alliance: state.peaceAllianceComplete ? 1 : 0,
    relationship_endings_ready: readyRelationshipCount,
    all_relationship_endings_ready: relationshipRoles.length > 0
      && readyRelationshipCount === relationshipRoles.length ? 1 : 0,
    dream_demon_other_species_allies: dreamDemonOtherSpeciesAllies,
    dream_demon_other_species_network: dreamDemonOtherSpeciesAllies >= dreamDemonRequiredSpeciesCount ? 1 : 0,
  };
  const endlessMetrics = {
    endless_closed: state.endlessClosed ? 1 : 0,
    endless_seasons_cleared: Number(state.endlessAuditPassedCount ?? 0),
    endless_survived_nights: Number(state.endlessCompletedOperations ?? 0),
    endless_last_audit_score: Number(state.endlessAuditReport?.score ?? 0),
    endless_last_audit_target: Number(state.endlessAuditReport?.target ?? 0),
    endless_last_audit_margin: Number(state.endlessAuditReport?.margin ?? 0),
    endless_best_audit_score: Number(
      state.endlessBestAuditScore ?? state.endlessAuditReport?.score ?? 0,
    ),
    endless_run_fame: Number(state.endlessRunFame ?? 0),
    endless_risk_tier: Number(state.endlessRiskTier ?? 0),
    endless_omitted_result_history: Number(state.endlessResultHistoryOmittedCount ?? 0),
    endless_omitted_audit_history: Number(state.endlessAuditHistoryOmittedCount ?? 0),
  };
  for (const species of formalSpecies) {
    campaignMetrics[`species_affinity_${species.metric_id}`] = Number(affinityById[species.id] ?? 0);
    campaignMetrics[`species_route_${species.metric_id}`] = triggered.has(species.id) ? 1 : 0;
    campaignMetrics[`dominant_species_${species.metric_id}`] = dominantSpeciesId === species.id ? 1 : 0;
    campaignMetrics[`relationship_ready_${species.metric_id}`] = relationshipProgress[species.relationship_role_id]?.ending_ready ? 1 : 0;
  }
  return {
    ...coreMetrics,
    final_gold: state.gold,
    final_reputation: state.hotelReputation,
    purchased_upgrades: state.ownedUpgradeIds.length,
    foresight_retries: state.foresightRetryCount ?? 0,
    expected_nights: data.prototype_mode?.total_nights ?? data.scenarios.length,
    ...campaignMetrics,
    ...endlessMetrics,
  };
}

function conditionMatches(metrics, condition) {
  const actual = metrics[condition.metric];
  if (!Number.isFinite(actual)) return false;
  if (condition.operator === "GTE") return actual >= condition.value;
  if (condition.operator === "LTE") return actual <= condition.value;
  if (condition.operator === "EQ") return actual === condition.value;
  return false;
}

export function resolveRunEnding(data, state) {
  const metrics = summarizeRun(data, state);
  const completion = data.run_completion;
  const matched = [...completion.ending_rules]
    .sort((left, right) => right.priority - left.priority)
    .find((ending) => ending.conditions.every((condition) => conditionMatches(metrics, condition)));
  return {
    ...(matched ?? completion.fallback_ending),
    metrics,
  };
}

export function buildRelationshipEpilogues(data, state, ending) {
  const roles = data.campaign?.relationship_roles ?? [];
  const progressByRole = state.relationshipProgressByRole ?? {};
  return roles.flatMap((role) => {
    const progress = progressByRole[role.id];
    if (!progress?.epilogue_unlocked) return [];
    const selected = ending.ending_tier === "TRUE_HAREM"
      || state.selectedEndingRelationshipRoleId === role.id
      || ending.relationship_role_id === role.id;
    const sameSpecies = ending.species_id === role.species_id;
    let description;
    if (ending.ending_tier === "BAD") {
      description = progress.hotel_dependency === "RESIDENT"
        ? "호텔에 기대었던 계획은 크게 흔들렸지만, 자신의 삶 전체가 호텔과 함께 무너지지는 않았습니다."
        : "베스페라와 이어질 수 있었던 가능성은 사라졌지만, 호텔 밖에서 이어 오던 자신의 삶으로 돌아갔습니다.";
    } else if (["TRUE", "TRUE_HAREM"].includes(ending.ending_tier)) {
      description = selected
        ? "평화 협약 이후에도 지배인과 가장 가까운 동반자로서 자신의 공동체와 호텔을 오갔습니다."
        : "평화 협약의 당사자이자 종족 연락책으로서 자기 삶을 유지하며 베스페라와 협력했습니다.";
    } else if (sameSpecies) {
      description = selected
        ? "자기 종족의 삶을 버리지 않은 채 지배인의 동반자이자 호텔 협력자로 남았습니다."
        : "종족과 호텔 사이의 연락책으로 활동하며 자기 공동체에서의 삶도 계속했습니다.";
    } else {
      description = "호텔의 일반 직원이 되지는 않았으며, 자신의 삶을 이어 가면서 필요할 때 베스페라를 돕는 협력자로 남았습니다.";
    }
    return [{
      relationship_role_id: role.id,
      species_id: role.species_id,
      label: role.label,
      presentation_id: state.relationshipPresentationIds?.[role.id] ?? "FEMALE",
      npc_stage: progress.npc_stage ?? "GUEST",
      selected,
      description,
    }];
  });
}

export function createRunRecord(data, state) {
  const ending = resolveRunEnding(data, state);
  const relationshipEpilogues = buildRelationshipEpilogues(data, state, ending);
  return {
    schema_version: RUN_RECORD_SCHEMA_VERSION,
    record_id: `${data.run_completion.record_namespace}:${state.runSeed}`,
    recorded_at: new Date().toISOString(),
    data_schema_version: data.schema_version,
    mode_id: data.prototype_mode.type,
    profile_id: state.profileId ?? "default",
    run_seed: state.runSeed,
    ending_id: ending.id,
    outcome: ending.outcome,
    title: ending.title,
    description: ending.description,
    ending_tier: ending.ending_tier ?? ending.outcome,
    species_id: ending.species_id ?? null,
    relationship_role_id: ending.relationship_role_id
      ?? state.selectedEndingRelationshipRoleId
      ?? null,
    manager_outcome: ending.manager_outcome ?? null,
    relationship_epilogues: relationshipEpilogues,
    player_gender_id: state.playerGenderId ?? null,
    relationship_gender_preset: state.relationshipGenderPreset ?? null,
    relationship_presentation_ids: state.relationshipPresentationIds ?? {},
    secretary_presentation_id: state.secretaryPresentationId ?? null,
    owned_display_relic_ids: [...(state.ownedDisplayRelicIds ?? [])],
    owned_upgrade_ids: [...(state.ownedUpgradeIds ?? [])],
    display_relic_trigger_counts: { ...(state.displayRelicTriggerCounts ?? {}) },
    endless_audit_history: (state.endlessAuditHistory ?? []).map((report) => ({
      ...report,
      evidence: (report.evidence ?? []).map((entry) => ({ ...entry })),
    })),
    endless_audit_history_omitted_count: Number(state.endlessAuditHistoryOmittedCount ?? 0),
    endless_closure_reason: state.endlessClosureReason ?? null,
    metrics: ending.metrics,
  };
}

export function readRunRecords(storage = globalThis.localStorage) {
  if (!storage) return [];
  try {
    const parsed = JSON.parse(storage.getItem(RUN_RECORD_STORAGE_KEY) ?? "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((record) => [1, 2, RUN_RECORD_SCHEMA_VERSION].includes(record?.schema_version) && typeof record.record_id === "string")
      .map((record) => ({
        profile_id: "default",
        description: "",
        ending_tier: record.outcome ?? "INCOMPLETE",
        species_id: null,
        relationship_role_id: null,
        manager_outcome: null,
        relationship_epilogues: [],
        relationship_presentation_ids: {},
        owned_display_relic_ids: [],
        owned_upgrade_ids: [],
        display_relic_trigger_counts: {},
        endless_audit_history: [],
        endless_audit_history_omitted_count: 0,
        endless_closure_reason: null,
        ...record,
        schema_version: RUN_RECORD_SCHEMA_VERSION,
      }));
  } catch {
    return [];
  }
}

export function storeRunRecord(record, storage = globalThis.localStorage) {
  const existing = readRunRecords(storage).filter((item) => item.record_id !== record.record_id);
  const records = [record, ...existing].slice(0, RUN_RECORD_LIMIT);
  if (!storage) return records;
  try {
    storage.setItem(RUN_RECORD_STORAGE_KEY, JSON.stringify(records));
    return records;
  } catch {
    return existing;
  }
}
