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
  return {
    rooms: byId(data.rooms),
    species: byId(data.species),
    ranks: byId(data.ranks),
    guests: byId(data.guests),
    facilities: byId(data.facilities),
    scenarios: byId(data.scenarios),
  };
}

function assertUnique(items, label) {
  const ids = items.map((item) => item.id);
  if (new Set(ids).size !== ids.length) {
    throw new Error(`${label} 데이터에 중복 ID가 있습니다.`);
  }
}

function validateData(data, indexes) {
  [
    [data.rooms, "객실"],
    [data.species, "종족"],
    [data.ranks, "등급"],
    [data.guests, "손님"],
    [data.facilities, "시설"],
    [data.scenarios, "영업"],
  ].forEach(([items, label]) => assertUnique(items, label));

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
  }

  for (const scenario of data.scenarios) {
    for (const guestId of [...scenario.fixed_guests, ...scenario.applicants]) {
      if (!indexes.guests[guestId]) {
        throw new Error(`${scenario.id}가 존재하지 않는 손님 ${guestId}을 참조합니다.`);
      }
    }
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
  return {
    commonRequired,
    rankRequired,
    personalRequired,
    commonPreferences,
    rankPreferences,
    personalPreferences,
    hard: [...commonRequired, ...rankRequired, ...personalRequired],
    soft: [...commonPreferences, ...rankPreferences, ...personalPreferences],
  };
}
