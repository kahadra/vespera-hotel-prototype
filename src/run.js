import { campaignOperationId } from "./campaign-progress.js";

export const RUN_RECORD_SCHEMA_VERSION = 6;
export const RUN_RECORD_STORAGE_KEY = "vespera.hotel.run-records.v1";
export const RUN_RECORD_LIMIT = 20;

function sum(results, selector) {
  return results.reduce((total, result) => total + selector(result), 0);
}

function isFormalCampaign(data) {
  return data?.prototype_mode?.type === "FORMAL_CAMPAIGN";
}

function formalOperationDescriptor(config, record) {
  return {
    type: "CAMPAIGN_OPERATION",
    stageNumber: record.resultIdentity.stageNumber,
    operationKind: record.resultIdentity.operationKind,
    templateIndex: record.resultIdentity.templateIndex,
    templatePolicyId: config.scenario_template_policy_id,
    templateProductionReady: config.scenario_templates_production_ready,
  };
}

function formalFinanceLedger(state) {
  return Array.isArray(state.campaignFinance?.ledger)
    ? state.campaignFinance.ledger
    : [];
}

function formalDay56DebtGateEvidence(data, state) {
  const boundaryStageNumber = 56;
  const ledger = formalFinanceLedger(state);
  const boundaryIndex = ledger.findIndex(
    (entry) => entry?.stageNumber === boundaryStageNumber,
  );
  if (boundaryIndex < 0) return null;
  const entry = ledger[boundaryIndex];
  const baseFinance = data.campaign?.formal_finance?.base_year;
  return {
    type: "CAMPAIGN_DEBT_GATE_EVIDENCE",
    gateId: baseFinance?.debt_gate_id ?? null,
    passed: entry.closingDebt === 0,
    boundaryStageNumber,
    financeConfigId: baseFinance?.id ?? null,
    financeConfigVersion: baseFinance?.version ?? null,
    originalPrincipal: Number(state.campaignFinance?.originalPrincipal ?? 0),
    cumulativeRepaymentAtBoundary: Number(entry.cumulativeRepayment ?? 0),
    remainingDebtAtBoundary: Number(entry.closingDebt ?? 0),
    checkpointOutcome: entry.checkpoint?.outcome ?? null,
    ledgerEntryCountAtBoundary: boundaryIndex + 1,
    debtGraceAfterBoundary: false,
  };
}

function formalOperatingFailureEvidence(state) {
  const failure = state.campaignFinance?.operatingFailure;
  if (!failure) return null;
  return {
    ...failure,
    campaignResultIdentity: { ...failure.campaignResultIdentity },
  };
}

function formalRunFields(data, state) {
  if (!isFormalCampaign(data)) return {};
  const config = data.campaign.formal_progress;
  const progress = state.campaignProgress;
  const finance = state.campaignFinance;
  const lastRecord = progress.operationRecords.at(-1);
  return {
    progression_authority: config.id,
    finance_authority: finance?.configId ?? null,
    day_56_debt_gate_evidence: formalDay56DebtGateEvidence(data, state),
    operating_failure_evidence: formalOperatingFailureEvidence(state),
    campaign_stage_limit: progress.stageLimit,
    true_extension_unlocked: progress.trueExtensionUnlocked,
    last_operation_id: lastRecord
      ? campaignOperationId(config, state.runSeed, formalOperationDescriptor(config, lastRecord))
      : null,
  };
}

export function summarizeRun(data, state) {
  const nightResults = state.nightResults.filter(Boolean);
  const isEndless = data.prototype_mode?.type === "ENDLESS";
  const isFormal = isFormalCampaign(data);
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
  if (isFormal) coreMetrics.completed_nights = state.campaignProgress.completedStageCount;
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
    campaign_operating_cash_shortfall: state.campaignFinance?.operatingFailure ? 1 : 0,
  };
  if (isFormal) {
    const finance = state.campaignFinance;
    const financeLedger = formalFinanceLedger(state);
    const debtGateEvidence = formalDay56DebtGateEvidence(data, state);
    const operatingFailure = formalOperatingFailureEvidence(state);
    const baseFinance = data.campaign?.formal_finance?.base_year;
    campaignMetrics.campaign_completed_stages = state.campaignProgress.completedStageCount;
    campaignMetrics.campaign_starting_cash = Number(baseFinance?.starting_cash ?? 0);
    campaignMetrics.campaign_original_principal = Number(finance?.originalPrincipal ?? 0);
    campaignMetrics.campaign_total_income = sum(
      financeLedger,
      (entry) => Number(entry.income ?? 0),
    );
    campaignMetrics.campaign_total_upkeep = sum(
      financeLedger,
      (entry) => Number(entry.upkeep ?? 0),
    );
    campaignMetrics.campaign_total_reactivation_spend = sum(
      financeLedger,
      (entry) => Number(entry.reactivation ?? 0),
    ) + Number(operatingFailure?.reactivation ?? 0);
    campaignMetrics.campaign_total_room_service_spend = sum(
      financeLedger,
      (entry) => Number(entry.roomService ?? 0),
    ) + Number(operatingFailure?.roomService ?? 0);
    campaignMetrics.campaign_total_repayment = sum(
      financeLedger,
      (entry) => Number(entry.manualRepayment ?? 0),
    );
    campaignMetrics.campaign_remaining_debt = Number(finance?.remainingDebt ?? 0);
    campaignMetrics.campaign_day_56_debt_cleared = debtGateEvidence?.passed ? 1 : 0;
    campaignMetrics.campaign_finance_ledger_entries = financeLedger.length;
    campaignMetrics.campaign_operating_failure_stage = Number(
      operatingFailure?.stageNumber ?? 0,
    );
    campaignMetrics.campaign_operating_failure_income = Number(
      operatingFailure?.income ?? 0,
    );
    campaignMetrics.campaign_operating_failure_available_cash = Number(
      operatingFailure?.availableCash ?? 0,
    );
    campaignMetrics.campaign_operating_failure_upkeep = Number(
      operatingFailure?.upkeep ?? 0,
    );
    campaignMetrics.campaign_operating_failure_reactivation = Number(
      operatingFailure?.reactivation ?? 0,
    );
    campaignMetrics.campaign_operating_failure_room_service = Number(
      operatingFailure?.roomService ?? 0,
    );
    campaignMetrics.campaign_operating_failure_outflow = Number(
      operatingFailure?.operatingOutflow ?? 0,
    );
    campaignMetrics.campaign_operating_failure_shortfall = Number(
      operatingFailure?.shortfallAmount ?? 0,
    );
  }
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
    expected_nights: isFormal
      ? state.campaignProgress.stageLimit
      : data.prototype_mode?.total_nights ?? data.scenarios.length,
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
    ...formalRunFields(data, state),
    metrics: ending.metrics,
  };
}

export function readRunRecords(storage = globalThis.localStorage) {
  if (!storage) return [];
  try {
    const parsed = JSON.parse(storage.getItem(RUN_RECORD_STORAGE_KEY) ?? "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((record) => [1, 2, 3, 4, 5, RUN_RECORD_SCHEMA_VERSION].includes(record?.schema_version) && typeof record.record_id === "string")
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
        finance_authority: null,
        day_56_debt_gate_evidence: null,
        operating_failure_evidence: null,
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
    const serialized = JSON.stringify(records);
    storage.setItem(RUN_RECORD_STORAGE_KEY, serialized);
    if (storage.getItem(RUN_RECORD_STORAGE_KEY) !== serialized) {
      throw new Error("Run record could not be read back after writing.");
    }
    return records;
  } catch (cause) {
    const error = new Error("실행 기록을 저장하지 못해 진행 저장을 보존했습니다.", { cause });
    error.code = "RUN_RECORD_WRITE_FAILED";
    throw error;
  }
}
