import { pickOne, pickWeighted } from "./random.js";

const RANK_IDS = ["N", "R", "SR", "SSR"];

function byId(items) {
  return Object.fromEntries(items.map((item) => [item.id, item]));
}

export function rankOddsFor(data, stage, reputation) {
  const safeStage = Math.max(1, Number(stage) || 1);
  const safeReputation = Math.max(0, Number(reputation) || 0);
  const rows = [...data.rank_odds].sort((left, right) => left.min_reputation - right.min_reputation);
  const row = rows.filter((candidate) => candidate.min_reputation <= safeReputation).at(-1) ?? rows[0];
  const ranks = byId(data.ranks);
  const odds = Object.fromEntries(RANK_IDS.map((rankId) => [rankId, Number(row.odds[rankId]) || 0]));

  for (let index = RANK_IDS.length - 1; index >= 0; index -= 1) {
    const rankId = RANK_IDS[index];
    const rank = ranks[rankId];
    const unlocked = rank.unlock_stage <= safeStage && rank.min_reputation <= safeReputation;
    if (unlocked || odds[rankId] === 0) continue;
    const recipient = RANK_IDS.slice(0, index)
      .reverse()
      .find((lowerId) => ranks[lowerId].unlock_stage <= safeStage && ranks[lowerId].min_reputation <= safeReputation)
      ?? "N";
    odds[recipient] += odds[rankId];
    odds[rankId] = 0;
  }

  const total = RANK_IDS.reduce((sum, rankId) => sum + odds[rankId], 0);
  if (total !== 100) odds.N += 100 - total;
  return odds;
}

function chooseGuestOfRank(candidates, rankId, rngState) {
  const matches = candidates.filter((guest) => guest.rank === rankId);
  if (!matches.length) return null;
  return pickOne(matches, rngState);
}

export function generateGuestOffer(
  data,
  scenario,
  odds,
  rngState,
  excludedIds = [],
) {
  const guests = byId(data.guests);
  const blocked = new Set([...(scenario.fixed_guests ?? []), ...excludedIds]);
  const poolIds = scenario.applicant_pool ?? scenario.applicants ?? [];
  const pool = poolIds
    .filter((guestId) => !blocked.has(guestId))
    .map((guestId) => guests[guestId])
    .filter(Boolean);
  const offerSize = scenario.offer_size ?? pool.length;
  const selected = [];
  const selectedIds = new Set();
  const specialInviteIds = [];
  let nextState = rngState;

  const addGuest = (guest, special = false) => {
    if (!guest || selectedIds.has(guest.id) || selected.length >= offerSize) return false;
    selected.push(guest);
    selectedIds.add(guest.id);
    if (special) specialInviteIds.push(guest.id);
    return true;
  };

  for (const guestId of scenario.special_invite_guest_ids ?? []) {
    if (blocked.has(guestId)) continue;
    addGuest(guests[guestId], true);
  }

  const guaranteedRank = scenario.guaranteed_rank;
  if (guaranteedRank && !selected.some((guest) => guest.rank === guaranteedRank)) {
    const candidates = pool.filter((guest) => !selectedIds.has(guest.id));
    const draw = chooseGuestOfRank(candidates, guaranteedRank, nextState);
    if (!draw) throw new Error(`${scenario.id} has no available ${guaranteedRank} guest for its guarantee.`);
    addGuest(draw.value);
    nextState = draw.rngState;
  }

  while (selected.length < offerSize) {
    const candidates = pool.filter(
      (guest) => !selectedIds.has(guest.id) && (odds[guest.rank] ?? 0) > 0,
    );
    if (!candidates.length) break;
    const availableRanks = RANK_IDS.filter((rankId) => candidates.some((guest) => guest.rank === rankId));
    const rankDraw = pickWeighted(availableRanks, (rankId) => odds[rankId] ?? 0, nextState);
    nextState = rankDraw.rngState;
    const guestDraw = chooseGuestOfRank(candidates, rankDraw.value, nextState);
    if (!guestDraw) throw new Error(`Unable to draw a ${rankDraw.value} guest from ${scenario.id}.`);
    addGuest(guestDraw.value);
    nextState = guestDraw.rngState;
  }

  if (selected.length < offerSize) {
    throw new Error(`${scenario.id} can only produce ${selected.length} of ${offerSize} requested guests.`);
  }

  return {
    guestIds: selected.map((guest) => guest.id),
    rngState: nextState,
    specialInviteIds,
  };
}
