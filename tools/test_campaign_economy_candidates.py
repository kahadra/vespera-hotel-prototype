from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


if __package__:
    from . import generate_campaign_economy_candidates as candidates
else:
    import generate_campaign_economy_candidates as candidates


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = (
    REPOSITORY_ROOT
    / "artifacts"
    / "campaign-economy-candidates"
    / "provisional-boundary-observations.json"
)

DEFAULT_AUDIT_REPOSITORY_PATH = (
    "artifacts/v2-core-playtest/exhaustive-placement-audit.json"
)
AUDIT_PATH_KIND = "REPOSITORY_RELATIVE_POSIX"
SIMULATION_COUNT_EVIDENCE = (
    "GENERATOR_EVALUATION_CACHE_MISS_TELEMETRY_NOT_RECONSTRUCTED_FROM_ARTIFACT"
)
FROZEN_DEFAULT_UNIQUE_RUNTIME_SIMULATION_COUNT = 3_642

ALLOWED_TERMINAL_CLASSES = {
    "REACHED_DAY_56_DEBT_ZERO",
    "PREPARATION_PLAN_UNEXECUTABLE",
    "OPERATING_CASH_SHORTFALL",
    "CHAPTER_HURDLE_MISSED",
    "DEBT_DEADLINE_MISSED",
}


def _assert_runtime_contract(report: dict[str, Any]) -> None:
    assert report["contract_status"] == candidates.CONTRACT_STATUS
    assert report["balance_verdict"] == candidates.BALANCE_VERDICT
    assert report["runtime_conformance"] is True
    assert (
        report["runtime_conformance_scope"]
        == candidates.frontier.RUNTIME_CONFORMANCE_SCOPE
    )
    assert (
        report["runtime_conformance_excludes"]
        == candidates.frontier.RUNTIME_CONFORMANCE_EXCLUDES
    )
    assert report["full_game_controller_conformance_claimed"] is False
    assert report["primary_policy"] == {
        "id": candidates.PRIMARY_POLICY,
        "role": "STRUCTURAL_REACHABILITY_WITNESS",
        "manual_extra_repayments": [],
        "claim": (
            "At each checkpoint, explicitly submit only the current cumulative gap; "
            "submit zero on non-checkpoint days."
        ),
        "automatic_game_debit_claimed": False,
    }


def _assert_default_audit_source(report: dict[str, Any]) -> None:
    source = report["source_evidence"]
    reference = source["audit_income_reference"]
    source_path = reference["path"]
    assert isinstance(source_path, str) and source_path
    assert reference["path_kind"] == AUDIT_PATH_KIND

    posix_path = PurePosixPath(source_path)
    windows_path = PureWindowsPath(source_path)
    assert source_path == posix_path.as_posix()
    assert "\\" not in source_path
    assert not posix_path.is_absolute()
    assert not windows_path.is_absolute()
    assert windows_path.drive == ""
    assert ".." not in posix_path.parts

    default_audit = candidates.frontier.DEFAULT_AUDIT_PATH.resolve()
    repository_relative = default_audit.relative_to(REPOSITORY_ROOT.resolve()).as_posix()
    assert repository_relative == DEFAULT_AUDIT_REPOSITORY_PATH
    assert source_path == repository_relative

    embedded_sha256 = source["audit_source_sha256"]
    assert isinstance(embedded_sha256, str)
    assert len(embedded_sha256) == 64
    assert embedded_sha256 == embedded_sha256.lower()
    assert all(character in "0123456789abcdef" for character in embedded_sha256)
    current_sha256 = hashlib.sha256(default_audit.read_bytes()).hexdigest()
    assert embedded_sha256 == current_sha256


def _assert_witness_cash(witness: dict[str, Any]) -> None:
    assert witness["conservation_delta"] == 0
    assert witness["minimum_live_cash"] >= 0
    assert witness["minimum_finance_cash"] >= 0
    assert witness["terminal_live_cash"] >= 0
    assert witness["terminal_finance_cash"] >= 0
    assert witness["terminal_pending_preparation"] >= 0
    assert (
        witness["terminal_live_cash"]
        + witness["terminal_pending_preparation"]
        == witness["terminal_finance_cash"]
    )
    if witness["day_56_observed"] is False:
        assert witness["day_56_remaining_debt"] is None
    assert witness["balance_verdict"] == "NOT_EVALUATED"


def _assert_boundary(boundary: dict[str, Any], anchor: dict[str, int]) -> None:
    assert boundary["balance_verdict"] == "NOT_EVALUATED"
    assert boundary["direction"] in {"MINIMUM_FEASIBLE", "MAXIMUM_FEASIBLE"}
    assert boundary["boundary_status"] in {
        "ADJACENT_INTEGER_BOUNDARY",
        "DOMAIN_MINIMUM_IS_FEASIBLE",
        "DOMAIN_MINIMUM_IS_MAXIMUM_FEASIBLE",
        "NO_FEASIBLE_NONNEGATIVE_VALUE_WITH_HELD_ANCHORS",
    }
    assert set(boundary["held_anchor_parameters"]) == set(anchor) - {
        boundary["axis_id"]
    }
    for key, value in boundary["held_anchor_parameters"].items():
        assert value == anchor[key]
    witnesses = boundary["witnesses"]
    assert witnesses
    assert len({witness["witness_id"] for witness in witnesses}) == len(witnesses)
    for witness in witnesses:
        assert witness["terminal_class"] in ALLOWED_TERMINAL_CLASSES
        _assert_witness_cash(witness)

    value = boundary["boundary_value"]
    if boundary["boundary_status"] == "ADJACENT_INTEGER_BOUNDARY":
        assert isinstance(value, int) and value >= 0
        relations = {witness["relation"]: witness for witness in witnesses}
        assert relations["AT_BOUNDARY"]["value"] == value
        if boundary["direction"] == "MINIMUM_FEASIBLE":
            assert relations["BELOW_BOUNDARY"]["value"] == value - 1
            assert relations["ABOVE_BOUNDARY"]["value"] == value + 1
            assert relations["BELOW_BOUNDARY"]["completed_structural_witness"] is False
            assert relations["AT_BOUNDARY"]["completed_structural_witness"] is True
            assert relations["ABOVE_BOUNDARY"]["completed_structural_witness"] is True
        else:
            if value > 0:
                assert relations["BELOW_BOUNDARY"]["value"] == value - 1
                assert relations["BELOW_BOUNDARY"]["completed_structural_witness"] is True
            assert relations["ABOVE_BOUNDARY"]["value"] == value + 1
            assert relations["AT_BOUNDARY"]["completed_structural_witness"] is True
            assert relations["ABOVE_BOUNDARY"]["completed_structural_witness"] is False
    elif boundary["boundary_status"] == "DOMAIN_MINIMUM_IS_FEASIBLE":
        assert value == 0
        assert witnesses[0]["relation"] == "AT_BOUNDARY"
        assert witnesses[0]["completed_structural_witness"] is True
    elif boundary["boundary_status"] == "DOMAIN_MINIMUM_IS_MAXIMUM_FEASIBLE":
        assert value == 0
        relations = {witness["relation"]: witness for witness in witnesses}
        assert set(relations) == {"AT_BOUNDARY", "ABOVE_BOUNDARY"}
        assert relations["AT_BOUNDARY"]["value"] == 0
        assert relations["AT_BOUNDARY"]["completed_structural_witness"] is True
        assert relations["ABOVE_BOUNDARY"]["value"] == 1
        assert relations["ABOVE_BOUNDARY"]["completed_structural_witness"] is False
    else:
        assert value is None
        assert len(witnesses) == 1
        assert witnesses[0]["relation"] == "DOMAIN_MINIMUM"
        assert witnesses[0]["value"] == 0
        assert witnesses[0]["completed_structural_witness"] is False


def _assert_boundary_groups(
    groups: list[dict[str, Any]], observations: list[dict[str, Any]]
) -> None:
    by_id = {observation["boundary_id"]: observation for observation in observations}
    assert len(by_id) == len(observations)
    for group in groups:
        assert group["phase_rotation_count"] == 5
        phases = group["phase_boundaries"]
        assert [phase["phase_offset"] for phase in phases] == list(range(5))
        assert all(phase["boundary_id"] in by_id for phase in phases)
        values = [
            phase["boundary_value"]
            for phase in phases
            if phase["boundary_value"] is not None
        ]
        assert group["observed_boundary_minimum"] == (min(values) if values else None)
        assert group["observed_boundary_maximum"] == (max(values) if values else None)
        all_values = len(values) == 5
        assert group["all_phases_have_boundary_value"] is all_values
        if not all_values:
            assert group["all_phase_feasible_envelope"] is None
            assert group["controlling_boundary_ids"] == []
            continue
        expected = (
            max(values)
            if group["direction"] == "MINIMUM_FEASIBLE"
            else min(values)
        )
        assert group["all_phase_feasible_envelope"] == expected
        expected_controllers = [
            phase["boundary_id"]
            for phase in phases
            if phase["boundary_value"] == expected
        ]
        assert group["controlling_boundary_ids"] == expected_controllers


def validate_report(path: Path) -> dict[str, Any]:
    raw_bytes = path.read_bytes()
    assert b"\r" not in raw_bytes
    text = raw_bytes.decode("utf-8")
    report = json.loads(text)
    normalized_text = text.replace("\r\n", "\n")
    assert "\r" not in normalized_text
    assert normalized_text == json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    candidates.assert_provisional_boundary(report)
    assert report["report_schema_version"] == candidates.REPORT_SCHEMA_VERSION
    assert report["status"] == candidates.REPORT_STATUS
    _assert_runtime_contract(report)
    _assert_default_audit_source(report)
    assert report["sampling_contract"] == {
        "trace_count": 15,
        "source_band_count": 3,
        "phase_rotation_count_per_band": 5,
        "probability_weights": None,
        "boundary_refinement": "INTEGER_ADJACENCY",
        "one_axis_at_a_time": True,
        "joint_feasible_region_claimed": False,
    }
    traces = report["trace_definitions"]
    assert len(traces) == 15
    assert len({trace["trace_id"] for trace in traces}) == 15
    assert all(len(trace["five_day_pattern_after_rotation"]) == 5 for trace in traces)
    assert all(len(trace["daily_gross_56"]) == 56 for trace in traces)
    assert all(trace["probability_weight"] is None for trace in traces)
    totals = {
        band: [trace["gross_total_56"] for trace in traces if trace["source_band"] == band]
        for band in ("GREEDY_LOW", "MECHANICAL_MIDPOINT", "CANONICAL")
    }
    assert (min(totals["GREEDY_LOW"]), max(totals["GREEDY_LOW"])) == (980, 997)
    assert (min(totals["MECHANICAL_MIDPOINT"]), max(totals["MECHANICAL_MIDPOINT"])) == (
        2195,
        2214,
    )
    assert (min(totals["CANONICAL"]), max(totals["CANONICAL"])) == (3433, 3477)
    assert len(report["target_curve_definitions"]) == 3
    assert len(report["reactivation_shape_definitions"]) == 2

    execution = report["execution"]
    assert execution["structure_count"] == 90
    assert execution["boundary_observation_count"] == 450
    assert execution["boundary_group_count"] == 90
    assert 0 < execution["unique_runtime_simulation_count"] <= execution["max_simulations"]
    assert (
        execution["unique_runtime_simulation_count_evidence"]
        == SIMULATION_COUNT_EVIDENCE
    )
    if path.resolve() == DEFAULT_REPORT.resolve():
        assert (
            execution["unique_runtime_simulation_count"]
            == FROZEN_DEFAULT_UNIQUE_RUNTIME_SIMULATION_COUNT
        )
    observations = report["boundary_observations"]
    assert len(observations) == 450
    assert len({observation["boundary_id"] for observation in observations}) == 450
    anchor = report["anchor"]["parameters"]
    for observation in observations:
        _assert_boundary(observation, anchor)
    groups = report["boundary_groups"]
    assert len(groups) == 90
    _assert_boundary_groups(groups, observations)

    anchor_groups = report["anchor_observation_groups"]
    assert len(anchor_groups) == 6
    for group in anchor_groups:
        assert group["trace_count"] == 15
        assert sum(group["terminal_class_counts"].values()) == 15
        assert group["probability_interpretation_allowed"] is False
        for source in group["source_band_observations"].values():
            assert source["trace_count"] == 5
            assert sum(source["terminal_class_counts"].values()) == 5

    spans = report["parameter_range_evidence"]
    assert set(spans) == {axis["id"] for axis in candidates.BOUNDARY_AXES}
    assert all(span["joint_feasible_region_claimed"] is False for span in spans.values())
    no_value_count = sum(
        observation["boundary_value"] is None for observation in observations
    )
    assert no_value_count == sum(
        1
        for group in groups
        for phase in group["phase_boundaries"]
        if phase["boundary_value"] is None
    )
    decision = report["decision_packet"]
    assert decision["user_gate"] == "MODEL_DECISION_REQUIRED"
    assert decision["linked_numeric_bundles_generated"] is False
    assert decision["numeric_bundle_selection_ready"] is False
    assert decision["exact_numeric_values_selected"] is False
    return {
        "status": "PASS",
        "report_schema_version": report["report_schema_version"],
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "trace_count": len(traces),
        "structure_count": execution["structure_count"],
        "boundary_observation_count": len(observations),
        "boundary_group_count": len(groups),
        "unique_runtime_simulation_count": execution[
            "unique_runtime_simulation_count"
        ],
        "boundary_without_value_count": no_value_count,
        "balance_verdict": report["balance_verdict"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the generated provisional campaign economy boundary report"
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    result = validate_report(args.report.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
