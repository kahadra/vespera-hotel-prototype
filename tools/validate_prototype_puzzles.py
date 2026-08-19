from __future__ import annotations

import itertools
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "prototype_v1.json"


def load_data():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def index_by_id(items):
    return {item["id"]: item for item in items}


def build_state(data, facility_id):
    rooms = {
        room["id"]: {
            **room,
            "attributes": set(room["attributes"]),
        }
        for room in data["rooms"]
    }
    blocked = set()
    extra_links = set()
    facility = None
    if facility_id is not None:
        facility = index_by_id(data["facilities"])[facility_id]
        blocked.update(facility["blocked_rooms"])
        for change in facility["room_attribute_changes"]:
            attrs = rooms[change["room_id"]]["attributes"]
            attrs.difference_update(change["remove"])
            attrs.update(change["add"])
        for left, right in facility["adjacency_links"]:
            extra_links.add(frozenset((left, right)))
    return rooms, blocked, extra_links, facility


def adjacent(room_a, room_b, rooms, extra_links):
    if frozenset((room_a, room_b)) in extra_links:
        return True
    a = rooms[room_a]
    b = rooms[room_b]
    return a["floor"] == b["floor"] and abs(a["wing"] - b["wing"]) == 1


def merged_rules(guest, species, rank):
    return (
        species["hard_constraints"] + rank["hard_constraints"] + guest["hard_constraints"],
        species["soft_preferences"] + rank["soft_preferences"] + guest["soft_preferences"],
    )


def hard_constraint_ok(rule, guest_id, placement, rooms, extra_links):
    room_id = placement[guest_id]
    room = rooms[room_id]
    rule_type = rule["type"]
    if rule_type == "ROOM_NOT_HAS":
        return rule["attribute"] not in room["attributes"]
    if rule_type == "MUST_ADJACENT_GUEST":
        other = rule["guest_id"]
        return other in placement and adjacent(room_id, placement[other], rooms, extra_links)
    if rule_type == "NO_OCCUPIED_ADJACENT":
        return all(
            other == guest_id or not adjacent(room_id, other_room, rooms, extra_links)
            for other, other_room in placement.items()
        )
    if rule_type == "MUST_SHARE_FLOOR":
        return any(
            other != guest_id and rooms[other_room]["floor"] == room["floor"]
            for other, other_room in placement.items()
        )
    raise ValueError(f"Unknown hard rule: {rule_type}")


def preference_points(rule, guest_id, placement, rooms, extra_links, facility):
    room_id = placement[guest_id]
    room = rooms[room_id]
    rule_type = rule["type"]
    matched = False
    if rule_type == "ROOM_HAS":
        matched = rule["attribute"] in room["attributes"]
    elif rule_type == "FLOOR_IS":
        matched = room["floor"] == rule["floor"]
    elif rule_type == "ELEVATOR_DISTANCE_AT_LEAST":
        matched = room["wing"] >= rule["distance"]
    elif rule_type == "ELEVATOR_DISTANCE_AT_MOST":
        matched = room["wing"] <= rule["distance"]
    elif rule_type == "ADJACENT_GUEST":
        other = rule["guest_id"]
        matched = other in placement and adjacent(room_id, placement[other], rooms, extra_links)
    elif rule_type == "NEAR_FACILITY":
        if facility is not None and facility["id"] == rule["facility_id"]:
            matched = any(
                adjacent(room_id, facility_room, rooms, extra_links)
                for facility_room in facility["blocked_rooms"]
            )
    else:
        raise ValueError(f"Unknown preference: {rule_type}")
    return rule["points"] if matched else 0


def evaluate_placement(accepted, placement, data, state):
    rooms, _, extra_links, facility = state
    guests = index_by_id(data["guests"])
    species = index_by_id(data["species"])
    ranks = index_by_id(data["ranks"])
    placement_score = 0
    breakdown = {}
    for guest_id in accepted:
        guest = guests[guest_id]
        hard, soft = merged_rules(guest, species[guest["species"]], ranks[guest["rank"]])
        if not all(
            hard_constraint_ok(rule, guest_id, placement, rooms, extra_links)
            for rule in hard
        ):
            return None
        guest_points = sum(
            preference_points(rule, guest_id, placement, rooms, extra_links, facility)
            for rule in soft
        )
        if facility is not None:
            guest_points += sum(
                bonus["points"]
                for bonus in facility.get("room_bonuses", [])
                if bonus["room_id"] == placement[guest_id]
            )
        breakdown[guest_id] = guest_points
        placement_score += guest_points
    return placement_score, breakdown


def enumerate_best(data, scenario, facility_id, accepted, rejected):
    guests = index_by_id(data["guests"])
    state = build_state(data, facility_id)
    rooms, blocked, _, _ = state
    available_rooms = [room_id for room_id in rooms if room_id not in blocked]
    if len(accepted) > scenario["capacity"] or len(accepted) > len(available_rooms):
        return None

    best = None
    valid_count = 0
    placement_scores = set()
    for selected_rooms in itertools.permutations(available_rooms, len(accepted)):
        placement = dict(zip(accepted, selected_rooms))
        result = evaluate_placement(accepted, placement, data, state)
        if result is None:
            continue
        valid_count += 1
        placement_score, breakdown = result
        placement_scores.add(placement_score)
        income = sum(guests[g]["base_fee"] for g in accepted) + placement_score
        reputation = (
            sum(guests[g]["satisfied_reputation"] for g in accepted)
            + sum(guests[g]["reject_reputation"] for g in rejected)
        )
        evaluation = placement_score + 2 * reputation + math.floor(income / 5)
        candidate = {
            "evaluation": evaluation,
            "placement_score": placement_score,
            "income": income,
            "reputation": reputation,
            "placement": placement,
            "breakdown": breakdown,
            "valid_count": valid_count,
        }
        if best is None or (
            candidate["evaluation"],
            candidate["placement_score"],
            candidate["income"],
        ) > (
            best["evaluation"],
            best["placement_score"],
            best["income"],
        ):
            best = candidate
    if best is not None:
        best["valid_count"] = valid_count
        best["min_placement_score"] = min(placement_scores)
        best["max_placement_score"] = max(placement_scores)
        best["distinct_placement_scores"] = len(placement_scores)
    return best


def accepted_options(scenario):
    fixed = scenario["fixed_guests"]
    applicants = scenario["applicants"]
    if not applicants:
        yield fixed, []
        return
    for count in range(len(applicants) + 1):
        for chosen in itertools.combinations(applicants, count):
            accepted = fixed + list(chosen)
            if len(accepted) <= scenario["capacity"]:
                rejected = [guest for guest in applicants if guest not in chosen]
                yield accepted, rejected


def validate_static_data(data):
    for collection in ("rooms", "species", "ranks", "guests", "facilities", "scenarios"):
        ids = [item["id"] for item in data[collection]]
        if len(ids) != len(set(ids)):
            raise AssertionError(f"Duplicate IDs in {collection}")
    for guest in data["guests"]:
        if abs(guest["cancel_reputation"]) <= abs(guest["reject_reputation"]):
            raise AssertionError(f"Cancel must be worse than reject: {guest['id']}")


def main():
    data = load_data()
    validate_static_data(data)
    guests = index_by_id(data["guests"])

    for scenario in data["scenarios"]:
        print(f"SCENARIO {scenario['id']} {scenario['name']}")
        for facility_id in scenario["facility_options"]:
            label = facility_id or "NONE"
            results = []
            for accepted, rejected in accepted_options(scenario):
                best = enumerate_best(data, scenario, facility_id, accepted, rejected)
                if best is not None:
                    results.append((best, accepted, rejected))
            results.sort(
                key=lambda item: (
                    item[0]["evaluation"],
                    item[0]["placement_score"],
                    item[0]["income"],
                ),
                reverse=True,
            )
            if not results:
                raise AssertionError(f"No valid result for {scenario['id']} / {label}")
            print(f"  FACILITY {label}")
            for best, accepted, rejected in results[:5]:
                accepted_names = [guests[g]["name"] for g in accepted]
                rejected_names = [guests[g]["name"] for g in rejected]
                print(
                    "    "
                    f"eval={best['evaluation']:>2} pref={best['placement_score']:>2} "
                    f"income={best['income']:>2} rep={best['reputation']:>2} "
                    f"valid={best['valid_count']:>4} "
                    f"pref_range={best['min_placement_score']}-{best['max_placement_score']} "
                    f"pref_levels={best['distinct_placement_scores']:>2} "
                    f"accept={accepted_names} reject={rejected_names}"
                )
                print(f"      placement={best['placement']}")


if __name__ == "__main__":
    main()
