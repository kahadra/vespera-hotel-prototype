import {
  CAMPAIGN_BASE_STAGE_LIMIT,
  CAMPAIGN_TRUE_STAGE_LIMIT,
  compileCampaignGreyboxOperationPlan,
  validateCampaignProgressConfig,
  validateCampaignProgressPrefix,
} from "./campaign-progress.js";

export const CAMPAIGN_OPERATION_PLAN_STATUS = "DEVELOPMENT_PLACEHOLDER";
export const CAMPAIGN_OPERATION_PLAN_ID = "CAMPAIGN_DEVELOPMENT_OPERATION_PLAN_V1";
export const CAMPAIGN_OPERATION_KIND = "NORMAL";
export const CAMPAIGN_OPERATION_BASE_PROJECTION_TYPE =
  "CAMPAIGN_OPERATION_PLAN_BASE_PROJECTION";

const PLAN_KEYS = Object.freeze([
  "plan_id",
  "plan_version",
  "status",
  "production_ready",
  "base_stage_limit",
  "true_stage_limit",
  "operations",
]);

const OPERATION_KEYS = Object.freeze([
  "stage_number",
  "operation_id",
  "operation_kind",
  "scenario_id",
]);

const BASE_PROJECTION_KEYS = Object.freeze([
  "type",
  "plan_id",
  "plan_version",
  "stage_limit",
  "operations",
]);

function assert(condition, message) {
  if (!condition) throw new Error(`Invalid campaign operation plan: ${message}`);
}

function nonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function positiveSafeInteger(value) {
  return Number.isSafeInteger(value) && value > 0;
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

function cloneOperation(operation) {
  return {
    stage_number: operation.stage_number,
    operation_id: operation.operation_id,
    operation_kind: operation.operation_kind,
    scenario_id: operation.scenario_id,
  };
}

function validateKnownScenarioIds(knownScenarioIds) {
  assert(isDenseArray(knownScenarioIds), "known scenario ids must be a dense array");
  assert(knownScenarioIds.length > 0, "known scenario ids must not be empty");
  const uniqueIds = new Set();
  knownScenarioIds.forEach((scenarioId, index) => {
    assert(nonEmptyString(scenarioId), `known scenario id ${index} must be non-empty`);
    assert(!uniqueIds.has(scenarioId), `duplicate known scenario id ${scenarioId}`);
    uniqueIds.add(scenarioId);
  });
  return uniqueIds;
}

export function createDevelopmentCampaignOperationPlan(knownScenarioIds) {
  validateKnownScenarioIds(knownScenarioIds);
  const operations = [];
  let scenarioIndex = 0;
  for (let stageNumber = 1; stageNumber <= CAMPAIGN_TRUE_STAGE_LIMIT; stageNumber += 1) {
    operations.push({
      stage_number: stageNumber,
      operation_id: `CAMPAIGN_DEVELOPMENT_DAY_${String(stageNumber).padStart(3, "0")}`,
      operation_kind: CAMPAIGN_OPERATION_KIND,
      scenario_id: knownScenarioIds[scenarioIndex],
    });
    scenarioIndex += 1;
    if (scenarioIndex === knownScenarioIds.length) scenarioIndex = 0;
  }
  const plan = {
    plan_id: CAMPAIGN_OPERATION_PLAN_ID,
    plan_version: 1,
    status: CAMPAIGN_OPERATION_PLAN_STATUS,
    production_ready: false,
    base_stage_limit: CAMPAIGN_BASE_STAGE_LIMIT,
    true_stage_limit: CAMPAIGN_TRUE_STAGE_LIMIT,
    operations,
  };
  validateCampaignOperationPlan(plan, knownScenarioIds);
  return plan;
}

export function validateCampaignOperationPlan(plan, knownScenarioIds) {
  assert(exactKeys(plan, PLAN_KEYS), "plan must have the exact contract shape");
  assert(plan.plan_id === CAMPAIGN_OPERATION_PLAN_ID, `plan_id must be ${CAMPAIGN_OPERATION_PLAN_ID}`);
  assert(plan.plan_version === 1, "plan_version must be 1");
  assert(
    plan.status === CAMPAIGN_OPERATION_PLAN_STATUS,
    `status must be ${CAMPAIGN_OPERATION_PLAN_STATUS}`,
  );
  assert(plan.production_ready === false, "production_ready must remain false");
  assert(
    plan.base_stage_limit === CAMPAIGN_BASE_STAGE_LIMIT,
    `base_stage_limit must be ${CAMPAIGN_BASE_STAGE_LIMIT}`,
  );
  assert(
    plan.true_stage_limit === CAMPAIGN_TRUE_STAGE_LIMIT,
    `true_stage_limit must be ${CAMPAIGN_TRUE_STAGE_LIMIT}`,
  );
  assert(isDenseArray(plan.operations), "operations must be a dense array");
  assert(
    plan.operations.length === CAMPAIGN_TRUE_STAGE_LIMIT,
    `operations must contain exactly ${CAMPAIGN_TRUE_STAGE_LIMIT} entries`,
  );

  const knownIds = validateKnownScenarioIds(knownScenarioIds);
  const operationIds = new Set();
  plan.operations.forEach((operation, index) => {
    assert(exactKeys(operation, OPERATION_KEYS), `operation ${index + 1} has invalid shape`);
    assert(
      operation.stage_number === index + 1,
      `operation ${index + 1} must have its sequential stage_number`,
    );
    assert(nonEmptyString(operation.operation_id), `operation ${index + 1} needs an operation_id`);
    assert(
      !operationIds.has(operation.operation_id),
      `duplicate operation_id ${operation.operation_id}`,
    );
    operationIds.add(operation.operation_id);
    assert(
      operation.operation_kind === CAMPAIGN_OPERATION_KIND,
      `operation ${index + 1} must be ${CAMPAIGN_OPERATION_KIND}`,
    );
    assert(
      nonEmptyString(operation.scenario_id) && knownIds.has(operation.scenario_id),
      `operation ${index + 1} references an unknown scenario`,
    );
  });
  return true;
}

export function projectCampaignOperationPlanBase(plan, knownScenarioIds) {
  validateCampaignOperationPlan(plan, knownScenarioIds);
  const projection = {
    type: CAMPAIGN_OPERATION_BASE_PROJECTION_TYPE,
    plan_id: plan.plan_id,
    plan_version: plan.plan_version,
    stage_limit: CAMPAIGN_BASE_STAGE_LIMIT,
    operations: plan.operations
      .slice(0, CAMPAIGN_BASE_STAGE_LIMIT)
      .map(cloneOperation),
  };
  validateCampaignOperationPlanBaseProjection(plan, projection, knownScenarioIds);
  return projection;
}

export function validateCampaignOperationPlanBaseProjection(
  plan,
  projection,
  knownScenarioIds,
) {
  validateCampaignOperationPlan(plan, knownScenarioIds);
  assert(
    exactKeys(projection, BASE_PROJECTION_KEYS),
    "base projection must have the exact contract shape",
  );
  assert(
    projection.type === CAMPAIGN_OPERATION_BASE_PROJECTION_TYPE,
    `base projection type must be ${CAMPAIGN_OPERATION_BASE_PROJECTION_TYPE}`,
  );
  assert(projection.plan_id === plan.plan_id, "base projection plan_id mismatch");
  assert(projection.plan_version === plan.plan_version, "base projection plan_version mismatch");
  assert(
    projection.stage_limit === CAMPAIGN_BASE_STAGE_LIMIT,
    `base projection stage_limit must be ${CAMPAIGN_BASE_STAGE_LIMIT}`,
  );
  assert(isDenseArray(projection.operations), "base projection operations must be dense");
  assert(
    projection.operations.length === CAMPAIGN_BASE_STAGE_LIMIT,
    `base projection must contain exactly ${CAMPAIGN_BASE_STAGE_LIMIT} entries`,
  );
  projection.operations.forEach((operation, index) => {
    assert(exactKeys(operation, OPERATION_KEYS), `base operation ${index + 1} has invalid shape`);
    assert(
      JSON.stringify(operation) === JSON.stringify(plan.operations[index]),
      `base operation ${index + 1} must equal the true-plan prefix`,
    );
  });
  return true;
}

export function resolveCampaignOperation(plan, stageNumber, knownScenarioIds) {
  validateCampaignOperationPlan(plan, knownScenarioIds);
  assert(positiveSafeInteger(stageNumber), "stage number must be a positive safe integer");
  assert(stageNumber <= CAMPAIGN_TRUE_STAGE_LIMIT, "stage number exceeds the true-stage limit");
  const operation = plan.operations[stageNumber - 1];
  assert(operation.stage_number === stageNumber, "resolved operation stage mismatch");
  return cloneOperation(operation);
}

export function validateCampaignOperationPlanProgressAlignment(
  plan,
  progressConfig,
  scenarios,
) {
  assert(isDenseArray(scenarios) && scenarios.length > 0, "scenarios must be a dense array");
  const scenarioIds = scenarios.map((scenario, index) => {
    assert(isPlainObject(scenario), `scenario ${index} must be an object`);
    assert(nonEmptyString(scenario.id), `scenario ${index} must have an id`);
    return scenario.id;
  });
  validateCampaignProgressConfig(progressConfig);
  validateCampaignProgressPrefix(progressConfig);
  assert(
    progressConfig.scenario_template_count === scenarios.length,
    "legacy template count must match the scenario count",
  );
  validateCampaignOperationPlan(plan, scenarioIds);
  const baseProjection = projectCampaignOperationPlanBase(plan, scenarioIds);
  validateCampaignOperationPlanBaseProjection(plan, baseProjection, scenarioIds);
  assert(
    plan.base_stage_limit === progressConfig.base_stage_limit,
    "base stage limit must match legacy progress",
  );
  assert(
    plan.true_stage_limit === progressConfig.true_stage_limit,
    "true stage limit must match legacy progress",
  );

  const legacyPlan = compileCampaignGreyboxOperationPlan(progressConfig, {
    includeTrueExtension: true,
  });
  assert(
    legacyPlan.operations.length === plan.operations.length,
    "operation count must match legacy progress",
  );
  plan.operations.forEach((operation, index) => {
    const legacyOperation = legacyPlan.operations[index];
    const legacyScenario = scenarios[legacyOperation.templateIndex];
    assert(
      operation.stage_number === legacyOperation.stageNumber,
      `stage ${index + 1} must match legacy progress`,
    );
    assert(
      operation.operation_kind === legacyOperation.operationKind,
      `operation kind ${index + 1} must match legacy progress`,
    );
    assert(
      operation.scenario_id === legacyScenario?.id,
      `scenario ${index + 1} must match the transitional legacy descriptor`,
    );
  });
  return true;
}

export function campaignPlanOperationIdentity(plan, operation, knownScenarioIds) {
  validateCampaignOperationPlan(plan, knownScenarioIds);
  assert(exactKeys(operation, OPERATION_KEYS), "identity operation must have the exact shape");
  const resolved = resolveCampaignOperation(plan, operation.stage_number, knownScenarioIds);
  assert(
    JSON.stringify(operation) === JSON.stringify(resolved),
    "identity operation must belong to the plan",
  );
  return {
    planId: plan.plan_id,
    planVersion: plan.plan_version,
    operationId: operation.operation_id,
    stageNumber: operation.stage_number,
    operationKind: operation.operation_kind,
    scenarioId: operation.scenario_id,
  };
}
