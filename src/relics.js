import { createRngState, pickWeighted } from "./random.js";

export function displayRelicById(data, relicId) {
  return data.indexes?.displayRelics?.[relicId]
    ?? data.display_relics?.find((relic) => relic.id === relicId)
    ?? null;
}

export function ownedDisplayRelics(data, ownedIds = []) {
  return ownedIds.map((id) => displayRelicById(data, id)).filter(Boolean);
}

export function displayRelicEffectValue(data, ownedIds, effectId) {
  return ownedDisplayRelics(data, ownedIds)
    .filter((relic) => relic.effect_id === effectId)
    .reduce((total, relic) => total + Number(relic.effect_params?.value ?? 0), 0);
}

export function generateDisplayRelicOffer(data, options = {}) {
  const poolIds = new Set(options.poolIds ?? ["COMMON"]);
  const ownedIds = new Set(options.ownedIds ?? []);
  const eligible = (data.display_relics ?? []).filter((relic) => (
    poolIds.has(relic.pool_type ?? relic.pool_id)
    && !ownedIds.has(relic.id)
  ));
  const offerSize = Math.max(1, Number(options.offerSize ?? 3));
  const offerIndex = Math.max(0, Number(options.offerIndex ?? 0));
  const isolatedRng = createRngState(`${options.runSeed ?? 1}:DISPLAY_RELIC:${offerIndex}`);
  const selected = [];
  let candidates = [...eligible];
  let nextRng = isolatedRng;
  while (selected.length < offerSize && candidates.length) {
    const draw = pickWeighted(candidates, (relic) => relic.offer_weight ?? 1, nextRng);
    selected.push(draw.value);
    candidates = candidates.filter((relic) => relic.id !== draw.value.id);
    nextRng = draw.rngState;
  }
  return {
    relicIds: selected.map((relic) => relic.id),
    offerIndex,
  };
}
