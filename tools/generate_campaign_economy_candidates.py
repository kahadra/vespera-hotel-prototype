from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable


if __package__:
    from . import analyze_campaign_economy_frontier as frontier
else:
    import analyze_campaign_economy_frontier as frontier


REPORT_SCHEMA_VERSION = 1
REPORT_STATUS = "PROVISIONAL_CANDIDATE_BOUNDARY_OBSERVATIONS"
PRIMARY_POLICY = frontier.POLICY_CHAPTER_MANUAL
TRACE_STATUS = "SYNTHETIC_FIVE_DAY_PATTERN_PHASE_ROTATIONS"
TARGET_ROUNDING_ID = "CEIL_RATIONAL_SHARE_V1"
REACTIVATION_ALLOCATION_ID = "LARGEST_REMAINDER_EARLIEST_INDEX_V1"
DEFAULT_MAX_SIMULATIONS = 5_000
SIMULATION_COUNT_EVIDENCE = (
    "GENERATOR_EVALUATION_CACHE_MISS_TELEMETRY_NOT_RECONSTRUCTED_FROM_ARTIFACT"
)

BALANCE_VERDICT = frontier.RUNTIME_BALANCE_VERDICT
CONTRACT_STATUS = frontier.RUNTIME_CONTRACT_STATUS

INTERPRETATION_LIMITS = (
    frontier.BALANCE_DISCLAIMER,
    frontier.AUDIT_LIMIT_KO,
    frontier.RUNTIME_SETTLEMENT_CONTRACT,
    (
        "The 15 traces are five phase rotations of two observed five-operation paths and one "
        "mechanical midpoint. Trace counts are sensitivity observations, not probabilities, "
        "completion rates, a 56-day income distribution, or a difficulty verdict."
    ),
    (
        "Every one-dimensional boundary holds the other anchor values fixed. It is not a joint "
        "feasible region and must not be promoted to a selected economy bundle."
    ),
)

TARGET_CURVES = (
    {
        "id": "REFERENCE_60_140_330_520_700_OVER_700",
        "description": "Rational form of the current illustrative checkpoint vector.",
        "shares": ((60, 700), (140, 700), (330, 700), (520, 700), (1, 1)),
    },
    {
        "id": "ELAPSED_DAY_SHARE",
        "description": "Cumulative target proportional to elapsed base-year days.",
        "shares": ((7, 56), (14, 56), (28, 56), (42, 56), (1, 1)),
    },
    {
        "id": "CHECKPOINT_COUNT_SHARE",
        "description": "Equal cumulative increments across the five checkpoint observations.",
        "shares": ((1, 5), (2, 5), (3, 5), (4, 5), (1, 1)),
    },
)

REACTIVATION_SHAPES = (
    {
        "id": "REFERENCE_RATIO_2_3_4_5",
        "description": "Relative shape of the current illustrative 30/45/60/75 schedule.",
        "weights": (2, 3, 4, 5),
    },
    {
        "id": "EQUAL_RATIO_1_1_1_1",
        "description": "Equal allocation across the four abstract activation events.",
        "weights": (1, 1, 1, 1),
    },
)

BOUNDARY_AXES = (
    {
        "id": "starting_cash",
        "direction": "MINIMUM_FEASIBLE",
        "monotonic_contract": "MORE_CANNOT_HURT_WITH_OTHER_VALUES_FIXED",
    },
    {
        "id": "principal",
        "direction": "MAXIMUM_FEASIBLE",
        "monotonic_contract": "LESS_CANNOT_HURT_WITH_OTHER_VALUES_FIXED",
    },
    {
        "id": "base_daily_upkeep",
        "direction": "MAXIMUM_FEASIBLE",
        "monotonic_contract": "LESS_CANNOT_HURT_WITH_OTHER_VALUES_FIXED",
    },
    {
        "id": "upkeep_per_active_unit",
        "direction": "MAXIMUM_FEASIBLE",
        "monotonic_contract": "LESS_CANNOT_HURT_WITH_OTHER_VALUES_FIXED",
    },
    {
        "id": "total_reactivation_cost",
        "direction": "MAXIMUM_FEASIBLE",
        "monotonic_contract": "LESS_CANNOT_HURT_WITH_OTHER_VALUES_FIXED",
    },
)

BANNED_REPORT_KEYS = {
    "recommended_candidate_id",
    "winner",
    "best_candidate",
    "balance_pass",
    "balance_fail",
    "completion_rate",
}

NORMALIZED_BANNED_REPORT_KEYS = {
    key.replace("_", "").lower() for key in BANNED_REPORT_KEYS
}


class CandidateInputError(ValueError):
    """Raised when a candidate-boundary input is ambiguous or unsafe."""


class SimulationLimitError(RuntimeError):
    """Raised before a candidate report exceeds its declared simulation budget."""


@dataclass(frozen=True)
class ScheduledCost:
    day: int
    amount: int
    label: str


@dataclass(frozen=True)
class AnchorSpec:
    starting_cash: int
    principal: int
    base_daily_upkeep: int
    upkeep_per_active_unit: int
    total_reactivation_cost: int
    activation_days: tuple[int, ...]
    room_service_spends: tuple[ScheduledCost, ...]


@dataclass(frozen=True)
class ParameterSet:
    starting_cash: int
    principal: int
    base_daily_upkeep: int
    upkeep_per_active_unit: int
    total_reactivation_cost: int


@dataclass(frozen=True)
class IncomeTrace:
    trace_id: str
    source_band: str
    source_kind: str
    phase_offset: int
    five_day_pattern: tuple[int, ...]
    daily_gross: tuple[int, ...]


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CandidateInputError(f"{name} must be an integer")
    if value < 0:
        raise CandidateInputError(f"{name} must not be negative")
    if value > frontier.MAX_SAFE_INTEGER:
        raise CandidateInputError(
            f"{name} must not exceed JavaScript safe integer {frontier.MAX_SAFE_INTEGER}"
        )
    return value


def _positive_day(value: Any, name: str) -> int:
    day = _nonnegative_int(value, name)
    if not 1 <= day <= frontier.BASE_YEAR_DAYS:
        raise CandidateInputError(
            f"{name} must be between 1 and {frontier.BASE_YEAR_DAYS}"
        )
    return day


def default_anchor_spec() -> AnchorSpec:
    return AnchorSpec(
        starting_cash=60,
        principal=700,
        base_daily_upkeep=2,
        upkeep_per_active_unit=1,
        total_reactivation_cost=210,
        activation_days=(8, 15, 29, 43),
        room_service_spends=(),
    )


def _parse_scheduled_costs(raw: Any, name: str) -> tuple[ScheduledCost, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise CandidateInputError(f"{name} must be a list")
    output: list[ScheduledCost] = []
    seen_labels: set[str] = set()
    for index, entry in enumerate(raw):
        owner = f"{name}[{index}]"
        if not isinstance(entry, dict):
            raise CandidateInputError(f"{owner} must be an object")
        if set(entry) != {"day", "amount", "label"}:
            raise CandidateInputError(
                f"{owner} must contain exactly day, amount, and label"
            )
        day = _positive_day(entry["day"], f"{owner}.day")
        amount = _nonnegative_int(entry["amount"], f"{owner}.amount")
        label = entry["label"]
        if not isinstance(label, str) or not label.strip():
            raise CandidateInputError(f"{owner}.label must be a non-empty string")
        label = label.strip()
        if label in seen_labels:
            raise CandidateInputError(f"duplicate scheduled-cost label {label!r}")
        seen_labels.add(label)
        output.append(ScheduledCost(day=day, amount=amount, label=label))
    return tuple(sorted(output, key=lambda entry: (entry.day, entry.label)))


def normalize_anchor_spec(raw: dict[str, Any]) -> AnchorSpec:
    if not isinstance(raw, dict):
        raise CandidateInputError("candidate spec must be an object")
    allowed = {
        "starting_cash",
        "principal",
        "base_daily_upkeep",
        "upkeep_per_active_unit",
        "total_reactivation_cost",
        "activation_days",
        "room_service_spends",
    }
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise CandidateInputError(f"unknown candidate spec fields: {', '.join(unknown)}")
    defaults = default_anchor_spec()
    activation_raw = raw.get("activation_days", list(defaults.activation_days))
    if not isinstance(activation_raw, list):
        raise CandidateInputError("activation_days must be a list")
    activation_days = tuple(
        _positive_day(day, f"activation_days[{index}]")
        for index, day in enumerate(activation_raw)
    )
    if len(activation_days) != 4:
        raise CandidateInputError("activation_days must contain exactly four days")
    if tuple(sorted(set(activation_days))) != activation_days:
        raise CandidateInputError("activation_days must be unique and strictly increasing")
    return AnchorSpec(
        starting_cash=_nonnegative_int(
            raw.get("starting_cash", defaults.starting_cash), "starting_cash"
        ),
        principal=_nonnegative_int(raw.get("principal", defaults.principal), "principal"),
        base_daily_upkeep=_nonnegative_int(
            raw.get("base_daily_upkeep", defaults.base_daily_upkeep),
            "base_daily_upkeep",
        ),
        upkeep_per_active_unit=_nonnegative_int(
            raw.get("upkeep_per_active_unit", defaults.upkeep_per_active_unit),
            "upkeep_per_active_unit",
        ),
        total_reactivation_cost=_nonnegative_int(
            raw.get("total_reactivation_cost", defaults.total_reactivation_cost),
            "total_reactivation_cost",
        ),
        activation_days=activation_days,
        room_service_spends=_parse_scheduled_costs(
            raw.get("room_service_spends"), "room_service_spends"
        ),
    )


def anchor_parameters(spec: AnchorSpec) -> ParameterSet:
    return ParameterSet(
        starting_cash=spec.starting_cash,
        principal=spec.principal,
        base_daily_upkeep=spec.base_daily_upkeep,
        upkeep_per_active_unit=spec.upkeep_per_active_unit,
        total_reactivation_cost=spec.total_reactivation_cost,
    )


def _repeat_to_base_year(pattern: tuple[int, ...]) -> tuple[int, ...]:
    if not pattern:
        raise CandidateInputError("income pattern must not be empty")
    return tuple(
        pattern[index % len(pattern)] for index in range(frontier.BASE_YEAR_DAYS)
    )


def _rotate_pattern(pattern: tuple[int, ...], offset: int) -> tuple[int, ...]:
    if not pattern:
        raise CandidateInputError("income pattern must not be empty")
    normalized = offset % len(pattern)
    return pattern[normalized:] + pattern[:normalized]


def build_phase_rotated_traces(reference: dict[str, Any]) -> tuple[IncomeTrace, ...]:
    try:
        low_raw = reference["greedy_low_reference"]["daily_gross"]
        canonical_raw = reference["canonical_representative_reference"]["daily_gross"]
    except (KeyError, TypeError) as exc:
        raise CandidateInputError("audit reference is missing the two income paths") from exc
    if not isinstance(low_raw, list) or not isinstance(canonical_raw, list):
        raise CandidateInputError("audit income paths must be lists")
    low = tuple(_nonnegative_int(value, "greedy low income") for value in low_raw)
    canonical = tuple(
        _nonnegative_int(value, "canonical income") for value in canonical_raw
    )
    if len(low) != 5 or len(canonical) != 5:
        raise CandidateInputError("candidate boundary method requires two five-day paths")
    midpoint = tuple((left + right) // 2 for left, right in zip(low, canonical))
    sources = (
        ("GREEDY_LOW", "OBSERVED_REACHED_FIVE_DAY_PATH", low),
        ("MECHANICAL_MIDPOINT", "DERIVED_ELEMENTWISE_FLOOR_MIDPOINT", midpoint),
        ("CANONICAL", "OBSERVED_REACHED_FIVE_DAY_PATH", canonical),
    )
    traces: list[IncomeTrace] = []
    for source_band, source_kind, pattern in sources:
        for phase_offset in range(len(pattern)):
            rotated = _rotate_pattern(pattern, phase_offset)
            traces.append(
                IncomeTrace(
                    trace_id=f"{source_band}__PHASE_{phase_offset}",
                    source_band=source_band,
                    source_kind=source_kind,
                    phase_offset=phase_offset,
                    five_day_pattern=rotated,
                    daily_gross=_repeat_to_base_year(rotated),
                )
            )
    return tuple(traces)


def realize_target_curve(curve: dict[str, Any], principal: int) -> dict[str, int]:
    principal = _nonnegative_int(principal, "principal")
    shares = curve.get("shares")
    if not isinstance(shares, tuple) or len(shares) != len(frontier.CHAPTER_DAYS):
        raise CandidateInputError(f"target curve {curve.get('id')!r} has invalid shares")
    normalized_shares: list[tuple[int, int]] = []
    targets: dict[str, int] = {}
    prior = 0
    for day, share in zip(frontier.CHAPTER_DAYS, shares):
        if (
            not isinstance(share, tuple)
            or len(share) != 2
            or isinstance(share[0], bool)
            or isinstance(share[1], bool)
            or not isinstance(share[0], int)
            or not isinstance(share[1], int)
            or share[0] < 0
            or share[1] <= 0
            or share[0] > share[1]
        ):
            raise CandidateInputError(f"target curve {curve.get('id')!r} has invalid ratio")
        numerator, denominator = share
        if normalized_shares:
            prior_numerator, prior_denominator = normalized_shares[-1]
            if prior_numerator * denominator > numerator * prior_denominator:
                raise CandidateInputError(
                    f"target curve {curve.get('id')!r} ratios must be nondecreasing"
                )
        normalized_shares.append((numerator, denominator))
        amount = (principal * numerator + denominator - 1) // denominator
        if day == frontier.BASE_YEAR_DAYS:
            amount = principal
        if amount < prior or amount > principal:
            raise CandidateInputError(
                f"target curve {curve.get('id')!r} is not cumulative and bounded"
            )
        targets[str(day)] = amount
        prior = amount
    if normalized_shares[-1][0] != normalized_shares[-1][1]:
        raise CandidateInputError(
            f"target curve {curve.get('id')!r} final ratio must equal one"
        )
    if targets[str(frontier.BASE_YEAR_DAYS)] != principal:
        raise AssertionError("candidate target curve must end at the full principal")
    return targets


def allocate_integer_total(total: int, weights: tuple[int, ...]) -> tuple[int, ...]:
    total = _nonnegative_int(total, "allocation total")
    if not weights or any(
        isinstance(weight, bool) or not isinstance(weight, int) or weight <= 0
        for weight in weights
    ):
        raise CandidateInputError("allocation weights must be positive integers")
    denominator = sum(weights)
    allocated = [total * weight // denominator for weight in weights]
    remaining = total - sum(allocated)
    ranking = sorted(
        range(len(weights)),
        key=lambda index: (-(total * weights[index] % denominator), index),
    )
    for index in ranking[:remaining]:
        allocated[index] += 1
    if sum(allocated) != total:
        raise AssertionError("integer allocation must conserve its total")
    return tuple(allocated)


def validate_candidate_definitions(spec: AnchorSpec) -> None:
    curve_ids = [curve.get("id") for curve in TARGET_CURVES]
    if any(not isinstance(curve_id, str) or not curve_id for curve_id in curve_ids):
        raise CandidateInputError("every target curve must have a non-empty ID")
    if len(set(curve_ids)) != len(curve_ids):
        raise CandidateInputError("target curve IDs must be unique")
    for curve in TARGET_CURVES:
        # Principal zero alone would hide malformed ratios after rounding, so validate
        # the rational definition with a nonzero probe too.
        realize_target_curve(curve, 997)

    shape_ids = [shape.get("id") for shape in REACTIVATION_SHAPES]
    if any(not isinstance(shape_id, str) or not shape_id for shape_id in shape_ids):
        raise CandidateInputError("every reactivation shape must have a non-empty ID")
    if len(set(shape_ids)) != len(shape_ids):
        raise CandidateInputError("reactivation shape IDs must be unique")
    for shape in REACTIVATION_SHAPES:
        weights = shape.get("weights")
        if not isinstance(weights, tuple) or len(weights) != len(spec.activation_days):
            raise CandidateInputError(
                f"reactivation shape {shape.get('id')!r} must match activation_days"
            )
        # Largest-remainder allocation is not house-monotone in general. These exact
        # fixed shapes are admitted only after every event and every activation-prefix
        # is nondecreasing across a bounded adjacent-total probe.
        prior = allocate_integer_total(0, weights)
        for total in range(1, 2 * sum(weights) + 1):
            current = allocate_integer_total(total, weights)
            if any(current[index] < prior[index] for index in range(len(weights))):
                raise CandidateInputError(
                    f"reactivation shape {shape.get('id')!r} is not event-monotone"
                )
            for prefix_end in range(1, len(weights) + 1):
                if sum(current[:prefix_end]) < sum(prior[:prefix_end]):
                    raise CandidateInputError(
                        f"reactivation shape {shape.get('id')!r} is not prefix-monotone"
                    )
            prior = current

    axis_ids = [axis.get("id") for axis in BOUNDARY_AXES]
    if len(set(axis_ids)) != len(axis_ids):
        raise CandidateInputError("boundary axis IDs must be unique")


def active_unit_counts(spec: AnchorSpec) -> tuple[int, ...]:
    return tuple(
        sum(1 for activation_day in spec.activation_days if activation_day <= day)
        for day in range(1, frontier.BASE_YEAR_DAYS + 1)
    )


def upkeep_schedule(spec: AnchorSpec, parameters: ParameterSet) -> tuple[int, ...]:
    return tuple(
        parameters.base_daily_upkeep
        + parameters.upkeep_per_active_unit * active_count
        for active_count in active_unit_counts(spec)
    )


def reactivation_events(
    spec: AnchorSpec,
    parameters: ParameterSet,
    shape: dict[str, Any],
) -> tuple[ScheduledCost, ...]:
    weights = shape.get("weights")
    if not isinstance(weights, tuple) or len(weights) != len(spec.activation_days):
        raise CandidateInputError(f"reactivation shape {shape.get('id')!r} is invalid")
    amounts = allocate_integer_total(parameters.total_reactivation_cost, weights)
    return tuple(
        ScheduledCost(day=day, amount=amount, label=f"ABSTRACT_ACTIVATION_{index}")
        for index, (day, amount) in enumerate(
            zip(spec.activation_days, amounts), start=1
        )
    )


def _scheduled_cost_json(costs: Iterable[ScheduledCost]) -> list[dict[str, Any]]:
    return [
        {"day": cost.day, "amount": cost.amount, "label": cost.label}
        for cost in costs
    ]


def _parameter_json(parameters: ParameterSet) -> dict[str, int]:
    return {
        "starting_cash": parameters.starting_cash,
        "principal": parameters.principal,
        "base_daily_upkeep": parameters.base_daily_upkeep,
        "upkeep_per_active_unit": parameters.upkeep_per_active_unit,
        "total_reactivation_cost": parameters.total_reactivation_cost,
    }


def _curve_by_id(curve_id: str) -> dict[str, Any]:
    for curve in TARGET_CURVES:
        if curve["id"] == curve_id:
            return curve
    raise CandidateInputError(f"unknown target curve {curve_id!r}")


def _shape_by_id(shape_id: str) -> dict[str, Any]:
    for shape in REACTIVATION_SHAPES:
        if shape["id"] == shape_id:
            return shape
    raise CandidateInputError(f"unknown reactivation shape {shape_id!r}")


def _terminal_projection(result: dict[str, Any]) -> dict[str, Any]:
    whole = result["whole_sequence_totals"]
    deadline = result["base_year_deadline"]
    rejection = result["analysis_rejection"]
    terminal_status = whole["terminal_status"]
    terminal_day: int | None
    terminal_shortfall_amount: int | None = None
    if rejection is not None:
        terminal_class = "PREPARATION_PLAN_UNEXECUTABLE"
        terminal_day = rejection["day"]
        terminal_shortfall_amount = rejection["shortfall_amount"]
    elif terminal_status == "OPERATING_CASH_SHORTFALL":
        terminal_class = "OPERATING_CASH_SHORTFALL"
        failure = result["runtime_terminal_state"]["operating_failure"]
        terminal_day = failure["stageNumber"] if failure is not None else None
        terminal_shortfall_amount = (
            failure.get("shortfallAmount") if failure is not None else None
        )
    elif terminal_status == "CHAPTER_HURDLE_MISSED":
        terminal_class = "CHAPTER_HURDLE_MISSED"
        missed = next(
            (
                checkpoint
                for checkpoint in result["chapter_hurdles"]
                if checkpoint["status"] == "MISSED"
            ),
            None,
        )
        terminal_day = missed["day"] if missed is not None else None
        if terminal_day not in frontier.CHAPTER_DAYS[:-1]:
            raise AssertionError("chapter-hurdle terminal did not identify a base checkpoint")
        terminal_shortfall_amount = missed["gap"]
    elif terminal_status == "DEBT_DEADLINE_MISSED":
        terminal_class = "DEBT_DEADLINE_MISSED"
        terminal_day = frontier.BASE_YEAR_DAYS
        terminal_shortfall_amount = whole["remaining_principal"]
    elif terminal_status == "COMPLETE":
        complete_invariants = (
            result["path_executable"] is True
            and deadline["observed"] is True
            and deadline["qualified"] is True
            and result["all_chapter_minimums_reached"] is True
            and whole["days"] == frontier.BASE_YEAR_DAYS
            and whole["remaining_principal"] == 0
            and whole["pending_preparation_expense"] == 0
        )
        if not complete_invariants:
            raise AssertionError("runtime COMPLETE state violated candidate success invariants")
        terminal_class = "REACHED_DAY_56_DEBT_ZERO"
        terminal_day = frontier.BASE_YEAR_DAYS
    else:
        raise AssertionError(
            f"candidate classifier does not recognize runtime terminal {terminal_status!r}"
        )

    day_56_observed = deadline["observed"] is True
    completed = terminal_class == "REACHED_DAY_56_DEBT_ZERO"
    return {
        "balance_verdict": BALANCE_VERDICT,
        "completed_structural_witness": completed,
        "path_executable": result["path_executable"],
        "terminal_class": terminal_class,
        "terminal_runtime_status": terminal_status,
        "terminal_day": terminal_day,
        "terminal_shortfall_amount": terminal_shortfall_amount,
        "observed_through_day": whole["days"],
        "completed_days": whole["days"],
        "attempted_operation_count": whole["attempted_operation_count"],
        "day_56_observed": day_56_observed,
        "day_56_remaining_debt": (
            deadline["remaining_principal"] if day_56_observed else None
        ),
        "day_56_cash": deadline["cash"] if day_56_observed else None,
        "terminal_remaining_debt": whole["remaining_principal"],
        "chapter_statuses": {
            str(checkpoint["day"]): checkpoint["status"]
            for checkpoint in result["chapter_hurdles"]
        },
        "cash_metrics": {
            "minimum_live_cash": whole["minimum_live_cash"],
            "minimum_finance_cash": whole["minimum_finance_cash"],
            "terminal_live_cash": whole["terminal_live_cash"],
            "terminal_finance_cash": whole["closing_finance_cash"],
            "terminal_pending_preparation": whole["pending_preparation_expense"],
        },
        "executed_prefix": {
            "gross": whole["gross"],
            "upkeep": whole["upkeep"],
            "reactivation": whole["reactivation"],
            "room_service": whole["room_service"],
            "repayment": whole["repayment"],
        },
        "analysis_rejection": copy.deepcopy(rejection),
        "conservation_delta": result["conservation_check"]["delta"],
    }


def _assert_runtime_result_contract(result: dict[str, Any]) -> None:
    expected = {
        "runtime_conformance": True,
        "runtime_conformance_scope": frontier.RUNTIME_CONFORMANCE_SCOPE,
        "runtime_conformance_excludes": frontier.RUNTIME_CONFORMANCE_EXCLUDES,
        "full_game_controller_conformance_claimed": False,
        "balance_verdict": BALANCE_VERDICT,
        "policy_id": PRIMARY_POLICY,
    }
    for key, value in expected.items():
        if result.get(key) != value:
            raise AssertionError(
                f"candidate analyzer contract drifted at {key}: "
                f"expected {value!r}, got {result.get(key)!r}"
            )


class EvaluationEngine:
    def __init__(
        self,
        spec: AnchorSpec,
        traces: tuple[IncomeTrace, ...],
        *,
        max_simulations: int,
    ) -> None:
        if max_simulations <= 0:
            raise CandidateInputError("max_simulations must be positive")
        self.spec = spec
        self.traces = {trace.trace_id: trace for trace in traces}
        self.max_simulations = max_simulations
        self.simulation_count = 0
        self._cache: dict[tuple[Any, ...], dict[str, Any]] = {}

    def evaluate(
        self,
        trace_id: str,
        curve_id: str,
        shape_id: str,
        parameters: ParameterSet,
    ) -> dict[str, Any]:
        trace = self.traces.get(trace_id)
        if trace is None:
            raise CandidateInputError(f"unknown income trace {trace_id!r}")
        curve = _curve_by_id(curve_id)
        shape = _shape_by_id(shape_id)
        key = (
            trace_id,
            curve_id,
            shape_id,
            parameters.starting_cash,
            parameters.principal,
            parameters.base_daily_upkeep,
            parameters.upkeep_per_active_unit,
            parameters.total_reactivation_cost,
        )
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        if self.simulation_count >= self.max_simulations:
            raise SimulationLimitError(
                f"candidate run would exceed --max-simulations {self.max_simulations}"
            )
        upkeep = upkeep_schedule(self.spec, parameters)
        reactivation = reactivation_events(self.spec, parameters, shape)
        scenario_id = (
            f"BOUNDARY__{trace_id}__{curve_id}__{shape_id}"
            f"__SC{parameters.starting_cash}__P{parameters.principal}"
            f"__BU{parameters.base_daily_upkeep}"
            f"__UU{parameters.upkeep_per_active_unit}"
            f"__R{parameters.total_reactivation_cost}"
        )
        raw = {
            "scenario_id": scenario_id,
            "starting_cash": parameters.starting_cash,
            "principal": parameters.principal,
            "daily_gross_sequence": list(trace.daily_gross),
            "per_day_upkeep_schedule": list(upkeep),
            "reactivation_spends": _scheduled_cost_json(reactivation),
            "room_service_spends": _scheduled_cost_json(
                self.spec.room_service_spends
            ),
            "chapter_cumulative_targets": realize_target_curve(
                curve, parameters.principal
            ),
            "manual_extra_repayments": [],
        }
        result = frontier.simulate_policy(
            frontier.normalize_config(raw), PRIMARY_POLICY, include_ledger=False
        )
        _assert_runtime_result_contract(result)
        outcome = {
            "trace_id": trace_id,
            "target_curve_id": curve_id,
            "reactivation_shape_id": shape_id,
            "parameters": _parameter_json(parameters),
            "realized_chapter_targets": raw["chapter_cumulative_targets"],
            "resolved_total_upkeep": sum(upkeep),
            "resolved_reactivation_events": raw["reactivation_spends"],
            "resolved_room_service_events": raw["room_service_spends"],
            **_terminal_projection(result),
        }
        if outcome["conservation_delta"] != 0:
            raise AssertionError("candidate runtime result violated cash conservation")
        cash = outcome["cash_metrics"]
        if (
            cash["terminal_live_cash"] + cash["terminal_pending_preparation"]
            != cash["terminal_finance_cash"]
        ):
            raise AssertionError("candidate terminal live/finance cash identity failed")
        self.simulation_count += 1
        self._cache[key] = outcome
        return outcome


def _replace_axis(parameters: ParameterSet, axis_id: str, value: int) -> ParameterSet:
    value = _nonnegative_int(value, axis_id)
    if axis_id not in {
        "starting_cash",
        "principal",
        "base_daily_upkeep",
        "upkeep_per_active_unit",
        "total_reactivation_cost",
    }:
        raise CandidateInputError(f"unknown boundary axis {axis_id!r}")
    return replace(parameters, **{axis_id: value})


def _is_complete(outcome: dict[str, Any]) -> bool:
    return outcome["completed_structural_witness"] is True


def _witness(relation: str, value: int, outcome: dict[str, Any]) -> dict[str, Any]:
    return {
        "relation": relation,
        "value": value,
        "completed_structural_witness": outcome["completed_structural_witness"],
        "terminal_class": outcome["terminal_class"],
        "terminal_runtime_status": outcome["terminal_runtime_status"],
        "terminal_day": outcome["terminal_day"],
        "terminal_shortfall_amount": outcome["terminal_shortfall_amount"],
        "completed_days": outcome["completed_days"],
        "attempted_operation_count": outcome["attempted_operation_count"],
        "day_56_observed": outcome["day_56_observed"],
        "day_56_remaining_debt": outcome["day_56_remaining_debt"],
        "terminal_remaining_debt": outcome["terminal_remaining_debt"],
        "minimum_live_cash": outcome["cash_metrics"]["minimum_live_cash"],
        "minimum_finance_cash": outcome["cash_metrics"]["minimum_finance_cash"],
        "terminal_live_cash": outcome["cash_metrics"]["terminal_live_cash"],
        "terminal_finance_cash": outcome["cash_metrics"]["terminal_finance_cash"],
        "terminal_pending_preparation": outcome["cash_metrics"][
            "terminal_pending_preparation"
        ],
        "conservation_delta": outcome["conservation_delta"],
        "balance_verdict": BALANCE_VERDICT,
    }


def find_minimum_boundary(
    evaluate_value: Callable[[int], dict[str, Any]],
    *,
    proven_feasible_upper: int,
) -> dict[str, Any]:
    upper = _nonnegative_int(proven_feasible_upper, "proven_feasible_upper")
    at_zero = evaluate_value(0)
    if _is_complete(at_zero):
        at_one = evaluate_value(1)
        return {
            "boundary_status": "DOMAIN_MINIMUM_IS_FEASIBLE",
            "boundary_value": 0,
            "search_domain": {"minimum": 0, "proven_feasible_upper": upper},
            "witnesses": [
                _witness("AT_BOUNDARY", 0, at_zero),
                _witness("ABOVE_BOUNDARY", 1, at_one),
            ],
        }
    at_upper = evaluate_value(upper)
    if not _is_complete(at_upper):
        raise AssertionError("declared minimum-boundary upper witness was not feasible")
    low = 0
    high = upper
    while high - low > 1:
        midpoint = (low + high) // 2
        if _is_complete(evaluate_value(midpoint)):
            high = midpoint
        else:
            low = midpoint
    below = evaluate_value(high - 1)
    at_boundary = evaluate_value(high)
    above = evaluate_value(high + 1)
    if _is_complete(below) or not _is_complete(at_boundary) or not _is_complete(above):
        raise AssertionError("minimum boundary adjacency verification failed")
    return {
        "boundary_status": "ADJACENT_INTEGER_BOUNDARY",
        "boundary_value": high,
        "search_domain": {"minimum": 0, "proven_feasible_upper": upper},
        "witnesses": [
            _witness("BELOW_BOUNDARY", high - 1, below),
            _witness("AT_BOUNDARY", high, at_boundary),
            _witness("ABOVE_BOUNDARY", high + 1, above),
        ],
    }


def find_maximum_boundary(
    evaluate_value: Callable[[int], dict[str, Any]],
    *,
    proven_infeasible_upper: int,
) -> dict[str, Any]:
    upper = _nonnegative_int(proven_infeasible_upper, "proven_infeasible_upper")
    if upper < 1:
        raise CandidateInputError("maximum-boundary upper witness must be at least 1")
    at_zero = evaluate_value(0)
    if not _is_complete(at_zero):
        return {
            "boundary_status": "NO_FEASIBLE_NONNEGATIVE_VALUE_WITH_HELD_ANCHORS",
            "boundary_value": None,
            "search_domain": {"minimum": 0, "proven_infeasible_upper": upper},
            "witnesses": [_witness("DOMAIN_MINIMUM", 0, at_zero)],
        }
    at_upper = evaluate_value(upper)
    if _is_complete(at_upper):
        raise AssertionError("declared maximum-boundary upper witness was still feasible")
    low = 0
    high = upper
    while high - low > 1:
        midpoint = (low + high) // 2
        if _is_complete(evaluate_value(midpoint)):
            low = midpoint
        else:
            high = midpoint
    below_value = max(0, low - 1)
    below = evaluate_value(below_value)
    at_boundary = evaluate_value(low)
    above = evaluate_value(low + 1)
    if not _is_complete(below) or not _is_complete(at_boundary) or _is_complete(above):
        raise AssertionError("maximum boundary adjacency verification failed")
    witnesses = []
    if below_value != low:
        witnesses.append(_witness("BELOW_BOUNDARY", below_value, below))
    witnesses.extend(
        (
            _witness("AT_BOUNDARY", low, at_boundary),
            _witness("ABOVE_BOUNDARY", low + 1, above),
        )
    )
    return {
        "boundary_status": (
            "DOMAIN_MINIMUM_IS_MAXIMUM_FEASIBLE"
            if low == 0
            else "ADJACENT_INTEGER_BOUNDARY"
        ),
        "boundary_value": low,
        "search_domain": {"minimum": 0, "proven_infeasible_upper": upper},
        "witnesses": witnesses,
    }


def _room_service_total(spec: AnchorSpec) -> int:
    return sum(cost.amount for cost in spec.room_service_spends)


def _proven_axis_upper(
    axis_id: str,
    spec: AnchorSpec,
    trace: IncomeTrace,
    parameters: ParameterSet,
) -> int:
    gross_total = sum(trace.daily_gross)
    room_total = _room_service_total(spec)
    active_weight = sum(active_unit_counts(spec))
    resolved_upkeep = sum(upkeep_schedule(spec, parameters))
    if axis_id == "starting_cash":
        # This amount can pay every debt/cost even if all gross income is ignored.
        return (
            parameters.principal
            + resolved_upkeep
            + parameters.total_reactivation_cost
            + room_total
        )
    if axis_id == "principal":
        available = (
            parameters.starting_cash
            + gross_total
            - resolved_upkeep
            - parameters.total_reactivation_cost
            - room_total
        )
        return max(0, available) + 1
    if axis_id == "base_daily_upkeep":
        available = (
            parameters.starting_cash
            + gross_total
            - parameters.principal
            - parameters.total_reactivation_cost
            - room_total
            - parameters.upkeep_per_active_unit * active_weight
        )
        return max(0, available // frontier.BASE_YEAR_DAYS) + 1
    if axis_id == "upkeep_per_active_unit":
        if active_weight <= 0:
            raise AssertionError("candidate activation schedule must contain active-unit days")
        available = (
            parameters.starting_cash
            + gross_total
            - parameters.principal
            - parameters.total_reactivation_cost
            - room_total
            - parameters.base_daily_upkeep * frontier.BASE_YEAR_DAYS
        )
        return max(0, available // active_weight) + 1
    if axis_id == "total_reactivation_cost":
        available = (
            parameters.starting_cash
            + gross_total
            - parameters.principal
            - resolved_upkeep
            - room_total
        )
        return max(0, available) + 1
    raise CandidateInputError(f"unknown boundary axis {axis_id!r}")


def _make_boundary_observation(
    boundary_id: str,
    engine: EvaluationEngine,
    trace: IncomeTrace,
    curve: dict[str, Any],
    shape: dict[str, Any],
    axis: dict[str, str],
    anchor: ParameterSet,
) -> dict[str, Any]:
    axis_id = axis["id"]

    def evaluate_value(value: int) -> dict[str, Any]:
        return engine.evaluate(
            trace.trace_id,
            curve["id"],
            shape["id"],
            _replace_axis(anchor, axis_id, value),
        )

    upper = _proven_axis_upper(axis_id, engine.spec, trace, anchor)
    if upper > frontier.MAX_SAFE_INTEGER:
        raise CandidateInputError(
            f"{axis_id} proof bound exceeds the JavaScript safe-integer input domain"
        )
    if axis["direction"] == "MINIMUM_FEASIBLE":
        boundary = find_minimum_boundary(
            evaluate_value, proven_feasible_upper=upper
        )
    else:
        boundary = find_maximum_boundary(
            evaluate_value, proven_infeasible_upper=upper
        )
    held = _parameter_json(anchor)
    held.pop(axis_id)
    witnesses = []
    proven_upper = max(boundary["search_domain"].values())
    for ordinal, witness in enumerate(boundary["witnesses"], start=1):
        witnesses.append(
            {
                "witness_id": f"{boundary_id}:W{ordinal}",
                "outside_proven_search_interval": witness["value"] > proven_upper,
                **witness,
            }
        )
    return {
        "boundary_id": boundary_id,
        "axis_id": axis_id,
        "direction": axis["direction"],
        "monotonic_contract": axis["monotonic_contract"],
        "trace_id": trace.trace_id,
        "source_band": trace.source_band,
        "phase_offset": trace.phase_offset,
        "target_curve_id": curve["id"],
        "reactivation_shape_id": shape["id"],
        "held_anchor_parameters": held,
        "boundary_status": boundary["boundary_status"],
        "boundary_value": boundary["boundary_value"],
        "search_domain": boundary["search_domain"],
        "upper_witness_basis": {
            "starting_cash": (
                "principal plus all resolved upkeep, reactivation, and room-service costs; "
                "this remains sufficient even if gross income is ignored"
            ),
            "principal": (
                "one above total opening cash plus gross minus held non-debt outflows"
            ),
            "base_daily_upkeep": (
                "one above the conservation-limited quotient across 56 base-year days"
            ),
            "upkeep_per_active_unit": (
                "one above the conservation-limited quotient across active-unit days"
            ),
            "total_reactivation_cost": (
                "one above total opening cash plus gross minus held debt and other outflows"
            ),
        }[axis_id],
        "witnesses": witnesses,
        "balance_verdict": BALANCE_VERDICT,
    }


def _terminal_counts(outcomes: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for outcome in outcomes:
        terminal_class = outcome["terminal_class"]
        counts[terminal_class] = counts.get(terminal_class, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def _anchor_observation_groups(
    engine: EvaluationEngine,
    traces: tuple[IncomeTrace, ...],
    anchor: ParameterSet,
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for curve in TARGET_CURVES:
        for shape in REACTIVATION_SHAPES:
            outcomes = [
                engine.evaluate(trace.trace_id, curve["id"], shape["id"], anchor)
                for trace in traces
            ]
            source_bands: dict[str, Any] = {}
            for source_band in ("GREEDY_LOW", "MECHANICAL_MIDPOINT", "CANONICAL"):
                selected = [
                    outcome
                    for outcome in outcomes
                    if engine.traces[outcome["trace_id"]].source_band == source_band
                ]
                source_bands[source_band] = {
                    "trace_count": len(selected),
                    "completed_trace_count": sum(
                        1 for outcome in selected if _is_complete(outcome)
                    ),
                    "terminal_class_counts": _terminal_counts(selected),
                }
            groups.append(
                {
                    "target_curve_id": curve["id"],
                    "reactivation_shape_id": shape["id"],
                    "trace_count": len(outcomes),
                    "completed_trace_count": sum(
                        1 for outcome in outcomes if _is_complete(outcome)
                    ),
                    "terminal_class_counts": _terminal_counts(outcomes),
                    "source_band_observations": source_bands,
                    "probability_interpretation_allowed": False,
                    "balance_verdict": BALANCE_VERDICT,
                }
            )
    return groups


def _boundary_groups(
    observations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for observation in observations:
        key = (
            observation["axis_id"],
            observation["target_curve_id"],
            observation["reactivation_shape_id"],
            observation["source_band"],
        )
        grouped.setdefault(key, []).append(observation)
    output: list[dict[str, Any]] = []
    for key, rows in grouped.items():
        axis_id, curve_id, shape_id, source_band = key
        rows = sorted(rows, key=lambda row: row["phase_offset"])
        values = [
            row["boundary_value"]
            for row in rows
            if row["boundary_value"] is not None
        ]
        all_phases_have_value = len(values) == len(rows)
        direction = rows[0]["direction"]
        if not all_phases_have_value:
            all_phase_envelope = None
        elif direction == "MINIMUM_FEASIBLE":
            all_phase_envelope = max(values)
        else:
            all_phase_envelope = min(values)
        output.append(
            {
                "axis_id": axis_id,
                "direction": direction,
                "target_curve_id": curve_id,
                "reactivation_shape_id": shape_id,
                "source_band": source_band,
                "phase_rotation_count": len(rows),
                "phase_boundaries": [
                    {
                        "phase_offset": row["phase_offset"],
                        "boundary_id": row["boundary_id"],
                        "boundary_status": row["boundary_status"],
                        "boundary_value": row["boundary_value"],
                    }
                    for row in rows
                ],
                "observed_boundary_minimum": min(values) if values else None,
                "observed_boundary_maximum": max(values) if values else None,
                "all_phase_feasible_envelope": all_phase_envelope,
                "controlling_boundary_ids": (
                    [
                        row["boundary_id"]
                        for row in rows
                        if row["boundary_value"] == all_phase_envelope
                    ]
                    if all_phase_envelope is not None
                    else []
                ),
                "all_phases_have_boundary_value": all_phases_have_value,
                "probability_interpretation_allowed": False,
                "balance_verdict": BALANCE_VERDICT,
            }
        )
    return output


def _overall_axis_spans(
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for axis in BOUNDARY_AXES:
        rows = [row for row in observations if row["axis_id"] == axis["id"]]
        values = [
            row["boundary_value"]
            for row in rows
            if row["boundary_value"] is not None
        ]
        output[axis["id"]] = {
            "direction": axis["direction"],
            "observation_count": len(rows),
            "boundary_value_count": len(values),
            "observed_boundary_minimum": min(values) if values else None,
            "observed_boundary_maximum": max(values) if values else None,
            "joint_feasible_region_claimed": False,
            "balance_verdict": BALANCE_VERDICT,
        }
    return output


def _trace_json(trace: IncomeTrace) -> dict[str, Any]:
    return {
        "trace_id": trace.trace_id,
        "source_band": trace.source_band,
        "source_kind": trace.source_kind,
        "phase_offset": trace.phase_offset,
        "five_day_pattern_after_rotation": list(trace.five_day_pattern),
        "daily_gross_56": list(trace.daily_gross),
        "gross_total_56": sum(trace.daily_gross),
        "construction": (
            "ROTATE_FIVE_DAY_PATTERN_THEN_REPEAT_AND_TRUNCATE_TO_56; "
            "THE_RESIDUAL_DAY_CHANGES_TOTAL_GROSS_BY_PHASE"
        ),
        "probability_weight": None,
    }


def _target_curve_json(curve: dict[str, Any], principal: int) -> dict[str, Any]:
    return {
        "id": curve["id"],
        "description": curve["description"],
        "shares": [
            {"numerator": numerator, "denominator": denominator}
            for numerator, denominator in curve["shares"]
        ],
        "rounding_id": TARGET_ROUNDING_ID,
        "anchor_realized_targets": realize_target_curve(curve, principal),
        "balance_verdict": BALANCE_VERDICT,
    }


def _shape_json(
    shape: dict[str, Any], spec: AnchorSpec, anchor: ParameterSet
) -> dict[str, Any]:
    return {
        "id": shape["id"],
        "description": shape["description"],
        "weights": list(shape["weights"]),
        "allocation_id": REACTIVATION_ALLOCATION_ID,
        "anchor_realized_events": _scheduled_cost_json(
            reactivation_events(spec, anchor, shape)
        ),
        "balance_verdict": BALANCE_VERDICT,
    }


def _spec_json(spec: AnchorSpec, anchor: ParameterSet) -> dict[str, Any]:
    counts = active_unit_counts(spec)
    return {
        "assumption_status": "ILLUSTRATIVE_ONLY",
        "parameters": _parameter_json(anchor),
        "activation_days": list(spec.activation_days),
        "activation_timing": (
            "PREPAID_BEFORE_OPERATION_AND_COUNTED_FROM_THE_SAME_ACTIVATION_DAY"
        ),
        "active_unit_count_by_day": list(counts),
        "active_unit_day_weight": sum(counts),
        "active_unit_semantics": "ABSTRACT_OWNED_UPGRADE_UNIT_PENDING_USER_MODEL_DECISION",
        "zero_cost_condition": (
            "A total reactivation cost of zero still activates four abstract units; this axis "
            "observes conditional price sensitivity, not upgrade eligibility."
        ),
        "room_service_spends": _scheduled_cost_json(spec.room_service_spends),
        "room_service_boundary_axis_included": False,
        "room_service_exclusion_reason": (
            "No production usage/demand model is settled; configured spends remain held inputs."
        ),
        "joint_bundle_selected": False,
        "balance_verdict": BALANCE_VERDICT,
    }


def assert_provisional_boundary(report: dict[str, Any]) -> None:
    if report.get("contract_status") != "PROVISIONAL":
        raise AssertionError("candidate report contract_status must remain PROVISIONAL")
    if report.get("balance_verdict") != "NOT_EVALUATED":
        raise AssertionError("candidate report cannot declare a balance verdict")
    if report.get("exact_values_selected") is not False:
        raise AssertionError("candidate report cannot select exact economy values")
    if report.get("selection_authority") != "USER":
        raise AssertionError("candidate report must preserve user selection authority")
    if report.get("runtime_conformance") is not True:
        raise AssertionError("candidate report lost runtime conformance evidence")
    if report.get("runtime_conformance_scope") != frontier.RUNTIME_CONFORMANCE_SCOPE:
        raise AssertionError("candidate report runtime conformance scope drifted")
    if report.get("runtime_conformance_excludes") != frontier.RUNTIME_CONFORMANCE_EXCLUDES:
        raise AssertionError("candidate report runtime conformance exclusions drifted")
    if report.get("full_game_controller_conformance_claimed") is not False:
        raise AssertionError("candidate report cannot claim full controller conformance")
    primary = report.get("primary_policy")
    if not isinstance(primary, dict) or primary.get("id") != PRIMARY_POLICY:
        raise AssertionError("candidate boundaries must use the fixed primary policy")
    if primary.get("manual_extra_repayments") != []:
        raise AssertionError("candidate boundaries must disable scheduled extra repayment")
    source = report.get("source_evidence", {}).get("audit_income_reference", {})
    if source.get("not_a_56_day_distribution") is not True:
        raise AssertionError("candidate report lost the five-day audit evidence boundary")
    source_path = source.get("path")
    if source_path is not None:
        if not isinstance(source_path, str) or not source_path:
            raise AssertionError("candidate report audit source path must be a string")
        if (
            "\\" in source_path
            or Path(source_path).is_absolute()
            or (len(source_path) >= 2 and source_path[1] == ":")
        ):
            raise AssertionError("candidate report cannot contain an absolute audit path")
        if source.get("path_kind") not in {
            "REPOSITORY_RELATIVE_POSIX",
            "BASENAME_ONLY_EXTERNAL_SOURCE",
        }:
            raise AssertionError("candidate report audit source path kind is missing")
    source_sha256 = report.get("source_evidence", {}).get("audit_source_sha256")
    if source_sha256 is not None and (
        not isinstance(source_sha256, str)
        or len(source_sha256) != 64
        or any(character not in "0123456789abcdef" for character in source_sha256)
    ):
        raise AssertionError("candidate report audit source sha256 is invalid")

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                lowered = key.lower()
                if lowered.replace("_", "") in NORMALIZED_BANNED_REPORT_KEYS:
                    raise AssertionError(f"candidate report contains banned key {path}.{key}")
                if lowered in {"balance_verdict", "balanceverdict"}:
                    if nested != "NOT_EVALUATED":
                        raise AssertionError(
                            f"candidate report contains non-provisional verdict at {path}.{key}"
                        )
                walk(nested, f"{path}.{key}")
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                walk(nested, f"{path}[{index}]")

    walk(report, "report")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable_audit_reference(
    reference: dict[str, Any], source_path: Path | None
) -> tuple[dict[str, Any], str | None]:
    portable = copy.deepcopy(reference)
    if source_path is None:
        raw_path = portable.pop("path", None)
        if raw_path is None:
            return portable, None
        source_path = Path(raw_path)
    resolved = source_path.resolve()
    if not resolved.is_file():
        raise CandidateInputError(f"audit source does not exist: {resolved}")
    repository_root = frontier.REPOSITORY_ROOT.resolve()
    try:
        relative = resolved.relative_to(repository_root)
    except ValueError:
        portable["path"] = resolved.name
        portable["path_kind"] = "BASENAME_ONLY_EXTERNAL_SOURCE"
        portable["path_redacted"] = True
    else:
        portable["path"] = relative.as_posix()
        portable["path_kind"] = "REPOSITORY_RELATIVE_POSIX"
        portable.pop("path_redacted", None)
    return portable, _sha256_file(resolved)


def make_candidate_range_report(
    reference: dict[str, Any],
    spec: AnchorSpec,
    *,
    source_path: Path | None = None,
    max_simulations: int = DEFAULT_MAX_SIMULATIONS,
    progress_stream: Any | None = None,
) -> dict[str, Any]:
    validate_candidate_definitions(spec)
    traces = build_phase_rotated_traces(reference)
    portable_reference, audit_source_sha256 = _portable_audit_reference(
        reference, source_path
    )
    anchor = anchor_parameters(spec)
    engine = EvaluationEngine(spec, traces, max_simulations=max_simulations)
    observations: list[dict[str, Any]] = []
    structure_count = len(traces) * len(TARGET_CURVES) * len(REACTIVATION_SHAPES)
    completed_structures = 0
    for curve in TARGET_CURVES:
        for shape in REACTIVATION_SHAPES:
            for trace in traces:
                for axis in BOUNDARY_AXES:
                    boundary_id = f"B{len(observations) + 1:04d}"
                    observations.append(
                        _make_boundary_observation(
                            boundary_id,
                            engine,
                            trace,
                            curve,
                            shape,
                            axis,
                            anchor,
                        )
                    )
                completed_structures += 1
                if progress_stream is not None:
                    print(
                        "candidate-boundary progress "
                        f"structures={completed_structures}/{structure_count} "
                        f"simulations={engine.simulation_count}",
                        file=progress_stream,
                        flush=True,
                    )
    anchor_groups = _anchor_observation_groups(engine, traces, anchor)
    groups = _boundary_groups(observations)
    report = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "status": REPORT_STATUS,
        "contract_status": CONTRACT_STATUS,
        "balance_verdict": BALANCE_VERDICT,
        "exact_values_selected": False,
        "selection_authority": "USER",
        "runtime_conformance": True,
        "runtime_conformance_scope": frontier.RUNTIME_CONFORMANCE_SCOPE,
        "runtime_conformance_excludes": frontier.RUNTIME_CONFORMANCE_EXCLUDES,
        "full_game_controller_conformance_claimed": False,
        "primary_policy": {
            "id": PRIMARY_POLICY,
            "role": "STRUCTURAL_REACHABILITY_WITNESS",
            "manual_extra_repayments": [],
            "claim": (
                "At each checkpoint, explicitly submit only the current cumulative gap; "
                "submit zero on non-checkpoint days."
            ),
            "automatic_game_debit_claimed": False,
        },
        "comparison_policies": {
            "evaluated_in_this_report": False,
            "available_ids": [
                frontier.POLICY_DAILY_AUTO,
                frontier.POLICY_FINAL_LUMP,
            ],
            "exclusion_reason": (
                "Strategy sensitivity must not be mixed into the structural boundary search."
            ),
        },
        "source_evidence": {
            "audit_income_reference": portable_reference,
            "audit_source_sha256": audit_source_sha256,
            "income_trace_status": TRACE_STATUS,
            "python_js_conformance_not_reexecuted_per_candidate": True,
            "candidate_engine": "analyze_campaign_economy_frontier.simulate_policy",
        },
        "sampling_contract": {
            "trace_count": len(traces),
            "source_band_count": 3,
            "phase_rotation_count_per_band": 5,
            "probability_weights": None,
            "boundary_refinement": "INTEGER_ADJACENCY",
            "one_axis_at_a_time": True,
            "joint_feasible_region_claimed": False,
        },
        "trace_definitions": [_trace_json(trace) for trace in traces],
        "target_curve_definitions": [
            _target_curve_json(curve, anchor.principal) for curve in TARGET_CURVES
        ],
        "reactivation_shape_definitions": [
            _shape_json(shape, spec, anchor) for shape in REACTIVATION_SHAPES
        ],
        "anchor": _spec_json(spec, anchor),
        "boundary_axis_definitions": [dict(axis) for axis in BOUNDARY_AXES],
        "execution": {
            "structure_count": structure_count,
            "boundary_observation_count": len(observations),
            "boundary_group_count": len(groups),
            "unique_runtime_simulation_count": engine.simulation_count,
            "unique_runtime_simulation_count_evidence": SIMULATION_COUNT_EVIDENCE,
            "max_simulations": max_simulations,
            "cache_reuse_count_not_reported_as_simulation": True,
        },
        "anchor_observation_groups": anchor_groups,
        "boundary_observations": observations,
        "boundary_groups": groups,
        "parameter_range_evidence": _overall_axis_spans(observations),
        "decision_packet": {
            "user_gate": "MODEL_DECISION_REQUIRED",
            "linked_numeric_bundles_generated": False,
            "numeric_bundle_selection_ready": False,
            "exact_numeric_values_selected": False,
            "boundary_group_count": len(groups),
            "unresolved_model_decisions": [
                {
                    "id": "ACTIVE_UNIT_SEMANTICS",
                    "question": (
                        "Keep one shared owned-upgrade upkeep unit, or separate room and facility upkeep?"
                    ),
                    "current_analysis_assumption": "ONE_ABSTRACT_OWNED_UPGRADE_UNIT",
                    "recommended_provisional_choice": "KEEP_ONE_SHARED_UNIT_FOR_FIRST_LINKED_BUNDLES",
                    "recommendation_reason": (
                        "It matches the current runtime model and avoids inventing type counts before "
                        "production room/facility content exists. Split coefficients remain a later axis."
                    ),
                },
            ],
            "deferred_input_policies": [
                {
                    "id": "ROOM_SERVICE_USAGE_MODEL",
                    "current_policy": "HOLD_DEFAULT_ZERO",
                    "next_evidence_step": (
                        "Add explicit low/medium/high stress overlays after wear and repair occurrence "
                        "rules exist; do not request a production schedule without that evidence."
                    ),
                }
            ],
            "selection_note": (
                "Boundary values are one-dimensional observations under held anchors. "
                "Generate linked economy bundles only after the active-unit model decision."
            ),
        },
        "interpretation_limits": list(INTERPRETATION_LIMITS),
    }
    assert_provisional_boundary(report)
    return report


def _fake_outcome(complete: bool, value: int) -> dict[str, Any]:
    return {
        "completed_structural_witness": complete,
        "terminal_class": (
            "REACHED_DAY_56_DEBT_ZERO" if complete else "CHAPTER_HURDLE_MISSED"
        ),
        "terminal_runtime_status": "COMPLETE" if complete else "CHAPTER_HURDLE_MISSED",
        "terminal_day": 56 if complete else 7,
        "terminal_shortfall_amount": None if complete else 1,
        "completed_days": 56 if complete else 7,
        "attempted_operation_count": 56 if complete else 7,
        "day_56_observed": complete,
        "day_56_remaining_debt": 0 if complete else None,
        "terminal_remaining_debt": 0 if complete else 1,
        "cash_metrics": {
            "minimum_live_cash": value,
            "minimum_finance_cash": value,
            "terminal_live_cash": value,
            "terminal_finance_cash": value,
            "terminal_pending_preparation": 0,
        },
        "conservation_delta": 0,
    }


def _simulate_self_test_raw(raw: dict[str, Any]) -> dict[str, Any]:
    result = frontier.simulate_policy(
        frontier.normalize_config(raw), PRIMARY_POLICY, include_ledger=False
    )
    _assert_runtime_result_contract(result)
    return _terminal_projection(result)


def run_self_tests() -> dict[str, Any]:
    checks: list[str] = []
    reference = {
        "greedy_low_reference": {"daily_gross": [23, 29, 12, 12, 12]},
        "canonical_representative_reference": {
            "daily_gross": [34, 66, 56, 78, 75]
        },
        "not_a_56_day_distribution": True,
    }
    traces = build_phase_rotated_traces(reference)
    assert len(traces) == 15
    assert len({trace.trace_id for trace in traces}) == 15
    totals_by_band = {
        band: [sum(trace.daily_gross) for trace in traces if trace.source_band == band]
        for band in ("GREEDY_LOW", "MECHANICAL_MIDPOINT", "CANONICAL")
    }
    assert (min(totals_by_band["GREEDY_LOW"]), max(totals_by_band["GREEDY_LOW"])) == (
        980,
        997,
    )
    assert (
        min(totals_by_band["MECHANICAL_MIDPOINT"]),
        max(totals_by_band["MECHANICAL_MIDPOINT"]),
    ) == (2195, 2214)
    assert (min(totals_by_band["CANONICAL"]), max(totals_by_band["CANONICAL"])) == (
        3433,
        3477,
    )
    checks.append("fifteen_phase_rotated_trace_totals")

    for curve in TARGET_CURVES:
        targets = realize_target_curve(curve, 701)
        values = [targets[str(day)] for day in frontier.CHAPTER_DAYS]
        assert values == sorted(values)
        assert values[-1] == 701
        prior_values = [0] * len(frontier.CHAPTER_DAYS)
        for principal in range(0, 50):
            current = [
                realize_target_curve(curve, principal)[str(day)]
                for day in frontier.CHAPTER_DAYS
            ]
            assert all(
                current[index] >= prior_values[index]
                for index in range(len(current))
            )
            prior_values = current
    checks.append("rational_target_curves_monotonic_and_full_at_day_56")

    for total in (0, 1, 2, 17, 210, 211):
        for shape in REACTIVATION_SHAPES:
            allocated = allocate_integer_total(total, shape["weights"])
            assert sum(allocated) == total
            assert all(amount >= 0 for amount in allocated)
    checks.append("integer_reactivation_allocation_conserves_total")

    spec = default_anchor_spec()
    validate_candidate_definitions(spec)
    counts = active_unit_counts(spec)
    assert counts[:7] == (0,) * 7
    assert counts[7:14] == (1,) * 7
    assert counts[14:28] == (2,) * 14
    assert counts[28:42] == (3,) * 14
    assert counts[42:] == (4,) * 14
    schedule = upkeep_schedule(spec, anchor_parameters(spec))
    assert schedule[6] == 2
    assert schedule[7] == 3
    assert schedule[14] == 4
    checks.append("activation_event_day_counts_owned_unit_for_upkeep")
    checks.append("curve_shape_and_boundary_definition_guards")

    minimum = find_minimum_boundary(
        lambda value: _fake_outcome(value >= 3, value),
        proven_feasible_upper=10,
    )
    assert minimum["boundary_value"] == 3
    assert [row["value"] for row in minimum["witnesses"]] == [2, 3, 4]
    maximum = find_maximum_boundary(
        lambda value: _fake_outcome(value <= 5, value),
        proven_infeasible_upper=10,
    )
    assert maximum["boundary_value"] == 5
    assert [row["value"] for row in maximum["witnesses"]] == [4, 5, 6]
    minimum_zero = find_minimum_boundary(
        lambda value: _fake_outcome(True, value), proven_feasible_upper=0
    )
    assert minimum_zero["boundary_value"] == 0
    maximum_zero = find_maximum_boundary(
        lambda value: _fake_outcome(value == 0, value), proven_infeasible_upper=1
    )
    assert maximum_zero["boundary_value"] == 0
    assert maximum_zero["boundary_status"] == "DOMAIN_MINIMUM_IS_MAXIMUM_FEASIBLE"
    no_feasible = find_maximum_boundary(
        lambda value: _fake_outcome(False, value), proven_infeasible_upper=1
    )
    assert no_feasible["boundary_value"] is None
    checks.append("adjacent_integer_boundary_witnesses")

    original = anchor_parameters(spec)
    for axis in BOUNDARY_AXES:
        changed = _replace_axis(original, axis["id"], getattr(original, axis["id"]) + 1)
        differences = [
            field
            for field in _parameter_json(original)
            if getattr(original, field) != getattr(changed, field)
        ]
        assert differences == [axis["id"]]
    checks.append("boundary_parameter_changes_one_axis_only")

    zero_targets = {str(day): 0 for day in frontier.CHAPTER_DAYS}
    complete = _simulate_self_test_raw(
        {
            "scenario_id": "CANDIDATE_SELF_COMPLETE",
            "starting_cash": 10,
            "principal": 10,
            "daily_gross_sequence": [0] * frontier.BASE_YEAR_DAYS,
            "per_day_upkeep_schedule": 0,
            "reactivation_spends": [],
            "room_service_spends": [],
            "chapter_cumulative_targets": {
                **zero_targets,
                "56": 10,
            },
            "manual_extra_repayments": [],
        }
    )
    assert complete["terminal_class"] == "REACHED_DAY_56_DEBT_ZERO"
    assert complete["day_56_remaining_debt"] == 0
    checks.append("hand_checkable_structural_completion")

    chapter_failure = _simulate_self_test_raw(
        {
            "scenario_id": "CANDIDATE_SELF_CHAPTER_FAIL",
            "starting_cash": 0,
            "principal": 10,
            "daily_gross_sequence": [0] * frontier.BASE_YEAR_DAYS,
            "per_day_upkeep_schedule": 0,
            "reactivation_spends": [],
            "room_service_spends": [],
            "chapter_cumulative_targets": {
                "7": 1,
                "14": 2,
                "28": 4,
                "42": 7,
                "56": 10,
            },
            "manual_extra_repayments": [],
        }
    )
    assert chapter_failure["terminal_class"] == "CHAPTER_HURDLE_MISSED"
    assert chapter_failure["terminal_day"] == 7
    assert chapter_failure["day_56_observed"] is False
    assert chapter_failure["day_56_remaining_debt"] is None
    checks.append("early_terminal_keeps_day_56_unobserved")

    prep_failure = _simulate_self_test_raw(
        {
            "scenario_id": "CANDIDATE_SELF_PREP_FAIL",
            "starting_cash": 10,
            "principal": 0,
            "daily_gross_sequence": [0] * frontier.BASE_YEAR_DAYS,
            "per_day_upkeep_schedule": [10] + [0] * (frontier.BASE_YEAR_DAYS - 1),
            "reactivation_spends": [
                {"day": 1, "amount": 5, "label": "PREPAID"}
            ],
            "room_service_spends": [],
            "chapter_cumulative_targets": zero_targets,
            "manual_extra_repayments": [],
        }
    )
    assert prep_failure["terminal_class"] == "OPERATING_CASH_SHORTFALL"
    prep_cash = prep_failure["cash_metrics"]
    assert prep_cash["terminal_live_cash"] + prep_cash["terminal_pending_preparation"] == (
        prep_cash["terminal_finance_cash"]
    )
    checks.append("failed_preparation_live_finance_cash_identity")

    unexecutable = _simulate_self_test_raw(
        {
            "scenario_id": "CANDIDATE_SELF_UNEXECUTABLE",
            "starting_cash": 4,
            "principal": 0,
            "daily_gross_sequence": [100] + [0] * (frontier.BASE_YEAR_DAYS - 1),
            "per_day_upkeep_schedule": 0,
            "reactivation_spends": [
                {"day": 1, "amount": 5, "label": "UNPAYABLE"}
            ],
            "room_service_spends": [],
            "chapter_cumulative_targets": zero_targets,
            "manual_extra_repayments": [],
        }
    )
    assert unexecutable["terminal_class"] == "PREPARATION_PLAN_UNEXECUTABLE"
    assert unexecutable["terminal_day"] == 1
    assert unexecutable["attempted_operation_count"] == 0
    checks.append("unexecutable_preparation_is_not_gameplay_income")

    debt_failure = _simulate_self_test_raw(
        {
            "scenario_id": "CANDIDATE_SELF_DEBT_FAIL",
            "starting_cash": 9,
            "principal": 10,
            "daily_gross_sequence": [0] * frontier.BASE_YEAR_DAYS,
            "per_day_upkeep_schedule": 0,
            "reactivation_spends": [],
            "room_service_spends": [],
            "chapter_cumulative_targets": {
                **zero_targets,
                "56": 10,
            },
            "manual_extra_repayments": [],
        }
    )
    assert debt_failure["terminal_class"] == "DEBT_DEADLINE_MISSED"
    assert debt_failure["terminal_day"] == 56
    assert debt_failure["day_56_observed"] is True
    assert debt_failure["day_56_remaining_debt"] == 1
    checks.append("day_56_debt_deadline_terminal_class")

    assert json.dumps(
        [_trace_json(trace) for trace in traces], ensure_ascii=False, sort_keys=True
    ) == json.dumps(
        [_trace_json(trace) for trace in build_phase_rotated_traces(reference)],
        ensure_ascii=False,
        sort_keys=True,
    )
    checks.append("deterministic_trace_construction")

    minimal_report = {
        "contract_status": "PROVISIONAL",
        "balance_verdict": "NOT_EVALUATED",
        "exact_values_selected": False,
        "selection_authority": "USER",
        "full_game_controller_conformance_claimed": False,
        "runtime_conformance": True,
        "runtime_conformance_scope": frontier.RUNTIME_CONFORMANCE_SCOPE,
        "runtime_conformance_excludes": frontier.RUNTIME_CONFORMANCE_EXCLUDES,
        "primary_policy": {
            "id": PRIMARY_POLICY,
            "manual_extra_repayments": [],
        },
        "source_evidence": {
            "audit_income_reference": {"not_a_56_day_distribution": True}
        },
        "nested": {"balance_verdict": "NOT_EVALUATED"},
    }
    assert_provisional_boundary(minimal_report)
    bad_verdict = copy.deepcopy(minimal_report)
    bad_verdict["nested"]["balance_verdict"] = "PASS"
    try:
        assert_provisional_boundary(bad_verdict)
    except AssertionError:
        pass
    else:
        raise AssertionError("nested balance verdict mutation was accepted")
    bad_selection = copy.deepcopy(minimal_report)
    bad_selection["recommended_candidate_id"] = "C0001"
    try:
        assert_provisional_boundary(bad_selection)
    except AssertionError:
        pass
    else:
        raise AssertionError("automatic candidate selection key was accepted")
    bad_exact_selection = copy.deepcopy(minimal_report)
    bad_exact_selection["exact_values_selected"] = True
    try:
        assert_provisional_boundary(bad_exact_selection)
    except AssertionError:
        pass
    else:
        raise AssertionError("exact-value selection mutation was accepted")
    checks.append("recursive_provisional_selection_guard")

    valid_contract = {
        "runtime_conformance": True,
        "runtime_conformance_scope": frontier.RUNTIME_CONFORMANCE_SCOPE,
        "runtime_conformance_excludes": frontier.RUNTIME_CONFORMANCE_EXCLUDES,
        "full_game_controller_conformance_claimed": False,
        "balance_verdict": BALANCE_VERDICT,
        "policy_id": PRIMARY_POLICY,
    }
    _assert_runtime_result_contract(valid_contract)
    drifted_contract = dict(valid_contract)
    drifted_contract["runtime_conformance_scope"] = "DRIFTED"
    try:
        _assert_runtime_result_contract(drifted_contract)
    except AssertionError:
        pass
    else:
        raise AssertionError("analyzer contract drift was accepted")
    checks.append("runtime_analyzer_contract_drift_guard")

    try:
        normalize_anchor_spec({"activation_days": [8, 8, 29, 43]})
    except CandidateInputError:
        pass
    else:
        raise AssertionError("duplicate activation day was accepted")
    checks.append("candidate_spec_validation")

    return {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "status": "SELF_TEST_PASS",
        "contract_status": CONTRACT_STATUS,
        "balance_verdict": BALANCE_VERDICT,
        "checks": checks,
        "check_count": len(checks),
        "disclaimer": frontier.BALANCE_DISCLAIMER,
    }


def _load_spec(path: Path | None) -> AnchorSpec:
    if path is None:
        return default_anchor_spec()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CandidateInputError(f"could not read candidate spec {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CandidateInputError(f"candidate spec is not valid JSON: {exc}") from exc
    return normalize_anchor_spec(raw)


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
            "Observe provisional integer economy boundaries with the runtime-conformant "
            "campaign finance analyzer; never selects final values or a balance verdict."
        )
    )
    parser.add_argument("--artifact", type=Path, default=frontier.DEFAULT_AUDIT_PATH)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--output", default="-")
    parser.add_argument(
        "--max-simulations", type=int, default=DEFAULT_MAX_SIMULATIONS
    )
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.self_test:
            _write_json(run_self_tests(), args.output)
            return 0
        artifact_path = args.artifact.resolve()
        reference = frontier.load_audit_income_reference(artifact_path)
        spec = _load_spec(args.spec.resolve() if args.spec is not None else None)
        report = make_candidate_range_report(
            reference,
            spec,
            source_path=artifact_path,
            max_simulations=args.max_simulations,
            progress_stream=sys.stderr if args.progress else None,
        )
        _write_json(report, args.output)
        return 0
    except (
        AssertionError,
        CandidateInputError,
        SimulationLimitError,
        frontier.EconomyInputError,
    ) as exc:
        print(f"candidate-boundary error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
