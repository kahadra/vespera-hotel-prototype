from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

try:
    from campaign_finance_runtime import (
        FinanceSimulationError,
        commit_day_result,
        create_finance_state,
        load_fixture,
        settle_day,
        simulate_fixture,
        validate_campaign_finance_state,
    )
except ModuleNotFoundError:  # Allows import as tools.test_campaign_finance_conformance.
    from tools.campaign_finance_runtime import (
        FinanceSimulationError,
        commit_day_result,
        create_finance_state,
        load_fixture,
        settle_day,
        simulate_fixture,
        validate_campaign_finance_state,
    )


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = (
    ROOT / "tools" / "fixtures" / "campaign_finance_conformance_v1.json"
)
DEFAULT_ORACLE = ROOT / "tools" / "campaign_finance_js_oracle.mjs"
REQUIRED_CASE_IDS = {
    "BASE_56_SUCCESS",
    "DAY_7_HURDLE_MISS_BY_1",
    "DAY_14_HURDLE_MISS_BY_1",
    "DAY_28_HURDLE_MISS_BY_1",
    "DAY_42_HURDLE_MISS_BY_1",
    "DAY_56_DEBT_MISS_BY_1",
    "DAY_2_OPERATING_SHORTFALL_AFTER_PREPARATION",
    "TRUE_70_SUCCESS",
    "DAY_57_NONZERO_REPAYMENT_REJECTED",
    "DAY_1_REPAYMENT_EXCEEDS_CASH_REJECTED",
    "DAY_1_REPAYMENT_EXCEEDS_DEBT_REJECTED",
    "DAY_2_PREPARATION_EXPENSE_SUCCESS",
    "SAFE_INTEGER_MAX_BOUNDARY_ACCEPTED",
    "DAY_1_AVAILABLE_CASH_OVERFLOW_REJECTED",
    "DAY_1_EXACT_CASH_OUTFLOW",
    "DAY_1_ZERO_INCOME_OPERATING_SHORTFALL",
    "DAY_1_CASH_AND_DEBT_EXCESS_PRIORITY",
    "DAY_1_PREPARATION_PRECEDES_OPERATING_SHORTFALL",
}
MAX_SAFE_INTEGER = (1 << 53) - 1


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def find_node(explicit: str | None) -> Path:
    if explicit:
        candidate = Path(explicit).resolve()
        require(candidate.is_file(), f"Node executable does not exist: {candidate}")
        return candidate

    path_node = shutil.which("node")
    if path_node:
        return Path(path_node).resolve()

    portable_root = ROOT / ".tmp" / "node-bootstrap" / "runtime-complete"
    portable = sorted(portable_root.glob("node-v*-win-x64/node.exe"), reverse=True)
    require(
        bool(portable),
        "Node.js was not found. Pass --node with an explicit executable path.",
    )
    return portable[0].resolve()


def first_difference(left: Any, right: Any, path: str = "$") -> str | None:
    if type(left) is not type(right):
        return (
            f"{path}: type differs: Python={type(left).__name__} "
            f"JS={type(right).__name__}"
        )
    if isinstance(left, dict):
        left_keys = set(left)
        right_keys = set(right)
        if left_keys != right_keys:
            return (
                f"{path}: keys differ: "
                f"Python-only={sorted(left_keys - right_keys)}, "
                f"JS-only={sorted(right_keys - left_keys)}"
            )
        for key in sorted(left_keys):
            difference = first_difference(left[key], right[key], f"{path}.{key}")
            if difference:
                return difference
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return f"{path}: length differs: Python={len(left)} JS={len(right)}"
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            difference = first_difference(left_item, right_item, f"{path}[{index}]")
            if difference:
                return difference
        return None
    if left != right:
        return f"{path}: value differs: Python={left!r} JS={right!r}"
    return None


def run_js_oracle(
    node_path: Path,
    oracle_path: Path,
    canonical_fixture: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    completed = subprocess.run(
        [str(node_path), str(oracle_path), "-"],
        input=json.dumps(canonical_fixture, ensure_ascii=False, separators=(",", ":")),
        text=True,
        encoding="utf-8",
        capture_output=True,
        cwd=ROOT,
        timeout=timeout_seconds,
        check=False,
    )
    require(
        completed.returncode == 0,
        "JS oracle failed "
        f"(exit {completed.returncode}): {completed.stderr.strip() or completed.stdout.strip()}",
    )
    require(bool(completed.stdout.strip()), "JS oracle produced no JSON output")
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"JS oracle output is not one JSON document: {completed.stdout[:500]!r}"
        ) from exc
    require(isinstance(report, dict), "JS oracle report root must be an object")
    return report


def js_oracle_rejection_code(
    node_path: Path,
    oracle_path: Path,
    raw_fixture: dict[str, Any],
    timeout_seconds: float,
) -> str:
    completed = subprocess.run(
        [str(node_path), str(oracle_path), "-"],
        input=json.dumps(raw_fixture, ensure_ascii=False, separators=(",", ":")),
        text=True,
        encoding="utf-8",
        capture_output=True,
        cwd=ROOT,
        timeout=timeout_seconds,
        check=False,
    )
    require(completed.returncode != 0, "invalid raw fixture was accepted by JS oracle")
    payload_text = completed.stderr.strip()
    require(bool(payload_text), "JS oracle rejection produced no error envelope")
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"JS oracle rejection is not one JSON document: {payload_text[:500]!r}"
        ) from exc
    require(payload.get("status") == "ORACLE_ERROR", "bad JS rejection envelope")
    code = payload.get("error", {}).get("code")
    require(isinstance(code, str) and bool(code), "JS rejection needs a stable code")
    return code


def python_loader_rejection_code(raw_fixture: dict[str, Any]) -> str:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix="campaign-finance-fixture-probe-",
        suffix=".json",
        dir=ROOT / "tools",
        delete=False,
    ) as handle:
        json.dump(raw_fixture, handle, ensure_ascii=False)
        path = Path(handle.name)
    error_code = None
    try:
        try:
            load_fixture(path)
        except FinanceSimulationError as exc:
            error_code = exc.code
    finally:
        path.unlink(missing_ok=True)
    if error_code is not None:
        return error_code
    raise AssertionError("invalid raw fixture was accepted by Python loader")


def validate_strict_rejection_probes(
    fixture_path: Path,
    node_path: Path,
    oracle_path: Path,
    timeout_seconds: float,
) -> int:
    raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    probes: list[tuple[str, dict[str, Any], str]] = []

    boolean_fixture_version = copy.deepcopy(raw)
    boolean_fixture_version["schemaVersion"] = True
    probes.append(("BOOLEAN_FIXTURE_VERSION", boolean_fixture_version, "INVALID_FIXTURE"))

    boolean_policy_version = copy.deepcopy(raw)
    boolean_policy_version["defaults"]["runtimePolicy"]["version"] = True
    probes.append(
        ("BOOLEAN_RUNTIME_POLICY_VERSION", boolean_policy_version, "INVALID_POSITIVE_INTEGER")
    )

    for probe_id, invalid_fixture, expected_code in probes:
        python_code = python_loader_rejection_code(invalid_fixture)
        js_code = js_oracle_rejection_code(
            node_path,
            oracle_path,
            invalid_fixture,
            timeout_seconds,
        )
        require(
            python_code == expected_code,
            f"{probe_id}: Python rejection {python_code!r}, expected {expected_code!r}",
        )
        require(
            js_code == expected_code,
            f"{probe_id}: JS rejection {js_code!r}, expected {expected_code!r}",
        )
    return len(probes)


def require_finance_rejection(
    probe_id: str,
    action: Any,
    expected_code: str,
) -> None:
    try:
        action()
    except FinanceSimulationError as exc:
        require(
            exc.code == expected_code,
            f"{probe_id}: rejection {exc.code!r}, expected {expected_code!r}",
        )
        return
    except Exception as exc:
        raise AssertionError(
            f"{probe_id}: validator leaked raw {type(exc).__name__}: {exc}"
        ) from exc
    raise AssertionError(f"{probe_id}: invalid input was accepted")


def validate_python_state_rejection_probes(
    canonical_fixture: dict[str, Any],
) -> int:
    base = canonical_fixture["cases"][0]["baseConfig"]
    pristine = create_finance_state(base)
    probes: list[tuple[str, dict[str, Any], str]] = []

    schema_drift = copy.deepcopy(pristine)
    schema_drift["schemaVersion"] += 1
    probes.append(("STATE_SCHEMA_VERSION_DRIFT", schema_drift, "INVALID_STATE"))

    ledger_count_drift = copy.deepcopy(pristine)
    ledger_count_drift["completedStageCount"] = 1
    probes.append(("STATE_LEDGER_COUNT_DRIFT", ledger_count_drift, "INVALID_STATE"))

    cash_reconstruction_drift = copy.deepcopy(pristine)
    cash_reconstruction_drift["cash"] += 1
    probes.append(("STATE_CASH_RECONSTRUCTION_DRIFT", cash_reconstruction_drift, "INVALID_STATE"))

    envelope_drift = copy.deepcopy(pristine)
    envelope_drift["phase"] = "CLOSED"
    probes.append(("STATE_PHASE_ENVELOPE_DRIFT", envelope_drift, "INVALID_STATE"))

    for probe_id, tampered_state, expected_code in probes:
        require_finance_rejection(
            probe_id,
            lambda state=tampered_state: validate_campaign_finance_state(base, state),
            expected_code,
        )

    public_entry_state = copy.deepcopy(pristine)
    public_entry_state["schemaVersion"] += 1
    public_entry_before = copy.deepcopy(public_entry_state)
    require_finance_rejection(
        "PUBLIC_COMMIT_REJECTS_STATE_BEFORE_OPERATION",
        lambda: commit_day_result(base, public_entry_state, {}),
        "INVALID_STATE",
    )
    require(
        public_entry_state == public_entry_before,
        "PUBLIC_COMMIT_REJECTS_STATE_BEFORE_OPERATION: rejected state was mutated",
    )
    return len(probes) + 1


def validate_python_public_api_shape_probes(
    canonical_fixture: dict[str, Any],
) -> int:
    case = canonical_fixture["cases"][0]
    base = case["baseConfig"]
    enriched_operation = copy.deepcopy(case["operations"][0])
    result = {
        key: copy.deepcopy(enriched_operation[key])
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
    require(len(result) == 7, "public result probe must use the JS seven-key shape")

    pristine = create_finance_state(base)
    pristine_before = copy.deepcopy(pristine)
    result_before = copy.deepcopy(result)
    committed = commit_day_result(base, pristine, result)
    require(
        committed["phase"] == "RESULT_COMMITTED"
        and committed["pendingDayResult"] is not None,
        "PUBLIC_COMMIT_ACCEPTS_JS_RESULT_SHAPE: seven-key result was not committed",
    )
    require(
        pristine == pristine_before and result == result_before,
        "PUBLIC_COMMIT_ACCEPTS_JS_RESULT_SHAPE: public commit mutated its inputs",
    )

    settlement = {"manualRepayment": enriched_operation["manualRepayment"]}
    settlement_before = copy.deepcopy(settlement)
    committed_before = copy.deepcopy(committed)
    settled = settle_day(base, committed, settlement)
    require(
        settled["completedStageCount"] == 1
        and settled["ledger"][0]["manualRepayment"] == settlement["manualRepayment"],
        "PUBLIC_SETTLE_ACCEPTS_JS_SHAPE: settlement object was not applied",
    )
    require(
        committed == committed_before and settlement == settlement_before,
        "PUBLIC_SETTLE_ACCEPTS_JS_SHAPE: public settlement mutated its inputs",
    )

    require_finance_rejection(
        "PUBLIC_COMMIT_REJECTS_ENRICHED_OPERATION",
        lambda: commit_day_result(base, pristine, enriched_operation),
        "INVALID_SHAPE",
    )
    require_finance_rejection(
        "PUBLIC_SETTLE_REJECTS_BARE_INTEGER",
        lambda: settle_day(base, committed, settlement["manualRepayment"]),
        "INVALID_SHAPE",
    )
    return 4


def expected_projection(result: dict[str, Any]) -> dict[str, Any]:
    if not result["accepted"]:
        return {
            "outcome": "REJECTED",
            "errorCode": result["error"]["code"],
        }

    state = result["finalState"]
    adapter = result["adapterState"]
    last_entry = state["ledger"][-1] if state["ledger"] else None
    last_checkpoint = last_entry["checkpoint"] if last_entry else None
    status = state["status"]
    outcome = "ACTIVE_PREFIX" if status == "ACTIVE" else status
    return {
        "outcome": outcome,
        "errorCode": None,
        "status": status,
        "phase": state["phase"],
        "completedStageCount": state["completedStageCount"],
        "nextStageNumber": state["nextStageNumber"],
        "cash": state["cash"],
        "remainingDebt": state["remainingDebt"],
        "cumulativeRepayment": state["cumulativeRepayment"],
        "debtClearedAtDeadline": state["debtClearedAtDeadline"],
        "ledgerLength": len(state["ledger"]),
        "liveCash": adapter["liveCash"],
        "ownedUpgradeCount": adapter["ownedUpgradeCount"],
        "pendingExpenses": adapter["pendingExpenses"],
        "checkpointOutcome": (
            last_checkpoint["outcome"] if last_checkpoint is not None else None
        ),
        "operatingShortfallAmount": (
            state["operatingFailure"]["shortfallAmount"]
            if state["operatingFailure"] is not None
            else None
        ),
        "financeConfigId": state["configId"],
        "metrics": result["metrics"],
        "financeLedgerMetrics": result["financeLedgerMetrics"],
        "adapterMetrics": result["adapterMetrics"],
    }


def validate_expected(
    canonical_fixture: dict[str, Any],
    report: dict[str, Any],
) -> None:
    result_by_id = {result["id"]: result for result in report["cases"]}
    for case in canonical_fixture["cases"]:
        case_id = case["id"]
        expected = case["expected"]
        actual = expected_projection(result_by_id[case_id])
        unknown = set(expected) - set(actual)
        require(not unknown, f"{case_id}: unsupported expected keys: {sorted(unknown)}")
        for key, expected_value in expected.items():
            require(
                type(actual[key]) is type(expected_value) and actual[key] == expected_value,
                f"{case_id}: expected {key}={expected_value!r}, got {actual[key]!r}",
            )


def validate_invariants(
    canonical_fixture: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, int]:
    require(report.get("schemaVersion") == 1, "report schemaVersion must be 1")
    require(
        report.get("contractStatus") == "PROVISIONAL",
        "conformance report must remain PROVISIONAL",
    )
    require(
        report.get("balanceVerdict") == "NOT_EVALUATED",
        "conformance must not claim a balance verdict",
    )

    canonical_ids = [case["id"] for case in canonical_fixture["cases"]]
    report_ids = [case["id"] for case in report.get("cases", [])]
    require(report_ids == canonical_ids, "report case order or membership drifted")
    require(
        REQUIRED_CASE_IDS.issubset(set(canonical_ids)),
        f"required cases missing: {sorted(REQUIRED_CASE_IDS - set(canonical_ids))}",
    )
    require(len(canonical_ids) >= 10, "at least ten conformance paths are required")

    accepted_count = 0
    rejected_count = 0
    ledger_entries = 0
    trace_events = 0
    for result in report["cases"]:
        require(result["contractStatus"] == "PROVISIONAL", f"{result['id']}: status drift")
        require(
            result["balanceVerdict"] == "NOT_EVALUATED",
            f"{result['id']}: balance boundary drift",
        )
        if not result["accepted"]:
            rejected_count += 1
            require(
                set(result) == {
                    "id",
                    "accepted",
                    "contractStatus",
                    "balanceVerdict",
                    "error",
                },
                f"{result['id']}: rejected result leaked partial authority",
            )
            require(
                isinstance(result["error"].get("code"), str)
                and bool(result["error"]["code"]),
                f"{result['id']}: rejection requires a stable error code",
            )
            continue

        accepted_count += 1
        state = result["finalState"]
        adapter = result["adapterState"]
        ledger = state["ledger"]
        trace = result["trace"]
        ledger_entries += len(ledger)
        trace_events += len(trace)
        require(
            len(ledger) == state["completedStageCount"],
            f"{result['id']}: ledger length must equal completed stages",
        )
        require(trace and trace[0]["event"] == "INITIAL", f"{result['id']}: bad trace")
        require(
            all(row["cashConservation"]["delta"] == 0 for row in ledger),
            f"{result['id']}: cash conservation drift",
        )
        require(
            all(row["debtConservation"]["delta"] == 0 for row in ledger),
            f"{result['id']}: debt conservation drift",
        )
        pending = adapter["pendingExpenses"]
        require(
            adapter["liveCash"] + pending["reactivation"] + pending["roomService"]
            == state["cash"],
            f"{result['id']}: live cash/pending expense invariant drift",
        )
        metrics = result["metrics"]
        expected_metrics = {
            "completedStageCount": state["completedStageCount"],
            "cash": state["cash"],
            "remainingDebt": state["remainingDebt"],
            "cumulativeRepayment": state["cumulativeRepayment"],
            "income": sum(row["income"] for row in ledger),
            "upkeep": sum(row["upkeep"] for row in ledger),
            "reactivation": sum(row["reactivation"] for row in ledger),
            "roomService": sum(row["roomService"] for row in ledger),
            "manualRepayment": sum(row["manualRepayment"] for row in ledger),
        }
        require(
            metrics == expected_metrics,
            f"{result['id']}: metrics must describe settled ledger entries only",
        )
        expected_finance_metrics = {
            "scope": "FINANCE_LEDGER_ONLY",
            "includesOnlySettledLedgerEntries": True,
            "excludesFailedPreparationExpenses": True,
            **expected_metrics,
            "financeCash": state["cash"],
        }
        require(
            result["financeLedgerMetrics"] == expected_finance_metrics,
            f"{result['id']}: finance ledger metric scope drift",
        )
        adapter_metrics = result["adapterMetrics"]
        pending_total = pending["reactivation"] + pending["roomService"]
        expected_failed_preparation = (
            {
                "reactivation": pending["reactivation"],
                "roomService": pending["roomService"],
                "total": pending_total,
            }
            if state["status"] == "OPERATING_CASH_SHORTFALL"
            else {"reactivation": 0, "roomService": 0, "total": 0}
        )
        require(
            adapter_metrics
            == {
                "scope": "LIVE_CASH_AND_PENDING_PREPARATION",
                "liveCash": adapter["liveCash"],
                "financeCash": state["cash"],
                "pendingExpenses": pending,
                "pendingExpenseTotal": pending_total,
                "pendingExpensesAlreadyPaid": pending_total > 0,
                "failedPreparationExpenses": expected_failed_preparation,
            },
            f"{result['id']}: adapter metric scope or failed-preparation meaning drift",
        )
        base_starting_cash = next(
            case["baseConfig"]["starting_cash"]
            for case in canonical_fixture["cases"]
            if case["id"] == result["id"]
        )
        require(
            base_starting_cash
            + metrics["income"]
            - metrics["upkeep"]
            - metrics["reactivation"]
            - metrics["roomService"]
            - metrics["manualRepayment"]
            == state["cash"],
            f"{result['id']}: aggregate cash conservation drift",
        )

        if state["status"] == "OPERATING_CASH_SHORTFALL":
            failure = state["operatingFailure"]
            require(failure is not None, f"{result['id']}: shortfall evidence missing")
            require(
                result["operationsApplied"] == state["completedStageCount"] + 1,
                f"{result['id']}: failed operation accounting drift",
            )
            require(
                trace[-1]["event"] == "RESULT_COMMITTED"
                and trace[-1]["status"] == "OPERATING_CASH_SHORTFALL",
                f"{result['id']}: shortfall trace must close at result commit",
            )
            require(
                pending == {
                    "reactivation": failure["reactivation"],
                    "roomService": failure["roomService"],
                },
                f"{result['id']}: failed preparation expenses lost from adapter state",
            )
            require(
                adapter["liveCash"]
                + failure["reactivation"]
                + failure["roomService"]
                == failure["openingCash"],
                f"{result['id']}: failed preparation live-cash meaning drift",
            )

    results_by_id = {result["id"]: result for result in report["cases"]}
    safe_boundary = results_by_id["SAFE_INTEGER_MAX_BOUNDARY_ACCEPTED"]
    require(
        safe_boundary["accepted"]
        and safe_boundary["finalState"]["cash"] == MAX_SAFE_INTEGER,
        "safe-integer maximum boundary must remain accepted and exact",
    )
    exact_cash = results_by_id["DAY_1_EXACT_CASH_OUTFLOW"]["finalState"]["ledger"][0]
    require(
        exact_cash["openingCash"] + exact_cash["income"]
        == exact_cash["upkeep"]
        + exact_cash["reactivation"]
        + exact_cash["roomService"]
        and exact_cash["closingCash"] == 0,
        "exact-cash operating outflow boundary drift",
    )
    require(
        results_by_id["DAY_1_AVAILABLE_CASH_OVERFLOW_REJECTED"]["error"]["code"]
        == "SAFE_INTEGER_OVERFLOW",
        "safe-integer overflow rejection drift",
    )
    require(
        results_by_id["DAY_1_CASH_AND_DEBT_EXCESS_PRIORITY"]["error"]["code"]
        == "MANUAL_REPAYMENT_EXCEEDS_CASH",
        "cash-before-debt compound rejection precedence drift",
    )
    require(
        results_by_id["DAY_1_PREPARATION_PRECEDES_OPERATING_SHORTFALL"]["error"]["code"]
        == "PREPARATION_COST_EXCEEDS_LIVE_CASH",
        "preparation-before-operating-shortfall rejection precedence drift",
    )

    return {
        "accepted": accepted_count,
        "rejected": rejected_count,
        "ledger_entries": ledger_entries,
        "trace_events": trace_events,
    }


def run(
    fixture_path: Path,
    node_path: Path,
    oracle_path: Path,
    timeout_seconds: float,
) -> dict[str, Any]:
    canonical_fixture = load_fixture(fixture_path)
    state_validation_probe_count = validate_python_state_rejection_probes(
        canonical_fixture
    )
    public_api_probe_count = validate_python_public_api_shape_probes(
        canonical_fixture
    )
    python_report = simulate_fixture(canonical_fixture)
    js_report = run_js_oracle(
        node_path,
        oracle_path,
        canonical_fixture,
        timeout_seconds,
    )
    difference = first_difference(python_report, js_report)
    require(difference is None, f"Python/JS conformance mismatch: {difference}")
    validate_expected(canonical_fixture, python_report)
    counts = validate_invariants(canonical_fixture, python_report)
    strict_probe_count = validate_strict_rejection_probes(
        fixture_path,
        node_path,
        oracle_path,
        timeout_seconds,
    )
    return {
        "status": "PASS",
        "mode": "RESOLVED_DAILY_FINANCE_TRANSITION_JS_PYTHON_PARITY",
        "scope": "RESOLVED_DAILY_FINANCE_TRANSITIONS",
        "fixture_schema_version": canonical_fixture["schemaVersion"],
        "case_count": len(canonical_fixture["cases"]),
        "accepted_case_count": counts["accepted"],
        "rejected_case_count": counts["rejected"],
        "compared_ledger_entries": counts["ledger_entries"],
        "compared_trace_events": counts["trace_events"],
        "strict_loader_probe_count": strict_probe_count,
        "state_validation_probe_count": state_validation_probe_count,
        "public_api_probe_count": public_api_probe_count,
        "contract_status": python_report["contractStatus"],
        "balance_verdict": python_report["balanceVerdict"],
        "node_executable": str(node_path),
        "js_oracle": str(oracle_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compare resolved daily campaign-finance transitions in an independent "
            "Python mirror with the real JavaScript production exports."
        )
    )
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--node", help="explicit Node.js executable")
    parser.add_argument("--oracle", type=Path, default=DEFAULT_ORACLE)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    args = parser.parse_args()
    require(args.timeout_seconds > 0, "--timeout-seconds must be positive")
    report = run(
        args.fixture.resolve(),
        find_node(args.node),
        args.oracle.resolve(),
        args.timeout_seconds,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
