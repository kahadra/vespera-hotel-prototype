const UINT32_RANGE = 0x1_0000_0000;
const STEP = 0x6d2b79f5;

function hashString(value) {
  let hash = 0x811c9dc5;
  for (const character of String(value)) {
    hash ^= character.codePointAt(0);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

function seedValue(seed) {
  if (typeof seed === "number" && Number.isFinite(seed)) return seed >>> 0;
  return hashString(seed ?? 1);
}

export function createRngState(seed = 1) {
  return { state: seedValue(seed) };
}

function normalizedState(rngState) {
  if (rngState && Number.isInteger(rngState.state)) {
    return { state: rngState.state >>> 0 };
  }
  return createRngState(rngState ?? 1);
}

// Mulberry32 keeps the entire generator state in one serializable uint32.
export function nextFloat(rngState) {
  const current = normalizedState(rngState);
  const nextState = (current.state + STEP) >>> 0;
  let value = nextState;
  value = Math.imul(value ^ (value >>> 15), value | 1);
  value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
  value = ((value ^ (value >>> 14)) >>> 0) / UINT32_RANGE;
  return { value, rngState: { state: nextState } };
}

export function randomInt(rngState, maxExclusive) {
  if (!Number.isInteger(maxExclusive) || maxExclusive <= 0) {
    throw new Error("maxExclusive must be a positive integer.");
  }
  const draw = nextFloat(rngState);
  return {
    value: Math.floor(draw.value * maxExclusive),
    rngState: draw.rngState,
  };
}

export function pickOne(items, rngState) {
  if (!items.length) throw new Error("Cannot pick from an empty collection.");
  const draw = randomInt(rngState, items.length);
  return { value: items[draw.value], rngState: draw.rngState };
}

export function pickWeighted(items, weightOf, rngState) {
  if (!items.length) throw new Error("Cannot pick from an empty collection.");
  const weights = items.map((item) => Math.max(0, Number(weightOf(item)) || 0));
  const total = weights.reduce((sum, weight) => sum + weight, 0);
  if (total <= 0) return pickOne(items, rngState);

  const draw = nextFloat(rngState);
  let cursor = draw.value * total;
  for (let index = 0; index < items.length; index += 1) {
    cursor -= weights[index];
    if (cursor < 0) return { value: items[index], rngState: draw.rngState };
  }
  return { value: items.at(-1), rngState: draw.rngState };
}

export function shuffle(items, rngState) {
  const values = [...items];
  let nextState = normalizedState(rngState);
  for (let index = values.length - 1; index > 0; index -= 1) {
    const draw = randomInt(nextState, index + 1);
    [values[index], values[draw.value]] = [values[draw.value], values[index]];
    nextState = draw.rngState;
  }
  return { values, rngState: nextState };
}
