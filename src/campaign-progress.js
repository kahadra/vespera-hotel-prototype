export const CAMPAIGN_PROGRESS_SCHEMA_VERSION = 2;
export const CAMPAIGN_BASE_STAGE_LIMIT = 56;
export const CAMPAIGN_TRUE_STAGE_LIMIT = 70;
export const CAMPAIGN_TRUE_ENTRY_GATE_ID = "BASE_DEBT_CLEARED_AT_STAGE_56";
export const CAMPAIGN_GREYBOX_TEMPLATE_POLICY_ID = "GREYBOX_ONLY_STAGE_MODULO";
export const CAMPAIGN_OPERATION_KINDS = Object.freeze(["NORMAL"]);
export const CAMPAIGN_PROGRESS_STATUSES = Object.freeze([
  "ACTIVE",
  "BASE_COMPLETE",
  "TRUE_COMPLETE",
]);

export const FORMAL_CAMPAIGN_PROGRESS_CONFIG = Object.freeze({
  id: "FORMAL_CAMPAIGN_PROGRESS",
  version: 1,
  base_stage_limit: CAMPAIGN_BASE_STAGE_LIMIT,
  true_stage_limit: CAMPAIGN_TRUE_STAGE_LIMIT,
  true_entry_gate_id: CAMPAIGN_TRUE_ENTRY_GATE_ID,
  scenario_template_policy_id: CAMPAIGN_GREYBOX_TEMPLATE_POLICY_ID,
  scenario_templates_production_ready: false,
  scenario_template_count: 5,
  template_offset: 0,
});

const CONFIG_KEYS = Object.freeze([
  "id",
  "version",
  "base_stage_limit",
  "true_stage_limit",
  "true_entry_gate_id",
  "scenario_template_policy_id",
  "scenario_templates_production_ready",
  "scenario_template_count",
  "template_offset",
]);

const PROGRESS_STATE_KEYS = Object.freeze([
  "type",
  "schemaVersion",
  "configId",
  "configVersion",
  "completedStageCount",
  "currentStageNumber",
  "stageLimit",
  "trueExtensionUnlocked",
  "status",
  "operationRecords",
]);

const OPERATION_DESCRIPTOR_KEYS = Object.freeze([
  "type",
  "stageNumber",
  "operationKind",
  "templateIndex",
  "templatePolicyId",
  "templateProductionReady",
]);

function assert(condition, message) {
  if (!condition) throw new Error(`Invalid campaign progress: ${message}`);
}

function nonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function positiveSafeInteger(value) {
  return Number.isSafeInteger(value) && value > 0;
}

function nonNegativeSafeInteger(value) {
  return Number.isSafeInteger(value) && value >= 0;
}

function unsigned32Integer(value) {
  return Number.isInteger(value) && value >= 0 && value <= 0xFFFFFFFF;
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isDenseArray(value) {
  if (!Array.isArray(value)) return false;
  for (let index = 0; index < value.length; index += 1) {
    if (!Object.prototype.hasOwnProperty.call(value, index)) return false;
  }
  return true;
}

function exactKeys(value, expectedKeys) {
  if (!isPlainObject(value)) return false;
  const actual = Object.keys(value).sort();
  const expected = [...expectedKeys].sort();
  return actual.length === expected.length
    && actual.every((key, index) => key === expected[index]);
}

function sameJson(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

export function validateCampaignProgressConfig(config) {
  assert(exactKeys(config, CONFIG_KEYS), "config has an invalid shape");
  assert(nonEmptyString(config.id), "config.id must be a non-empty string");
  assert(positiveSafeInteger(config.version), "config.version must be a positive safe integer");
  assert(config.base_stage_limit === CAMPAIGN_BASE_STAGE_LIMIT,
    `config.base_stage_limit must be ${CAMPAIGN_BASE_STAGE_LIMIT}`);
  assert(config.true_stage_limit === CAMPAIGN_TRUE_STAGE_LIMIT,
    `config.true_stage_limit must be ${CAMPAIGN_TRUE_STAGE_LIMIT}`);
  assert(config.true_stage_limit > config.base_stage_limit,
    "config.true_stage_limit must exceed config.base_stage_limit");
  assert(config.true_entry_gate_id === CAMPAIGN_TRUE_ENTRY_GATE_ID,
    `config.true_entry_gate_id must be ${CAMPAIGN_TRUE_ENTRY_GATE_ID}`);
  assert(config.scenario_template_policy_id === CAMPAIGN_GREYBOX_TEMPLATE_POLICY_ID,
    `config.scenario_template_policy_id must be ${CAMPAIGN_GREYBOX_TEMPLATE_POLICY_ID}`);
  assert(config.scenario_templates_production_ready === false,
    "modulo scenario template selection must remain GREYBOX_ONLY");
  assert(positiveSafeInteger(config.scenario_template_count),
    "config.scenario_template_count must be a positive safe integer");
  assert(nonNegativeSafeInteger(config.template_offset),
    "config.template_offset must be a non-negative safe integer");
  assert(config.template_offset < config.scenario_template_count,
    "config.template_offset must be smaller than scenario_template_count");
  return true;
}

export function campaignScenarioTemplateIndex(config, stageNumber) {
  validateCampaignProgressConfig(config);
  assert(positiveSafeInteger(stageNumber), "stageNumber must be a positive safe integer");
  assert(stageNumber <= config.true_stage_limit,
    "stageNumber must remain within the formal campaign limit");
  return (stageNumber - 1 + config.template_offset) % config.scenario_template_count;
}

function validateOperationDescriptor(config, operation) {
  assert(exactKeys(operation, OPERATION_DESCRIPTOR_KEYS),
    "operation descriptor has an invalid shape");
  assert(operation.type === "CAMPAIGN_OPERATION", "operation.type is unknown");
  assert(positiveSafeInteger(operation.stageNumber),
    "operation.stageNumber must be a positive safe integer");
  assert(operation.stageNumber <= config.true_stage_limit,
    "operation.stageNumber exceeds the formal campaign limit");
  assert(operation.operationKind === "NORMAL",
    "operation.operationKind must be NORMAL");
  assert(nonNegativeSafeInteger(operation.templateIndex),
    "operation.templateIndex must be a non-negative safe integer");
  assert(operation.templateIndex === campaignScenarioTemplateIndex(config, operation.stageNumber),
    "operation.templateIndex does not match deterministic template selection");
  assert(operation.templatePolicyId === CAMPAIGN_GREYBOX_TEMPLATE_POLICY_ID,
    "operation.templatePolicyId must identify the GREYBOX_ONLY selector");
  assert(operation.templateProductionReady === false,
    "modulo template assignment cannot be marked production ready");
  return true;
}

function operationDescriptor(config, stageNumber) {
  const operation = {
    type: "CAMPAIGN_OPERATION",
    stageNumber,
    operationKind: "NORMAL",
    templateIndex: campaignScenarioTemplateIndex(config, stageNumber),
    templatePolicyId: CAMPAIGN_GREYBOX_TEMPLATE_POLICY_ID,
    templateProductionReady: false,
  };
  validateOperationDescriptor(config, operation);
  return operation;
}

export function campaignResultIdentity(config, operation) {
  validateCampaignProgressConfig(config);
  validateOperationDescriptor(config, operation);
  return {
    stageNumber: operation.stageNumber,
    operationKind: "NORMAL",
    templateIndex: operation.templateIndex,
  };
}

export function campaignOperationId(config, runSeed, operation) {
  validateCampaignProgressConfig(config);
  assert(unsigned32Integer(runSeed), "runSeed must be an unsigned 32-bit integer");
  validateOperationDescriptor(config, operation);
  return `${config.id}@${config.version}:${runSeed}:${operation.stageNumber}`;
}

function cloneOperationRecords(records) {
  return records.map((record) => ({
    resultIdentity: { ...record.resultIdentity },
  }));
}

function expectedStatus(progress) {
  if (progress.completedStageCount < progress.stageLimit) return "ACTIVE";
  return progress.trueExtensionUnlocked ? "TRUE_COMPLETE" : "BASE_COMPLETE";
}

function validateOperationRecord(config, record, index) {
  const owner = `operationRecords[${index}]`;
  assert(exactKeys(record, ["resultIdentity"]), `${owner} has an invalid shape`);
  assert(exactKeys(record.resultIdentity, ["stageNumber", "operationKind", "templateIndex"]),
    `${owner}.resultIdentity must contain only the append identity fields`);
  const identity = record.resultIdentity;
  assert(identity.stageNumber === index + 1,
    `${owner}.resultIdentity.stageNumber must preserve sequential stage authority`);
  assert(identity.operationKind === "NORMAL",
    `${owner}.resultIdentity.operationKind must be NORMAL`);
  assert(identity.templateIndex === campaignScenarioTemplateIndex(config, identity.stageNumber),
    `${owner}.resultIdentity.templateIndex is not deterministic`);
}

export function validateCampaignProgressState(config, progress) {
  validateCampaignProgressConfig(config);
  assert(exactKeys(progress, PROGRESS_STATE_KEYS), "progress has an invalid shape");
  assert(progress.type === "CAMPAIGN_PROGRESS_STATE", "progress.type is unknown");
  assert(progress.schemaVersion === CAMPAIGN_PROGRESS_SCHEMA_VERSION,
    "progress.schemaVersion is unsupported");
  assert(progress.configId === config.id, "progress.configId does not match config");
  assert(progress.configVersion === config.version,
    "progress.configVersion does not match config");
  assert(nonNegativeSafeInteger(progress.completedStageCount),
    "progress.completedStageCount must be a non-negative safe integer");
  assert(typeof progress.trueExtensionUnlocked === "boolean",
    "progress.trueExtensionUnlocked must be boolean");
  const expectedLimit = progress.trueExtensionUnlocked
    ? config.true_stage_limit
    : config.base_stage_limit;
  assert(progress.stageLimit === expectedLimit,
    "progress.stageLimit does not match the unlocked campaign extent");
  assert(progress.completedStageCount <= progress.stageLimit,
    "progress.completedStageCount exceeds the unlocked campaign extent");
  if (progress.trueExtensionUnlocked) {
    assert(progress.completedStageCount >= config.base_stage_limit,
      "the true extension cannot be unlocked before base completion");
  }
  assert(CAMPAIGN_PROGRESS_STATUSES.includes(progress.status),
    "progress.status is unknown");
  assert(progress.status === expectedStatus(progress),
    "progress.status does not match completed stage authority");
  const expectedCurrentStage = progress.status === "ACTIVE"
    ? progress.completedStageCount + 1
    : null;
  assert(progress.currentStageNumber === expectedCurrentStage,
    "progress.currentStageNumber must be derived from completedStageCount");
  assert(isDenseArray(progress.operationRecords),
    "progress.operationRecords must be a dense array");
  assert(progress.operationRecords.length === progress.completedStageCount,
    "progress.operationRecords must contain exactly one record per completed stage");
  progress.operationRecords.forEach((record, index) => {
    validateOperationRecord(config, record, index);
  });
  return true;
}

export function createCampaignProgress(config = FORMAL_CAMPAIGN_PROGRESS_CONFIG) {
  validateCampaignProgressConfig(config);
  const progress = {
    type: "CAMPAIGN_PROGRESS_STATE",
    schemaVersion: CAMPAIGN_PROGRESS_SCHEMA_VERSION,
    configId: config.id,
    configVersion: config.version,
    completedStageCount: 0,
    currentStageNumber: 1,
    stageLimit: config.base_stage_limit,
    trueExtensionUnlocked: false,
    status: "ACTIVE",
    operationRecords: [],
  };
  validateCampaignProgressState(config, progress);
  return progress;
}

export function campaignOperationDescriptor(config, progress) {
  validateCampaignProgressState(config, progress);
  assert(progress.status === "ACTIVE", "completed progress has no current operation");
  return operationDescriptor(config, progress.currentStageNumber);
}

export function completeCampaignOperation(config, progress, operation) {
  validateCampaignProgressState(config, progress);
  validateOperationDescriptor(config, operation);
  const expected = campaignOperationDescriptor(config, progress);
  assert(sameJson(operation, expected),
    "operation is stale or does not match the current campaign transition");
  const completedStageCount = progress.completedStageCount + 1;
  assert(Number.isSafeInteger(completedStageCount),
    "completedStageCount overflowed safe integer range");
  const operationRecords = cloneOperationRecords(progress.operationRecords);
  operationRecords.push({
    resultIdentity: campaignResultIdentity(config, operation),
  });
  const isComplete = completedStageCount === progress.stageLimit;
  const next = {
    ...progress,
    completedStageCount,
    currentStageNumber: isComplete ? null : completedStageCount + 1,
    status: isComplete
      ? (progress.trueExtensionUnlocked ? "TRUE_COMPLETE" : "BASE_COMPLETE")
      : "ACTIVE",
    operationRecords,
  };
  validateCampaignProgressState(config, next);
  return next;
}

export function unlockTrueCampaignExtension(config, progress, gateEvidence) {
  validateCampaignProgressState(config, progress);
  assert(progress.status === "BASE_COMPLETE",
    "true extension can unlock only after base completion");
  assert(progress.completedStageCount === config.base_stage_limit,
    "true extension requires every base stage to be completed");
  assert(progress.trueExtensionUnlocked === false,
    "true extension is already unlocked");
  assert(isPlainObject(gateEvidence), "gateEvidence must be an object");
  assert(gateEvidence.gateId === config.true_entry_gate_id,
    "gateEvidence.gateId does not match the true entry gate");
  assert(gateEvidence.passed === true, "gateEvidence must explicitly pass");
  assert(gateEvidence.boundaryStageNumber === config.base_stage_limit,
    "gateEvidence must be observed at the base boundary");
  const next = {
    ...progress,
    currentStageNumber: config.base_stage_limit + 1,
    stageLimit: config.true_stage_limit,
    trueExtensionUnlocked: true,
    status: "ACTIVE",
    operationRecords: cloneOperationRecords(progress.operationRecords),
  };
  validateCampaignProgressState(config, next);
  return next;
}

export function compileCampaignGreyboxOperationPlan(
  config = FORMAL_CAMPAIGN_PROGRESS_CONFIG,
  options = {},
) {
  validateCampaignProgressConfig(config);
  assert(isPlainObject(options), "plan options must be an object");
  const includeTrueExtension = options.includeTrueExtension ?? false;
  assert(typeof includeTrueExtension === "boolean",
    "plan options.includeTrueExtension must be boolean");
  const totalStages = includeTrueExtension
    ? config.true_stage_limit
    : config.base_stage_limit;
  return {
    type: "COMPILED_CAMPAIGN_GREYBOX_OPERATION_PLAN",
    configId: config.id,
    configVersion: config.version,
    templatePolicyId: CAMPAIGN_GREYBOX_TEMPLATE_POLICY_ID,
    productionReady: false,
    totalStages,
    includeTrueExtension,
    operations: Array.from(
      { length: totalStages },
      (_, index) => operationDescriptor(config, index + 1),
    ),
  };
}

export function validateCampaignProgressPrefix(config = FORMAL_CAMPAIGN_PROGRESS_CONFIG) {
  const base = compileCampaignGreyboxOperationPlan(config, { includeTrueExtension: false });
  const extended = compileCampaignGreyboxOperationPlan(config, { includeTrueExtension: true });
  assert(extended.totalStages > base.totalStages,
    "true operation plan must extend the base plan");
  assert(sameJson(extended.operations.slice(0, base.totalStages), base.operations),
    "true operation plan must preserve the complete base prefix");
  return true;
}
