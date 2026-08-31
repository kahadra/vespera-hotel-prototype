from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT = ROOT / "artifacts" / "v2-core-playtest" / "exhaustive-placement-audit.json"
DEFAULT_DATA = ROOT / "data" / "prototype_v1.json"
DEFAULT_RULES = ROOT / "src" / "rules.js"

NUMBER_PATTERN = r"-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bracket_delta(line: str) -> int:
    """Count JSON array brackets outside strings on one pretty-printed line."""
    delta = 0
    in_string = False
    escaped = False
    for character in line:
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
        elif character == "[":
            delta += 1
        elif character == "]":
            delta -= 1
    return delta


def load_without_variants(path: Path) -> tuple[dict[str, Any], list[dict[str, int]]]:
    """Load the audit while streaming away its very large placement variants.

    Exact placement counts are retained, including the number whose reputation
    delta is negative. This keeps the audit useful on machines where fully
    materializing the historical 50+ MB JSON would be unnecessarily expensive.
    """
    multiline_start = re.compile(r'^(\s*)"variants"\s*:\s*\[\s*$')
    inline_empty = re.compile(r'^(\s*)"variants"\s*:\s*\[\s*\]\s*,?\s*$')
    reputation_line: re.Pattern[str] | None = None
    count_line: re.Pattern[str] | None = None
    variant_summaries: list[dict[str, int]] = []
    retained_lines: list[str] = []

    skipping = False
    depth = 0
    property_indent = ""
    current_reputation: float | None = None
    current_summary: dict[str, int] | None = None

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not skipping:
                if inline_empty.match(line):
                    retained_lines.append(line)
                    variant_summaries.append(
                        {"negativePlacements": 0, "totalPlacements": 0, "variantRecords": 0}
                    )
                    continue
                match = multiline_start.match(line)
                if not match:
                    retained_lines.append(line)
                    continue

                skipping = True
                depth = 1
                property_indent = match.group(1) + "    "
                reputation_line = re.compile(
                    rf'^{re.escape(property_indent)}"reputationDelta"\s*:\s*({NUMBER_PATTERN})\s*,?\s*$'
                )
                count_line = re.compile(
                    rf'^{re.escape(property_indent)}"count"\s*:\s*(\d+)\s*,?\s*$'
                )
                current_reputation = None
                current_summary = {
                    "negativePlacements": 0,
                    "totalPlacements": 0,
                    "variantRecords": 0,
                }
                continue

            assert current_summary is not None
            assert reputation_line is not None
            assert count_line is not None

            reputation_match = reputation_line.match(line)
            if reputation_match:
                current_reputation = float(reputation_match.group(1))

            count_match = count_line.match(line)
            if count_match:
                count = int(count_match.group(1))
                if current_reputation is None:
                    raise ValueError(
                        f"variant count appeared before reputationDelta at {path}:{line_number}"
                    )
                current_summary["variantRecords"] += 1
                current_summary["totalPlacements"] += count
                if current_reputation < 0:
                    current_summary["negativePlacements"] += count
                current_reputation = None

            depth += bracket_delta(line)
            if depth > 0:
                continue
            if depth < 0:
                raise ValueError(f"variant array nesting became invalid at {path}:{line_number}")

            suffix = "," if line.rstrip().endswith(",") else ""
            variants_indent = property_indent[:-4]
            retained_lines.append(f'{variants_indent}"variants": []{suffix}\n')
            variant_summaries.append(current_summary)
            skipping = False
            current_summary = None

    if skipping:
        raise ValueError(f"unterminated variants array in {path}")

    return json.loads("".join(retained_lines)), variant_summaries


def attach_variant_summaries(
    artifact: dict[str, Any], variant_summaries: list[dict[str, int]]
) -> dict[str, Any]:
    subsets = [
        subset
        for route in artifact.get("routes", [])
        for stage in route.get("stages", [])
        for subset in stage.get("subsets", [])
    ]
    if len(subsets) != len(variant_summaries):
        raise ValueError(
            "variant/subset accounting mismatch: "
            f"{len(variant_summaries)} variant arrays for {len(subsets)} subsets"
        )

    mismatches: list[dict[str, int]] = []
    for index, (subset, summary) in enumerate(zip(subsets, variant_summaries, strict=True)):
        subset["_variantSummary"] = summary
        expected = int(subset.get("validPlacements", 0))
        if expected != summary["totalPlacements"]:
            mismatches.append(
                {
                    "subsetIndex": index,
                    "reportedValidPlacements": expected,
                    "variantPlacementCount": summary["totalPlacements"],
                }
            )
    return {
        "subsetCount": len(subsets),
        "variantAccountingValid": not mismatches,
        "mismatches": mismatches[:20],
    }


def finite_mean(subset: dict[str, Any], field: str) -> float | None:
    value = subset.get(field, {}).get("mean")
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def subset_identity(subset: dict[str, Any]) -> dict[str, Any]:
    return {
        "acceptedGuestIds": subset.get("acceptedGuestIds", []),
        "rejectedGuestIds": subset.get("rejectedGuestIds", []),
        "validPlacements": int(subset.get("validPlacements", 0)),
    }


def best_subset(subsets: list[dict[str, Any]], field: str) -> dict[str, Any] | None:
    candidates = [subset for subset in subsets if finite_mean(subset, field) is not None]
    if not candidates:
        return None
    winner = max(candidates, key=lambda subset: finite_mean(subset, field) or -math.inf)
    return {
        **subset_identity(winner),
        "mean": finite_mean(winner, field),
    }


def analyze_stage(route_name: str, stage: dict[str, Any]) -> dict[str, Any]:
    offers = list(stage.get("offerGuestIds", []))
    subsets = list(stage.get("subsets", []))
    valid_subsets = [subset for subset in subsets if int(subset.get("validPlacements", 0)) > 0]
    all_accept = next(
        (subset for subset in subsets if not subset.get("rejectedGuestIds", [])),
        None,
    )

    fixed_count = len(set(stage.get("fixedGuestIds", [])))
    all_guest_count = len(set(stage.get("fixedGuestIds", []) + offers))
    service_limit = int(stage.get("serviceLimit", 0))
    physical_limit = int(stage.get("physicalPlacementLimit", 0))
    capacity_feasible = all_guest_count <= min(service_limit, physical_limit)

    best_reputation = best_subset(valid_subsets, "reputationDelta")
    best_income = best_subset(valid_subsets, "income")
    all_reputation = finite_mean(all_accept, "reputationDelta") if all_accept else None
    all_income = finite_mean(all_accept, "income") if all_accept else None
    tolerance = 1e-12
    reputation_dominates = bool(
        all_reputation is not None
        and best_reputation is not None
        and all_reputation + tolerance >= float(best_reputation["mean"])
    )
    income_dominates = bool(
        all_income is not None
        and best_income is not None
        and all_income + tolerance >= float(best_income["mean"])
    )

    variant_summary = (
        all_accept.get("_variantSummary", {}) if all_accept is not None else {}
    )
    valid_placements = int(all_accept.get("validPlacements", 0)) if all_accept else 0
    negative_placements = int(variant_summary.get("negativePlacements", 0))
    aggregate_negative = sum(
        int(subset.get("_variantSummary", {}).get("negativePlacements", 0))
        for subset in valid_subsets
    )

    return {
        "route": route_name,
        "stage": stage.get("stage"),
        "scenarioId": stage.get("scenarioId"),
        "offerGuestIds": offers,
        "offeredGuestCount": len(offers),
        "fixedGuestCount": fixed_count,
        "allGuestCount": all_guest_count,
        "serviceLimit": service_limit,
        "physicalPlacementLimit": physical_limit,
        "allAcceptCapacityFeasible": capacity_feasible,
        "allAcceptEntryPresent": all_accept is not None,
        "allAcceptHasValidSolution": valid_placements > 0,
        "allAccept": None
        if all_accept is None
        else {
            **subset_identity(all_accept),
            "candidateAssignments": int(all_accept.get("candidateAssignments", 0)),
            "meanReputationDelta": all_reputation,
            "meanIncome": all_income,
            "negativePlacementCount": negative_placements,
            "negativePlacementRate": (
                negative_placements / valid_placements if valid_placements else None
            ),
        },
        "comparisonAgainstEveryValidSubset": {
            "validSubsetCount": len(valid_subsets),
            "bestMeanReputationSubset": best_reputation,
            "bestMeanIncomeSubset": best_income,
            "allAcceptTiesOrBeatsBestMeanReputation": reputation_dominates,
            "allAcceptTiesOrBeatsBestMeanIncome": income_dominates,
            "allAcceptDominatesBothMeans": reputation_dominates and income_dominates,
            "negativePlacementCountAcrossAllValidSubsets": aggregate_negative,
        },
    }


def extract_species_synergy_metrics(data: dict[str, Any], rules_path: Path) -> dict[str, Any]:
    source = rules_path.read_text(encoding="utf-8")
    lines = source.splitlines()
    start_match = re.search(r"function\s+applySpeciesEffects\s*\(", source)
    if not start_match:
        raise ValueError(f"applySpeciesEffects was not found in {rules_path}")
    conflict_match = re.search(r"\n\s*const explicitConflicts\s*=", source[start_match.start() :])
    if not conflict_match:
        raise ValueError(f"species synergy/conflict boundary was not found in {rules_path}")
    synergy_end = start_match.start() + conflict_match.start()
    synergy_source = source[start_match.start() : synergy_end]

    count_gate = bool(
        re.search(r"guestIds\.length\s*>=\s*entry\.count", synergy_source)
    )
    spatial_patterns = {
        "areAdjacent": r"\bareAdjacent\b",
        "roomFloor": r"\.floor\b",
        "roomWing": r"\.wing\b",
        "boardRooms": r"board\.rooms",
        "adjacencyToken": r"\badjacent\b|ADJACENT",
        "sameFloorToken": r"same[_A-Z-]*floor|SAME_FLOOR",
    }
    spatial_hits = [
        name for name, pattern in spatial_patterns.items() if re.search(pattern, synergy_source, re.I)
    ]
    rank_gate = bool(re.search(r"\brank\b|acceptedRanks", synergy_source, re.I))
    placed_guest_gate = bool(
        re.search(r"acceptedGuestIds\.filter\(\(id\)\s*=>\s*placements\[id\]\)", synergy_source)
    )

    species_thresholds = [
        {
            "speciesId": species.get("id"),
            "thresholds": [
                {
                    "count": entry.get("count"),
                    "points": entry.get("points_per_guest", entry.get("points", 0)),
                }
                for entry in species.get("synergy_thresholds", [])
            ],
        }
        for species in data.get("species", [])
        if species.get("synergy_thresholds")
    ]
    all_thresholds = [
        entry
        for species in data.get("species", [])
        for entry in species.get("synergy_thresholds", [])
    ]
    minimum_count = min(
        (int(entry["count"]) for entry in all_thresholds if isinstance(entry.get("count"), int)),
        default=None,
    )
    function_line = source.count("\n", 0, start_match.start()) + 1
    count_gate_line = next(
        (
            index
            for index, line in enumerate(lines, start=1)
            if "guestIds.length >= entry.count" in line
        ),
        None,
    )

    location_independent = count_gate and not spatial_hits
    return {
        "function": "applySpeciesEffects",
        "sourceLines": {
            "functionStart": function_line,
            "guestCountGate": count_gate_line,
        },
        "placedGuestExistenceGatePresent": placed_guest_gate,
        "speciesGuestCountGatePresent": count_gate,
        "rankGatePresent": rank_gate,
        "spatialConditionTokensFoundBeforeConflictLogic": spatial_hits,
        "automaticSpeciesSynergyIsLocationIndependent": location_independent,
        "automaticSpeciesSynergySelectionUsesOnlyPlacedSameSpeciesCount": (
            placed_guest_gate and count_gate and not rank_gate and not spatial_hits
        ),
        "minimumTriggerGuestCount": minimum_count,
        "speciesWithMinimumTrigger": sum(
            any(entry.get("count") == minimum_count for entry in species.get("synergy_thresholds", []))
            for species in data.get("species", [])
        )
        if minimum_count is not None
        else 0,
        "nRankCanContributeWithoutLocationCheck": location_independent and not rank_gate,
        "configuredSpeciesThresholds": species_thresholds,
    }


def build_report(artifact_path: Path, data_path: Path, rules_path: Path) -> dict[str, Any]:
    artifact, variant_summaries = load_without_variants(artifact_path)
    accounting = attach_variant_summaries(artifact, variant_summaries)
    data = json.loads(data_path.read_text(encoding="utf-8"))

    stages = [
        analyze_stage(str(route.get("route", "unknown")), stage)
        for route in artifact.get("routes", [])
        for stage in route.get("stages", [])
        if stage.get("offerGuestIds")
    ]
    feasible = [stage for stage in stages if stage["allAcceptCapacityFeasible"]]
    with_entry = [stage for stage in stages if stage["allAcceptEntryPresent"]]
    with_solution = [stage for stage in stages if stage["allAcceptHasValidSolution"]]
    dominates_reputation = [
        stage
        for stage in stages
        if stage["comparisonAgainstEveryValidSubset"][
            "allAcceptTiesOrBeatsBestMeanReputation"
        ]
    ]
    dominates_income = [
        stage
        for stage in stages
        if stage["comparisonAgainstEveryValidSubset"]["allAcceptTiesOrBeatsBestMeanIncome"]
    ]
    dominates_both = [
        stage
        for stage in stages
        if stage["comparisonAgainstEveryValidSubset"]["allAcceptDominatesBothMeans"]
    ]

    uniformly_present = bool(stages) and len(with_entry) == len(stages)
    uniformly_solvable = bool(stages) and len(with_solution) == len(stages)
    uniformly_dominant = bool(stages) and len(dominates_both) == len(stages)
    feasible_present = bool(feasible) and all(stage["allAcceptEntryPresent"] for stage in feasible)
    feasible_solvable = bool(feasible) and all(stage["allAcceptHasValidSolution"] for stage in feasible)
    feasible_dominant = bool(feasible) and all(
        stage["comparisonAgainstEveryValidSubset"]["allAcceptDominatesBothMeans"]
        for stage in feasible
    )

    if not stages:
        verdict = "INCONCLUSIVE_NO_OFFER_STAGES"
    elif uniformly_present and uniformly_solvable and uniformly_dominant:
        verdict = "ALL_ACCEPT_STRUCTURALLY_DOMINANT_IN_AUDITED_STATES"
    elif feasible_present and feasible_solvable and feasible_dominant:
        verdict = "ALL_ACCEPT_DOMINANT_WHEN_CAPACITY_FEASIBLE"
    elif feasible_solvable:
        verdict = "ALL_ACCEPT_SOLVABLE_BUT_NOT_UNIFORMLY_DOMINANT"
    else:
        verdict = "ALL_ACCEPT_NOT_UNIFORMLY_SOLVABLE"

    negative_total = sum(
        int(stage["allAccept"]["negativePlacementCount"])
        for stage in stages
        if stage["allAccept"] is not None
    )
    valid_total = sum(
        int(stage["allAccept"]["validPlacements"])
        for stage in stages
        if stage["allAccept"] is not None
    )

    report = {
        "status": "PASS" if accounting["variantAccountingValid"] else "ERROR",
        "schema": "RESERVATION_PRESSURE_AUDIT_V1",
        "verdict": verdict,
        "source": {
            "artifact": str(artifact_path),
            "artifactSha256": sha256_file(artifact_path),
            "artifactSchema": artifact.get("schema"),
            "artifactStatus": artifact.get("status"),
            "fixedSeed": artifact.get("seed"),
            "artifactScope": artifact.get("scope"),
            "currentData": str(data_path),
            "currentDataSha256": sha256_file(data_path),
            "currentRules": str(rules_path),
            "currentRulesSha256": sha256_file(rules_path),
            "artifactBindsSourceHashes": False,
            "currentCodeDriftFromArtifact": "POSSIBLE_NOT_VERIFIABLE",
        },
        "allAcceptSummary": {
            "offeredStageStateCount": len(stages),
            "capacityFeasibleStageStateCount": len(feasible),
            "capacityBlockedStageStateCount": len(stages) - len(feasible),
            "allAcceptEntryPresentCount": len(with_entry),
            "allAcceptValidSolutionCount": len(with_solution),
            "allAcceptDominatesMeanReputationCount": len(dominates_reputation),
            "allAcceptDominatesMeanIncomeCount": len(dominates_income),
            "allAcceptDominatesBothMeansCount": len(dominates_both),
            "uniformlyPresent": uniformly_present,
            "uniformlySolvable": uniformly_solvable,
            "uniformlyDominantOnBothMeans": uniformly_dominant,
            "capacityFeasibleStatesAllSolvable": feasible_solvable,
            "capacityFeasibleStatesAllDominantOnBothMeans": feasible_dominant,
            "allAcceptValidPlacementCount": valid_total,
            "allAcceptNegativePlacementCount": negative_total,
            "allAcceptNegativePlacementRate": negative_total / valid_total if valid_total else None,
        },
        "stageStates": stages,
        "automaticSpeciesSynergy": extract_species_synergy_metrics(data, rules_path),
        "artifactAccounting": accounting,
        "limitations": [
            "The placement artifact is a historical fixed-seed observation, not a fresh replay of current code.",
            "The artifact does not bind data.js/rules.js/data source hashes, so current-code drift cannot be excluded.",
            "Only the canonical and greedy-minimum reached stage states were audited; cross-night Cartesian routes were not exhaustively expanded.",
            "Mean dominance compares all-accept against every valid reservation subset within the same reached stage state; it does not prove future campaign optimality.",
            "The automatic species-synergy location verdict is a source-structure metric for the pre-conflict block of applySpeciesEffects, not a fresh gameplay replay.",
        ],
    }
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Summarize all-accept reservation pressure from the retained exhaustive audit "
            "and inspect whether automatic species synergy is location-independent."
        )
    )
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--output", type=Path, help="Optionally write the same JSON report to a file.")
    parser.add_argument("--indent", type=int, default=2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args.artifact.resolve(), args.data.resolve(), args.rules.resolve())
    rendered = json.dumps(report, ensure_ascii=False, indent=args.indent)
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
