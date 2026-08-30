import { resolveRunEnding } from "./run.js";

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function dummyNightResult() {
  return {
    valid: true,
    income: 0,
    reputationDelta: 0,
    acceptedGuestIds: [],
    rejectedGuestIds: [],
    canceledGuestIds: [],
    emergencyReport: null,
  };
}

function baseWitness(data) {
  const relationshipProgressByRole = Object.fromEntries(
    (data.campaign?.relationship_roles ?? []).map((role) => [role.id, {
      ending_ready: false,
    }]),
  );
  const speciesAffinityById = Object.fromEntries(
    (data.campaign?.formal_species ?? []).map((species) => [species.id, 0]),
  );
  return {
    nightResults: [],
    gold: 0,
    hotelReputation: 0,
    ownedUpgradeIds: [],
    foresightRetryCount: 0,
    chapterHurdleFailures: 0,
    campaignFinance: null,
    truthEvidenceCount: 0,
    peaceAllianceComplete: false,
    relationshipProgressByRole,
    speciesAffinityById,
    speciesEndingTriggerIds: [],
    speciesEndingCommitmentId: null,
  };
}

function ensureCompletedNights(state, count) {
  while (state.nightResults.length < count) state.nightResults.push(dummyNightResult());
}

function formalSpeciesByMetric(data, metricId) {
  return (data.campaign?.formal_species ?? []).find((species) => species.metric_id === metricId);
}

function makeSpeciesDominant(data, state, metricId) {
  const species = formalSpeciesByMetric(data, metricId);
  if (!species) throw new Error(`Unknown species metric: ${metricId}`);
  const threshold = data.campaign?.ending_thresholds?.species_affinity ?? 5;
  state.speciesAffinityById[species.id] = threshold;
  state.speciesEndingTriggerIds = [species.id];
  state.speciesEndingCommitmentId = species.id;
}

function makeRelationshipReady(data, state, metricId) {
  const species = formalSpeciesByMetric(data, metricId);
  if (!species) throw new Error(`Unknown relationship metric: ${metricId}`);
  state.relationshipProgressByRole[species.relationship_role_id] = { ending_ready: true };
}

function makeDreamDemonNetwork(data, state) {
  const threshold = data.campaign?.ending_thresholds?.dream_demon_other_species_affinity ?? 3;
  const required = data.campaign?.ending_thresholds?.dream_demon_other_species_count ?? 2;
  (data.campaign?.formal_species ?? [])
    .filter((species) => species.id !== "DREAM_DEMON")
    .slice(0, required)
    .forEach((species) => {
      state.speciesAffinityById[species.id] = threshold;
    });
}

function satisfyCondition(data, state, condition) {
  const value = Number(condition.value);
  const scalarStateKeys = {
    final_gold: "gold",
    final_reputation: "hotelReputation",
    chapter_hurdle_failures: "chapterHurdleFailures",
    truth_evidence: "truthEvidenceCount",
    foresight_retries: "foresightRetryCount",
  };
  if (condition.metric === "completed_nights") {
    ensureCompletedNights(state, value);
    return;
  }
  if (condition.metric === "campaign_operating_cash_shortfall") {
    state.campaignFinance = value >= 1
      ? { operatingFailure: { stageNumber: 1, shortfallAmount: 1 } }
      : null;
    return;
  }
  if (scalarStateKeys[condition.metric]) {
    state[scalarStateKeys[condition.metric]] = value;
    return;
  }
  if (condition.metric === "peace_alliance") {
    state.peaceAllianceComplete = value === 1;
    return;
  }
  if (condition.metric === "all_relationship_endings_ready") {
    if (value === 1) {
      Object.keys(state.relationshipProgressByRole).forEach((roleId) => {
        state.relationshipProgressByRole[roleId] = { ending_ready: true };
      });
    }
    return;
  }
  if (condition.metric === "relationship_endings_ready") {
    Object.keys(state.relationshipProgressByRole).slice(0, value).forEach((roleId) => {
      state.relationshipProgressByRole[roleId] = { ending_ready: true };
    });
    return;
  }
  if (condition.metric === "dream_demon_other_species_network") {
    if (value === 1) makeDreamDemonNetwork(data, state);
    return;
  }
  if (condition.metric.startsWith("dominant_species_")) {
    makeSpeciesDominant(data, state, condition.metric.slice("dominant_species_".length));
    return;
  }
  if (condition.metric.startsWith("relationship_ready_")) {
    makeRelationshipReady(data, state, condition.metric.slice("relationship_ready_".length));
    return;
  }
  if (condition.metric.startsWith("species_affinity_")) {
    const metricId = condition.metric.slice("species_affinity_".length);
    const species = formalSpeciesByMetric(data, metricId);
    if (!species) throw new Error(`Unknown affinity metric: ${metricId}`);
    state.speciesAffinityById[species.id] = value;
    return;
  }
  if (condition.metric.startsWith("species_route_")) {
    const metricId = condition.metric.slice("species_route_".length);
    const species = formalSpeciesByMetric(data, metricId);
    if (!species) throw new Error(`Unknown route metric: ${metricId}`);
    if (value === 1) state.speciesEndingTriggerIds.push(species.id);
    return;
  }
  throw new Error(`Campaign ending witness does not support metric: ${condition.metric}`);
}

export function buildEndingWitness(data, endingRule) {
  const state = baseWitness(data);
  for (const condition of endingRule.conditions ?? []) satisfyCondition(data, state, condition);
  return state;
}

function referenceAudit(data) {
  const errors = [];
  const storyNodes = data.campaign?.story_nodes ?? [];
  const storyIds = new Set(storyNodes.map((node) => node.id));
  const roleIds = new Set((data.campaign?.relationship_roles ?? []).map((role) => role.id));
  const speciesIds = new Set((data.campaign?.formal_species ?? []).map((species) => species.id));
  const relicIds = new Set((data.display_relics ?? []).map((relic) => relic.id));
  const relicPoolIds = new Set((data.display_relics ?? []).map((relic) => relic.pool_type ?? relic.pool_id));

  if (storyIds.size !== storyNodes.length) errors.push("Duplicate campaign story node ID");
  if (!storyIds.has("CAMPAIGN_PROLOGUE")) errors.push("Missing CAMPAIGN_PROLOGUE");
  const reachableStoryIds = new Set(["CAMPAIGN_PROLOGUE"]);
  for (const [night, storyId] of Object.entries(data.campaign?.story_after_nights ?? {})) {
    if (!storyIds.has(storyId)) errors.push(`Night ${night} references unknown story ${storyId}`);
    reachableStoryIds.add(storyId);
  }
  for (const story of storyNodes) {
    if (!reachableStoryIds.has(story.id)) errors.push(`Story ${story.id} has no campaign entry point`);
    const action = story.continuation?.action;
    if (!["BEGIN_DAY", "OPEN_UPGRADE", "COMPLETE_RUN"].includes(action)) {
      errors.push(`Story ${story.id} has unsupported continuation ${action}`);
    }
    if (action === "BEGIN_DAY" && !Number.isInteger(story.continuation?.night_index)) {
      errors.push(`Story ${story.id} requires an integer night_index`);
    }
  }
  for (const schedule of data.campaign?.display_relic_offer_schedule ?? []) {
    if (!storyIds.has(schedule.after_story_id)) {
      errors.push(`${schedule.id} references unknown story ${schedule.after_story_id}`);
    }
    for (const poolId of schedule.pool_ids ?? []) {
      if (!relicPoolIds.has(poolId)) errors.push(`${schedule.id} references empty relic pool ${poolId}`);
    }
    const available = (data.display_relics ?? []).filter(
      (relic) => (schedule.pool_ids ?? []).includes(relic.pool_type ?? relic.pool_id),
    ).length;
    if (available < Number(schedule.offer_size ?? 3)) {
      errors.push(`${schedule.id} has ${available} candidates for ${schedule.offer_size ?? 3} slots`);
    }
  }
  if (relicIds.size !== (data.display_relics ?? []).length) errors.push("Duplicate display relic ID");
  for (const route of data.campaign?.ending_preview_routes ?? []) {
    for (const speciesId of Object.keys(route.species_affinity_by_id ?? {})) {
      if (!speciesIds.has(speciesId)) errors.push(`${route.id} references unknown affinity species ${speciesId}`);
    }
    for (const speciesId of route.species_ending_trigger_ids ?? []) {
      if (!speciesIds.has(speciesId)) errors.push(`${route.id} references unknown route species ${speciesId}`);
    }
    if (route.species_ending_commitment_id && !speciesIds.has(route.species_ending_commitment_id)) {
      errors.push(`${route.id} references unknown commitment species ${route.species_ending_commitment_id}`);
    }
    if (route.selected_ending_relationship_role_id && !roleIds.has(route.selected_ending_relationship_role_id)) {
      errors.push(`${route.id} references unknown selected relationship ${route.selected_ending_relationship_role_id}`);
    }
    for (const roleId of Object.keys(route.relationship_progress_by_role ?? {})) {
      if (!roleIds.has(roleId)) errors.push(`${route.id} references unknown relationship progress ${roleId}`);
    }
  }
  for (const ending of data.run_completion?.ending_rules ?? []) {
    if (ending.species_id && !speciesIds.has(ending.species_id)) {
      errors.push(`${ending.id} references unknown species ${ending.species_id}`);
    }
    if (ending.relationship_role_id && !roleIds.has(ending.relationship_role_id)) {
      errors.push(`${ending.id} references unknown relationship role ${ending.relationship_role_id}`);
    }
  }
  return errors;
}

export function auditCampaignReachability(data) {
  if (!data.campaign || data.prototype_mode?.type !== "CAMPAIGN") {
    throw new Error("Campaign reachability audit requires campaign data.");
  }
  const endingRules = data.run_completion?.ending_rules ?? [];
  const endingIds = endingRules.map((ending) => ending.id);
  const duplicateEndingIds = endingIds.filter((id, index) => endingIds.indexOf(id) !== index);
  const witnesses = endingRules.map((ending) => {
    const witness = buildEndingWitness(data, ending);
    const resolved = resolveRunEnding(data, clone(witness));
    return {
      ending_id: ending.id,
      ending_tier: ending.ending_tier,
      resolved_ending_id: resolved.id,
      reachable: resolved.id === ending.id,
      metrics: resolved.metrics,
    };
  });
  const fallbackState = baseWitness(data);
  const fallback = resolveRunEnding(data, fallbackState);
  const referenceErrors = referenceAudit(data);
  return {
    status: duplicateEndingIds.length === 0
      && witnesses.every((entry) => entry.reachable)
      && fallback.id === data.run_completion.fallback_ending.id
      && referenceErrors.length === 0
      ? "PASS"
      : "FAIL",
    ending_rule_count: endingRules.length,
    reachable_ending_count: witnesses.filter((entry) => entry.reachable).length,
    unreachable_ending_ids: witnesses.filter((entry) => !entry.reachable).map((entry) => entry.ending_id),
    duplicate_ending_ids: [...new Set(duplicateEndingIds)],
    fallback_expected_id: data.run_completion.fallback_ending.id,
    fallback_resolved_id: fallback.id,
    reference_errors: referenceErrors,
    witnesses,
  };
}
