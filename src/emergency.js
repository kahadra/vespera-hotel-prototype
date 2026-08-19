import { createBoardState, evaluatePlacement } from "./rules.js";

function usableRoomIds(data, facilityId) {
  const board = createBoardState(data, facilityId);
  return data.rooms
    .map((room) => room.id)
    .filter((roomId) => !board.blockedRooms.has(roomId));
}

function sanitizedFixedPlacements(guestIds, placements, roomIds) {
  const allowedGuests = new Set(guestIds);
  const allowedRooms = new Set(roomIds);
  const usedRooms = new Set();
  const fixed = {};
  for (const guestId of guestIds) {
    const roomId = placements[guestId];
    if (!allowedGuests.has(guestId) || !allowedRooms.has(roomId) || usedRooms.has(roomId)) continue;
    fixed[guestId] = roomId;
    usedRooms.add(roomId);
  }
  return fixed;
}

function firstValidAssignment(data, guestIds, facilityId, fixedPlacements = {}) {
  const roomIds = usableRoomIds(data, facilityId);
  const assignment = { ...fixedPlacements };
  const usedRooms = new Set(Object.values(fixedPlacements));
  const remainingGuests = guestIds.filter((guestId) => !assignment[guestId]);

  function search(index) {
    if (index >= remainingGuests.length) {
      return evaluatePlacement(data, guestIds, assignment, facilityId).valid
        ? { ...assignment }
        : null;
    }
    const guestId = remainingGuests[index];
    for (const roomId of roomIds) {
      if (usedRooms.has(roomId)) continue;
      assignment[guestId] = roomId;
      usedRooms.add(roomId);
      const result = search(index + 1);
      if (result) return result;
      usedRooms.delete(roomId);
      delete assignment[guestId];
    }
    return null;
  }

  return search(0);
}

function combinations(values, count, start = 0, picked = [], output = []) {
  if (picked.length === count) {
    output.push([...picked]);
    return output;
  }
  for (let index = start; index <= values.length - (count - picked.length); index += 1) {
    picked.push(values[index]);
    combinations(values, count, index + 1, picked, output);
    picked.pop();
  }
  return output;
}

export function createEmergencyPlan(data, acceptedGuestIds, placements, facilityId) {
  const roomIds = usableRoomIds(data, facilityId);
  const fixed = sanitizedFixedPlacements(acceptedGuestIds, placements, roomIds);
  let assignment = firstValidAssignment(data, acceptedGuestIds, facilityId, fixed);
  let keptExisting = true;

  if (!assignment) {
    assignment = firstValidAssignment(data, acceptedGuestIds, facilityId);
    keptExisting = false;
  }

  let housedGuestIds = [...acceptedGuestIds];
  let canceledGuestIds = [];
  if (!assignment) {
    const cancellationPriority = [...acceptedGuestIds].reverse();
    for (let count = 1; count <= acceptedGuestIds.length && !assignment; count += 1) {
      for (const canceled of combinations(cancellationPriority, count)) {
        const canceledSet = new Set(canceled);
        const remaining = acceptedGuestIds.filter((guestId) => !canceledSet.has(guestId));
        const candidate = firstValidAssignment(data, remaining, facilityId);
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
  };
}
