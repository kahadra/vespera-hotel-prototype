"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { performance } = require("node:perf_hooks");

const FILE_SCHEMA_VERSION = 1;
const PROFILE_STORAGE_KEY = "vespera.hotel.profile.v1";
const RUN_RECORD_STORAGE_KEY = "vespera.hotel.run-records.v1";
const LEGACY_ACTIVE_RUN_STORAGE_KEY = "vespera.hotel.active-run.v1";
const ACTIVE_RUN_STORAGE_PREFIX = "vespera.hotel.active-run.v2";
const ACTIVE_MODE_PATTERN = /^[a-z0-9][a-z0-9_-]{0,63}$/;
const DEFAULT_MAX_VALUE_BYTES = 8 * 1024 * 1024;
const DEFAULT_MAX_TOTAL_BYTES = 24 * 1024 * 1024;
const ENVELOPE_OVERHEAD_BYTES = 16 * 1024;

const EXACT_FILES = new Map([
  [PROFILE_STORAGE_KEY, "profile.v1.json"],
  [RUN_RECORD_STORAGE_KEY, "run-records.v1.json"],
  [LEGACY_ACTIVE_RUN_STORAGE_KEY, "active-run.v1.legacy.json"],
]);

class StorageContractError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "StorageContractError";
    this.code = code;
  }
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function activeModeFromKey(key) {
  const prefix = `${ACTIVE_RUN_STORAGE_PREFIX}.`;
  if (!key.startsWith(prefix)) return null;
  const mode = key.slice(prefix.length);
  return ACTIVE_MODE_PATTERN.test(mode) ? mode : null;
}

function storageFileName(key) {
  if (EXACT_FILES.has(key)) return EXACT_FILES.get(key);
  const mode = activeModeFromKey(key);
  if (mode) return `active-run.v2.${mode}.json`;
  throw new StorageContractError("UNSUPPORTED_KEY", `허용되지 않은 저장 키입니다: ${key}`);
}

function keyFromStorageFileName(fileName) {
  for (const [key, candidate] of EXACT_FILES.entries()) {
    if (candidate === fileName) return key;
  }
  const matched = /^active-run\.v2\.([a-z0-9][a-z0-9_-]{0,63})\.json$/.exec(fileName);
  return matched ? `${ACTIVE_RUN_STORAGE_PREFIX}.${matched[1]}` : null;
}

function checksumFields(envelope) {
  return JSON.stringify({
    file_schema_version: envelope.file_schema_version,
    storage_key: envelope.storage_key,
    revision: envelope.revision,
    written_at: envelope.written_at,
    deleted: envelope.deleted,
    payload: envelope.payload,
  });
}

function checksumFor(envelope) {
  return crypto.createHash("sha256").update(checksumFields(envelope), "utf8").digest("hex");
}

function createEnvelope(key, revision, payload, deleted = false, now = new Date()) {
  const envelope = {
    file_schema_version: FILE_SCHEMA_VERSION,
    storage_key: key,
    revision,
    written_at: now.toISOString(),
    deleted,
    payload: deleted ? null : payload,
  };
  return { ...envelope, checksum_sha256: checksumFor(envelope) };
}

function validateEnvelope(value, expectedKey) {
  if (!isPlainObject(value)
    || value.file_schema_version !== FILE_SCHEMA_VERSION
    || value.storage_key !== expectedKey
    || !Number.isSafeInteger(value.revision)
    || value.revision < 1
    || typeof value.written_at !== "string"
    || !Number.isFinite(Date.parse(value.written_at))
    || typeof value.deleted !== "boolean"
    || (value.deleted ? value.payload !== null : typeof value.payload !== "string")
    || typeof value.checksum_sha256 !== "string"
    || !/^[a-f0-9]{64}$/.test(value.checksum_sha256)) {
    return false;
  }
  return crypto.timingSafeEqual(
    Buffer.from(value.checksum_sha256, "hex"),
    Buffer.from(checksumFor(value), "hex"),
  );
}

function readEnvelopeFile(filePath, expectedKey, maxBytes = DEFAULT_MAX_VALUE_BYTES) {
  try {
    if (!fs.existsSync(filePath)) return { status: "missing", envelope: null };
    const stat = fs.statSync(filePath);
    // payload is already JSON text; embedding it in the envelope can escape every
    // quote/backslash once more, so the on-disk representation may approach 2x.
    if (!stat.isFile() || stat.size > (maxBytes * 2) + ENVELOPE_OVERHEAD_BYTES) {
      return { status: "invalid", envelope: null, code: "INVALID_FILE_SIZE" };
    }
    const parsed = JSON.parse(fs.readFileSync(filePath, "utf8"));
    if (!validateEnvelope(parsed, expectedKey)) {
      return { status: "invalid", envelope: null, code: "INVALID_ENVELOPE" };
    }
    return { status: "valid", envelope: parsed };
  } catch (error) {
    return { status: "invalid", envelope: null, code: error.code ?? "READ_ERROR" };
  }
}

function atomicWriteEnvelope(filePath, envelope, maxBytes) {
  const directory = path.dirname(filePath);
  fs.mkdirSync(directory, { recursive: true });
  const temporary = `${filePath}.tmp-${process.pid}-${crypto.randomBytes(6).toString("hex")}`;
  const serialized = `${JSON.stringify(envelope, null, 2)}\n`;
  let descriptor = null;
  try {
    descriptor = fs.openSync(temporary, "wx", 0o600);
    fs.writeFileSync(descriptor, serialized, "utf8");
    fs.fsyncSync(descriptor);
    fs.closeSync(descriptor);
    descriptor = null;
    const verified = readEnvelopeFile(temporary, envelope.storage_key, maxBytes);
    if (verified.status !== "valid") {
      throw new StorageContractError("TEMP_VERIFY_FAILED", "임시 저장 파일 검증에 실패했습니다.");
    }
    fs.renameSync(temporary, filePath);
  } finally {
    if (descriptor !== null) fs.closeSync(descriptor);
    if (fs.existsSync(temporary)) fs.rmSync(temporary, { force: true });
  }
}

class FileStorageService {
  constructor(rootDirectory, options = {}) {
    if (typeof rootDirectory !== "string" || rootDirectory.length === 0) {
      throw new StorageContractError("INVALID_ROOT", "저장 루트가 필요합니다.");
    }
    this.rootDirectory = path.resolve(rootDirectory);
    this.corruptDirectory = path.join(this.rootDirectory, "corrupt");
    this.maxValueBytes = options.maxValueBytes ?? DEFAULT_MAX_VALUE_BYTES;
    this.maxTotalBytes = options.maxTotalBytes ?? DEFAULT_MAX_TOTAL_BYTES;
    this.cache = new Map();
    this.revisions = new Map();
    this.loadedKeys = new Set();
    this.recoveryEvents = [];
    this.mutationDurationsMs = [];
    this.mutationCount = 0;
    this.lastErrorCode = null;
    fs.mkdirSync(this.rootDirectory, { recursive: true });
  }

  _pathsFor(key) {
    const fileName = storageFileName(key);
    const primary = path.join(this.rootDirectory, fileName);
    return { fileName, primary, backup: `${primary}.bak` };
  }

  _recordRecovery(code, key, detail = null) {
    this.recoveryEvents.push({ code, key, detail, observedAt: new Date().toISOString() });
  }

  _cleanupTemporaryFiles(fileName, key) {
    for (const candidate of fs.readdirSync(this.rootDirectory, { withFileTypes: true })) {
      if (!candidate.isFile() || !candidate.name.startsWith(`${fileName}.tmp-`)) continue;
      fs.rmSync(path.join(this.rootDirectory, candidate.name), { force: true });
      this._recordRecovery("STALE_TEMP_REMOVED", key);
    }
  }

  _quarantine(filePath, key, code) {
    if (!fs.existsSync(filePath)) return;
    fs.mkdirSync(this.corruptDirectory, { recursive: true });
    const suffix = `${Date.now()}-${crypto.randomBytes(4).toString("hex")}`;
    const destination = path.join(
      this.corruptDirectory,
      `${path.basename(filePath)}.${suffix}.corrupt`,
    );
    fs.renameSync(filePath, destination);
    this._recordRecovery("CORRUPT_FILE_QUARANTINED", key, code);
  }

  _loadKey(key) {
    const { fileName, primary, backup } = this._pathsFor(key);
    this._cleanupTemporaryFiles(fileName, key);
    let primaryResult = readEnvelopeFile(primary, key, this.maxValueBytes);
    let backupResult = readEnvelopeFile(backup, key, this.maxValueBytes);

    if (primaryResult.status === "valid") {
      const envelope = primaryResult.envelope;
      if (envelope.deleted && (
        backupResult.status !== "valid"
        || !backupResult.envelope.deleted
        || backupResult.envelope.revision < envelope.revision
      )) {
        if (backupResult.status === "invalid") this._quarantine(backup, key, backupResult.code);
        atomicWriteEnvelope(backup, envelope, this.maxValueBytes);
        backupResult = { status: "valid", envelope };
        this._recordRecovery("TOMBSTONE_BACKUP_HEALED", key);
      }
      this.cache.set(key, envelope.deleted ? null : envelope.payload);
      this.revisions.set(key, envelope.revision);
      this.loadedKeys.add(key);
      return;
    }

    if (primaryResult.status === "invalid") {
      this._quarantine(primary, key, primaryResult.code);
      primaryResult = { status: "missing", envelope: null };
    }
    if (backupResult.status === "valid") {
      atomicWriteEnvelope(primary, backupResult.envelope, this.maxValueBytes);
      this.cache.set(key, backupResult.envelope.deleted ? null : backupResult.envelope.payload);
      this.revisions.set(key, backupResult.envelope.revision);
      this.loadedKeys.add(key);
      this._recordRecovery("RECOVERED_FROM_BACKUP", key);
      return;
    }
    if (backupResult.status === "invalid") this._quarantine(backup, key, backupResult.code);
    this.cache.set(key, null);
    this.revisions.set(key, 0);
    this.loadedKeys.add(key);
  }

  _ensureLoaded(key) {
    storageFileName(key);
    if (!this.loadedKeys.has(key)) this._loadKey(key);
  }

  _candidateKeys() {
    const keys = new Set(EXACT_FILES.keys());
    for (const candidate of fs.readdirSync(this.rootDirectory, { withFileTypes: true })) {
      if (!candidate.isFile()) continue;
      const candidateName = candidate.name.endsWith(".bak")
        ? candidate.name.slice(0, -4)
        : candidate.name;
      const key = keyFromStorageFileName(candidateName);
      if (key) keys.add(key);
    }
    return [...keys];
  }

  _validateValue(value) {
    if (typeof value !== "string") {
      throw new StorageContractError("VALUE_NOT_STRING", "저장 값은 문자열이어야 합니다.");
    }
    const bytes = Buffer.byteLength(value, "utf8");
    if (bytes > this.maxValueBytes) {
      throw new StorageContractError("VALUE_TOO_LARGE", "저장 값이 파일별 제한을 초과했습니다.");
    }
    try {
      JSON.parse(value);
    } catch {
      throw new StorageContractError("VALUE_NOT_JSON", "게임 저장 값은 유효한 JSON이어야 합니다.");
    }
    return bytes;
  }

  _totalBytesWith(key, valueBytes) {
    let total = valueBytes;
    for (const [candidateKey, value] of this.cache.entries()) {
      if (candidateKey === key || value === null) continue;
      total += Buffer.byteLength(value, "utf8");
    }
    return total;
  }

  _measureMutation(callback) {
    const started = performance.now();
    try {
      const result = callback();
      this.lastErrorCode = null;
      return result;
    } catch (error) {
      this.lastErrorCode = error.code ?? "WRITE_ERROR";
      throw error;
    } finally {
      this.mutationCount += 1;
      this.mutationDurationsMs.push(performance.now() - started);
      if (this.mutationDurationsMs.length > 512) this.mutationDurationsMs.shift();
    }
  }

  bootstrap() {
    for (const key of this._candidateKeys()) this._ensureLoaded(key);
    return {
      entries: [...this.cache.entries()].filter(([, value]) => value !== null),
      revisions: Object.fromEntries(this.revisions),
      recoveryEvents: this.recoveryEvents.map((event) => ({ ...event })),
    };
  }

  getItem(key) {
    const normalizedKey = String(key);
    this._ensureLoaded(normalizedKey);
    return this.cache.get(normalizedKey) ?? null;
  }

  setItem(key, value) {
    const normalizedKey = String(key);
    this._ensureLoaded(normalizedKey);
    const valueBytes = this._validateValue(value);
    if (this._totalBytesWith(normalizedKey, valueBytes) > this.maxTotalBytes) {
      throw new StorageContractError("TOTAL_QUOTA_EXCEEDED", "전체 저장 용량 제한을 초과했습니다.");
    }
    return this._measureMutation(() => {
      const revision = (this.revisions.get(normalizedKey) ?? 0) + 1;
      const envelope = createEnvelope(normalizedKey, revision, value, false);
      const { primary, backup } = this._pathsFor(normalizedKey);
      const current = readEnvelopeFile(primary, normalizedKey, this.maxValueBytes);
      if (current.status === "valid") {
        atomicWriteEnvelope(backup, current.envelope, this.maxValueBytes);
      }
      atomicWriteEnvelope(primary, envelope, this.maxValueBytes);
      if (current.status !== "valid") atomicWriteEnvelope(backup, envelope, this.maxValueBytes);
      this.cache.set(normalizedKey, value);
      this.revisions.set(normalizedKey, revision);
      return revision;
    });
  }

  removeItem(key) {
    const normalizedKey = String(key);
    this._ensureLoaded(normalizedKey);
    if (this.cache.get(normalizedKey) === null) return this.revisions.get(normalizedKey) ?? 0;
    return this._measureMutation(() => {
      const revision = (this.revisions.get(normalizedKey) ?? 0) + 1;
      const envelope = createEnvelope(normalizedKey, revision, null, true);
      const { primary, backup } = this._pathsFor(normalizedKey);
      atomicWriteEnvelope(backup, envelope, this.maxValueBytes);
      atomicWriteEnvelope(primary, envelope, this.maxValueBytes);
      this.cache.set(normalizedKey, null);
      this.revisions.set(normalizedKey, revision);
      return revision;
    });
  }

  diagnostics() {
    const sorted = [...this.mutationDurationsMs].sort((left, right) => left - right);
    const percentileIndex = sorted.length ? Math.ceil(sorted.length * 0.95) - 1 : -1;
    return {
      authority: "FILE",
      fileSchemaVersion: FILE_SCHEMA_VERSION,
      loadedKeyCount: this.loadedKeys.size,
      liveEntryCount: [...this.cache.values()].filter((value) => value !== null).length,
      mutationCount: this.mutationCount,
      writeP95Ms: percentileIndex >= 0 ? sorted[percentileIndex] : null,
      writeMaxMs: sorted.length ? sorted.at(-1) : null,
      recoveryEvents: this.recoveryEvents.map((event) => ({ ...event })),
      lastErrorCode: this.lastErrorCode,
    };
  }
}

module.exports = {
  ACTIVE_RUN_STORAGE_PREFIX,
  DEFAULT_MAX_TOTAL_BYTES,
  DEFAULT_MAX_VALUE_BYTES,
  FILE_SCHEMA_VERSION,
  FileStorageService,
  LEGACY_ACTIVE_RUN_STORAGE_KEY,
  PROFILE_STORAGE_KEY,
  RUN_RECORD_STORAGE_KEY,
  StorageContractError,
  checksumFor,
  keyFromStorageFileName,
  readEnvelopeFile,
  storageFileName,
  validateEnvelope,
};
