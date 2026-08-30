"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const sourcePath = path.join(__dirname, "..", "src", "mode-hub.js");
const source = fs.readFileSync(sourcePath, "utf8");
const modulePromise = import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);

function checkpoint(modeId, overrides = {}) {
  const base = {
    schema_version: 6,
    data_schema_version: 4,
    mode_id: modeId,
    profile_id: "default",
    saved_at: "2026-08-30T12:34:56.000Z",
    state: {
      phase: "DAY_OPENING",
      runSeed: 424242,
      currentNightIndex: 3,
    },
    stage_checkpoint: null,
  };
  return {
    ...base,
    ...overrides,
    state: overrides.state === undefined ? base.state : overrides.state,
  };
}

function storageFixture(entries = {}, { throwOnGet = false } = {}) {
  const values = new Map(Object.entries(entries));
  let mutationCount = 0;
  return {
    get mutationCount() {
      return mutationCount;
    },
    getItem(key) {
      if (throwOnGet) throw new Error("storage unavailable");
      return values.has(key) ? values.get(key) : null;
    },
    setItem() {
      mutationCount += 1;
    },
    removeItem() {
      mutationCount += 1;
    },
  };
}

test("declares the three strict desktop mode identities", async () => {
  const { DESKTOP_MODE_OPTIONS, isDesktopModeId } = await modulePromise;
  assert.deepEqual(
    DESKTOP_MODE_OPTIONS.map(({ id, modeId }) => ({ id, modeId })),
    [
      { id: "campaign", modeId: "CAMPAIGN" },
      { id: "endless", modeId: "ENDLESS" },
      { id: "showcase", modeId: "SHOWCASE" },
    ],
  );
  assert.equal(isDesktopModeId("campaign"), true);
  assert.equal(isDesktopModeId("endless"), true);
  assert.equal(isDesktopModeId("showcase"), true);
  assert.equal(isDesktopModeId("CAMPAIGN"), false);
  assert.equal(isDesktopModeId(" campaign"), false);
  assert.equal(isDesktopModeId(null), false);
});

test("summarizes valid checkpoints without mutating storage", async () => {
  const { readDesktopModeSummaries } = await modulePromise;
  const campaign = checkpoint("CAMPAIGN");
  const endless = checkpoint("ENDLESS", {
    saved_at: "2026-08-30T13:00:00.000Z",
    state: { phase: "ENDLESS_AUDIT", runSeed: 7, currentNightIndex: 4 },
  });
  const storage = storageFixture({
    "vespera.hotel.active-run.v2.campaign": JSON.stringify(campaign),
    "vespera.hotel.active-run.v2.endless": JSON.stringify(endless),
  });
  const summaries = readDesktopModeSummaries(storage, new Map([
    ["campaign", campaign],
    ["endless", endless],
  ]));
  assert.deepEqual(summaries[0], {
    id: "campaign",
    modeId: "CAMPAIGN",
    label: "시나리오 캠페인",
    description: "상속받은 호텔의 새 게임부터 결말까지 잇는 현재 5영업 회색 상자입니다.",
    eyebrow: "STORY CAMPAIGN",
    glyph: "◇",
    availabilityNote: "모드별 독립 저장",
    status: "AVAILABLE",
    savedAt: "2026-08-30T12:34:56.000Z",
    phase: "DAY_OPENING",
    runSeed: 424242,
    currentNightIndex: 3,
  });
  assert.equal(summaries[1].status, "AVAILABLE");
  assert.equal(summaries[1].phase, "ENDLESS_AUDIT");
  assert.equal(summaries[2].status, "NONE");
  assert.equal(storage.mutationCount, 0);
});

test("raw checkpoint presence is never independently treated as available", async () => {
  const { readDesktopModeSummaries } = await modulePromise;
  const rawCheckpoint = checkpoint("CAMPAIGN");
  const storage = storageFixture({
    "vespera.hotel.active-run.v2.campaign": JSON.stringify(rawCheckpoint),
  });
  const withoutAuthority = readDesktopModeSummaries(storage);
  assert.equal(withoutAuthority[0].status, "INVALID");
  const rejectedByAuthority = readDesktopModeSummaries(storage, new Map([
    ["campaign", null],
  ]));
  assert.equal(rejectedByAuthority[0].status, "INVALID");
  const acceptedByAuthority = readDesktopModeSummaries(storage, new Map([
    ["campaign", rawCheckpoint],
  ]));
  assert.equal(acceptedByAuthority[0].status, "AVAILABLE");
});

test("a stale validated map cannot make a missing raw checkpoint available", async () => {
  const { readDesktopModeSummaries } = await modulePromise;
  const summaries = readDesktopModeSummaries(storageFixture(), new Map([
    ["campaign", checkpoint("CAMPAIGN")],
  ]));
  assert.equal(summaries[0].status, "NONE");
});

test("marks corrupt, malformed, and mode-mismatched checkpoints invalid", async () => {
  const { readDesktopModeSummaries } = await modulePromise;
  const storage = storageFixture({
    "vespera.hotel.active-run.v2.campaign": "{truncated",
    "vespera.hotel.active-run.v2.endless": JSON.stringify(checkpoint("CAMPAIGN")),
    "vespera.hotel.active-run.v2.showcase": JSON.stringify(checkpoint("SHOWCASE", {
      state: { phase: "DAY_OPENING", runSeed: -1, currentNightIndex: 0 },
    })),
  });
  const summaries = readDesktopModeSummaries(storage);
  assert.deepEqual(summaries.map(({ status }) => status), ["INVALID", "INVALID", "INVALID"]);
  for (const summary of summaries) {
    assert.equal(summary.savedAt, null);
    assert.equal(summary.phase, null);
    assert.equal(summary.runSeed, null);
    assert.equal(summary.currentNightIndex, null);
  }
});

test("uses the valid legacy showcase checkpoint as a fallback", async () => {
  const { readDesktopModeSummaries } = await modulePromise;
  const legacy = checkpoint("SHOWCASE", {
    schema_version: 3,
    state: { phase: "PLACEMENT", runSeed: 99, currentNightIndex: 1 },
  });
  const storage = storageFixture({
    "vespera.hotel.active-run.v2.showcase": JSON.stringify(checkpoint("CAMPAIGN")),
    "vespera.hotel.active-run.v1": JSON.stringify(legacy),
  });
  const showcase = readDesktopModeSummaries(storage, new Map([
    ["showcase", legacy],
  ])).find(({ id }) => id === "showcase");
  assert.equal(showcase.status, "AVAILABLE");
  assert.equal(showcase.phase, "PLACEMENT");
  assert.equal(showcase.runSeed, 99);
});

test("rejects a validated checkpoint supplied under the wrong mode", async () => {
  const { readDesktopModeSummaries } = await modulePromise;
  const storage = storageFixture({
    "vespera.hotel.active-run.v2.endless": JSON.stringify(checkpoint("CAMPAIGN")),
  });
  const endless = readDesktopModeSummaries(storage, new Map([
    ["endless", checkpoint("CAMPAIGN")],
  ])).find(({ id }) => id === "endless");
  assert.equal(endless.status, "INVALID");
});

test("storage access failures are safely reported as invalid", async () => {
  const { readDesktopModeSummaries } = await modulePromise;
  const summaries = readDesktopModeSummaries(storageFixture({}, { throwOnGet: true }));
  assert.deepEqual(summaries.map(({ status }) => status), ["INVALID", "INVALID", "INVALID"]);
  assert.deepEqual(
    readDesktopModeSummaries(null).map(({ status }) => status),
    ["INVALID", "INVALID", "INVALID"],
  );
});

test("builds canonical mode and hub URLs without carrying runtime parameters", async () => {
  const { desktopHubUrl, desktopModeUrl } = await modulePromise;
  assert.equal(
    desktopModeUrl("vespera://app/index.html?seed=42&debug=1#hotel", "campaign"),
    "vespera://app/index.html?mode=campaign",
  );
  assert.equal(
    desktopModeUrl("https://example.test/game?mode=endless&seed=7", "showcase"),
    "https://example.test/index.html?mode=showcase",
  );
  assert.equal(
    desktopHubUrl("vespera://app/index.html?mode=endless&seed=7&debug=1#hotel"),
    "vespera://app/index.html",
  );
});

test("rejects unsupported modes and malformed desktop URLs", async () => {
  const { desktopHubUrl, desktopModeUrl } = await modulePromise;
  assert.throws(() => desktopModeUrl("vespera://app/index.html", "CAMPAIGN"), TypeError);
  assert.throws(() => desktopModeUrl("/index.html", "campaign"), TypeError);
  assert.throws(() => desktopHubUrl(" javascript:alert(1)"), TypeError);
  assert.throws(() => desktopHubUrl("file:///tmp/index.html"), TypeError);
});
