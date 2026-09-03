const SUPPORTED_AUDIT_POLICY_ID = "PROVISIONAL_REPUTATION_WITH_EMERGENCY_PENALTY";

function finiteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function assertEndless(condition, message) {
  if (!condition) throw new Error(message);
}

function exactKeys(value, expected) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const actual = Object.keys(value).sort();
  const sortedExpected = [...expected].sort();
  return actual.length === sortedExpected.length
    && actual.every((key, index) => key === sortedExpected[index]);
}

function sameValues(actual, expected) {
  return Array.isArray(actual)
    && actual.length === expected.length
    && actual.every((value, index) => value === expected[index]);
}

function validateConfigurationScale(data, config) {
  assertEndless(data.prototype_mode?.type === "ENDLESS", "무한 영업 데이터의 모드 유형이 ENDLESS가 아닙니다.");
  assertEndless(data.prototype_mode?.total_nights === 7, "무한 영업 파생 데이터는 7영업 단위를 사용해야 합니다.");
  assertEndless(config.season_length === 7, "무한 영업 시즌은 7영업이어야 합니다.");
  assertEndless(
    data.prototype_mode?.upgrade_offer_sizes?.EXPANSION === 2,
    "무한 영업 증축 제안은 한 막간에 최대 두 후보를 보여야 합니다.",
  );

  const fixture = config.configuration_fixture;
  assertEndless(
    exactKeys(fixture, [
      "profile_id",
      "zone_id",
      "status",
      "operation_count",
      "starting_active_room_ids",
      "validation_room_ids",
    ]),
    "무한 영업 구성 검증 fixture 필드가 잘못되었습니다.",
  );
  assertEndless(
    fixture.profile_id === "ENDLESS_SPATIAL_CONFIGURATION_FIXTURE_V1",
    "무한 영업 구성 검증 fixture ID가 잘못되었습니다.",
  );
  assertEndless(
    typeof fixture.zone_id === "string"
      && fixture.zone_id.trim().length > 0
      && fixture.zone_id === "ENDLESS_ZONE_GREYBOX_01",
    "무한 영업 구성 검증 구역 ID가 잘못되었습니다.",
  );
  assertEndless(fixture.status === "PROVISIONAL", "무한 영업 구성 검증 fixture는 PROVISIONAL이어야 합니다.");
  assertEndless(fixture.operation_count === 14, "무한 영업 구성 검증 fixture는 14영업을 대상으로 해야 합니다.");
  assertEndless(
    Array.isArray(fixture.starting_active_room_ids)
      && new Set(fixture.starting_active_room_ids).size === fixture.starting_active_room_ids.length,
    "무한 영업 검증 시작 객실 ID가 잘못되었습니다.",
  );
  assertEndless(
    Array.isArray(fixture.validation_room_ids)
      && new Set(fixture.validation_room_ids).size === fixture.validation_room_ids.length,
    "무한 영업 구성 검증 객실 ID가 잘못되었습니다.",
  );
  assertEndless(fixture.starting_active_room_ids.length === 9, "무한 영업 검증 시작 객실 수는 9개여야 합니다.");
  assertEndless(fixture.validation_room_ids.length === 15, "무한 영업 구성 검증 객실 수는 15개여야 합니다.");
  assertEndless(
    fixture.operation_count === config.season_length * 2,
    "무한 영업 구성 검증 기간은 정확히 두 시즌이어야 합니다.",
  );

  assertEndless(Array.isArray(data.rooms), "무한 영업 객실 데이터가 없습니다.");
  assertEndless(Array.isArray(data.upgrades), "무한 영업 개선 데이터가 없습니다.");
  const rooms = Object.fromEntries(data.rooms.map((room) => [room.id, room]));
  const upgrades = Object.fromEntries(data.upgrades.map((upgrade) => [upgrade.id, upgrade]));
  const startingRoomIds = data.rooms
    .filter((room) => room.built_from_start !== false)
    .map((room) => room.id);
  const validationRoomIds = data.rooms.map((room) => room.id);
  const actualRoomIds = new Set(validationRoomIds);
  assertEndless(
    fixture.starting_active_room_ids.every((roomId) => actualRoomIds.has(roomId)),
    "무한 영업 검증 시작 객실에 알 수 없는 ID가 있습니다.",
  );
  assertEndless(
    fixture.validation_room_ids.every((roomId) => actualRoomIds.has(roomId)),
    "무한 영업 검증 객실에 알 수 없는 ID가 있습니다.",
  );
  const fixtureValidationRoomIds = new Set(fixture.validation_room_ids);
  assertEndless(
    fixture.starting_active_room_ids.every((roomId) => fixtureValidationRoomIds.has(roomId)),
    "무한 영업 검증 시작 객실은 검증 객실의 부분집합이어야 합니다.",
  );
  assertEndless(
    sameValues(startingRoomIds, fixture.starting_active_room_ids),
    "실제 시작 객실 집합이 구성 fixture와 다릅니다.",
  );
  assertEndless(
    sameValues(validationRoomIds, fixture.validation_room_ids),
    "실제 검증 보드 객실 집합이 구성 fixture와 다릅니다.",
  );

  const expansionBranches = [
    {
      wing: 3,
      roomSuffix: "D",
      introducedInSaveSchema: null,
      upgrades: [
        { floor: 1, requires: [] },
        { floor: 2, requires: ["EXPAND_F1_D"] },
        { floor: 3, requires: ["EXPAND_F2_D"] },
      ],
    },
    {
      wing: 4,
      roomSuffix: "E",
      introducedInSaveSchema: 8,
      upgrades: [
        { floor: 1, rarity: "N", cost: 26, stage: 2, reputation: 0, requires: [] },
        { floor: 2, rarity: "R", cost: 36, stage: 3, reputation: 4, requires: ["EXPAND_F1_E"] },
        { floor: 3, rarity: "SR", cost: 48, stage: 4, reputation: 8, requires: ["EXPAND_F2_E"] },
      ],
    },
  ];

  const branchUpgradeIds = new Set();
  for (const branch of expansionBranches) {
    for (const expected of branch.upgrades) {
      const roomId = `F${expected.floor}-${branch.roomSuffix}`;
      const upgradeId = `EXPAND_F${expected.floor}_${branch.roomSuffix}`;
      branchUpgradeIds.add(upgradeId);
      const room = rooms[roomId];
      assertEndless(Boolean(room), `무한 영업 증축 객실 ${roomId}가 없습니다.`);
      assertEndless(room.floor === expected.floor && room.wing === branch.wing, `${roomId}의 공간 좌표가 잘못되었습니다.`);
      assertEndless(room.built_from_start === false, `${roomId}는 시작 시 비활성 객실이어야 합니다.`);
      if (branch.introducedInSaveSchema !== null) {
        assertEndless(
          room.introduced_in_save_schema === branch.introducedInSaveSchema,
          `${roomId}의 저장 스키마 도입 버전이 잘못되었습니다.`,
        );
      }

      const upgrade = upgrades[upgradeId];
      assertEndless(Boolean(upgrade), `무한 영업 증축 ${upgradeId}가 없습니다.`);
      assertEndless(upgrade.kind === "EXPANSION", `${upgradeId}는 EXPANSION이어야 합니다.`);
      assertEndless(sameValues(upgrade.room_unlocks, [roomId]), `${upgradeId}의 해금 객실이 잘못되었습니다.`);
      if (expected.rarity !== undefined) {
        assertEndless(upgrade.rarity === expected.rarity, `${upgradeId}의 등급이 잘못되었습니다.`);
        assertEndless(upgrade.cost === expected.cost, `${upgradeId}의 비용이 잘못되었습니다.`);
        assertEndless(upgrade.unlock_stage === expected.stage, `${upgradeId}의 등장 단계가 잘못되었습니다.`);
        assertEndless(
          upgrade.minimum_reputation === expected.reputation,
          `${upgradeId}의 최소 평판이 잘못되었습니다.`,
        );
      }
      assertEndless(sameValues(upgrade.requires, expected.requires), `${upgradeId}의 선행 증축이 잘못되었습니다.`);
    }
  }
  for (const upgradeId of branchUpgradeIds) {
    const suffix = upgradeId.endsWith("_D") ? "_D" : "_E";
    assertEndless(
      (upgrades[upgradeId].requires ?? []).every((requiredId) => requiredId.endsWith(suffix)),
      `${upgradeId}는 다른 증축 가지를 선행조건으로 사용할 수 없습니다.`,
    );
  }
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
  validateConfigurationScale(data, config);
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
  const seasonLength = Number(data.endless?.season_length ?? 7);
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
  const seasonLength = Number(data.endless?.season_length ?? 7);
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
