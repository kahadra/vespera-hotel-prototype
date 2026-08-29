from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "prototype_v1.json"
RANK_IDS = ("N", "R", "SR", "SSR")
DEFAULT_SHOWCASE_SEED = 20_260_819
UINT32_MASK = 0xFFFF_FFFF
RNG_STEP = 0x6D2B79F5


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_data() -> dict[str, Any]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def index_by_id(items: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in items}


def imul(left: int, right: int) -> int:
    return (left * right) & UINT32_MASK


@dataclass
class SeededRng:
    """Python mirror of src/random.js Mulberry32 state transitions."""

    state: int

    def next_float(self) -> float:
        self.state = (self.state + RNG_STEP) & UINT32_MASK
        value = self.state
        value = imul(value ^ (value >> 15), value | 1)
        value ^= (value + imul(value ^ (value >> 7), value | 61)) & UINT32_MASK
        value &= UINT32_MASK
        value = (value ^ (value >> 14)) & UINT32_MASK
        return value / 0x1_0000_0000

    def pick_one(self, items: list[Any]) -> Any:
        require(bool(items), "Cannot pick from an empty collection")
        return items[int(self.next_float() * len(items))]

    def pick_weighted(self, items: list[Any], weight_of) -> Any:
        require(bool(items), "Cannot pick from an empty weighted collection")
        weights = [max(0.0, float(weight_of(item) or 0)) for item in items]
        total = sum(weights)
        if total <= 0:
            return self.pick_one(items)
        cursor = self.next_float() * total
        for item, weight in zip(items, weights):
            cursor -= weight
            if cursor < 0:
                return item
        return items[-1]


def rank_odds_for(data: dict[str, Any], stage: int, reputation: int) -> dict[str, int]:
    safe_stage = max(1, int(stage or 1))
    safe_reputation = max(0, int(reputation or 0))
    rows = sorted(data["rank_odds"], key=lambda row: row["min_reputation"])
    row = next(
        (candidate for candidate in reversed(rows) if candidate["min_reputation"] <= safe_reputation),
        rows[0],
    )
    ranks = index_by_id(data["ranks"])
    odds = {rank_id: int(row["odds"].get(rank_id, 0)) for rank_id in RANK_IDS}
    for index in range(len(RANK_IDS) - 1, -1, -1):
        rank_id = RANK_IDS[index]
        rank = ranks[rank_id]
        unlocked = rank["unlock_stage"] <= safe_stage and rank["min_reputation"] <= safe_reputation
        if unlocked or odds[rank_id] == 0:
            continue
        recipient = next(
            (
                lower_id
                for lower_id in reversed(RANK_IDS[:index])
                if ranks[lower_id]["unlock_stage"] <= safe_stage
                and ranks[lower_id]["min_reputation"] <= safe_reputation
            ),
            "N",
        )
        odds[recipient] += odds[rank_id]
        odds[rank_id] = 0
    odds["N"] += 100 - sum(odds.values())
    return odds


def generate_guest_offer(
    data: dict[str, Any],
    scenario: dict[str, Any],
    odds: dict[str, int],
    rng: SeededRng,
    excluded_ids: Iterable[str] = (),
) -> tuple[list[str], list[str]]:
    guests = index_by_id(data["guests"])
    blocked = set(scenario.get("fixed_guests", ())) | set(excluded_ids)
    pool = [
        guests[guest_id]
        for guest_id in scenario.get("applicant_pool", scenario.get("applicants", ()))
        if guest_id not in blocked and guest_id in guests
    ]
    offer_size = int(scenario.get("offer_size", len(pool)))
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    special_ids: list[str] = []

    def add_guest(guest: dict[str, Any] | None, special: bool = False) -> bool:
        if guest is None or guest["id"] in selected_ids or len(selected) >= offer_size:
            return False
        selected.append(guest)
        selected_ids.add(guest["id"])
        if special:
            special_ids.append(guest["id"])
        return True

    for guest_id in scenario.get("special_invite_guest_ids", ()):
        if guest_id not in blocked:
            add_guest(guests.get(guest_id), True)

    guaranteed_rank = scenario.get("guaranteed_rank")
    if guaranteed_rank and not any(guest["rank"] == guaranteed_rank for guest in selected):
        matches = [
            guest
            for guest in pool
            if guest["id"] not in selected_ids and guest["rank"] == guaranteed_rank
        ]
        require(bool(matches), f"{scenario['id']} cannot satisfy its {guaranteed_rank} guarantee")
        add_guest(rng.pick_one(matches))

    while len(selected) < offer_size:
        candidates = [
            guest
            for guest in pool
            if guest["id"] not in selected_ids and odds.get(guest["rank"], 0) > 0
        ]
        require(bool(candidates), f"{scenario['id']} cannot fill its {offer_size}-guest offer")
        available_ranks = [
            rank_id for rank_id in RANK_IDS if any(guest["rank"] == rank_id for guest in candidates)
        ]
        rank_id = rng.pick_weighted(available_ranks, lambda value: odds.get(value, 0))
        add_guest(rng.pick_one([guest for guest in candidates if guest["rank"] == rank_id]))

    return [guest["id"] for guest in selected], special_ids


def can_purchase_upgrade(
    upgrades: dict[str, dict[str, Any]], upgrade_id: str, owned_ids: Iterable[str]
) -> bool:
    owned = set(owned_ids)
    upgrade = upgrades.get(upgrade_id)
    return bool(
        upgrade
        and upgrade_id not in owned
        and all(required_id in owned for required_id in upgrade.get("requires", ()))
    )


def generate_upgrade_offer(
    data: dict[str, Any],
    stage: int,
    reputation: int,
    owned_ids: list[str],
    gold: int,
    rng: SeededRng,
) -> list[str]:
    upgrades = index_by_id(data["upgrades"])
    ranks = index_by_id(data["ranks"])
    odds = rank_odds_for(data, stage, reputation)
    eligible = [
        upgrade
        for upgrade in data["upgrades"]
        if upgrade["unlock_stage"] <= stage
        and upgrade["minimum_reputation"] <= max(0, reputation)
        and ranks[upgrade["rarity"]]["unlock_stage"] <= stage
        and can_purchase_upgrade(upgrades, upgrade["id"], owned_ids)
    ]
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    configured_sizes = data["prototype_mode"].get("upgrade_offer_sizes", {})
    offer_sizes = {
        "EXPANSION": int(configured_sizes.get("EXPANSION", 1)),
        "FACILITY": int(configured_sizes.get("FACILITY", data["prototype_mode"].get("upgrade_offer_size", 3))),
    }
    for kind in ("EXPANSION", "FACILITY"):
        kind_eligible = [upgrade for upgrade in eligible if upgrade["kind"] == kind]
        kind_selected: list[dict[str, Any]] = []
        while len(kind_selected) < offer_sizes[kind]:
            remaining = [upgrade for upgrade in kind_eligible if upgrade["id"] not in selected_ids]
            if not remaining:
                break
            available_rarities = list(dict.fromkeys(upgrade["rarity"] for upgrade in remaining))
            rarity = rng.pick_weighted(available_rarities, lambda value: odds.get(value, 0))
            same_rarity = [upgrade for upgrade in remaining if upgrade["rarity"] == rarity]
            chosen = rng.pick_weighted(same_rarity, lambda upgrade: upgrade.get("offer_weight", 1))
            kind_selected.append(chosen)
            selected.append(chosen)
            selected_ids.add(chosen["id"])

        affordable = [
            upgrade
            for upgrade in kind_eligible
            if upgrade["cost"] <= gold and upgrade["id"] not in selected_ids
        ]
        if kind_selected and not any(upgrade["cost"] <= gold for upgrade in kind_selected) and affordable:
            replacement = rng.pick_one(affordable)
            replaced = kind_selected[-1]
            selected_ids.remove(replaced["id"])
            selected[selected.index(replaced)] = replacement
            kind_selected[-1] = replacement
            selected_ids.add(replacement["id"])
    return [upgrade["id"] for upgrade in selected]


def build_board(data: dict[str, Any], owned_upgrade_ids: Iterable[str] = ()) -> dict[str, Any]:
    facilities = index_by_id(data["facilities"])
    upgrades = index_by_id(data["upgrades"])
    rooms = {
        room["id"]: {**room, "attributes": set(room.get("attributes", ())) }
        for room in data["rooms"]
    }
    unlocked = {room["id"] for room in data["rooms"] if room.get("built_from_start", True)}
    blocked: set[str] = set()
    links: set[frozenset[str]] = set()
    bonuses: list[dict[str, Any]] = []
    active_facilities: list[str] = []
    for upgrade_id in dict.fromkeys(owned_upgrade_ids):
        upgrade = upgrades.get(upgrade_id)
        if not upgrade:
            continue
        unlocked.update(upgrade.get("room_unlocks", ()))
        facility = facilities.get(upgrade.get("facility_id", ""))
        if not facility:
            continue
        active_facilities.append(facility["id"])
        for change in facility.get("room_attribute_changes", ()):
            room = rooms[change["room_id"]]
            room["attributes"].difference_update(change.get("remove", ()))
            room["attributes"].update(change.get("add", ()))
        blocked.update(facility.get("blocked_rooms", ()))
        links.update(frozenset(link) for link in facility.get("adjacency_links", ()))
        bonuses.extend(facility.get("room_bonuses", ()))
    blocked.update(set(rooms) - unlocked)
    return {
        "rooms": rooms,
        "unlocked": unlocked,
        "blocked": blocked,
        "links": links,
        "bonuses": bonuses,
        "facilities": active_facilities,
    }


def adjacent(left_id: str, right_id: str, board: dict[str, Any]) -> bool:
    if not left_id or not right_id or left_id == right_id:
        return False
    if frozenset((left_id, right_id)) in board["links"]:
        return True
    left = board["rooms"][left_id]
    right = board["rooms"][right_id]
    return left["floor"] == right["floor"] and abs(left["wing"] - right["wing"]) == 1


def merged_hard_rules(data: dict[str, Any], guest_id: str) -> list[dict[str, Any]]:
    guests = index_by_id(data["guests"])
    species = index_by_id(data["species"])
    ranks = index_by_id(data["ranks"])
    guest = guests[guest_id]
    return [
        *species[guest["species"]].get("hard_constraints", ()),
        *ranks[guest["rank"]].get("hard_constraints", ()),
        *guest.get("hard_constraints", ()),
    ]


def hard_rule_ok(
    rule: dict[str, Any], guest_id: str, placements: dict[str, str], board: dict[str, Any]
) -> bool:
    room_id = placements[guest_id]
    room = board["rooms"][room_id]
    rule_type = rule["type"]
    if rule_type == "ROOM_NOT_HAS":
        return rule["attribute"] not in room["attributes"]
    if rule_type == "ROOM_HAS":
        return rule["attribute"] in room["attributes"]
    if rule_type == "FLOOR_IS":
        return room["floor"] == rule["floor"]
    if rule_type == "FLOOR_AT_LEAST":
        return room["floor"] >= rule["floor"]
    if rule_type == "FLOOR_AT_MOST":
        return room["floor"] <= rule["floor"]
    if rule_type == "ELEVATOR_DISTANCE_AT_LEAST":
        return room["wing"] >= rule["distance"]
    if rule_type == "ELEVATOR_DISTANCE_AT_MOST":
        return room["wing"] <= rule["distance"]
    if rule_type == "MUST_ADJACENT_GUEST":
        return rule["guest_id"] in placements and adjacent(room_id, placements[rule["guest_id"]], board)
    if rule_type == "NO_OCCUPIED_ADJACENT":
        return all(
            other_id == guest_id or not adjacent(room_id, other_room, board)
            for other_id, other_room in placements.items()
        )
    if rule_type == "MUST_SHARE_FLOOR":
        return any(
            other_id != guest_id and board["rooms"][other_room]["floor"] == room["floor"]
            for other_id, other_room in placements.items()
        )
    raise AssertionError(f"Unsupported hard rule in validator: {rule_type}")


def find_valid_assignment(
    data: dict[str, Any], guest_ids: list[str], owned_upgrade_ids: Iterable[str] = ()
) -> dict[str, str] | None:
    """Return the first valid representative placement; never enumerate scores or all permutations."""

    board = build_board(data, owned_upgrade_ids)
    rooms = [room_id for room_id in board["rooms"] if room_id not in board["blocked"]]
    rules = {guest_id: merged_hard_rules(data, guest_id) for guest_id in guest_ids}

    def unary_ok(guest_id: str, room_id: str) -> bool:
        unary_types = {
            "ROOM_NOT_HAS", "ROOM_HAS", "FLOOR_IS", "FLOOR_AT_LEAST", "FLOOR_AT_MOST",
            "ELEVATOR_DISTANCE_AT_LEAST", "ELEVATOR_DISTANCE_AT_MOST",
        }
        placement = {guest_id: room_id}
        return all(
            hard_rule_ok(rule, guest_id, placement, board)
            for rule in rules[guest_id]
            if rule["type"] in unary_types
        )

    domains = {
        guest_id: [room_id for room_id in rooms if unary_ok(guest_id, room_id)]
        for guest_id in guest_ids
    }
    if any(not domain for domain in domains.values()):
        return None
    ordered = sorted(guest_ids, key=lambda guest_id: (len(domains[guest_id]), guest_id))
    placements: dict[str, str] = {}
    used: set[str] = set()

    def search(index: int) -> dict[str, str] | None:
        if index == len(ordered):
            if all(
                hard_rule_ok(rule, guest_id, placements, board)
                for guest_id in guest_ids
                for rule in rules[guest_id]
            ):
                return dict(placements)
            return None
        guest_id = ordered[index]
        for room_id in domains[guest_id]:
            if room_id in used:
                continue
            placements[guest_id] = room_id
            used.add(room_id)
            result = search(index + 1)
            if result:
                return result
            used.remove(room_id)
            del placements[guest_id]
        return None

    return search(0)


def synergy_and_conflict_totals(
    data: dict[str, Any], guest_ids: list[str], placements: dict[str, str]
) -> tuple[int, int]:
    guests = index_by_id(data["guests"])
    species = index_by_id(data["species"])
    rooms = index_by_id(data["rooms"])
    grouped: dict[str, list[str]] = {}
    for guest_id in guest_ids:
        grouped.setdefault(guests[guest_id]["species"], []).append(guest_id)
    synergy = 0
    for species_id, members in grouped.items():
        active = [row for row in species[species_id]["synergy_thresholds"] if len(members) >= row["count"]]
        if active:
            row = max(active, key=lambda value: value["count"])
            synergy += (row.get("points_per_guest", row.get("points", 0))) * len(members)
    conflict = 0
    for row in data.get("species_conflicts", ()):
        left, right = row["species"]
        affected: set[str] = set()
        for left_id in grouped.get(left, ()):
            for right_id in grouped.get(right, ()):
                if rooms[placements[left_id]]["floor"] == rooms[placements[right_id]]["floor"]:
                    affected.update((left_id, right_id))
        conflict += row["points"] * len(affected)
    return synergy, conflict


def revisit_bonus_for(data: dict[str, Any], history: dict[str, int] | None) -> int:
    if not history or not history.get("visits"):
        return 0
    thresholds = data.get("balance", {}).get("revisit_bonus_thresholds") or [
        {"min_satisfaction": 0, "points": 1},
        {"min_satisfaction": 5, "points": 2},
        {"min_satisfaction": 10, "points": 3},
    ]
    matched = [row for row in thresholds if history["lastSatisfaction"] >= row["min_satisfaction"]]
    return max(matched, key=lambda row: row["min_satisfaction"])["points"] if matched else 0


def showcase_signature(data: dict[str, Any], seed: int) -> dict[str, Any]:
    rng = SeededRng(seed & UINT32_MASK)
    reputations_after = {1: 4, 2: 8, 3: 14, 4: 20, 5: 24}
    gold = 200
    owned: list[str] = []
    signature: dict[str, Any] = {"seed": seed, "guests": [], "upgrades": []}
    upgrades = index_by_id(data["upgrades"])
    for scenario in sorted(data["scenarios"], key=lambda item: item["stage"]):
        stage = scenario["stage"]
        odds = rank_odds_for(data, stage, reputations_after.get(stage - 1, 0))
        offer, special = generate_guest_offer(data, scenario, odds, rng)
        signature["guests"].append({"stage": stage, "ids": offer, "special": special})
        if stage >= data["prototype_mode"]["total_nights"]:
            continue
        next_stage = stage + 1
        upgrade_offer = generate_upgrade_offer(
            data, next_stage, reputations_after[stage], owned, gold, rng
        )
        signature["upgrades"].append({"stage": next_stage, "ids": upgrade_offer})
        for kind in ("EXPANSION", "FACILITY"):
            chosen = next(
                (
                    upgrade_id
                    for upgrade_id in upgrade_offer
                    if upgrades[upgrade_id]["kind"] == kind
                    and upgrades[upgrade_id]["cost"] <= gold
                    and can_purchase_upgrade(upgrades, upgrade_id, owned)
                ),
                None,
            )
            if chosen:
                owned.append(chosen)
                gold -= upgrades[chosen]["cost"]
    signature["owned"] = owned
    signature["rng_state"] = rng.state
    return signature


def validate_static_data(data: dict[str, Any]) -> dict[str, Any]:
    collections = ("rooms", "species", "ranks", "guests", "facilities", "upgrades", "scenarios")
    for name in collections:
        ids = [item["id"] for item in data[name]]
        require(len(ids) == len(set(ids)), f"Duplicate IDs in {name}")

    require(data.get("schema_version") == 4, "Showcase data must use schema_version 4")
    completion = data.get("run_completion", {})
    require(completion.get("record_namespace"), "Run record namespace is required")
    endings = completion.get("ending_rules", [])
    require(endings, "At least one data-driven ending rule is required")
    require(len({ending.get("id") for ending in endings}) == len(endings), "Ending ids must be unique")
    ending_metrics = {
        "completed_nights", "total_income", "reputation_delta", "final_gold",
        "final_reputation", "accepted_guests", "rejected_guests", "canceled_guests",
        "purchased_upgrades", "emergency_nights", "foresight_retries", "expected_nights",
    }
    require(
        all(
            condition.get("metric") in ending_metrics
            and condition.get("operator") in {"GTE", "LTE", "EQ"}
            and isinstance(condition.get("value"), (int, float))
            for ending in endings
            for condition in ending.get("conditions", ())
        ),
        "Ending conditions must use supported metrics and operators",
    )
    fallback = completion.get("fallback_ending", {})
    require(fallback.get("id"), "A fallback ending is required")
    require(fallback.get("id") not in {ending.get("id") for ending in endings}, "Fallback ending id must be unique")
    mode = data.get("prototype_mode", {})
    require(mode.get("type") == "SHOWCASE" and mode.get("accelerated") is True, "Accelerated showcase metadata is missing")
    require(mode.get("total_nights") == 5 and len(data["scenarios"]) == 5, "Exactly five playable nights are required")
    require(bool(mode.get("notice")) and bool(mode.get("production_progression_note")), "Showcase/production progression copy is missing")
    require(
        mode.get("upgrade_offer_sizes") == {"EXPANSION": 1, "FACILITY": 3},
        "Renovation offers must expose one expansion and three facility/interior choices",
    )
    require(len(data["species"]) == 4, "Exactly four species are required")
    require(len(data["ranks"]) == 4 and {rank["id"] for rank in data["ranks"]} == set(RANK_IDS), "Ranks must be N/R/SR/SSR")
    require(len(data["guests"]) == 16, "The showcase contract requires exactly 16 guests")
    require(len(data["facilities"]) >= 8, "At least eight facilities are required")
    require(len(data["upgrades"]) >= 11, "At least eleven facility/expansion upgrades are required")
    require([scenario["stage"] for scenario in data["scenarios"]] == [1, 2, 3, 4, 5], "Scenario stages must be ordered 1..5")
    require(
        data.get("balance", {}).get("booking_capacity_per_expansion_room") == 1,
        "Each completed expansion room must add exactly one booking slot",
    )
    require(
        [scenario["capacity"] for scenario in data["scenarios"]] == [5, 5, 5, 5, 5],
        "Every scenario must retain the five-guest base booking limit",
    )
    require(
        all("room_quality_required" not in guest for guest in data["guests"]),
        "Unused room_quality_required fields must not remain in guest data",
    )
    require(
        all("satisfied_reputation" not in guest for guest in data["guests"]),
        "A valid placement must not award fixed reputation",
    )

    ranks = index_by_id(data["ranks"])
    guests = index_by_id(data["guests"])
    upgrades = index_by_id(data["upgrades"])
    require({guest["rank"] for guest in data["guests"]} == set(RANK_IDS), "Every guest rank must be represented")
    require({facility["rarity"] for facility in data["facilities"]} == set(RANK_IDS), "Every facility rank must be represented")
    require({upgrade["rarity"] for upgrade in data["upgrades"]} == set(RANK_IDS), "Every upgrade rank must be represented")
    ordered_ranks = sorted(data["ranks"], key=lambda rank: rank["order"])
    require(
        all(
            ordered_ranks[index]["reputation_influence"]
            < ordered_ranks[index + 1]["reputation_influence"]
            for index in range(len(ordered_ranks) - 1)
        ),
        "Higher guest ranks must have greater reputation influence",
    )
    require(
        all(
            len(ordered_ranks[index].get("soft_preferences", ())) + len(ordered_ranks[index].get("soft_dislikes", ()))
            <= len(ordered_ranks[index + 1].get("soft_preferences", ())) + len(ordered_ranks[index + 1].get("soft_dislikes", ()))
            for index in range(len(ordered_ranks) - 1)
        ),
        "Higher guest ranks must not have fewer preference/dislike conditions",
    )
    for rank in ordered_ranks:
        require(rank.get("positive_satisfaction_threshold", 0) > 0, f"{rank['id']} needs a positive-review threshold")
        for dislike in rank.get("soft_dislikes", ()):
            require(dislike.get("points", 0) < 0, f"{rank['id']} dislikes must reduce internal satisfaction")
            require(dislike.get("ignored_at_prestige_gap", 0) >= 1, f"{rank['id']} dislikes need a prestige tolerance gap")
    render_source = (ROOT / "src" / "render.js").read_text(encoding="utf-8")
    state_source = (ROOT / "src" / "state.js").read_text(encoding="utf-8")
    input_source = (ROOT / "src" / "input.js").read_text(encoding="utf-8")
    save_source = (ROOT / "src" / "save.js").read_text(encoding="utf-8")
    data_source = (ROOT / "src" / "data.js").read_text(encoding="utf-8")
    presenter_source = (ROOT / "submission_video" / "presenter.js").read_text(encoding="utf-8")
    player_facing_meta_terms = ("압축", "쇼케이스", "시연", "SHOWCASE", "ACCELERATED")
    player_data_text = json.dumps(
        {
            **data,
            "prototype_mode": {
                key: value
                for key, value in data["prototype_mode"].items()
                if key != "type"
            },
        },
        ensure_ascii=False,
    )
    require(
        all(term not in render_source and term not in player_data_text for term in player_facing_meta_terms),
        "Build/meta terminology must not appear in player-facing game copy",
    )
    require(
        all(token in render_source for token in (
            "개장 전 초청 영업에",
            "PRE-OPENING INVITATIONAL · 5 NIGHTS",
            "PRE-OPENING PROGRAM",
            "PRE-OPENING NIGHT ${controller.currentNightNumber} COMPLETE",
            "PRE-OPENING NIGHT ${controller.currentNightNumber} OF ${controller.totalNights}",
            "개장 전 초청 영업에서 확인한 호텔의 운영 기록입니다.",
            "PRE-OPENING INVITATIONAL COMPLETE",
            "개장 전 다섯 영업을 마쳤습니다.",
            'data-video-target="guest-reviews"',
            "오늘의 투숙 후기",
            "내부 만족도 수치 대신",
            'class="elevator-landing',
            "A열 객실과 바로 인접",
            'classes.push("elevator-adjacent")',
            'classes.push("noisy-room")',
            '"open-result-review"',
            'data-action="start-day-business"',
            'data-action="restart-day-through-secretary"',
            'data-action="retry-stage"',
            "비서에게 마감 장부를 건넨다",
            "이번 영업 다시",
            "아침 장부부터 다시 읽어 줘.",
            "처음 펼친 장부인데",
        )),
        "PRE-OPENING hotel-fiction copy is incomplete across the player flow",
    )
    permanent_unlock_copy = "영구 해금이 아닌 시연용 특별 초청입니다."
    require(
        "영구 해금" not in render_source and presenter_source.count(permanent_unlock_copy) == 1,
        "The permanent-unlock disclaimer must appear once in the video and not repeat in game UI",
    )
    require(
        'action === "unplace"' not in input_source
        and 'data-action="unplace"' not in render_source
        and "target.dataset.roomId && controller.state.selectedGuestId" not in input_source,
        "Room placement/removal must not remain available through click actions",
    )
    require(
        all(token in input_source for token in ('addEventListener("dragstart"', 'addEventListener("drop"')),
        "Placement and removal require drag/drop handlers",
    )
    require(
        all(token in state_source for token in (
            "roomCapacitySummary()",
            "get currentServiceLimit()",
            "overPhysicalCapacity",
        )),
        "Controller booking and physical-capacity contracts are incomplete",
    )
    require(
        all(token in render_source for token in (
            'data-action="open-reservation-board"',
            'data-room-state="${roomState}"',
            'data-video-target="reservation-existing-layout"',
        )),
        "Reservation room-ledger states and video target are incomplete",
    )
    require("퍼즐" not in render_source, "Player-facing render copy must describe hotel operations, not a puzzle")
    require(
        all(token in save_source for token in (
            "RUN_SAVE_SCHEMA_VERSION",
            "ACTIVE_RUN_STORAGE_KEY",
            "data_schema_version",
            "readActiveRunSave",
            "writeActiveRunSave",
            "clearActiveRunSave",
            "stage_checkpoint",
            "RUN_SAVE_SCHEMA_VERSION = 5",
            "PROFILE_SCHEMA_VERSION = 1",
            "PROFILE_STORAGE_KEY",
            "activeRunStorageKey(data)",
            "readProfile",
            "writeProfile",
        )),
        "Versioned profile and mode-run checkpoint contract is incomplete",
    )
    require('data-action="resume"' in render_source and "지난 영업 이어하기" in render_source, "Checkpoint resume action is missing")
    require(
        all(token in state_source for token in (
            'DAY_OPENING: "DAY_OPENING"',
            'RESULT_REVIEW: "RESULT_REVIEW"',
            "beginOperatingDay(index)",
            "restartDayThroughSecretary()",
            'get isEndlessMode()',
        ))
        and all(token in input_source for token in (
            'action === "open-result-review"',
            'action === "restart-day-through-secretary"',
        )),
        "Campaign-only secretary day-opening and result-review contract is incomplete",
    )
    require(
        all(token in state_source for token in (
            'NEW_GAME: "NEW_GAME"',
            'STORY: "STORY"',
            "confirmNewGame()",
            "continueStory()",
            "prepareNextUpgrade()",
            "persistProfileKnowledge()",
            "setGreyboxEndingRoute(routeId)",
            "relationshipProgressByRole",
            "speciesAffinityById",
        ))
        and all(token in render_source for token in (
            'data-action="confirm-new-game"',
            'data-action="continue-story"',
            'data-action="set-greybox-ending-route"',
            "인연을 맺은 손님들의 이후",
            "상속 조건을 채우지 못했습니다.",
        ))
        and "createCampaignGreyboxData" in data_source
        and all(ending_id in data_source for ending_id in (
            "BAD_CHAPTER_HURDLE",
            "BAD_OPERATIONAL",
            "NORMAL_STEWARDSHIP",
            "SPECIES_HEROINE_",
            "TRUE_PEACE",
            "TRUE_HAREM",
            "dream_demon_other_species_network",
            "OPTIONAL_WITCH_AWAKENING",
            "OPTIONAL_DREAM_DEMON_REINCARNATION",
            'formal_rank_ids: ["N", "R", "SR", "SSR", "UR"]',
            'minimum_guest_rank_id: "SR"',
            "other_species_occupancy_preferences",
        )),
        "Greybox campaign new-game, story, six-tier ending, and epilogue spine is incomplete",
    )
    require(
        all(term not in render_source for term in ("예지", "관측", "시뮬레이션", "세계선")),
        "Player-facing UI must not directly reveal the hidden interpretation of replay",
    )
    require("현재 만족도 합계" not in render_source and "지난 만족 ${" not in render_source, "Internal satisfaction numbers must remain hidden")
    require(
        "연박 객실은 공사 불가" in render_source,
        "Renovation UI must explain why a stayover room cannot be changed",
    )
    for rank_id in ("SR", "SSR"):
        rank = ranks[rank_id]
        require(
            all(rule["type"] != "NO_OCCUPIED_ADJACENT" for rule in rank.get("hard_constraints", ())),
            f"{rank_id} empty-adjacent-room request must not be a hard constraint",
        )
        require(
            any(rule["type"] == "NO_OCCUPIED_ADJACENT" for rule in rank.get("soft_preferences", ())),
            f"{rank_id} needs the optional empty-adjacent-room preference",
        )

    previous_threshold = -1
    for row in data["rank_odds"]:
        require(row["min_reputation"] > previous_threshold, "Reputation odds rows must be strictly ordered")
        previous_threshold = row["min_reputation"]
        require(set(row["odds"]) == set(RANK_IDS), "Every odds row must contain all ranks")
        require(all(isinstance(row["odds"][rank_id], int) and row["odds"][rank_id] >= 0 for rank_id in RANK_IDS), "Rank odds must be non-negative integers")
        require(sum(row["odds"].values()) == 100, "Every raw rank odds row must sum to 100")
        for stage in range(1, 6):
            odds = rank_odds_for(data, stage, row["min_reputation"])
            require(sum(odds.values()) == 100, f"Effective odds do not sum to 100 at stage {stage}")
            for rank_id in RANK_IDS:
                rank = ranks[rank_id]
                if rank["unlock_stage"] > stage or rank["min_reputation"] > row["min_reputation"]:
                    require(odds[rank_id] == 0, f"Locked {rank_id} has non-zero odds at stage {stage}")
    require(rank_odds_for(data, 1, 999) == {"N": 100, "R": 0, "SR": 0, "SSR": 0}, "Stage 1 must remain N-only")

    hidden_ids: set[str] = set()
    for species in data["species"]:
        hidden = species.get("hidden_preferences_by_rank", {})
        require(set(hidden) == set(RANK_IDS), f"{species['id']} must define all hidden-rank buckets")
        require(hidden["N"] == [], f"{species['id']} N guests must not have hidden preferences")
        for rank_id in ("R", "SR", "SSR"):
            require(bool(hidden[rank_id]), f"{species['id']}:{rank_id} needs a hidden soft preference")
            for rule in hidden[rank_id]:
                require(rule.get("id") and rule["id"] not in hidden_ids, "Hidden preference IDs must be present and unique")
                hidden_ids.add(rule["id"])
                require(rule.get("points", 0) > 0, f"{rule['id']} must award positive soft points")
                require(rule.get("required") is not True and rule.get("hard") is not True and rule.get("kind") != "HARD", f"{rule['id']} cannot be a hard rule")
        require(bool(species.get("synergy_thresholds")), f"{species['id']} needs a species synergy")
    require(all(not any(key.startswith("hidden_") for key in guest) for guest in data["guests"]), "Hidden rules must be species x rank data, not personal guest fields")
    require(bool(data.get("species_conflicts")), "Species conflicts are required")
    require(all(row.get("scope") == "SAME_FLOOR" and row.get("points", 0) < 0 for row in data["species_conflicts"]), "Species conflicts must be soft same-floor penalties")

    fifth = data["scenarios"][4]
    require(fifth.get("guaranteed_rank") == "SSR", "Night 5 must guarantee SSR")
    require(fifth.get("special_invite_showcase_only") is True, "Night 5 SSR must be showcase-only")
    require(bool(fifth.get("special_invite_guest_ids")), "Night 5 needs a special invite")
    for guest_id in fifth["special_invite_guest_ids"]:
        guest = guests[guest_id]
        require(guest["rank"] == "SSR" and guest.get("showcase_only") is True, f"{guest_id} must be a showcase SSR")

    expansion_by_room = {
        room_id: upgrade["id"]
        for upgrade in data["upgrades"]
        for room_id in upgrade.get("room_unlocks", ())
    }
    require(all(room_id in expansion_by_room for room_id in ("F1-D", "F2-D", "F3-D")), "F1-D/F2-D/F3-D expansions are required")
    f1, f2, f3 = (expansion_by_room[room_id] for room_id in ("F1-D", "F2-D", "F3-D"))
    require(f1 in upgrades[f2].get("requires", ()), "F2-D must require F1-D")
    require(f2 in upgrades[f3].get("requires", ()), "F3-D must require F2-D")
    require(not can_purchase_upgrade(upgrades, f2, []), "F2-D must not be purchasable before F1-D")
    require(can_purchase_upgrade(upgrades, f1, []), "F1-D must be the expansion entry point")
    require(can_purchase_upgrade(upgrades, f2, [f1]), "F2-D must unlock after F1-D")
    require(not can_purchase_upgrade(upgrades, f3, [f1]), "F3-D must remain locked without F2-D")
    require(can_purchase_upgrade(upgrades, f3, [f1, f2]), "F3-D must unlock after F1-D and F2-D")
    starting_room_count = sum(room.get("built_from_start") is not False for room in data["rooms"])
    expansion_progression = [(), (f1,), (f1, f2), (f1, f2, f3), (f1, f2, f3)]
    service_limits = [
        scenario["capacity"]
        + (len(build_board(data, owned)["unlocked"]) - starting_room_count)
        * data["balance"]["booking_capacity_per_expansion_room"]
        for scenario, owned in zip(data["scenarios"], expansion_progression)
    ]
    require(service_limits == [5, 6, 7, 8, 8], "Expansion booking progression must be 5/6/7/8/8")

    base_board = build_board(data)
    require(all(room_id in base_board["blocked"] for room_id in ("F1-D", "F2-D", "F3-D")), "Unbuilt rooms must begin blocked")
    first_board = build_board(data, [f1])
    require("F1-D" not in first_board["blocked"] and "F2-D" in first_board["blocked"], "F1-D must not float-unlock upper floors")
    multi = build_board(data, ["SOUNDPROOFING", "SERVICE_STAIRS", f1])
    require("quiet" in multi["rooms"]["F2-A"]["attributes"] and "noisy" not in multi["rooms"]["F2-A"]["attributes"], "Soundproofing did not alter F2-A")
    require(frozenset(("F1-A", "F2-A")) in multi["links"], "Service stairs adjacency is missing")
    require("F1-D" not in multi["blocked"] and {"SOUNDPROOFING", "SERVICE_STAIRS"}.issubset(multi["facilities"]), "Multi-facility/expansion board composition failed")

    for upgrade in data["upgrades"]:
        require(upgrade["rarity"] in ranks, f"Unknown upgrade rank: {upgrade['id']}")
        require(upgrade["unlock_stage"] >= ranks[upgrade["rarity"]]["unlock_stage"], f"{upgrade['id']} bypasses its rank stage gate")
        require(upgrade["minimum_reputation"] >= ranks[upgrade["rarity"]]["min_reputation"], f"{upgrade['id']} bypasses its rank reputation gate")
        require(all(required in upgrades for required in upgrade.get("requires", ())), f"{upgrade['id']} has an unknown prerequisite")
        require(upgrade["cost"] >= 0, f"{upgrade['id']} has a negative cost")
    require(not can_purchase_upgrade(upgrades, "UNKNOWN", []), "Unknown upgrade purchase must fail")

    synergy, conflict = synergy_and_conflict_totals(
        data, ["G01_LUNE", "G02_MORROW"], {"G01_LUNE": "F1-A", "G02_MORROW": "F1-B"}
    )
    require(synergy == 4 and conflict == 0, "Two-guest species synergy must apply per guest")
    synergy, conflict = synergy_and_conflict_totals(
        data, ["G01_LUNE", "G04_ARU"], {"G01_LUNE": "F1-A", "G04_ARU": "F1-C"}
    )
    require(synergy == 0 and conflict == -4, "Same-floor rival penalty must affect both guests once")
    _, separated_conflict = synergy_and_conflict_totals(
        data, ["G01_LUNE", "G04_ARU"], {"G01_LUNE": "F1-A", "G04_ARU": "F2-C"}
    )
    require(separated_conflict == 0, "Rivals on separate floors must not conflict")

    require(revisit_bonus_for(data, None) == 0, "First visits must not get a revisit bonus")
    require(revisit_bonus_for(data, {"visits": 1, "lastSatisfaction": 5}) == 2, "Revisit threshold bonus is incorrect")
    earlier_guests = set(data["scenarios"][0]["fixed_guests"])
    later_references = set(itertools.chain.from_iterable(
        itertools.chain(
            scenario.get("fixed_guests", ()),
            scenario.get("applicant_pool", ()),
        )
        for scenario in data["scenarios"][1:]
    ))
    require(bool(earlier_guests & later_references), "The showcase contains no possible returning guest")

    representative_assignments: dict[str, dict[str, str]] = {}
    expansion_progress = {1: [], 2: [f1], 3: [f1, f2], 4: [f1, f2, f3], 5: [f1, f2, f3]}
    for scenario in data["scenarios"]:
        group = list(dict.fromkeys([*scenario.get("fixed_guests", ()), *scenario.get("applicants", ())]))
        group = group[: scenario["capacity"]]
        require(bool(group), f"{scenario['id']} has no representative guests")
        assignment = find_valid_assignment(data, group, expansion_progress[scenario["stage"]])
        require(assignment is not None, f"No valid representative assignment for {scenario['id']}: {group}")
        representative_assignments[scenario["id"]] = assignment

    default_signature = showcase_signature(data, DEFAULT_SHOWCASE_SEED)
    repeated_signature = showcase_signature(data, DEFAULT_SHOWCASE_SEED)
    alternate_signature = showcase_signature(data, DEFAULT_SHOWCASE_SEED + 1)
    require(default_signature == repeated_signature, "The same seed must reproduce every offer")
    require(default_signature != alternate_signature, "Different seeds must vary at least one offer")
    final_offer = default_signature["guests"][-1]
    require(bool(final_offer["special"]), "The default showcase seed must retain the SSR special invitation")
    require(any(guests[guest_id]["rank"] == "SSR" for guest_id in final_offer["ids"]), "The default Night 5 offer must include SSR")

    return {
        "schema": data["schema_version"],
        "nights": len(data["scenarios"]),
        "species": len(data["species"]),
        "ranks": list(RANK_IDS),
        "guests": len(data["guests"]),
        "facilities": len(data["facilities"]),
        "upgrades": len(data["upgrades"]),
        "hidden_preferences": len(hidden_ids),
        "booking_service_limits": service_limits,
        "default_seed": DEFAULT_SHOWCASE_SEED,
        "default_guest_offers": default_signature["guests"],
        "default_upgrade_offers": default_signature["upgrades"],
        "representative_assignments": representative_assignments,
    }


def main() -> None:
    summary = validate_static_data(load_data())
    print(json.dumps({"status": "PASS", **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
