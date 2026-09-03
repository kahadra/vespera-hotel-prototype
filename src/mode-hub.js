const ACTIVE_RUN_STORAGE_PREFIX = "vespera.hotel.active-run.v2";
const LEGACY_SHOWCASE_STORAGE_KEY = "vespera.hotel.active-run.v1";

function frozenModeOption(option) {
  return Object.freeze(option);
}

export const DESKTOP_MODE_OPTIONS = Object.freeze([
  frozenModeOption({
    id: "campaign",
    modeId: "CAMPAIGN",
    label: "시나리오 캠페인",
    description: "상속받은 호텔의 새 게임부터 결말까지 잇는 현재 5영업 회색 상자입니다.",
    eyebrow: "STORY CAMPAIGN",
    glyph: "◇",
    availabilityNote: "모드별 독립 저장",
  }),
  frozenModeOption({
    id: "endless",
    modeId: "ENDLESS",
    label: "무한 영업",
    description: "7일을 한 시즌으로 삼아 운영 감사를 넘기며, 장기 증축과 공간 시너지가 누적되는 호텔을 이어갑니다.",
    eyebrow: "ENDLESS OPERATION",
    glyph: "∞",
    availabilityNote: "모드별 독립 저장",
  }),
  frozenModeOption({
    id: "showcase",
    modeId: "SHOWCASE",
    label: "초청 영업",
    description: "핵심 배치 규칙을 짧게 익힙니다.",
    eyebrow: "INVITATIONAL",
    glyph: "✦",
    availabilityNote: "기존 기록 호환",
  }),
]);

const MODE_BY_ID = new Map(DESKTOP_MODE_OPTIONS.map((option) => [option.id, option]));

export function isDesktopModeId(id) {
  return typeof id === "string" && MODE_BY_ID.has(id);
}

function emptySummary(option, status) {
  return Object.freeze({
    ...option,
    status,
    savedAt: null,
    phase: null,
    runSeed: null,
    currentNightIndex: null,
  });
}

function availableSummary(option, checkpoint) {
  return Object.freeze({
    ...option,
    status: "AVAILABLE",
    savedAt: typeof checkpoint.saved_at === "string" ? checkpoint.saved_at : null,
    phase: checkpoint.state.phase,
    runSeed: checkpoint.state.runSeed,
    currentNightIndex: checkpoint.state.currentNightIndex,
  });
}

function safeStorageRead(storage, key) {
  if (!storage || typeof storage.getItem !== "function") {
    return { kind: "INVALID", value: null };
  }
  try {
    const value = storage.getItem(key);
    if (value === null || value === undefined) return { kind: "NONE", value: null };
    if (typeof value !== "string") return { kind: "INVALID", value: null };
    return { kind: "VALUE", value };
  } catch {
    return { kind: "INVALID", value: null };
  }
}

function validatedCheckpointFor(validatedCheckpoints, option) {
  try {
    const checkpoint = typeof validatedCheckpoints === "function"
      ? validatedCheckpoints(option.id, option)
      : validatedCheckpoints instanceof Map
        ? validatedCheckpoints.get(option.id)
        : null;
    if (!checkpoint
      || checkpoint.mode_id !== option.modeId
      || !checkpoint.state
      || typeof checkpoint.state !== "object"
      || Array.isArray(checkpoint.state)) {
      return null;
    }
    return checkpoint;
  } catch {
    return null;
  }
}

function readModeSummary(storage, option, validatedCheckpoints) {
  const keys = [`${ACTIVE_RUN_STORAGE_PREFIX}.${option.id}`];
  if (option.id === "showcase") keys.push(LEGACY_SHOWCASE_STORAGE_KEY);
  let rawCandidatePresent = false;
  for (const key of keys) {
    const stored = safeStorageRead(storage, key);
    if (stored.kind === "NONE") continue;
    if (stored.kind === "INVALID") return emptySummary(option, "INVALID");
    rawCandidatePresent = true;
  }
  if (!rawCandidatePresent) return emptySummary(option, "NONE");
  const checkpoint = validatedCheckpointFor(validatedCheckpoints, option);
  return checkpoint
    ? availableSummary(option, checkpoint)
    : emptySummary(option, "INVALID");
}

export function readDesktopModeSummaries(storage, validatedCheckpoints = null) {
  return Object.freeze(DESKTOP_MODE_OPTIONS.map(
    (option) => readModeSummary(storage, option, validatedCheckpoints),
  ));
}

function parsedDesktopUrl(currentHref) {
  if (typeof currentHref !== "string" || currentHref.length === 0 || currentHref.trim() !== currentHref) {
    throw new TypeError("currentHref must be a non-empty absolute URL without surrounding whitespace");
  }
  let url;
  try {
    url = new URL(currentHref);
  } catch {
    throw new TypeError("currentHref must be a valid absolute URL");
  }
  if (!["http:", "https:", "vespera:"].includes(url.protocol)) {
    throw new TypeError("currentHref uses an unsupported protocol");
  }
  return url;
}

export function desktopModeUrl(currentHref, id) {
  if (!isDesktopModeId(id)) throw new TypeError("id must be a supported desktop mode id");
  const url = parsedDesktopUrl(currentHref);
  url.pathname = "/index.html";
  url.search = "";
  url.hash = "";
  url.searchParams.set("mode", id);
  return url.href;
}

export function desktopHubUrl(currentHref) {
  const url = parsedDesktopUrl(currentHref);
  url.pathname = "/index.html";
  url.search = "";
  url.hash = "";
  return url.href;
}

export function browserModeUrl(currentHref, id) {
  if (!isDesktopModeId(id)) throw new TypeError("id must be a supported browser mode id");
  const url = parsedDesktopUrl(currentHref);
  if (!["http:", "https:"].includes(url.protocol)) {
    throw new TypeError("browser mode URLs require http or https");
  }
  url.search = "";
  url.hash = "";
  url.searchParams.set("mode", id);
  return url.href;
}

export function browserHubUrl(currentHref) {
  const url = parsedDesktopUrl(currentHref);
  if (!["http:", "https:"].includes(url.protocol)) {
    throw new TypeError("browser hub URLs require http or https");
  }
  url.search = "";
  url.hash = "";
  return url.href;
}
