import { getGuestRules } from "./data.js";

const ATTRIBUTE_LABELS = {
  noisy: "시끄러운",
  quiet: "조용한",
  sunny: "햇빛",
  dark: "암막",
  spacious: "넓은",
};

function pairKey(left, right) {
  return [left, right].sort().join("|");
}

function normalizeHotelContext(context = {}) {
  if (typeof context === "string") return { ownedFacilityIds: [context] };
  if (Array.isArray(context)) return { ownedFacilityIds: context };
  return context ?? {};
}

export function createBoardState(data, sourceContext = {}) {
  const context = normalizeHotelContext(sourceContext);
  const ownedFacilityIds = [...new Set(context.ownedFacilityIds ?? [])];
  const facilityIndex = data.indexes.upgrades ?? data.indexes.facilities ?? {};
  const facilities = ownedFacilityIds
    .map((id) => facilityIndex[id])
    .filter(Boolean);
  const rooms = Object.fromEntries(
    data.rooms.map((room) => [
      room.id,
      { ...room, attributes: new Set(room.attributes ?? []) },
    ]),
  );
  const unlockedRooms = new Set(
    data.rooms.filter((room) => room.built_from_start !== false).map((room) => room.id),
  );
  const blockedRooms = new Set();
  const blockedReasons = new Map();
  const extraLinks = new Set();
  const roomBonuses = [];

  for (const facility of facilities) {
    for (const roomId of facility.room_unlocks ?? []) unlockedRooms.add(roomId);
    for (const change of facility.room_attribute_changes ?? []) {
      const room = rooms[change.room_id];
      if (!room) continue;
      for (const value of change.remove ?? []) room.attributes.delete(value);
      for (const value of change.add ?? []) room.attributes.add(value);
    }
    for (const [left, right] of facility.adjacency_links ?? []) {
      extraLinks.add(pairKey(left, right));
    }
    for (const bonus of facility.room_bonuses ?? []) {
      roomBonuses.push({ ...bonus, facility_id: facility.id });
    }
  }

  for (const room of data.rooms) {
    if (!unlockedRooms.has(room.id)) {
      blockedRooms.add(room.id);
      blockedReasons.set(room.id, "미증축 객실");
    }
  }

  for (const facility of facilities) {
    for (const roomId of facility.blocked_rooms ?? []) {
      blockedRooms.add(roomId);
      blockedReasons.set(roomId, `${facility.name} 사용 중`);
    }
  }

  const minimumCleanliness = data.balance?.minimum_cleanliness ?? 40;
  const minimumDurability = data.balance?.minimum_durability ?? 35;
  const protectedRoomIds = new Set(context.protectedRoomIds ?? []);
  for (const [roomId, condition] of Object.entries(context.roomConditions ?? {})) {
    if (!rooms[roomId]) continue;
    if (protectedRoomIds.has(roomId)) continue;
    if ((condition.cleanliness ?? 100) < minimumCleanliness) {
      blockedRooms.add(roomId);
      blockedReasons.set(roomId, "청소 필요");
    } else if ((condition.durability ?? 100) < minimumDurability) {
      blockedRooms.add(roomId);
      blockedReasons.set(roomId, "수리 필요");
    }
  }

  return {
    rooms,
    blockedRooms,
    blockedReasons,
    extraLinks,
    facilities,
    facilityIds: ownedFacilityIds,
    roomBonuses,
    unlockedRooms,
    roomConditions: context.roomConditions ?? {},
  };
}

export function areAdjacent(leftId, rightId, board) {
  if (!leftId || !rightId || leftId === rightId) return false;
  if (board.extraLinks.has(pairKey(leftId, rightId))) return true;
  const left = board.rooms[leftId];
  const right = board.rooms[rightId];
  if (!left || !right) return false;
  return left.floor === right.floor && Math.abs(left.wing - right.wing) === 1;
}

function hardViolation(rule, guestId, placements, data, board) {
  const guest = data.indexes.guests[guestId];
  const roomId = placements[guestId];
  const room = board.rooms[roomId];

  if (rule.type === "ROOM_NOT_HAS") {
    if (!room.attributes.has(rule.attribute)) return null;
    return {
      guestId,
      ruleType: rule.type,
      relatedIds: [roomId],
      message: `${guest.name}는 ${ATTRIBUTE_LABELS[rule.attribute] ?? rule.attribute} 객실에 머물 수 없습니다.`,
    };
  }

  if (rule.type === "ROOM_HAS") {
    if (room.attributes.has(rule.attribute)) return null;
    return {
      guestId,
      ruleType: rule.type,
      relatedIds: [roomId],
      message: `${guest.name}에게 ${ATTRIBUTE_LABELS[rule.attribute] ?? rule.attribute} 객실이 필요합니다.`,
    };
  }

  if (rule.type === "FLOOR_IS" || rule.type === "FLOOR_AT_LEAST" || rule.type === "FLOOR_AT_MOST") {
    const matched = rule.type === "FLOOR_IS"
      ? room.floor === rule.floor
      : rule.type === "FLOOR_AT_LEAST"
        ? room.floor >= rule.floor
        : room.floor <= rule.floor;
    if (matched) return null;
    return {
      guestId,
      ruleType: rule.type,
      relatedIds: [roomId],
      message: `${guest.name}의 등급 또는 종족에 맞는 층을 배정해야 합니다.`,
    };
  }

  if (rule.type === "ELEVATOR_DISTANCE_AT_LEAST" || rule.type === "ELEVATOR_DISTANCE_AT_MOST") {
    const matched = rule.type === "ELEVATOR_DISTANCE_AT_LEAST"
      ? room.wing >= rule.distance
      : room.wing <= rule.distance;
    if (matched) return null;
    return {
      guestId,
      ruleType: rule.type,
      relatedIds: [roomId],
      message: `${guest.name}의 등급에 맞는 엘리베이터 동선을 확보해야 합니다.`,
    };
  }

  if (rule.type === "MUST_ADJACENT_GUEST") {
    const other = data.indexes.guests[rule.guest_id];
    if (placements[rule.guest_id] && areAdjacent(roomId, placements[rule.guest_id], board)) return null;
    return {
      guestId,
      ruleType: rule.type,
      relatedIds: [rule.guest_id],
      message: `${guest.name}은 ${other?.name ?? "지정 손님"}의 옆방에 있어야 합니다.`,
    };
  }

  if (rule.type === "NO_OCCUPIED_ADJACENT") {
    const neighbors = Object.entries(placements)
      .filter(([otherId, otherRoom]) => otherId !== guestId && areAdjacent(roomId, otherRoom, board))
      .map(([otherId]) => otherId);
    if (!neighbors.length) return null;
    const names = neighbors.map((id) => data.indexes.guests[id]?.name ?? id).join(", ");
    return {
      guestId,
      ruleType: rule.type,
      relatedIds: neighbors,
      message: `${guest.name}의 옆방은 비어 있어야 합니다. 현재 이웃: ${names}.`,
    };
  }

  if (rule.type === "MUST_SHARE_FLOOR") {
    const sameFloor = Object.entries(placements).some(
      ([otherId, otherRoom]) =>
        otherId !== guestId && board.rooms[otherRoom]?.floor === room.floor,
    );
    if (sameFloor) return null;
    return {
      guestId,
      ruleType: rule.type,
      relatedIds: [roomId],
      message: `${guest.name}은 같은 층에 다른 손님이 있어야 합니다.`,
    };
  }

  throw new Error(`알 수 없는 필수 조건 규칙: ${rule.type}`);
}

function preferenceMatched(rule, guestId, placements, data, board) {
  const roomId = placements[guestId];
  const room = board.rooms[roomId];

  if (rule.type === "ROOM_HAS") return room.attributes.has(rule.attribute);
  if (rule.type === "ROOM_NOT_HAS") return !room.attributes.has(rule.attribute);
  if (rule.type === "FLOOR_IS") return room.floor === rule.floor;
  if (rule.type === "FLOOR_AT_LEAST") return room.floor >= rule.floor;
  if (rule.type === "FLOOR_AT_MOST") return room.floor <= rule.floor;
  if (rule.type === "ELEVATOR_DISTANCE_AT_LEAST") return room.wing >= rule.distance;
  if (rule.type === "ELEVATOR_DISTANCE_AT_MOST") return room.wing <= rule.distance;
  if (rule.type === "ADJACENT_GUEST") {
    return Boolean(placements[rule.guest_id] && areAdjacent(roomId, placements[rule.guest_id], board));
  }
  if (rule.type === "NO_OCCUPIED_ADJACENT") {
    return !Object.entries(placements).some(([otherId, otherRoom]) =>
      otherId !== guestId && areAdjacent(roomId, otherRoom, board));
  }
  if (rule.type === "ADJACENT_SPECIES") {
    return Object.entries(placements).some(([otherId, otherRoom]) =>
      otherId !== guestId
      && data.indexes.guests[otherId]?.species === rule.species_id
      && areAdjacent(roomId, otherRoom, board));
  }
  if (rule.type === "SAME_FLOOR_SPECIES") {
    return Object.entries(placements).some(([otherId, otherRoom]) =>
      otherId !== guestId
      && data.indexes.guests[otherId]?.species === rule.species_id
      && board.rooms[otherRoom]?.floor === room.floor);
  }
  if (rule.type === "NEAR_FACILITY") {
    const facility = board.facilities.find((item) => item.id === rule.facility_id);
    if (!facility) return false;
    const anchors = [...new Set([
      ...(facility.blocked_rooms ?? []),
      ...(facility.anchor_rooms ?? []),
      ...(facility.room_bonuses ?? []).map((bonus) => bonus.room_id),
      ...(facility.adjacency_links ?? []).flat(),
    ])];
    return anchors.some((facilityRoom) => areAdjacent(roomId, facilityRoom, board));
  }
  throw new Error(`알 수 없는 선호 사항 규칙: ${rule.type}`);
}

function addScoreItem(guestScores, guestId, item) {
  if (!guestScores[guestId]) guestScores[guestId] = { total: 0, items: [] };
  guestScores[guestId].items.push(item);
  guestScores[guestId].total += item.points;
}

export function revisitBonusFor(data, history) {
  if (!history?.visits) return 0;
  const thresholds = data.balance?.revisit_bonus_thresholds ?? [
    { min_satisfaction: 0, points: 1 },
    { min_satisfaction: 5, points: 2 },
    { min_satisfaction: 10, points: 3 },
  ];
  const matched = [...thresholds]
    .filter((entry) => history.lastSatisfaction >= entry.min_satisfaction)
    .sort((a, b) => b.min_satisfaction - a.min_satisfaction)[0];
  return matched?.points ?? 0;
}

function applySpeciesEffects(data, acceptedGuestIds, placements, board, guestScores) {
  const groupEffects = [];
  const placedIds = acceptedGuestIds.filter((id) => placements[id]);
  const bySpecies = new Map();
  for (const guestId of placedIds) {
    const speciesId = data.indexes.guests[guestId].species;
    if (!bySpecies.has(speciesId)) bySpecies.set(speciesId, []);
    bySpecies.get(speciesId).push(guestId);
  }

  for (const [speciesId, guestIds] of bySpecies.entries()) {
    const species = data.indexes.species[speciesId];
    const active = [...(species.synergy_thresholds ?? [])]
      .filter((entry) => guestIds.length >= entry.count)
      .sort((a, b) => b.count - a.count)[0];
    if (!active) continue;
    const points = active.points_per_guest ?? active.points ?? 0;
    for (const guestId of guestIds) {
      addScoreItem(guestScores, guestId, {
        label: active.label ?? `${species.name} ${guestIds.length}인 시너지`,
        points,
        source: "synergy",
      });
    }
    groupEffects.push({
      type: "synergy",
      speciesIds: [speciesId],
      guestIds: [...guestIds],
      points: points * guestIds.length,
      label: active.label ?? `${species.name} 시너지`,
    });
  }

  const explicitConflicts = (data.species_conflicts ?? []).map((conflict) => ({
    leftId: conflict.species[0],
    rightId: conflict.species[1],
    points: conflict.points,
    label: conflict.label,
  }));
  const embeddedConflicts = data.species.flatMap((species) => (species.rivals ?? []).map((rival) => ({
    leftId: species.id,
    rightId: rival.species_id,
    points: rival.same_floor_penalty,
    label: rival.label,
  })));
  const handledPairs = new Set();
  for (const conflict of [...explicitConflicts, ...embeddedConflicts]) {
      const key = pairKey(conflict.leftId, conflict.rightId);
      if (handledPairs.has(key)) continue;
      handledPairs.add(key);
      const leftIds = bySpecies.get(conflict.leftId) ?? [];
      const rightIds = bySpecies.get(conflict.rightId) ?? [];
      const affected = new Set();
      for (const leftId of leftIds) {
        for (const rightId of rightIds) {
          const leftRoom = board.rooms[placements[leftId]];
          const rightRoom = board.rooms[placements[rightId]];
          if (leftRoom?.floor === rightRoom?.floor) {
            affected.add(leftId);
            affected.add(rightId);
          }
        }
      }
      if (!affected.size) continue;
      const points = conflict.points ?? -2;
      const leftName = data.indexes.species[conflict.leftId]?.name ?? conflict.leftId;
      const rightName = data.indexes.species[conflict.rightId]?.name ?? conflict.rightId;
      const label = conflict.label ?? `${leftName}·${rightName} 같은 층 충돌`;
      for (const guestId of affected) {
        addScoreItem(guestScores, guestId, { label, points, source: "conflict" });
      }
      groupEffects.push({
        type: "conflict",
        speciesIds: [conflict.leftId, conflict.rightId],
        guestIds: [...affected],
        points: points * affected.size,
        label,
      });
  }
  return groupEffects;
}

export function evaluatePlacement(data, acceptedGuestIds, placements, hotelContext = {}) {
  const board = createBoardState(data, hotelContext);
  const violations = [];
  const guestScores = {};

  for (const guestId of acceptedGuestIds) {
    const guest = data.indexes.guests[guestId];
    if (!guest) continue;
    guestScores[guestId] = { total: 0, items: [] };
    if (!placements[guestId]) {
      violations.push({
        guestId,
        ruleType: "UNPLACED",
        relatedIds: [],
        message: `${guest.name}에게 객실을 배정해야 합니다.`,
      });
      continue;
    }

    if (board.blockedRooms.has(placements[guestId])) {
      violations.push({
        guestId,
        ruleType: "BLOCKED_ROOM",
        relatedIds: [placements[guestId]],
        message: `${placements[guestId]}은 ${board.blockedReasons.get(placements[guestId]) ?? "사용 불가"} 상태입니다.`,
      });
      continue;
    }

    const rules = getGuestRules(data, guestId);
    for (const rule of rules.hard) {
      const violation = hardViolation(rule, guestId, placements, data, board);
      if (violation) violations.push(violation);
    }

    for (const rule of rules.soft) {
      if (preferenceMatched(rule, guestId, placements, data, board)) {
        addScoreItem(guestScores, guestId, {
          label: rule.label,
          points: rule.points,
          source: "preference",
        });
      }
    }
    for (let index = 0; index < (rules.hiddenPreferences ?? []).length; index += 1) {
      const rule = rules.hiddenPreferences[index];
      if (preferenceMatched(rule, guestId, placements, data, board)) {
        addScoreItem(guestScores, guestId, {
          label: rule.label,
          points: rule.points,
          source: "hidden",
          hiddenId: rule.id ?? `${guestId}:hidden:${index}`,
        });
      }
    }
    const continuingStay = (hotelContext.stayoverGuestIds ?? []).includes(guestId);
    const revisitPoints = continuingStay
      ? 0
      : revisitBonusFor(data, hotelContext.guestHistory?.[guestId]);
    if (revisitPoints) {
      addScoreItem(guestScores, guestId, {
        label: "다시 찾은 만족",
        points: revisitPoints,
        source: "revisit",
      });
    }
    for (const bonus of board.roomBonuses) {
      if (bonus.room_id === placements[guestId]) {
        addScoreItem(guestScores, guestId, {
          label: bonus.label,
          points: bonus.points,
          source: "facility",
        });
      }
    }
  }

  const placedRooms = Object.values(placements).filter(Boolean);
  if (new Set(placedRooms).size !== placedRooms.length) {
    violations.push({
      guestId: null,
      ruleType: "DUPLICATE_ROOM",
      relatedIds: placedRooms,
      message: "한 객실에 두 명 이상의 손님을 배치할 수 없습니다.",
    });
  }

  const groupEffects = applySpeciesEffects(data, acceptedGuestIds, placements, board, guestScores);
  const placementScore = Object.values(guestScores)
    .reduce((sum, score) => sum + score.total, 0);
  const hiddenMatches = Object.entries(guestScores).flatMap(([guestId, score]) =>
    score.items.filter((item) => item.source === "hidden").map((item) => ({ guestId, ...item })),
  );

  return {
    valid: violations.length === 0,
    violations,
    guestScores,
    groupEffects,
    hiddenMatches,
    placementScore,
    board,
  };
}

export function attributeLabel(attribute) {
  return ATTRIBUTE_LABELS[attribute] ?? attribute;
}
