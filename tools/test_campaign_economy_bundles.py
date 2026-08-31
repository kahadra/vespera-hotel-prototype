from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable


if __package__:
    from . import generate_campaign_economy_bundles as bundles
else:
    import generate_campaign_economy_bundles as bundles


boundaries = bundles.boundaries
frontier = bundles.frontier

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = bundles.DEFAULT_OUTPUT

EXPECTED_GENERATOR_COUNT_EVIDENCE = (
    "GENERATOR_EVALUATION_CACHE_MISS_TELEMETRY_NOT_"
    "RECONSTRUCTED_FROM_ARTIFACT"
)
ALLOWED_TERMINAL_CLASSES = {
    "REACHED_DAY_56_DEBT_ZERO",
    "PREPARATION_PLAN_UNEXECUTABLE",
    "OPERATING_CASH_SHORTFALL",
    "CHAPTER_HURDLE_MISSED",
    "DEBT_DEADLINE_MISSED",
}
COMPACT_OUTCOME_FIELDS = {
    "trace_id",
    "target_curve_id",
    "reactivation_shape_id",
    "completed_structural_witness",
    "path_executable",
    "terminal_class",
    "terminal_runtime_status",
    "terminal_day",
    "terminal_shortfall_amount",
    "completed_days",
    "attempted_operation_count",
    "day_56_observed",
    "day_56_remaining_debt",
    "day_56_cash",
    "terminal_remaining_debt",
    "minimum_live_cash",
    "minimum_finance_cash",
    "terminal_live_cash",
    "terminal_finance_cash",
    "terminal_pending_preparation",
    "conservation_delta",
    "balance_verdict",
}
PARAMETER_FIELDS = (
    "starting_cash",
    "principal",
    "base_daily_upkeep",
    "upkeep_per_active_unit",
    "total_reactivation_cost",
)
TOP_LEVEL_FIELDS = {
    "report_schema_version",
    "status",
    "contract_status",
    "balance_verdict",
    "selection_authority",
    "exact_numeric_values_selected",
    "player_facing_labels_selected",
    "complete_difficulty_profile_claimed",
    "difficulty_direction",
    "difficulty_axis_scope",
    "model_decisions",
    "source_evidence",
    "primary_structural_family",
    "sensitivity_structures",
    "pressure_path_contract",
    "screen_definitions",
    "anchor",
    "linked_bundles",
    "execution",
    "interpretation_limits",
}
BUNDLE_FIELDS = {
    "bundle_id",
    "ordinal",
    "status",
    "player_facing_label",
    "balance_verdict",
    "path_index",
    "pressure_basis_points",
    "parameters",
    "required_source_bands",
    "screen_interpretation",
    "resolved_primary_structure",
    "result_summary",
    "results",
    "adjacent_higher_pressure_failure_witness",
}
ADJACENT_WITNESS_FIELDS = {
    "path_index",
    "pressure_basis_points",
    "parameters",
    "screen_passed",
    "failure_observation_count",
    "failures",
}


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _assert_lower_hex_sha256(value: Any) -> None:
    assert isinstance(value, str)
    assert len(value) == 64
    assert value == value.lower()
    assert all(character in "0123456789abcdef" for character in value)


def _load_canonical_json(path: Path) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes()
    assert raw
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in raw
    text = raw.decode("utf-8")
    assert text.endswith("\n")
    value = json.loads(text)
    assert isinstance(value, dict)
    assert text == json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    return raw, value


def _repository_path(relative: Any) -> Path:
    assert isinstance(relative, str) and relative
    posix = PurePosixPath(relative)
    windows = PureWindowsPath(relative)
    assert relative == posix.as_posix()
    assert "\\" not in relative
    assert not posix.is_absolute()
    assert not windows.is_absolute()
    assert windows.drive == ""
    assert ".." not in posix.parts
    resolved = (REPOSITORY_ROOT / Path(*posix.parts)).resolve()
    resolved.relative_to(REPOSITORY_ROOT.resolve())
    return resolved


def _parameter_tuple(parameters: dict[str, Any]) -> tuple[int, ...]:
    assert set(parameters) == set(PARAMETER_FIELDS)
    values = tuple(parameters[field] for field in PARAMETER_FIELDS)
    assert all(isinstance(value, int) and not isinstance(value, bool) for value in values)
    assert all(0 <= value <= frontier.MAX_SAFE_INTEGER for value in values)
    return values


def _parameter_set(parameters: dict[str, Any]) -> boundaries.ParameterSet:
    _parameter_tuple(parameters)
    return boundaries.ParameterSet(
        starting_cash=parameters["starting_cash"],
        principal=parameters["principal"],
        base_daily_upkeep=parameters["base_daily_upkeep"],
        upkeep_per_active_unit=parameters["upkeep_per_active_unit"],
        total_reactivation_cost=parameters["total_reactivation_cost"],
    )


def _round_half_up(numerator: int, denominator: int) -> int:
    assert numerator >= 0
    assert denominator > 0
    return (numerator + denominator // 2) // denominator


def _pressure_parameters(
    anchor: dict[str, int], basis_points: int, denominator: int
) -> dict[str, int]:
    assert basis_points > 0
    return {
        "starting_cash": _round_half_up(
            anchor["starting_cash"] * denominator, basis_points
        ),
        "principal": _round_half_up(
            anchor["principal"] * basis_points, denominator
        ),
        "base_daily_upkeep": _round_half_up(
            anchor["base_daily_upkeep"] * basis_points, denominator
        ),
        "upkeep_per_active_unit": _round_half_up(
            anchor["upkeep_per_active_unit"] * basis_points, denominator
        ),
        "total_reactivation_cost": _round_half_up(
            anchor["total_reactivation_cost"] * basis_points, denominator
        ),
    }


def _reconstruct_pressure_path(
    report: dict[str, Any], anchor: dict[str, int]
) -> list[dict[str, Any]]:
    contract = report["pressure_path_contract"]
    assert contract == {
        "scaling_denominator": bundles.PRESSURE_SCALE_DENOMINATOR,
        "minimum_basis_points": bundles.PRESSURE_PATH_MINIMUM_BASIS_POINTS,
        "maximum_basis_points": bundles.PRESSURE_PATH_MAXIMUM_BASIS_POINTS,
        "step_basis_points": bundles.PRESSURE_PATH_STEP_BASIS_POINTS,
        "rounding": bundles.PRESSURE_PATH_ROUNDING,
        "starting_cash_scaling": "ANCHOR_DIVIDED_BY_PRESSURE",
        "adverse_axis_scaling": "ANCHOR_MULTIPLIED_BY_PRESSURE",
        "componentwise_pressure_order_required": True,
        "path_vector_count": len(contract["path_vectors"]),
        "path_vectors": contract["path_vectors"],
    }
    denominator = contract["scaling_denominator"]
    reconstructed: list[dict[str, Any]] = []
    prior: tuple[int, ...] | None = None
    for basis_points in range(
        contract["minimum_basis_points"],
        contract["maximum_basis_points"] + 1,
        contract["step_basis_points"],
    ):
        parameters = _pressure_parameters(anchor, basis_points, denominator)
        current = _parameter_tuple(parameters)
        if current == prior:
            continue
        reconstructed.append(
            {
                "path_index": len(reconstructed),
                "pressure_basis_points": basis_points,
                "parameters": parameters,
            }
        )
        prior = current

    assert contract["path_vector_count"] == len(reconstructed)
    assert contract["path_vectors"] == reconstructed
    assert len({_parameter_tuple(row["parameters"]) for row in reconstructed}) == len(
        reconstructed
    )
    for index, row in enumerate(reconstructed):
        assert row["path_index"] == index
        if index == 0:
            continue
        prior_parameters = reconstructed[index - 1]["parameters"]
        parameters = row["parameters"]
        assert row["pressure_basis_points"] > reconstructed[index - 1][
            "pressure_basis_points"
        ]
        assert parameters["starting_cash"] <= prior_parameters["starting_cash"]
        for field in PARAMETER_FIELDS[1:]:
            assert parameters[field] >= prior_parameters[field]
        assert _parameter_tuple(parameters) != _parameter_tuple(prior_parameters)
    return reconstructed


def _assert_source_evidence(report: dict[str, Any]) -> dict[str, Any]:
    source = report["source_evidence"]
    boundary_path = _repository_path(source["boundary_report_path"])
    assert boundary_path == bundles.DEFAULT_BOUNDARY_REPORT.resolve()
    boundary_raw, boundary_report = _load_canonical_json(boundary_path)
    boundary_sha256 = _sha256_bytes(boundary_raw)
    _assert_lower_hex_sha256(source["boundary_report_sha256"])
    assert source["boundary_report_sha256"] == boundary_sha256
    boundary_receipt = bundles.boundary_validator.validate_report(boundary_path)
    assert boundary_receipt["sha256"] == boundary_sha256

    boundary_source = boundary_report["source_evidence"]
    boundary_audit_reference = boundary_source["audit_income_reference"]
    assert source["audit_source_path"] == boundary_audit_reference["path"]
    assert source["audit_source_sha256"] == boundary_source["audit_source_sha256"]
    audit_path = _repository_path(source["audit_source_path"])
    assert audit_path == frontier.DEFAULT_AUDIT_PATH.resolve()
    audit_sha256 = _sha256_bytes(audit_path.read_bytes())
    _assert_lower_hex_sha256(source["audit_source_sha256"])
    assert source["audit_source_sha256"] == audit_sha256
    assert source["income_trace_status"] == boundaries.TRACE_STATUS
    assert source["not_a_56_day_income_distribution"] is True
    return boundary_report


def _owned_upgrade_counts(spec: boundaries.AnchorSpec) -> list[int]:
    activation_days = list(spec.activation_days)
    assert len(activation_days) == len(set(activation_days))
    return [
        sum(activation_day <= day for activation_day in activation_days)
        for day in range(1, frontier.BASE_YEAR_DAYS + 1)
    ]


def _assert_owned_unit_contract(
    report: dict[str, Any], spec: boundaries.AnchorSpec
) -> list[int]:
    counts = _owned_upgrade_counts(spec)
    expected = {
        "counting_model": "EACH_OWNED_UPGRADE_COUNTS_AS_NORMALIZED_UNIT_ONE",
        "normalized_unit_weight_per_owned_upgrade": 1,
        "baseline_hotel_covered_by_base_daily_upkeep": True,
        "initial_additional_owned_upgrade_count": 0,
        "activation_days": list(spec.activation_days),
        "owned_upgrade_count_by_day": counts,
        "owned_upgrade_day_weight": sum(counts),
        "upkeep_per_active_unit_is_bundle_coefficient": True,
    }
    assert report["model_decisions"]["owned_upgrade_upkeep"] == expected
    prior = 0
    activation_days = set(spec.activation_days)
    for day, count in enumerate(counts, start=1):
        assert count == prior + (1 if day in activation_days else 0)
        prior = count
    return counts


def _compact_runtime_outcome(outcome: dict[str, Any]) -> dict[str, Any]:
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
        "balance_verdict": bundles.BALANCE_VERDICT,
    }


def _fresh_results(
    spec: boundaries.AnchorSpec,
    traces: tuple[boundaries.IncomeTrace, ...],
    parameters: dict[str, int],
) -> list[dict[str, Any]]:
    expected_count = (
        len(boundaries.TARGET_CURVES)
        * len(boundaries.REACTIVATION_SHAPES)
        * len(traces)
    )
    engine = boundaries.EvaluationEngine(
        spec, traces, max_simulations=expected_count
    )
    parameter_set = _parameter_set(parameters)
    results: list[dict[str, Any]] = []
    for curve in boundaries.TARGET_CURVES:
        for shape in boundaries.REACTIVATION_SHAPES:
            for trace in traces:
                results.append(
                    _compact_runtime_outcome(
                        engine.evaluate(
                            trace.trace_id,
                            curve["id"],
                            shape["id"],
                            parameter_set,
                        )
                    )
                )
    assert engine.simulation_count == expected_count
    return results


def _result_key(result: dict[str, Any]) -> tuple[str, str, str]:
    return (
        result["target_curve_id"],
        result["reactivation_shape_id"],
        result["trace_id"],
    )


def _assert_compact_outcome(result: dict[str, Any]) -> None:
    assert set(result) == COMPACT_OUTCOME_FIELDS
    assert result["terminal_class"] in ALLOWED_TERMINAL_CLASSES
    completed = result["terminal_class"] == "REACHED_DAY_56_DEBT_ZERO"
    assert result["completed_structural_witness"] is completed
    assert result["balance_verdict"] == bundles.BALANCE_VERDICT
    assert result["conservation_delta"] == 0
    for field in (
        "minimum_live_cash",
        "minimum_finance_cash",
        "terminal_live_cash",
        "terminal_finance_cash",
        "terminal_pending_preparation",
        "terminal_remaining_debt",
    ):
        assert isinstance(result[field], int) and result[field] >= 0
    assert (
        result["terminal_live_cash"] + result["terminal_pending_preparation"]
        == result["terminal_finance_cash"]
    )
    if result["day_56_observed"] is False:
        assert result["day_56_remaining_debt"] is None
        assert result["day_56_cash"] is None
    if completed:
        assert result["path_executable"] is True
        assert result["terminal_runtime_status"] == "COMPLETE"
        assert result["terminal_day"] == frontier.BASE_YEAR_DAYS
        assert result["day_56_observed"] is True
        assert result["day_56_remaining_debt"] == 0
        assert result["terminal_remaining_debt"] == 0
        assert result["terminal_pending_preparation"] == 0


def _trace_band_map(
    traces: tuple[boundaries.IncomeTrace, ...]
) -> dict[str, str]:
    mapping = {trace.trace_id: trace.source_band for trace in traces}
    assert len(mapping) == 15
    assert Counter(mapping.values()) == Counter(
        {band: 5 for band in bundles.SOURCE_BAND_ORDER}
    )
    return mapping


def _screen_failures(
    results: Iterable[dict[str, Any]],
    required_bands: Iterable[str],
    trace_bands: dict[str, str],
) -> list[dict[str, Any]]:
    required = set(required_bands)
    assert required <= set(bundles.SOURCE_BAND_ORDER)
    return [
        result
        for result in results
        if trace_bands[result["trace_id"]] in required
        and result["completed_structural_witness"] is not True
    ]


def _result_summary(
    traces: tuple[boundaries.IncomeTrace, ...],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    trace_bands = _trace_band_map(traces)
    structures: list[dict[str, Any]] = []
    for curve in boundaries.TARGET_CURVES:
        for shape in boundaries.REACTIVATION_SHAPES:
            selected = [
                result
                for result in results
                if result["target_curve_id"] == curve["id"]
                and result["reactivation_shape_id"] == shape["id"]
            ]
            band_rows: dict[str, Any] = {}
            for band in bundles.SOURCE_BAND_ORDER:
                band_results = [
                    result
                    for result in selected
                    if trace_bands[result["trace_id"]] == band
                ]
                band_rows[band] = {
                    "observation_count": len(band_results),
                    "structural_completion_observation_count": sum(
                        result["completed_structural_witness"] is True
                        for result in band_results
                    ),
                    "terminal_class_counts": dict(
                        sorted(
                            Counter(
                                result["terminal_class"] for result in band_results
                            ).items()
                        )
                    ),
                }
            structures.append(
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
            result["completed_structural_witness"] is True for result in results
        ),
        "terminal_class_counts": dict(
            sorted(Counter(result["terminal_class"] for result in results).items())
        ),
        "probability_interpretation_allowed": False,
        "structure_observations": structures,
    }


def _allocate_total(total: int, weights: tuple[int, ...]) -> list[int]:
    assert total >= 0
    assert weights and all(weight > 0 for weight in weights)
    denominator = sum(weights)
    floors = [(total * weight) // denominator for weight in weights]
    remaining = total - sum(floors)
    remainders = [
        ((total * weight) % denominator, index)
        for index, weight in enumerate(weights)
    ]
    for _, index in sorted(remainders, key=lambda item: (-item[0], item[1]))[
        :remaining
    ]:
        floors[index] += 1
    assert sum(floors) == total
    return floors


def _assert_resolved_primary_structure(
    bundle: dict[str, Any],
    spec: boundaries.AnchorSpec,
    owned_counts: list[int],
) -> None:
    parameters = bundle["parameters"]
    primary = bundle["resolved_primary_structure"]
    assert primary["target_curve_id"] == bundles.PRIMARY_CURVE_ID
    assert (
        primary["reactivation_shape_id"]
        == bundles.PRIMARY_REACTIVATION_SHAPE_ID
    )
    curve = next(
        curve
        for curve in boundaries.TARGET_CURVES
        if curve["id"] == bundles.PRIMARY_CURVE_ID
    )
    assert primary["chapter_cumulative_targets"] == boundaries.realize_target_curve(
        curve, parameters["principal"]
    )
    assert primary["per_day_upkeep_schedule"] == [
        parameters["base_daily_upkeep"]
        + parameters["upkeep_per_active_unit"] * owned_count
        for owned_count in owned_counts
    ]
    shape = next(
        shape
        for shape in boundaries.REACTIVATION_SHAPES
        if shape["id"] == bundles.PRIMARY_REACTIVATION_SHAPE_ID
    )
    amounts = _allocate_total(
        parameters["total_reactivation_cost"], shape["weights"]
    )
    assert primary["reactivation_events"] == [
        {
            "day": day,
            "amount": amount,
            "label": f"ABSTRACT_ACTIVATION_{index}",
        }
        for index, (day, amount) in enumerate(
            zip(spec.activation_days, amounts), start=1
        )
    ]


def _assert_pressure_order_and_success_inclusion(
    linked: list[dict[str, Any]],
    spec: boundaries.AnchorSpec,
    owned_counts: list[int],
) -> None:
    for easier, harder in zip(linked, linked[1:]):
        assert easier["path_index"] < harder["path_index"]
        easy = easier["parameters"]
        hard = harder["parameters"]
        assert easy["starting_cash"] >= hard["starting_cash"]
        for field in PARAMETER_FIELDS[1:]:
            assert easy[field] <= hard[field]
        assert _parameter_tuple(easy) != _parameter_tuple(hard)

        easy_upkeep = [
            easy["base_daily_upkeep"]
            + easy["upkeep_per_active_unit"] * count
            for count in owned_counts
        ]
        hard_upkeep = [
            hard["base_daily_upkeep"]
            + hard["upkeep_per_active_unit"] * count
            for count in owned_counts
        ]
        assert all(left <= right for left, right in zip(easy_upkeep, hard_upkeep))

        for curve in boundaries.TARGET_CURVES:
            easy_targets = boundaries.realize_target_curve(curve, easy["principal"])
            hard_targets = boundaries.realize_target_curve(curve, hard["principal"])
            assert all(
                easy_targets[str(day)] <= hard_targets[str(day)]
                for day in frontier.CHAPTER_DAYS
            )

        for shape in boundaries.REACTIVATION_SHAPES:
            easy_amounts = _allocate_total(
                easy["total_reactivation_cost"], shape["weights"]
            )
            hard_amounts = _allocate_total(
                hard["total_reactivation_cost"], shape["weights"]
            )
            assert all(
                left <= right for left, right in zip(easy_amounts, hard_amounts)
            )
            assert all(
                sum(easy_amounts[:prefix]) <= sum(hard_amounts[:prefix])
                for prefix in range(1, len(easy_amounts) + 1)
            )

        easy_successes = {
            _result_key(result)
            for result in easier["results"]
            if result["completed_structural_witness"] is True
        }
        hard_successes = {
            _result_key(result)
            for result in harder["results"]
            if result["completed_structural_witness"] is True
        }
        assert hard_successes <= easy_successes


def _assert_provisional_scope(report: dict[str, Any]) -> None:
    assert set(report) == TOP_LEVEL_FIELDS
    bundles.assert_provisional_linked_report(report)
    assert report["status"] == bundles.REPORT_STATUS
    assert report["contract_status"] == bundles.CONTRACT_STATUS
    assert report["balance_verdict"] == bundles.BALANCE_VERDICT
    assert report["selection_authority"] == bundles.SELECTION_AUTHORITY
    assert report["exact_numeric_values_selected"] is False
    assert report["player_facing_labels_selected"] is False
    assert report["complete_difficulty_profile_claimed"] is False
    assert report["difficulty_axis_scope"] == {
        "puzzle_pressure": "NOT_EVALUATED",
        "economy_pressure": "OBSERVED_PROVISIONAL_CANDIDATE_SLICE",
        "information_assistance": "NOT_EVALUATED",
    }
    assert report["difficulty_direction"] == {
        "player_difficulty_selection_adopted": True,
        "economic_order": [
            definition["bundle_id"] for definition in bundles.SCREEN_DEFINITIONS
        ],
        "lower_to_higher_pressure": True,
        "exact_values_require_user_review": True,
    }
    assert report["interpretation_limits"] == [
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
    ]

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                normalized = key.replace("_", "").lower()
                assert normalized not in bundles.BANNED_NORMALIZED_KEYS
                if normalized == "balanceverdict":
                    assert nested == bundles.BALANCE_VERDICT
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(report)


def validate_report(path: Path) -> dict[str, Any]:
    raw, report = _load_canonical_json(path)
    assert report["report_schema_version"] == bundles.REPORT_SCHEMA_VERSION
    _assert_provisional_scope(report)
    _assert_source_evidence(report)

    spec = boundaries.default_anchor_spec()
    default_anchor = boundaries.anchor_parameters(spec)
    anchor_parameters = {
        field: getattr(default_anchor, field) for field in PARAMETER_FIELDS
    }
    assert report["anchor"] == {
        "pressure_basis_points": bundles.PRESSURE_SCALE_DENOMINATOR,
        "parameters": anchor_parameters,
        "role": "EXPLANATORY_CENTER_NOT_A_SELECTED_DIFFICULTY",
    }
    pressure_path = _reconstruct_pressure_path(report, anchor_parameters)
    owned_counts = _assert_owned_unit_contract(report, spec)

    reference = frontier.load_audit_income_reference(frontier.DEFAULT_AUDIT_PATH)
    traces = boundaries.build_phase_rotated_traces(reference)
    assert len(traces) == 15
    trace_bands = _trace_band_map(traces)
    expected_result_keys = [
        (curve["id"], shape["id"], trace.trace_id)
        for curve in boundaries.TARGET_CURVES
        for shape in boundaries.REACTIVATION_SHAPES
        for trace in traces
    ]
    assert len(expected_result_keys) == 90

    assert report["primary_structural_family"] == {
        "target_curve_id": bundles.PRIMARY_CURVE_ID,
        "reactivation_shape_id": bundles.PRIMARY_REACTIVATION_SHAPE_ID,
        "status": "PROVISIONAL_REFERENCE_FOR_DISPLAY",
    }
    assert report["sensitivity_structures"] == {
        "target_curve_ids": [curve["id"] for curve in boundaries.TARGET_CURVES],
        "reactivation_shape_ids": [
            shape["id"] for shape in boundaries.REACTIVATION_SHAPES
        ],
        "structure_count": 6,
        "each_screen_requires_every_structure": True,
    }
    expected_screen_definitions = json.loads(
        json.dumps([dict(definition) for definition in bundles.SCREEN_DEFINITIONS])
    )
    assert report["screen_definitions"] == expected_screen_definitions

    linked = report["linked_bundles"]
    assert len(linked) == 3
    assert [bundle["bundle_id"] for bundle in linked] == [
        definition["bundle_id"] for definition in bundles.SCREEN_DEFINITIONS
    ]
    assert [bundle["ordinal"] for bundle in linked] == [1, 2, 3]

    fresh_runtime_simulation_count = 0
    for definition, bundle in zip(bundles.SCREEN_DEFINITIONS, linked):
        assert set(bundle) == BUNDLE_FIELDS
        assert bundle["status"] == "PROVISIONAL_LINKED_PATH_BOUNDARY_CANDIDATE"
        assert bundle["player_facing_label"] is None
        assert bundle["balance_verdict"] == bundles.BALANCE_VERDICT
        assert bundle["required_source_bands"] == list(
            definition["required_source_bands"]
        )
        assert bundle["screen_interpretation"] == definition["interpretation"]

        path_index = bundle["path_index"]
        assert 0 <= path_index < len(pressure_path) - 1
        path_entry = pressure_path[path_index]
        assert bundle["pressure_basis_points"] == path_entry["pressure_basis_points"]
        assert bundle["parameters"] == path_entry["parameters"]
        _parameter_tuple(bundle["parameters"])
        _assert_resolved_primary_structure(bundle, spec, owned_counts)

        saved_results = bundle["results"]
        assert len(saved_results) == 90
        assert [_result_key(result) for result in saved_results] == expected_result_keys
        assert len({_result_key(result) for result in saved_results}) == 90
        for result in saved_results:
            _assert_compact_outcome(result)
        assert bundle["result_summary"] == _result_summary(traces, saved_results)
        assert not _screen_failures(
            saved_results,
            definition["required_source_bands"],
            trace_bands,
        )

        fresh_selected = _fresh_results(spec, traces, bundle["parameters"])
        fresh_runtime_simulation_count += len(fresh_selected)
        assert fresh_selected == saved_results

        adjacent = bundle["adjacent_higher_pressure_failure_witness"]
        assert set(adjacent) == ADJACENT_WITNESS_FIELDS
        assert adjacent["path_index"] == path_index + 1
        adjacent_entry = pressure_path[adjacent["path_index"]]
        assert adjacent["pressure_basis_points"] == adjacent_entry[
            "pressure_basis_points"
        ]
        assert adjacent["parameters"] == adjacent_entry["parameters"]
        assert adjacent["screen_passed"] is False
        assert adjacent["failure_observation_count"] == len(adjacent["failures"])
        assert adjacent["failure_observation_count"] > 0
        for result in adjacent["failures"]:
            _assert_compact_outcome(result)
            assert result["completed_structural_witness"] is False
            assert trace_bands[result["trace_id"]] in set(
                definition["required_source_bands"]
            )

        fresh_adjacent = _fresh_results(spec, traces, adjacent["parameters"])
        fresh_runtime_simulation_count += len(fresh_adjacent)
        assert adjacent["failures"] == _screen_failures(
            fresh_adjacent,
            definition["required_source_bands"],
            trace_bands,
        )

    _assert_pressure_order_and_success_inclusion(linked, spec, owned_counts)

    execution = report["execution"]
    assert execution["generator_runtime_simulation_count"] > 0
    assert (
        execution["generator_runtime_simulation_count"]
        <= execution["max_simulations"]
    )
    assert (
        execution["generator_runtime_simulation_count_evidence"]
        == EXPECTED_GENERATOR_COUNT_EVIDENCE
    )
    assert execution["saved_bundle_result_count"] == 270
    assert sum(len(bundle["results"]) for bundle in linked) == 270
    assert fresh_runtime_simulation_count == 540

    return {
        "status": "PASS",
        "report_schema_version": report["report_schema_version"],
        "sha256": _sha256_bytes(raw),
        "pressure_path_vector_count": len(pressure_path),
        "linked_bundle_count": len(linked),
        "saved_bundle_result_count": execution["saved_bundle_result_count"],
        "fresh_runtime_simulation_count": fresh_runtime_simulation_count,
        "balance_verdict": report["balance_verdict"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate provisional A/B/C linked campaign economy bundle observations"
        )
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    result = validate_report(args.report.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
