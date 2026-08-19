import { getGuestRules } from "./data.js";

const ATTRIBUTE_LABELS = {
  noisy: "시끄러운",
  quiet: "조용한",
  sunny: "햇빛",
};

function pairKey(left, right) {
  return [left, right].sort().join("|");
}

export function createBoardState(data, facilityId = null) {
  const rooms = Object.fromEntries(
    data.rooms.map((room) => [
      room.id,
      { ...room, attributes: new Set(room.attributes) },
    ]),
  );
  const blockedRooms = new Set();
  const extraLinks = new Set();
  const facility = facilityId ? data.indexes.facilities[facilityId] : null;

  if (facility) {
    for (const roomId of facility.blocked_rooms) blockedRooms.add(roomId);
    for (const change of facility.room_attribute_changes) {
      const attributes = rooms[change.room_id].attributes;
      for (const value of change.remove) attributes.delete(value);
      for (const value of change.add) attributes.add(value);
    }
    for (const [left, right] of facility.adjacency_links) {
      extraLinks.add(pairKey(left, right));
    }
  }

  return { rooms, blockedRooms, extraLinks, facility };
}

export function areAdjacent(leftId, rightId, board) {
  if (!leftId || !rightId || leftId === rightId) return false;
  if (board.extraLinks.has(pairKey(leftId, rightId))) return true;
  const left = board.rooms[leftId];
  const right = board.rooms[rightId];
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

  if (rule.type === "MUST_ADJACENT_GUEST") {
    const other = data.indexes.guests[rule.guest_id];
    if (placements[rule.guest_id] && areAdjacent(roomId, placements[rule.guest_id], board)) return null;
    return {
      guestId,
      ruleType: rule.type,
      relatedIds: [rule.guest_id],
      message: `${guest.name}은 ${other.name}의 옆방에 있어야 합니다.`,
    };
  }

  if (rule.type === "NO_OCCUPIED_ADJACENT") {
    const neighbors = Object.entries(placements)
      .filter(([otherId, otherRoom]) => otherId !== guestId && areAdjacent(roomId, otherRoom, board))
      .map(([otherId]) => otherId);
    if (!neighbors.length) return null;
    const names = neighbors.map((id) => data.indexes.guests[id].name).join(", ");
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
        otherId !== guestId && board.rooms[otherRoom].floor === room.floor,
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
  if (rule.type === "FLOOR_IS") return room.floor === rule.floor;
  if (rule.type === "ELEVATOR_DISTANCE_AT_LEAST") return room.wing >= rule.distance;
  if (rule.type === "ELEVATOR_DISTANCE_AT_MOST") return room.wing <= rule.distance;
  if (rule.type === "ADJACENT_GUEST") {
    return Boolean(
      placements[rule.guest_id] && areAdjacent(roomId, placements[rule.guest_id], board),
    );
  }
  if (rule.type === "NEAR_FACILITY") {
    if (!board.facility || board.facility.id !== rule.facility_id) return false;
    return board.facility.blocked_rooms.some((facilityRoom) =>
      areAdjacent(roomId, facilityRoom, board),
    );
  }
  throw new Error(`알 수 없는 선호 사항 규칙: ${rule.type}`);
}

export function evaluatePlacement(data, acceptedGuestIds, placements, facilityId = null) {
  const board = createBoardState(data, facilityId);
  const violations = [];
  const guestScores = {};
  let placementScore = 0;

  for (const guestId of acceptedGuestIds) {
    const guest = data.indexes.guests[guestId];
    if (!placements[guestId]) {
      violations.push({
        guestId,
        ruleType: "UNPLACED",
        relatedIds: [],
        message: `${guest.name}에게 객실을 배정해야 합니다.`,
      });
      guestScores[guestId] = { total: 0, items: [] };
      continue;
    }

    if (board.blockedRooms.has(placements[guestId])) {
      violations.push({
        guestId,
        ruleType: "BLOCKED_ROOM",
        relatedIds: [placements[guestId]],
        message: `${placements[guestId]}은 시설이 사용 중이라 객실로 배정할 수 없습니다.`,
      });
    }

    const rules = getGuestRules(data, guestId);
    for (const rule of rules.hard) {
      const violation = hardViolation(rule, guestId, placements, data, board);
      if (violation) violations.push(violation);
    }

    const items = [];
    for (const rule of rules.soft) {
      if (preferenceMatched(rule, guestId, placements, data, board)) {
        items.push({ label: rule.label, points: rule.points, source: "preference" });
      }
    }
    if (board.facility) {
      for (const bonus of board.facility.room_bonuses ?? []) {
        if (bonus.room_id === placements[guestId]) {
          items.push({ label: bonus.label, points: bonus.points, source: "facility" });
        }
      }
    }
    const total = items.reduce((sum, item) => sum + item.points, 0);
    guestScores[guestId] = { total, items };
    placementScore += total;
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

  return {
    valid: violations.length === 0,
    violations,
    guestScores,
    placementScore,
    board,
  };
}

export function attributeLabel(attribute) {
  return ATTRIBUTE_LABELS[attribute] ?? attribute;
}
