#!/usr/bin/env python3
"""Run the cleanliness/stayover contract against the real JavaScript modules."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def find_node() -> tuple[Path, dict[str, str]]:
    """Return a Node-compatible executable and any required environment."""
    on_path = shutil.which("node")
    if on_path:
        return Path(on_path), {}

    portable = sorted(
        (ROOT / ".tmp" / "node-bootstrap" / "runtime-complete").glob(
            "node-v*-win-x64/node.exe"
        )
    )
    if portable:
        return portable[-1], {}

    electron = ROOT / "node_modules" / "electron" / "dist" / "electron.exe"
    if electron.exists():
        return electron, {"ELECTRON_RUN_AS_NODE": "1"}

    raise FileNotFoundError(
        "Node.js was not found on PATH, in .tmp/node-bootstrap, or in node_modules/electron."
    )


def module_uri(relative_path: str) -> str:
    return (ROOT / relative_path).resolve().as_uri()


def javascript_test() -> str:
    data_path = json.dumps(str((ROOT / "data" / "prototype_v1.json").resolve()))
    data_uri = json.dumps(module_uri("src/data.js"))
    rules_uri = json.dumps(module_uri("src/rules.js"))
    scoring_uri = json.dumps(module_uri("src/scoring.js"))
    state_uri = json.dumps(module_uri("src/state.js"))
    save_uri = json.dumps(module_uri("src/save.js"))

    return f"""
import assert from "node:assert/strict";
import fs from "node:fs";
import {{ createIndexes, getGuestRules, validateData }} from {data_uri};
import {{ evaluatePlacement }} from {rules_uri};
import {{ calculateNightResult }} from {scoring_uri};
import {{ GameController, PHASES }} from {state_uri};
import {{
  RUN_SAVE_SCHEMA_VERSION,
  activeRunStorageKey,
  createRunSave,
  readActiveRunSave,
}} from {save_uri};

const source = JSON.parse(fs.readFileSync({data_path}, "utf8"));
source.indexes = createIndexes(source);
validateData(source, source.indexes);

function cloneIndexed(value) {{
  const clone = structuredClone(value);
  delete clone.indexes;
  clone.indexes = createIndexes(clone);
  return clone;
}}

function memoryStorage() {{
  const entries = new Map();
  return {{
    getItem(key) {{ return entries.has(key) ? entries.get(key) : null; }},
    setItem(key, value) {{ entries.set(key, String(value)); }},
    removeItem(key) {{ entries.delete(key); }},
  }};
}}

function controllerFor(seed) {{
  const controller = new GameController(source, {{ seed, storage: memoryStorage() }});
  controller.state.phase = PHASES.UPGRADE;
  controller.state.gold = 100;
  controller.state.hotelReputation = 5;
  return controller;
}}

function collectKeyMatches(value, needle, path = "$", matches = []) {{
  if (Array.isArray(value)) {{
    value.forEach((entry, index) => collectKeyMatches(entry, needle, `${{path}}[${{index}}]`, matches));
    return matches;
  }}
  if (!value || typeof value !== "object") return matches;
  for (const [key, child] of Object.entries(value)) {{
    const childPath = `${{path}}.${{key}}`;
    if (key.toLowerCase().includes(needle)) matches.push(childPath);
    collectKeyMatches(child, needle, childPath, matches);
  }}
  return matches;
}}

const checks = [];

// One room-condition axis: live state and guest data expose cleanliness, never durability.
assert.deepEqual(collectKeyMatches(source, "durability"), []);
assert.ok(source.guests.every((guest) => Number.isFinite(guest.cleanliness_impact)));
const shapeController = controllerFor(1001);
for (const [roomId, condition] of Object.entries(shapeController.state.roomConditions)) {{
  assert.deepEqual(Object.keys(condition).sort(), ["cleanliness"], roomId);
  assert.equal(condition.cleanliness, 100, roomId);
}}
checks.push("single_cleanliness_shape");

// Common species/rank layers cannot silently award and penalize the same
// condition. Personal exceptions remain legal and are tested by Garr below.
const commonConflictData = cloneIndexed(source);
commonConflictData.indexes.ranks.SSR.soft_dislikes[2] = {{
  type: "ROOM_HAS",
  attribute: "sunny",
  points: -2,
  ignored_at_prestige_gap: 3,
  label: "conflicting sunny dislike",
}};
assert.throws(
  () => validateData(commonConflictData, commonConflictData.indexes),
  /공통 계층에서 같은 조건/,
);
const garrRules = getGuestRules(source, "G06_GARR");
assert.ok(garrRules.personalPreferences.some((rule) => rule.type === "ELEVATOR_DISTANCE_AT_MOST"));
assert.ok(garrRules.rankDislikes.some((rule) => rule.type === "ELEVATOR_DISTANCE_AT_MOST"));
checks.push("common_rule_contradiction_lint_with_personal_exception");

// Isolate cleanliness so the actual rank influence, rather than an unrelated preference,
// explains the reputation difference.
const satisfactionData = cloneIndexed(source);
for (const species of satisfactionData.species) {{
  species.soft_preferences = [];
  species.soft_dislikes = [];
  species.synergy_thresholds = [];
  species.hidden_preferences_by_rank = {{ N: [], R: [], SR: [], SSR: [] }};
}}
for (const rank of satisfactionData.ranks) {{
  rank.soft_preferences = [];
  rank.soft_dislikes = [];
}}
for (const guest of satisfactionData.guests) {{
  guest.soft_preferences = [];
  guest.soft_dislikes = [];
}}
satisfactionData.species_conflicts = [];
satisfactionData.indexes = createIndexes(satisfactionData);

function resultFor(guestId, roomId, cleanliness) {{
  return calculateNightResult(
    satisfactionData,
    satisfactionData.scenarios[0],
    [guestId],
    [],
    {{ [guestId]: roomId }},
    {{
      roomConditions: {{ [roomId]: {{ cleanliness }} }},
      protectedRoomIds: [roomId],
      hotelReputation: 0,
    }},
  );
}}

const nClean = resultFor("G01_LUNE", "F1-A", 100);
const nDirty = resultFor("G01_LUNE", "F1-A", 0);
const srClean = resultFor("G03_LADY_NOX", "F1-B", 100);
const srDirty = resultFor("G03_LADY_NOX", "F1-B", 0);
for (const result of [nClean, nDirty, srClean, srDirty]) assert.equal(result.valid, true);
assert.equal(nClean.guestReviews[0].satisfaction, 0);
assert.equal(srClean.guestReviews[0].satisfaction, 0);
assert.equal(nDirty.guestReviews[0].satisfaction, -6);
assert.equal(srDirty.guestReviews[0].satisfaction, -6);
assert.equal(nDirty.reputationDelta, -1);
assert.equal(srDirty.reputationDelta, -4);
assert.equal(srDirty.guestReviews[0].reputationInfluence, 4);
checks.push("dirty_satisfaction_rank_weighted_reputation");

// Paladin noise is not a species-wide hard rule. It remains a rank hard rule at SR.
const paladin = source.indexes.species.PALADIN;
assert.deepEqual(paladin.hard_constraints, []);
const rowanRules = getGuestRules(source, "G13_ROWAN");
assert.deepEqual(rowanRules.commonRequired, []);
assert.equal(rowanRules.hard.some((rule) => rule.type === "ROOM_NOT_HAS" && rule.attribute === "noisy"), false);
const aureliaRules = getGuestRules(source, "G15_AURELIA");
assert.deepEqual(aureliaRules.commonRequired, []);
assert.equal(
  aureliaRules.rankRequired.some((rule) => rule.type === "ROOM_NOT_HAS" && rule.attribute === "noisy"),
  true,
);
assert.equal(
  evaluatePlacement(source, ["G15_AURELIA"], {{ G15_AURELIA: "F1-A" }}).valid,
  false,
);
checks.push("paladin_common_vs_sr_noise_constraint");

// The manager can proactively clean an occupied stayover room during intermission.
const proactive = controllerFor(2002);
proactive.state.stayovers = {{ G03_LADY_NOX: {{ roomId: "F1-B", remainingNights: 1 }} }};
proactive.state.roomConditions["F1-B"] = {{ cleanliness: 63 }};
const proactiveGold = proactive.state.gold;
assert.equal(proactive.serviceRoom("F1-B"), true);
assert.equal(proactive.state.gold, proactiveGold - source.balance.room_service_cost);
assert.deepEqual(proactive.state.roomConditions["F1-B"], {{ cleanliness: 100 }});
checks.push("proactive_stayover_cleaning");

function prepareRequestController(seed) {{
  const controller = controllerFor(seed);
  controller.state.stayovers = {{
    G03_LADY_NOX: {{ roomId: "F1-B", remainingNights: 1 }},
    G11_CIRCE: {{ roomId: "F2-B", remainingNights: 1 }},
    G15_AURELIA: {{ roomId: "F3-B", remainingNights: 1 }},
  }};
  controller.state.roomConditions["F1-B"] = {{ cleanliness: 62 }};
  controller.state.roomConditions["F2-B"] = {{ cleanliness: 78 }};
  controller.state.roomConditions["F3-B"] = {{ cleanliness: 100 }};
  return controller;
}}

let triggerSeed = null;
for (let seed = 1; seed <= 4096; seed += 1) {{
  const candidate = prepareRequestController(seed);
  if (candidate.openStayoverCleaningRequest()) {{
    triggerSeed = seed;
    break;
  }}
}}
assert.notEqual(triggerSeed, null, "a request-triggering seed should exist");

const firstSeeded = prepareRequestController(triggerSeed);
assert.deepEqual(
  firstSeeded.dirtyStayoverCleaningCandidates().map((entry) => entry.guestId).sort(),
  ["G03_LADY_NOX", "G11_CIRCE"],
);
assert.equal(firstSeeded.openStayoverCleaningRequest(), true);
const seededRequest = structuredClone(firstSeeded.state.pendingStayoverCleaningRequest);
assert.ok(["G03_LADY_NOX", "G11_CIRCE"].includes(seededRequest.guestId));
assert.notEqual(seededRequest.guestId, "G15_AURELIA");
const rngAfterRequest = structuredClone(firstSeeded.state.rngState);
assert.equal(firstSeeded.openStayoverCleaningRequest(), true);
assert.deepEqual(firstSeeded.state.pendingStayoverCleaningRequest, seededRequest);
assert.deepEqual(firstSeeded.state.rngState, rngAfterRequest);

const repeatedSeed = prepareRequestController(triggerSeed);
assert.equal(repeatedSeed.openStayoverCleaningRequest(), true);
assert.deepEqual(repeatedSeed.state.pendingStayoverCleaningRequest, seededRequest);
checks.push("seeded_dirty_only_one_request_per_intermission");

const accepted = prepareRequestController(triggerSeed);
accepted.state.nightResults = [{{ reputationDelta: 0 }}];
assert.equal(accepted.openStayoverCleaningRequest(), true);
const acceptedRequest = structuredClone(accepted.state.pendingStayoverCleaningRequest);
const acceptedGold = accepted.state.gold;
const acceptedReputation = accepted.state.hotelReputation;
assert.equal(accepted.resolveStayoverCleaningRequest(true), true);
assert.equal(accepted.state.gold, acceptedGold - acceptedRequest.serviceCost);
assert.equal(accepted.state.hotelReputation, acceptedReputation + 1);
assert.deepEqual(accepted.state.roomConditions[acceptedRequest.roomId], {{ cleanliness: 100 }});
assert.ok(accepted.state.stayoverCleaningRequestGuestIds.includes(acceptedRequest.guestId));
assert.equal(accepted.state.pendingStayoverCleaningRequest, null);
assert.equal(accepted.state.nightResults[0].reputationDelta, 1);
assert.equal(accepted.state.nightResults[0].intermissionReputationDelta, 1);
assert.deepEqual(accepted.state.nightResults[0].intermissionEvents, [{{
  type: "STAYOVER_CLEANING_REQUEST",
  requestId: acceptedRequest.requestId,
  guestId: acceptedRequest.guestId,
  roomId: acceptedRequest.roomId,
  outcome: "ACCEPTED",
  reputationDelta: 1,
}}]);
assert.equal(accepted.openStayoverCleaningRequest(), false);

// Simulate the next intermission of the same stay: even if dirty again, the same guest
// cannot make another request.
accepted.state.stayoverCleaningRequestChecked = false;
accepted.state.declinedStayoverCleaningRoomIds = [];
accepted.state.stayovers = {{
  [acceptedRequest.guestId]: {{ roomId: acceptedRequest.roomId, remainingNights: 1 }},
}};
accepted.state.roomConditions[acceptedRequest.roomId] = {{ cleanliness: 55 }};
assert.deepEqual(accepted.dirtyStayoverCleaningCandidates(), []);
assert.equal(accepted.openStayoverCleaningRequest(), false);
checks.push("request_accept_cost_cleanliness_reputation_once_per_stay");

const rejected = prepareRequestController(triggerSeed);
assert.equal(rejected.openStayoverCleaningRequest(), true);
const rejectedRequest = structuredClone(rejected.state.pendingStayoverCleaningRequest);
const rejectedGold = rejected.state.gold;
const rejectedReputation = rejected.state.hotelReputation;
const rejectedCondition = structuredClone(rejected.state.roomConditions[rejectedRequest.roomId]);
assert.equal(rejected.resolveStayoverCleaningRequest(false), true);
assert.equal(rejected.state.gold, rejectedGold);
assert.equal(rejected.state.hotelReputation, rejectedReputation - 1);
assert.deepEqual(rejected.state.roomConditions[rejectedRequest.roomId], rejectedCondition);
assert.ok(rejected.state.declinedStayoverCleaningRoomIds.includes(rejectedRequest.roomId));
assert.equal(rejected.serviceRoom(rejectedRequest.roomId), false);
assert.deepEqual(rejected.state.roomConditions[rejectedRequest.roomId], rejectedCondition);
checks.push("request_reject_penalty_dirty_and_same_intermission_block");

// Schema 6 saves migrate both current state and checkpoint-era room shapes to
// schema 7, while a malformed schema 7 save cannot smuggle durability back in.
const migrationController = controllerFor(5005);
migrationController.state.roomConditions["F1-A"] = {{ cleanliness: 72 }};
migrationController.state.lastRoomWear = [{{
  guestId: "G01_LUNE",
  roomId: "F1-A",
  cleanlinessLoss: 8,
  cleanliness: 72,
}}];
const migrationCheckpoint = structuredClone(migrationController.state);
migrationCheckpoint.phase = PHASES.RESERVATION;
const modernSave = createRunSave(source, migrationController.state, migrationCheckpoint);
assert.equal(modernSave.schema_version, RUN_SAVE_SCHEMA_VERSION);
const legacySave = structuredClone(modernSave);
legacySave.schema_version = 6;
legacySave.data_schema_version = 4;
for (const snapshot of [legacySave.state, legacySave.stage_checkpoint]) {{
  for (const condition of Object.values(snapshot.roomConditions)) condition.durability = 100;
  snapshot.lastRoomWear[0].durabilityLoss = 2;
  snapshot.lastRoomWear[0].durability = 98;
  delete snapshot.pendingStayoverCleaningRequest;
  delete snapshot.stayoverCleaningRequestChecked;
  delete snapshot.declinedStayoverCleaningRoomIds;
  delete snapshot.stayoverCleaningRequestGuestIds;
}}
const migrationStorage = memoryStorage();
migrationStorage.setItem(activeRunStorageKey(source), JSON.stringify(legacySave));
const migratedSave = readActiveRunSave(source, migrationStorage);
assert.equal(migratedSave.schema_version, 7);
assert.deepEqual(migratedSave.state.roomConditions["F1-A"], {{ cleanliness: 72 }});
assert.deepEqual(migratedSave.state.lastRoomWear[0], {{
  guestId: "G01_LUNE",
  roomId: "F1-A",
  cleanlinessLoss: 8,
  cleanliness: 72,
}});
assert.deepEqual(migratedSave.stage_checkpoint.roomConditions["F1-A"], {{ cleanliness: 72 }});
assert.deepEqual(migratedSave.stage_checkpoint.lastRoomWear[0], migratedSave.state.lastRoomWear[0]);
assert.equal(migratedSave.stage_checkpoint.pendingStayoverCleaningRequest, null);
assert.equal(migratedSave.stage_checkpoint.stayoverCleaningRequestChecked, false);
assert.equal(migratedSave.state.pendingStayoverCleaningRequest, null);
assert.equal(migratedSave.state.stayoverCleaningRequestChecked, false);

const malformedCurrentSave = structuredClone(modernSave);
malformedCurrentSave.state.roomConditions["F1-A"].durability = 100;
const malformedStorage = memoryStorage();
malformedStorage.setItem(activeRunStorageKey(source), JSON.stringify(malformedCurrentSave));
assert.equal(readActiveRunSave(source, malformedStorage), null);
checks.push("schema6_to_schema7_migration_and_schema7_strictness");

process.stdout.write(JSON.stringify({{
  status: "PASS",
  schema: source.schema_version,
  triggerSeed,
  roomServiceCost: source.balance.room_service_cost,
  cleanlinessPenalty: nDirty.guestReviews[0].satisfaction,
  rankWeightedReputation: {{ N: nDirty.reputationDelta, SR: srDirty.reputationDelta }},
  checks,
}}, null, 2));
"""


def main() -> int:
    try:
        node, extra_env = find_node()
    except FileNotFoundError as error:
        print(f"SKIP: {error}", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env.update(extra_env)
    completed = subprocess.run(
        [str(node), "--no-warnings", "--input-type=module", "--eval", javascript_test()],
        cwd=ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )

    if completed.stdout:
        print(completed.stdout)
    if completed.stderr:
        print(completed.stderr, file=sys.stderr)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
