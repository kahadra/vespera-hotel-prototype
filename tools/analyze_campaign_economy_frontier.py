from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


if __package__:
    from .campaign_finance_runtime import (
        BALANCE_VERDICT as RUNTIME_BALANCE_VERDICT,
        CONTRACT_STATUS as RUNTIME_CONTRACT_STATUS,
        DEBT_DEADLINE_STAGE as RUNTIME_DEBT_DEADLINE_STAGE,
        DEBT_GATE_ID as RUNTIME_DEBT_GATE_ID,
        FinanceSimulationError,
        MAX_SAFE_INTEGER as RUNTIME_MAX_SAFE_INTEGER,
        SETTLEMENT_SEQUENCE as RUNTIME_SETTLEMENT_SEQUENCE,
        commit_day_result,
        create_finance_state,
        debt_gate_evidence,
        settle_day,
        unlock_true_extension,
    )
else:
    from campaign_finance_runtime import (
        BALANCE_VERDICT as RUNTIME_BALANCE_VERDICT,
        CONTRACT_STATUS as RUNTIME_CONTRACT_STATUS,
        DEBT_DEADLINE_STAGE as RUNTIME_DEBT_DEADLINE_STAGE,
        DEBT_GATE_ID as RUNTIME_DEBT_GATE_ID,
        FinanceSimulationError,
        MAX_SAFE_INTEGER as RUNTIME_MAX_SAFE_INTEGER,
        SETTLEMENT_SEQUENCE as RUNTIME_SETTLEMENT_SEQUENCE,
        commit_day_result,
        create_finance_state,
        debt_gate_evidence,
        settle_day,
        unlock_true_extension,
    )


BASE_YEAR_DAYS = 56
CHAPTER_DAYS = (7, 14, 28, 42, 56)
REPORT_SCHEMA_VERSION = 2
MAX_SAFE_INTEGER = RUNTIME_MAX_SAFE_INTEGER
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
RUNTIME_SETTLEMENT_CONTRACT = (
    "Every comparison policy is an analysis agent that selects one explicit manualRepayment within "
    "the available cash and remaining debt. The runtime applies commit -> explicit repayment -> "
    "checkpoint atomically; it never performs an implicit mandatory debit or silently truncates a "
    "player request. Reactivation and room-service inputs represent preparation costs already paid "
    "from live cash before result commit, so an unaffordable preparation bundle rejects the analysis "
    "path before operation. Operating and checkpoint failures terminate the simulated route immediately."
)
RUNTIME_CONFORMANCE_SCOPE = (
    "CAMPAIGN_FINANCE_KERNEL_ONLY_WITH_PREPAID_RESOLVED_DAILY_INPUTS"
)
RUNTIME_CONFORMANCE_EXCLUDES = (
    "guest generation, placement/scoring, upgrade offers and eligibility, room-state eligibility, "
    "and full GameController rollback are outside this analyzer; reactivation and room-service "
    "amounts are resolved inputs that must already have been payable from live cash"
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
    room_service_spends: tuple[Spend, ...]
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
    if len(daily_gross) not in (BASE_YEAR_DAYS, 70):
        raise EconomyInputError(
            f"daily_gross_sequence must contain exactly {BASE_YEAR_DAYS} or 70 days"
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
    room_service_spends = _normalize_spends(
        raw.get("room_service_spends"),
        "room_service_spends",
        total_days,
        "ROOM_SERVICE",
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
        + sum(spend.amount for spend in room_service_spends)
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
        room_service_spends=room_service_spends,
        chapter_targets=chapter_targets,
        manual_extra_repayments=manual_extra,
    )


def _group_spends(spends: tuple[Spend, ...]) -> dict[int, list[Spend]]:
    grouped: dict[int, list[Spend]] = {}
    for spend in spends:
        grouped.setdefault(spend.day, []).append(spend)
    return grouped


def _daily_auto_cumulative_target(principal: int, day: int) -> int:
    if day >= BASE_YEAR_DAYS:
        return principal
    return (principal * day + BASE_YEAR_DAYS - 1) // BASE_YEAR_DAYS


def _runtime_configs(config: EconomyConfig) -> tuple[dict[str, Any], dict[str, Any]]:
    shared = {
        "version": 1,
        "contract_status": RUNTIME_CONTRACT_STATUS,
        "debt_deadline_stage": RUNTIME_DEBT_DEADLINE_STAGE,
        "debt_gate_id": RUNTIME_DEBT_GATE_ID,
        "starting_cash": config.starting_cash,
        "principal": config.principal,
        "chapter_cumulative_targets": {
            str(day): config.chapter_targets[day] for day in CHAPTER_DAYS
        },
    }
    base = {
        **shared,
        "id": f"{config.scenario_id}__RUNTIME_BASE",
        "total_stages": BASE_YEAR_DAYS,
    }
    extended = {
        **shared,
        "id": f"{config.scenario_id}__RUNTIME_TRUE_EXTENSION",
        "total_stages": 70,
    }
    return base, extended


def _policy_repayment_selection(
    config: EconomyConfig,
    policy_id: str,
    day: int,
    cumulative_repayment: int,
    available_cash: int,
    remaining_principal: int,
    scheduled_manual_requested: int,
) -> dict[str, Any]:
    ignored_manual_requested = 0
    checkpoint_gap = 0
    if day > BASE_YEAR_DAYS:
        strategy_target_requested = 0
        ignored_manual_requested = scheduled_manual_requested
        reason = "POST_DEADLINE_REPAYMENT_DISABLED"
    elif policy_id == POLICY_CHAPTER_MANUAL:
        if day in config.chapter_targets:
            checkpoint_gap = max(
                0, config.chapter_targets[day] - cumulative_repayment
            )
        strategy_target_requested = checkpoint_gap + scheduled_manual_requested
        reason = "CHECKPOINT_GAP_PLUS_SCHEDULED_EXTRA"
    elif policy_id == POLICY_FINAL_LUMP:
        strategy_target_requested = (
            remaining_principal if day == BASE_YEAR_DAYS else 0
        )
        ignored_manual_requested = scheduled_manual_requested
        reason = "FINAL_DAY_POLICY_AGENT"
    elif policy_id == POLICY_DAILY_AUTO:
        desired_cumulative = _daily_auto_cumulative_target(config.principal, day)
        strategy_target_requested = max(
            0, desired_cumulative - cumulative_repayment
        )
        ignored_manual_requested = scheduled_manual_requested
        reason = "DAILY_LINEAR_POLICY_AGENT"
    else:  # guarded by simulate_policy
        raise EconomyInputError(f"unknown repayment policy {policy_id!r}")

    selected_manual_repayment = min(
        strategy_target_requested,
        available_cash,
        remaining_principal,
    )
    return {
        "reason": reason,
        "strategy_target_requested": strategy_target_requested,
        "selected_manual_repayment": selected_manual_repayment,
        "selection_was_bounded": (
            selected_manual_repayment != strategy_target_requested
        ),
        "checkpoint_gap_requested": checkpoint_gap,
        "scheduled_manual_requested": scheduled_manual_requested,
        "ignored_manual_requested_by_policy": ignored_manual_requested,
    }


def _legacy_checkpoint(checkpoint: dict[str, Any] | None) -> dict[str, Any] | None:
    if checkpoint is None:
        return None
    reached = checkpoint["outcome"] in {"MET", "DEBT_CLEARED"}
    return {
        "day": checkpoint["stageNumber"],
        "cumulative_target": checkpoint["targetAmount"],
        "cumulative_repayment": checkpoint["cumulativeRepayment"],
        "gap": checkpoint["shortfallAmount"],
        "status": "REACHED" if reached else "MISSED",
        "runtime_outcome": checkpoint["outcome"],
    }


def simulate_policy(
    config: EconomyConfig,
    policy_id: str,
    *,
    include_ledger: bool = True,
) -> dict[str, Any]:
    if policy_id not in POLICY_IDS:
        raise EconomyInputError(f"unknown repayment policy {policy_id!r}")
    reactivation_by_day = _group_spends(config.reactivation_spends)
    room_service_by_day = _group_spends(config.room_service_spends)
    manual_by_day = _group_spends(config.manual_extra_repayments)
    base_config, extended_config = _runtime_configs(config)
    active_config = base_config
    state = create_finance_state(base_config)
    ledger: list[dict[str, Any]] = []
    checkpoints: list[dict[str, Any]] = []
    base_deadline_snapshot: dict[str, Any] | None = None
    extension_unlocked = False
    analysis_rejection: dict[str, Any] | None = None
    failed_day_preparation = {
        "day": None,
        "reactivation": 0,
        "room_service": 0,
        "total": 0,
    }
    terminal_live_cash = state["cash"]
    minimum_cash = state["cash"]
    minimum_finance_cash = state["cash"]

    for day, gross in enumerate(config.daily_gross, start=1):
        if state["status"] != "ACTIVE":
            break
        opening_cash = state["cash"]
        upkeep = config.daily_upkeep[day - 1]
        reactivation_entries = reactivation_by_day.get(day, [])
        reactivation = sum(entry.amount for entry in reactivation_entries)
        room_service_entries = room_service_by_day.get(day, [])
        room_service = sum(entry.amount for entry in room_service_entries)
        preparation_total = reactivation + room_service
        manual_entries = manual_by_day.get(day, [])
        manual_requested_source = sum(entry.amount for entry in manual_entries)
        if preparation_total > opening_cash:
            analysis_rejection = {
                "type": "UNEXECUTABLE_PREPARATION_PLAN",
                "day": day,
                "opening_finance_cash": opening_cash,
                "requested_reactivation": reactivation,
                "requested_room_service": room_service,
                "requested_preparation_total": preparation_total,
                "shortfall_amount": preparation_total - opening_cash,
                "reason": (
                    "reactivation and room-service preparation must be paid from live cash "
                    "before the day result is committed"
                ),
            }
            ledger.append(
                {
                    "day": day,
                    "period": "BASE_YEAR" if day <= BASE_YEAR_DAYS else "TRUE_EXTENSION",
                    "row_type": "ANALYSIS_PREPARATION_REJECTION",
                    "operation_attempted": False,
                    "opening_cash": opening_cash,
                    "opening_finance_cash": opening_cash,
                    "live_cash_after_preparation": opening_cash,
                    "gross": gross,
                    "upkeep": upkeep,
                    "reactivation": {
                        "amount": reactivation,
                        "items": [
                            {"label": entry.label, "amount": entry.amount}
                            for entry in reactivation_entries
                        ],
                    },
                    "room_service": {
                        "amount": room_service,
                        "items": [
                            {"label": entry.label, "amount": entry.amount}
                            for entry in room_service_entries
                        ],
                    },
                    "preparation": {
                        "requested": preparation_total,
                        "paid": 0,
                        "payable": False,
                    },
                    "cash_before_repayment": None,
                    "repayment": {
                        "requested": 0,
                        "paid": 0,
                        "selected_manual_repayment": 0,
                        "strategy_target_requested": 0,
                        "selection_was_bounded": False,
                        "mandatory_requested": 0,
                        "mandatory_paid": 0,
                        "manual_requested": 0,
                        "manual_paid": 0,
                        "automatic_requested": 0,
                        "automatic_paid": 0,
                        "ignored_manual_requested_by_policy": manual_requested_source,
                    },
                    "cumulative_repayment": state["cumulativeRepayment"],
                    "remaining_principal": state["remainingDebt"],
                    "closing_cash": opening_cash,
                    "closing_finance_cash": opening_cash,
                    "closing_live_cash": opening_cash,
                    "liquidity_shortfall": False,
                    "conservation_delta": 0,
                    "chapter_hurdle": None,
                    "runtime_checkpoint": None,
                    "runtime_status": state["status"],
                    "operating_failure": None,
                    "analysis_rejection": analysis_rejection,
                }
            )
            break

        live_cash_after_preparation = opening_cash - preparation_total
        terminal_live_cash = live_cash_after_preparation
        minimum_cash = min(minimum_cash, live_cash_after_preparation)
        operation = {
            "stageNumber": day,
            "campaignOperationId": f"ECONOMY:{config.scenario_id}:{day}",
            "campaignResultIdentity": {
                "stageNumber": day,
                "operationKind": "NORMAL",
                "templateIndex": (day - 1) % 5,
            },
            "income": gross,
            "upkeep": upkeep,
            "reactivation": reactivation,
            "roomService": room_service,
        }
        committed = commit_day_result(active_config, state, operation)
        if committed["status"] == "OPERATING_CASH_SHORTFALL":
            failure = committed["operatingFailure"]
            failed_day_preparation = {
                "day": day,
                "reactivation": reactivation,
                "room_service": room_service,
                "total": preparation_total,
            }
            ledger.append(
                {
                    "day": day,
                    "period": "BASE_YEAR" if day <= BASE_YEAR_DAYS else "TRUE_EXTENSION",
                    "row_type": "RUNTIME_OPERATING_FAILURE",
                    "operation_attempted": True,
                    "opening_cash": opening_cash,
                    "opening_finance_cash": opening_cash,
                    "live_cash_after_preparation": live_cash_after_preparation,
                    "gross": gross,
                    "upkeep": upkeep,
                    "reactivation": {
                        "amount": reactivation,
                        "items": [
                            {"label": entry.label, "amount": entry.amount}
                            for entry in reactivation_entries
                        ],
                    },
                    "room_service": {
                        "amount": room_service,
                        "items": [
                            {"label": entry.label, "amount": entry.amount}
                            for entry in room_service_entries
                        ],
                    },
                    "preparation": {
                        "requested": preparation_total,
                        "paid": preparation_total,
                        "payable": True,
                    },
                    "cash_before_repayment": None,
                    "repayment": {
                        "requested": 0,
                        "paid": 0,
                        "selected_manual_repayment": 0,
                        "strategy_target_requested": 0,
                        "selection_was_bounded": False,
                        "mandatory_requested": 0,
                        "mandatory_paid": 0,
                        "manual_requested": 0,
                        "manual_paid": 0,
                        "automatic_requested": 0,
                        "automatic_paid": 0,
                        "ignored_manual_requested_by_policy": manual_requested_source,
                    },
                    "cumulative_repayment": committed["cumulativeRepayment"],
                    "remaining_principal": committed["remainingDebt"],
                    "closing_cash": terminal_live_cash,
                    "closing_finance_cash": committed["cash"],
                    "closing_live_cash": terminal_live_cash,
                    "liquidity_shortfall": True,
                    "conservation_delta": None,
                    "chapter_hurdle": None,
                    "runtime_checkpoint": None,
                    "runtime_status": committed["status"],
                    "operating_failure": failure,
                    "analysis_rejection": None,
                }
            )
            state = committed
            minimum_finance_cash = min(minimum_finance_cash, state["cash"])
            break

        selection = _policy_repayment_selection(
            config,
            policy_id,
            day,
            committed["cumulativeRepayment"],
            committed["cash"],
            committed["remainingDebt"],
            manual_requested_source,
        )
        settled = settle_day(
            active_config,
            committed,
            {"manualRepayment": selection["selected_manual_repayment"]},
        )
        runtime_entry = settled["ledger"][-1]
        checkpoint = _legacy_checkpoint(runtime_entry["checkpoint"])
        if checkpoint is not None:
            checkpoints.append(checkpoint)

        row = {
            "day": day,
            "period": "BASE_YEAR" if day <= BASE_YEAR_DAYS else "TRUE_EXTENSION",
            "row_type": "RUNTIME_SETTLED_DAY",
            "operation_attempted": True,
            "opening_cash": opening_cash,
            "opening_finance_cash": opening_cash,
            "live_cash_after_preparation": live_cash_after_preparation,
            "gross": gross,
            "upkeep": upkeep,
            "reactivation": {
                "amount": reactivation,
                "items": [
                    {"label": entry.label, "amount": entry.amount}
                    for entry in reactivation_entries
                ],
            },
            "room_service": {
                "amount": room_service,
                "items": [
                    {"label": entry.label, "amount": entry.amount}
                    for entry in room_service_entries
                ],
            },
            "preparation": {
                "requested": preparation_total,
                "paid": preparation_total,
                "payable": True,
            },
            "cash_before_repayment": committed["cash"],
            "repayment": {
                "requested": selection["selected_manual_repayment"],
                "paid": runtime_entry["manualRepayment"],
                "selected_manual_repayment": selection["selected_manual_repayment"],
                "strategy_target_requested": selection["strategy_target_requested"],
                "selection_was_bounded": selection["selection_was_bounded"],
                "selection_reason": selection["reason"],
                "checkpoint_gap_requested": selection["checkpoint_gap_requested"],
                "scheduled_manual_requested": selection["scheduled_manual_requested"],
                "mandatory_requested": 0,
                "mandatory_paid": 0,
                "manual_requested": selection["selected_manual_repayment"],
                "manual_paid": runtime_entry["manualRepayment"],
                "automatic_requested": 0,
                "automatic_paid": 0,
                "ignored_manual_requested_by_policy": selection[
                    "ignored_manual_requested_by_policy"
                ],
            },
            "cumulative_repayment": settled["cumulativeRepayment"],
            "remaining_principal": settled["remainingDebt"],
            "closing_cash": settled["cash"],
            "closing_finance_cash": settled["cash"],
            "closing_live_cash": settled["cash"],
            "liquidity_shortfall": False,
            "conservation_delta": runtime_entry["cashConservation"]["delta"],
            "chapter_hurdle": checkpoint,
            "runtime_checkpoint": runtime_entry["checkpoint"],
            "runtime_status": settled["status"],
            "operating_failure": None,
            "analysis_rejection": None,
        }
        ledger.append(row)
        if day == BASE_YEAR_DAYS:
            base_deadline_snapshot = {
                "day": BASE_YEAR_DAYS,
                "observed": True,
                "cash": settled["cash"],
                "finance_cash": settled["cash"],
                "cumulative_repayment": settled["cumulativeRepayment"],
                "remaining_principal": settled["remainingDebt"],
                "qualified": settled["remainingDebt"] == 0,
                "status": (
                    "QUALIFIED_BY_DAY_56"
                    if settled["remainingDebt"] == 0
                    else "NOT_QUALIFIED_BY_DAY_56"
                ),
            }
            if config.total_days > BASE_YEAR_DAYS and settled["remainingDebt"] == 0:
                evidence = debt_gate_evidence(base_config, settled)
                settled = unlock_true_extension(
                    base_config,
                    extended_config,
                    settled,
                    evidence,
                )
                active_config = extended_config
                extension_unlocked = True
        state = settled
        terminal_live_cash = state["cash"]
        minimum_cash = min(minimum_cash, state["cash"])
        minimum_finance_cash = min(minimum_finance_cash, state["cash"])

    if base_deadline_snapshot is None:
        base_deadline_snapshot = {
            "day": BASE_YEAR_DAYS,
            "observed": False,
            "cash": terminal_live_cash,
            "finance_cash": state["cash"],
            "cumulative_repayment": state["cumulativeRepayment"],
            "remaining_principal": state["remainingDebt"],
            "qualified": False,
            "status": "NOT_REACHED_EARLY_TERMINAL",
            "terminal_status": (
                "ANALYSIS_INPUT_UNEXECUTABLE_PREPARATION_PLAN"
                if analysis_rejection is not None
                else state["status"]
            ),
        }

    runtime_entries = state["ledger"]
    base_entries = [entry for entry in runtime_entries if entry["stageNumber"] <= 56]
    extension_entries = [entry for entry in runtime_entries if entry["stageNumber"] > 56]
    extension_repayment = sum(entry["manualRepayment"] for entry in extension_entries)
    if extension_repayment != 0:
        raise AssertionError("runtime-conformant extension cannot contain repayment")
    failed_preparation_is_base = (
        failed_day_preparation["day"] is not None
        and failed_day_preparation["day"] <= BASE_YEAR_DAYS
    )
    base_failed_reactivation = (
        failed_day_preparation["reactivation"] if failed_preparation_is_base else 0
    )
    base_failed_room_service = (
        failed_day_preparation["room_service"] if failed_preparation_is_base else 0
    )
    base_totals = {
        "gross": sum(entry["income"] for entry in base_entries),
        "upkeep": sum(entry["upkeep"] for entry in base_entries),
        "reactivation": (
            sum(entry["reactivation"] for entry in base_entries)
            + base_failed_reactivation
        ),
        "room_service": (
            sum(entry["roomService"] for entry in base_entries)
            + base_failed_room_service
        ),
        "repayment": sum(entry["manualRepayment"] for entry in base_entries),
    }
    total_gross = sum(entry["income"] for entry in runtime_entries)
    total_upkeep = sum(entry["upkeep"] for entry in runtime_entries)
    total_reactivation = (
        sum(entry["reactivation"] for entry in runtime_entries)
        + failed_day_preparation["reactivation"]
    )
    total_room_service = (
        sum(entry["roomService"] for entry in runtime_entries)
        + failed_day_preparation["room_service"]
    )
    total_repayment = sum(entry["manualRepayment"] for entry in runtime_entries)
    pending_preparation_expense = state["cash"] - terminal_live_cash
    if pending_preparation_expense != failed_day_preparation["total"]:
        raise AssertionError("terminal finance/live cash gap must equal paid failed-day preparation")
    terminal_status = (
        "ANALYSIS_INPUT_UNEXECUTABLE_PREPARATION_PLAN"
        if analysis_rejection is not None
        else state["status"]
    )
    result = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "status": (
            "ANALYSIS_INPUT_UNEXECUTABLE_PREPARATION_PLAN"
            if analysis_rejection is not None
            else "SIMULATED_RUNTIME_CONFORMANT_PROVISIONAL"
        ),
        "runtime_conformance": True,
        "runtime_conformance_scope": RUNTIME_CONFORMANCE_SCOPE,
        "runtime_conformance_excludes": RUNTIME_CONFORMANCE_EXCLUDES,
        "full_game_controller_conformance_claimed": False,
        "path_executable": analysis_rejection is None,
        "analysis_rejection": analysis_rejection,
        "balance_verdict": RUNTIME_BALANCE_VERDICT,
        "policy_id": policy_id,
        "policy_role": (
            "runtime_conformant_analysis_strategy"
            if policy_id == POLICY_CHAPTER_MANUAL
            else "runtime_conformant_comparison_strategy"
        ),
        "settlement_assumption": "EXPLICIT_BOUNDED_MANUAL_REPAYMENT_POLICY_AGENT",
        "settlement_sequence": RUNTIME_SETTLEMENT_SEQUENCE,
        "scenario_id": config.scenario_id,
        "base_year_deadline": base_deadline_snapshot,
        "true_extension_rule": {
            "extension_days_present": config.total_days > BASE_YEAR_DAYS,
            "extension_unlocked": extension_unlocked,
            "repayment_paid_after_day_56": extension_repayment,
            "final_debt_changed_after_day_56": False,
            "repayment_after_day_56_can_retroactively_change_qualification": False,
        },
        "chapter_hurdles": checkpoints,
        "all_chapter_minimums_reached": len(checkpoints) == len(CHAPTER_DAYS) and all(
            checkpoint["status"] == "REACHED" for checkpoint in checkpoints
        ),
        "base_year_totals": base_totals,
        "whole_sequence_totals": {
            "days": state["completedStageCount"],
            "scheduled_days": config.total_days,
            "gross": total_gross,
            "upkeep": total_upkeep,
            "reactivation": total_reactivation,
            "room_service": total_room_service,
            "repayment": total_repayment,
            "closing_cash": terminal_live_cash,
            "closing_finance_cash": state["cash"],
            "terminal_live_cash": terminal_live_cash,
            "pending_preparation_expense": pending_preparation_expense,
            "failed_day_preparation": failed_day_preparation,
            "remaining_principal": state["remainingDebt"],
            "minimum_cash": minimum_cash,
            "minimum_live_cash": minimum_cash,
            "minimum_finance_cash": minimum_finance_cash,
            "liquidity_shortfall_days": [
                row["day"] for row in ledger if row["liquidity_shortfall"]
            ],
            "terminal_status": terminal_status,
            "attempted_operation_count": sum(
                1 for row in ledger if row["operation_attempted"]
            ),
        },
        "conservation_check": {
            "opening_cash_plus_gross": config.starting_cash + total_gross,
            "closing_cash_plus_outflows": (
                terminal_live_cash
                + total_upkeep
                + total_reactivation
                + total_room_service
                + total_repayment
            ),
            "delta": (
                config.starting_cash
                + total_gross
                - terminal_live_cash
                - total_upkeep
                - total_reactivation
                - total_room_service
                - total_repayment
            ),
        },
        "runtime_terminal_state": {
            "phase": state["phase"],
            "status": state["status"],
            "completed_stage_count": state["completedStageCount"],
            "operating_failure": state["operatingFailure"],
            "finance_cash": state["cash"],
            "terminal_live_cash": terminal_live_cash,
            "pending_preparation_expense": pending_preparation_expense,
            "game_terminal": state["status"] != "ACTIVE",
            "analysis_status": terminal_status,
        },
        "disclaimer": BALANCE_DISCLAIMER,
        "settlement_limit": RUNTIME_SETTLEMENT_CONTRACT,
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
    day_56_observed = base["observed"] is True
    return {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "scenario_id": result["scenario_id"],
        "policy_id": result["policy_id"],
        "policy_role": result["policy_role"],
        "runtime_conformance": result["runtime_conformance"],
        "path_executable": result["path_executable"],
        "analysis_rejection_type": (
            result["analysis_rejection"]["type"]
            if result["analysis_rejection"] is not None
            else None
        ),
        "executed_prefix_completed_days": whole["days"],
        "executed_prefix_attempted_operation_count": whole[
            "attempted_operation_count"
        ],
        "executed_prefix_gross": whole["gross"],
        "executed_prefix_upkeep": whole["upkeep"],
        "executed_prefix_reactivation": whole["reactivation"],
        "executed_prefix_room_service": whole["room_service"],
        "terminal_live_cash": whole["terminal_live_cash"],
        "terminal_finance_cash": whole["closing_finance_cash"],
        "day_56_observed": day_56_observed,
        "gross_days_1_56": totals["gross"] if day_56_observed else None,
        "upkeep_days_1_56": totals["upkeep"] if day_56_observed else None,
        "reactivation_days_1_56": (
            totals["reactivation"] if day_56_observed else None
        ),
        "room_service_days_1_56": (
            totals["room_service"] if day_56_observed else None
        ),
        "repaid_by_day_56": (
            base["cumulative_repayment"] if day_56_observed else None
        ),
        "remaining_principal_day_56": (
            base["remaining_principal"] if day_56_observed else None
        ),
        "cash_day_56": base["cash"] if day_56_observed else None,
        "day_56_gate": base["status"] if day_56_observed else None,
        "legacy_day_56_fields": {
            "deprecated": True,
            "observed_only": True,
            "meaning": (
                "legacy *_days_1_56 and *_day_56 values are populated only after "
                "day 56 has actually settled; use executed_prefix_* for early terminals"
            ),
        },
        "all_chapter_minimums_reached": result["all_chapter_minimums_reached"],
        "chapter_statuses": {
            str(checkpoint["day"]): checkpoint["status"]
            for checkpoint in result["chapter_hurdles"]
        },
        "minimum_cash": whole["minimum_cash"],
        "liquidity_shortfall_day_count": len(whole["liquidity_shortfall_days"]),
        "terminal_status": whole["terminal_status"],
        "completed_days": whole["days"],
        "balance_verdict": RUNTIME_BALANCE_VERDICT,
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
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "status": "RUNTIME_CONFORMANT_PROVISIONAL_SENSITIVITY_ANALYSIS",
        "runtime_conformance": True,
        "runtime_conformance_scope": RUNTIME_CONFORMANCE_SCOPE,
        "runtime_conformance_excludes": RUNTIME_CONFORMANCE_EXCLUDES,
        "full_game_controller_conformance_claimed": False,
        "balance_verdict": RUNTIME_BALANCE_VERDICT,
        "base_year_days": BASE_YEAR_DAYS,
        "chapter_days": list(CHAPTER_DAYS),
        "currency_contract": (
            "nonnegative JavaScript-safe integer gold inputs and aggregate exposure; "
            "cash never becomes negative; a preparation bundle above opening finance cash rejects "
            "the analysis path, while a later operating shortfall closes the executed route"
        ),
        "audit_income_reference": reference,
        "assumption_status": "ILLUSTRATIVE_ONLY",
        "assumptions": {
            "starting_cash": 60,
            "principal": 700,
            "chapter_cumulative_targets": _default_targets(700),
            "reactivation_spends": {"8": 30, "15": 45, "29": 60, "43": 75},
            "room_service_spends": {},
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
            RUNTIME_SETTLEMENT_CONTRACT,
        ],
    }


def policy_definitions() -> dict[str, str]:
    return {
        POLICY_CHAPTER_MANUAL: (
            "An analysis agent proposes the next checkpoint gap plus any player-scheduled extra amount, "
            "bounds that proposal to cash and remaining debt, and submits the result as one explicit "
            "manualRepayment. A remaining checkpoint gap closes the route immediately."
        ),
        POLICY_FINAL_LUMP: (
            "An analysis agent explicitly selects zero before day 56 and a cash/debt-bounded manual "
            "repayment on day 56. A nonzero earlier checkpoint target therefore closes this route at "
            "the first missed chapter rather than allowing a later lump-sum recovery."
        ),
        POLICY_DAILY_AUTO: (
            "On each base-year result review, an analysis agent explicitly selects a cash/debt-bounded "
            "manual repayment toward ceil(principal * day / 56). This is a comparison strategy, not an "
            "automatic debit performed by the game."
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
        "room_service_spends": [],
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
    assert conservation["runtime_conformance"] is True
    assert conservation["whole_sequence_totals"]["minimum_cash"] >= 0
    checks.append("runtime_cash_conservation_equation")

    for bad_field, bad_value in (
        ("per_day_upkeep_schedule", -1),
        ("reactivation_spends", [{"day": 1, "amount": -1}]),
        ("room_service_spends", [{"day": 1, "amount": -1}]),
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
                chapter_cumulative_targets={
                    "7": 0,
                    "14": 0,
                    "28": 0,
                    "42": 0,
                    "56": 100,
                },
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
                chapter_cumulative_targets={
                    "7": 0,
                    "14": 0,
                    "28": 0,
                    "42": 0,
                    "56": 100,
                },
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
    assert extension["whole_sequence_totals"]["remaining_principal"] == 100
    assert extension["whole_sequence_totals"]["days"] == 56
    assert extension["true_extension_rule"]["extension_unlocked"] is False
    assert extension["true_extension_rule"]["repayment_paid_after_day_56"] == 0
    assert (
        extension["true_extension_rule"][
            "repayment_after_day_56_can_retroactively_change_qualification"
        ]
        is False
    )
    checks.append("failed_day_56_does_not_consume_extension")

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
    assert lump["base_year_deadline"]["observed"] is False
    assert lump["whole_sequence_totals"]["days"] == 7
    assert lump["whole_sequence_totals"]["terminal_status"] == "CHAPTER_HURDLE_MISSED"
    lump_compact = _compact_result(lump)
    assert lump_compact["report_schema_version"] == REPORT_SCHEMA_VERSION
    assert lump_compact["executed_prefix_completed_days"] == 7
    assert lump_compact["executed_prefix_gross"] == 70
    assert lump_compact["executed_prefix_upkeep"] == 0
    assert lump_compact["terminal_live_cash"] == lump["whole_sequence_totals"][
        "terminal_live_cash"
    ]
    assert lump_compact["terminal_finance_cash"] == lump["whole_sequence_totals"][
        "closing_finance_cash"
    ]
    assert lump_compact["day_56_observed"] is False
    assert lump_compact["gross_days_1_56"] is None
    assert lump_compact["upkeep_days_1_56"] is None
    assert lump_compact["reactivation_days_1_56"] is None
    assert lump_compact["room_service_days_1_56"] is None
    assert lump_compact["repaid_by_day_56"] is None
    assert lump_compact["remaining_principal_day_56"] is None
    assert lump_compact["cash_day_56"] is None
    assert lump_compact["day_56_gate"] is None
    checks.append("day_7_terminal_compact_uses_executed_prefix_schema")
    assert daily["daily_ledger"][0]["repayment"]["manual_paid"] > 0
    assert all(result["runtime_conformance"] is True for result in comparison.values())
    assert all(
        row["closing_cash"] >= 0
        for result in comparison.values()
        for row in result["daily_ledger"]
    )
    assert set(comparison) == set(POLICY_IDS)
    checks.append("three_explicit_manual_policy_agents")

    operating_failure = simulate_policy(
        normalize_config(
            _base_self_test_raw(
                starting_cash=0,
                principal=0,
                daily_gross_sequence=[0] * BASE_YEAR_DAYS,
                per_day_upkeep_schedule=1,
                chapter_cumulative_targets={
                    "7": 0,
                    "14": 0,
                    "28": 0,
                    "42": 0,
                    "56": 0,
                },
            )
        ),
        POLICY_CHAPTER_MANUAL,
    )
    assert operating_failure["runtime_terminal_state"]["status"] == (
        "OPERATING_CASH_SHORTFALL"
    )
    assert operating_failure["whole_sequence_totals"]["days"] == 0
    assert operating_failure["whole_sequence_totals"]["closing_cash"] == 0
    assert operating_failure["whole_sequence_totals"]["liquidity_shortfall_days"] == [1]
    checks.append("operating_shortfall_is_atomic_terminal")

    prep_paid_failure = simulate_policy(
        normalize_config(
            _base_self_test_raw(
                starting_cash=10,
                principal=0,
                daily_gross_sequence=[20, 9] + [0] * (BASE_YEAR_DAYS - 2),
                per_day_upkeep_schedule=[17, 18]
                + [0] * (BASE_YEAR_DAYS - 2),
                reactivation_spends=[{"day": 2, "amount": 5}],
                room_service_spends=[{"day": 2, "amount": 8}],
                chapter_cumulative_targets={
                    "7": 0,
                    "14": 0,
                    "28": 0,
                    "42": 0,
                    "56": 0,
                },
            )
        ),
        POLICY_CHAPTER_MANUAL,
    )
    prep_totals = prep_paid_failure["whole_sequence_totals"]
    prep_terminal = prep_paid_failure["runtime_terminal_state"]
    assert prep_terminal["status"] == "OPERATING_CASH_SHORTFALL"
    assert prep_terminal["completed_stage_count"] == 1
    assert prep_terminal["finance_cash"] == 13
    assert prep_terminal["terminal_live_cash"] == 0
    assert prep_terminal["pending_preparation_expense"] == 13
    assert prep_totals["gross"] == 20
    assert prep_totals["upkeep"] == 17
    assert prep_totals["reactivation"] == 5
    assert prep_totals["room_service"] == 8
    assert prep_totals["closing_finance_cash"] == 13
    assert prep_totals["terminal_live_cash"] == 0
    assert prep_totals["minimum_cash"] == 0
    assert prep_totals["failed_day_preparation"] == {
        "day": 2,
        "reactivation": 5,
        "room_service": 8,
        "total": 13,
    }
    assert prep_paid_failure["base_year_totals"]["reactivation"] == 5
    assert prep_paid_failure["base_year_totals"]["room_service"] == 8
    assert prep_paid_failure["conservation_check"] == {
        "opening_cash_plus_gross": 30,
        "closing_cash_plus_outflows": 30,
        "delta": 0,
    }
    checks.append("prep_paid_operating_failure_conservation")

    unpayable_preparation = simulate_policy(
        normalize_config(
            _base_self_test_raw(
                starting_cash=5,
                principal=0,
                daily_gross_sequence=[100] + [0] * (BASE_YEAR_DAYS - 1),
                per_day_upkeep_schedule=0,
                reactivation_spends=[{"day": 1, "amount": 6}],
                chapter_cumulative_targets={
                    "7": 0,
                    "14": 0,
                    "28": 0,
                    "42": 0,
                    "56": 0,
                },
            )
        ),
        POLICY_CHAPTER_MANUAL,
    )
    assert unpayable_preparation["path_executable"] is False
    assert unpayable_preparation["analysis_rejection"]["day"] == 1
    assert unpayable_preparation["analysis_rejection"]["shortfall_amount"] == 1
    assert unpayable_preparation["whole_sequence_totals"]["days"] == 0
    assert unpayable_preparation["whole_sequence_totals"]["attempted_operation_count"] == 0
    assert unpayable_preparation["whole_sequence_totals"]["closing_cash"] == 5
    assert unpayable_preparation["whole_sequence_totals"]["reactivation"] == 0
    assert unpayable_preparation["runtime_terminal_state"]["game_terminal"] is False
    assert unpayable_preparation["conservation_check"]["delta"] == 0
    assert all(
        row["closing_live_cash"] >= 0
        for row in unpayable_preparation["daily_ledger"]
    )
    checks.append("unpayable_preparation_plan_rejected_before_operation")

    post_deadline = simulate_policy(
        normalize_config(
            _base_self_test_raw(
                starting_cash=10,
                principal=0,
                daily_gross_sequence=[0] * 70,
                per_day_upkeep_schedule=0,
                room_service_spends=[{"day": 1, "amount": 3}],
                chapter_cumulative_targets={
                    "7": 0,
                    "14": 0,
                    "28": 0,
                    "42": 0,
                    "56": 0,
                },
                manual_extra_repayments=[{"day": 57, "amount": 5}],
            )
        ),
        POLICY_CHAPTER_MANUAL,
    )
    day_57 = next(row for row in post_deadline["daily_ledger"] if row["day"] == 57)
    assert post_deadline["true_extension_rule"]["extension_unlocked"] is True
    assert post_deadline["base_year_totals"]["room_service"] == 3
    assert day_57["repayment"]["manual_paid"] == 0
    assert day_57["repayment"]["ignored_manual_requested_by_policy"] == 5
    checks.append("room_service_and_zero_post_deadline_repayment")

    return {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "status": "SELF_TEST_PASS",
        "runtime_conformance": True,
        "runtime_conformance_scope": RUNTIME_CONFORMANCE_SCOPE,
        "runtime_conformance_excludes": RUNTIME_CONFORMANCE_EXCLUDES,
        "full_game_controller_conformance_claimed": False,
        "checks": checks,
        "balance_verdict": RUNTIME_BALANCE_VERDICT,
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
            args.room_service_spend,
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
    room_service = _parse_day_amount_specs(
        args.room_service_spend, "--room-service-spend", allow_label=True
    )
    if room_service is not None:
        raw["room_service_spends"] = room_service
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
            "Compare provisional 56/70-day campaign repayment strategies through the "
            "finance kernel plus a resolved/prepaid-input adapter without claiming full "
            "GameController conformance or a final balance verdict."
        )
    )
    parser.add_argument("--input", help="scenario JSON path, or - for stdin")
    parser.add_argument("--artifact", type=Path, default=DEFAULT_AUDIT_PATH)
    parser.add_argument("--scenario-id")
    parser.add_argument("--starting-cash", type=int)
    parser.add_argument("--principal", type=int)
    parser.add_argument(
        "--daily-gross", help="comma-separated sequence with exactly 56 or 70 integer amounts"
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
        "--room-service-spend",
        action="append",
        help="repeatable DAY:AMOUNT[:LABEL] resolved room-service spend",
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
                    "report_schema_version": REPORT_SCHEMA_VERSION,
                    "status": "RUNTIME_CONFORMANT_PROVISIONAL_POLICY_COMPARISON",
                    "runtime_conformance": True,
                    "runtime_conformance_scope": RUNTIME_CONFORMANCE_SCOPE,
                    "runtime_conformance_excludes": RUNTIME_CONFORMANCE_EXCLUDES,
                    "full_game_controller_conformance_claimed": False,
                    "balance_verdict": RUNTIME_BALANCE_VERDICT,
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
                        "room_service_spends": [
                            {
                                "day": spend.day,
                                "amount": spend.amount,
                                "label": spend.label,
                            }
                            for spend in config.room_service_spends
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
                        RUNTIME_SETTLEMENT_CONTRACT,
                    ],
                }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (EconomyInputError, FinanceSimulationError, json.JSONDecodeError, OSError) as exc:
        print(
            json.dumps(
                {
                    "status": "INPUT_ERROR",
                    "error": str(exc),
                    "runtime_conformance": False,
                    "balance_verdict": RUNTIME_BALANCE_VERDICT,
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
