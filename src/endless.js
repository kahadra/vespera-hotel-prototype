const SUPPORTED_AUDIT_POLICY_ID = "PROVISIONAL_REPUTATION_WITH_EMERGENCY_PENALTY";

function finiteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function round2(value) {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

function auditScoreParts(data, results) {
  const reputationDelta = round2(
    results.reduce((total, result) => total + Number(result.reputationDelta ?? 0), 0),
  );
  const emergencyNights = results.filter((result) => result.emergencyReport?.timedOut).length;
  const emergencyPenalty = round2(
    emergencyNights * Number(data.endless?.audit?.emergency_penalty ?? 0),
  );
  return {
    reputationDelta,
    emergencyNights,
    emergencyPenalty,
    score: round2(reputationDelta - emergencyPenalty),
  };
}

export function validateEndlessData(data) {
  const config = data.endless;
  if (!config || config.status !== "GREYBOX") {
    throw new Error("무한 영업 회색 상자 설정이 없습니다.");
  }
  if (!Number.isInteger(config.season_length) || config.season_length < 1) {
    throw new Error("무한 영업 시즌 길이는 1 이상의 정수여야 합니다.");
  }
  if (
    !Number.isInteger(config.result_history_limit)
    || config.result_history_limit < config.season_length
    || !Number.isInteger(config.audit_history_limit)
    || config.audit_history_limit < 1
  ) {
    throw new Error("무한 영업 이력 보존 상한이 잘못되었습니다.");
  }
  if (!Array.isArray(data.scenarios) || data.scenarios.length < 1) {
    throw new Error("무한 영업에 재사용할 영업 시나리오가 없습니다.");
  }
  const audit = config.audit;
  if (audit?.policy_id !== SUPPORTED_AUDIT_POLICY_ID || audit.provisional !== true) {
    throw new Error("무한 영업 감사 정책은 지원되는 PROVISIONAL 정책이어야 합니다.");
  }
  for (const key of [
    "initial_target",
    "target_step_per_cleared_season",
    "max_target",
    "reachability_gain_per_remaining_operation",
    "emergency_penalty",
  ]) {
    if (!finiteNumber(audit[key])) throw new Error(`무한 영업 감사 ${key} 값이 잘못되었습니다.`);
  }
  if (
    audit.target_step_per_cleared_season < 0
    || audit.max_target < audit.initial_target
    || audit.emergency_penalty < 0
  ) {
    throw new Error("무한 영업 감사 목표 곡선이 잘못되었습니다.");
  }
  if (audit.reachability_gain_per_remaining_operation <= 0) {
    throw new Error("무한 영업 감사 도달 가능성 표본값은 양수여야 합니다.");
  }
  const fame = config.run_fame;
  if (
    fame?.policy_id !== "PROVISIONAL_CLEARED_SEASON_COUNT"
    || fame.provisional !== true
    || !finiteNumber(fame.fame_per_cleared_season)
    || fame.fame_per_cleared_season < 0
  ) {
    throw new Error("무한 영업 런 명성 정책이 잘못되었습니다.");
  }
  const risk = config.risk;
  if (
    risk?.policy_id !== "PROVISIONAL_CLEARED_SEASON_TIER"
    || risk.provisional !== true
    || !Number.isInteger(risk.initial_tier)
    || !Number.isInteger(risk.tier_per_cleared_season)
    || risk.initial_tier < 1
    || risk.tier_per_cleared_season < 0
  ) {
    throw new Error("무한 영업 위험 단계 정책이 잘못되었습니다.");
  }
  return true;
}

export function endlessAuditTarget(data, clearedSeasonCount = 0) {
  const audit = data.endless?.audit ?? {};
  const target = Number(audit.initial_target ?? 0)
    + Number(audit.target_step_per_cleared_season ?? 0) * Math.max(0, clearedSeasonCount);
  return Math.min(Number(audit.max_target ?? target), target);
}

export function endlessRiskTier(data, clearedSeasonCount = 0) {
  const risk = data.endless?.risk ?? {};
  return Number(risk.initial_tier ?? 1)
    + Number(risk.tier_per_cleared_season ?? 0) * Math.max(0, clearedSeasonCount);
}

export function endlessAuditProgress(data, state) {
  const seasonLength = Number(data.endless?.season_length ?? 5);
  const startIndex = Math.max(0, Number(state.endlessSeasonStartResultIndex ?? 0));
  const results = state.nightResults.slice(startIndex, startIndex + seasonLength).filter(Boolean);
  const { score } = auditScoreParts(data, results);
  const target = Number(state.endlessAuditTarget ?? endlessAuditTarget(
    data,
    state.endlessAuditPassedCount ?? 0,
  ));
  const remainingOperations = Math.max(0, seasonLength - results.length);
  const reachabilityGain = Number(
    data.endless?.audit?.reachability_gain_per_remaining_operation ?? 0,
  );
  const projectedCeiling = score + remainingOperations * reachabilityGain;
  return {
    operations: results.length,
    score,
    target,
    remainingOperations,
    projectedCeiling,
    reachable: projectedCeiling >= target,
  };
}

export function calculateEndlessAudit(data, state) {
  const policyId = data.endless?.audit?.policy_id;
  if (policyId !== SUPPORTED_AUDIT_POLICY_ID) {
    throw new Error(`지원하지 않는 무한 영업 감사 정책입니다: ${policyId ?? "UNKNOWN"}`);
  }
  const seasonLength = Number(data.endless?.season_length ?? 5);
  const startIndex = Math.max(0, Number(state.endlessSeasonStartResultIndex ?? 0));
  const results = state.nightResults.slice(startIndex, startIndex + seasonLength).filter(Boolean);
  const scoreParts = auditScoreParts(data, results);
  const { score } = scoreParts;
  const target = Number(state.endlessAuditTarget ?? endlessAuditTarget(
    data,
    state.endlessAuditPassedCount ?? 0,
  ));
  const evidence = results.map((result, index) => ({
    operationNumber: index + 1,
    scenarioId: data.scenarios[index % data.scenarios.length]?.id ?? null,
    reputationDelta: round2(Number(result.reputationDelta ?? 0)),
    emergencyPenalty: result.emergencyReport?.timedOut
      ? Number(data.endless?.audit?.emergency_penalty ?? 0)
      : 0,
    acceptedGuests: result.acceptedGuestIds?.length ?? 0,
    rejectedGuests: result.rejectedGuestIds?.length ?? 0,
    canceledGuests: result.canceledGuestIds?.length ?? 0,
    emergency: Boolean(result.emergencyReport?.timedOut),
  }));
  return {
    auditId: `${data.endless?.id ?? "ENDLESS"}:S${Number(state.endlessSeasonIndex ?? 0) + 1}`,
    policyId,
    provisional: data.endless?.audit?.provisional === true,
    seasonNumber: Number(state.endlessSeasonIndex ?? 0) + 1,
    riskTier: Number(state.endlessRiskTier ?? endlessRiskTier(
      data,
      state.endlessAuditPassedCount ?? 0,
    )),
    operations: results.length,
    score,
    target,
    margin: round2(score - target),
    passed: results.length === seasonLength && score >= target,
    reputationDelta: scoreParts.reputationDelta,
    emergencyPenalty: scoreParts.emergencyPenalty,
    acceptedGuests: results.reduce((total, result) => total + (result.acceptedGuestIds?.length ?? 0), 0),
    rejectedGuests: results.reduce((total, result) => total + (result.rejectedGuestIds?.length ?? 0), 0),
    canceledGuests: results.reduce((total, result) => total + (result.canceledGuestIds?.length ?? 0), 0),
    emergencyNights: scoreParts.emergencyNights,
    evidence,
  };
}
