"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const {
  ACTIVE_RUN_STORAGE_PREFIX,
  FileStorageService,
  PROFILE_STORAGE_KEY,
  RUN_RECORD_STORAGE_KEY,
  readEnvelopeFile,
  storageFileName,
} = require("./file-storage.cjs");

function fixture(t) {
  const systemTemp = path.resolve(os.tmpdir());
  const root = fs.mkdtempSync(path.join(systemTemp, "vespera-file-storage-"));
  t.after(() => {
    const resolved = path.resolve(root);
    assert.ok(resolved.startsWith(`${systemTemp}${path.sep}`));
    fs.rmSync(resolved, { recursive: true, force: true });
  });
  return root;
}

test("separates profile, records, and active runs and survives restart", (t) => {
  const root = fixture(t);
  const activeKey = `${ACTIVE_RUN_STORAGE_PREFIX}.campaign`;
  const profile = JSON.stringify({ schema_version: 1, profile_id: "default" });
  const records = JSON.stringify([{ schema_version: 6, record_id: "R1" }]);
  const active = JSON.stringify({ schema_version: 6, mode_id: "CAMPAIGN", seed: 424242 });
  const storage = new FileStorageService(root);
  storage.setItem(PROFILE_STORAGE_KEY, profile);
  storage.setItem(RUN_RECORD_STORAGE_KEY, records);
  storage.setItem(activeKey, active);

  const expectedFiles = [
    "profile.v1.json",
    "run-records.v1.json",
    "active-run.v2.campaign.json",
  ];
  for (const fileName of expectedFiles) {
    assert.ok(fs.existsSync(path.join(root, fileName)));
    assert.ok(fs.existsSync(path.join(root, `${fileName}.bak`)));
  }

  const reopened = new FileStorageService(root);
  assert.equal(reopened.getItem(PROFILE_STORAGE_KEY), profile);
  assert.equal(reopened.getItem(RUN_RECORD_STORAGE_KEY), records);
  assert.equal(reopened.getItem(activeKey), active);
  assert.equal(reopened.diagnostics().authority, "FILE");
});

test("recovers the previous valid revision from backup and quarantines corruption", (t) => {
  const root = fixture(t);
  const storage = new FileStorageService(root);
  const first = JSON.stringify({ version: 1 });
  const second = JSON.stringify({ version: 2 });
  storage.setItem(PROFILE_STORAGE_KEY, first);
  storage.setItem(PROFILE_STORAGE_KEY, second);
  const primary = path.join(root, storageFileName(PROFILE_STORAGE_KEY));
  fs.writeFileSync(primary, "{truncated", "utf8");

  const recovered = new FileStorageService(root);
  assert.equal(recovered.getItem(PROFILE_STORAGE_KEY), first);
  assert.ok(recovered.diagnostics().recoveryEvents.some(
    (event) => event.code === "RECOVERED_FROM_BACKUP" && event.key === PROFILE_STORAGE_KEY,
  ));
  assert.ok(fs.readdirSync(path.join(root, "corrupt")).some(
    (fileName) => fileName.startsWith("profile.v1.json."),
  ));
});

test("bootstraps a dynamic active run when only its backup remains", (t) => {
  const root = fixture(t);
  const activeKey = `${ACTIVE_RUN_STORAGE_PREFIX}.showcase`;
  const active = JSON.stringify({ schema_version: 6, seed: 424242 });
  const storage = new FileStorageService(root);
  storage.setItem(activeKey, active);
  const primary = path.join(root, storageFileName(activeKey));
  fs.rmSync(primary);

  const reopened = new FileStorageService(root);
  const entries = new Map(reopened.bootstrap().entries);
  assert.equal(entries.get(activeKey), active);
  assert.ok(fs.existsSync(primary));
  assert.ok(reopened.diagnostics().recoveryEvents.some(
    (event) => event.code === "RECOVERED_FROM_BACKUP" && event.key === activeKey,
  ));
});

test("checksum tampering cannot become authoritative", (t) => {
  const root = fixture(t);
  const storage = new FileStorageService(root);
  const first = JSON.stringify({ version: 1 });
  const second = JSON.stringify({ version: 2 });
  storage.setItem(PROFILE_STORAGE_KEY, first);
  storage.setItem(PROFILE_STORAGE_KEY, second);
  const primary = path.join(root, storageFileName(PROFILE_STORAGE_KEY));
  const tampered = JSON.parse(fs.readFileSync(primary, "utf8"));
  tampered.payload = JSON.stringify({ version: 999 });
  fs.writeFileSync(primary, JSON.stringify(tampered), "utf8");

  const reopened = new FileStorageService(root);
  assert.equal(reopened.getItem(PROFILE_STORAGE_KEY), first);
});

test("tombstones prevent a deleted run from returning through backup recovery", (t) => {
  const root = fixture(t);
  const activeKey = `${ACTIVE_RUN_STORAGE_PREFIX}.endless`;
  const storage = new FileStorageService(root);
  storage.setItem(activeKey, JSON.stringify({ seed: 7 }));
  storage.removeItem(activeKey);
  assert.equal(storage.getItem(activeKey), null);

  const primary = path.join(root, storageFileName(activeKey));
  const backup = `${primary}.bak`;
  assert.equal(readEnvelopeFile(primary, activeKey).envelope.deleted, true);
  assert.equal(readEnvelopeFile(backup, activeKey).envelope.deleted, true);
  assert.equal(new FileStorageService(root).getItem(activeKey), null);
});

test("rejects unknown keys, unsafe modes, invalid JSON, and quota overflow", (t) => {
  const root = fixture(t);
  const storage = new FileStorageService(root, { maxValueBytes: 64, maxTotalBytes: 96 });
  assert.throws(() => storage.getItem("../../escape"), { code: "UNSUPPORTED_KEY" });
  assert.throws(
    () => storage.setItem(`${ACTIVE_RUN_STORAGE_PREFIX}.BAD/MODE`, "{}"),
    { code: "UNSUPPORTED_KEY" },
  );
  assert.throws(() => storage.setItem(PROFILE_STORAGE_KEY, "not json"), { code: "VALUE_NOT_JSON" });
  assert.throws(
    () => storage.setItem(PROFILE_STORAGE_KEY, JSON.stringify({ value: "x".repeat(100) })),
    { code: "VALUE_TOO_LARGE" },
  );
});

test("accepts a valid near-limit JSON value whose envelope needs escaping", (t) => {
  const root = fixture(t);
  const maxValueBytes = 64 * 1024;
  const storage = new FileStorageService(root, {
    maxValueBytes,
    maxTotalBytes: maxValueBytes,
  });
  const value = JSON.stringify({ value: "\\".repeat(30 * 1024) });
  assert.ok(Buffer.byteLength(value, "utf8") <= maxValueBytes);
  storage.setItem(PROFILE_STORAGE_KEY, value);
  assert.equal(new FileStorageService(root, {
    maxValueBytes,
    maxTotalBytes: maxValueBytes,
  }).getItem(PROFILE_STORAGE_KEY), value);
});

test("isolates different operating-system user data roots", (t) => {
  const parent = fixture(t);
  const firstRoot = path.join(parent, "user-a");
  const secondRoot = path.join(parent, "user-b");
  const first = new FileStorageService(firstRoot);
  const second = new FileStorageService(secondRoot);
  first.setItem(PROFILE_STORAGE_KEY, JSON.stringify({ owner: "A" }));
  assert.equal(second.getItem(PROFILE_STORAGE_KEY), null);
  second.setItem(PROFILE_STORAGE_KEY, JSON.stringify({ owner: "B" }));
  assert.notEqual(first.getItem(PROFILE_STORAGE_KEY), second.getItem(PROFILE_STORAGE_KEY));
});

test("reports bounded synchronous mutation latency evidence", (t) => {
  const root = fixture(t);
  const storage = new FileStorageService(root);
  for (let index = 0; index < 12; index += 1) {
    storage.setItem(PROFILE_STORAGE_KEY, JSON.stringify({ index }));
  }
  const diagnostics = storage.diagnostics();
  assert.equal(diagnostics.mutationCount, 12);
  assert.ok(Number.isFinite(diagnostics.writeP95Ms));
  assert.ok(diagnostics.writeP95Ms >= 0);
  assert.ok(diagnostics.writeMaxMs >= diagnostics.writeP95Ms);
});
