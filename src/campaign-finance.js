export const CAMPAIGN_FINANCE_SCHEMA_VERSION = 1;
export const CAMPAIGN_FINANCE_CONTRACT_STATUS = "PROVISIONAL";
export const CAMPAIGN_FINANCE_BALANCE_VERDICT = "NOT_EVALUATED";
export const CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE = 56;
export const CAMPAIGN_FINANCE_DEBT_GATE_ID = "BASE_DEBT_CLEARED_AT_STAGE_56";
export const CAMPAIGN_FINANCE_CHECKPOINT_STAGES = Object.freeze([7, 14, 28, 42, 56]);
export const CAMPAIGN_FINANCE_SUPPORTED_STAGE_LIMITS = Object.freeze([56, 70]);
export const CAMPAIGN_FINANCE_OPERATION_KINDS = Object.freeze(["NORMAL", "RECOVERY"]);
export const CAMPAIGN_FINANCE_SETTLEMENT_SEQUENCE =
  "RESULT_COMMIT_THEN_OPTIONAL_REPAYMENT_THEN_CHECKPOINT";
export const CAMPAIGN_FINANCE_RECOVERY_POLICY_STATUS = "TBD";

const STATE_KEYS = Object.freeze([
  "type",
  "schemaVersion",
  "configId",
  "configVersion",
  "contractStatus",
  "balanceVerdict",
  "totalStages",
  "debtDeadlineStageNumber",
  "completedStageCount",
  "nextStageNumber",
  "phase",
  "status",
  "cash",
  "originalPrincipal",
  "remainingDebt",
  "cumulativeRepayment",
  "debtClearedAtDeadline",
  "pendingDayResult",
  "ledger",
]);

const CONFIG_KEYS = Object.freeze([
  "id",
  "version",
  "contract_status",
  "total_stages",
  "debt_deadline_stage",
  "debt_gate_id",
  "starting_cash",
  "principal",
  "chapter_cumulative_targets",
]);

const PENDING_RESULT_KEYS = Object.freeze([
  "type",
  "stageNumber",
  "campaignOperationId",
  "campaignResultIdentity",
  "openingCash",
  "income",
  "upkeep",
  "reactivation",
  "roomService",
  "cashAfterOperations",
  "openingDebt",
  "cumulativeRepaymentBefore",
]);

const LEDGER_ENTRY_KEYS = Object.freeze([
  "type",
  "stageNumber",
  "campaignOperationId",
  "campaignResultIdentity",
  "settlementSequence",
  "openingCash",
  "income",
  "upkeep",
  "reactivation",
  "roomService",
  "cashAfterOperations",
  "manualRepayment",
  "closingCash",
  "openingDebt",
  "closingDebt",
  "cumulativeRepayment",
  "cashConservation",
  "debtConservation",
  "checkpoint",
]);

function assert(condition, message) {
  if (!condition) throw new Error(`Invalid campaign finance: ${message}`);
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

function sameFlatRecord(left, right) {
  if (!exactKeys(left, Object.keys(right))) return false;
  return Object.keys(right).every((key) => left[key] === right[key]);
}

function cloneJson(value) {
  return value === null ? null : JSON.parse(JSON.stringify(value));
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

function assertAmount(value, owner) {
  assert(nonNegativeSafeInteger(value), `${owner} must be a non-negative safe integer`);
  return value;
}

function safeSum(owner, ...values) {
  values.forEach((value, index) => assertAmount(value, `${owner}[${index}]`));
  const total = values.reduce((sum, value) => sum + value, 0);
  assert(Number.isSafeInteger(total), `${owner} exceeds the safe-integer range`);
  return total;
}

function chapterTargets(config) {
  return config.chapter_cumulative_targets;
}

export function validateCampaignFinanceConfig(config) {
  assert(exactKeys(config, CONFIG_KEYS), "config has an invalid shape");
  assert(nonEmptyString(config.id), "config.id must be a non-empty string");
  assert(positiveSafeInteger(config.version),
    "config.version must be a positive safe integer");
  assert(config.contract_status === CAMPAIGN_FINANCE_CONTRACT_STATUS,
    `config.contract_status must remain ${CAMPAIGN_FINANCE_CONTRACT_STATUS}`);
  assert(CAMPAIGN_FINANCE_SUPPORTED_STAGE_LIMITS.includes(config.total_stages),
    `config.total_stages must be one of ${CAMPAIGN_FINANCE_SUPPORTED_STAGE_LIMITS.join(",")}`);
  assert(config.debt_deadline_stage === CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE,
    `config.debt_deadline_stage must be ${CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE}`);
  assert(config.debt_gate_id === CAMPAIGN_FINANCE_DEBT_GATE_ID,
    `config.debt_gate_id must be ${CAMPAIGN_FINANCE_DEBT_GATE_ID}`);
  assertAmount(config.starting_cash, "config.starting_cash");
  assertAmount(config.principal, "config.principal");

  const targets = chapterTargets(config);
  assert(isPlainObject(targets), "config.chapter_cumulative_targets must be an object");
  assert(exactKeys(targets, CAMPAIGN_FINANCE_CHECKPOINT_STAGES.map(String)),
    "config.chapter_cumulative_targets must define exactly days 7,14,28,42,56");
  let previousTarget = 0;
  for (const stageNumber of CAMPAIGN_FINANCE_CHECKPOINT_STAGES) {
    const target = targets[String(stageNumber)];
    assertAmount(target, `config.chapter_cumulative_targets[${stageNumber}]`);
    assert(target >= previousTarget,
      "config.chapter_cumulative_targets must be nondecreasing");
    assert(target <= config.principal,
      `chapter target on stage ${stageNumber} exceeds principal`);
    previousTarget = target;
  }
  assert(targets[String(CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE)] === config.principal,
    "the day 56 cumulative target must equal the full principal");
  return true;
}

function validateCampaignResultIdentity(identity, stageNumber, owner) {
  assert(exactKeys(identity, ["stageNumber", "operationKind", "templateIndex"]),
    `${owner} must contain exactly stageNumber, operationKind, and templateIndex`);
  assert(identity.stageNumber === stageNumber,
    `${owner}.stageNumber must match the finance stage`);
  assert(CAMPAIGN_FINANCE_OPERATION_KINDS.includes(identity.operationKind),
    `${owner}.operationKind is unknown`);
  assert(nonNegativeSafeInteger(identity.templateIndex),
    `${owner}.templateIndex must be a non-negative safe integer`);
}

function validateCampaignOperationIdentity(operationId, resultIdentity, stageNumber, owner) {
  assert(nonEmptyString(operationId), `${owner}.campaignOperationId must be non-empty`);
  validateCampaignResultIdentity(
    resultIdentity,
    stageNumber,
    `${owner}.campaignResultIdentity`,
  );
}

function recoveryRequirement(stageNumber, shortfallAmount) {
  return {
    type: "CAMPAIGN_FINANCE_RECOVERY_REQUIREMENT",
    required: true,
    boundaryStageNumber: stageNumber,
    shortfallAmount,
    deadlineExtensionAllowed: false,
    penaltyPolicyStatus: CAMPAIGN_FINANCE_RECOVERY_POLICY_STATUS,
  };
}

function checkpointFor(config, stageNumber, cumulativeRepayment, remainingDebt) {
  if (!CAMPAIGN_FINANCE_CHECKPOINT_STAGES.includes(stageNumber)) return null;
  const targetAmount = chapterTargets(config)[String(stageNumber)];
  const shortfallAmount = Math.max(0, targetAmount - cumulativeRepayment);
  const finalCheckpoint = stageNumber === CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE;
  let outcome = "MET";
  let recovery = null;
  if (finalCheckpoint) {
    outcome = remainingDebt === 0 ? "DEBT_CLEARED" : "DEBT_DEADLINE_MISSED";
  } else if (shortfallAmount > 0) {
    outcome = "RECOVERY_REQUIRED";
    recovery = recoveryRequirement(stageNumber, shortfallAmount);
  }
  return {
    type: "CAMPAIGN_DEBT_CHECKPOINT",
    stageNumber,
    kind: finalCheckpoint ? "FINAL_CLEARANCE" : "CUMULATIVE_MINIMUM",
    targetAmount,
    cumulativeRepayment,
    remainingDebt,
    shortfallAmount,
    outcome,
    recoveryRequirement: recovery,
    debtDeadlineExtended: false,
  };
}

function expectedEnvelope(config, completedStageCount, debtClearedAtDeadline, pendingDayResult) {
  const missedDeadline = completedStageCount >= CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE
    && debtClearedAtDeadline === false;
  if (missedDeadline) {
    assert(completedStageCount === CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE,
      "a missed day 56 deadline cannot advance into later stages");
    assert(pendingDayResult === null,
      "a missed day 56 deadline cannot retain a pending result");
    return {
      phase: "CLOSED",
      status: "DEBT_DEADLINE_MISSED",
      nextStageNumber: null,
    };
  }
  if (completedStageCount === config.total_stages) {
    assert(pendingDayResult === null,
      "completed finance cannot retain a pending result");
    return { phase: "CLOSED", status: "COMPLETE", nextStageNumber: null };
  }
  return {
    phase: pendingDayResult === null ? "AWAITING_RESULT" : "RESULT_COMMITTED",
    status: "ACTIVE",
    nextStageNumber: completedStageCount + 1,
  };
}

function expectedCashConservation(entry) {
  const openingPlusIncome = safeSum(
    `ledger[${entry.stageNumber}].cashConservation.openingPlusIncome`,
    entry.openingCash,
    entry.income,
  );
  const closingPlusOutflows = safeSum(
    `ledger[${entry.stageNumber}].cashConservation.closingPlusOutflows`,
    entry.closingCash,
    entry.upkeep,
    entry.reactivation,
    entry.roomService,
    entry.manualRepayment,
  );
  return {
    openingPlusIncome,
    closingPlusOutflows,
    delta: openingPlusIncome - closingPlusOutflows,
  };
}

function expectedDebtConservation(config, entry) {
  const repaidPlusRemaining = safeSum(
    `ledger[${entry.stageNumber}].debtConservation.repaidPlusRemaining`,
    entry.cumulativeRepayment,
    entry.closingDebt,
  );
  return {
    originalPrincipal: config.principal,
    repaidPlusRemaining,
    delta: config.principal - repaidPlusRemaining,
  };
}

function validateLedgerEntry(config, entry, stageNumber, prior, seenOperationIds) {
  const owner = `ledger[${stageNumber - 1}]`;
  assert(exactKeys(entry, LEDGER_ENTRY_KEYS), `${owner} has an invalid shape`);
  assert(entry.type === "CAMPAIGN_FINANCE_LEDGER_ENTRY", `${owner}.type is unknown`);
  assert(entry.stageNumber === stageNumber, `${owner}.stageNumber must be sequential`);
  validateCampaignOperationIdentity(
    entry.campaignOperationId,
    entry.campaignResultIdentity,
    stageNumber,
    owner,
  );
  assert(!seenOperationIds.has(entry.campaignOperationId),
    `${owner}.campaignOperationId must be unique within the ledger`);
  seenOperationIds.add(entry.campaignOperationId);
  assert(entry.settlementSequence === CAMPAIGN_FINANCE_SETTLEMENT_SEQUENCE,
    `${owner}.settlementSequence is unsupported`);
  for (const field of [
    "openingCash",
    "income",
    "upkeep",
    "reactivation",
    "roomService",
    "cashAfterOperations",
    "manualRepayment",
    "closingCash",
    "openingDebt",
    "closingDebt",
    "cumulativeRepayment",
  ]) {
    assertAmount(entry[field], `${owner}.${field}`);
  }
  assert(entry.openingCash === prior.cash, `${owner}.openingCash does not follow the ledger`);
  assert(entry.openingDebt === prior.remainingDebt,
    `${owner}.openingDebt does not follow the ledger`);

  const available = safeSum(`${owner}.availableCash`, entry.openingCash, entry.income);
  const operatingOutflow = safeSum(
    `${owner}.operatingOutflow`,
    entry.upkeep,
    entry.reactivation,
    entry.roomService,
  );
  assert(operatingOutflow <= available, `${owner} would produce negative operating cash`);
  assert(entry.cashAfterOperations === available - operatingOutflow,
    `${owner}.cashAfterOperations is inconsistent`);
  assert(entry.manualRepayment <= entry.cashAfterOperations,
    `${owner}.manualRepayment exceeds cash`);
  assert(entry.manualRepayment <= entry.openingDebt,
    `${owner}.manualRepayment exceeds remaining debt`);
  if (stageNumber > CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE) {
    assert(entry.openingDebt === 0 && entry.manualRepayment === 0,
      `${owner} cannot carry or repay debt after day 56`);
  }
  assert(entry.closingCash === entry.cashAfterOperations - entry.manualRepayment,
    `${owner}.closingCash is inconsistent`);
  assert(entry.closingDebt === entry.openingDebt - entry.manualRepayment,
    `${owner}.closingDebt is inconsistent`);
  const expectedCumulative = safeSum(
    `${owner}.cumulativeRepayment`,
    prior.cumulativeRepayment,
    entry.manualRepayment,
  );
  assert(entry.cumulativeRepayment === expectedCumulative,
    `${owner}.cumulativeRepayment is inconsistent`);

  const cashConservation = expectedCashConservation(entry);
  assert(cashConservation.delta === 0, `${owner} violates cash conservation`);
  assert(sameJson(entry.cashConservation, cashConservation),
    `${owner}.cashConservation is inconsistent`);
  const debtConservation = expectedDebtConservation(config, entry);
  assert(debtConservation.delta === 0, `${owner} violates debt conservation`);
  assert(sameJson(entry.debtConservation, debtConservation),
    `${owner}.debtConservation is inconsistent`);

  const checkpoint = checkpointFor(
    config,
    stageNumber,
    entry.cumulativeRepayment,
    entry.closingDebt,
  );
  assert(sameJson(entry.checkpoint, checkpoint), `${owner}.checkpoint is inconsistent`);
  return {
    cash: entry.closingCash,
    remainingDebt: entry.closingDebt,
    cumulativeRepayment: entry.cumulativeRepayment,
  };
}

function validatePendingDayResult(config, pending, stageNumber, prior, seenOperationIds) {
  const owner = "pendingDayResult";
  assert(exactKeys(pending, PENDING_RESULT_KEYS), `${owner} has an invalid shape`);
  assert(pending.type === "CAMPAIGN_DAY_RESULT_COMMIT", `${owner}.type is unknown`);
  assert(pending.stageNumber === stageNumber, `${owner}.stageNumber is inconsistent`);
  validateCampaignOperationIdentity(
    pending.campaignOperationId,
    pending.campaignResultIdentity,
    stageNumber,
    owner,
  );
  assert(!seenOperationIds.has(pending.campaignOperationId),
    `${owner}.campaignOperationId already exists in the settled ledger`);
  for (const field of [
    "openingCash",
    "income",
    "upkeep",
    "reactivation",
    "roomService",
    "cashAfterOperations",
    "openingDebt",
    "cumulativeRepaymentBefore",
  ]) {
    assertAmount(pending[field], `${owner}.${field}`);
  }
  assert(pending.openingCash === prior.cash, `${owner}.openingCash does not follow the ledger`);
  assert(pending.openingDebt === prior.remainingDebt,
    `${owner}.openingDebt does not follow the ledger`);
  assert(pending.cumulativeRepaymentBefore === prior.cumulativeRepayment,
    `${owner}.cumulativeRepaymentBefore does not follow the ledger`);
  const available = safeSum(`${owner}.availableCash`, pending.openingCash, pending.income);
  const operatingOutflow = safeSum(
    `${owner}.operatingOutflow`,
    pending.upkeep,
    pending.reactivation,
    pending.roomService,
  );
  assert(operatingOutflow <= available, `${owner} would produce negative operating cash`);
  assert(pending.cashAfterOperations === available - operatingOutflow,
    `${owner}.cashAfterOperations is inconsistent`);
  if (stageNumber > CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE) {
    assert(pending.openingDebt === 0,
      `${owner} cannot carry debt after day 56`);
  }
}

export function validateCampaignFinanceState(config, state) {
  validateCampaignFinanceConfig(config);
  assert(exactKeys(state, STATE_KEYS), "state has an invalid shape");
  assert(state.type === "CAMPAIGN_FINANCE_STATE", "state.type is unknown");
  assert(state.schemaVersion === CAMPAIGN_FINANCE_SCHEMA_VERSION,
    "state.schemaVersion is unsupported");
  assert(state.configId === config.id, "state.configId does not match config");
  assert(state.configVersion === config.version,
    "state.configVersion does not match config");
  assert(state.contractStatus === CAMPAIGN_FINANCE_CONTRACT_STATUS,
    "state.contractStatus is unsupported");
  assert(state.balanceVerdict === CAMPAIGN_FINANCE_BALANCE_VERDICT,
    "state.balanceVerdict must remain NOT_EVALUATED");
  assert(state.totalStages === config.total_stages,
    "state.totalStages does not match config");
  assert(state.debtDeadlineStageNumber === CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE,
    "state.debtDeadlineStageNumber is inconsistent");
  assert(nonNegativeSafeInteger(state.completedStageCount),
    "state.completedStageCount must be a non-negative safe integer");
  assert(state.completedStageCount <= config.total_stages,
    "state.completedStageCount exceeds the configured stage limit");
  assertAmount(state.cash, "state.cash");
  assert(state.originalPrincipal === config.principal,
    "state.originalPrincipal does not match config");
  assertAmount(state.remainingDebt, "state.remainingDebt");
  assertAmount(state.cumulativeRepayment, "state.cumulativeRepayment");
  assert(state.remainingDebt <= config.principal,
    "state.remainingDebt exceeds the original principal");
  assert(safeSum(
    "state debt conservation",
    state.remainingDebt,
    state.cumulativeRepayment,
  ) === config.principal, "state violates debt conservation");
  assert(isDenseArray(state.ledger), "state.ledger must be a dense array");
  assert(state.ledger.length === state.completedStageCount,
    "state.ledger must contain one entry per completed stage");

  let reconstructed = {
    cash: config.starting_cash,
    remainingDebt: config.principal,
    cumulativeRepayment: 0,
  };
  const seenOperationIds = new Set();
  state.ledger.forEach((entry, index) => {
    reconstructed = validateLedgerEntry(
      config,
      entry,
      index + 1,
      reconstructed,
      seenOperationIds,
    );
  });
  if (state.pendingDayResult !== null) {
    assert(state.completedStageCount < config.total_stages,
      "completed finance cannot have a pending result");
    validatePendingDayResult(
      config,
      state.pendingDayResult,
      state.completedStageCount + 1,
      reconstructed,
      seenOperationIds,
    );
    assert(state.cash === state.pendingDayResult.cashAfterOperations,
      "state.cash must include the committed operating result");
    assert(state.remainingDebt === reconstructed.remainingDebt,
      "pending result cannot change debt before settlement");
    assert(state.cumulativeRepayment === reconstructed.cumulativeRepayment,
      "pending result cannot change cumulative repayment before settlement");
  } else {
    assert(state.cash === reconstructed.cash, "state.cash does not match the ledger");
    assert(state.remainingDebt === reconstructed.remainingDebt,
      "state.remainingDebt does not match the ledger");
    assert(state.cumulativeRepayment === reconstructed.cumulativeRepayment,
      "state.cumulativeRepayment does not match the ledger");
  }

  let expectedDeadlineFlag = null;
  if (state.completedStageCount >= CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE) {
    const deadlineEntry = state.ledger[CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE - 1];
    expectedDeadlineFlag = deadlineEntry.closingDebt === 0;
  }
  assert(state.debtClearedAtDeadline === expectedDeadlineFlag,
    "state.debtClearedAtDeadline must preserve the day 56 observation");
  if (state.completedStageCount > CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE) {
    assert(state.debtClearedAtDeadline === true && state.remainingDebt === 0,
      "post-deadline stages require debt cleared at day 56");
  }

  const envelope = expectedEnvelope(
    config,
    state.completedStageCount,
    state.debtClearedAtDeadline,
    state.pendingDayResult,
  );
  assert(state.phase === envelope.phase, "state.phase is inconsistent");
  assert(state.status === envelope.status, "state.status is inconsistent");
  assert(state.nextStageNumber === envelope.nextStageNumber,
    "state.nextStageNumber is inconsistent");
  return true;
}

export function createCampaignFinanceState(config) {
  validateCampaignFinanceConfig(config);
  assert(config.total_stages === CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE,
    "new finance must begin with the 56-stage base config");
  const state = {
    type: "CAMPAIGN_FINANCE_STATE",
    schemaVersion: CAMPAIGN_FINANCE_SCHEMA_VERSION,
    configId: config.id,
    configVersion: config.version,
    contractStatus: CAMPAIGN_FINANCE_CONTRACT_STATUS,
    balanceVerdict: CAMPAIGN_FINANCE_BALANCE_VERDICT,
    totalStages: config.total_stages,
    debtDeadlineStageNumber: CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE,
    completedStageCount: 0,
    nextStageNumber: 1,
    phase: "AWAITING_RESULT",
    status: "ACTIVE",
    cash: config.starting_cash,
    originalPrincipal: config.principal,
    remainingDebt: config.principal,
    cumulativeRepayment: 0,
    debtClearedAtDeadline: null,
    pendingDayResult: null,
    ledger: [],
  };
  validateCampaignFinanceState(config, state);
  return state;
}

export function commitCampaignDayResult(config, state, result) {
  validateCampaignFinanceState(config, state);
  assert(state.status === "ACTIVE" && state.phase === "AWAITING_RESULT",
    "a day result can be committed only while awaiting the next result");
  assert(exactKeys(result, [
    "stageNumber",
    "campaignOperationId",
    "campaignResultIdentity",
    "income",
    "upkeep",
    "reactivation",
    "roomService",
  ]),
    "result has an invalid shape");
  assert(result.stageNumber === state.nextStageNumber,
    "result.stageNumber does not match the next finance stage");
  validateCampaignOperationIdentity(
    result.campaignOperationId,
    result.campaignResultIdentity,
    result.stageNumber,
    "result",
  );
  const campaignOperationId = result.campaignOperationId.trim();
  assert(!state.ledger.some((entry) => entry.campaignOperationId === campaignOperationId),
    "result.campaignOperationId already exists in the settled ledger");
  assertAmount(result.income, "result.income");
  assertAmount(result.upkeep, "result.upkeep");
  assertAmount(result.reactivation, "result.reactivation");
  assertAmount(result.roomService, "result.roomService");
  if (result.stageNumber > CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE) {
    assert(state.debtClearedAtDeadline === true && state.remainingDebt === 0,
      "day 57 and later cannot carry unresolved debt as grace");
  }
  const available = safeSum("result available cash", state.cash, result.income);
  const operatingOutflow = safeSum(
    "result operating outflow",
    result.upkeep,
    result.reactivation,
    result.roomService,
  );
  assert(operatingOutflow <= available,
    "upkeep, reactivation, and room service cannot produce negative cash");
  const pendingDayResult = {
    type: "CAMPAIGN_DAY_RESULT_COMMIT",
    stageNumber: result.stageNumber,
    campaignOperationId,
    campaignResultIdentity: { ...result.campaignResultIdentity },
    openingCash: state.cash,
    income: result.income,
    upkeep: result.upkeep,
    reactivation: result.reactivation,
    roomService: result.roomService,
    cashAfterOperations: available - operatingOutflow,
    openingDebt: state.remainingDebt,
    cumulativeRepaymentBefore: state.cumulativeRepayment,
  };
  const next = {
    ...state,
    phase: "RESULT_COMMITTED",
    cash: pendingDayResult.cashAfterOperations,
    pendingDayResult,
    ledger: cloneJson(state.ledger),
  };
  validateCampaignFinanceState(config, next);
  return next;
}

export function settleCampaignDay(config, state, settlement) {
  validateCampaignFinanceState(config, state);
  assert(state.status === "ACTIVE" && state.phase === "RESULT_COMMITTED",
    "settlement requires a committed day result");
  assert(exactKeys(settlement, ["manualRepayment"]),
    "settlement has an invalid shape");
  const manualRepayment = assertAmount(
    settlement.manualRepayment,
    "settlement.manualRepayment",
  );
  const pending = state.pendingDayResult;
  if (pending.stageNumber > CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE) {
    assert(manualRepayment === 0,
      "day 57 and later cannot accept debt repayment");
  }
  assert(manualRepayment <= state.cash,
    "manual repayment exceeds available cash; partial payment is never implicit");
  assert(manualRepayment <= state.remainingDebt,
    "manual repayment exceeds remaining debt; partial payment is never implicit");

  const closingCash = state.cash - manualRepayment;
  const closingDebt = state.remainingDebt - manualRepayment;
  const cumulativeRepayment = safeSum(
    "settlement cumulative repayment",
    state.cumulativeRepayment,
    manualRepayment,
  );
  const checkpoint = checkpointFor(
    config,
    pending.stageNumber,
    cumulativeRepayment,
    closingDebt,
  );
  const entry = {
    type: "CAMPAIGN_FINANCE_LEDGER_ENTRY",
    stageNumber: pending.stageNumber,
    campaignOperationId: pending.campaignOperationId,
    campaignResultIdentity: { ...pending.campaignResultIdentity },
    settlementSequence: CAMPAIGN_FINANCE_SETTLEMENT_SEQUENCE,
    openingCash: pending.openingCash,
    income: pending.income,
    upkeep: pending.upkeep,
    reactivation: pending.reactivation,
    roomService: pending.roomService,
    cashAfterOperations: pending.cashAfterOperations,
    manualRepayment,
    closingCash,
    openingDebt: pending.openingDebt,
    closingDebt,
    cumulativeRepayment,
    cashConservation: null,
    debtConservation: null,
    checkpoint,
  };
  entry.cashConservation = expectedCashConservation(entry);
  entry.debtConservation = expectedDebtConservation(config, entry);
  assert(entry.cashConservation.delta === 0, "cash conservation failed during settlement");
  assert(entry.debtConservation.delta === 0, "debt conservation failed during settlement");

  const completedStageCount = pending.stageNumber;
  const debtClearedAtDeadline = completedStageCount === CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE
    ? closingDebt === 0
    : state.debtClearedAtDeadline;
  const envelope = expectedEnvelope(
    config,
    completedStageCount,
    debtClearedAtDeadline,
    null,
  );
  const next = {
    ...state,
    completedStageCount,
    nextStageNumber: envelope.nextStageNumber,
    phase: envelope.phase,
    status: envelope.status,
    cash: closingCash,
    remainingDebt: closingDebt,
    cumulativeRepayment,
    debtClearedAtDeadline,
    pendingDayResult: null,
    ledger: [...cloneJson(state.ledger), entry],
  };
  validateCampaignFinanceState(config, next);
  return next;
}

function validateTrueExtensionConfigPair(baseConfig, extendedConfig) {
  validateCampaignFinanceConfig(baseConfig);
  validateCampaignFinanceConfig(extendedConfig);
  assert(baseConfig.total_stages === CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE,
    "baseConfig must end at day 56");
  assert(extendedConfig.total_stages === 70,
    "extendedConfig must extend the campaign to day 70");
  assert(baseConfig.id !== extendedConfig.id,
    "extendedConfig.id must distinguish the extended finance authority");
  assert(baseConfig.version === extendedConfig.version,
    "extendedConfig.version cannot differ from the base contract");
  for (const key of [
    "contract_status",
    "debt_deadline_stage",
    "debt_gate_id",
    "starting_cash",
    "principal",
  ]) {
    assert(baseConfig[key] === extendedConfig[key],
      `extendedConfig.${key} cannot differ from baseConfig`);
  }
  for (const stageNumber of CAMPAIGN_FINANCE_CHECKPOINT_STAGES) {
    assert(
      baseConfig.chapter_cumulative_targets[String(stageNumber)]
        === extendedConfig.chapter_cumulative_targets[String(stageNumber)],
      "extendedConfig.chapter_cumulative_targets must preserve the base targets",
    );
  }
}

export function unlockCampaignFinanceTrueExtension(
  baseConfig,
  extendedConfig,
  state,
  debtGateEvidence,
) {
  validateTrueExtensionConfigPair(baseConfig, extendedConfig);
  validateCampaignFinanceState(baseConfig, state);
  assert(state.completedStageCount === CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE,
    "true finance extension cannot unlock before day 56 settlement");
  assert(state.status === "COMPLETE" && state.phase === "CLOSED",
    "true finance extension requires the completed base finance state");
  assert(state.debtClearedAtDeadline === true && state.remainingDebt === 0,
    "true finance extension requires debt cleared at day 56");
  const expectedEvidence = campaignDebtGateEvidence(baseConfig, state);
  assert(sameFlatRecord(debtGateEvidence, expectedEvidence),
    "debtGateEvidence does not match the base finance ledger");
  assert(debtGateEvidence.passed === true,
    "debtGateEvidence must explicitly pass");

  const next = {
    ...state,
    configId: extendedConfig.id,
    configVersion: extendedConfig.version,
    totalStages: extendedConfig.total_stages,
    nextStageNumber: CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE + 1,
    phase: "AWAITING_RESULT",
    status: "ACTIVE",
    pendingDayResult: null,
    ledger: cloneJson(state.ledger),
  };
  validateCampaignFinanceState(extendedConfig, next);
  return next;
}

export function campaignDebtGateEvidence(config, state) {
  validateCampaignFinanceState(config, state);
  assert(state.completedStageCount >= CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE,
    "day 56 must be settled before debt gate evidence exists");
  const deadlineEntry = state.ledger[CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE - 1];
  const passed = deadlineEntry.closingDebt === 0;
  return {
    type: "CAMPAIGN_DEBT_GATE_EVIDENCE",
    gateId: config.debt_gate_id,
    passed,
    boundaryStageNumber: CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE,
    financeConfigId: config.id,
    financeConfigVersion: config.version,
    originalPrincipal: config.principal,
    cumulativeRepaymentAtBoundary: deadlineEntry.cumulativeRepayment,
    remainingDebtAtBoundary: deadlineEntry.closingDebt,
    checkpointOutcome: deadlineEntry.checkpoint.outcome,
    ledgerEntryCountAtBoundary: CAMPAIGN_FINANCE_DEBT_DEADLINE_STAGE,
    debtGraceAfterBoundary: false,
  };
}
