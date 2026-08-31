from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


if __package__:
    from . import generate_campaign_economy_candidates as boundaries
    from . import test_campaign_economy_candidates as boundary_validator
else:
    import generate_campaign_economy_candidates as boundaries
    import test_campaign_economy_candidates as boundary_validator


frontier = boundaries.frontier

REPORT_SCHEMA_VERSION = 1
REPORT_STATUS = "PROVISIONAL_LINKED_ECONOMY_BUNDLE_OBSERVATIONS"
CONTRACT_STATUS = "PROVISIONAL"
BALANCE_VERDICT = "NOT_EVALUATED"
SELECTION_AUTHORITY = "USER"

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BOUNDARY_REPORT = (
    REPOSITORY_ROOT
    / "artifacts"
    / "campaign-economy-candidates"
    / "provisional-boundary-observations.json"
)
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT
    / "artifacts"
    / "campaign-economy-bundles"
    / "provisional-linked-bundles.json"
)

PRIMARY_CURVE_ID = boundaries.TARGET_CURVES[0]["id"]
PRIMARY_REACTIVATION_SHAPE_ID = boundaries.REACTIVATION_SHAPES[0]["id"]

PRESSURE_SCALE_DENOMINATOR = 10_000
PRESSURE_PATH_MINIMUM_BASIS_POINTS = 5_000
PRESSURE_PATH_MAXIMUM_BASIS_POINTS = 30_000
PRESSURE_PATH_STEP_BASIS_POINTS = 125
PRESSURE_PATH_ROUNDING = "NEAREST_INTEGER_HALF_UP_V1"

SOURCE_BAND_ORDER = (
    "GREEDY_LOW",
    "MECHANICAL_MIDPOINT",
    "CANONICAL",
)

SCREEN_DEFINITIONS = (
    {
        "bundle_id": "ECONOMY_SLICE_A",
        "ordinal": 1,
        "required_source_bands": SOURCE_BAND_ORDER,
        "interpretation": (
            "Maximum linked-path pressure that structurally completes every declared trace "
            "under every target-curve and reactivation-shape sensitivity structure."
        ),
    },
    {
        "bundle_id": "ECONOMY_SLICE_B",
        "ordinal": 2,
        "required_source_bands": (
            "MECHANICAL_MIDPOINT",
            "CANONICAL",
        ),
        "interpretation": (
            "Maximum linked-path pressure that structurally completes all midpoint and "
            "canonical traces under every sensitivity structure."
        ),
    },
    {
        "bundle_id": "ECONOMY_SLICE_C",
        "ordinal": 3,
        "required_source_bands": ("CANONICAL",),
        "interpretation": (
            "Maximum linked-path pressure that structurally completes all canonical traces "
            "under every sensitivity structure."
        ),
    },
)

BANNED_NORMALIZED_KEYS = {
    "winner",
    "bestcandidate",
    "recommendedcandidate",
    "recommendedcandidateid",
    "completionrate",
    "balancepass",
    "balancefail",
}


class BundleInputError(ValueError):
    """Raised when a linked-bundle input or declared model is ambiguous."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repository_relative_posix(path: Path) -> str:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(REPOSITORY_ROOT.resolve())
    except ValueError as exc:
        raise BundleInputError(
            f"linked-bundle evidence must remain inside the repository: {resolved}"
        ) from exc
    return relative.as_posix()


def _parameter_json(parameters: boundaries.ParameterSet) -> dict[str, int]:
    return {
        "starting_cash": parameters.starting_cash,
        "principal": parameters.principal,
        "base_daily_upkeep": parameters.base_daily_upkeep,
        "upkeep_per_active_unit": parameters.upkeep_per_active_unit,
        "total_reactivation_cost": parameters.total_reactivation_cost,
    }


def _nearest_half_up(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise BundleInputError("rounding denominator must be positive")
    if numerator < 0:
        raise BundleInputError("rounding numerator must not be negative")
    return (numerator + denominator // 2) // denominator


def pressure_parameters(
    anchor: boundaries.ParameterSet, pressure_basis_points: int
) -> boundaries.ParameterSet:
    bp = boundaries._nonnegative_int(
        pressure_basis_points, "pressure_basis_points"
    )
    if bp <= 0:
        raise BundleInputError("pressure basis points must be positive")
    return boundaries.ParameterSet(
        starting_cash=_nearest_half_up(
            anchor.starting_cash * PRESSURE_SCALE_DENOMINATOR, bp
        ),
        principal=_nearest_half_up(
            anchor.principal * bp, PRESSURE_SCALE_DENOMINATOR
        ),
        base_daily_upkeep=_nearest_half_up(
            anchor.base_daily_upkeep * bp, PRESSURE_SCALE_DENOMINATOR
        ),
        upkeep_per_active_unit=_nearest_half_up(
            anchor.upkeep_per_active_unit * bp, PRESSURE_SCALE_DENOMINATOR
        ),
        total_reactivation_cost=_nearest_half_up(
            anchor.total_reactivation_cost * bp, PRESSURE_SCALE_DENOMINATOR
        ),
    )


def build_pressure_path(
    anchor: boundaries.ParameterSet,
) -> tuple[dict[str, Any], ...]:
    entries: list[dict[str, Any]] = []
    prior: boundaries.ParameterSet | None = None
    for basis_points in range(
        PRESSURE_PATH_MINIMUM_BASIS_POINTS,
        PRESSURE_PATH_MAXIMUM_BASIS_POINTS + 1,
        PRESSURE_PATH_STEP_BASIS_POINTS,
    ):
        parameters = pressure_parameters(anchor, basis_points)
        if parameters == prior:
            continue
        entries.append(
            {
                "path_index": len(entries),
                "pressure_basis_points": basis_points,
                "parameters": _parameter_json(parameters),
            }
        )
        prior = parameters
    if not entries:
        raise AssertionError("linked pressure path is empty")
    _assert_pressure_path(entries)
    return tuple(entries)


def _parameters_from_entry(entry: dict[str, Any]) -> boundaries.ParameterSet:
    raw = entry["parameters"]
    return boundaries.ParameterSet(
        starting_cash=raw["starting_cash"],
        principal=raw["principal"],
        base_daily_upkeep=raw["base_daily_upkeep"],
        upkeep_per_active_unit=raw["upkeep_per_active_unit"],
        total_reactivation_cost=raw["total_reactivation_cost"],
    )


def _assert_pressure_path(entries: Iterable[dict[str, Any]]) -> None:
    rows = list(entries)
    for expected_index, row in enumerate(rows):
        if row["path_index"] != expected_index:
            raise AssertionError("linked pressure path indices must be consecutive")
        if expected_index == 0:
            continue
        prior = _parameters_from_entry(rows[expected_index - 1])
        current = _parameters_from_entry(row)
        if current == prior:
            raise AssertionError("linked pressure path contains a duplicate vector")
        if current.starting_cash > prior.starting_cash:
            raise AssertionError("starting cash increased on the pressure path")
        for field in (
            "principal",
            "base_daily_upkeep",
            "upkeep_per_active_unit",
            "total_reactivation_cost",
        ):
            if getattr(current, field) < getattr(prior, field):
                raise AssertionError(f"{field} decreased on the pressure path")


def _normalized_owned_unit_contract(
    spec: boundaries.AnchorSpec,
) -> dict[str, Any]:
    counts = boundaries.active_unit_counts(spec)
    if len(counts) != frontier.BASE_YEAR_DAYS:
        raise AssertionError("owned-upgrade schedule did not cover the base year")
    prior = 0
    activation_days = set(spec.activation_days)
    for day, count in enumerate(counts, start=1):
        expected = prior + (1 if day in activation_days else 0)
        if count != expected:
            raise AssertionError(
                "every activation must add exactly one normalized owned-upgrade unit"
            )
        prior = count
    return {
        "counting_model": "EACH_OWNED_UPGRADE_COUNTS_AS_NORMALIZED_UNIT_ONE",
        "normalized_unit_weight_per_owned_upgrade": 1,
        "baseline_hotel_covered_by_base_daily_upkeep": True,
        "initial_additional_owned_upgrade_count": 0,
        "activation_days": list(spec.activation_days),
        "owned_upgrade_count_by_day": list(counts),
        "owned_upgrade_day_weight": sum(counts),
        "upkeep_per_active_unit_is_bundle_coefficient": True,
    }


def _assert_resolved_pressure_path(
    spec: boundaries.AnchorSpec, entries: Iterable[dict[str, Any]]
) -> None:
    rows = list(entries)
    for left_entry, right_entry in zip(rows, rows[1:]):
        left = _parameters_from_entry(left_entry)
        right = _parameters_from_entry(right_entry)
        left_upkeep = boundaries.upkeep_schedule(spec, left)
        right_upkeep = boundaries.upkeep_schedule(spec, right)
        if any(a > b for a, b in zip(left_upkeep, right_upkeep)):
            raise AssertionError("resolved daily upkeep decreased on the pressure path")
        for curve in boundaries.TARGET_CURVES:
            left_targets = boundaries.realize_target_curve(curve, left.principal)
            right_targets = boundaries.realize_target_curve(curve, right.principal)
            if any(
                left_targets[str(day)] > right_targets[str(day)]
                for day in frontier.CHAPTER_DAYS
            ):
                raise AssertionError("resolved chapter target decreased on the pressure path")
        for shape in boundaries.REACTIVATION_SHAPES:
            left_events = boundaries.reactivation_events(spec, left, shape)
            right_events = boundaries.reactivation_events(spec, right, shape)
            if any(
                left_event.amount > right_event.amount
                for left_event, right_event in zip(left_events, right_events)
            ):
                raise AssertionError(
                    "resolved reactivation event decreased on the pressure path"
                )


def _compact_outcome(outcome: dict[str, Any]) -> dict[str, Any]:
    cash = outcome["cash_metrics"]
    return {
        "trace_id": outcome["trace_id"],
        "target_curve_id": outcome["target_curve_id"],
        "reactivation_shape_id": outcome["reactivation_shape_id"],
        "completed_structural_witness": outcome["completed_structural_witness"],
        "path_executable": outcome["path_executable"],
        "terminal_class": outcome["terminal_class"],
        "terminal_runtime_status": outcome["terminal_runtime_status"],
        "terminal_day": outcome["terminal_day"],
        "terminal_shortfall_amount": outcome["terminal_shortfall_amount"],
        "completed_days": outcome["completed_days"],
        "attempted_operation_count": outcome["attempted_operation_count"],
        "day_56_observed": outcome["day_56_observed"],
        "day_56_remaining_debt": outcome["day_56_remaining_debt"],
        "day_56_cash": outcome["day_56_cash"],
        "terminal_remaining_debt": outcome["terminal_remaining_debt"],
        "minimum_live_cash": cash["minimum_live_cash"],
        "minimum_finance_cash": cash["minimum_finance_cash"],
        "terminal_live_cash": cash["terminal_live_cash"],
        "terminal_finance_cash": cash["terminal_finance_cash"],
        "terminal_pending_preparation": cash["terminal_pending_preparation"],
        "conservation_delta": outcome["conservation_delta"],
        "balance_verdict": BALANCE_VERDICT,
    }


def _evaluate_full_vector(
    engine: boundaries.EvaluationEngine,
    traces: tuple[boundaries.IncomeTrace, ...],
    parameters: boundaries.ParameterSet,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for curve in boundaries.TARGET_CURVES:
        for shape in boundaries.REACTIVATION_SHAPES:
            for trace in traces:
                results.append(
                    _compact_outcome(
                        engine.evaluate(
                            trace.trace_id,
                            curve["id"],
                            shape["id"],
                            parameters,
                        )
                    )
                )
    return results


def _required_trace_ids(
    traces: tuple[boundaries.IncomeTrace, ...], required_bands: Iterable[str]
) -> set[str]:
    required = set(required_bands)
    unknown = required - set(SOURCE_BAND_ORDER)
    if unknown:
        raise BundleInputError(f"unknown source bands: {sorted(unknown)!r}")
    return {trace.trace_id for trace in traces if trace.source_band in required}


def _screen_vector(
    engine: boundaries.EvaluationEngine,
    traces: tuple[boundaries.IncomeTrace, ...],
    parameters: boundaries.ParameterSet,
    required_bands: Iterable[str],
    *,
    stop_at_first_failure: bool,
) -> tuple[bool, list[dict[str, Any]]]:
    required_ids = _required_trace_ids(traces, required_bands)
    failures: list[dict[str, Any]] = []
    for curve in boundaries.TARGET_CURVES:
        for shape in boundaries.REACTIVATION_SHAPES:
            for trace in traces:
                if trace.trace_id not in required_ids:
                    continue
                outcome = engine.evaluate(
                    trace.trace_id, curve["id"], shape["id"], parameters
                )
                if outcome["completed_structural_witness"] is not True:
                    failures.append(_compact_outcome(outcome))
                    if stop_at_first_failure:
                        return False, failures
    return not failures, failures


def _find_maximum_passing_path_index(
    engine: boundaries.EvaluationEngine,
    traces: tuple[boundaries.IncomeTrace, ...],
    path: tuple[dict[str, Any], ...],
    required_bands: Iterable[str],
) -> tuple[int, int]:
    cache: dict[int, bool] = {}

    def passes(index: int) -> bool:
        if index not in cache:
            cache[index] = _screen_vector(
                engine,
                traces,
                _parameters_from_entry(path[index]),
                required_bands,
                stop_at_first_failure=True,
            )[0]
        return cache[index]

    low = 0
    high = len(path) - 1
    if not passes(low):
        raise AssertionError("pressure-path minimum did not pass a bundle screen")
    if passes(high):
        raise AssertionError("pressure-path maximum did not fail a bundle screen")
    while high - low > 1:
        midpoint = (low + high) // 2
        if passes(midpoint):
            low = midpoint
        else:
            high = midpoint
    if not passes(low) or passes(high):
        raise AssertionError("linked-path boundary adjacency verification failed")
    return low, high


def _source_band_for_trace(
    traces: tuple[boundaries.IncomeTrace, ...], trace_id: str
) -> str:
    for trace in traces:
        if trace.trace_id == trace_id:
            return trace.source_band
    raise AssertionError(f"unknown saved trace {trace_id!r}")


def _result_summary(
    traces: tuple[boundaries.IncomeTrace, ...], results: list[dict[str, Any]]
) -> dict[str, Any]:
    structure_rows: list[dict[str, Any]] = []
    for curve in boundaries.TARGET_CURVES:
        for shape in boundaries.REACTIVATION_SHAPES:
            selected = [
                row
                for row in results
                if row["target_curve_id"] == curve["id"]
                and row["reactivation_shape_id"] == shape["id"]
            ]
            band_rows: dict[str, Any] = {}
            for band in SOURCE_BAND_ORDER:
                band_results = [
                    row
                    for row in selected
                    if _source_band_for_trace(traces, row["trace_id"]) == band
                ]
                band_rows[band] = {
                    "observation_count": len(band_results),
                    "structural_completion_observation_count": sum(
                        row["completed_structural_witness"] is True
                        for row in band_results
                    ),
                    "terminal_class_counts": dict(
                        sorted(Counter(row["terminal_class"] for row in band_results).items())
                    ),
                }
            structure_rows.append(
                {
                    "target_curve_id": curve["id"],
                    "reactivation_shape_id": shape["id"],
                    "observation_count": len(selected),
                    "source_band_observations": band_rows,
                }
            )
    return {
        "observation_count": len(results),
        "structural_completion_observation_count": sum(
            row["completed_structural_witness"] is True for row in results
        ),
        "terminal_class_counts": dict(
            sorted(Counter(row["terminal_class"] for row in results).items())
        ),
        "probability_interpretation_allowed": False,
        "structure_observations": structure_rows,
    }


def _resolved_primary_bundle(
    spec: boundaries.AnchorSpec, parameters: boundaries.ParameterSet
) -> dict[str, Any]:
    curve = next(
        curve for curve in boundaries.TARGET_CURVES if curve["id"] == PRIMARY_CURVE_ID
    )
    shape = next(
        shape
        for shape in boundaries.REACTIVATION_SHAPES
        if shape["id"] == PRIMARY_REACTIVATION_SHAPE_ID
    )
    return {
        "target_curve_id": PRIMARY_CURVE_ID,
        "reactivation_shape_id": PRIMARY_REACTIVATION_SHAPE_ID,
        "chapter_cumulative_targets": boundaries.realize_target_curve(
            curve, parameters.principal
        ),
        "per_day_upkeep_schedule": list(boundaries.upkeep_schedule(spec, parameters)),
        "reactivation_events": boundaries._scheduled_cost_json(
            boundaries.reactivation_events(spec, parameters, shape)
        ),
    }


def _assert_bundle_pressure_order(bundles: list[dict[str, Any]]) -> None:
    if [bundle["bundle_id"] for bundle in bundles] != [
        definition["bundle_id"] for definition in SCREEN_DEFINITIONS
    ]:
        raise AssertionError("linked bundles are not in A/B/C order")
    for left, right in zip(bundles, bundles[1:]):
        if left["path_index"] >= right["path_index"]:
            raise AssertionError("A/B/C path indices must strictly increase")
        easy = left["parameters"]
        hard = right["parameters"]
        if easy["starting_cash"] < hard["starting_cash"]:
            raise AssertionError("starting cash pressure order failed")
        for field in (
            "principal",
            "base_daily_upkeep",
            "upkeep_per_active_unit",
            "total_reactivation_cost",
        ):
            if easy[field] > hard[field]:
                raise AssertionError(f"{field} pressure order failed")
        left_primary = left["resolved_primary_structure"]
        right_primary = right["resolved_primary_structure"]
        if any(
            lvalue > rvalue
            for lvalue, rvalue in zip(
                left_primary["per_day_upkeep_schedule"],
                right_primary["per_day_upkeep_schedule"],
            )
        ):
            raise AssertionError("daily upkeep pressure order failed")
        left_targets = left_primary["chapter_cumulative_targets"]
        right_targets = right_primary["chapter_cumulative_targets"]
        if any(
            left_targets[str(day)] > right_targets[str(day)]
            for day in frontier.CHAPTER_DAYS
        ):
            raise AssertionError("chapter target pressure order failed")
        left_events = left_primary["reactivation_events"]
        right_events = right_primary["reactivation_events"]
        if [event["day"] for event in left_events] != [
            event["day"] for event in right_events
        ]:
            raise AssertionError("reactivation event days drifted across bundles")
        if any(
            left_event["amount"] > right_event["amount"]
            for left_event, right_event in zip(left_events, right_events)
        ):
            raise AssertionError("reactivation event pressure order failed")


def assert_provisional_linked_report(report: dict[str, Any]) -> None:
    required = {
        "status": REPORT_STATUS,
        "contract_status": CONTRACT_STATUS,
        "balance_verdict": BALANCE_VERDICT,
        "selection_authority": SELECTION_AUTHORITY,
        "exact_numeric_values_selected": False,
        "complete_difficulty_profile_claimed": False,
        "player_facing_labels_selected": False,
    }
    for key, expected in required.items():
        if report.get(key) != expected:
            raise AssertionError(
                f"linked economy report {key} must be {expected!r}"
            )
    model = report.get("model_decisions", {}).get("owned_upgrade_upkeep")
    if not isinstance(model, dict):
        raise AssertionError("linked report lost the owned-upgrade upkeep decision")
    if model.get("normalized_unit_weight_per_owned_upgrade") != 1:
        raise AssertionError("owned upgrades must count as normalized unit one")
    axes = report.get("difficulty_axis_scope", {})
    if axes.get("economy_pressure") != "OBSERVED_PROVISIONAL_CANDIDATE_SLICE":
        raise AssertionError("linked report lost its economy-pressure scope")
    if axes.get("puzzle_pressure") != "NOT_EVALUATED":
        raise AssertionError("linked report cannot claim puzzle difficulty")
    if axes.get("information_assistance") != "NOT_EVALUATED":
        raise AssertionError("linked report cannot claim information difficulty")

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                normalized = key.replace("_", "").lower()
                if normalized in BANNED_NORMALIZED_KEYS:
                    raise AssertionError(f"linked report contains banned key {path}.{key}")
                if normalized == "balanceverdict" and nested != BALANCE_VERDICT:
                    raise AssertionError(
                        f"linked report contains a non-provisional verdict at {path}.{key}"
                    )
                walk(nested, f"{path}.{key}")
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                walk(nested, f"{path}[{index}]")

    walk(report, "report")


def make_linked_bundle_report(
    boundary_report_path: Path,
    *,
    max_simulations: int = 5_000,
    progress_stream: Any | None = None,
) -> dict[str, Any]:
    boundary_report_path = boundary_report_path.resolve()
    boundary_receipt = boundary_validator.validate_report(boundary_report_path)
    boundary_report = json.loads(boundary_report_path.read_text(encoding="utf-8"))
    reference = frontier.load_audit_income_reference(frontier.DEFAULT_AUDIT_PATH)
    traces = boundaries.build_phase_rotated_traces(reference)
    spec = boundaries.default_anchor_spec()
    anchor = boundaries.anchor_parameters(spec)
    owned_unit_contract = _normalized_owned_unit_contract(spec)
    path = build_pressure_path(anchor)
    _assert_resolved_pressure_path(spec, path)
    engine = boundaries.EvaluationEngine(
        spec, traces, max_simulations=max_simulations
    )

    boundaries_by_bundle: list[tuple[dict[str, Any], int, int]] = []
    for definition in SCREEN_DEFINITIONS:
        passing_index, failing_index = _find_maximum_passing_path_index(
            engine,
            traces,
            path,
            definition["required_source_bands"],
        )
        boundaries_by_bundle.append((definition, passing_index, failing_index))
        if progress_stream is not None:
            print(
                "linked-bundle boundary "
                f"{definition['bundle_id']} pass_index={passing_index} "
                f"fail_index={failing_index} simulations={engine.simulation_count}",
                file=progress_stream,
                flush=True,
            )

    bundles: list[dict[str, Any]] = []
    for definition, passing_index, failing_index in boundaries_by_bundle:
        passing_entry = path[passing_index]
        failing_entry = path[failing_index]
        parameters = _parameters_from_entry(passing_entry)
        next_parameters = _parameters_from_entry(failing_entry)
        results = _evaluate_full_vector(engine, traces, parameters)
        screen_passed, unexpected_failures = _screen_vector(
            engine,
            traces,
            parameters,
            definition["required_source_bands"],
            stop_at_first_failure=False,
        )
        if not screen_passed or unexpected_failures:
            raise AssertionError("saved linked bundle did not pass its declared screen")
        adjacent_passed, adjacent_failures = _screen_vector(
            engine,
            traces,
            next_parameters,
            definition["required_source_bands"],
            stop_at_first_failure=False,
        )
        if adjacent_passed or not adjacent_failures:
            raise AssertionError("linked bundle lost its adjacent failing path witness")
        bundles.append(
            {
                "bundle_id": definition["bundle_id"],
                "ordinal": definition["ordinal"],
                "status": "PROVISIONAL_LINKED_PATH_BOUNDARY_CANDIDATE",
                "player_facing_label": None,
                "balance_verdict": BALANCE_VERDICT,
                "path_index": passing_index,
                "pressure_basis_points": passing_entry["pressure_basis_points"],
                "parameters": _parameter_json(parameters),
                "required_source_bands": list(
                    definition["required_source_bands"]
                ),
                "screen_interpretation": definition["interpretation"],
                "resolved_primary_structure": _resolved_primary_bundle(
                    spec, parameters
                ),
                "result_summary": _result_summary(traces, results),
                "results": results,
                "adjacent_higher_pressure_failure_witness": {
                    "path_index": failing_index,
                    "pressure_basis_points": failing_entry[
                        "pressure_basis_points"
                    ],
                    "parameters": _parameter_json(next_parameters),
                    "screen_passed": False,
                    "failure_observation_count": len(adjacent_failures),
                    "failures": adjacent_failures,
                },
            }
        )

    _assert_bundle_pressure_order(bundles)
    report = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "status": REPORT_STATUS,
        "contract_status": CONTRACT_STATUS,
        "balance_verdict": BALANCE_VERDICT,
        "selection_authority": SELECTION_AUTHORITY,
        "exact_numeric_values_selected": False,
        "player_facing_labels_selected": False,
        "complete_difficulty_profile_claimed": False,
        "difficulty_direction": {
            "player_difficulty_selection_adopted": True,
            "economic_order": [
                definition["bundle_id"] for definition in SCREEN_DEFINITIONS
            ],
            "lower_to_higher_pressure": True,
            "exact_values_require_user_review": True,
        },
        "difficulty_axis_scope": {
            "puzzle_pressure": "NOT_EVALUATED",
            "economy_pressure": "OBSERVED_PROVISIONAL_CANDIDATE_SLICE",
            "information_assistance": "NOT_EVALUATED",
        },
        "model_decisions": {
            "owned_upgrade_upkeep": owned_unit_contract,
            "room_service_usage": {
                "center_input": 0,
                "status": "DEFERRED_UNTIL_OCCURRENCE_RULES_EXIST",
                "future_low_medium_high_stress_overlays": True,
            },
        },
        "source_evidence": {
            "boundary_report_path": _repository_relative_posix(
                boundary_report_path
            ),
            "boundary_report_sha256": boundary_receipt["sha256"],
            "audit_source_path": boundary_report["source_evidence"][
                "audit_income_reference"
            ]["path"],
            "audit_source_sha256": boundary_report["source_evidence"][
                "audit_source_sha256"
            ],
            "income_trace_status": boundaries.TRACE_STATUS,
            "not_a_56_day_income_distribution": True,
        },
        "primary_structural_family": {
            "target_curve_id": PRIMARY_CURVE_ID,
            "reactivation_shape_id": PRIMARY_REACTIVATION_SHAPE_ID,
            "status": "PROVISIONAL_REFERENCE_FOR_DISPLAY",
        },
        "sensitivity_structures": {
            "target_curve_ids": [
                curve["id"] for curve in boundaries.TARGET_CURVES
            ],
            "reactivation_shape_ids": [
                shape["id"] for shape in boundaries.REACTIVATION_SHAPES
            ],
            "structure_count": len(boundaries.TARGET_CURVES)
            * len(boundaries.REACTIVATION_SHAPES),
            "each_screen_requires_every_structure": True,
        },
        "pressure_path_contract": {
            "scaling_denominator": PRESSURE_SCALE_DENOMINATOR,
            "minimum_basis_points": PRESSURE_PATH_MINIMUM_BASIS_POINTS,
            "maximum_basis_points": PRESSURE_PATH_MAXIMUM_BASIS_POINTS,
            "step_basis_points": PRESSURE_PATH_STEP_BASIS_POINTS,
            "rounding": PRESSURE_PATH_ROUNDING,
            "starting_cash_scaling": "ANCHOR_DIVIDED_BY_PRESSURE",
            "adverse_axis_scaling": "ANCHOR_MULTIPLIED_BY_PRESSURE",
            "componentwise_pressure_order_required": True,
            "path_vector_count": len(path),
            "path_vectors": list(path),
        },
        "screen_definitions": [dict(definition) for definition in SCREEN_DEFINITIONS],
        "anchor": {
            "pressure_basis_points": PRESSURE_SCALE_DENOMINATOR,
            "parameters": _parameter_json(anchor),
            "role": "EXPLANATORY_CENTER_NOT_A_SELECTED_DIFFICULTY",
        },
        "linked_bundles": bundles,
        "execution": {
            "generator_runtime_simulation_count": engine.simulation_count,
            "generator_runtime_simulation_count_evidence": (
                "GENERATOR_EVALUATION_CACHE_MISS_TELEMETRY_NOT_"
                "RECONSTRUCTED_FROM_ARTIFACT"
            ),
            "max_simulations": max_simulations,
            "saved_bundle_result_count": sum(
                len(bundle["results"]) for bundle in bundles
            ),
        },
        "interpretation_limits": [
            (
                "A/B/C are economy-pressure boundary candidates, not selected final values, "
                "player-facing names, probabilities, completion rates, or balance verdicts."
            ),
            (
                "The repeated five-day traces are sensitivity inputs, not a production 56-day "
                "income distribution or seed sample."
            ),
            (
                "Puzzle pressure, guest generation, placement complexity, time pressure, events, "
                "and information assistance are not evaluated by this report."
            ),
            (
                "Each bundle is one complete linked vector on a declared monotone path; values "
                "from different one-axis boundaries were not combined."
            ),
        ],
    }
    assert_provisional_linked_report(report)
    return report


def run_self_tests() -> dict[str, Any]:
    checks: list[str] = []
    spec = boundaries.default_anchor_spec()
    anchor = boundaries.anchor_parameters(spec)
    path = build_pressure_path(anchor)
    assert pressure_parameters(anchor, PRESSURE_SCALE_DENOMINATOR) == anchor
    checks.append("pressure_anchor_identity")
    assert len(path) > 3
    _assert_pressure_path(path)
    _assert_resolved_pressure_path(spec, path)
    checks.append("pressure_path_componentwise_monotone")
    contract = _normalized_owned_unit_contract(spec)
    assert contract["normalized_unit_weight_per_owned_upgrade"] == 1
    assert contract["owned_upgrade_day_weight"] == 133
    checks.append("owned_upgrade_normalized_unit_one")

    def synthetic_boundary(values: tuple[bool, ...]) -> tuple[int, int]:
        low = 0
        high = len(values) - 1
        assert values[low] is True and values[high] is False
        while high - low > 1:
            midpoint = (low + high) // 2
            if values[midpoint]:
                low = midpoint
            else:
                high = midpoint
        return low, high

    assert synthetic_boundary((True, True, True, False, False)) == (2, 3)
    checks.append("linked_path_adjacent_screen_search")

    minimal = {
        "status": REPORT_STATUS,
        "contract_status": CONTRACT_STATUS,
        "balance_verdict": BALANCE_VERDICT,
        "selection_authority": SELECTION_AUTHORITY,
        "exact_numeric_values_selected": False,
        "player_facing_labels_selected": False,
        "complete_difficulty_profile_claimed": False,
        "model_decisions": {"owned_upgrade_upkeep": contract},
        "difficulty_axis_scope": {
            "puzzle_pressure": "NOT_EVALUATED",
            "economy_pressure": "OBSERVED_PROVISIONAL_CANDIDATE_SLICE",
            "information_assistance": "NOT_EVALUATED",
        },
    }
    assert_provisional_linked_report(minimal)
    bad = json.loads(json.dumps(minimal))
    bad["winner"] = "ECONOMY_SLICE_B"
    try:
        assert_provisional_linked_report(bad)
    except AssertionError:
        pass
    else:
        raise AssertionError("linked report accepted an automatic winner")
    bad = json.loads(json.dumps(minimal))
    bad["exact_numeric_values_selected"] = True
    try:
        assert_provisional_linked_report(bad)
    except AssertionError:
        pass
    else:
        raise AssertionError("linked report accepted exact numeric selection")
    checks.append("provisional_selection_and_winner_guards")
    return {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "status": "SELF_TEST_PASS",
        "contract_status": CONTRACT_STATUS,
        "balance_verdict": BALANCE_VERDICT,
        "check_count": len(checks),
        "checks": checks,
    }


def _write_json(value: dict[str, Any], output: str) -> None:
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if output == "-":
        sys.stdout.write(encoded)
        return
    path = Path(output).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded, encoding="utf-8", newline="\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate provisional A/B/C linked economy-pressure boundary candidates without "
            "selecting final numbers, labels, or a balance verdict."
        )
    )
    parser.add_argument(
        "--boundary-report", type=Path, default=DEFAULT_BOUNDARY_REPORT
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--max-simulations", type=int, default=5_000)
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.self_test:
            _write_json(run_self_tests(), args.output)
            return 0
        report = make_linked_bundle_report(
            args.boundary_report,
            max_simulations=args.max_simulations,
            progress_stream=sys.stderr if args.progress else None,
        )
        _write_json(report, args.output)
        return 0
    except (
        AssertionError,
        BundleInputError,
        boundaries.CandidateInputError,
        boundaries.SimulationLimitError,
        frontier.EconomyInputError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"linked-bundle error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
