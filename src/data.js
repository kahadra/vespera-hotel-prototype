const DATA_URL = "./data/prototype_v1.json";

export async function loadGameData() {
  const response = await fetch(DATA_URL, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`데이터를 불러오지 못했습니다: ${DATA_URL} (${response.status})`);
  }
  const data = await response.json();
  const indexes = createIndexes(data);
  validateData(data, indexes);
  return { ...data, indexes };
}

export function createIndexes(data) {
  const byId = (items) => Object.fromEntries(items.map((item) => [item.id, item]));
  const facilities = byId(data.facilities);
  const upgrades = Object.fromEntries(
    data.upgrades.map((upgrade) => {
      const facility = upgrade.facility_id ? facilities[upgrade.facility_id] : null;
      return [
        upgrade.id,
        {
          ...(facility ?? {}),
          ...upgrade,
          id: upgrade.id,
        },
      ];
    }),
  );
  return {
    rooms: byId(data.rooms),
    species: byId(data.species),
    ranks: byId(data.ranks),
    guests: byId(data.guests),
    facilities,
    upgrades,
    scenarios: byId(data.scenarios),
  };
}

function assertUnique(items, label) {
  const ids = items.map((item) => item.id);
  if (new Set(ids).size !== ids.length) {
    throw new Error(`${label} 데이터에 중복 ID가 있습니다.`);
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function assertReferences(ids, index, owner, label) {
  for (const id of ids) {
    if (!index[id]) throw new Error(`${owner}가 존재하지 않는 ${label} ${id}을 참조합니다.`);
  }
}

function validateUpgradeGraph(data, indexes) {
  const visiting = new Set();
  const visited = new Set();

  function visit(upgradeId) {
    if (visited.has(upgradeId)) return;
    if (visiting.has(upgradeId)) throw new Error(`개선 선행조건에 순환이 있습니다: ${upgradeId}`);
    visiting.add(upgradeId);
    for (const requiredId of indexes.upgrades[upgradeId].requires ?? []) visit(requiredId);
    visiting.delete(upgradeId);
    visited.add(upgradeId);
  }

  for (const upgrade of data.upgrades) visit(upgrade.id);
}

function validateHiddenPreference(rule, owner, indexes, seenIds) {
  const supportedTypes = new Set([
    "ROOM_HAS",
    "ROOM_NOT_HAS",
    "FLOOR_IS",
    "FLOOR_AT_LEAST",
    "FLOOR_AT_MOST",
    "ELEVATOR_DISTANCE_AT_LEAST",
    "ELEVATOR_DISTANCE_AT_MOST",
    "ADJACENT_GUEST",
    "NO_OCCUPIED_ADJACENT",
    "ADJACENT_SPECIES",
    "SAME_FLOOR_SPECIES",
    "NEAR_FACILITY",
  ]);
  assert(typeof rule.id === "string" && rule.id.length > 0, `${owner}의 숨은 선호에 ID가 없습니다.`);
  assert(!seenIds.has(rule.id), `숨은 선호 ID가 중복되었습니다: ${rule.id}`);
  seenIds.add(rule.id);
  assert(supportedTypes.has(rule.type), `${owner}의 숨은 선호 ${rule.id}에 지원하지 않는 규칙 ${rule.type}이 있습니다.`);
  assert(Number.isFinite(rule.points) && rule.points > 0, `${owner}의 숨은 선호 ${rule.id}는 양의 점수여야 합니다.`);
  assert(typeof rule.label === "string" && rule.label.length > 0, `${owner}의 숨은 선호 ${rule.id}에 설명이 없습니다.`);
  assert(rule.required !== true && rule.hard !== true && rule.kind !== "HARD", `${owner}의 숨은 선호는 필수 조건이 될 수 없습니다.`);

  if (["ROOM_HAS", "ROOM_NOT_HAS"].includes(rule.type)) {
    assert(typeof rule.attribute === "string" && rule.attribute.length > 0, `${rule.id}에 객실 속성이 필요합니다.`);
  } else if (["FLOOR_IS", "FLOOR_AT_LEAST", "FLOOR_AT_MOST"].includes(rule.type)) {
    assert(Number.isInteger(rule.floor), `${rule.id}에 층 정보가 필요합니다.`);
  } else if (["ELEVATOR_DISTANCE_AT_LEAST", "ELEVATOR_DISTANCE_AT_MOST"].includes(rule.type)) {
    assert(Number.isInteger(rule.distance) && rule.distance >= 0, `${rule.id}에 거리 정보가 필요합니다.`);
  } else if (rule.type === "ADJACENT_GUEST") {
    assertReferences([rule.guest_id], indexes.guests, rule.id, "손님");
  } else if (["ADJACENT_SPECIES", "SAME_FLOOR_SPECIES"].includes(rule.type)) {
    assertReferences([rule.species_id], indexes.species, rule.id, "종족");
  } else if (rule.type === "NEAR_FACILITY") {
    assertReferences([rule.facility_id], indexes.facilities, rule.id, "시설");
  }
}

export function validateData(data, indexes = createIndexes(data)) {
  const rankIds = ["N", "R", "SR", "SSR"];
  const expectedRanks = new Set(rankIds);
  assert(data.prototype_mode?.type === "SHOWCASE", "프로토타입 모드는 SHOWCASE여야 합니다.");
  assert(data.prototype_mode?.total_nights === 5, "쇼케이스는 정확히 5회 영업이어야 합니다.");
  assert(data.prototype_mode?.accelerated === true, "쇼케이스의 압축 성장 표시가 필요합니다.");
  assert(Boolean(data.prototype_mode?.notice), "쇼케이스 안내 문구가 필요합니다.");
  assert(data.prototype_mode?.upgrade_offer_sizes?.EXPANSION === 1, "영업 준비에는 증축 제안 1개가 필요합니다.");
  assert(data.prototype_mode?.upgrade_offer_sizes?.FACILITY >= 2, "영업 준비에는 시설·인테리어 제안이 최소 2개 필요합니다.");
  assert(data.stayover_rules?.locks_initial_room === true, "연박 손님은 첫 배정 객실을 유지해야 합니다.");
  assert(Number.isFinite(data.balance?.room_service_cost) && data.balance.room_service_cost >= 0, "객실 정비 비용이 잘못되었습니다.");
  assert(Number.isFinite(data.balance?.minimum_cleanliness), "최소 청결 기준이 필요합니다.");
  assert(Number.isFinite(data.balance?.minimum_durability), "최소 내구 기준이 필요합니다.");
  assert(data.balance?.booking_capacity_per_expansion_room === 1, "증축 객실당 응대 한도는 1명씩 늘어야 합니다.");

  [
    [data.rooms, "객실"],
    [data.species, "종족"],
    [data.ranks, "등급"],
    [data.guests, "손님"],
    [data.facilities, "시설"],
    [data.upgrades, "개선"],
    [data.scenarios, "영업"],
  ].forEach(([items, label]) => assertUnique(items, label));

  assert(data.species.length === 4, "쇼케이스에는 정확히 4개 종족이 필요합니다.");
  assert(data.guests.length >= 12, "쇼케이스에는 손님이 최소 12명 필요합니다.");
  assert(data.upgrades.length >= 8, "쇼케이스에는 시설·증축 개선이 최소 8개 필요합니다.");
  assert(Array.isArray(data.prototype_mode.tutorial_guest_ids) && data.prototype_mode.tutorial_guest_ids.length === 2, "튜토리얼 손님은 두 명이어야 합니다.");
  assertReferences(data.prototype_mode.tutorial_guest_ids, indexes.guests, "튜토리얼", "손님");
  assert(
    data.ranks.length === 4 && data.ranks.every((rank) => expectedRanks.has(rank.id)),
    "등급은 N, R, SR, SSR 네 종류만 사용할 수 있습니다.",
  );

  const orderedRanks = [...data.ranks].sort((left, right) => left.order - right.order);
  orderedRanks.forEach((rank, index) => {
    assert(rank.id === rankIds[index], `등급 순서가 올바르지 않습니다: ${rank.id}`);
    assert(Number.isInteger(rank.unlock_stage) && rank.unlock_stage >= 1 && rank.unlock_stage <= 5, `${rank.id} unlock_stage가 잘못되었습니다.`);
    assert(Number.isInteger(rank.min_reputation) && rank.min_reputation >= 0, `${rank.id} min_reputation이 잘못되었습니다.`);
    assert(Boolean(rank.symbol), `${rank.id} 등급 기호가 없습니다.`);
    assert(/^#[0-9a-f]{6}$/i.test(rank.color), `${rank.id} 등급 색상이 잘못되었습니다.`);
    if (index > 0) {
      assert(rank.unlock_stage >= orderedRanks[index - 1].unlock_stage, "상위 등급의 단계 잠금이 하위 등급보다 빨라서는 안 됩니다.");
      assert(rank.min_reputation >= orderedRanks[index - 1].min_reputation, "상위 등급의 평판 조건이 하위 등급보다 낮아서는 안 됩니다.");
    }
  });

  assert(Array.isArray(data.rank_odds) && data.rank_odds.length > 0, "평판별 등장 확률표가 필요합니다.");
  let previousThreshold = -1;
  for (const row of data.rank_odds) {
    assert(Number.isInteger(row.min_reputation) && row.min_reputation > previousThreshold, "등장 확률표의 평판 구간은 오름차순이어야 합니다.");
    previousThreshold = row.min_reputation;
    assert(Object.keys(row.odds).length === 4 && rankIds.every((rankId) => rankId in row.odds), "등장 확률표에는 네 등급이 모두 있어야 합니다.");
    const total = rankIds.reduce((sum, rankId) => {
      const value = row.odds[rankId];
      assert(Number.isFinite(value) && value >= 0, `${row.min_reputation} 평판의 ${rankId} 확률이 잘못되었습니다.`);
      return sum + value;
    }, 0);
    assert(total === 100, `${row.min_reputation} 평판의 등급 확률 합은 100이어야 합니다.`);
  }

  const hiddenPreferenceIds = new Set();
  for (const species of data.species) {
    assert(Boolean(species.icon), `${species.id}의 아이콘이 없습니다.`);
    assert(Array.isArray(species.synergy_thresholds) && species.synergy_thresholds.length > 0, `${species.id}의 종족 시너지가 없습니다.`);
    let previousCount = 1;
    for (const threshold of species.synergy_thresholds) {
      assert(Number.isInteger(threshold.count) && threshold.count > previousCount, `${species.id}의 시너지 인원 구간이 잘못되었습니다.`);
      assert(Number.isFinite(threshold.points) && threshold.points > 0, `${species.id}의 시너지 점수가 잘못되었습니다.`);
      previousCount = threshold.count;
    }
    const forbiddenHiddenFields = Object.keys(species).filter(
      (field) => field.startsWith("hidden_") && field !== "hidden_preferences_by_rank",
    );
    assert(forbiddenHiddenFields.length === 0, `${species.id}에 필수 또는 비선호 형태의 숨은 데이터가 있습니다: ${forbiddenHiddenFields.join(", ")}`);
    const hiddenByRank = species.hidden_preferences_by_rank;
    assert(hiddenByRank && typeof hiddenByRank === "object", `${species.id}의 종족·등급별 숨은 선호가 없습니다.`);
    assert(Object.keys(hiddenByRank).length === 4 && rankIds.every((rankId) => rankId in hiddenByRank), `${species.id}의 숨은 선호에는 N, R, SR, SSR 키가 모두 필요합니다.`);
    for (const rankId of rankIds) {
      const hiddenPreferences = hiddenByRank[rankId];
      assert(Array.isArray(hiddenPreferences), `${species.id}:${rankId} 숨은 선호는 배열이어야 합니다.`);
      if (rankId === "N") assert(hiddenPreferences.length === 0, `${species.id}:N에는 숨은 선호를 두지 않습니다.`);
      else assert(hiddenPreferences.length > 0, `${species.id}:${rankId}에는 숨은 선호가 필요합니다.`);
      for (const rule of hiddenPreferences) {
        validateHiddenPreference(rule, `${species.id}:${rankId}`, indexes, hiddenPreferenceIds);
      }
    }
  }

  for (const conflict of data.species_conflicts ?? []) {
    assert(conflict.species?.length === 2, "종족 상극은 두 종족을 참조해야 합니다.");
    assertReferences(conflict.species, indexes.species, conflict.label ?? "종족 상극", "종족");
    assert(Number.isFinite(conflict.points) && conflict.points < 0, `${conflict.label}의 상극 점수는 음수여야 합니다.`);
  }

  for (const guest of data.guests) {
    if (!indexes.species[guest.species]) {
      throw new Error(`${guest.id}의 종족 ${guest.species}이 존재하지 않습니다.`);
    }
    if (!indexes.ranks[guest.rank]) {
      throw new Error(`${guest.id}의 등급 ${guest.rank}이 존재하지 않습니다.`);
    }
    if (Math.abs(guest.cancel_reputation) <= Math.abs(guest.reject_reputation)) {
      throw new Error(`${guest.id}의 막판 취소 손실은 거절 손실보다 커야 합니다.`);
    }
    assert(Number.isInteger(guest.stay_nights) && guest.stay_nights >= 1, `${guest.id}의 stay_nights가 잘못되었습니다.`);
    assert(guest.stayover_locks_initial_room === true, `${guest.id}는 연박 시 첫 객실을 유지해야 합니다.`);
    for (const field of ["cleanliness_impact", "durability_impact"]) {
      assert(Number.isInteger(guest[field]) && guest[field] >= 0, `${guest.id}의 ${field}가 잘못되었습니다.`);
    }
    for (const rule of [...guest.hard_constraints, ...guest.soft_preferences]) {
      if (rule.guest_id) assertReferences([rule.guest_id], indexes.guests, guest.id, "손님");
      if (rule.facility_id) assertReferences([rule.facility_id], indexes.facilities, guest.id, "시설");
    }
    const hiddenFields = Object.keys(guest).filter((field) => field.startsWith("hidden_"));
    assert(hiddenFields.length === 0, `${guest.id}에는 개인 숨은 규칙을 둘 수 없습니다: ${hiddenFields.join(", ")}`);
  }

  for (const facility of data.facilities) {
    assert(expectedRanks.has(facility.rarity), `${facility.id}의 시설 등급이 잘못되었습니다.`);
    assert(facility.stackable === true, `${facility.id}는 다른 시설과 함께 보유 가능해야 합니다.`);
    assertReferences(facility.blocked_rooms ?? [], indexes.rooms, facility.id, "객실");
    assertReferences((facility.room_attribute_changes ?? []).map((change) => change.room_id), indexes.rooms, facility.id, "객실");
    assertReferences((facility.room_bonuses ?? []).map((bonus) => bonus.room_id), indexes.rooms, facility.id, "객실");
    for (const link of facility.adjacency_links ?? []) {
      assert(link.length === 2, `${facility.id}의 이웃 연결은 객실 두 개여야 합니다.`);
      assertReferences(link, indexes.rooms, facility.id, "객실");
    }
  }

  const upgradeRarities = new Set();
  const roomUnlockOwner = {};
  for (const upgrade of data.upgrades) {
    upgradeRarities.add(upgrade.rarity);
    assert(expectedRanks.has(upgrade.rarity), `${upgrade.id}의 개선 등급이 잘못되었습니다.`);
    assert(["FACILITY", "EXPANSION"].includes(upgrade.kind), `${upgrade.id}의 개선 종류가 잘못되었습니다.`);
    assert(Number.isFinite(upgrade.cost) && upgrade.cost >= 0, `${upgrade.id}의 비용이 잘못되었습니다.`);
    assert(Number.isInteger(upgrade.unlock_stage) && upgrade.unlock_stage >= 2 && upgrade.unlock_stage <= 5, `${upgrade.id}의 등장 단계가 잘못되었습니다.`);
    assert(Number.isInteger(upgrade.minimum_reputation) && upgrade.minimum_reputation >= 0, `${upgrade.id}의 평판 조건이 잘못되었습니다.`);
    assert(upgrade.unlock_stage >= indexes.ranks[upgrade.rarity].unlock_stage, `${upgrade.id}가 등급 단계보다 일찍 등장합니다.`);
    assert(upgrade.minimum_reputation >= indexes.ranks[upgrade.rarity].min_reputation, `${upgrade.id}가 등급 평판 조건보다 일찍 등장합니다.`);
    assertReferences(upgrade.requires ?? [], indexes.upgrades, upgrade.id, "선행 개선");
    if (upgrade.kind === "FACILITY") {
      assertReferences([upgrade.facility_id], indexes.facilities, upgrade.id, "시설");
      assert(upgrade.stackable === true, `${upgrade.id} 시설 개선은 누적 보유 가능해야 합니다.`);
    } else {
      assert(Array.isArray(upgrade.room_unlocks) && upgrade.room_unlocks.length > 0, `${upgrade.id}의 증축 객실이 없습니다.`);
      assertReferences(upgrade.room_unlocks, indexes.rooms, upgrade.id, "객실");
      for (const roomId of upgrade.room_unlocks) {
        assert(!roomUnlockOwner[roomId], `${roomId}를 두 개선이 동시에 해금합니다.`);
        assert(indexes.rooms[roomId].built_from_start === false, `${upgrade.id}는 이미 건설된 객실을 해금할 수 없습니다.`);
        roomUnlockOwner[roomId] = upgrade.id;
      }
    }
  }
  assert(rankIds.every((rankId) => upgradeRarities.has(rankId)), "개선 제안에는 N, R, SR, SSR 등급이 모두 있어야 합니다.");
  validateUpgradeGraph(data, indexes);

  const f1Expansion = roomUnlockOwner["F1-D"];
  const f2Expansion = roomUnlockOwner["F2-D"];
  const f3Expansion = roomUnlockOwner["F3-D"];
  assert(Boolean(f1Expansion && f2Expansion && f3Expansion), "F1-D, F2-D, F3-D 증축이 모두 필요합니다.");
  assert(indexes.upgrades[f2Expansion].requires.includes(f1Expansion), "F2-D 증축은 F1-D 증축을 선행조건으로 가져야 합니다.");
  assert(indexes.upgrades[f3Expansion].requires.includes(f2Expansion), "F3-D 증축은 F2-D 증축을 선행조건으로 가져야 합니다.");

  assert(data.scenarios.length === 5, "쇼케이스에는 정확히 5개 영업 시나리오가 필요합니다.");
  const stages = [...data.scenarios].map((scenario) => scenario.stage).sort((left, right) => left - right);
  assert(stages.every((stage, index) => stage === index + 1), "영업 단계는 1부터 5까지 한 번씩 있어야 합니다.");
  for (const scenario of data.scenarios) {
    const allGuestReferences = [
      ...scenario.fixed_guests,
      ...(scenario.applicants ?? []),
      ...(scenario.applicant_pool ?? []),
      ...(scenario.special_invite_guest_ids ?? []),
    ];
    assertReferences(allGuestReferences, indexes.guests, scenario.id, "손님");
    assertReferences((scenario.facility_options ?? []).filter(Boolean), indexes.facilities, scenario.id, "시설");
    assert(Number.isInteger(scenario.capacity) && scenario.capacity > 0, `${scenario.id}의 기본 예약 응대 한도가 잘못되었습니다.`);
    assert(Number.isInteger(scenario.offer_size) && scenario.offer_size >= 0, `${scenario.id}의 제안 인원이 잘못되었습니다.`);
    for (const guestId of scenario.applicant_pool ?? []) {
      const rank = indexes.ranks[indexes.guests[guestId].rank];
      assert(rank.unlock_stage <= scenario.stage, `${scenario.id} 후보 ${guestId}의 등급이 단계보다 먼저 등장합니다.`);
    }
    if (scenario.guaranteed_rank) {
      assert(expectedRanks.has(scenario.guaranteed_rank), `${scenario.id}의 보장 등급이 잘못되었습니다.`);
      assert(indexes.ranks[scenario.guaranteed_rank].unlock_stage <= scenario.stage, `${scenario.id}의 보장 등급이 단계 잠금을 위반합니다.`);
    }
  }

  const firstScenario = data.scenarios.find((scenario) => scenario.stage === 1);
  assert(firstScenario.fixed_guests.every((guestId) => indexes.guests[guestId].rank === "N"), "첫 영업의 고정 손님은 모두 N 등급이어야 합니다.");
  const secondScenario = data.scenarios.find((scenario) => scenario.stage === 2);
  assert(secondScenario.guaranteed_rank === "R", "두 번째 영업은 R 손님을 보장해야 합니다.");
  const srScenario = data.scenarios.find((scenario) => [3, 4].includes(scenario.stage) && scenario.guaranteed_rank === "SR");
  assert(Boolean(srScenario), "세 번째 또는 네 번째 영업은 SR 손님을 보장해야 합니다.");
  const fifthScenario = data.scenarios.find((scenario) => scenario.stage === 5);
  assert(fifthScenario.guaranteed_rank === "SSR", "다섯 번째 영업은 SSR 손님을 보장해야 합니다.");
  assert(fifthScenario.special_invite_showcase_only === true, "다섯 번째 SSR은 쇼케이스 전용 초청이어야 합니다.");
  assert((fifthScenario.special_invite_guest_ids ?? []).length > 0, "다섯 번째 영업의 특별 초청 손님이 없습니다.");
  for (const guestId of fifthScenario.special_invite_guest_ids) {
    const guest = indexes.guests[guestId];
    assert(guest.rank === "SSR" && guest.showcase_only === true, `${guestId}는 쇼케이스 전용 SSR이어야 합니다.`);
  }
}

export function getGuestRules(data, guestId) {
  const guest = data.indexes.guests[guestId];
  const species = data.indexes.species[guest.species];
  const rank = data.indexes.ranks[guest.rank];
  const commonRequired = [...species.hard_constraints];
  const rankRequired = [...rank.hard_constraints];
  const personalRequired = [...guest.hard_constraints];
  const commonPreferences = [...species.soft_preferences];
  const rankPreferences = [...rank.soft_preferences];
  const personalPreferences = [...guest.soft_preferences];
  const hiddenPreferences = [...(species.hidden_preferences_by_rank?.[guest.rank] ?? [])];
  return {
    commonRequired,
    rankRequired,
    personalRequired,
    commonPreferences,
    rankPreferences,
    personalPreferences,
    hiddenPreferences,
    hard: [...commonRequired, ...rankRequired, ...personalRequired],
    soft: [...commonPreferences, ...rankPreferences, ...personalPreferences],
  };
}
