from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from smoke_browser import (
    CdpClient,
    DEMO_SEED,
    auto_assign,
    choose_reservations,
    choose_upgrade,
    controller_state,
    debugger_target,
    place,
    rerender,
    seeded_url,
    wait_for,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "v2-core-playtest" / "exhaustive-placement-audit.json"


ENUMERATE_STAGE = r"""
(async () => {
  const controller = window.__vesperaController;
  if (!controller || !['RESERVATION', 'PLACEMENT'].includes(controller.state.phase)) {
    return {ok: false, reason: 'NOT_AUDITABLE', phase: controller?.state?.phase ?? null};
  }
  const [{evaluatePlacement}, {calculateNightResult}] = await Promise.all([
    import('./src/rules.js'),
    import('./src/scoring.js'),
  ]);
  const state = controller.state;
  const scenario = controller.currentScenario;
  const context = controller.hotelContext();
  const capacity = controller.roomCapacitySummary();
  const usableRooms = capacity.usableRoomIds.slice().sort();
  const fixedIds = state.currentFixedGuestIds.slice();
  const offerIds = state.currentGuestOfferIds.slice();
  const lockedIds = state.lockedGuestIds.slice();
  const lockedSet = new Set(lockedIds);
  const lockedPlacements = Object.fromEntries(
    lockedIds.map(guestId => [guestId, state.placements[guestId]]),
  );
  const occupiedLockedRooms = new Set(Object.values(lockedPlacements));
  const freeRooms = usableRooms.filter(roomId => !occupiedLockedRooms.has(roomId));

  const permutations = (n, k) => {
    if (k < 0 || k > n) return 0;
    let value = 1;
    for (let index = 0; index < k; index += 1) value *= n - index;
    return value;
  };
  const freshStats = () => ({
    count: 0,
    sum: 0,
    sumSquares: 0,
    min: null,
    max: null,
  });
  const addStat = (stats, value) => {
    stats.count += 1;
    stats.sum += value;
    stats.sumSquares += value * value;
    stats.min = stats.min === null ? value : Math.min(stats.min, value);
    stats.max = stats.max === null ? value : Math.max(stats.max, value);
  };
  const finalizeStats = stats => {
    if (!stats.count) return {count: 0, min: null, max: null, mean: null, stddev: null};
    const mean = stats.sum / stats.count;
    const variance = Math.max(0, stats.sumSquares / stats.count - mean * mean);
    return {
      count: stats.count,
      min: stats.min,
      max: stats.max,
      mean,
      stddev: Math.sqrt(variance),
    };
  };
  const effectKey = effects => effects
    .map(effect => [
      effect.type,
      effect.label,
      effect.points,
      (effect.guestIds ?? []).slice().sort().join(','),
    ].join(':'))
    .sort();
  const guestTotalKey = scores => Object.fromEntries(
    Object.entries(scores)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([guestId, score]) => [guestId, {
        satisfaction: score.total,
        preference: score.preferenceTotal,
        activeDislikes: score.activeDislikes.map(item => item.label),
        ignoredDislikes: score.ignoredDislikes.map(item => item.label),
      }]),
  );
  const placementKey = placements => Object.fromEntries(
    Object.entries(placements).sort(([left], [right]) => left.localeCompare(right)),
  );

  const subsets = [];
  const globalPlacement = freshStats();
  const globalSatisfaction = freshStats();
  const globalReputation = freshStats();
  const globalEvaluation = freshStats();
  const globalIncome = freshStats();
  const globalGrades = {};
  let globalValid = 0;
  let globalCandidates = 0;
  let globalMinimum = null;
  let globalMaximum = null;

  for (let mask = 0; mask < (1 << offerIds.length); mask += 1) {
    const chosen = offerIds.filter((_, index) => mask & (1 << index));
    const accepted = [...new Set([...fixedIds, ...chosen])];
    const rejected = offerIds.filter(guestId => !chosen.includes(guestId));
    if (!accepted.length) continue;
    if (accepted.length > capacity.serviceLimit || accepted.length > capacity.physicalPlacementLimit) continue;
    const movable = accepted.filter(guestId => !lockedSet.has(guestId));
    if (movable.length > freeRooms.length) continue;

    const entry = {
      acceptedGuestIds: accepted,
      rejectedGuestIds: rejected,
      acceptedRanks: Object.fromEntries(['N', 'R', 'SR', 'SSR'].map(rankId => [
        rankId,
        accepted.filter(guestId => controller.data.indexes.guests[guestId].rank === rankId).length,
      ])),
      candidateAssignments: permutations(freeRooms.length, movable.length),
      validPlacements: 0,
      placementScore: freshStats(),
      satisfactionTotal: freshStats(),
      evaluationScore: freshStats(),
      income: freshStats(),
      reputationDelta: freshStats(),
      grades: {},
      variants: new Map(),
      minimum: null,
      maximum: null,
    };
    globalCandidates += entry.candidateAssignments;
    const placements = {...lockedPlacements};
    const used = new Set(occupiedLockedRooms);

    const visit = index => {
      if (index < movable.length) {
        const guestId = movable[index];
        for (const roomId of freeRooms) {
          if (used.has(roomId)) continue;
          used.add(roomId);
          placements[guestId] = roomId;
          visit(index + 1);
          delete placements[guestId];
          used.delete(roomId);
        }
        return;
      }

      const evaluation = evaluatePlacement(controller.data, accepted, placements, context);
      if (!evaluation.valid) return;
      const result = calculateNightResult(
        controller.data,
        scenario,
        accepted,
        rejected,
        placements,
        context,
      );
      entry.validPlacements += 1;
      globalValid += 1;
      addStat(entry.placementScore, result.placementScore);
      addStat(entry.satisfactionTotal, result.satisfactionTotal);
      addStat(entry.reputationDelta, result.reputationDelta);
      addStat(entry.evaluationScore, result.evaluationScore);
      addStat(entry.income, result.income);
      addStat(globalPlacement, result.placementScore);
      addStat(globalSatisfaction, result.satisfactionTotal);
      addStat(globalReputation, result.reputationDelta);
      addStat(globalEvaluation, result.evaluationScore);
      addStat(globalIncome, result.income);
      entry.grades[result.grade] = (entry.grades[result.grade] ?? 0) + 1;
      globalGrades[result.grade] = (globalGrades[result.grade] ?? 0) + 1;

      const compact = {
        placementScore: result.placementScore,
        satisfactionTotal: result.satisfactionTotal,
        baseFees: result.baseFees,
        tips: result.tips,
        income: result.income,
        reputationDelta: result.reputationDelta,
        evaluationScore: result.evaluationScore,
        grade: result.grade,
        guestTotals: guestTotalKey(result.guestScores),
        guestReviews: result.guestReviews.map(review => ({
          guestId: review.guestId,
          reaction: review.reaction,
          reputationImpact: review.reputationImpact,
          headline: review.headline,
        })),
        groupEffects: effectKey(result.groupEffects),
      };
      const signature = JSON.stringify(compact);
      const previous = entry.variants.get(signature);
      if (previous) {
        previous.count += 1;
      } else {
        entry.variants.set(signature, {
          ...compact,
          count: 1,
          exemplarPlacement: placementKey(placements),
        });
      }

      const candidate = {
        acceptedGuestIds: accepted,
        rejectedGuestIds: rejected,
        ...compact,
        placements: placementKey(placements),
      };
      if (!entry.minimum || candidate.evaluationScore < entry.minimum.evaluationScore
          || (candidate.evaluationScore === entry.minimum.evaluationScore
              && candidate.placementScore < entry.minimum.placementScore)) {
        entry.minimum = candidate;
      }
      if (!entry.maximum || candidate.evaluationScore > entry.maximum.evaluationScore
          || (candidate.evaluationScore === entry.maximum.evaluationScore
              && candidate.placementScore > entry.maximum.placementScore)) {
        entry.maximum = candidate;
      }
      if (!globalMinimum || candidate.evaluationScore < globalMinimum.evaluationScore
          || (candidate.evaluationScore === globalMinimum.evaluationScore
              && candidate.placementScore < globalMinimum.placementScore)) {
        globalMinimum = candidate;
      }
      if (!globalMaximum || candidate.evaluationScore > globalMaximum.evaluationScore
          || (candidate.evaluationScore === globalMaximum.evaluationScore
              && candidate.placementScore > globalMaximum.placementScore)) {
        globalMaximum = candidate;
      }
    };

    visit(0);
    entry.placementScore = finalizeStats(entry.placementScore);
    entry.satisfactionTotal = finalizeStats(entry.satisfactionTotal);
    entry.reputationDelta = finalizeStats(entry.reputationDelta);
    entry.evaluationScore = finalizeStats(entry.evaluationScore);
    entry.income = finalizeStats(entry.income);
    entry.variants = [...entry.variants.values()].sort((left, right) => (
      left.evaluationScore - right.evaluationScore
      || left.placementScore - right.placementScore
      || JSON.stringify(left.guestTotals).localeCompare(JSON.stringify(right.guestTotals))
    ));
    entry.distinctResultVariants = entry.variants.length;
    subsets.push(entry);
  }

  return {
    ok: true,
    stage: controller.currentNightNumber,
    scenarioId: scenario.id,
    scenarioName: scenario.name,
    phase: state.phase,
    runSeed: state.runSeed,
    hotelReputation: state.hotelReputation,
    gold: state.gold,
    currentRankOdds: state.currentRankOdds,
    ownedUpgradeIds: state.ownedUpgradeIds,
    fixedGuestIds: fixedIds,
    offerGuestIds: offerIds,
    specialInviteGuestIds: state.specialInviteGuestIds,
    lockedGuestIds: lockedIds,
    lockedPlacements,
    usableRoomIds: usableRooms,
    serviceLimit: capacity.serviceLimit,
    physicalPlacementLimit: capacity.physicalPlacementLimit,
    reservationSubsets: subsets.length,
    candidateAssignments: globalCandidates,
    validPlacements: globalValid,
    placementScore: finalizeStats(globalPlacement),
    satisfactionTotal: finalizeStats(globalSatisfaction),
    reputationDelta: finalizeStats(globalReputation),
    evaluationScore: finalizeStats(globalEvaluation),
    income: finalizeStats(globalIncome),
    grades: globalGrades,
    distinctResultVariants: subsets.reduce((sum, entry) => sum + entry.distinctResultVariants, 0),
    globalMinimum,
    globalMaximum,
    subsets,
  };
})()
"""


def open_seeded_game(client: CdpClient, url: str, seed: int) -> None:
    client.command("Runtime.enable")
    client.command("Page.enable")
    client.command("Network.enable")
    client.command("Network.setCacheDisabled", {"cacheDisabled": True})
    client.command("Page.navigate", {"url": "about:blank"})
    wait_for(client, "document.readyState === 'complete'")
    client.command("Page.navigate", {"url": seeded_url(url, seed)})
    wait_for(client, "document.readyState === 'complete'")
    wait_for(client, "Boolean(window.__vesperaController)")


def audit_stage(client: CdpClient) -> dict[str, Any]:
    client.ws.settimeout(180)
    result = client.evaluate(ENUMERATE_STAGE)
    if not result or not result.get("ok"):
        raise AssertionError(f"Stage audit failed: {result}")
    return result


def result_snapshot(client: CdpClient) -> dict[str, Any]:
    state = controller_state(client)
    result = state["nightResults"][state["currentNightIndex"]]
    return {
        "stage": state["currentNightIndex"] + 1,
        "placementScore": result["placementScore"],
        "satisfactionTotal": result["satisfactionTotal"],
        "income": result["income"],
        "reputationDelta": result["reputationDelta"],
        "satisfactionReputation": result["satisfactionReputation"],
        "guestReviews": [
            {
                "guestId": review["guestId"],
                "reaction": review["reaction"],
                "reputationImpact": review["reputationImpact"],
                "headline": review["headline"],
            }
            for review in result["guestReviews"]
        ],
        "evaluationScore": result["evaluationScore"],
        "grade": result["grade"],
        "acceptedGuestIds": result["acceptedGuestIds"],
        "rejectedGuestIds": result["rejectedGuestIds"],
        "placements": result["placements"],
        "hotelReputationAfter": state["hotelReputation"],
        "goldAfter": state["gold"],
    }


def finish_tutorial(client: CdpClient) -> None:
    client.click('[data-action="start"]')
    wait_for(client, "window.__vesperaController.state.phase === 'TUTORIAL'")
    auto_assign(client)
    client.click('[data-action="finish-night"]')
    wait_for(client, "window.__vesperaController.state.phase === 'PLACEMENT'")


def drive_canonical(client: CdpClient, url: str, seed: int) -> dict[str, Any]:
    open_seeded_game(client, url, seed)
    finish_tutorial(client)
    stages: list[dict[str, Any]] = []
    actual_results: list[dict[str, Any]] = []
    upgrade_steps: list[dict[str, Any]] = []

    reservation_modes = {2: "balanced", 3: "hidden", 4: "synergy", 5: "ssr"}
    for stage in range(1, 6):
        if stage > 1:
            wait_for(client, "window.__vesperaController.state.phase === 'RESERVATION'")
        stages.append(audit_stage(client))
        if stage > 1:
            route = choose_reservations(client, reservation_modes[stage])
            if not route.get("ok"):
                raise AssertionError(f"No canonical reservation route at stage {stage}: {route}")
            client.click('[data-action="confirm-reservation"]')
        auto_assign(client)
        client.click('[data-action="finish-night"]')
        wait_for(client, "window.__vesperaController.state.phase === 'RESULT'")
        actual_results.append(result_snapshot(client))
        if stage == 5:
            break
        client.click('[data-action="continue-result"]')
        wait_for(client, "window.__vesperaController.state.phase === 'UPGRADE'")
        purchase = choose_upgrade(client, prefer_expansion=True)
        upgrade_steps.append({"afterStage": stage, **purchase})

    return {
        "route": "canonical-high-capacity",
        "stages": stages,
        "actualResults": actual_results,
        "upgradeSteps": upgrade_steps,
        "finalState": controller_state(client),
    }


def apply_audit_minimum(client: CdpClient, audit: dict[str, Any]) -> None:
    target = audit["globalMinimum"]
    state = controller_state(client)
    if state["phase"] == "RESERVATION":
        accepted = set(target["acceptedGuestIds"])
        for guest_id in state["currentGuestOfferIds"]:
            action = "accept" if guest_id in accepted else "reject"
            client.click(f'[data-action="{action}"][data-guest-id="{guest_id}"]')
        client.click('[data-action="confirm-reservation"]')
        wait_for(client, "window.__vesperaController.state.phase === 'PLACEMENT'")

    state = controller_state(client)
    locked = set(state["lockedGuestIds"])
    for guest_id, room_id in target["placements"].items():
        if guest_id in locked:
            continue
        place(client, guest_id, room_id)
    rerender(client)


def drive_greedy_low(client: CdpClient, url: str, seed: int) -> dict[str, Any]:
    open_seeded_game(client, url, seed)
    finish_tutorial(client)
    stages: list[dict[str, Any]] = []
    actual_results: list[dict[str, Any]] = []
    upgrade_steps: list[dict[str, Any]] = []

    for stage in range(1, 6):
        if stage > 1:
            wait_for(client, "window.__vesperaController.state.phase === 'RESERVATION'")
        audit = audit_stage(client)
        stages.append(audit)
        apply_audit_minimum(client, audit)
        client.click('[data-action="finish-night"]')
        wait_for(client, "window.__vesperaController.state.phase === 'RESULT'")
        actual_results.append(result_snapshot(client))
        if stage == 5:
            break
        client.click('[data-action="continue-result"]')
        wait_for(client, "window.__vesperaController.state.phase === 'UPGRADE'")
        upgrade_steps.append({
            "afterStage": stage,
            "offeredIds": controller_state(client)["currentUpgradeOfferIds"],
            "chosenIds": [],
            "skipped": True,
        })
        client.click('[data-action="finish-upgrade"]')

    return {
        "route": "greedy-minimum-no-upgrades",
        "stages": stages,
        "actualResults": actual_results,
        "upgradeSteps": upgrade_steps,
        "finalState": controller_state(client),
    }


def concise_stage(stage: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage": stage["stage"],
        "reputationBefore": stage["hotelReputation"],
        "rankOdds": stage["currentRankOdds"],
        "offers": stage["offerGuestIds"],
        "specialInvites": stage["specialInviteGuestIds"],
        "reservationSubsets": stage["reservationSubsets"],
        "candidateAssignments": stage["candidateAssignments"],
        "validPlacements": stage["validPlacements"],
        "distinctResultVariants": stage["distinctResultVariants"],
        "placementScore": stage["placementScore"],
        "satisfactionTotal": stage["satisfactionTotal"],
        "reputationDelta": stage["reputationDelta"],
        "evaluationScore": stage["evaluationScore"],
        "income": stage["income"],
        "grades": stage["grades"],
        "minimum": stage["globalMinimum"],
        "maximum": stage["globalMaximum"],
    }


def build_summary(canonical: dict[str, Any], low: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical": [concise_stage(stage) for stage in canonical["stages"]],
        "greedyLow": [concise_stage(stage) for stage in low["stages"]],
        "canonicalActualResults": canonical["actualResults"],
        "greedyLowActualResults": low["actualResults"],
        "canonicalUpgradeSteps": canonical["upgradeSteps"],
        "greedyLowUpgradeSteps": low["upgradeSteps"],
        "finalComparison": {
            "canonicalReputation": canonical["finalState"]["hotelReputation"],
            "greedyLowReputation": low["finalState"]["hotelReputation"],
            "canonicalGold": canonical["finalState"]["gold"],
            "greedyLowGold": low["finalState"]["gold"],
            "canonicalSeenRanks": canonical["finalState"]["seenRankIds"],
            "greedyLowSeenRanks": low["finalState"]["seenRankIds"],
            "lowStage5SpecialInvites": low["stages"][4]["specialInviteGuestIds"],
            "lowStage5RankOdds": low["stages"][4]["currentRankOdds"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--debug-port", type=int, default=9223)
    parser.add_argument("--seed", type=int, default=DEMO_SEED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    target = debugger_target(args.debug_port)
    client = CdpClient(target["webSocketDebuggerUrl"])
    try:
        canonical = drive_canonical(client, args.url, args.seed)
        low = drive_greedy_low(client, args.url, args.seed)
        payload = {
            "status": "PASS",
            "schema": 2,
            "seed": args.seed,
            "scope": (
                "Every reservation subset and every injective room assignment was evaluated "
                "within each reached live stage state. Cross-night Cartesian combinations are "
                "represented by the canonical and greedy-minimum routes, not exhaustively expanded."
            ),
            "summary": build_summary(canonical, low),
            "routes": [canonical, low],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({
            "status": payload["status"],
            "seed": args.seed,
            "output": str(args.output),
            "summary": payload["summary"],
        }, ensure_ascii=False, indent=2))
    finally:
        client.close()


if __name__ == "__main__":
    main()
