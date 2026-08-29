from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


BASE_YEAR_DAYS = 56
CHAPTER_DAYS = (7, 14, 28, 42, 56)
MAX_SAFE_INTEGER = (1 << 53) - 1
POLICY_CHAPTER_MANUAL = "CHAPTER_MINIMUM_PLUS_MANUAL"
POLICY_FINAL_LUMP = "FINAL_DAY_LUMP_SUM"
POLICY_DAILY_AUTO = "DAILY_AUTOMATIC"
POLICY_IDS = (POLICY_CHAPTER_MANUAL, POLICY_FINAL_LUMP, POLICY_DAILY_AUTO)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT_PATH = (
    REPOSITORY_ROOT
    / "artifacts"
    / "v2-core-playtest"
    / "exhaustive-placement-audit.json"
)

BALANCE_DISCLAIMER = (
    "This tool compares provisional cash-flow assumptions. It does not establish "
    "a final debt, upkeep, reactivation, income distribution, difficulty, or balance PASS."
)
AUDIT_LIMIT_KO = (
    "감사 JSON의 두 actualResults 배열은 실제로 도달한 5영업 경로의 하루 수입 규모 참고치다. "
    "이를 반복한 민감도 가정은 56일 전체 수입 분포, 하한, 평균 또는 상환 가능성을 증명하지 않는다."
)
PARTIAL_SETTLEMENT_LIMIT = (
    "CHAPTER_MINIMUM_PLUS_MANUAL pays as much of a chapter gap as available cash allows, "
    "then records the hurdle as missed if a gap remains. This is an analyzer-only partial-settlement "
    "assumption, not a decision that the game will debit partial amounts instead of applying the "
    "player's explicit repayment atomically and failing a missed chapter hurdle."
)


class EconomyInputError(ValueError):
    """Raised when a scenario would make the ledger contract ambiguous."""


@dataclass(frozen=True)
class Spend:
    day: int
    amount: int
    label: str


@dataclass(frozen=True)
class EconomyConfig:
    scenario_id: str
    starting_cash: int
    principal: int
    daily_gross: tuple[int, ...]
    daily_upkeep: tuple[int, ...]
    reactivation_spends: tuple[Spend, ...]
    chapter_targets: dict[int, int]
    manual_extra_repayments: tuple[Spend, ...]

    @property
    def total_days(self) -> int:
        return len(self.daily_gross)


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EconomyInputError(f"{name} must be an integer gold amount")
    if value < 0:
        raise EconomyInputError(f"{name} must not be negative")
    if value > MAX_SAFE_INTEGER:
        raise EconomyInputError(
            f"{name} must not exceed the JavaScript safe-integer limit {MAX_SAFE_INTEGER}"
        )
    return value


def _positive_day(value: Any, name: str, total_days: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EconomyInputError(f"{name} must be an integer day")
    if not 1 <= value <= total_days:
        raise EconomyInputError(f"{name} must be between 1 and {total_days}")
    return value


def _day_token(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise EconomyInputError(f"{name} must be an integer day")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value.strip()):
        return int(value.strip())
    raise EconomyInputError(f"{name} must be an integer day")


def _first_present(raw: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in raw:
            return raw[key]
    return default


def _expand_upkeep(raw: Any, total_days: int) -> tuple[int, ...]:
    if raw is None:
        return (0,) * total_days
    if isinstance(raw, int) and not isinstance(raw, bool):
        amount = _nonnegative_int(raw, "per_day_upkeep_schedule")
        return (amount,) * total_days
    if isinstance(raw, dict):
        values = [0] * total_days
        seen: set[int] = set()
        for day_text, amount_raw in raw.items():
            day_raw = _day_token(
                day_text, f"per_day_upkeep_schedule key {day_text!r}"
            )
            day = _positive_day(day_raw, "per_day_upkeep_schedule day", total_days)
            if day in seen:
                raise EconomyInputError(f"duplicate upkeep day {day}")
            seen.add(day)
            values[day - 1] = _nonnegative_int(
                amount_raw, f"per_day_upkeep_schedule[{day}]"
            )
        return tuple(values)
    if not isinstance(raw, list):
        raise EconomyInputError(
            "per_day_upkeep_schedule must be an integer, day mapping, daily list, or segment list"
        )
    if all(isinstance(value, int) and not isinstance(value, bool) for value in raw):
        if len(raw) != total_days:
            raise EconomyInputError(
                f"daily upkeep list must have exactly {total_days} entries"
            )
        return tuple(
            _nonnegative_int(value, f"per_day_upkeep_schedule[{index}]")
            for index, value in enumerate(raw, start=1)
        )
    values = [0] * total_days
    covered: set[int] = set()
    for index, segment in enumerate(raw):
        owner = f"per_day_upkeep_schedule[{index}]"
        if not isinstance(segment, dict):
            raise EconomyInputError(f"{owner} must be an object")
        start_raw = segment.get("start_day", segment.get("day"))
        end_raw = segment.get("end_day", start_raw)
        start = _positive_day(start_raw, f"{owner}.start_day", total_days)
        end = _positive_day(end_raw, f"{owner}.end_day", total_days)
        if end < start:
            raise EconomyInputError(f"{owner}.end_day must not precede start_day")
        amount = _nonnegative_int(segment.get("amount"), f"{owner}.amount")
        for day in range(start, end + 1):
            if day in covered:
                raise EconomyInputError(f"upkeep segments overlap on day {day}")
            covered.add(day)
            values[day - 1] = amount
    return tuple(values)


def _normalize_spends(
    raw: Any,
    name: str,
    total_days: int,
    default_label: str,
) -> tuple[Spend, ...]:
    if raw is None:
        return ()
    entries: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        for day_text, value in raw.items():
            day = _day_token(day_text, f"{name} key {day_text!r}")
            if isinstance(value, dict):
                entries.append({**value, "day": day})
            else:
                entries.append({"day": day, "amount": value})
    elif isinstance(raw, list):
        entries = raw
    else:
        raise EconomyInputError(f"{name} must be a day mapping or list")

    spends: list[Spend] = []
    for index, entry in enumerate(entries):
        owner = f"{name}[{index}]"
        if not isinstance(entry, dict):
            raise EconomyInputError(f"{owner} must be an object")
        day = _positive_day(
            _day_token(entry.get("day"), f"{owner}.day"),
            f"{owner}.day",
            total_days,
        )
        amount = _nonnegative_int(entry.get("amount"), f"{owner}.amount")
        label_raw = entry.get("label", f"{default_label}_{day}")
        if not isinstance(label_raw, str) or not label_raw.strip():
            raise EconomyInputError(f"{owner}.label must be a non-empty string")
        spends.append(Spend(day=day, amount=amount, label=label_raw.strip()))
    return tuple(sorted(spends, key=lambda spend: (spend.day, spend.label)))


def _normalize_targets(raw: Any, principal: int) -> dict[int, int]:
    if raw is None:
        raise EconomyInputError("chapter_cumulative_targets is required")
    targets: dict[int, int] = {}
    if isinstance(raw, dict):
        entries: Iterable[tuple[Any, Any]] = raw.items()
    elif isinstance(raw, list):
        parsed: list[tuple[Any, Any]] = []
        for index, entry in enumerate(raw):
            if not isinstance(entry, dict):
                raise EconomyInputError(
                    f"chapter_cumulative_targets[{index}] must be an object"
                )
            parsed.append((entry.get("day"), entry.get("amount")))
        entries = parsed
    else:
        raise EconomyInputError("chapter_cumulative_targets must be a mapping or list")

    for day_raw, amount_raw in entries:
        day = _day_token(day_raw, f"chapter target day {day_raw!r}")
        if day in targets:
            raise EconomyInputError(f"duplicate chapter target day {day}")
        targets[day] = _nonnegative_int(
            amount_raw, f"chapter_cumulative_targets[{day}]"
        )

    if set(targets) != set(CHAPTER_DAYS):
        raise EconomyInputError(
            "chapter_cumulative_targets must define exactly days "
            + ", ".join(str(day) for day in CHAPTER_DAYS)
        )
    prior = 0
    for day in CHAPTER_DAYS:
        amount = targets[day]
        if amount < prior:
            raise EconomyInputError("chapter cumulative targets must be nondecreasing")
        if amount > principal:
            raise EconomyInputError(
                f"chapter target on day {day} exceeds principal {principal}"
            )
        prior = amount
    if targets[BASE_YEAR_DAYS] != principal:
        raise EconomyInputError(
            f"day {BASE_YEAR_DAYS} cumulative target must equal principal {principal}"
        )
    return targets


def normalize_config(raw: dict[str, Any]) -> EconomyConfig:
    if not isinstance(raw, dict):
        raise EconomyInputError("scenario JSON must be an object")
    scenario_id = raw.get("scenario_id", "CUSTOM_SCENARIO")
    if not isinstance(scenario_id, str) or not scenario_id.strip():
        raise EconomyInputError("scenario_id must be a non-empty string")
    starting_cash = _nonnegative_int(raw.get("starting_cash"), "starting_cash")
    principal = _nonnegative_int(raw.get("principal"), "principal")
    gross_raw = _first_present(raw, "daily_gross_sequence", "daily_gross")
    if not isinstance(gross_raw, list):
        raise EconomyInputError("daily_gross_sequence must be a list")
    daily_gross = tuple(
        _nonnegative_int(value, f"daily_gross_sequence[{index}]")
        for index, value in enumerate(gross_raw, start=1)
    )
    if len(daily_gross) < BASE_YEAR_DAYS:
        raise EconomyInputError(
            f"daily_gross_sequence must contain at least {BASE_YEAR_DAYS} days"
        )
    total_days = len(daily_gross)
    daily_upkeep = _expand_upkeep(
        _first_present(
            raw,
            "per_day_upkeep_schedule",
            "per_day_upkeep",
            "upkeep_schedule",
        ),
        total_days,
    )
    reactivation_spends = _normalize_spends(
        raw.get("reactivation_spends"),
        "reactivation_spends",
        total_days,
        "REACTIVATION",
    )
    chapter_targets = _normalize_targets(
        raw.get("chapter_cumulative_targets"), principal
    )
    manual_extra = _normalize_spends(
        raw.get("manual_extra_repayments"),
        "manual_extra_repayments",
        total_days,
        "MANUAL_EXTRA",
    )
    aggregate_bound = (
        starting_cash
        + principal
        + sum(daily_gross)
        + sum(daily_upkeep)
        + sum(spend.amount for spend in reactivation_spends)
        + sum(spend.amount for spend in manual_extra)
    )
    if aggregate_bound > MAX_SAFE_INTEGER:
        raise EconomyInputError(
            "combined scenario cash-flow exposure exceeds the JavaScript safe-integer limit"
        )
    return EconomyConfig(
        scenario_id=scenario_id.strip(),
        starting_cash=starting_cash,
        principal=principal,
        daily_gross=daily_gross,
        daily_upkeep=daily_upkeep,
        reactivation_spends=reactivation_spends,
        chapter_targets=chapter_targets,
        manual_extra_repayments=manual_extra,
    )


def _group_spends(spends: tuple[Spend, ...]) -> dict[int, list[Spend]]:
    grouped: dict[int, list[Spend]] = {}
    for spend in spends:
        grouped.setdefault(spend.day, []).append(spend)
    return grouped


def _affordable_payment(requested: int, cash: int, remaining_principal: int) -> int:
    return min(requested, max(cash, 0), remaining_principal)


def _daily_auto_cumulative_target(principal: int, day: int) -> int:
    if day >= BASE_YEAR_DAYS:
        return principal
    return (principal * day + BASE_YEAR_DAYS - 1) // BASE_YEAR_DAYS


def simulate_policy(
    config: EconomyConfig,
    policy_id: str,
    *,
    include_ledger: bool = True,
) -> dict[str, Any]:
    if policy_id not in POLICY_IDS:
        raise EconomyInputError(f"unknown repayment policy {policy_id!r}")
    reactivation_by_day = _group_spends(config.reactivation_spends)
    manual_by_day = _group_spends(config.manual_extra_repayments)

    cash = config.starting_cash
    cumulative_repayment = 0
    ledger: list[dict[str, Any]] = []
    checkpoints: list[dict[str, Any]] = []
    base_deadline_snapshot: dict[str, Any] | None = None

    total_gross = 0
    total_upkeep = 0
    total_reactivation = 0
    total_repayment = 0
    minimum_cash = cash

    for day, gross in enumerate(config.daily_gross, start=1):
        opening_cash = cash
        upkeep = config.daily_upkeep[day - 1]
        reactivation_entries = reactivation_by_day.get(day, [])
        reactivation = sum(entry.amount for entry in reactivation_entries)
        manual_entries = manual_by_day.get(day, [])
        manual_requested_source = sum(entry.amount for entry in manual_entries)

        cash = opening_cash + gross - upkeep - reactivation
        cash_before_repayment = cash
        remaining_before = config.principal - cumulative_repayment

        mandatory_requested = 0
        mandatory_paid = 0
        manual_requested = 0
        manual_paid = 0
        automatic_requested = 0
        automatic_paid = 0
        ignored_manual_requested = 0

        if policy_id == POLICY_CHAPTER_MANUAL:
            if day in config.chapter_targets:
                mandatory_requested = max(
                    0, config.chapter_targets[day] - cumulative_repayment
                )
                mandatory_paid = _affordable_payment(
                    mandatory_requested, cash, remaining_before
                )
                cash -= mandatory_paid
                cumulative_repayment += mandatory_paid
                remaining_before -= mandatory_paid
            manual_requested = manual_requested_source
            manual_paid = _affordable_payment(
                manual_requested, cash, remaining_before
            )
            cash -= manual_paid
            cumulative_repayment += manual_paid
        elif policy_id == POLICY_FINAL_LUMP:
            ignored_manual_requested = manual_requested_source
            if day == BASE_YEAR_DAYS:
                automatic_requested = config.principal - cumulative_repayment
                automatic_paid = _affordable_payment(
                    automatic_requested, cash, remaining_before
                )
                cash -= automatic_paid
                cumulative_repayment += automatic_paid
        elif policy_id == POLICY_DAILY_AUTO:
            ignored_manual_requested = manual_requested_source
            if day <= BASE_YEAR_DAYS:
                desired_cumulative = _daily_auto_cumulative_target(
                    config.principal, day
                )
                automatic_requested = max(
                    0, desired_cumulative - cumulative_repayment
                )
                automatic_paid = _affordable_payment(
                    automatic_requested, cash, remaining_before
                )
                cash -= automatic_paid
                cumulative_repayment += automatic_paid

        repayment_requested = (
            mandatory_requested + manual_requested + automatic_requested
        )
        repayment_paid = mandatory_paid + manual_paid + automatic_paid
        remaining_principal = config.principal - cumulative_repayment
        conservation_left = opening_cash + gross
        conservation_right = cash + upkeep + reactivation + repayment_paid
        conservation_delta = conservation_left - conservation_right
        if conservation_delta != 0:
            raise AssertionError(
                f"cash conservation failed on day {day}: {conservation_delta}"
            )

        checkpoint: dict[str, Any] | None = None
        if day in config.chapter_targets:
            target = config.chapter_targets[day]
            checkpoint = {
                "day": day,
                "cumulative_target": target,
                "cumulative_repayment": cumulative_repayment,
                "gap": max(0, target - cumulative_repayment),
                "status": "REACHED" if cumulative_repayment >= target else "MISSED",
            }
            checkpoints.append(checkpoint)

        row = {
            "day": day,
            "period": "BASE_YEAR" if day <= BASE_YEAR_DAYS else "TRUE_EXTENSION",
            "opening_cash": opening_cash,
            "gross": gross,
            "upkeep": upkeep,
            "reactivation": {
                "amount": reactivation,
                "items": [
                    {"label": entry.label, "amount": entry.amount}
                    for entry in reactivation_entries
                ],
            },
            "cash_before_repayment": cash_before_repayment,
            "repayment": {
                "requested": repayment_requested,
                "paid": repayment_paid,
                "mandatory_requested": mandatory_requested,
                "mandatory_paid": mandatory_paid,
                "manual_requested": manual_requested,
                "manual_paid": manual_paid,
                "automatic_requested": automatic_requested,
                "automatic_paid": automatic_paid,
                "ignored_manual_requested_by_policy": ignored_manual_requested,
            },
            "cumulative_repayment": cumulative_repayment,
            "remaining_principal": remaining_principal,
            "closing_cash": cash,
            "liquidity_shortfall": cash < 0,
            "conservation_delta": conservation_delta,
            "chapter_hurdle": checkpoint,
        }
        ledger.append(row)
        if day == BASE_YEAR_DAYS:
            base_deadline_snapshot = {
                "day": BASE_YEAR_DAYS,
                "cash": cash,
                "cumulative_repayment": cumulative_repayment,
                "remaining_principal": remaining_principal,
                "qualified": cumulative_repayment >= config.principal,
                "status": (
                    "QUALIFIED_BY_DAY_56"
                    if cumulative_repayment >= config.principal
                    else "NOT_QUALIFIED_BY_DAY_56"
                ),
            }

        total_gross += gross
        total_upkeep += upkeep
        total_reactivation += reactivation
        total_repayment += repayment_paid
        minimum_cash = min(minimum_cash, cash)

    assert base_deadline_snapshot is not None
    base_rows = ledger[:BASE_YEAR_DAYS]
    extension_rows = ledger[BASE_YEAR_DAYS:]
    extension_repayment = sum(
        row["repayment"]["paid"] for row in extension_rows
    )
    base_totals = {
        "gross": sum(row["gross"] for row in base_rows),
        "upkeep": sum(row["upkeep"] for row in base_rows),
        "reactivation": sum(row["reactivation"]["amount"] for row in base_rows),
        "repayment": sum(row["repayment"]["paid"] for row in base_rows),
    }
    result = {
        "status": "SIMULATED_PROVISIONAL",
        "balance_verdict": "NOT_EVALUATED",
        "policy_id": policy_id,
        "policy_role": (
            "recommended_structure_under_test"
            if policy_id == POLICY_CHAPTER_MANUAL
            else "comparison_only"
        ),
        "settlement_assumption": (
            "PARTIAL_CHAPTER_GAP_FROM_AVAILABLE_CASH_ANALYSIS_ONLY"
            if policy_id == POLICY_CHAPTER_MANUAL
            else "NOT_APPLICABLE"
        ),
        "scenario_id": config.scenario_id,
        "base_year_deadline": base_deadline_snapshot,
        "true_extension_rule": {
            "extension_days_present": config.total_days > BASE_YEAR_DAYS,
            "repayment_paid_after_day_56": extension_repayment,
            "final_debt_changed_after_day_56": extension_repayment > 0,
            "repayment_after_day_56_can_retroactively_change_qualification": False,
        },
        "chapter_hurdles": checkpoints,
        "all_chapter_minimums_reached": all(
            checkpoint["status"] == "REACHED" for checkpoint in checkpoints
        ),
        "base_year_totals": base_totals,
        "whole_sequence_totals": {
            "days": config.total_days,
            "gross": total_gross,
            "upkeep": total_upkeep,
            "reactivation": total_reactivation,
            "repayment": total_repayment,
            "closing_cash": cash,
            "remaining_principal": config.principal - cumulative_repayment,
            "minimum_cash": minimum_cash,
            "liquidity_shortfall_days": [
                row["day"] for row in ledger if row["liquidity_shortfall"]
            ],
        },
        "conservation_check": {
            "opening_cash_plus_gross": config.starting_cash + total_gross,
            "closing_cash_plus_outflows": (
                cash + total_upkeep + total_reactivation + total_repayment
            ),
            "delta": (
                config.starting_cash
                + total_gross
                - cash
                - total_upkeep
                - total_reactivation
                - total_repayment
            ),
        },
        "disclaimer": BALANCE_DISCLAIMER,
        "settlement_limit": PARTIAL_SETTLEMENT_LIMIT,
    }
    if include_ledger:
        result["daily_ledger"] = ledger
    return result


def _extract_named_json_object(path: Path, key: str) -> dict[str, Any]:
    """Extract one object without loading the audit's 50 MB route payload."""

    needle = json.dumps(key)
    collecting = False
    depth = 0
    in_string = False
    escaped = False
    pieces: list[str] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            scan = line
            if not collecting:
                key_index = scan.find(needle)
                if key_index < 0:
                    continue
                brace_index = scan.find("{", key_index + len(needle))
                if brace_index < 0:
                    continue
                scan = scan[brace_index:]
                collecting = True
            end_index: int | None = None
            for index, character in enumerate(scan):
                if in_string:
                    if escaped:
                        escaped = False
                    elif character == "\\":
                        escaped = True
                    elif character == '"':
                        in_string = False
                    continue
                if character == '"':
                    in_string = True
                elif character == "{":
                    depth += 1
                elif character == "}":
                    depth -= 1
                    if depth == 0:
                        end_index = index + 1
                        break
            pieces.append(scan if end_index is None else scan[:end_index])
            if end_index is not None:
                parsed = json.loads("".join(pieces))
                if not isinstance(parsed, dict):
                    raise EconomyInputError(f"audit {key} must be an object")
                return parsed
    raise EconomyInputError(f"could not find JSON object {key!r} in {path}")


def _extract_prefix_string(prefix: str, key: str) -> str | None:
    match = re.search(
        rf'{re.escape(json.dumps(key))}\s*:\s*("(?:\\.|[^"\\])*")', prefix
    )
    return json.loads(match.group(1)) if match else None


def load_audit_income_reference(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise EconomyInputError(f"audit artifact does not exist: {path}")
    summary = _extract_named_json_object(path, "summary")
    canonical_results = summary.get("canonicalActualResults")
    low_results = summary.get("greedyLowActualResults")
    if not isinstance(canonical_results, list) or not isinstance(low_results, list):
        raise EconomyInputError(
            "audit summary must contain canonicalActualResults and greedyLowActualResults"
        )

    def incomes(entries: list[Any], owner: str) -> list[int]:
        output: list[int] = []
        expected_stage = 1
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise EconomyInputError(f"{owner}[{index}] must be an object")
            if entry.get("stage") != expected_stage:
                raise EconomyInputError(f"{owner} stages must be consecutive from 1")
            output.append(_nonnegative_int(entry.get("income"), f"{owner}[{index}].income"))
            expected_stage += 1
        if not output:
            raise EconomyInputError(f"{owner} must not be empty")
        return output

    canonical = incomes(canonical_results, "canonicalActualResults")
    lower = incomes(low_results, "greedyLowActualResults")
    with path.open("r", encoding="utf-8") as handle:
        prefix = handle.read(16_384)
    return {
        "path": str(path),
        "artifact_status": _extract_prefix_string(prefix, "status"),
        "artifact_scope": _extract_prefix_string(prefix, "scope"),
        "canonical_representative_reference": {
            "source_key": "summary.canonicalActualResults",
            "days": len(canonical),
            "daily_gross": canonical,
            "minimum": min(canonical),
            "maximum": max(canonical),
            "mean": mean(canonical),
        },
        "greedy_low_reference": {
            "source_key": "summary.greedyLowActualResults",
            "days": len(lower),
            "daily_gross": lower,
            "minimum": min(lower),
            "maximum": max(lower),
            "mean": mean(lower),
        },
        "not_a_56_day_distribution": True,
        "interpretation_limit_ko": AUDIT_LIMIT_KO,
    }


def _repeat_to_days(pattern: list[int], days: int) -> list[int]:
    return [pattern[index % len(pattern)] for index in range(days)]


def _default_targets(principal: int) -> dict[str, int]:
    ratios = {7: 60, 14: 140, 28: 330, 42: 520, 56: 700}
    return {
        str(day): round(principal * amount / 700)
        for day, amount in ratios.items()
    }


def build_default_scenarios(reference: dict[str, Any]) -> list[EconomyConfig]:
    canonical = reference["canonical_representative_reference"]["daily_gross"]
    lower = reference["greedy_low_reference"]["daily_gross"]
    midpoint = [(left + right) // 2 for left, right in zip(lower, canonical)]
    gross_patterns = {
        "GREEDY_LOW_5_DAY_PATTERN_REPEATED": lower,
        "MIDPOINT_OF_TWO_5_DAY_PATTERNS_REPEATED": midpoint,
        "CANONICAL_5_DAY_PATTERN_REPEATED": canonical,
    }
    upkeep_profiles = {
        "LEAN_2_PER_DAY": 2,
        "STAGED_2_4_6_8": [
            {"start_day": 1, "end_day": 14, "amount": 2},
            {"start_day": 15, "end_day": 28, "amount": 4},
            {"start_day": 29, "end_day": 42, "amount": 6},
            {"start_day": 43, "end_day": 56, "amount": 8},
        ],
    }
    output: list[EconomyConfig] = []
    for gross_id, pattern in gross_patterns.items():
        for upkeep_id, upkeep in upkeep_profiles.items():
            output.append(
                normalize_config(
                    {
                        "scenario_id": f"{gross_id}__{upkeep_id}",
                        "starting_cash": 60,
                        "principal": 700,
                        "daily_gross_sequence": _repeat_to_days(pattern, BASE_YEAR_DAYS),
                        "per_day_upkeep_schedule": upkeep,
                        "reactivation_spends": [
                            {"day": 8, "amount": 30, "label": "AREA_1"},
                            {"day": 15, "amount": 45, "label": "AREA_2"},
                            {"day": 29, "amount": 60, "label": "AREA_3"},
                            {"day": 43, "amount": 75, "label": "AREA_4"},
                        ],
                        "chapter_cumulative_targets": _default_targets(700),
                        "manual_extra_repayments": [
                            {"day": 21, "amount": 30, "label": "PLAYER_EXTRA_1"},
                            {"day": 35, "amount": 30, "label": "PLAYER_EXTRA_2"},
                        ],
                    }
                )
            )
    return output


def _compact_result(result: dict[str, Any]) -> dict[str, Any]:
    base = result["base_year_deadline"]
    totals = result["base_year_totals"]
    whole = result["whole_sequence_totals"]
    return {
        "scenario_id": result["scenario_id"],
        "policy_id": result["policy_id"],
        "policy_role": result["policy_role"],
        "gross_days_1_56": totals["gross"],
        "upkeep_days_1_56": totals["upkeep"],
        "reactivation_days_1_56": totals["reactivation"],
        "repaid_by_day_56": base["cumulative_repayment"],
        "remaining_principal_day_56": base["remaining_principal"],
        "cash_day_56": base["cash"],
        "day_56_gate": base["status"],
        "all_chapter_minimums_reached": result["all_chapter_minimums_reached"],
        "chapter_statuses": {
            str(checkpoint["day"]): checkpoint["status"]
            for checkpoint in result["chapter_hurdles"]
        },
        "minimum_cash": whole["minimum_cash"],
        "liquidity_shortfall_day_count": len(whole["liquidity_shortfall_days"]),
        "balance_verdict": "NOT_EVALUATED",
    }


def make_sensitivity_report(
    reference: dict[str, Any],
    policy_ids: Iterable[str],
    *,
    include_ledger: bool,
) -> dict[str, Any]:
    scenarios = build_default_scenarios(reference)
    table: list[dict[str, Any]] = []
    detailed: list[dict[str, Any]] = []
    for config in scenarios:
        for policy_id in policy_ids:
            result = simulate_policy(config, policy_id, include_ledger=include_ledger)
            table.append(_compact_result(result))
            if include_ledger:
                detailed.append(result)
    return {
        "status": "PROVISIONAL_SENSITIVITY_ANALYSIS",
        "balance_verdict": "NOT_EVALUATED",
        "base_year_days": BASE_YEAR_DAYS,
        "chapter_days": list(CHAPTER_DAYS),
        "currency_contract": (
            "nonnegative JavaScript-safe integer gold inputs and aggregate exposure; "
            "cash may become negative to expose liquidity shortfall"
        ),
        "audit_income_reference": reference,
        "assumption_status": "ILLUSTRATIVE_ONLY",
        "assumptions": {
            "starting_cash": 60,
            "principal": 700,
            "chapter_cumulative_targets": _default_targets(700),
            "reactivation_spends": {"8": 30, "15": 45, "29": 60, "43": 75},
            "manual_extra_repayments": {"21": 30, "35": 30},
            "gross_construction": (
                "Each five-day audit reference, plus its elementwise midpoint, is mechanically "
                "repeated to 56 days for sensitivity only."
            ),
            "upkeep_profiles": ["LEAN_2_PER_DAY", "STAGED_2_4_6_8"],
        },
        "policy_definitions": policy_definitions(),
        "sensitivity_table": table,
        "detailed_results": detailed if include_ledger else None,
        "interpretation_limits": [
            BALANCE_DISCLAIMER,
            AUDIT_LIMIT_KO,
            PARTIAL_SETTLEMENT_LIMIT,
        ],
    }


def policy_definitions() -> dict[str, str]:
    return {
        POLICY_CHAPTER_MANUAL: (
            "At each chapter boundary, pay the gap to the cumulative minimum from available cash, "
            "then apply player-scheduled extra repayments. Earlier extras reduce later cumulative gaps. "
            "A cash-short gap receives a partial payment in this analyzer only; the actual game applies "
            "only the player's explicit repayment atomically and closes a missed chapter hurdle."
        ),
        POLICY_FINAL_LUMP: (
            "Make no repayment before day 56, then pay as much of the remaining principal as cash allows."
        ),
        POLICY_DAILY_AUTO: (
            "Each base-year day, catch up toward ceil(principal * day / 56) from available cash."
        ),
    }


def _base_self_test_raw(**overrides: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "scenario_id": "SELF_TEST",
        "starting_cash": 20,
        "principal": 100,
        "daily_gross_sequence": [10] * BASE_YEAR_DAYS,
        "per_day_upkeep_schedule": 2,
        "reactivation_spends": [],
        "chapter_cumulative_targets": {
            "7": 10,
            "14": 20,
            "28": 40,
            "42": 60,
            "56": 100,
        },
        "manual_extra_repayments": [],
    }
    raw.update(overrides)
    return raw


def run_self_tests() -> dict[str, Any]:
    checks: list[str] = []

    conservation = simulate_policy(
        normalize_config(_base_self_test_raw()), POLICY_CHAPTER_MANUAL
    )
    assert conservation["conservation_check"]["delta"] == 0
    assert all(row["conservation_delta"] == 0 for row in conservation["daily_ledger"])
    checks.append("cash_conservation_equation")

    for bad_field, bad_value in (
        ("per_day_upkeep_schedule", -1),
        ("reactivation_spends", [{"day": 1, "amount": -1}]),
        ("manual_extra_repayments", [{"day": 1, "amount": -1}]),
    ):
        try:
            normalize_config(_base_self_test_raw(**{bad_field: bad_value}))
        except EconomyInputError:
            pass
        else:
            raise AssertionError(f"negative {bad_field} was accepted")
    checks.append("negative_spending_rejected")

    try:
        normalize_config(
            _base_self_test_raw(
                starting_cash=MAX_SAFE_INTEGER,
                daily_gross_sequence=[1] * BASE_YEAR_DAYS,
            )
        )
    except EconomyInputError:
        pass
    else:
        raise AssertionError("safe-integer aggregate overflow was accepted")
    checks.append("safe_integer_overflow_rejected")

    wrong_final_target = _base_self_test_raw()
    wrong_final_target["chapter_cumulative_targets"] = {
        **wrong_final_target["chapter_cumulative_targets"],
        "56": 99,
    }
    try:
        normalize_config(wrong_final_target)
    except EconomyInputError:
        pass
    else:
        raise AssertionError("day 56 target below principal was accepted")
    checks.append("day_56_target_equals_principal")

    full = simulate_policy(
        normalize_config(
            _base_self_test_raw(
                starting_cash=100,
                daily_gross_sequence=[0] * BASE_YEAR_DAYS,
                per_day_upkeep_schedule=0,
            )
        ),
        POLICY_FINAL_LUMP,
    )
    short = simulate_policy(
        normalize_config(
            _base_self_test_raw(
                starting_cash=99,
                daily_gross_sequence=[0] * BASE_YEAR_DAYS,
                per_day_upkeep_schedule=0,
            )
        ),
        POLICY_FINAL_LUMP,
    )
    assert full["base_year_deadline"]["qualified"] is True
    assert short["base_year_deadline"]["qualified"] is False
    checks.append("day_56_full_repayment_gate")

    extension_raw = _base_self_test_raw(
        starting_cash=0,
        daily_gross_sequence=[0] * BASE_YEAR_DAYS + [100] + [0] * 13,
        per_day_upkeep_schedule=0,
        chapter_cumulative_targets={
            "7": 0,
            "14": 0,
            "28": 0,
            "42": 0,
            "56": 100,
        },
        manual_extra_repayments=[{"day": 57, "amount": 100}],
    )
    extension = simulate_policy(
        normalize_config(extension_raw), POLICY_CHAPTER_MANUAL
    )
    assert extension["base_year_deadline"]["qualified"] is False
    assert extension["whole_sequence_totals"]["remaining_principal"] == 0
    assert (
        extension["true_extension_rule"][
            "repayment_after_day_56_can_retroactively_change_qualification"
        ]
        is False
    )
    checks.append("true_extension_does_not_retroactively_change_gate")

    comparison_config = normalize_config(
        _base_self_test_raw(
            starting_cash=0,
            daily_gross_sequence=[10] * BASE_YEAR_DAYS,
            per_day_upkeep_schedule=0,
            manual_extra_repayments=[{"day": 20, "amount": 10}],
        )
    )
    comparison = {
        policy: simulate_policy(comparison_config, policy)
        for policy in POLICY_IDS
    }
    chapter = comparison[POLICY_CHAPTER_MANUAL]
    lump = comparison[POLICY_FINAL_LUMP]
    daily = comparison[POLICY_DAILY_AUTO]
    assert any(
        row["repayment"]["manual_paid"] > 0 for row in chapter["daily_ledger"]
    )
    assert lump["chapter_hurdles"][0]["status"] == "MISSED"
    assert lump["base_year_deadline"]["qualified"] is True
    assert daily["daily_ledger"][0]["repayment"]["automatic_paid"] > 0
    assert set(comparison) == set(POLICY_IDS)
    checks.append("three_policy_comparison")

    return {
        "status": "SELF_TEST_PASS",
        "checks": checks,
        "balance_verdict": "NOT_EVALUATED",
        "disclaimer": BALANCE_DISCLAIMER,
    }


def _parse_csv_ints(text: str, name: str) -> list[int]:
    if not text.strip():
        raise EconomyInputError(f"{name} must not be empty")
    output: list[int] = []
    for index, part in enumerate(text.split(","), start=1):
        try:
            value = int(part.strip())
        except ValueError as exc:
            raise EconomyInputError(f"{name} item {index} is not an integer") from exc
        output.append(_nonnegative_int(value, f"{name}[{index}]"))
    return output


def _parse_day_amount_specs(
    specs: list[str] | None, name: str, *, allow_label: bool
) -> list[dict[str, Any]] | None:
    if specs is None:
        return None
    output: list[dict[str, Any]] = []
    for index, spec in enumerate(specs, start=1):
        parts = spec.split(":", 2 if allow_label else 1)
        expected = 2
        if len(parts) < expected:
            raise EconomyInputError(f"{name} item {index} must be DAY:AMOUNT")
        try:
            day = int(parts[0])
            amount = int(parts[1])
        except ValueError as exc:
            raise EconomyInputError(
                f"{name} item {index} has a non-integer day or amount"
            ) from exc
        entry: dict[str, Any] = {"day": day, "amount": amount}
        if allow_label and len(parts) == 3 and parts[2].strip():
            entry["label"] = parts[2].strip()
        output.append(entry)
    return output


def _load_input_json(path_text: str) -> dict[str, Any]:
    if path_text == "-":
        raw = json.loads(sys.stdin.read())
    else:
        raw = json.loads(Path(path_text).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise EconomyInputError("input JSON must contain an object")
    return raw


def _custom_raw_from_args(args: argparse.Namespace) -> dict[str, Any] | None:
    scenario_args_present = any(
        value is not None
        for value in (
            args.input,
            args.starting_cash,
            args.principal,
            args.daily_gross,
            args.per_day_upkeep,
            args.reactivation_spend,
            args.chapter_target,
            args.manual_extra,
            args.scenario_id,
        )
    )
    if not scenario_args_present:
        return None
    raw = _load_input_json(args.input) if args.input else {}
    if args.scenario_id is not None:
        raw["scenario_id"] = args.scenario_id
    if args.starting_cash is not None:
        raw["starting_cash"] = args.starting_cash
    if args.principal is not None:
        raw["principal"] = args.principal
    if args.daily_gross is not None:
        raw["daily_gross_sequence"] = _parse_csv_ints(
            args.daily_gross, "--daily-gross"
        )
    if args.per_day_upkeep is not None:
        parsed_upkeep = _parse_csv_ints(args.per_day_upkeep, "--per-day-upkeep")
        raw["per_day_upkeep_schedule"] = (
            parsed_upkeep[0] if len(parsed_upkeep) == 1 else parsed_upkeep
        )
    reactivation = _parse_day_amount_specs(
        args.reactivation_spend, "--reactivation-spend", allow_label=True
    )
    if reactivation is not None:
        raw["reactivation_spends"] = reactivation
    chapter_targets = _parse_day_amount_specs(
        args.chapter_target, "--chapter-target", allow_label=False
    )
    if chapter_targets is not None:
        raw["chapter_cumulative_targets"] = chapter_targets
    manual = _parse_day_amount_specs(
        args.manual_extra, "--manual-extra", allow_label=True
    )
    if manual is not None:
        raw["manual_extra_repayments"] = manual
    return raw


def _selected_policies(selection: str) -> tuple[str, ...]:
    return POLICY_IDS if selection == "all" else (selection,)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare provisional 56-day campaign debt repayment policies without claiming "
            "a final balance verdict."
        )
    )
    parser.add_argument("--input", help="scenario JSON path, or - for stdin")
    parser.add_argument("--artifact", type=Path, default=DEFAULT_AUDIT_PATH)
    parser.add_argument("--scenario-id")
    parser.add_argument("--starting-cash", type=int)
    parser.add_argument("--principal", type=int)
    parser.add_argument(
        "--daily-gross", help="comma-separated sequence with at least 56 integer amounts"
    )
    parser.add_argument(
        "--per-day-upkeep",
        help="one integer repeated for every day, or one comma-separated amount per gross day",
    )
    parser.add_argument(
        "--reactivation-spend",
        action="append",
        help="repeatable DAY:AMOUNT[:LABEL] planned reactivation spend",
    )
    parser.add_argument(
        "--chapter-target",
        action="append",
        help="repeat for exact boundaries 7,14,28,42,56 as DAY:AMOUNT",
    )
    parser.add_argument(
        "--manual-extra",
        action="append",
        help="repeatable DAY:AMOUNT[:LABEL] optional extra repayment",
    )
    parser.add_argument(
        "--policy",
        choices=("all",) + POLICY_IDS,
        default="all",
    )
    parser.add_argument(
        "--include-ledger",
        action="store_true",
        help="include daily ledgers in the default multi-scenario sensitivity report",
    )
    parser.add_argument("--self-test", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.self_test:
            report = run_self_tests()
        else:
            policies = _selected_policies(args.policy)
            custom_raw = _custom_raw_from_args(args)
            reference = load_audit_income_reference(args.artifact.resolve())
            if custom_raw is None:
                report = make_sensitivity_report(
                    reference, policies, include_ledger=args.include_ledger
                )
            else:
                config = normalize_config(custom_raw)
                report = {
                    "status": "PROVISIONAL_POLICY_COMPARISON",
                    "balance_verdict": "NOT_EVALUATED",
                    "base_year_days": BASE_YEAR_DAYS,
                    "chapter_days": list(CHAPTER_DAYS),
                    "audit_income_reference": reference,
                    "input_summary": {
                        "scenario_id": config.scenario_id,
                        "starting_cash": config.starting_cash,
                        "principal": config.principal,
                        "total_days": config.total_days,
                        "daily_gross_sequence": list(config.daily_gross),
                        "per_day_upkeep_schedule": list(config.daily_upkeep),
                        "reactivation_spends": [
                            {
                                "day": spend.day,
                                "amount": spend.amount,
                                "label": spend.label,
                            }
                            for spend in config.reactivation_spends
                        ],
                        "chapter_cumulative_targets": {
                            str(day): config.chapter_targets[day]
                            for day in CHAPTER_DAYS
                        },
                        "manual_extra_repayments": [
                            {
                                "day": spend.day,
                                "amount": spend.amount,
                                "label": spend.label,
                            }
                            for spend in config.manual_extra_repayments
                        ],
                    },
                    "policy_definitions": policy_definitions(),
                    "results": [
                        simulate_policy(config, policy, include_ledger=True)
                        for policy in policies
                    ],
                    "interpretation_limits": [
                        BALANCE_DISCLAIMER,
                        AUDIT_LIMIT_KO,
                        PARTIAL_SETTLEMENT_LIMIT,
                    ],
                }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (EconomyInputError, json.JSONDecodeError, OSError) as exc:
        print(
            json.dumps(
                {
                    "status": "INPUT_ERROR",
                    "error": str(exc),
                    "balance_verdict": "NOT_EVALUATED",
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
