from __future__ import annotations

import argparse
import json
import time

from smoke_browser import (
    CdpClient,
    DEMO_SEED,
    assert_capacity_contract,
    assert_preopening_copy,
    auto_assign,
    choose_reservations,
    choose_upgrade,
    controller_state,
    debugger_target,
    no_maximum_reveal,
    require_text,
    rerender,
    seeded_url,
    wait_for,
)


def assert_guest_review_settlement(client: CdpClient, result_index: int) -> dict:
    """Settlement exposes qualitative reviews while exact satisfaction stays internal."""

    result = client.evaluate(
        f"""
        (() => {{
          const controller = window.__vesperaController;
          const nightResult = controller.state.nightResults[{result_index}];
          const section = document.querySelector('[data-video-target="guest-reviews"]');
          const cards = [...(section?.querySelectorAll('.guest-review-card') ?? [])];
          return {{
            phase: controller.state.phase,
            reviewCount: nightResult?.guestReviews?.length ?? -1,
            acceptedCount: nightResult?.acceptedGuestIds?.length ?? -1,
            cardCount: cards.length,
            hasSection: Boolean(section),
            leaksInternalField: Boolean(section?.innerHTML.includes('satisfaction')),
            satisfactionReputation: nightResult?.satisfactionReputation,
            summedReviewImpact: (nightResult?.guestReviews ?? [])
              .reduce((sum, review) => sum + review.reputationImpact, 0),
            reactions: (nightResult?.guestReviews ?? []).map(review => {{
              const guest = controller.data.indexes.guests[review.guestId];
              const threshold = controller.data.indexes.ranks[guest.rank]
                .positive_satisfaction_threshold;
              const expectedReaction = review.satisfaction < 0
                ? 'negative'
                : review.satisfaction >= threshold ? 'positive' : 'neutral';
              return {{
                reaction: review.reaction,
                expectedReaction,
                reputationImpact: review.reputationImpact,
              }};
            }}),
          }};
        }})()
        """
    )
    assert result["phase"] == "RESULT", result
    assert result["hasSection"], result
    assert result["reviewCount"] == result["acceptedCount"], result
    assert result["cardCount"] == result["reviewCount"], result
    assert result["leaksInternalField"] is False, result
    assert result["summedReviewImpact"] == result["satisfactionReputation"], result
    assert all(
        item["reaction"] == item["expectedReaction"]
        for item in result["reactions"]
    ), result
    assert all(
        item["reputationImpact"] == 0
        for item in result["reactions"]
        if item["reaction"] == "neutral"
    ), result
    return {
        "night": result_index + 1,
        "reviews": result["reviewCount"],
        "reactions": {
            reaction: sum(1 for item in result["reactions"] if item["reaction"] == reaction)
            for reaction in ("positive", "neutral", "negative")
        },
        "review_reputation": result["satisfactionReputation"],
        "exact_satisfaction_hidden": True,
    }


def assert_elevator_room_context(client: CdpClient) -> dict:
    """Each floor visually places an elevator immediately beside noisy A rooms."""

    result = client.evaluate(
        """
        (() => {
          const rows = [...document.querySelectorAll('.hotel-board .floor-row')];
          return {
            rowCount: rows.length,
            floors: rows.map(row => {
              const elevator = row.querySelector('.elevator-landing');
              const roomA = row.querySelector('.room-card.elevator-adjacent');
              const elevatorRect = elevator?.getBoundingClientRect();
              const roomRect = roomA?.getBoundingClientRect();
              return {
                elevatorPresent: Boolean(elevator),
                accessibleContext: elevator?.getAttribute('aria-label') ?? '',
                roomId: roomA?.dataset.roomId ?? null,
                noisyRoom: Boolean(roomA?.classList.contains('noisy-room')),
                gap: elevatorRect && roomRect
                  ? Math.round(roomRect.left - elevatorRect.right)
                  : null,
              };
            }),
          };
        })()
        """
    )
    assert result["rowCount"] == 3, result
    assert all(item["elevatorPresent"] for item in result["floors"]), result
    assert all(item["roomId"].endswith("-A") for item in result["floors"]), result
    assert all(item["noisyRoom"] for item in result["floors"]), result
    assert all(0 <= item["gap"] <= 10 for item in result["floors"]), result
    assert all("A열 객실과 바로 인접" in item["accessibleContext"] for item in result["floors"]), result
    return result


def assert_reservation_cardinality_gates(client: CdpClient) -> dict:
    """Probe booking and physical cardinality gates, restoring the run."""

    result = client.evaluate(
        """
        (() => {
          const controller = window.__vesperaController;
          if (controller.state.phase !== 'RESERVATION') {
            return { ok: false, reason: 'NOT_RESERVATION' };
          }
          const snapshot = JSON.parse(JSON.stringify({
            roomConditions: controller.state.roomConditions,
            currentFixedGuestIds: controller.state.currentFixedGuestIds,
            currentGuestOfferIds: controller.state.currentGuestOfferIds,
            applicantDecisions: controller.state.applicantDecisions,
            acceptedGuestIds: controller.state.acceptedGuestIds,
            rejectedGuestIds: controller.state.rejectedGuestIds,
            phase: controller.state.phase,
            serviceTimerMs: controller.state.serviceTimerMs,
          }));
          const restore = () => {
            controller.state.roomConditions = snapshot.roomConditions;
            controller.state.currentFixedGuestIds = snapshot.currentFixedGuestIds;
            controller.state.currentGuestOfferIds = snapshot.currentGuestOfferIds;
            controller.state.applicantDecisions = snapshot.applicantDecisions;
            controller.state.acceptedGuestIds = snapshot.acceptedGuestIds;
            controller.state.rejectedGuestIds = snapshot.rejectedGuestIds;
            controller.state.phase = snapshot.phase;
            controller.state.serviceTimerMs = snapshot.serviceTimerMs;
          };

          const normal = controller.reservationSummary();
          const protectedRooms = new Set(
            Object.values(controller.state.stayovers).map(entry => entry.roomId),
          );
          const degradedRoomIds = [];
          for (const roomId of controller.roomCapacitySummary().usableRoomIds) {
            if (protectedRooms.has(roomId)) continue;
            controller.state.roomConditions[roomId] = { cleanliness: 0 };
            degradedRoomIds.push(roomId);
            if (controller.roomCapacitySummary().physicalPlacementLimit < normal.accepted.length) break;
          }
          const physical = controller.reservationSummary();
          const physicalConfirmed = controller.confirmReservation();

          restore();
          const restoredCapacity = controller.roomCapacitySummary();
          const bookingCount = restoredCapacity.serviceLimit + 1;
          controller.state.currentFixedGuestIds = controller.data.guests
            .slice(0, bookingCount)
            .map(guest => guest.id);
          controller.state.applicantDecisions = Object.fromEntries(
            controller.state.currentGuestOfferIds.map(id => [id, 'reject']),
          );
          const booking = controller.reservationSummary();
          const bookingConfirmed = controller.confirmReservation();
          restore();

          return {
            ok: true,
            normal,
            degradedRoomIds,
            physical,
            physicalConfirmed,
            booking,
            bookingConfirmed,
            restored: controller.reservationSummary(),
          };
        })()
        """
    )
    assert result["ok"], result
    assert not result["normal"]["pending"], result
    assert result["degradedRoomIds"], result
    assert result["physical"]["overCapacity"] is False, result
    assert result["physical"]["overPhysicalCapacity"] is True, result
    assert result["physicalConfirmed"] is False, result
    assert result["booking"]["overCapacity"] is True, result
    assert result["booking"]["overPhysicalCapacity"] is False, result
    assert result["bookingConfirmed"] is False, result
    assert result["restored"] == result["normal"], result
    rerender(client)
    return result


def assert_capacity_does_not_guarantee_hard_feasibility(client: CdpClient) -> dict:
    """A within-limit group may still have no all-hard-rules placement."""

    result = client.evaluate(
        """
        (async () => {
          const controller = window.__vesperaController;
          const { createEmergencyPlan } = await import(
            new URL('./src/emergency.js', document.baseURI).href
          );
          const originalAttributes = Object.fromEntries(
            controller.data.rooms.map(room => [room.id, [...room.attributes]]),
          );
          // Two vampires and at most one room from which blackout curtains can
          // remove the injected sunlight makes a tiny, deterministic Hall-type
          // failure while leaving the cardinality limits untouched.
          for (const room of controller.data.rooms) room.attributes = ['sunny', 'noisy', 'quiet'];
          const guestIds = ['G01_LUNE', 'G02_MORROW'];
          const capacity = controller.roomCapacitySummary();
          const plan = createEmergencyPlan(
            controller.data,
            guestIds,
            {},
            controller.hotelContext(),
            { lockedGuestIds: [] },
          );
          for (const room of controller.data.rooms) room.attributes = originalAttributes[room.id];
          return {
            guestIds,
            serviceLimit: capacity.serviceLimit,
            physicalPlacementLimit: capacity.physicalPlacementLimit,
            housedGuestIds: plan.housedGuestIds,
            canceledGuestIds: plan.canceledGuestIds,
          };
        })()
        """
    )
    assert len(result["guestIds"]) <= result["serviceLimit"], result
    assert len(result["guestIds"]) <= result["physicalPlacementLimit"], result
    assert result["canceledGuestIds"], result
    assert len(result["housedGuestIds"]) < len(result["guestIds"]), result
    rerender(client)
    return result


def assert_facility_room_excluded_from_service(client: CdpClient) -> dict:
    """A room converted into a facility cannot appear in or use maintenance."""

    result = client.evaluate(
        """
        (async () => {
          const controller = window.__vesperaController;
          if (controller.state.phase !== 'UPGRADE') {
            return { ok: false, reason: 'NOT_UPGRADE' };
          }
          const ownedFacilities = controller.state.ownedUpgradeIds
            .map(id => controller.data.indexes.facilities[id])
            .filter(Boolean);
          let candidate = ownedFacilities
            .flatMap(facility => (facility.blocked_rooms ?? []).map(roomId => ({
              facilityId: facility.id,
              roomId,
            })))[0];
          const originalOwnedUpgradeIds = [...controller.state.ownedUpgradeIds];
          let injectedForProbe = false;
          if (!candidate) {
            const facility = controller.data.facilities.find(item => item.blocked_rooms?.length);
            if (!facility) return { ok: false, reason: 'NO_CONVERTED_ROOM_DATA' };
            candidate = { facilityId: facility.id, roomId: facility.blocked_rooms[0] };
            controller.state.ownedUpgradeIds = [
              ...new Set([...controller.state.ownedUpgradeIds, facility.id]),
            ];
            injectedForProbe = true;
          }
          const before = {
            gold: controller.state.gold,
            condition: { ...controller.state.roomConditions[candidate.roomId] },
          };
          controller.state.gold = 999;
          controller.state.roomConditions[candidate.roomId] = {
            cleanliness: 1,
          };
          const { renderApp } = await import(new URL('./src/render.js', document.baseURI).href);
          renderApp(document.querySelector('#app'), controller);
          const buttonBefore = document.querySelector(
            `[data-action="service-room"][data-room-id="${candidate.roomId}"]`,
          );
          const goldBeforeAttempt = controller.state.gold;
          const conditionBeforeAttempt = { ...controller.state.roomConditions[candidate.roomId] };
          const serviced = controller.serviceRoom(candidate.roomId);
          const goldAfterAttempt = controller.state.gold;
          const conditionAfterAttempt = { ...controller.state.roomConditions[candidate.roomId] };
          const structuralBlocked = controller.structuralBoardState().blockedRooms.has(candidate.roomId);
          controller.state.gold = before.gold;
          controller.state.roomConditions[candidate.roomId] = before.condition;
          controller.state.ownedUpgradeIds = originalOwnedUpgradeIds;
          renderApp(document.querySelector('#app'), controller);
          return {
            ok: true,
            ...candidate,
            injectedForProbe,
            structuralBlocked,
            buttonPresent: Boolean(buttonBefore),
            serviced,
            goldBeforeAttempt,
            goldAfterAttempt,
            conditionBeforeAttempt,
            conditionAfterAttempt,
          };
        })()
        """
    )
    assert result["ok"], result
    assert result["structuralBlocked"] is True, result
    assert result["buttonPresent"] is False, result
    assert result["serviced"] is False, result
    assert result["goldAfterAttempt"] == result["goldBeforeAttempt"], result
    assert result["conditionAfterAttempt"] == result["conditionBeforeAttempt"], result
    return result


def assert_timed_placement(client: CdpClient, night_number: int) -> dict:
    current = controller_state(client)
    assert current["phase"] == "PLACEMENT", current
    assert current["currentNightIndex"] == night_number - 1, current
    assert 118_000 <= current["serviceTimerMs"] <= 120_000, current["serviceTimerMs"]
    return current


def assert_renovation_category_gate(client: CdpClient) -> dict:
    """Probe two same-kind contracts, then restore the live run exactly."""

    result = client.evaluate(
        """
        (() => {
          const controller = window.__vesperaController;
          if (controller.state.phase !== 'UPGRADE') return { ok: false, reason: 'NOT_UPGRADE' };
          const snapshot = {
            gold: controller.state.gold,
            ownedUpgradeIds: [...controller.state.ownedUpgradeIds],
            renovationPurchaseIds: [...controller.state.renovationPurchaseIds],
          };
          const offers = controller.state.currentUpgradeOfferIds
            .map(id => controller.data.indexes.upgrades[id])
            .filter(Boolean);
          const groups = Object.groupBy
            ? Object.groupBy(offers, item => item.kind)
            : offers.reduce((result, item) => {
                (result[item.kind] ??= []).push(item);
                return result;
              }, {});
          const sameKind = Object.values(groups).find(items => items.length >= 2);
          if (!sameKind) return { ok: false, reason: 'NO_SAME_KIND_PAIR', offers: offers.map(item => item.id) };
          controller.state.gold = 999;
          const first = controller.buyUpgrade(sameKind[0].id);
          const phaseAfterFirst = controller.state.phase;
          const second = controller.buyUpgrade(sameKind[1].id);
          const unknown = controller.buyUpgrade('NOT_AN_OFFER');
          const contracted = [...controller.state.renovationPurchaseIds];
          controller.state.gold = snapshot.gold;
          controller.state.ownedUpgradeIds = snapshot.ownedUpgradeIds;
          controller.state.renovationPurchaseIds = snapshot.renovationPurchaseIds;
          return {
            ok: true,
            first,
            second,
            unknown,
            phaseAfterFirst,
            kind: sameKind[0].kind,
            contracted,
          };
        })()
        """
    )
    assert result["ok"], result
    assert result["first"] is True, result
    assert result["phaseAfterFirst"] == "UPGRADE", result
    assert result["second"] is False, result
    assert result["unknown"] is False, result
    assert len(result["contracted"]) == 1, result
    rerender(client)
    return result


def assert_stayover_renovation_guard(
    client: CdpClient,
    room_id: str,
    *,
    expected_blocked: bool,
    upgrade_id: str | None = None,
) -> dict:
    """Try the same room-affecting facility contract without changing the run."""

    result = client.evaluate(
        f"""
        (() => {{
          const controller = window.__vesperaController;
          if (controller.state.phase !== 'UPGRADE') return {{ ok: false, reason: 'NOT_UPGRADE' }};
          const roomId = {json.dumps(room_id)};
          const requestedId = {json.dumps(upgrade_id)};
          const renovationRooms = upgrade => [...new Set([
            ...(upgrade.blocked_rooms ?? []),
            ...(upgrade.room_attribute_changes ?? []).map(change => change.room_id),
            ...(upgrade.room_bonuses ?? []).map(bonus => bonus.room_id),
            ...(upgrade.adjacency_links ?? []).flat(),
          ])];
          const candidate = requestedId
            ? controller.data.indexes.upgrades[requestedId]
            : Object.values(controller.data.indexes.upgrades).find(upgrade => (
                upgrade.kind === 'FACILITY'
                && !controller.state.ownedUpgradeIds.includes(upgrade.id)
                && renovationRooms(upgrade).includes(roomId)
              ));
          if (!candidate) return {{ ok: false, reason: 'NO_ROOM_AFFECTING_FACILITY', roomId }};
          if (candidate.kind !== 'FACILITY' || !renovationRooms(candidate).includes(roomId)) {{
            return {{ ok: false, reason: 'BAD_CANDIDATE', candidate: candidate.id, roomId }};
          }}
          const snapshot = {{
            gold: controller.state.gold,
            ownedUpgradeIds: [...controller.state.ownedUpgradeIds],
            currentUpgradeOfferIds: [...controller.state.currentUpgradeOfferIds],
            renovationPurchaseIds: [...controller.state.renovationPurchaseIds],
          }};
          controller.state.gold = 999;
          controller.state.currentUpgradeOfferIds = [
            ...new Set([...controller.state.currentUpgradeOfferIds, candidate.id]),
          ];
          const blocked = controller.upgradeBlockedByStayover(candidate.id);
          const canContract = controller.canContractUpgrade(candidate.id);
          const contracted = controller.buyUpgrade(candidate.id);
          const ownedAfter = controller.state.ownedUpgradeIds.includes(candidate.id);
          controller.state.gold = snapshot.gold;
          controller.state.ownedUpgradeIds = snapshot.ownedUpgradeIds;
          controller.state.currentUpgradeOfferIds = snapshot.currentUpgradeOfferIds;
          controller.state.renovationPurchaseIds = snapshot.renovationPurchaseIds;
          return {{
            ok: true,
            upgradeId: candidate.id,
            affectedRoomIds: renovationRooms(candidate),
            blocked,
            canContract,
            contracted,
            ownedAfter,
          }};
        }})()
        """
    )
    assert result["ok"], result
    assert result["blocked"] is expected_blocked, result
    assert result["canContract"] is (not expected_blocked), result
    assert result["contracted"] is (not expected_blocked), result
    assert result["ownedAfter"] is (not expected_blocked), result
    rerender(client)
    return result


def assert_guest_card_selection(
    client: CdpClient,
    guest_id: str,
    *,
    location: str,
) -> dict:
    """Any guest-card click only selects and opens detail."""

    before = controller_state(client)
    assert location in {"waiting", "placed", "stayover"}, location
    expected_placed = location != "waiting"
    expected_locked = location == "stayover"
    assert (guest_id in before["placements"]) is expected_placed, (guest_id, location, before["placements"])
    assert (guest_id in before["lockedGuestIds"]) is expected_locked, (
        guest_id,
        location,
        before["lockedGuestIds"],
    )
    assert before["selectedGuestId"] != guest_id, (guest_id, before["selectedGuestId"])
    client.click(f'button.guest-chip[data-guest-id={json.dumps(guest_id)}]')
    after = controller_state(client)
    timer_delta = before["serviceTimerMs"] - after["serviceTimerMs"]
    detail_matches = client.evaluate(
        f"""
        (() => {{
          const controller = window.__vesperaController;
          const name = controller.data.indexes.guests[{json.dumps(guest_id)}].name;
          return document.querySelector('.detail-panel')?.innerText.includes(name) ?? false;
        }})()
        """
    )
    assert after["selectedGuestId"] == guest_id, after["selectedGuestId"]
    assert after["placements"] == before["placements"], (before["placements"], after["placements"])
    assert after["relocationCount"] == before["relocationCount"], (before, after)
    assert -1 <= timer_delta < 1_000, timer_delta
    assert (guest_id in after["lockedGuestIds"]) is expected_locked, after["lockedGuestIds"]
    assert detail_matches is True
    return {
        "guest_id": guest_id,
        "location": location,
        "locked": expected_locked,
        "placement_unchanged": True,
        "relocation_unchanged": True,
        "timer_delta_ms": round(timer_delta),
        "detail_opened": True,
    }


def dispatch_drag(client: CdpClient, guest_id: str, target_selector: str) -> dict:
    """Dispatch the same HTML5 drag/drop events handled by setupInput."""

    result = client.evaluate(
        f"""
        (() => {{
          const guestId = {json.dumps(guest_id)};
          const source = document.querySelector(`[data-drag-guest="${{guestId}}"]`);
          const target = document.querySelector({json.dumps(target_selector)});
          if (!source || !target) return {{
            ok: false,
            sourceFound: Boolean(source),
            targetFound: Boolean(target),
          }};
          const transfer = new DataTransfer();
          source.dispatchEvent(new DragEvent('dragstart', {{
            bubbles: true,
            cancelable: true,
            dataTransfer: transfer,
          }}));
          target.dispatchEvent(new DragEvent('dragover', {{
            bubbles: true,
            cancelable: true,
            dataTransfer: transfer,
          }}));
          target.dispatchEvent(new DragEvent('drop', {{
            bubbles: true,
            cancelable: true,
            dataTransfer: transfer,
          }}));
          return {{
            ok: true,
            transferredGuestId: transfer.getData('text/plain'),
          }};
        }})()
        """
    )
    assert result["ok"], (guest_id, target_selector, result)
    assert result["transferredGuestId"] == guest_id, result
    return result


def assert_click_does_not_mutate_placement(
    client: CdpClient,
    selector: str,
    label: str,
) -> dict:
    before = controller_state(client)
    client.click(selector)
    after = controller_state(client)
    timer_delta = before["serviceTimerMs"] - after["serviceTimerMs"]
    assert after["placements"] == before["placements"], (label, before["placements"], after["placements"])
    assert after["relocationCount"] == before["relocationCount"], (label, before, after)
    assert after["selectedGuestId"] == before["selectedGuestId"], (label, before, after)
    assert -1 <= timer_delta < 1_000, (label, timer_delta)
    return {
        "label": label,
        "placements_unchanged": True,
        "relocation_unchanged": True,
        "selected_unchanged": True,
        "timer_delta_ms": round(timer_delta),
    }


def assert_drag_drop_only_placement(client: CdpClient) -> dict:
    """Exercise placement, move, swap, and removal only through drag/drop."""

    start = controller_state(client)
    assert start["phase"] == "PLACEMENT", start
    assert not start["placements"], start["placements"]

    waiting_card = assert_guest_card_selection(
        client,
        "G02_MORROW",
        location="waiting",
    )
    inert_clicks = [assert_click_does_not_mutate_placement(
        client,
        'article.room-card[data-room-id="F1-A"]',
        "empty-room-click",
    )]

    before_first = controller_state(client)
    dispatch_drag(client, "G02_MORROW", 'article.room-card[data-room-id="F1-A"]')
    after_first = controller_state(client)
    assert after_first["placements"].get("G02_MORROW") == "F1-A", after_first["placements"]
    assert after_first["relocationCount"] == before_first["relocationCount"], after_first
    assert -1 <= before_first["serviceTimerMs"] - after_first["serviceTimerMs"] < 1_000

    dispatch_drag(client, "G01_LUNE", 'article.room-card[data-room-id="F1-B"]')
    placed_card = assert_guest_card_selection(
        client,
        "G02_MORROW",
        location="placed",
    )
    inert_clicks.append(assert_click_does_not_mutate_placement(
        client,
        'article.room-card[data-room-id="F2-B"]',
        "empty-room-move-click",
    ))
    inert_clicks.append(assert_click_does_not_mutate_placement(
        client,
        'article.room-card[data-room-id="F1-B"]',
        "occupied-room-swap-click",
    ))

    legacy_unplace_button = client.evaluate("Boolean(document.querySelector('[data-action=unplace]'))")
    if legacy_unplace_button:
        inert_clicks.append(assert_click_does_not_mutate_placement(
            client,
            '[data-action="unplace"]',
            "legacy-unplace-button-click",
        ))

    before_move = controller_state(client)
    dispatch_drag(client, "G02_MORROW", 'article.room-card[data-room-id="F2-B"]')
    after_move = controller_state(client)
    move_cost = before_move["serviceTimerMs"] - after_move["serviceTimerMs"]
    assert after_move["placements"].get("G02_MORROW") == "F2-B", after_move["placements"]
    assert after_move["placements"].get("G01_LUNE") == "F1-B", after_move["placements"]
    assert after_move["relocationCount"] == before_move["relocationCount"] + 1, after_move
    assert 4_700 <= move_cost <= 5_900, move_cost

    before_swap = controller_state(client)
    dispatch_drag(client, "G02_MORROW", 'article.room-card[data-room-id="F1-B"]')
    after_swap = controller_state(client)
    swap_cost = before_swap["serviceTimerMs"] - after_swap["serviceTimerMs"]
    assert after_swap["placements"].get("G02_MORROW") == "F1-B", after_swap["placements"]
    assert after_swap["placements"].get("G01_LUNE") == "F2-B", after_swap["placements"]
    assert after_swap["relocationCount"] == before_swap["relocationCount"] + 1, after_swap
    assert 4_700 <= swap_cost <= 5_900, swap_cost

    inert_clicks.append(assert_click_does_not_mutate_placement(
        client,
        '[data-waiting-zone]',
        "waiting-zone-click",
    ))
    before_remove = controller_state(client)
    dispatch_drag(client, "G02_MORROW", '[data-waiting-zone]')
    after_remove = controller_state(client)
    remove_cost = before_remove["serviceTimerMs"] - after_remove["serviceTimerMs"]
    assert "G02_MORROW" not in after_remove["placements"], after_remove["placements"]
    assert after_remove["placements"].get("G01_LUNE") == "F2-B", after_remove["placements"]
    assert after_remove["relocationCount"] == before_remove["relocationCount"] + 1, after_remove
    assert 4_700 <= remove_cost <= 5_900, remove_cost

    return {
        "waiting_card": waiting_card,
        "placed_card": placed_card,
        "inert_clicks": inert_clicks,
        "legacy_unplace_button_present": legacy_unplace_button,
        "drag_place": True,
        "drag_move": {"timer_cost_ms": round(move_cost)},
        "drag_swap": {"timer_cost_ms": round(swap_cost)},
        "drag_remove": {"timer_cost_ms": round(remove_cost)},
    }


def complete_reservation_night(
    client: CdpClient,
    night_number: int,
    mode: str,
    *,
    timeout: bool = False,
) -> tuple[dict, dict]:
    current = controller_state(client)
    assert current["phase"] == "RESERVATION", current
    route = choose_reservations(client, mode)
    client.click('[data-action="confirm-reservation"]')
    assert_timed_placement(client, night_number)
    plan = auto_assign(client)
    if timeout:
        client.evaluate("window.__vesperaController.state.serviceTimerMs = 100")
        wait_for(
            client,
            f"window.__vesperaController.state.phase === 'RESULT' && window.__vesperaController.state.currentNightIndex === {night_number - 1}",
            timeout=5,
        )
    else:
        client.click('[data-action="finish-night"]')
        wait_for(client, "window.__vesperaController.state.phase === 'RESULT'")
    no_maximum_reveal(client)
    return route, plan


def continue_through_renovation(
    client: CdpClient,
    *,
    probe_category_gate: bool = False,
) -> dict:
    client.click('[data-action="continue-result"]')
    wait_for(client, "window.__vesperaController.state.phase === 'UPGRADE'")
    if probe_category_gate:
        assert_renovation_category_gate(client)
    before = controller_state(client)
    result = choose_upgrade(client, prefer_expansion=True)
    after = controller_state(client)
    assert before["phase"] == "UPGRADE"
    assert after["phase"] in {"RESERVATION", "PLACEMENT"}, after
    assert len(result["chosenIds"]) <= 2
    if len(result["chosenIds"]) == 2:
        kinds = client.evaluate(
            "window.__vesperaController.state.ownedUpgradeIds.slice(-2).map(id => window.__vesperaController.data.indexes.upgrades[id].kind)"
        )
        assert len(set(kinds)) == 2, kinds
    return result


def assert_stayover_cleaning_request_input_paths(
    client: CdpClient,
    guest_id: str,
    room_id: str,
) -> dict:
    """Exercise both rendered request buttons through the live click handler."""

    expression = """
    (async () => {
      const controller = window.__vesperaController;
      const guestId = __GUEST_ID__;
      const roomId = __ROOM_ID__;
      if (controller.state.phase !== 'UPGRADE') return { ok: false, reason: 'NOT_UPGRADE' };
      if (controller.state.stayovers[guestId]?.roomId !== roomId) {
        return { ok: false, reason: 'NOT_CURRENT_STAYOVER' };
      }
      const { renderApp } = await import(new URL('./src/render.js', document.baseURI).href);
      const snapshot = structuredClone(controller.state);
      const selector = outcome => (
        `[data-action="${outcome}-stayover-cleaning-request"]`
      );
      const capture = () => {
        const latest = controller.state.nightResults.at(-1);
        const request = controller.state.pendingStayoverCleaningRequest;
        const controls = [
          document.querySelector('[data-stayover-cleaning-request]'),
          document.querySelector(selector('accept')),
          document.querySelector(selector('reject')),
        ];
        return {
          pending: Boolean(request),
          requestVisible: Boolean(controls[0]),
          controlsPresent: controls.every(Boolean),
          controlsVisible: controls.every(element => {
            if (!element) return false;
            const rect = element.getBoundingClientRect();
            return rect.top >= 0 && rect.bottom <= window.innerHeight;
          }),
          acceptDisabled: controls[1]?.disabled ?? null,
          gold: controller.state.gold,
          reputation: controller.state.hotelReputation,
          cleanliness: controller.state.roomConditions[roomId].cleanliness,
          declined: controller.state.declinedStayoverCleaningRoomIds.includes(roomId),
          resolved: controller.state.stayoverCleaningRequestGuestIds.includes(guestId),
          resultReputation: Number(latest?.reputationDelta ?? 0),
          intermissionReputation: Number(latest?.intermissionReputationDelta ?? 0),
          eventCount: latest?.intermissionEvents?.length ?? 0,
          lastOutcome: latest?.intermissionEvents?.at(-1)?.outcome ?? null,
        };
      };
      const prepare = () => {
        controller.state = structuredClone(snapshot);
        const config = controller.stayoverCleaningRequestConfig();
        const serviceCost = controller.roomServiceCost();
        const cleanliness = Math.min(72, controller.state.roomConditions[roomId].cleanliness);
        controller.state.gold = Math.max(controller.state.gold, serviceCost + 20);
        controller.state.roomConditions[roomId] = { cleanliness };
        controller.state.stayoverCleaningRequestChecked = true;
        controller.state.declinedStayoverCleaningRoomIds = [];
        controller.state.stayoverCleaningRequestGuestIds = (
          controller.state.stayoverCleaningRequestGuestIds ?? []
        ).filter(id => id !== guestId);
        controller.state.pendingStayoverCleaningRequest = {
          requestId: `STAYOVER_CLEANING:${controller.currentNightNumber}:${guestId}:${roomId}`,
          guestId,
          roomId,
          cleanliness,
          serviceCost,
          acceptReputation: config.acceptReputation,
          rejectReputation: config.rejectReputation,
        };
        renderApp(document.querySelector('#app'), controller);
        return {
          ...capture(),
          serviceCost,
          acceptReputation: config.acceptReputation,
          rejectReputation: config.rejectReputation,
        };
      };

      let output;
      try {
        const acceptBefore = prepare();
        document.querySelector(selector('accept'))?.click();
        const acceptAfter = capture();
        const rejectBefore = prepare();
        document.querySelector(selector('reject'))?.click();
        const rejectAfter = capture();
        output = {
          ok: true,
          viewport: { width: window.innerWidth, height: window.innerHeight },
          acceptBefore,
          acceptAfter,
          rejectBefore,
          rejectAfter,
        };
      } finally {
        controller.state = structuredClone(snapshot);
        controller.saveCheckpoint();
        renderApp(document.querySelector('#app'), controller);
      }
      output.originalStateRestored = controller.state.phase === snapshot.phase
        && controller.state.gold === snapshot.gold
        && controller.state.hotelReputation === snapshot.hotelReputation;
      return output;
    })()
    """.replace("__GUEST_ID__", json.dumps(guest_id)).replace(
        "__ROOM_ID__", json.dumps(room_id)
    )
    result = client.evaluate(expression)
    assert result["ok"], result
    assert result["viewport"] == {"width": 1280, "height": 720}, result
    assert result["originalStateRestored"] is True, result

    accepted_before = result["acceptBefore"]
    accepted = result["acceptAfter"]
    rejected_before = result["rejectBefore"]
    rejected = result["rejectAfter"]
    for prepared in (accepted_before, rejected_before):
        assert prepared["controlsPresent"] is True, result
        assert prepared["controlsVisible"] is True, result
        assert prepared["acceptDisabled"] is False, result

    assert accepted["pending"] is False and accepted["requestVisible"] is False, accepted
    assert accepted["gold"] == accepted_before["gold"] - accepted_before["serviceCost"], accepted
    assert accepted["reputation"] == (
        accepted_before["reputation"] + accepted_before["acceptReputation"]
    ), accepted
    assert accepted["cleanliness"] == 100, accepted
    assert accepted["declined"] is False and accepted["resolved"] is True, accepted
    assert accepted["resultReputation"] == (
        accepted_before["resultReputation"] + accepted_before["acceptReputation"]
    ), accepted
    assert accepted["intermissionReputation"] == (
        accepted_before["intermissionReputation"] + accepted_before["acceptReputation"]
    ), accepted
    assert accepted["eventCount"] == accepted_before["eventCount"] + 1, accepted
    assert accepted["lastOutcome"] == "ACCEPTED", accepted

    assert rejected["pending"] is False and rejected["requestVisible"] is False, rejected
    assert rejected["gold"] == rejected_before["gold"], rejected
    assert rejected["reputation"] == (
        rejected_before["reputation"] + rejected_before["rejectReputation"]
    ), rejected
    assert rejected["cleanliness"] == rejected_before["cleanliness"], rejected
    assert rejected["declined"] is True and rejected["resolved"] is True, rejected
    assert rejected["resultReputation"] == (
        rejected_before["resultReputation"] + rejected_before["rejectReputation"]
    ), rejected
    assert rejected["intermissionReputation"] == (
        rejected_before["intermissionReputation"] + rejected_before["rejectReputation"]
    ), rejected
    assert rejected["eventCount"] == rejected_before["eventCount"] + 1, rejected
    assert rejected["lastOutcome"] == "REJECTED", rejected

    return {
        "viewport": result["viewport"],
        "controls_visible": True,
        "accept": {
            "charged": accepted_before["gold"] - accepted["gold"],
            "cleanliness": accepted["cleanliness"],
            "reputation": accepted_before["acceptReputation"],
            "event": accepted["lastOutcome"],
        },
        "reject": {
            "charged": rejected_before["gold"] - rejected["gold"],
            "cleanliness": rejected["cleanliness"],
            "reputation": rejected_before["rejectReputation"],
            "event": rejected["lastOutcome"],
        },
        "original_state_restored": True,
    }


def run(url: str, port: int, seed: int = DEMO_SEED):
    target = debugger_target(port)
    client = CdpClient(target["webSocketDebuggerUrl"])
    timers: list[int] = []
    upgrades: list[str] = []
    card_selection_checks: dict[str, dict] = {}
    capacity_audits: list[dict] = []
    capacity_gate_checks: dict | None = None
    hard_feasibility_check: dict | None = None
    facility_service_check: dict | None = None
    drag_drop_checks: dict | None = None
    review_settlements: list[dict] = []
    elevator_context: dict | None = None
    checkpoint_reload: dict | None = None
    stayover_cleaning_request_inputs: dict | None = None
    try:
        client.command("Runtime.enable")
        client.command("Page.enable")
        client.command("Log.enable")
        client.command("Network.enable")
        client.command("Network.setCacheDisabled", {"cacheDisabled": True})
        client.command(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1280, "height": 720, "deviceScaleFactor": 1, "mobile": False},
        )
        client.command("Page.navigate", {"url": f"{seeded_url(url, seed)}&test_reset=bootstrap"})
        wait_for(client, "document.readyState !== 'loading'")
        client.command("Page.navigate", {"url": seeded_url(url, seed)})
        wait_for(client, "document.readyState !== 'loading'")
        wait_for(client, "Boolean(window.__vesperaController)", timeout=45.0)
        # Shared profile knowledge is a product feature; this deterministic
        # regression owns a clean browser-storage fixture.
        client.evaluate("localStorage.clear(); true")
        client.command("Page.navigate", {"url": f"{seeded_url(url, seed)}&test_reset=storage"})
        wait_for(client, "document.readyState !== 'loading'")
        client.command("Page.navigate", {"url": seeded_url(url, seed)})
        wait_for(client, "document.readyState !== 'loading'")
        wait_for(client, "Boolean(window.__vesperaController)", timeout=45.0)
        assert_preopening_copy(
            client,
            "개장 전 초청 영업에",
            "PRE-OPENING INVITATIONAL",
        )

        campaign_secretary_contract = client.evaluate(
            """
            (async () => {
              const [{ GameController }, { renderApp }] = await Promise.all([
                import('./src/state.js'),
                import('./src/render.js'),
              ]);
              const source = window.__vesperaController.data;
              const campaignData = {
                ...source,
                prototype_mode: { ...source.prototype_mode, type: 'CAMPAIGN' },
              };
              const memoryStorage = () => {
                const values = new Map();
                return {
                  getItem: key => values.has(key) ? values.get(key) : null,
                  setItem: (key, value) => values.set(key, value),
                  removeItem: key => values.delete(key),
                };
              };
              const campaign = new GameController(campaignData, {
                seed: 314159,
                storage: memoryStorage(),
              });
              const host = document.createElement('div');
              const selected = campaign.setSecretaryPresentation('MALE');
              const opened = campaign.beginOperatingDay(0);
              renderApp(host, campaign);
              const openingText = host.innerText;
              const openingPhase = campaign.state.phase;
              campaign.startDayBusiness();
              const businessPhase = campaign.state.phase;
              campaign.completeNight({
                income: 9,
                reputationDelta: 2,
                acceptedGuestIds: [],
                rejectedGuestIds: [],
                canceledGuestIds: [],
                placements: {},
                guestScores: {},
                guestReviews: [],
              });
              campaign.state.discoveredHiddenPreferenceIds.push('TEST:HIDDEN');
              campaign.state.lastDiscoveries = [{ hiddenId: 'TEST:HIDDEN' }];
              const reviewOpened = campaign.openResultReview();
              renderApp(host, campaign);
              const reviewText = host.innerText;
              const restarted = campaign.restartDayThroughSecretary();
              renderApp(host, campaign);
              const repeatedOpeningText = host.innerText;

              const showcase = new GameController(source, {
                seed: 314159,
                storage: memoryStorage(),
              });
              showcase.beginOperatingDay(0);
              showcase.state.phase = 'RESULT';
              const showcaseReviewOpened = showcase.openResultReview();

              const endlessData = {
                ...source,
                prototype_mode: { ...source.prototype_mode, type: 'ENDLESS' },
              };
              const endless = new GameController(endlessData, {
                seed: 271828,
                storage: memoryStorage(),
              });
              endless.beginOperatingDay(0);
              const endlessStartPhase = endless.state.phase;
              endless.completeNight({
                income: 7,
                reputationDelta: 1,
                acceptedGuestIds: [],
                rejectedGuestIds: [],
                canceledGuestIds: [],
                placements: {},
                guestScores: {},
                guestReviews: [],
              });
              const endlessRetried = endless.retryCurrentStage();
              return {
                selected,
                opened,
                openingPhase,
                businessPhase,
                reviewOpened,
                restarted,
                restoredPhase: campaign.state.phase,
                restoredGold: campaign.state.gold,
                restoredResults: campaign.state.nightResults.length,
                retryCount: campaign.state.foresightRetryCount,
                remembered: campaign.state.discoveredHiddenPreferenceIds.includes('TEST:HIDDEN'),
                presentation: campaign.state.secretaryPresentationId,
                openingHasBriefing: openingText.includes('영업 개시 보고'),
                reviewHasIndirectChoice: reviewText.includes('아침 장부부터 다시 읽어 줘.'),
                repeatedOpeningHasClue: repeatedOpeningText.includes('처음 펼친 장부인데'),
                leaksExplanation: ['예지', '관측', '시뮬레이션', '세계선'].some(
                  term => `${openingText} ${reviewText} ${repeatedOpeningText}`.includes(term),
                ),
                showcaseReviewOpened,
                endlessStartPhase,
                endlessRetried,
                endlessRestoredPhase: endless.state.phase,
              };
            })()
            """
        )
        assert campaign_secretary_contract == {
            "selected": True,
            "opened": True,
            "openingPhase": "DAY_OPENING",
            "businessPhase": "PLACEMENT",
            "reviewOpened": True,
            "restarted": True,
            "restoredPhase": "DAY_OPENING",
            "restoredGold": 0,
            "restoredResults": 0,
            "retryCount": 1,
            "remembered": True,
            "presentation": "MALE",
            "openingHasBriefing": True,
            "reviewHasIndirectChoice": True,
            "repeatedOpeningHasClue": True,
            "leaksExplanation": False,
            "showcaseReviewOpened": False,
            "endlessStartPhase": "PLACEMENT",
            "endlessRetried": True,
            "endlessRestoredPhase": "PLACEMENT",
        }, campaign_secretary_contract

        # Tutorial: two guests, no deadline, and a valid solution starts Night 1.
        client.click('[data-action="start"]')
        tutorial = controller_state(client)
        assert tutorial["phase"] == "TUTORIAL"
        assert tutorial["serviceTimerMs"] is None
        checkpoint_before_reload = {
            "phase": tutorial["phase"],
            "runSeed": tutorial["runSeed"],
            "acceptedGuestIds": tutorial["acceptedGuestIds"],
        }
        client.command("Page.navigate", {"url": f"{seeded_url(url, seed)}&test_reset=checkpoint"})
        wait_for(client, "document.readyState !== 'loading'")
        client.command("Page.navigate", {"url": seeded_url(url, seed)})
        wait_for(client, "document.readyState !== 'loading'")
        wait_for(client, "Boolean(window.__vesperaController)", timeout=45.0)
        reloaded_title = controller_state(client)
        assert reloaded_title["phase"] == "TITLE", reloaded_title
        assert client.evaluate("window.__vesperaController.hasCheckpoint()") is True
        require_text(client, "지난 영업 이어하기")
        client.click('[data-action="resume"]')
        resumed = controller_state(client)
        assert resumed["phase"] == checkpoint_before_reload["phase"], resumed
        assert resumed["runSeed"] == checkpoint_before_reload["runSeed"], resumed
        assert resumed["acceptedGuestIds"] == checkpoint_before_reload["acceptedGuestIds"], resumed
        assert resumed["serviceTimerMs"] is None, resumed
        checkpoint_reload = {
            "saved_phase": checkpoint_before_reload["phase"],
            "reloaded_at_title": True,
            "resume_action_visible": True,
            "restored_seed": resumed["runSeed"],
            "restored_phase": resumed["phase"],
        }
        elevator_context = assert_elevator_room_context(client)
        require_text(client, "시간 제한 없음")
        dispatch_drag(client, "G01_LUNE", 'article.room-card[data-room-id="F3-B"]')
        dispatch_drag(client, "G02_MORROW", 'article.room-card[data-room-id="F1-B"]')
        assert controller_state(client)["placements"] == {
            "G01_LUNE": "F3-B",
            "G02_MORROW": "F1-B",
        }
        client.click('[data-action="finish-night"]')

        # Night 1: first placement is free, moving costs five seconds, handbook pauses.
        started = assert_timed_placement(client, 1)
        capacity_audits.append(assert_capacity_contract(
            client,
            "night1",
            expected_service_limit=5,
        ))
        timers.append(started["serviceTimerMs"])
        drag_drop_checks = assert_drag_drop_only_placement(client)
        card_selection_checks["waiting_guest"] = drag_drop_checks["waiting_card"]
        card_selection_checks["night1_placed_guest"] = drag_drop_checks["placed_card"]
        relocation_cost = drag_drop_checks["drag_move"]["timer_cost_ms"]

        client.click('[data-action="open-handbook"]')
        assert_preopening_copy(client, "개장 전 초청 영업")
        paused_at = controller_state(client)["serviceTimerMs"]
        time.sleep(1.1)
        paused_after = controller_state(client)["serviceTimerMs"]
        assert abs(paused_at - paused_after) <= 80, (paused_at, paused_after)
        client.click('[data-action="close-handbook"]')

        # The first timeout proves deterministic emergency assignment without preference maximization.
        client.evaluate("window.__vesperaController.state.serviceTimerMs = 100")
        wait_for(client, "window.__vesperaController.state.phase === 'RESULT'", timeout=5)
        night1 = controller_state(client)
        report1 = night1["nightResults"][0]["emergencyReport"]
        assert report1["timedOut"] is True
        assert night1["nightResults"][0]["valid"] is True
        assert report1["autoAssignedGuestIds"]
        require_text(client, "프런트 긴급 배정")
        assert_preopening_copy(client, "PRE-OPENING NIGHT 1 COMPLETE")
        assert "이번 영업 다시" not in client.body_text()
        no_maximum_reveal(client)
        review_settlements.append(assert_guest_review_settlement(client, 0))

        renovation = continue_through_renovation(client, probe_category_gate=True)
        upgrades.extend(renovation["chosenIds"])

        # Night 2 normal placement.
        capacity_audits.append(assert_capacity_contract(
            client,
            "night2",
            expected_service_limit=6,
        ))
        assert_preopening_copy(client, "PRE-OPENING NIGHT 2 OF 5")
        route2 = choose_reservations(client, "balanced")
        client.click('[data-action="confirm-reservation"]')
        night2_placement = assert_timed_placement(client, 2)
        timers.append(night2_placement["serviceTimerMs"])
        auto_assign(client)
        other_guest = client.evaluate(
            """
            (() => {
              const state = window.__vesperaController.state;
              return Object.keys(state.placements).find(
                id => id !== state.selectedGuestId && !state.lockedGuestIds.includes(id),
              );
            })()
            """
        )
        assert other_guest, controller_state(client)
        card_selection_checks["placed_guest"] = assert_guest_card_selection(
            client,
            other_guest,
            location="placed",
        )
        client.click('[data-action="finish-night"]')
        wait_for(client, "window.__vesperaController.state.phase === 'RESULT'")
        assert len(controller_state(client)["nightResults"]) == 2
        no_maximum_reveal(client)
        review_settlements.append(assert_guest_review_settlement(client, 1))
        renovation = continue_through_renovation(client)
        upgrades.extend(renovation["chosenIds"])

        # Night 3 favors an R+ guest, and returning fixed guest Morrow receives
        # a revisit item. The complete route must reveal hidden data by Night 5.
        capacity_audits.append(assert_capacity_contract(
            client,
            "night3",
            expected_service_limit=7,
        ))
        route3 = choose_reservations(client, "hidden")
        client.click('[data-action="confirm-reservation"]')
        night3_placement = assert_timed_placement(client, 3)
        timers.append(night3_placement["serviceTimerMs"])
        auto_assign(client)
        client.click('[data-action="finish-night"]')
        wait_for(client, "window.__vesperaController.state.phase === 'RESULT'")
        after_night3 = controller_state(client)
        review_settlements.append(assert_guest_review_settlement(client, 2))
        assert any(
            item.get("source") == "revisit"
            for score in after_night3["nightResults"][2]["guestScores"].values()
            for item in score["items"]
        )
        assert after_night3["stayovers"], "Night 3 must create a two-night stayover"
        stayover_id, stayover_entry = next(iter(after_night3["stayovers"].items()))
        stayover_room = stayover_entry["roomId"]

        # During the intermission an occupied stayover room can be cleaned
        # proactively before the guest needs to make a formal request.
        client.click('[data-action="continue-result"]')
        wait_for(client, "window.__vesperaController.state.phase === 'UPGRADE'")
        stayover_cleaning_request_inputs = assert_stayover_cleaning_request_input_paths(
            client,
            stayover_id,
            stayover_room,
        )
        before_stayover_state = controller_state(client)
        before_stayover_service = before_stayover_state["roomConditions"][stayover_room]
        assert before_stayover_service["cleanliness"] < 100
        stayover_service_cost = client.evaluate(
            "window.__vesperaController.roomServiceCost()"
        )
        proactive_service = client.evaluate(
            f"window.__vesperaController.serviceRoom({json.dumps(stayover_room)})"
        )
        assert proactive_service is True
        after_stayover_service = controller_state(client)
        assert after_stayover_service["roomConditions"][stayover_room] == {
            "cleanliness": 100,
        }
        assert after_stayover_service["gold"] == (
            before_stayover_state["gold"] - stayover_service_cost
        )
        # Keep the rest of this long route comparable with its pre-cleanliness
        # capacity and upgrade assertions; the probe above already verified the
        # real charge, so only its test-local gold mutation is rolled back.
        client.evaluate(
            f"window.__vesperaController.state.gold = {before_stayover_state['gold']}; true"
        )
        rerender(client)
        blocked_renovation = assert_stayover_renovation_guard(
            client,
            stayover_room,
            expected_blocked=True,
        )
        renovation = choose_upgrade(client, prefer_expansion=True)
        upgrades.extend(renovation["chosenIds"])

        # Night 4: the stayover occupies capacity, keeps its room, cannot be
        # moved, and cannot be selected for timeout cancellation.
        night4_reservation = controller_state(client)
        assert night4_reservation["phase"] == "RESERVATION"
        assert stayover_id in night4_reservation["lockedGuestIds"]
        assert stayover_id in night4_reservation["currentFixedGuestIds"]
        assert night4_reservation["placements"][stayover_id] == stayover_room
        capacity_audits.append(assert_capacity_contract(
            client,
            "night4",
            expected_service_limit=7,
        ))
        summary = client.evaluate("window.__vesperaController.reservationSummary()")
        assert stayover_id in summary["accepted"], summary
        assert len(summary["accepted"]) == len(set(summary["accepted"])), summary
        assert summary["accepted"].count(stayover_id) == 1, summary
        assert summary["stayoverRoomCount"] == len({
            entry["roomId"] for entry in night4_reservation["stayovers"].values()
        }), summary
        other_room = client.evaluate(
            f"window.__vesperaController.data.rooms.find(room => room.id !== {json.dumps(stayover_room)} && room.built_from_start !== false).id"
        )
        move_results = client.evaluate(
            f"""
            (() => {{
              const controller = window.__vesperaController;
              return {{
                unplace: controller.unplaceGuest({json.dumps(stayover_id)}),
                move: controller.placeGuest({json.dumps(stayover_id)}, {json.dumps(other_room)}),
                room: controller.state.placements[{json.dumps(stayover_id)}],
              }};
            }})()
            """
        )
        assert move_results == {"unplace": False, "move": False, "room": stayover_room}
        rerender(client)

        hard_feasibility_check = assert_capacity_does_not_guarantee_hard_feasibility(client)
        route4 = choose_reservations(client, "synergy")
        capacity_gate_checks = assert_reservation_cardinality_gates(client)
        client.click('[data-action="confirm-reservation"]')
        night4_placement = assert_timed_placement(client, 4)
        timers.append(night4_placement["serviceTimerMs"])
        plan4 = auto_assign(client)
        assert plan4["placements"][stayover_id] == stayover_room
        card_selection_checks["stayover_guest"] = assert_guest_card_selection(
            client,
            stayover_id,
            location="stayover",
        )
        client.evaluate("window.__vesperaController.state.serviceTimerMs = 100")
        wait_for(client, "window.__vesperaController.state.phase === 'RESULT'", timeout=5)
        after_night4 = controller_state(client)
        report4 = after_night4["nightResults"][3]["emergencyReport"]
        assert stayover_id in report4["lockedGuestIds"]
        assert stayover_id not in after_night4["nightResults"][3]["canceledGuestIds"]
        assert after_night4["nightResults"][3]["placements"][stayover_id] == stayover_room
        assert stayover_id not in after_night4["stayovers"], "Two-night stayover must release after its second night"
        no_maximum_reveal(client)
        review_settlements.append(assert_guest_review_settlement(client, 3))

        # Once released, the worn room can be serviced in the next preparation step.
        client.click('[data-action="continue-result"]')
        wait_for(client, "window.__vesperaController.state.phase === 'UPGRADE'")
        facility_service_check = assert_facility_room_excluded_from_service(client)
        before_service = controller_state(client)["roomConditions"][stayover_room]
        assert before_service != {"cleanliness": 100}
        released_service = client.evaluate(
            f"window.__vesperaController.serviceRoom({json.dumps(stayover_room)})"
        )
        assert released_service is True
        assert controller_state(client)["roomConditions"][stayover_room] == {
            "cleanliness": 100,
        }
        released_renovation = assert_stayover_renovation_guard(
            client,
            stayover_room,
            expected_blocked=False,
            upgrade_id=blocked_renovation["upgradeId"],
        )
        # Stayover-cleaning requests have their own focused regression. Keep
        # this legacy timed-service route on its original upgrade-flow scope.
        client.evaluate(
            "window.__vesperaController.state.stayoverCleaningRequestChecked = true; true"
        )
        renovation = choose_upgrade(client, prefer_expansion=True)
        upgrades.extend(renovation["chosenIds"])

        # Night 5: SSR appears as an explicit showcase invitation, not a
        # permanent unlock. Its placement is timed like every real night.
        fifth = controller_state(client)
        assert fifth["phase"] == "RESERVATION"
        capacity_audits.append(assert_capacity_contract(
            client,
            "night5",
            expected_service_limit=7,
        ))
        assert fifth["specialInviteGuestIds"]
        require_text(client, "SSR 왕실 특별 초청")
        require_text(client, "최종 등급의 까다로운 요청과 높은 보상이 함께 도착했습니다")
        assert "영구 해금" not in client.body_text()
        route5 = choose_reservations(client, "ssr")
        assert set(fifth["specialInviteGuestIds"]) & set(route5["chosen"])
        client.click('[data-action="confirm-reservation"]')
        night5_placement = assert_timed_placement(client, 5)
        timers.append(night5_placement["serviceTimerMs"])
        auto_assign(client)
        client.click('[data-action="finish-night"]')
        wait_for(client, "window.__vesperaController.state.phase === 'RESULT'")
        assert len(controller_state(client)["nightResults"]) == 5
        review_settlements.append(assert_guest_review_settlement(client, 4))
        client.click('[data-action="continue-result"]')
        wait_for(client, "window.__vesperaController.state.phase === 'FINAL'")
        final = controller_state(client)
        assert final["phase"] == "FINAL"
        assert len(final["nightResults"]) == 5
        assert final["runSeed"] == seed
        assert final["runRecord"]["ending_id"] == "PREOPENING_COMPLETE"
        assert final["runRecord"]["outcome"] == "COMPLETE"
        assert final["runRecord"]["metrics"]["completed_nights"] == 5
        assert final["recordArchiveCount"] >= 1
        assert final["discoveredHiddenPreferenceIds"], final["nightResults"]
        assert_preopening_copy(
            client,
            "PRE-OPENING INVITATIONAL COMPLETE",
            "개장 전 다섯 영업",
        )
        require_text(client, "수용과 배치, 공사 계약으로 달라진 호텔의 운영 기록입니다")
        assert "영구 해금" not in client.body_text()
        no_maximum_reveal(client)

        exception_events = [
            event
            for event in client.events
            if event.get("method") in {"Runtime.exceptionThrown", "Log.entryAdded"}
            and (
                event.get("method") == "Runtime.exceptionThrown"
                or event.get("params", {}).get("entry", {}).get("level") == "error"
            )
        ]
        if exception_events:
            raise AssertionError(f"Browser errors detected: {exception_events}")

        record_and_restart = client.evaluate(
            """
            (() => {
              const controller = window.__vesperaController;
              const before = {
                count: controller.state.recordArchiveCount,
                recordId: controller.state.runRecord.record_id,
                seed: controller.state.runSeed,
              };
              controller.completeRun();
              const afterDuplicateCompletion = {
                count: controller.state.recordArchiveCount,
                recordId: controller.state.runRecord.record_id,
              };
              controller.restart();
              return {
                before,
                afterDuplicateCompletion,
                restarted: {
                  phase: controller.state.phase,
                  seed: controller.state.runSeed,
                  runRecord: controller.state.runRecord,
                  archiveCount: controller.state.recordArchiveCount,
                },
              };
            })()
            """
        )
        assert record_and_restart["afterDuplicateCompletion"] == {
            "count": record_and_restart["before"]["count"],
            "recordId": record_and_restart["before"]["recordId"],
        }, record_and_restart
        assert record_and_restart["restarted"]["phase"] == "TITLE", record_and_restart
        assert record_and_restart["restarted"]["seed"] == (seed + 1) & 0xFFFFFFFF, record_and_restart
        assert record_and_restart["restarted"]["runRecord"] is None, record_and_restart
        assert record_and_restart["restarted"]["archiveCount"] == record_and_restart["before"]["count"], record_and_restart

        return {
            "status": "PASS",
            "seed": seed,
            "tutorial": "untimed-complete",
            "timed_nights": len(timers),
            "timer_starts_ms": timers,
            "relocation_cost_ms": relocation_cost,
            "handbook_pauses_timer": True,
            "guest_card_selection": card_selection_checks,
            "drag_drop_only_placement": drag_drop_checks,
            "emergency_nights": [1, 4],
            "stayover": {
                "guest_id": stayover_id,
                "room_id": stayover_room,
                "capacity_counted": True,
                "fixed_and_noncancellable": True,
                "proactive_cleaning_during_stay": proactive_service is True,
                "cleaning_request_input_paths": stayover_cleaning_request_inputs,
                "service_after_release": released_service is True,
                "renovation_blocked_then_released": {
                    "upgrade_id": blocked_renovation["upgradeId"],
                    "affected_rooms": blocked_renovation["affectedRoomIds"],
                    "blocked_during_stay": blocked_renovation["contracted"] is False,
                    "contractable_after_checkout": released_renovation["contracted"] is True,
                },
            },
            "renovation_category_gate": True,
            "capacity_audits": [
                {
                    "label": item["label"],
                    "service_limit": item["serviceLimit"],
                    "built_rooms": item["builtRoomCount"],
                    "physical_slots": item["physicalPlacementLimit"],
                    "open_slots": item["openRoomCount"],
                    "stayover_rooms": item["stayoverRoomIds"],
                }
                for item in capacity_audits
            ],
            "capacity_cardinality_gates": {
                "physical_gate": capacity_gate_checks["physical"],
                "booking_gate": capacity_gate_checks["booking"],
            },
            "capacity_not_hard_feasibility": hard_feasibility_check,
            "facility_room_service_exclusion": facility_service_check,
            "owned_upgrades": final["ownedUpgradeIds"],
            "purchased_route": upgrades,
            "hidden_discoveries": final["discoveredHiddenPreferenceIds"],
            "reservation_routes": {
                "night2": route2,
                "night3": route3,
                "night4": route4,
                "night5": route5,
            },
            "results": len(final["nightResults"]),
            "guest_review_settlements": review_settlements,
            "elevator_room_context": elevator_context,
            "record_and_restart": record_and_restart,
            "checkpoint_reload": checkpoint_reload,
            "campaign_secretary_contract": campaign_secretary_contract,
            "final_phase": final["phase"],
        }
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--debug-port", type=int, default=9223)
    parser.add_argument("--seed", type=int, default=DEMO_SEED)
    args = parser.parse_args()
    print(json.dumps(run(args.url, args.debug_port, args.seed), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
