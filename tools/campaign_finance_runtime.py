from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


MAX_SAFE_INTEGER = (1 << 53) - 1
SCHEMA_VERSION = 3
CONTRACT_STATUS = "PROVISIONAL"
BALANCE_VERDICT = "NOT_EVALUATED"
DEBT_DEADLINE_STAGE = 56
DEBT_GATE_ID = "BASE_DEBT_CLEARED_AT_STAGE_56"
CHECKPOINT_STAGES = (7, 14, 28, 42, 56)
SUPPORTED_STAGE_LIMITS = (56, 70)
SETTLEMENT_SEQUENCE = "RESULT_COMMIT_THEN_OPTIONAL_REPAYMENT_THEN_CHECKPOINT"
FIXTURE_SCHEMA_VERSION = 1


class FinanceSimulationError(ValueError):
    """A stable Python-side rejection category for JS/Python conformance."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _reject(code: str, message: str) -> None:
    raise FinanceSimulationError(code, message)


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        _reject(code, message)


def _is_plain_object(value: Any) -> bool:
    return isinstance(value, dict)


def _is_safe_integer(value: Any, *, positive: bool = False) -> bool:
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    lower = 1 if positive else 0
    return lower <= value <= MAX_SAFE_INTEGER


def _amount(value: Any, owner: str) -> int:
    _require(
        _is_safe_integer(value),
        "INVALID_AMOUNT",
        f"{owner} must be a non-negative JavaScript safe integer",
    )
    return value


def _positive_integer(value: Any, owner: str) -> int:
    _require(
        _is_safe_integer(value, positive=True),
        "INVALID_POSITIVE_INTEGER",
        f"{owner} must be a positive JavaScript safe integer",
    )
    return value


def _safe_sum(owner: str, *values: int) -> int:
    checked = [_amount(value, f"{owner}[{index}]") for index, value in enumerate(values)]
    total = sum(checked)
    _require(
        total <= MAX_SAFE_INTEGER,
        "SAFE_INTEGER_OVERFLOW",
        f"{owner} exceeds the JavaScript safe-integer range",
    )
    return total


def _non_empty_string(value: Any, owner: str) -> str:
    _require(
        isinstance(value, str) and bool(value.strip()),
        "INVALID_STRING",
        f"{owner} must be a non-empty string",
    )
    return value.strip()


def _exact_keys(value: Any, keys: set[str], owner: str) -> None:
    _require(_is_plain_object(value), "INVALID_SHAPE", f"{owner} must be an object")
    actual = set(value)
    _require(
        actual == keys,
        "INVALID_SHAPE",
        f"{owner} keys differ: missing={sorted(keys - actual)}, extra={sorted(actual - keys)}",
    )


def _clone(value: Any) -> Any:
    return copy.deepcopy(value)


CONFIG_KEYS = {
    "id",
    "version",
    "contract_status",
    "total_stages",
    "debt_deadline_stage",
    "debt_gate_id",
    "starting_cash",
    "principal",
    "chapter_cumulative_targets",
}

RUNTIME_POLICY_KEYS = {
    "id",
    "version",
    "status",
    "balance_verdict",
    "base_daily_upkeep",
    "upkeep_per_owned_upgrade",
}

OPERATION_KEYS = {
    "stageNumber",
    "campaignOperationId",
    "campaignResultIdentity",
    "income",
    "ownedUpgradeCount",
    "upkeep",
    "reactivation",
    "roomService",
    "manualRepayment",
}

RESULT_KEYS = {
    "stageNumber",
    "campaignOperationId",
    "campaignResultIdentity",
    "income",
    "upkeep",
    "reactivation",
    "roomService",
}

SETTLEMENT_KEYS = {"manualRepayment"}

STATE_KEYS = {
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
    "operatingFailure",
    "ledger",
}

PENDING_RESULT_KEYS = {
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
}

LEDGER_ENTRY_KEYS = {
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
}

OPERATING_FAILURE_KEYS = {
    "type",
    "stageNumber",
    "campaignOperationId",
    "campaignResultIdentity",
    "openingCash",
    "income",
    "availableCash",
    "upkeep",
    "reactivation",
    "roomService",
    "operatingOutflow",
    "shortfallAmount",
}

CAMPAIGN_RESULT_IDENTITY_KEYS = {
    "stageNumber",
    "operationKind",
    "templateIndex",
}

FINANCE_LEDGER_METRICS_SCOPE = "FINANCE_LEDGER_ONLY"
ADAPTER_METRICS_SCOPE = "LIVE_CASH_AND_PENDING_PREPARATION"


def validate_config(config: dict[str, Any]) -> None:
    _exact_keys(config, CONFIG_KEYS, "finance config")
    _non_empty_string(config["id"], "config.id")
    _positive_integer(config["version"], "config.version")
    _require(
        config["contract_status"] == CONTRACT_STATUS,
        "INVALID_CONFIG",
        f"config.contract_status must remain {CONTRACT_STATUS}",
    )
    _require(
        config["total_stages"] in SUPPORTED_STAGE_LIMITS,
        "INVALID_CONFIG",
        "config.total_stages must be 56 or 70",
    )
    _require(
        config["debt_deadline_stage"] == DEBT_DEADLINE_STAGE,
        "INVALID_CONFIG",
        "config.debt_deadline_stage must be 56",
    )
    _require(
        config["debt_gate_id"] == DEBT_GATE_ID,
        "INVALID_CONFIG",
        f"config.debt_gate_id must be {DEBT_GATE_ID}",
    )
    _amount(config["starting_cash"], "config.starting_cash")
    principal = _amount(config["principal"], "config.principal")
    targets = config["chapter_cumulative_targets"]
    _exact_keys(targets, {str(stage) for stage in CHECKPOINT_STAGES}, "chapter targets")
    prior = 0
    for stage in CHECKPOINT_STAGES:
        target = _amount(targets[str(stage)], f"chapter target {stage}")
        _require(target >= prior, "INVALID_CONFIG", "chapter targets must not decrease")
        _require(target <= principal, "INVALID_CONFIG", "chapter target exceeds principal")
        prior = target
    _require(
        targets[str(DEBT_DEADLINE_STAGE)] == principal,
        "INVALID_CONFIG",
        "day 56 target must equal principal",
    )


def validate_runtime_policy(policy: dict[str, Any]) -> None:
    _exact_keys(policy, RUNTIME_POLICY_KEYS, "runtime policy")
    _non_empty_string(policy["id"], "runtime policy id")
    _positive_integer(policy["version"], "runtime policy version")
    _require(
        policy["status"] == CONTRACT_STATUS and policy["balance_verdict"] == BALANCE_VERDICT,
        "INVALID_POLICY",
        "runtime policy must remain PROVISIONAL/NOT_EVALUATED",
    )
    _amount(policy["base_daily_upkeep"], "runtime policy base upkeep")
    _amount(policy["upkeep_per_owned_upgrade"], "runtime policy upgrade upkeep")


def validate_config_pair(base: dict[str, Any], extended: dict[str, Any]) -> None:
    validate_config(base)
    validate_config(extended)
    _require(base["total_stages"] == 56, "INVALID_CONFIG_PAIR", "base config must end at 56")
    _require(extended["total_stages"] == 70, "INVALID_CONFIG_PAIR", "extended config must end at 70")
    _require(base["id"] != extended["id"], "INVALID_CONFIG_PAIR", "config ids must differ")
    for key in (
        "version",
        "contract_status",
        "debt_deadline_stage",
        "debt_gate_id",
        "starting_cash",
        "principal",
        "chapter_cumulative_targets",
    ):
        _require(
            base[key] == extended[key],
            "INVALID_CONFIG_PAIR",
            f"extended config cannot change {key}",
        )


def calculate_upkeep(policy: dict[str, Any], owned_upgrade_count: int) -> int:
    validate_runtime_policy(policy)
    count = _amount(owned_upgrade_count, "ownedUpgradeCount")
    per_upgrade = policy["upkeep_per_owned_upgrade"]
    upgrade_upkeep = count * per_upgrade
    _require(
        upgrade_upkeep <= MAX_SAFE_INTEGER,
        "SAFE_INTEGER_OVERFLOW",
        "upgrade upkeep exceeds the JavaScript safe-integer range",
    )
    return _safe_sum("daily upkeep", policy["base_daily_upkeep"], upgrade_upkeep)


def _materialize_operation(
    case_id: str,
    stage_number: int,
    raw: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    allowed = {
        "income",
        "ownedUpgradeCount",
        "upkeep",
        "reactivation",
        "roomService",
        "manualRepayment",
        "campaignOperationId",
        "templateIndex",
    }
    _require(
        _is_plain_object(raw) and set(raw).issubset(allowed),
        "INVALID_OPERATION",
        f"operation {stage_number} has an invalid shape",
    )
    income = _amount(raw.get("income", 0), f"operation {stage_number} income")
    owned = _amount(
        raw.get("ownedUpgradeCount", 0),
        f"operation {stage_number} ownedUpgradeCount",
    )
    derived_upkeep = calculate_upkeep(policy, owned)
    if "upkeep" in raw:
        explicit_upkeep = _amount(raw["upkeep"], f"operation {stage_number} upkeep")
        _require(
            explicit_upkeep == derived_upkeep,
            "UPKEEP_ADAPTER_DRIFT",
            f"operation {stage_number} upkeep differs from runtime policy",
        )
    operation_id = _non_empty_string(
        raw.get("campaignOperationId", f"{case_id}:NORMAL:{stage_number}"),
        f"operation {stage_number} id",
    )
    template_index = _amount(
        raw.get("templateIndex", (stage_number - 1) % 5),
        f"operation {stage_number} templateIndex",
    )
    return {
        "stageNumber": stage_number,
        "campaignOperationId": operation_id,
        "campaignResultIdentity": {
            "stageNumber": stage_number,
            "operationKind": "NORMAL",
            "templateIndex": template_index,
        },
        "income": income,
        "ownedUpgradeCount": owned,
        "upkeep": derived_upkeep,
        "reactivation": _amount(
            raw.get("reactivation", 0),
            f"operation {stage_number} reactivation",
        ),
        "roomService": _amount(
            raw.get("roomService", 0),
            f"operation {stage_number} roomService",
        ),
        "manualRepayment": _amount(
            raw.get("manualRepayment", 0),
            f"operation {stage_number} manualRepayment",
        ),
    }


def _materialize_case(raw: dict[str, Any]) -> dict[str, Any]:
    _require(_is_plain_object(raw), "INVALID_CASE", "fixture case must be an object")
    case_id = _non_empty_string(raw.get("id"), "case.id")
    base = _clone(raw.get("baseConfig", raw.get("base_config")))
    extended = _clone(raw.get("extendedConfig", raw.get("extended_config")))
    policy = _clone(raw.get("runtimePolicy", raw.get("runtime_policy")))
    _require(
        _is_plain_object(base) and _is_plain_object(extended) and _is_plain_object(policy),
        "INVALID_CASE",
        f"{case_id} requires base, extended, and runtime policy objects",
    )
    validate_config_pair(base, extended)
    validate_runtime_policy(policy)
    seed = _positive_integer(raw.get("seed", 1), f"{case_id}.seed")
    unlock = raw.get("unlockTrueExtension", raw.get("unlock_true_extension", False))
    _require(isinstance(unlock, bool), "INVALID_CASE", "unlockTrueExtension must be boolean")

    operations_raw = raw.get("operations")
    plan = None
    if _is_plain_object(operations_raw):
        plan = operations_raw
        operations_raw = None
    if operations_raw is None:
        plan = plan or raw.get("operationPlan", raw.get("operation_plan"))
        _require(_is_plain_object(plan), "INVALID_CASE", f"{case_id} needs operations or a plan")
        plan_keys = set(plan)
        _require(
            plan_keys in (
                {"count", "defaults", "overrides"},
                {"throughStage", "defaults", "overrides"},
            ),
            "INVALID_SHAPE",
            f"{case_id}.operationPlan must use count or throughStage",
        )
        count_raw = plan.get("count", plan.get("throughStage"))
        count = _positive_integer(count_raw, f"{case_id}.operationPlan.count")
        _require(count <= 70, "INVALID_CASE", "operation plan cannot exceed day 70")
        defaults = plan["defaults"]
        overrides = plan["overrides"]
        _require(_is_plain_object(defaults), "INVALID_CASE", "operation defaults must be an object")
        _require(_is_plain_object(overrides), "INVALID_CASE", "operation overrides must be an object")
        operations_raw = []
        for stage_number in range(1, count + 1):
            override = overrides.get(str(stage_number), {})
            _require(_is_plain_object(override), "INVALID_CASE", "operation override must be an object")
            operations_raw.append({**defaults, **override})
    _require(isinstance(operations_raw, list), "INVALID_CASE", "operations must be a list")
    operations = [
        _materialize_operation(case_id, index, operation, policy)
        for index, operation in enumerate(operations_raw, start=1)
    ]
    expected = _clone(raw.get("expected", {}))
    _require(_is_plain_object(expected), "INVALID_CASE", "expected must be an object")
    return {
        "id": case_id,
        "seed": seed,
        "baseConfig": base,
        "extendedConfig": extended,
        "runtimePolicy": policy,
        "unlockTrueExtension": unlock,
        "operations": operations,
        "expected": expected,
    }


def materialize_fixture(raw: dict[str, Any]) -> dict[str, Any]:
    _require(_is_plain_object(raw), "INVALID_FIXTURE", "fixture root must be an object")
    version = raw.get("schemaVersion", raw.get("schema_version"))
    _require(
        type(version) is int and version == FIXTURE_SCHEMA_VERSION,
        "INVALID_FIXTURE",
        f"fixture schema must be {FIXTURE_SCHEMA_VERSION}",
    )
    cases_raw = raw.get("cases")
    _require(isinstance(cases_raw, list) and cases_raw, "INVALID_FIXTURE", "cases must be non-empty")
    defaults = raw.get("defaults", {})
    _require(_is_plain_object(defaults), "INVALID_FIXTURE", "defaults must be an object")
    cases = [
        _materialize_case({**_clone(defaults), **case})
        for case in cases_raw
    ]
    ids = [case["id"] for case in cases]
    _require(len(ids) == len(set(ids)), "INVALID_FIXTURE", "case ids must be unique")
    return {
        "schemaVersion": FIXTURE_SCHEMA_VERSION,
        "contractStatus": CONTRACT_STATUS,
        "balanceVerdict": BALANCE_VERDICT,
        "cases": cases,
    }


def load_fixture(path: str | Path) -> dict[str, Any]:
    fixture_path = Path(path)
    return materialize_fixture(json.loads(fixture_path.read_text(encoding="utf-8")))


def create_finance_state(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    _require(config["total_stages"] == 56, "INVALID_CONFIG", "new finance must begin at 56")
    state = {
        "type": "CAMPAIGN_FINANCE_STATE",
        "schemaVersion": SCHEMA_VERSION,
        "configId": config["id"],
        "configVersion": config["version"],
        "contractStatus": CONTRACT_STATUS,
        "balanceVerdict": BALANCE_VERDICT,
        "totalStages": config["total_stages"],
        "debtDeadlineStageNumber": DEBT_DEADLINE_STAGE,
        "completedStageCount": 0,
        "nextStageNumber": 1,
        "phase": "AWAITING_RESULT",
        "status": "ACTIVE",
        "cash": config["starting_cash"],
        "originalPrincipal": config["principal"],
        "remainingDebt": config["principal"],
        "cumulativeRepayment": 0,
        "debtClearedAtDeadline": None,
        "pendingDayResult": None,
        "operatingFailure": None,
        "ledger": [],
    }
    validate_campaign_finance_state(config, state)
    return state


def _checkpoint(
    config: dict[str, Any],
    stage_number: int,
    cumulative_repayment: int,
    remaining_debt: int,
) -> dict[str, Any] | None:
    if stage_number not in CHECKPOINT_STAGES:
        return None
    target = config["chapter_cumulative_targets"][str(stage_number)]
    shortfall = max(0, target - cumulative_repayment)
    final = stage_number == DEBT_DEADLINE_STAGE
    if final:
        outcome = "DEBT_CLEARED" if remaining_debt == 0 else "DEBT_DEADLINE_MISSED"
    else:
        outcome = "CHAPTER_HURDLE_MISSED" if shortfall > 0 else "MET"
    return {
        "type": "CAMPAIGN_DEBT_CHECKPOINT",
        "stageNumber": stage_number,
        "kind": "FINAL_CLEARANCE" if final else "CUMULATIVE_MINIMUM",
        "targetAmount": target,
        "cumulativeRepayment": cumulative_repayment,
        "remainingDebt": remaining_debt,
        "shortfallAmount": shortfall,
        "outcome": outcome,
        "debtDeadlineExtended": False,
    }


def _terminal_status(checkpoint: dict[str, Any] | None) -> str | None:
    if checkpoint and checkpoint["outcome"] in {
        "CHAPTER_HURDLE_MISSED",
        "DEBT_DEADLINE_MISSED",
    }:
        return checkpoint["outcome"]
    return None


def _strict_equal(left: Any, right: Any) -> bool:
    """Approximate JavaScript strict equality for JSON-compatible scalars."""

    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    return type(left) is type(right) and left == right


def _same_ordered_flat_record(value: Any, expected: dict[str, Any]) -> bool:
    if not _is_plain_object(value) or list(value) != list(expected):
        return False
    return all(_strict_equal(value[key], expected[key]) for key in expected)


def _same_flat_record(value: Any, expected: dict[str, Any]) -> bool:
    if not _is_plain_object(value) or set(value) != set(expected):
        return False
    return all(_strict_equal(value[key], expected[key]) for key in expected)


def _validate_campaign_result_identity(
    identity: Any,
    stage_number: int,
    owner: str,
) -> None:
    _exact_keys(identity, CAMPAIGN_RESULT_IDENTITY_KEYS, owner)
    _require(
        _strict_equal(identity["stageNumber"], stage_number),
        "INVALID_OPERATION_IDENTITY",
        f"{owner}.stageNumber must match the finance stage",
    )
    _require(
        identity["operationKind"] == "NORMAL",
        "INVALID_OPERATION_IDENTITY",
        f"{owner}.operationKind is unknown",
    )
    _amount(identity["templateIndex"], f"{owner}.templateIndex")


def _validate_campaign_operation_identity(
    operation_id: Any,
    result_identity: Any,
    stage_number: int,
    owner: str,
) -> None:
    _non_empty_string(operation_id, f"{owner}.campaignOperationId")
    _validate_campaign_result_identity(
        result_identity,
        stage_number,
        f"{owner}.campaignResultIdentity",
    )


def _expected_cash_conservation(entry: dict[str, Any]) -> dict[str, int]:
    opening_plus_income = _safe_sum(
        f"ledger[{entry['stageNumber']}].cashConservation.openingPlusIncome",
        entry["openingCash"],
        entry["income"],
    )
    closing_plus_outflows = _safe_sum(
        f"ledger[{entry['stageNumber']}].cashConservation.closingPlusOutflows",
        entry["closingCash"],
        entry["upkeep"],
        entry["reactivation"],
        entry["roomService"],
        entry["manualRepayment"],
    )
    return {
        "openingPlusIncome": opening_plus_income,
        "closingPlusOutflows": closing_plus_outflows,
        "delta": opening_plus_income - closing_plus_outflows,
    }


def _expected_debt_conservation(
    config: dict[str, Any],
    entry: dict[str, Any],
) -> dict[str, int]:
    repaid_plus_remaining = _safe_sum(
        f"ledger[{entry['stageNumber']}].debtConservation.repaidPlusRemaining",
        entry["cumulativeRepayment"],
        entry["closingDebt"],
    )
    return {
        "originalPrincipal": config["principal"],
        "repaidPlusRemaining": repaid_plus_remaining,
        "delta": config["principal"] - repaid_plus_remaining,
    }


def _validate_ledger_entry(
    config: dict[str, Any],
    entry: Any,
    stage_number: int,
    prior: dict[str, Any],
    seen_operation_ids: set[str],
) -> dict[str, Any]:
    owner = f"ledger[{stage_number - 1}]"
    _require(
        prior["terminalStatus"] is None,
        "INVALID_LEDGER",
        f"{owner} cannot follow a missed chapter hurdle",
    )
    _exact_keys(entry, LEDGER_ENTRY_KEYS, owner)
    _require(
        entry["type"] == "CAMPAIGN_FINANCE_LEDGER_ENTRY",
        "INVALID_LEDGER",
        f"{owner}.type is unknown",
    )
    _require(
        _strict_equal(entry["stageNumber"], stage_number),
        "INVALID_LEDGER",
        f"{owner}.stageNumber must be sequential",
    )
    _validate_campaign_operation_identity(
        entry["campaignOperationId"],
        entry["campaignResultIdentity"],
        stage_number,
        owner,
    )
    operation_id = entry["campaignOperationId"]
    _require(
        operation_id not in seen_operation_ids,
        "DUPLICATE_OPERATION_ID",
        f"{owner}.campaignOperationId must be unique within the ledger",
    )
    seen_operation_ids.add(operation_id)
    _require(
        entry["settlementSequence"] == SETTLEMENT_SEQUENCE,
        "INVALID_LEDGER",
        f"{owner}.settlementSequence is unsupported",
    )
    for field in (
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
    ):
        _amount(entry[field], f"{owner}.{field}")
    _require(
        _strict_equal(entry["openingCash"], prior["cash"]),
        "INVALID_LEDGER",
        f"{owner}.openingCash does not follow the ledger",
    )
    _require(
        _strict_equal(entry["openingDebt"], prior["remainingDebt"]),
        "INVALID_LEDGER",
        f"{owner}.openingDebt does not follow the ledger",
    )

    available = _safe_sum(
        f"{owner}.availableCash",
        entry["openingCash"],
        entry["income"],
    )
    operating_outflow = _safe_sum(
        f"{owner}.operatingOutflow",
        entry["upkeep"],
        entry["reactivation"],
        entry["roomService"],
    )
    _require(
        operating_outflow <= available,
        "INVALID_LEDGER",
        f"{owner} would produce negative operating cash",
    )
    _require(
        _strict_equal(entry["cashAfterOperations"], available - operating_outflow),
        "INVALID_LEDGER",
        f"{owner}.cashAfterOperations is inconsistent",
    )
    _require(
        entry["manualRepayment"] <= entry["cashAfterOperations"],
        "INVALID_LEDGER",
        f"{owner}.manualRepayment exceeds cash",
    )
    _require(
        entry["manualRepayment"] <= entry["openingDebt"],
        "INVALID_LEDGER",
        f"{owner}.manualRepayment exceeds remaining debt",
    )
    if stage_number > DEBT_DEADLINE_STAGE:
        _require(
            entry["openingDebt"] == 0 and entry["manualRepayment"] == 0,
            "INVALID_LEDGER",
            f"{owner} cannot carry or repay debt after day 56",
        )
    _require(
        _strict_equal(
            entry["closingCash"],
            entry["cashAfterOperations"] - entry["manualRepayment"],
        ),
        "INVALID_LEDGER",
        f"{owner}.closingCash is inconsistent",
    )
    _require(
        _strict_equal(
            entry["closingDebt"],
            entry["openingDebt"] - entry["manualRepayment"],
        ),
        "INVALID_LEDGER",
        f"{owner}.closingDebt is inconsistent",
    )
    expected_cumulative = _safe_sum(
        f"{owner}.cumulativeRepayment",
        prior["cumulativeRepayment"],
        entry["manualRepayment"],
    )
    _require(
        _strict_equal(entry["cumulativeRepayment"], expected_cumulative),
        "INVALID_LEDGER",
        f"{owner}.cumulativeRepayment is inconsistent",
    )

    cash_conservation = _expected_cash_conservation(entry)
    _require(
        cash_conservation["delta"] == 0,
        "CASH_DRIFT",
        f"{owner} violates cash conservation",
    )
    _require(
        _same_ordered_flat_record(entry["cashConservation"], cash_conservation),
        "INVALID_LEDGER",
        f"{owner}.cashConservation is inconsistent",
    )
    debt_conservation = _expected_debt_conservation(config, entry)
    _require(
        debt_conservation["delta"] == 0,
        "DEBT_DRIFT",
        f"{owner} violates debt conservation",
    )
    _require(
        _same_ordered_flat_record(entry["debtConservation"], debt_conservation),
        "INVALID_LEDGER",
        f"{owner}.debtConservation is inconsistent",
    )
    checkpoint = _checkpoint(
        config,
        stage_number,
        entry["cumulativeRepayment"],
        entry["closingDebt"],
    )
    if checkpoint is None:
        checkpoint_matches = entry["checkpoint"] is None
    else:
        checkpoint_matches = _same_ordered_flat_record(entry["checkpoint"], checkpoint)
    _require(
        checkpoint_matches,
        "INVALID_LEDGER",
        f"{owner}.checkpoint is inconsistent",
    )
    return {
        "cash": entry["closingCash"],
        "remainingDebt": entry["closingDebt"],
        "cumulativeRepayment": entry["cumulativeRepayment"],
        "terminalStatus": _terminal_status(checkpoint),
    }


def _validate_pending_day_result(
    config: dict[str, Any],
    pending: Any,
    stage_number: int,
    prior: dict[str, Any],
    seen_operation_ids: set[str],
) -> None:
    owner = "pendingDayResult"
    _exact_keys(pending, PENDING_RESULT_KEYS, owner)
    _require(
        pending["type"] == "CAMPAIGN_DAY_RESULT_COMMIT",
        "INVALID_PENDING_RESULT",
        f"{owner}.type is unknown",
    )
    _require(
        _strict_equal(pending["stageNumber"], stage_number),
        "INVALID_PENDING_RESULT",
        f"{owner}.stageNumber is inconsistent",
    )
    _validate_campaign_operation_identity(
        pending["campaignOperationId"],
        pending["campaignResultIdentity"],
        stage_number,
        owner,
    )
    _require(
        pending["campaignOperationId"] not in seen_operation_ids,
        "DUPLICATE_OPERATION_ID",
        f"{owner}.campaignOperationId already exists in the settled ledger",
    )
    for field in (
        "openingCash",
        "income",
        "upkeep",
        "reactivation",
        "roomService",
        "cashAfterOperations",
        "openingDebt",
        "cumulativeRepaymentBefore",
    ):
        _amount(pending[field], f"{owner}.{field}")
    _require(
        _strict_equal(pending["openingCash"], prior["cash"]),
        "INVALID_PENDING_RESULT",
        f"{owner}.openingCash does not follow the ledger",
    )
    _require(
        _strict_equal(pending["openingDebt"], prior["remainingDebt"]),
        "INVALID_PENDING_RESULT",
        f"{owner}.openingDebt does not follow the ledger",
    )
    _require(
        _strict_equal(
            pending["cumulativeRepaymentBefore"],
            prior["cumulativeRepayment"],
        ),
        "INVALID_PENDING_RESULT",
        f"{owner}.cumulativeRepaymentBefore does not follow the ledger",
    )
    available = _safe_sum(
        f"{owner}.availableCash",
        pending["openingCash"],
        pending["income"],
    )
    operating_outflow = _safe_sum(
        f"{owner}.operatingOutflow",
        pending["upkeep"],
        pending["reactivation"],
        pending["roomService"],
    )
    _require(
        operating_outflow <= available,
        "INVALID_PENDING_RESULT",
        f"{owner} would produce negative operating cash",
    )
    _require(
        _strict_equal(pending["cashAfterOperations"], available - operating_outflow),
        "INVALID_PENDING_RESULT",
        f"{owner}.cashAfterOperations is inconsistent",
    )
    if stage_number > DEBT_DEADLINE_STAGE:
        _require(
            pending["openingDebt"] == 0,
            "INVALID_PENDING_RESULT",
            f"{owner} cannot carry debt after day 56",
        )


def _validate_operating_failure(
    config: dict[str, Any],
    failure: Any,
    stage_number: int,
    prior: dict[str, Any],
    seen_operation_ids: set[str],
) -> None:
    owner = "operatingFailure"
    _exact_keys(failure, OPERATING_FAILURE_KEYS, owner)
    _require(
        failure["type"] == "CAMPAIGN_OPERATING_CASH_SHORTFALL",
        "INVALID_OPERATING_FAILURE",
        f"{owner}.type is unknown",
    )
    _require(
        _strict_equal(failure["stageNumber"], stage_number),
        "INVALID_OPERATING_FAILURE",
        f"{owner}.stageNumber is inconsistent",
    )
    _require(
        stage_number <= config["total_stages"],
        "INVALID_OPERATING_FAILURE",
        f"{owner}.stageNumber exceeds the stage limit",
    )
    _validate_campaign_operation_identity(
        failure["campaignOperationId"],
        failure["campaignResultIdentity"],
        stage_number,
        owner,
    )
    _require(
        failure["campaignOperationId"] == failure["campaignOperationId"].strip(),
        "INVALID_OPERATING_FAILURE",
        f"{owner}.campaignOperationId must be canonical",
    )
    _require(
        failure["campaignOperationId"] not in seen_operation_ids,
        "DUPLICATE_OPERATION_ID",
        f"{owner}.campaignOperationId already exists in the settled ledger",
    )
    for field in (
        "openingCash",
        "income",
        "availableCash",
        "upkeep",
        "reactivation",
        "roomService",
        "operatingOutflow",
        "shortfallAmount",
    ):
        _amount(failure[field], f"{owner}.{field}")
    _require(
        _strict_equal(failure["openingCash"], prior["cash"]),
        "INVALID_OPERATING_FAILURE",
        f"{owner}.openingCash does not follow the ledger",
    )
    available = _safe_sum(
        f"{owner}.availableCash",
        failure["openingCash"],
        failure["income"],
    )
    _require(
        _strict_equal(failure["availableCash"], available),
        "INVALID_OPERATING_FAILURE",
        f"{owner}.availableCash is inconsistent",
    )
    operating_outflow = _safe_sum(
        f"{owner}.operatingOutflow",
        failure["upkeep"],
        failure["reactivation"],
        failure["roomService"],
    )
    _require(
        _strict_equal(failure["operatingOutflow"], operating_outflow),
        "INVALID_OPERATING_FAILURE",
        f"{owner}.operatingOutflow is inconsistent",
    )
    _require(
        operating_outflow > available,
        "INVALID_OPERATING_FAILURE",
        f"{owner} requires operating outflow above available cash",
    )
    _require(
        _strict_equal(failure["shortfallAmount"], operating_outflow - available),
        "INVALID_OPERATING_FAILURE",
        f"{owner}.shortfallAmount is inconsistent",
    )


def _expected_envelope(
    config: dict[str, Any],
    completed_stage_count: int,
    debt_cleared_at_deadline: bool | None,
    pending_day_result: Any,
    terminal_status: str | None,
    operating_failure: Any,
) -> dict[str, Any]:
    if operating_failure is not None:
        _require(
            terminal_status is None,
            "INVALID_STATE",
            "an operating cash shortfall cannot follow a terminal checkpoint",
        )
        _require(
            pending_day_result is None,
            "INVALID_STATE",
            "an operating cash shortfall cannot retain a pending result",
        )
        return {
            "phase": "CLOSED",
            "status": "OPERATING_CASH_SHORTFALL",
            "nextStageNumber": None,
        }
    if terminal_status is not None:
        _require(
            pending_day_result is None,
            "INVALID_STATE",
            "a missed chapter hurdle cannot retain a pending result",
        )
        return {
            "phase": "CLOSED",
            "status": terminal_status,
            "nextStageNumber": None,
        }
    _require(
        not (
            completed_stage_count >= DEBT_DEADLINE_STAGE
            and debt_cleared_at_deadline is False
        ),
        "INVALID_STATE",
        "a missed day 56 deadline must close the finance state",
    )
    if completed_stage_count == config["total_stages"]:
        _require(
            pending_day_result is None,
            "INVALID_STATE",
            "completed finance cannot retain a pending result",
        )
        return {"phase": "CLOSED", "status": "COMPLETE", "nextStageNumber": None}
    return {
        "phase": "AWAITING_RESULT" if pending_day_result is None else "RESULT_COMMITTED",
        "status": "ACTIVE",
        "nextStageNumber": completed_stage_count + 1,
    }


def validate_campaign_finance_state(
    config: dict[str, Any],
    state: dict[str, Any],
) -> None:
    """Mirror src/campaign-finance.js validateCampaignFinanceState."""

    validate_config(config)
    _exact_keys(state, STATE_KEYS, "finance state")
    _require(
        state["type"] == "CAMPAIGN_FINANCE_STATE",
        "INVALID_STATE",
        "state.type is unknown",
    )
    _require(
        _strict_equal(state["schemaVersion"], SCHEMA_VERSION),
        "INVALID_STATE",
        "state.schemaVersion is unsupported",
    )
    _require(
        _strict_equal(state["configId"], config["id"]),
        "INVALID_STATE",
        "state.configId does not match config",
    )
    _require(
        _strict_equal(state["configVersion"], config["version"]),
        "INVALID_STATE",
        "state.configVersion does not match config",
    )
    _require(
        state["contractStatus"] == CONTRACT_STATUS,
        "INVALID_STATE",
        "state.contractStatus is unsupported",
    )
    _require(
        state["balanceVerdict"] == BALANCE_VERDICT,
        "INVALID_STATE",
        "state.balanceVerdict must remain NOT_EVALUATED",
    )
    _require(
        _strict_equal(state["totalStages"], config["total_stages"]),
        "INVALID_STATE",
        "state.totalStages does not match config",
    )
    _require(
        _strict_equal(state["debtDeadlineStageNumber"], DEBT_DEADLINE_STAGE),
        "INVALID_STATE",
        "state.debtDeadlineStageNumber is inconsistent",
    )
    completed_stage_count = _amount(
        state["completedStageCount"],
        "state.completedStageCount",
    )
    _require(
        completed_stage_count <= config["total_stages"],
        "INVALID_STATE",
        "state.completedStageCount exceeds the configured stage limit",
    )
    _amount(state["cash"], "state.cash")
    _require(
        _strict_equal(state["originalPrincipal"], config["principal"]),
        "INVALID_STATE",
        "state.originalPrincipal does not match config",
    )
    _amount(state["remainingDebt"], "state.remainingDebt")
    _amount(state["cumulativeRepayment"], "state.cumulativeRepayment")
    _require(
        state["remainingDebt"] <= config["principal"],
        "INVALID_STATE",
        "state.remainingDebt exceeds the original principal",
    )
    _require(
        _safe_sum(
            "state debt conservation",
            state["remainingDebt"],
            state["cumulativeRepayment"],
        )
        == config["principal"],
        "INVALID_STATE",
        "state violates debt conservation",
    )
    _require(
        isinstance(state["ledger"], list),
        "INVALID_STATE",
        "state.ledger must be a dense array",
    )
    _require(
        len(state["ledger"]) == completed_stage_count,
        "INVALID_STATE",
        "state.ledger must contain one entry per completed stage",
    )

    reconstructed = {
        "cash": config["starting_cash"],
        "remainingDebt": config["principal"],
        "cumulativeRepayment": 0,
        "terminalStatus": None,
    }
    seen_operation_ids: set[str] = set()
    for index, entry in enumerate(state["ledger"]):
        reconstructed = _validate_ledger_entry(
            config,
            entry,
            index + 1,
            reconstructed,
            seen_operation_ids,
        )

    _require(
        state["operatingFailure"] is None
        or _is_plain_object(state["operatingFailure"]),
        "INVALID_STATE",
        "state.operatingFailure must be null or an object",
    )
    if state["operatingFailure"] is not None:
        _require(
            reconstructed["terminalStatus"] is None,
            "INVALID_STATE",
            "an operating cash shortfall cannot follow a terminal checkpoint",
        )
        _require(
            state["pendingDayResult"] is None,
            "INVALID_STATE",
            "an operating cash shortfall cannot retain a pending result",
        )
        _require(
            completed_stage_count < config["total_stages"],
            "INVALID_STATE",
            "completed finance cannot retain an operating failure",
        )
        _validate_operating_failure(
            config,
            state["operatingFailure"],
            completed_stage_count + 1,
            reconstructed,
            seen_operation_ids,
        )
        _require(
            _strict_equal(state["cash"], reconstructed["cash"]),
            "INVALID_STATE",
            "operating failure cannot apply attempted income or outflow",
        )
        _require(
            _strict_equal(state["remainingDebt"], reconstructed["remainingDebt"]),
            "INVALID_STATE",
            "operating failure cannot change remaining debt",
        )
        _require(
            _strict_equal(
                state["cumulativeRepayment"],
                reconstructed["cumulativeRepayment"],
            ),
            "INVALID_STATE",
            "operating failure cannot change cumulative repayment",
        )
    elif state["pendingDayResult"] is not None:
        _require(
            reconstructed["terminalStatus"] is None,
            "INVALID_STATE",
            "a missed chapter hurdle cannot have a later pending result",
        )
        _require(
            completed_stage_count < config["total_stages"],
            "INVALID_STATE",
            "completed finance cannot have a pending result",
        )
        _validate_pending_day_result(
            config,
            state["pendingDayResult"],
            completed_stage_count + 1,
            reconstructed,
            seen_operation_ids,
        )
        _require(
            _strict_equal(
                state["cash"],
                state["pendingDayResult"]["cashAfterOperations"],
            ),
            "INVALID_STATE",
            "state.cash must include the committed operating result",
        )
        _require(
            _strict_equal(state["remainingDebt"], reconstructed["remainingDebt"]),
            "INVALID_STATE",
            "pending result cannot change debt before settlement",
        )
        _require(
            _strict_equal(
                state["cumulativeRepayment"],
                reconstructed["cumulativeRepayment"],
            ),
            "INVALID_STATE",
            "pending result cannot change cumulative repayment before settlement",
        )
    else:
        _require(
            _strict_equal(state["cash"], reconstructed["cash"]),
            "INVALID_STATE",
            "state.cash does not match the ledger",
        )
        _require(
            _strict_equal(state["remainingDebt"], reconstructed["remainingDebt"]),
            "INVALID_STATE",
            "state.remainingDebt does not match the ledger",
        )
        _require(
            _strict_equal(
                state["cumulativeRepayment"],
                reconstructed["cumulativeRepayment"],
            ),
            "INVALID_STATE",
            "state.cumulativeRepayment does not match the ledger",
        )

    expected_deadline_flag = None
    if completed_stage_count >= DEBT_DEADLINE_STAGE:
        deadline_entry = state["ledger"][DEBT_DEADLINE_STAGE - 1]
        expected_deadline_flag = deadline_entry["closingDebt"] == 0
    _require(
        state["debtClearedAtDeadline"] is expected_deadline_flag,
        "INVALID_STATE",
        "state.debtClearedAtDeadline must preserve the day 56 observation",
    )
    if completed_stage_count > DEBT_DEADLINE_STAGE:
        _require(
            state["debtClearedAtDeadline"] is True and state["remainingDebt"] == 0,
            "INVALID_STATE",
            "post-deadline stages require debt cleared at day 56",
        )

    envelope = _expected_envelope(
        config,
        completed_stage_count,
        state["debtClearedAtDeadline"],
        state["pendingDayResult"],
        reconstructed["terminalStatus"],
        state["operatingFailure"],
    )
    _require(
        _strict_equal(state["phase"], envelope["phase"]),
        "INVALID_STATE",
        "state.phase is inconsistent",
    )
    _require(
        _strict_equal(state["status"], envelope["status"]),
        "INVALID_STATE",
        "state.status is inconsistent",
    )
    _require(
        _strict_equal(state["nextStageNumber"], envelope["nextStageNumber"]),
        "INVALID_STATE",
        "state.nextStageNumber is inconsistent",
    )


def commit_day_result(
    config: dict[str, Any],
    state: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    validate_campaign_finance_state(config, state)
    _require(
        state["status"] == "ACTIVE" and state["phase"] == "AWAITING_RESULT",
        "RESULT_NOT_AWAITED",
        "a result can be committed only while awaiting a result",
    )
    _exact_keys(result, RESULT_KEYS, "result")
    stage_number = result["stageNumber"]
    _require(
        _strict_equal(stage_number, state["nextStageNumber"]),
        "STAGE_MISMATCH",
        "stage does not match",
    )
    identity = result["campaignResultIdentity"]
    _validate_campaign_operation_identity(
        result["campaignOperationId"],
        identity,
        stage_number,
        "result",
    )
    operation_id = result["campaignOperationId"].strip()
    _require(
        not any(row["campaignOperationId"] == operation_id for row in state["ledger"]),
        "DUPLICATE_OPERATION_ID",
        "operation id already exists",
    )
    income = _amount(result["income"], "result income")
    upkeep = _amount(result["upkeep"], "result upkeep")
    reactivation = _amount(result["reactivation"], "result reactivation")
    room_service = _amount(result["roomService"], "result roomService")
    if stage_number > DEBT_DEADLINE_STAGE:
        _require(
            state["debtClearedAtDeadline"] is True and state["remainingDebt"] == 0,
            "UNRESOLVED_POST_DEADLINE_DEBT",
            "day 57 and later cannot carry debt",
        )
    available = _safe_sum("available cash", state["cash"], income)
    outflow = _safe_sum("operating outflow", upkeep, reactivation, room_service)
    if outflow > available:
        failed = _clone(state)
        failed.update(
            {
                "nextStageNumber": None,
                "phase": "CLOSED",
                "status": "OPERATING_CASH_SHORTFALL",
                "pendingDayResult": None,
                "operatingFailure": {
                    "type": "CAMPAIGN_OPERATING_CASH_SHORTFALL",
                    "stageNumber": stage_number,
                    "campaignOperationId": operation_id,
                    "campaignResultIdentity": _clone(identity),
                    "openingCash": state["cash"],
                    "income": income,
                    "availableCash": available,
                    "upkeep": upkeep,
                    "reactivation": reactivation,
                    "roomService": room_service,
                    "operatingOutflow": outflow,
                    "shortfallAmount": outflow - available,
                },
            }
        )
        validate_campaign_finance_state(config, failed)
        return failed
    pending = {
        "type": "CAMPAIGN_DAY_RESULT_COMMIT",
        "stageNumber": stage_number,
        "campaignOperationId": operation_id,
        "campaignResultIdentity": _clone(identity),
        "openingCash": state["cash"],
        "income": income,
        "upkeep": upkeep,
        "reactivation": reactivation,
        "roomService": room_service,
        "cashAfterOperations": available - outflow,
        "openingDebt": state["remainingDebt"],
        "cumulativeRepaymentBefore": state["cumulativeRepayment"],
    }
    committed = _clone(state)
    committed.update(
        {
            "phase": "RESULT_COMMITTED",
            "cash": pending["cashAfterOperations"],
            "pendingDayResult": pending,
            "operatingFailure": None,
        }
    )
    validate_campaign_finance_state(config, committed)
    return committed


def settle_day(
    config: dict[str, Any],
    state: dict[str, Any],
    settlement: dict[str, Any],
) -> dict[str, Any]:
    validate_campaign_finance_state(config, state)
    _require(
        state["status"] == "ACTIVE" and state["phase"] == "RESULT_COMMITTED",
        "RESULT_NOT_COMMITTED",
        "settlement requires a committed result",
    )
    _exact_keys(settlement, SETTLEMENT_KEYS, "settlement")
    repayment = _amount(settlement["manualRepayment"], "settlement.manualRepayment")
    pending = state["pendingDayResult"]
    if pending["stageNumber"] > DEBT_DEADLINE_STAGE and repayment != 0:
        _reject(
            "INVALID_MANUAL_REPAYMENT_POST_DEADLINE",
            "day 57 and later cannot accept debt repayment",
        )
    _require(
        repayment <= state["cash"],
        "MANUAL_REPAYMENT_EXCEEDS_CASH",
        "manual repayment exceeds cash; partial payment is never implicit",
    )
    _require(
        repayment <= state["remainingDebt"],
        "MANUAL_REPAYMENT_EXCEEDS_DEBT",
        "manual repayment exceeds debt; partial payment is never implicit",
    )
    closing_cash = state["cash"] - repayment
    closing_debt = state["remainingDebt"] - repayment
    cumulative = _safe_sum("cumulative repayment", state["cumulativeRepayment"], repayment)
    checkpoint = _checkpoint(config, pending["stageNumber"], cumulative, closing_debt)
    opening_plus_income = _safe_sum("opening plus income", pending["openingCash"], pending["income"])
    closing_plus_outflows = _safe_sum(
        "closing plus outflows",
        closing_cash,
        pending["upkeep"],
        pending["reactivation"],
        pending["roomService"],
        repayment,
    )
    repaid_plus_remaining = _safe_sum("repaid plus remaining", cumulative, closing_debt)
    entry = {
        "type": "CAMPAIGN_FINANCE_LEDGER_ENTRY",
        "stageNumber": pending["stageNumber"],
        "campaignOperationId": pending["campaignOperationId"],
        "campaignResultIdentity": _clone(pending["campaignResultIdentity"]),
        "settlementSequence": SETTLEMENT_SEQUENCE,
        "openingCash": pending["openingCash"],
        "income": pending["income"],
        "upkeep": pending["upkeep"],
        "reactivation": pending["reactivation"],
        "roomService": pending["roomService"],
        "cashAfterOperations": pending["cashAfterOperations"],
        "manualRepayment": repayment,
        "closingCash": closing_cash,
        "openingDebt": pending["openingDebt"],
        "closingDebt": closing_debt,
        "cumulativeRepayment": cumulative,
        "cashConservation": {
            "openingPlusIncome": opening_plus_income,
            "closingPlusOutflows": closing_plus_outflows,
            "delta": opening_plus_income - closing_plus_outflows,
        },
        "debtConservation": {
            "originalPrincipal": config["principal"],
            "repaidPlusRemaining": repaid_plus_remaining,
            "delta": config["principal"] - repaid_plus_remaining,
        },
        "checkpoint": checkpoint,
    }
    _require(entry["cashConservation"]["delta"] == 0, "CASH_DRIFT", "cash drifted")
    _require(entry["debtConservation"]["delta"] == 0, "DEBT_DRIFT", "debt drifted")
    completed = pending["stageNumber"]
    debt_cleared = (
        closing_debt == 0 if completed == DEBT_DEADLINE_STAGE else state["debtClearedAtDeadline"]
    )
    terminal = _terminal_status(checkpoint)
    if terminal is not None:
        phase, status, next_stage = "CLOSED", terminal, None
    elif completed == config["total_stages"]:
        phase, status, next_stage = "CLOSED", "COMPLETE", None
    else:
        phase, status, next_stage = "AWAITING_RESULT", "ACTIVE", completed + 1
    settled = _clone(state)
    settled.update(
        {
            "completedStageCount": completed,
            "nextStageNumber": next_stage,
            "phase": phase,
            "status": status,
            "cash": closing_cash,
            "remainingDebt": closing_debt,
            "cumulativeRepayment": cumulative,
            "debtClearedAtDeadline": debt_cleared,
            "pendingDayResult": None,
            "operatingFailure": None,
            "ledger": [*_clone(state["ledger"]), entry],
        }
    )
    validate_campaign_finance_state(config, settled)
    return settled


def debt_gate_evidence(config: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    validate_campaign_finance_state(config, state)
    _require(
        state["completedStageCount"] >= DEBT_DEADLINE_STAGE,
        "DEBT_GATE_NOT_REACHED",
        "day 56 must be settled before debt gate evidence exists",
    )
    entry = state["ledger"][DEBT_DEADLINE_STAGE - 1]
    return {
        "type": "CAMPAIGN_DEBT_GATE_EVIDENCE",
        "gateId": config["debt_gate_id"],
        "passed": entry["closingDebt"] == 0,
        "boundaryStageNumber": DEBT_DEADLINE_STAGE,
        "financeConfigId": config["id"],
        "financeConfigVersion": config["version"],
        "originalPrincipal": config["principal"],
        "cumulativeRepaymentAtBoundary": entry["cumulativeRepayment"],
        "remainingDebtAtBoundary": entry["closingDebt"],
        "checkpointOutcome": entry["checkpoint"]["outcome"],
        "ledgerEntryCountAtBoundary": DEBT_DEADLINE_STAGE,
        "debtGraceAfterBoundary": False,
    }


def unlock_true_extension(
    base: dict[str, Any],
    extended: dict[str, Any],
    state: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    validate_config_pair(base, extended)
    validate_campaign_finance_state(base, state)
    _require(
        state["completedStageCount"] == 56,
        "TRUE_EXTENSION_NOT_ELIGIBLE",
        "true extension cannot unlock before day 56 settlement",
    )
    _require(
        state["phase"] == "CLOSED" and state["status"] == "COMPLETE",
        "TRUE_EXTENSION_NOT_ELIGIBLE",
        "true extension requires the completed base finance state",
    )
    _require(
        state["debtClearedAtDeadline"] is True and state["remainingDebt"] == 0,
        "TRUE_EXTENSION_NOT_ELIGIBLE",
        "true extension requires debt cleared at day 56",
    )
    expected_evidence = debt_gate_evidence(base, state)
    _require(
        _same_flat_record(evidence, expected_evidence),
        "TRUE_EXTENSION_EVIDENCE_MISMATCH",
        "debt gate evidence does not match",
    )
    _require(
        evidence["passed"] is True,
        "TRUE_EXTENSION_EVIDENCE_MISMATCH",
        "debt gate evidence must explicitly pass",
    )
    extended_state = _clone(state)
    extended_state.update(
        {
            "configId": extended["id"],
            "configVersion": extended["version"],
            "totalStages": extended["total_stages"],
            "nextStageNumber": 57,
            "phase": "AWAITING_RESULT",
            "status": "ACTIVE",
            "pendingDayResult": None,
        }
    )
    validate_campaign_finance_state(extended, extended_state)
    return extended_state


def _trace_state(
    event: str,
    state: dict[str, Any],
    stage_number: int | None,
    adapter_state: dict[str, Any],
) -> dict[str, Any]:
    checkpoint = None
    if state["ledger"] and state["ledger"][-1]["stageNumber"] == stage_number:
        checkpoint = _clone(state["ledger"][-1]["checkpoint"])
    return {
        "event": event,
        "stageNumber": stage_number,
        "phase": state["phase"],
        "status": state["status"],
        "completedStageCount": state["completedStageCount"],
        "nextStageNumber": state["nextStageNumber"],
        "totalStages": state["totalStages"],
        "cash": state["cash"],
        "remainingDebt": state["remainingDebt"],
        "cumulativeRepayment": state["cumulativeRepayment"],
        "debtClearedAtDeadline": state["debtClearedAtDeadline"],
        "checkpoint": checkpoint,
        "operatingFailure": _clone(state["operatingFailure"]),
        "adapterState": _clone(adapter_state),
    }


def _finance_ledger_metrics(state: dict[str, Any]) -> dict[str, Any]:
    """Settled finance-ledger totals; deliberately excludes failed preparation."""

    ledger = state["ledger"]
    return {
        "scope": FINANCE_LEDGER_METRICS_SCOPE,
        "includesOnlySettledLedgerEntries": True,
        "excludesFailedPreparationExpenses": True,
        "completedStageCount": state["completedStageCount"],
        # ``cash`` remains for analyzer/report compatibility. ``financeCash``
        # names its actual authority explicitly: this is campaign-finance cash,
        # not necessarily the controller's post-purchase live cash on failure.
        "cash": state["cash"],
        "financeCash": state["cash"],
        "remainingDebt": state["remainingDebt"],
        "cumulativeRepayment": state["cumulativeRepayment"],
        "income": sum(row["income"] for row in ledger),
        "upkeep": sum(row["upkeep"] for row in ledger),
        "reactivation": sum(row["reactivation"] for row in ledger),
        "roomService": sum(row["roomService"] for row in ledger),
        "manualRepayment": sum(row["manualRepayment"] for row in ledger),
    }


def _adapter_metrics(
    state: dict[str, Any],
    adapter_state: dict[str, Any],
) -> dict[str, Any]:
    _exact_keys(
        adapter_state,
        {"liveCash", "ownedUpgradeCount", "pendingExpenses"},
        "adapter state",
    )
    live_cash = _amount(adapter_state["liveCash"], "adapterState.liveCash")
    _amount(
        adapter_state["ownedUpgradeCount"],
        "adapterState.ownedUpgradeCount",
    )
    pending = adapter_state["pendingExpenses"]
    _exact_keys(pending, {"reactivation", "roomService"}, "adapter pending expenses")
    pending_reactivation = _amount(
        pending["reactivation"],
        "adapterState.pendingExpenses.reactivation",
    )
    pending_room_service = _amount(
        pending["roomService"],
        "adapterState.pendingExpenses.roomService",
    )
    pending_total = _safe_sum(
        "adapter pending expense total",
        pending_reactivation,
        pending_room_service,
    )
    _require(
        _safe_sum("adapter live cash invariant", live_cash, pending_total)
        == state["cash"],
        "ADAPTER_CASH_INVARIANT_DRIFT",
        "adapter live cash plus paid pending expenses must equal finance cash",
    )
    failed_preparation = state["status"] == "OPERATING_CASH_SHORTFALL"
    return {
        "scope": ADAPTER_METRICS_SCOPE,
        "liveCash": live_cash,
        "financeCash": state["cash"],
        "pendingExpenses": _clone(pending),
        "pendingExpenseTotal": pending_total,
        "pendingExpensesAlreadyPaid": pending_total > 0,
        "failedPreparationExpenses": {
            "reactivation": pending_reactivation if failed_preparation else 0,
            "roomService": pending_room_service if failed_preparation else 0,
            "total": pending_total if failed_preparation else 0,
        },
    }


def _legacy_metrics(finance_ledger_metrics: dict[str, Any]) -> dict[str, Any]:
    """Preserve the pre-scope report API for analyzer and fixture consumers."""

    return {
        key: finance_ledger_metrics[key]
        for key in (
            "completedStageCount",
            "cash",
            "remainingDebt",
            "cumulativeRepayment",
            "income",
            "upkeep",
            "reactivation",
            "roomService",
            "manualRepayment",
        )
    }


def _metrics(state: dict[str, Any]) -> dict[str, Any]:
    """Backward-compatible settled-ledger metric projection."""

    return _legacy_metrics(_finance_ledger_metrics(state))


def simulate_case(case: dict[str, Any]) -> dict[str, Any]:
    base = case["baseConfig"]
    extended = case["extendedConfig"]
    policy = case["runtimePolicy"]
    validate_config_pair(base, extended)
    validate_runtime_policy(policy)
    state = create_finance_state(base)
    active_config = base
    adapter_state = {
        "liveCash": state["cash"],
        "ownedUpgradeCount": 0,
        "pendingExpenses": {"reactivation": 0, "roomService": 0},
    }
    trace = [_trace_state("INITIAL", state, None, adapter_state)]
    gate_evidence = None
    operations_applied = 0

    for index, operation in enumerate(case["operations"]):
        _require(
            state["status"] == "ACTIVE",
            "UNUSED_OPERATIONS_AFTER_TERMINAL",
            f"operation {index + 1} follows terminal status {state['status']}",
        )
        _exact_keys(operation, OPERATION_KEYS, f"adapter operation {index + 1}")
        _require(
            operation["upkeep"] == calculate_upkeep(policy, operation["ownedUpgradeCount"]),
            "UPKEEP_ADAPTER_DRIFT",
            "operation upkeep no longer matches runtime policy",
        )
        _require(
            operation["ownedUpgradeCount"] >= adapter_state["ownedUpgradeCount"],
            "OWNED_UPGRADE_COUNT_DECREASED",
            "owned upgrade count cannot decrease",
        )
        pending_total = _safe_sum(
            "pending preparation expenses",
            operation["reactivation"],
            operation["roomService"],
        )
        _require(
            pending_total <= state["cash"],
            "PREPARATION_COST_EXCEEDS_LIVE_CASH",
            "preparation expense exceeds live cash and could not have been purchased",
        )
        adapter_state = {
            "liveCash": state["cash"] - pending_total,
            "ownedUpgradeCount": operation["ownedUpgradeCount"],
            "pendingExpenses": {
                "reactivation": operation["reactivation"],
                "roomService": operation["roomService"],
            },
        }
        trace.append(
            _trace_state("OPERATION_PREPARED", state, operation["stageNumber"], adapter_state)
        )
        finance_result = {
            key: _clone(operation[key])
            for key in (
                "stageNumber",
                "campaignOperationId",
                "campaignResultIdentity",
                "income",
                "upkeep",
                "reactivation",
                "roomService",
            )
        }
        state = commit_day_result(active_config, state, finance_result)
        operations_applied += 1
        if state["status"] != "OPERATING_CASH_SHORTFALL":
            adapter_state = {
                "liveCash": state["cash"],
                "ownedUpgradeCount": operation["ownedUpgradeCount"],
                "pendingExpenses": {"reactivation": 0, "roomService": 0},
            }
        trace.append(
            _trace_state("RESULT_COMMITTED", state, operation["stageNumber"], adapter_state)
        )
        if state["status"] == "OPERATING_CASH_SHORTFALL":
            continue
        state = settle_day(
            active_config,
            state,
            {"manualRepayment": operation["manualRepayment"]},
        )
        adapter_state["liveCash"] = state["cash"]
        trace.append(
            _trace_state("DAY_SETTLED", state, operation["stageNumber"], adapter_state)
        )
        if operation["stageNumber"] == DEBT_DEADLINE_STAGE:
            gate_evidence = debt_gate_evidence(base, state)
            if case["unlockTrueExtension"] and gate_evidence["passed"]:
                state = unlock_true_extension(base, extended, state, gate_evidence)
                active_config = extended
                trace.append(
                    _trace_state("TRUE_EXTENSION_UNLOCKED", state, 56, adapter_state)
                )

    finance_ledger_metrics = _finance_ledger_metrics(state)
    adapter_metrics = _adapter_metrics(state, adapter_state)
    return {
        "id": case["id"],
        "accepted": True,
        "contractStatus": CONTRACT_STATUS,
        "balanceVerdict": BALANCE_VERDICT,
        "operationsApplied": operations_applied,
        "debtGateEvidence": gate_evidence,
        "finalState": state,
        "adapterState": adapter_state,
        # ``metrics`` preserves the exact legacy analyzer/report shape. New
        # consumers should select the explicitly scoped records below.
        "metrics": _metrics(state),
        "financeLedgerMetrics": finance_ledger_metrics,
        "adapterMetrics": adapter_metrics,
        "trace": trace,
    }


def simulate_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for case in fixture["cases"]:
        try:
            results.append(simulate_case(case))
        except FinanceSimulationError as exc:
            results.append(
                {
                    "id": case["id"],
                    "accepted": False,
                    "contractStatus": CONTRACT_STATUS,
                    "balanceVerdict": BALANCE_VERDICT,
                    "error": {"code": exc.code},
                }
            )
    return {
        "schemaVersion": FIXTURE_SCHEMA_VERSION,
        "contractStatus": CONTRACT_STATUS,
        "balanceVerdict": BALANCE_VERDICT,
        "cases": results,
    }
