import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const TOOL_DIR = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(TOOL_DIR, "..");
const FINANCE_SOURCE_PATH = resolve(ROOT, "src", "campaign-finance.js");
const DEFAULT_FIXTURE_PATH = resolve(
  TOOL_DIR,
  "fixtures",
  "campaign_finance_conformance_v1.json",
);
const FIXTURE_SCHEMA_VERSION = 1;
const CONTRACT_STATUS = "PROVISIONAL";
const BALANCE_VERDICT = "NOT_EVALUATED";
const RUNTIME_POLICY_KEYS = [
  "id",
  "version",
  "status",
  "balance_verdict",
  "base_daily_upkeep",
  "upkeep_per_owned_upgrade",
];

const clone = value => (value === undefined ? undefined : JSON.parse(JSON.stringify(value)));

class OracleError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

function requireCondition(condition, code, message) {
  if (!condition) throw new OracleError(code, message);
}

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function exactKeys(value, keys) {
  if (!isPlainObject(value)) return false;
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  return actual.length === expected.length
    && actual.every((key, index) => key === expected[index]);
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

function validateRuntimePolicy(policy) {
  requireCondition(exactKeys(policy, RUNTIME_POLICY_KEYS), "INVALID_SHAPE",
    "runtime policy has an invalid shape");
  requireCondition(nonEmptyString(policy.id), "INVALID_STRING",
    "runtime policy id must be a non-empty string");
  requireCondition(positiveSafeInteger(policy.version), "INVALID_POSITIVE_INTEGER",
    "runtime policy version must be a positive safe integer");
  requireCondition(
    policy.status === CONTRACT_STATUS && policy.balance_verdict === BALANCE_VERDICT,
    "INVALID_POLICY",
    "runtime policy must remain PROVISIONAL/NOT_EVALUATED",
  );
  requireCondition(nonNegativeSafeInteger(policy.base_daily_upkeep), "INVALID_AMOUNT",
    "runtime policy base upkeep must be a non-negative safe integer");
  requireCondition(nonNegativeSafeInteger(policy.upkeep_per_owned_upgrade), "INVALID_AMOUNT",
    "runtime policy upgrade upkeep must be a non-negative safe integer");
}

function validateFixtureHeader(raw) {
  requireCondition(isPlainObject(raw), "INVALID_FIXTURE", "fixture root must be an object");
  const version = raw.schemaVersion ?? raw.schema_version;
  requireCondition(
    positiveSafeInteger(version) && version === FIXTURE_SCHEMA_VERSION,
    "INVALID_FIXTURE",
    `fixture schema must be ${FIXTURE_SCHEMA_VERSION}`,
  );
  requireCondition(Array.isArray(raw.cases) && raw.cases.length > 0,
    "INVALID_FIXTURE", "fixture cases must be non-empty");
}

function errorCode(error) {
  if (error instanceof OracleError) return error.code;
  const message = String(error?.message ?? error);
  const mappings = [
    ["exceeds the safe-integer range", "SAFE_INTEGER_OVERFLOW"],
    ["must be a positive safe integer", "INVALID_POSITIVE_INTEGER"],
    ["must be a non-negative safe integer", "INVALID_AMOUNT"],
    ["day 57 and later cannot accept debt repayment", "INVALID_MANUAL_REPAYMENT_POST_DEADLINE"],
    ["manual repayment exceeds available cash", "MANUAL_REPAYMENT_EXCEEDS_CASH"],
    ["manual repayment exceeds remaining debt", "MANUAL_REPAYMENT_EXCEEDS_DEBT"],
    ["a day result can be committed only while awaiting", "RESULT_NOT_AWAITED"],
    ["result.stageNumber does not match", "STAGE_MISMATCH"],
    ["campaignOperationId already exists", "DUPLICATE_OPERATION_ID"],
    ["day 57 and later cannot carry unresolved debt", "UNRESOLVED_POST_DEADLINE_DEBT"],
    ["settlement requires a committed day result", "RESULT_NOT_COMMITTED"],
    ["true finance extension requires", "TRUE_EXTENSION_NOT_ELIGIBLE"],
    ["debtGateEvidence does not match", "TRUE_EXTENSION_EVIDENCE_MISMATCH"],
  ];
  return mappings.find(([needle]) => message.includes(needle))?.[1] ?? "JS_ORACLE_REJECTED";
}

async function importProductionFinance() {
  const source = await readFile(FINANCE_SOURCE_PATH, "utf8");
  const encoded = Buffer.from(source, "utf8").toString("base64");
  return import(`data:text/javascript;base64,${encoded}`);
}

function materializeOperations(caseId, rawOperations, policy) {
  let operations = rawOperations;
  if (operations && !Array.isArray(operations)) {
    const count = operations.throughStage ?? operations.count;
    const defaults = operations.defaults ?? {};
    const overrides = operations.overrides ?? {};
    operations = Array.from({ length: count }, (_, index) => ({
      ...defaults,
      ...(overrides[String(index + 1)] ?? {}),
    }));
  }
  requireCondition(Array.isArray(operations), "INVALID_FIXTURE", `${caseId} has no operations`);
  return operations.map((raw, index) => {
    const stageNumber = index + 1;
    const ownedUpgradeCount = raw.ownedUpgradeCount ?? 0;
    const upkeep = policy.base_daily_upkeep
      + policy.upkeep_per_owned_upgrade * ownedUpgradeCount;
    return {
      stageNumber,
      campaignOperationId: raw.campaignOperationId ?? `${caseId}:NORMAL:${stageNumber}`,
      campaignResultIdentity: {
        stageNumber,
        operationKind: "NORMAL",
        templateIndex: raw.templateIndex ?? ((stageNumber - 1) % 5),
      },
      income: raw.income ?? 0,
      ownedUpgradeCount,
      upkeep: raw.upkeep ?? upkeep,
      reactivation: raw.reactivation ?? 0,
      roomService: raw.roomService ?? 0,
      manualRepayment: raw.manualRepayment ?? 0,
    };
  });
}

function materializeFixture(raw) {
  validateFixtureHeader(raw);
  if (
    raw.schemaVersion === FIXTURE_SCHEMA_VERSION
    && Array.isArray(raw.cases)
    && raw.cases.every(caseData => Array.isArray(caseData.operations))
    && raw.cases.every(caseData => caseData.baseConfig && caseData.runtimePolicy)
  ) {
    raw.cases.forEach(caseData => validateRuntimePolicy(caseData.runtimePolicy));
    return clone(raw);
  }

  const defaults = raw.defaults ?? {};
  return {
    schemaVersion: FIXTURE_SCHEMA_VERSION,
    contractStatus: CONTRACT_STATUS,
    balanceVerdict: BALANCE_VERDICT,
    cases: raw.cases.map(rawCase => {
      const merged = { ...clone(defaults), ...clone(rawCase) };
      validateRuntimePolicy(merged.runtimePolicy);
      return {
        id: merged.id,
        seed: merged.seed ?? 1,
        baseConfig: merged.baseConfig,
        extendedConfig: merged.extendedConfig,
        runtimePolicy: merged.runtimePolicy,
        unlockTrueExtension: merged.unlockTrueExtension ?? false,
        operations: materializeOperations(merged.id, merged.operations, merged.runtimePolicy),
        expected: merged.expected ?? {},
      };
    }),
  };
}

function traceState(event, state, stageNumber, adapterState) {
  let checkpoint = null;
  const last = state.ledger.at(-1);
  if (last && last.stageNumber === stageNumber) checkpoint = clone(last.checkpoint);
  return {
    event,
    stageNumber,
    phase: state.phase,
    status: state.status,
    completedStageCount: state.completedStageCount,
    nextStageNumber: state.nextStageNumber,
    totalStages: state.totalStages,
    cash: state.cash,
    remainingDebt: state.remainingDebt,
    cumulativeRepayment: state.cumulativeRepayment,
    debtClearedAtDeadline: state.debtClearedAtDeadline,
    checkpoint,
    operatingFailure: clone(state.operatingFailure),
    adapterState: clone(adapterState),
  };
}

function financeLedgerMetrics(state) {
  const sum = key => state.ledger.reduce((total, row) => total + row[key], 0);
  return {
    scope: "FINANCE_LEDGER_ONLY",
    includesOnlySettledLedgerEntries: true,
    excludesFailedPreparationExpenses: true,
    completedStageCount: state.completedStageCount,
    cash: state.cash,
    financeCash: state.cash,
    remainingDebt: state.remainingDebt,
    cumulativeRepayment: state.cumulativeRepayment,
    income: sum("income"),
    upkeep: sum("upkeep"),
    reactivation: sum("reactivation"),
    roomService: sum("roomService"),
    manualRepayment: sum("manualRepayment"),
  };
}

function adapterMetrics(state, adapterState) {
  const pending = adapterState.pendingExpenses;
  const pendingTotal = pending.reactivation + pending.roomService;
  requireCondition(Number.isSafeInteger(pendingTotal), "SAFE_INTEGER_OVERFLOW",
    "adapter pending expense total exceeds the safe-integer range");
  requireCondition(adapterState.liveCash + pendingTotal === state.cash,
    "ADAPTER_CASH_INVARIANT_DRIFT",
    "adapter live cash plus paid pending expenses must equal finance cash");
  const failedPreparation = state.status === "OPERATING_CASH_SHORTFALL";
  return {
    scope: "LIVE_CASH_AND_PENDING_PREPARATION",
    liveCash: adapterState.liveCash,
    financeCash: state.cash,
    pendingExpenses: clone(pending),
    pendingExpenseTotal: pendingTotal,
    pendingExpensesAlreadyPaid: pendingTotal > 0,
    failedPreparationExpenses: {
      reactivation: failedPreparation ? pending.reactivation : 0,
      roomService: failedPreparation ? pending.roomService : 0,
      total: failedPreparation ? pendingTotal : 0,
    },
  };
}

function legacyMetrics(settledMetrics) {
  return {
    completedStageCount: settledMetrics.completedStageCount,
    cash: settledMetrics.cash,
    remainingDebt: settledMetrics.remainingDebt,
    cumulativeRepayment: settledMetrics.cumulativeRepayment,
    income: settledMetrics.income,
    upkeep: settledMetrics.upkeep,
    reactivation: settledMetrics.reactivation,
    roomService: settledMetrics.roomService,
    manualRepayment: settledMetrics.manualRepayment,
  };
}

function validateConfigPair(finance, base, extended) {
  finance.validateCampaignFinanceConfig(base);
  finance.validateCampaignFinanceConfig(extended);
  requireCondition(base.total_stages === 56, "INVALID_CONFIG_PAIR", "base config must end at 56");
  requireCondition(extended.total_stages === 70,
    "INVALID_CONFIG_PAIR", "extended config must end at 70");
  requireCondition(base.id !== extended.id, "INVALID_CONFIG_PAIR", "config ids must differ");
  for (const key of [
    "version",
    "contract_status",
    "debt_deadline_stage",
    "debt_gate_id",
    "starting_cash",
    "principal",
    "chapter_cumulative_targets",
  ]) {
    requireCondition(JSON.stringify(base[key]) === JSON.stringify(extended[key]),
      "INVALID_CONFIG_PAIR", `extended config cannot change ${key}`);
  }
}

function calculateUpkeep(policy, ownedUpgradeCount) {
  validateRuntimePolicy(policy);
  requireCondition(Number.isSafeInteger(ownedUpgradeCount) && ownedUpgradeCount >= 0,
    "INVALID_AMOUNT", "ownedUpgradeCount must be a non-negative safe integer");
  const upgradeUpkeep = policy.upkeep_per_owned_upgrade * ownedUpgradeCount;
  const total = policy.base_daily_upkeep + upgradeUpkeep;
  requireCondition(Number.isSafeInteger(upgradeUpkeep) && Number.isSafeInteger(total),
    "SAFE_INTEGER_OVERFLOW", "daily upkeep exceeds the safe-integer range");
  return total;
}

function simulateCase(finance, caseData) {
  const base = caseData.baseConfig;
  const extended = caseData.extendedConfig;
  const policy = caseData.runtimePolicy;
  validateConfigPair(finance, base, extended);
  validateRuntimePolicy(policy);

  let state = finance.createCampaignFinanceState(base);
  let activeConfig = base;
  let adapterState = {
    liveCash: state.cash,
    ownedUpgradeCount: 0,
    pendingExpenses: { reactivation: 0, roomService: 0 },
  };
  const trace = [traceState("INITIAL", state, null, adapterState)];
  let debtGateEvidence = null;
  let operationsApplied = 0;

  for (const operation of caseData.operations) {
    requireCondition(state.status === "ACTIVE", "UNUSED_OPERATIONS_AFTER_TERMINAL",
      `operation ${operation.stageNumber} follows terminal status ${state.status}`);
    requireCondition(
      operation.upkeep === calculateUpkeep(policy, operation.ownedUpgradeCount),
      "UPKEEP_ADAPTER_DRIFT",
      `operation ${operation.stageNumber} upkeep differs from runtime policy`,
    );
    requireCondition(operation.ownedUpgradeCount >= adapterState.ownedUpgradeCount,
      "OWNED_UPGRADE_COUNT_DECREASED", "owned upgrade count cannot decrease");
    const pendingTotal = operation.reactivation + operation.roomService;
    requireCondition(Number.isSafeInteger(pendingTotal), "SAFE_INTEGER_OVERFLOW",
      "pending preparation expenses exceed the safe-integer range");
    requireCondition(pendingTotal <= state.cash, "PREPARATION_COST_EXCEEDS_LIVE_CASH",
      "preparation expense exceeds live cash and could not have been purchased");
    adapterState = {
      liveCash: state.cash - pendingTotal,
      ownedUpgradeCount: operation.ownedUpgradeCount,
      pendingExpenses: {
        reactivation: operation.reactivation,
        roomService: operation.roomService,
      },
    };
    trace.push(traceState("OPERATION_PREPARED", state, operation.stageNumber, adapterState));
    const result = {
      stageNumber: operation.stageNumber,
      campaignOperationId: operation.campaignOperationId,
      campaignResultIdentity: clone(operation.campaignResultIdentity),
      income: operation.income,
      upkeep: operation.upkeep,
      reactivation: operation.reactivation,
      roomService: operation.roomService,
    };
    state = finance.commitCampaignDayResult(activeConfig, state, result);
    operationsApplied += 1;
    if (state.status !== "OPERATING_CASH_SHORTFALL") {
      adapterState = {
        liveCash: state.cash,
        ownedUpgradeCount: operation.ownedUpgradeCount,
        pendingExpenses: { reactivation: 0, roomService: 0 },
      };
    }
    trace.push(traceState("RESULT_COMMITTED", state, operation.stageNumber, adapterState));
    if (state.status === "OPERATING_CASH_SHORTFALL") continue;

    state = finance.settleCampaignDay(activeConfig, state, {
      manualRepayment: operation.manualRepayment,
    });
    adapterState.liveCash = state.cash;
    trace.push(traceState("DAY_SETTLED", state, operation.stageNumber, adapterState));
    if (operation.stageNumber === 56) {
      debtGateEvidence = finance.campaignDebtGateEvidence(base, state);
      if (caseData.unlockTrueExtension && debtGateEvidence.passed) {
        state = finance.unlockCampaignFinanceTrueExtension(
          base,
          extended,
          state,
          debtGateEvidence,
        );
        activeConfig = extended;
        trace.push(traceState("TRUE_EXTENSION_UNLOCKED", state, 56, adapterState));
      }
    }
  }

  const settledMetrics = financeLedgerMetrics(state);
  const liveAdapterMetrics = adapterMetrics(state, adapterState);
  return {
    id: caseData.id,
    accepted: true,
    contractStatus: CONTRACT_STATUS,
    balanceVerdict: BALANCE_VERDICT,
    operationsApplied,
    debtGateEvidence,
    finalState: state,
    adapterState,
    metrics: legacyMetrics(settledMetrics),
    financeLedgerMetrics: settledMetrics,
    adapterMetrics: liveAdapterMetrics,
    trace,
  };
}

function simulateFixture(finance, fixture) {
  const results = fixture.cases.map(caseData => {
    try {
      return simulateCase(finance, caseData);
    } catch (error) {
      return {
        id: caseData.id,
        accepted: false,
        contractStatus: CONTRACT_STATUS,
        balanceVerdict: BALANCE_VERDICT,
        error: { code: errorCode(error) },
      };
    }
  });
  return {
    schemaVersion: FIXTURE_SCHEMA_VERSION,
    contractStatus: CONTRACT_STATUS,
    balanceVerdict: BALANCE_VERDICT,
    cases: results,
  };
}

async function readInput() {
  const inputPath = process.argv[2] ?? DEFAULT_FIXTURE_PATH;
  if (inputPath === "-") {
    const chunks = [];
    for await (const chunk of process.stdin) chunks.push(chunk);
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  }
  return JSON.parse(await readFile(resolve(process.cwd(), inputPath), "utf8"));
}

async function main() {
  const [finance, raw] = await Promise.all([importProductionFinance(), readInput()]);
  requireCondition(finance.CAMPAIGN_FINANCE_SCHEMA_VERSION === 3,
    "AUTHORITY_DRIFT", "production finance schema drifted");
  requireCondition(finance.CAMPAIGN_FINANCE_CONTRACT_STATUS === "PROVISIONAL",
    "AUTHORITY_DRIFT", "production finance contract status drifted");
  requireCondition(finance.CAMPAIGN_FINANCE_BALANCE_VERDICT === "NOT_EVALUATED",
    "AUTHORITY_DRIFT", "production balance boundary drifted");
  const fixture = materializeFixture(raw);
  process.stdout.write(`${JSON.stringify(simulateFixture(finance, fixture))}\n`);
}

main().catch(error => {
  process.stderr.write(`${JSON.stringify({
    status: "ORACLE_ERROR",
    error: { code: errorCode(error), message: String(error?.message ?? error) },
  })}\n`);
  process.exitCode = 2;
});
