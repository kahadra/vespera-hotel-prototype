import { rankOddsFor } from "./progression.js";
import { pickOne, pickWeighted } from "./random.js";

function upgradeIndex(data) {
  return data.indexes?.upgrades
    ?? Object.fromEntries(data.upgrades.map((upgrade) => [upgrade.id, upgrade]));
}

export function renovationRoomIds(upgrade) {
  if (!upgrade) return [];
  return [...new Set([
    ...(upgrade.blocked_rooms ?? []),
    ...(upgrade.room_attribute_changes ?? []).map((change) => change.room_id),
    ...(upgrade.room_bonuses ?? []).map((bonus) => bonus.room_id),
    ...(upgrade.adjacency_links ?? []).flat(),
  ])];
}

export function canPurchaseUpgrade(data, upgradeId, ownedIds = []) {
  const upgrade = upgradeIndex(data)[upgradeId];
  if (!upgrade || ownedIds.includes(upgradeId)) return false;
  const owned = new Set(ownedIds);
  return (upgrade.requires ?? []).every((requiredId) => owned.has(requiredId));
}

export function purchaseUpgrade(data, upgradeId, ownedIds = [], gold = 0) {
  const upgrade = upgradeIndex(data)[upgradeId];
  if (!upgrade) return { ok: false, reason: "UNKNOWN_UPGRADE", ownedIds: [...ownedIds], gold };
  if (ownedIds.includes(upgradeId)) return { ok: false, reason: "ALREADY_OWNED", ownedIds: [...ownedIds], gold };
  if (!canPurchaseUpgrade(data, upgradeId, ownedIds)) {
    return { ok: false, reason: "MISSING_PREREQUISITE", ownedIds: [...ownedIds], gold };
  }
  if (gold < upgrade.cost) return { ok: false, reason: "NOT_ENOUGH_GOLD", ownedIds: [...ownedIds], gold };
  return {
    ok: true,
    reason: null,
    ownedIds: [...ownedIds, upgradeId],
    gold: gold - upgrade.cost,
  };
}

export function generateUpgradeOffer(
  data,
  nextStage,
  reputation,
  ownedIds,
  gold,
  rngState,
) {
  const ranks = Object.fromEntries(data.ranks.map((rank) => [rank.id, rank]));
  const odds = rankOddsFor(data, nextStage, reputation);
  const eligible = data.upgrades.filter((upgrade) => (
    upgrade.unlock_stage <= nextStage
    && upgrade.minimum_reputation <= Math.max(0, reputation)
    && ranks[upgrade.rarity].unlock_stage <= nextStage
    && canPurchaseUpgrade(data, upgrade.id, ownedIds)
  ));
  const selected = [];
  const selectedIds = new Set();
  let nextState = rngState;
  const configuredSizes = data.prototype_mode.upgrade_offer_sizes ?? {};
  const offerSizes = {
    EXPANSION: configuredSizes.EXPANSION ?? 1,
    FACILITY: configuredSizes.FACILITY ?? data.prototype_mode.upgrade_offer_size ?? 3,
  };

  for (const kind of ["EXPANSION", "FACILITY"]) {
    const kindEligible = eligible.filter((upgrade) => upgrade.kind === kind);
    const kindSelected = [];
    while (kindSelected.length < offerSizes[kind]) {
      const remaining = kindEligible.filter((upgrade) => !selectedIds.has(upgrade.id));
      if (!remaining.length) break;
      const availableRarities = [...new Set(remaining.map((upgrade) => upgrade.rarity))];
      const rarityDraw = pickWeighted(availableRarities, (rarity) => odds[rarity] ?? 0, nextState);
      nextState = rarityDraw.rngState;
      const sameRarity = remaining.filter((upgrade) => upgrade.rarity === rarityDraw.value);
      const upgradeDraw = pickWeighted(sameRarity, (upgrade) => upgrade.offer_weight ?? 1, nextState);
      kindSelected.push(upgradeDraw.value);
      selected.push(upgradeDraw.value);
      selectedIds.add(upgradeDraw.value.id);
      nextState = upgradeDraw.rngState;
    }

    const affordable = kindEligible.filter(
      (upgrade) => upgrade.cost <= gold && !selectedIds.has(upgrade.id),
    );
    if (kindSelected.length && !kindSelected.some((upgrade) => upgrade.cost <= gold) && affordable.length) {
      const affordableDraw = pickOne(affordable, nextState);
      const replaced = kindSelected.at(-1);
      selectedIds.delete(replaced.id);
      selected[selected.indexOf(replaced)] = affordableDraw.value;
      kindSelected[kindSelected.length - 1] = affordableDraw.value;
      selectedIds.add(affordableDraw.value.id);
      nextState = affordableDraw.rngState;
    }
  }

  return {
    upgradeIds: selected.map((upgrade) => upgrade.id),
    rngState: nextState,
  };
}
