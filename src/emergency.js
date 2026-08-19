import { getGuestRules } from "./data.js";
import { areAdjacent, createBoardState, evaluatePlacement } from "./rules.js";

const UNARY_RULE_TYPES = new Set([
  "ROOM_NOT_HAS",
  "ROOM_HAS",
  "FLOOR_IS",
  "FLOOR_AT_LEAST",
  "FLOOR_AT_MOST",
  "ELEVATOR_DISTANCE_AT_LEAST",
  "ELEVATOR_DISTANCE_AT_MOST",
]);

function unaryRuleMatched(rule, room) {
  if (rule.type === "ROOM_NOT_HAS") return !room.attributes.has(rule.attribute);
  if (rule.type === "ROOM_HAS") return room.attributes.has(rule.attribute);
  if (rule.type === "FLOOR_IS") return room.floor === rule.floor;
  if (rule.type === "FLOOR_AT_LEAST") return room.floor >= rule.floor;
  if (rule.type === "FLOOR_AT_MOST") return room.floor <= rule.floor;
  if (rule.type === "ELEVATOR_DISTANCE_AT_LEAST") return room.wing >= rule.distance;
  if (rule.type === "ELEVATOR_DISTANCE_AT_MOST") return room.wing <= rule.distance;
  return true;
}

function sanitizedPlacements(guestIds, placements, roomIds, onlyGuestIds = null) {
  const allowedGuests = new Set(onlyGuestIds ?? guestIds);
  const allowedRooms = new Set(roomIds);
  const usedRooms = new Set();
  const fixed = {};
  for (const guestId of guestIds) {
    if (!allowedGuests.has(guestId)) continue;
    const roomId = placements[guestId];
    if (!allowedRooms.has(roomId) || usedRooms.has(roomId)) continue;
    fixed[guestId] = roomId;
    usedRooms.add(roomId);
  }
  return fixed;
}

function createAssignmentSolver(data, hotelContext) {
  const board = createBoardState(data, hotelContext);
  const roomIds = data.rooms
    .map((room) => room.id)
    .filter((roomId) => !board.blockedRooms.has(roomId));
  const hardRulesByGuest = new Map();
  const unaryDomainsByGuest = new Map();
  const resultCache = new Map();

  function hardRules(guestId) {
    if (!hardRulesByGuest.has(guestId)) {
      hardRulesByGuest.set(guestId, getGuestRules(data, guestId).hard);
    }
    return hardRulesByGuest.get(guestId);
  }

  function unaryDomain(guestId) {
    if (!unaryDomainsByGuest.has(guestId)) {
      const rules = hardRules(guestId).filter((rule) => UNARY_RULE_TYPES.has(rule.type));
      unaryDomainsByGuest.set(
        guestId,
        roomIds.filter((roomId) => rules.every((rule) => unaryRuleMatched(rule, board.rooms[roomId]))),
      );
    }
    return unaryDomainsByGuest.get(guestId);
  }

  function forbidsOccupiedNeighbor(guestId) {
    return hardRules(guestId).some((rule) => rule.type === "NO_OCCUPIED_ADJACENT");
  }

  function candidateRooms(guestId, activeGuestSet, assignment, usedRooms) {
    return unaryDomain(guestId).filter((roomId) => {
      if (usedRooms.has(roomId)) return false;
      for (const [otherId, otherRoomId] of Object.entries(assignment)) {
        if (!areAdjacent(roomId, otherRoomId, board)) continue;
        if (forbidsOccupiedNeighbor(guestId) || forbidsOccupiedNeighbor(otherId)) return false;
      }
      for (const rule of hardRules(guestId)) {
        if (rule.type !== "MUST_ADJACENT_GUEST") continue;
        if (!activeGuestSet.has(rule.guest_id)) return false;
        const otherRoomId = assignment[rule.guest_id];
        if (otherRoomId && !areAdjacent(roomId, otherRoomId, board)) return false;
      }
      return true;
    });
  }

  function hasDistinctRoomMatching(guestIds, domains) {
    const roomOwner = new Map();
    const ordered = [...guestIds].sort((left, right) =>
      domains.get(left).length - domains.get(right).length);

    function claimRoom(guestId, visitedRooms) {
      for (const roomId of domains.get(guestId)) {
        if (visitedRooms.has(roomId)) continue;
        visitedRooms.add(roomId);
        const owner = roomOwner.get(roomId);
        if (owner === undefined || claimRoom(owner, visitedRooms)) {
          roomOwner.set(roomId, guestId);
          return true;
        }
      }
      return false;
    }

    return ordered.every((guestId) => claimRoom(guestId, new Set()));
  }

  function analyzePartial(activeGuestIds, activeGuestSet, assignment, usedRooms) {
    const unassigned = activeGuestIds.filter((guestId) => !assignment[guestId]);
    if (unassigned.length > roomIds.length - usedRooms.size) return null;

    for (const [guestId, roomId] of Object.entries(assignment)) {
      if (!activeGuestSet.has(guestId) || !unaryDomain(guestId).includes(roomId)) return null;
      for (const rule of hardRules(guestId)) {
        if (rule.type === "NO_OCCUPIED_ADJACENT") {
          const hasNeighbor = Object.entries(assignment).some(
            ([otherId, otherRoomId]) => otherId !== guestId && areAdjacent(roomId, otherRoomId, board),
          );
          if (hasNeighbor) return null;
        } else if (rule.type === "MUST_ADJACENT_GUEST") {
          if (!activeGuestSet.has(rule.guest_id)) return null;
          const otherRoomId = assignment[rule.guest_id];
          if (otherRoomId && !areAdjacent(roomId, otherRoomId, board)) return null;
        }
      }
    }

    const domains = new Map(
      unassigned.map((guestId) => [
        guestId,
        candidateRooms(guestId, activeGuestSet, assignment, usedRooms),
      ]),
    );
    if ([...domains.values()].some((domain) => domain.length === 0)) return null;
    if (!hasDistinctRoomMatching(unassigned, domains)) return null;

    for (const guestId of activeGuestIds) {
      const assignedRoomId = assignment[guestId];
      for (const rule of hardRules(guestId)) {
        if (rule.type === "MUST_ADJACENT_GUEST") {
          const otherId = rule.guest_id;
          if (!activeGuestSet.has(otherId)) return null;
          const otherRoomId = assignment[otherId];
          if (assignedRoomId && otherRoomId) continue;
          if (assignedRoomId) {
            if (!domains.get(otherId)?.some((roomId) => areAdjacent(assignedRoomId, roomId, board))) return null;
          } else if (otherRoomId) {
            if (!domains.get(guestId)?.some((roomId) => areAdjacent(roomId, otherRoomId, board))) return null;
          } else {
            const ownDomain = domains.get(guestId) ?? [];
            const otherDomain = domains.get(otherId) ?? [];
            const possiblePair = ownDomain.some((roomId) =>
              otherDomain.some((otherCandidate) => areAdjacent(roomId, otherCandidate, board)));
            if (!possiblePair) return null;
          }
        } else if (rule.type === "MUST_SHARE_FLOOR") {
          if (assignedRoomId) {
            const assignedCompanion = Object.entries(assignment).some(
              ([otherId, otherRoomId]) => otherId !== guestId
                && board.rooms[otherRoomId].floor === board.rooms[assignedRoomId].floor,
            );
            if (assignedCompanion) continue;
            const possibleCompanion = unassigned.some((otherId) =>
              otherId !== guestId
                && domains.get(otherId).some(
                  (roomId) => board.rooms[roomId].floor === board.rooms[assignedRoomId].floor,
                ));
            if (!possibleCompanion) return null;
          } else {
            const possibleFloorMate = domains.get(guestId).some((roomId) => {
              const floor = board.rooms[roomId].floor;
              const assignedCompanion = Object.entries(assignment).some(
                ([otherId, otherRoomId]) => otherId !== guestId && board.rooms[otherRoomId].floor === floor,
              );
              if (assignedCompanion) return true;
              return unassigned.some((otherId) =>
                otherId !== guestId
                  && domains.get(otherId).some(
                    (otherRoomId) => otherRoomId !== roomId && board.rooms[otherRoomId].floor === floor,
                  ));
            });
            if (!possibleFloorMate) return null;
          }
        }
      }
    }

    return domains;
  }

  function solve(guestIds, fixedPlacements = {}) {
    const activeGuestIds = [...new Set(guestIds)];
    const activeGuestSet = new Set(activeGuestIds);
    const fixedEntries = Object.entries(fixedPlacements)
      .filter(([guestId]) => activeGuestSet.has(guestId))
      .sort(([left], [right]) => left.localeCompare(right));
    const cacheKey = `${activeGuestIds.join(",")}|${fixedEntries.map(([id, room]) => `${id}:${room}`).join(",")}`;
    if (resultCache.has(cacheKey)) {
      const cached = resultCache.get(cacheKey);
      return cached ? { ...cached } : null;
    }

    const assignment = Object.fromEntries(fixedEntries);
    const usedRooms = new Set(Object.values(assignment));
    if (usedRooms.size !== fixedEntries.length || activeGuestIds.length > roomIds.length) {
      resultCache.set(cacheKey, null);
      return null;
    }
    const deadStates = new Set();

    function search() {
      const domains = analyzePartial(activeGuestIds, activeGuestSet, assignment, usedRooms);
      if (!domains) return null;
      if (domains.size === 0) {
        return evaluatePlacement(data, activeGuestIds, assignment, hotelContext).valid
          ? { ...assignment }
          : null;
      }

      const stateKey = activeGuestIds
        .map((guestId) => `${guestId}:${assignment[guestId] ?? "-"}`)
        .join("|");
      if (deadStates.has(stateKey)) return null;
      const guestId = [...domains.keys()].sort((left, right) => {
        const domainDifference = domains.get(left).length - domains.get(right).length;
        return domainDifference || activeGuestIds.indexOf(left) - activeGuestIds.indexOf(right);
      })[0];

      for (const roomId of domains.get(guestId)) {
        assignment[guestId] = roomId;
        usedRooms.add(roomId);
        const result = search();
        if (result) return result;
        usedRooms.delete(roomId);
        delete assignment[guestId];
      }
      deadStates.add(stateKey);
      return null;
    }

    const result = search();
    resultCache.set(cacheKey, result ? { ...result } : null);
    return result;
  }

  return { roomIds, solve };
}

function* combinations(values, count, start = 0, picked = []) {
  if (picked.length === count) {
    yield [...picked];
    return;
  }
  for (let index = start; index <= values.length - (count - picked.length); index += 1) {
    picked.push(values[index]);
    yield* combinations(values, count, index + 1, picked);
    picked.pop();
  }
}

export function createEmergencyPlan(
  data,
  acceptedGuestIds,
  placements,
  hotelContext = {},
  options = {},
) {
  const lockedGuestIds = options.lockedGuestIds ?? [];
  const lockedSet = new Set(lockedGuestIds);
  const solver = createAssignmentSolver(data, hotelContext);
  const lockedPlacements = sanitizedPlacements(
    acceptedGuestIds,
    placements,
    solver.roomIds,
    lockedGuestIds,
  );
  const fixed = sanitizedPlacements(acceptedGuestIds, placements, solver.roomIds);
  let assignment = solver.solve(acceptedGuestIds, fixed);
  let keptExisting = true;

  if (!assignment) {
    assignment = solver.solve(acceptedGuestIds, lockedPlacements);
    keptExisting = false;
  }

  let housedGuestIds = [...acceptedGuestIds];
  let canceledGuestIds = [];
  if (!assignment) {
    const cancellationPriority = [...acceptedGuestIds]
      .reverse()
      .filter((guestId) => !lockedSet.has(guestId));
    for (let count = 1; count <= cancellationPriority.length && !assignment; count += 1) {
      for (const canceled of combinations(cancellationPriority, count)) {
        const canceledSet = new Set(canceled);
        const remaining = acceptedGuestIds.filter((guestId) => !canceledSet.has(guestId));
        const remainingSet = new Set(remaining);
        const remainingLocked = Object.fromEntries(
          Object.entries(lockedPlacements).filter(([guestId]) => remainingSet.has(guestId)),
        );
        const candidate = solver.solve(remaining, remainingLocked);
        if (!candidate) continue;
        assignment = candidate;
        housedGuestIds = remaining;
        canceledGuestIds = canceled;
        break;
      }
    }
  }

  assignment ??= {};
  const autoAssignedGuestIds = housedGuestIds.filter(
    (guestId) => placements[guestId] !== assignment[guestId],
  );

  return {
    placements: assignment,
    housedGuestIds,
    canceledGuestIds,
    autoAssignedGuestIds,
    keptExisting,
    lockedGuestIds: [...lockedGuestIds],
  };
}
