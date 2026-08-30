from __future__ import annotations

import argparse
import base64
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import websocket


ROOT = Path(__file__).resolve().parents[1]
DEMO_SEED = 20_260_819
PLAYER_FACING_META_TERMS = ("압축", "쇼케이스", "시연", "SHOWCASE", "ACCELERATED")

# Kept for callers that imported the old route names. The five-night smoke now
# follows generated offers and can own several facilities at once.
ROUTES = {
    "SOUNDPROOFING": {},
    "LOUNGE": {},
    "SECRET_PASSAGE": {},
}

VIDEO_FRAME_NAMES = (
    "title.png",
    "tutorial.png",
    "handbook-ranks.png",
    "night1.png",
    "result1.png",
    "upgrade-r.png",
    "reservation2.png",
    "result3-discovery.png",
    "upgrade-expansion.png",
    "night4-synergy.png",
    "reservation5-ssr.png",
    "night5.png",
    "final.png",
)


class CdpClient:
    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(
            ws_url,
            # A fresh Edge 152 profile can acknowledge its first same-host
            # navigation after more than eight seconds while still completing
            # normally. Keep the command channel aligned with the controller
            # startup allowance so a slow cold start is not reported as a game
            # regression.
            timeout=45,
            origin="http://127.0.0.1",
            suppress_origin=True,
        )
        self.next_id = 1
        self.events = []

    def close(self):
        self.ws.close()

    def command(self, method: str, params: dict | None = None):
        command_id = self.next_id
        self.next_id += 1
        self.ws.send(json.dumps({"id": command_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == command_id:
                if "error" in message:
                    raise RuntimeError(f"CDP {method} failed: {message['error']}")
                return message.get("result", {})
            self.events.append(message)

    def evaluate(self, expression: str):
        result = self.command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"])
        return result.get("result", {}).get("value")

    def click(self, selector: str):
        encoded = json.dumps(selector)
        clicked = self.evaluate(
            f"""
            (() => {{
              const element = document.querySelector({encoded});
              if (!element || element.disabled) return false;
              element.click();
              return true;
            }})()
            """
        )
        if not clicked:
            raise AssertionError(f"Element not found or disabled: {selector}")

    def body_text(self):
        return self.evaluate("document.body.innerText") or ""


def debugger_target(port: int, timeout: float = 10.0):
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/json"
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                targets = json.load(response)
            pages = [
                target for target in targets
                if target.get("type") == "page"
                and target.get("url", "").startswith(("http://", "https://"))
            ]
            if pages:
                return pages[0]
        except Exception as error:  # browser may still be starting
            last_error = error
        time.sleep(0.15)
    raise RuntimeError(f"Could not find Edge debugging target: {last_error}")


def wait_for(client: CdpClient, expression: str, timeout: float = 10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if client.evaluate(expression):
            return
        time.sleep(0.1)
    raise AssertionError(f"Timed out waiting for: {expression}")


def place(client: CdpClient, guest_id: str, room_id: str):
    """Compatibility placement helper using the live HTML5 drag/drop path."""

    result = client.evaluate(
        f"""
        (() => {{
          const guestId = {json.dumps(guest_id)};
          const roomId = {json.dumps(room_id)};
          const source = document.querySelector(`[data-drag-guest="${{guestId}}"]`);
          const target = document.querySelector(`article.room-card[data-room-id="${{roomId}}"]`);
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
    if not result["ok"] or result["transferredGuestId"] != guest_id:
        raise AssertionError(f"Could not drag {guest_id} to {room_id}: {result}")


def require_text(client: CdpClient, expected: str):
    text = client.body_text()
    if expected not in text:
        raise AssertionError(f"Expected text not found: {expected}\n--- BODY ---\n{text[:5000]}")


def assert_preopening_copy(client: CdpClient, *required: str) -> dict:
    """Keep build/meta terminology out of the player-facing hotel fiction."""

    body = client.body_text()
    found_forbidden = [term for term in PLAYER_FACING_META_TERMS if term in body]
    missing = [text for text in required if text not in body]
    assert not found_forbidden, {
        "forbidden_terms": found_forbidden,
        "body": body[:5_000],
    }
    assert not missing, {
        "missing_preopening_copy": missing,
        "body": body[:5_000],
    }
    return {
        "forbidden_terms": [],
        "required_copy": list(required),
    }


def capture(client: CdpClient, path: Path):
    """Compatibility helper used by the video exporter."""

    client.evaluate("window.scrollTo(0, 0); true")
    image = client.command("Page.captureScreenshot", {"format": "png"})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(image["data"]))


def controller_state(client: CdpClient) -> dict:
    return client.evaluate("JSON.parse(JSON.stringify(window.__vesperaController.state))")


def seeded_url(url: str, seed: int) -> str:
    parts = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    query["seed"] = str(seed)
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path or "/", urllib.parse.urlencode(query), parts.fragment)
    )


def rerender(client: CdpClient) -> None:
    rendered = client.evaluate(
        """
        import(new URL('./src/render.js', document.baseURI).href).then(({ renderApp }) => {
          renderApp(document.querySelector('#app'), window.__vesperaController);
          return true;
        })
        """
    )
    if not rendered:
        raise AssertionError("Could not rerender the game")


def auto_assign(client: CdpClient, allow_cancellation: bool = False) -> dict:
    result = client.evaluate(
        """
        (async () => {
          const controller = window.__vesperaController;
          const { createEmergencyPlan } = await import(new URL('./src/emergency.js', document.baseURI).href);
          const plan = createEmergencyPlan(
            controller.data,
            controller.state.acceptedGuestIds,
            controller.state.placements,
            controller.hotelContext(),
            { lockedGuestIds: controller.state.lockedGuestIds },
          );
          controller.state.acceptedGuestIds = [...plan.housedGuestIds];
          controller.state.placements = { ...plan.placements };
          controller.state.selectedGuestId = plan.housedGuestIds.find(
            id => !controller.state.lockedGuestIds.includes(id),
          ) ?? plan.housedGuestIds[0] ?? null;
          const evaluation = controller.currentEvaluation();
          const { renderApp } = await import(new URL('./src/render.js', document.baseURI).href);
          renderApp(document.querySelector('#app'), controller);
          return {
            ...plan,
            valid: evaluation?.valid ?? false,
            placementScore: evaluation?.placementScore ?? 0,
            groupEffects: evaluation?.groupEffects ?? [],
          };
        })()
        """
    )
    if not result["valid"]:
        raise AssertionError(f"Automatic representative assignment is invalid: {result}")
    if result["canceledGuestIds"] and not allow_cancellation:
        raise AssertionError(f"Representative route unexpectedly canceled guests: {result}")
    return result


def choose_reservations(client: CdpClient, mode: str = "balanced") -> dict:
    """Choose the best feasible subset from the four visible applications.

    The helper does not inject guests. It only evaluates subsets of the seeded
    offer, then calls the same public decision methods as the UI.
    """

    encoded_mode = json.dumps(mode)
    result = client.evaluate(
        f"""
        (async () => {{
          const controller = window.__vesperaController;
          const mode = {encoded_mode};
          const {{ createEmergencyPlan }} = await import(new URL('./src/emergency.js', document.baseURI).href);
          const offers = [...controller.state.currentGuestOfferIds];
          const fixed = [...controller.state.currentFixedGuestIds];
          const capacity = controller.roomCapacitySummary();
          const ranks = {{ N: 0, R: 1, SR: 2, SSR: 3 }};
          let best = null;
          for (let mask = 0; mask < (1 << offers.length); mask += 1) {{
            const chosen = offers.filter((_, index) => mask & (1 << index));
            const accepted = [...new Set([...fixed, ...chosen])];
            if (
              !accepted.length
              || accepted.length > capacity.serviceLimit
              || accepted.length > capacity.physicalPlacementLimit
            ) continue;
            const plan = createEmergencyPlan(
              controller.data,
              accepted,
              controller.state.placements,
              controller.hotelContext(),
              {{ lockedGuestIds: controller.state.lockedGuestIds }},
            );
            if (plan.canceledGuestIds.length || plan.housedGuestIds.length !== accepted.length) continue;
            const counts = {{}};
            for (const id of accepted) {{
              const species = controller.data.indexes.guests[id].species;
              counts[species] = (counts[species] ?? 0) + 1;
            }}
            const maxSpecies = Math.max(0, ...Object.values(counts));
            const highRanks = chosen.reduce((sum, id) => sum + (ranks[controller.data.indexes.guests[id].rank] > 0 ? 1 : 0), 0);
            const rankValue = chosen.reduce((sum, id) => sum + ranks[controller.data.indexes.guests[id].rank], 0);
            const specials = chosen.filter(id => controller.state.specialInviteGuestIds.includes(id)).length;
            let score = chosen.length * 100 + rankValue * 10 + maxSpecies;
            if (mode === 'hidden') score += highRanks * 10_000;
            if (mode === 'synergy') score += maxSpecies * 10_000;
            if (mode === 'ssr') score += specials * 100_000 + rankValue * 1_000;
            if (!best || score > best.score) best = {{ chosen, accepted, plan, score, maxSpecies }};
          }}
          if (!best) return {{ ok: false, reason: 'NO_FEASIBLE_SUBSET', offers, fixed }};
          for (const id of offers) {{
            controller.setApplicantDecision(id, best.chosen.includes(id) ? 'accept' : 'reject');
          }}
          const {{ renderApp }} = await import(new URL('./src/render.js', document.baseURI).href);
          renderApp(document.querySelector('#app'), controller);
          return {{
            ok: true,
            chosen: best.chosen,
            rejected: offers.filter(id => !best.chosen.includes(id)),
            accepted: best.accepted,
            maxSpecies: best.maxSpecies,
            offerIds: offers,
          }};
        }})()
        """
    )
    if not result["ok"]:
        raise AssertionError(f"No feasible seeded reservation decision: {result}")
    return result


def choose_upgrade(client: CdpClient, prefer_expansion: bool = True) -> dict:
    result = client.evaluate(
        f"""
        (async () => {{
          const controller = window.__vesperaController;
          const offers = controller.state.currentUpgradeOfferIds
            .map(id => controller.data.indexes.upgrades[id])
            .filter(Boolean);
          const order = {{ EXPAND_F1_D: 1, EXPAND_F2_D: 2, EXPAND_F3_D: 3 }};
          const chosenIds = [];
          const kinds = {str(prefer_expansion).lower()}
            ? ['EXPANSION', 'FACILITY']
            : ['FACILITY', 'EXPANSION'];
          for (const kind of kinds) {{
            const candidates = offers
              .filter(item => item.kind === kind && item.cost <= controller.state.gold)
              .sort((left, right) => (order[left.id] ?? 99) - (order[right.id] ?? 99));
            const chosen = candidates.find(item => controller.buyUpgrade(item.id));
            if (chosen) chosenIds.push(chosen.id);
          }}
          const ok = controller.finishUpgrade();
          const {{ renderApp }} = await import(new URL('./src/render.js', document.baseURI).href);
          renderApp(document.querySelector('#app'), controller);
          return {{
            ok,
            chosenId: chosenIds[0] ?? null,
            chosenIds,
            offeredIds: offers.map(item => item.id),
          }};
        }})()
        """
    )
    if not result["ok"]:
        raise AssertionError(f"Could not leave upgrade screen: {result}")
    return result


def collect_target_rectangles(client: CdpClient) -> list[dict]:
    return client.evaluate(
        """
        Array.from(document.querySelectorAll('[data-video-target]')).map((element) => {
          const rect = element.getBoundingClientRect();
          const style = getComputedStyle(element);
          let left = Math.max(0, rect.left);
          let right = Math.min(innerWidth, rect.right);
          let top = Math.max(0, rect.top);
          let bottom = Math.min(innerHeight, rect.bottom);
          for (let ancestor = element.parentElement; ancestor; ancestor = ancestor.parentElement) {
            const ancestorStyle = getComputedStyle(ancestor);
            const ancestorRect = ancestor.getBoundingClientRect();
            if (['auto', 'scroll', 'hidden', 'clip'].includes(ancestorStyle.overflowX)) {
              left = Math.max(left, ancestorRect.left);
              right = Math.min(right, ancestorRect.right);
            }
            if (['auto', 'scroll', 'hidden', 'clip'].includes(ancestorStyle.overflowY)) {
              top = Math.max(top, ancestorRect.top);
              bottom = Math.min(bottom, ancestorRect.bottom);
            }
          }
          const inViewport = right > left && bottom > top;
          const inset = 2;
          const points = inViewport ? [
            [(left + right) / 2, (top + bottom) / 2],
            [Math.min(right - inset, left + inset), Math.min(bottom - inset, top + inset)],
            [Math.max(left + inset, right - inset), Math.min(bottom - inset, top + inset)],
            [Math.min(right - inset, left + inset), Math.max(top + inset, bottom - inset)],
            [Math.max(left + inset, right - inset), Math.max(top + inset, bottom - inset)],
          ] : [];
          const unobscured = points.some(([x, y]) => {
            const hit = document.elementFromPoint(x, y);
            return Boolean(hit && (hit === element || element.contains(hit)));
          });
          const visible = rect.width > 0 && rect.height > 0
            && inViewport
            && style.display !== 'none'
            && style.visibility !== 'hidden'
            && Number(style.opacity) > 0
            && unobscured;
          return {
            target: element.dataset.videoTarget,
            x: Math.round(left),
            y: Math.round(top),
            width: Math.round(right - left),
            height: Math.round(bottom - top),
            visible,
          };
        }).filter(item => item.visible)
        """
    )


def capture_frame(
    client: CdpClient,
    path: Path,
    target_log: dict[str, list[dict]],
    scroll_target: str | None = None,
) -> None:
    if scroll_target:
        client.evaluate(
            f"""
            (() => {{
              const element = document.querySelector('[data-video-target={json.dumps(scroll_target)[1:-1]}]');
              if (!element) return false;
              element.scrollIntoView({{ block: 'center', inline: 'center' }});
              return true;
            }})()
            """
        )
    else:
        client.evaluate("window.scrollTo(0, 0); true")
    time.sleep(0.05)
    image = client.command("Page.captureScreenshot", {"format": "png"})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(image["data"]))
    target_log[path.name] = collect_target_rectangles(client)


def no_maximum_reveal(client: CdpClient) -> None:
    body = client.body_text()
    forbidden = ("최대 만족", "최고 만족", "최대 평가", "validated_max")
    found = [text for text in forbidden if text in body]
    if found:
        raise AssertionError(f"The UI revealed a validated maximum: {found}")


def assert_placement_layout(
    client: CdpClient,
    viewport_height: int,
    label: str,
) -> dict:
    """Reject document scrolling or clipped placement controls at this state."""

    result = client.evaluate(
        """
        (() => {
          const measure = selector => {
            const element = document.querySelector(selector);
            if (!element) return null;
            const rect = element.getBoundingClientRect();
            const style = getComputedStyle(element);
            return {
              selector,
              left: Math.round(rect.left),
              top: Math.round(rect.top),
              right: Math.round(rect.right),
              bottom: Math.round(rect.bottom),
              width: Math.round(rect.width),
              height: Math.round(rect.height),
              clientWidth: element.clientWidth,
              clientHeight: element.clientHeight,
              scrollWidth: element.scrollWidth,
              scrollHeight: element.scrollHeight,
              overflowX: style.overflowX,
              overflowY: style.overflowY,
            };
          };
          const controller = window.__vesperaController;
          return {
            phase: controller?.state.phase ?? null,
            scrollY: Math.round(scrollY),
            documentScrollHeight: Math.max(
              document.documentElement.scrollHeight,
              document.body?.scrollHeight ?? 0,
            ),
            documentClientHeight: document.documentElement.clientHeight,
            screen: measure('.placement-screen'),
            layout: measure('.placement-layout'),
            boardPanel: measure('.board-panel'),
            board: measure('.hotel-board'),
            waiting: measure('[data-waiting-zone]'),
            waitingGuests: measure('.waiting-guests'),
            detail: measure('.detail-panel'),
            actionBar: measure('.placement-screen > .action-bar'),
          };
        })()
        """
    )
    result["label"] = label
    assert result["phase"] in {"TUTORIAL", "PLACEMENT"}, result
    assert result["documentScrollHeight"] <= viewport_height + 1, result
    assert result["documentClientHeight"] == viewport_height, result
    assert abs(result["scrollY"]) <= 1, result

    action_bar = result["actionBar"]
    assert action_bar and action_bar["top"] >= -1, result
    assert action_bar["bottom"] <= viewport_height + 1, result

    for key in ("layout", "boardPanel", "board", "waiting", "waitingGuests"):
        box = result[key]
        assert box, (label, key, result)
        assert box["scrollWidth"] <= box["clientWidth"] + 1, (label, key, box)
        assert box["scrollHeight"] <= box["clientHeight"] + 1, (label, key, box)

    board_panel = result["boardPanel"]
    waiting = result["waiting"]
    assert waiting["bottom"] <= board_panel["bottom"] + 1, result
    assert result["layout"]["bottom"] <= action_bar["top"] + 1, result
    assert result["detail"]["bottom"] <= result["layout"]["bottom"] + 1, result
    return result


def assert_action_screen_layout(
    client: CdpClient,
    viewport_height: int,
    label: str,
    *,
    expected_phase: str,
    screen_selector: str,
    action_selector: str,
) -> dict:
    """Ensure a result/final action stays reachable without page scrolling."""

    result = client.evaluate(
        f"""
        (() => {{
          const measure = selector => {{
            const element = document.querySelector(selector);
            if (!element) return null;
            const rect = element.getBoundingClientRect();
            return {{
              left: Math.round(rect.left),
              top: Math.round(rect.top),
              right: Math.round(rect.right),
              bottom: Math.round(rect.bottom),
              width: Math.round(rect.width),
              height: Math.round(rect.height),
              clientWidth: element.clientWidth,
              clientHeight: element.clientHeight,
              scrollWidth: element.scrollWidth,
              scrollHeight: element.scrollHeight,
            }};
          }};
          return {{
            phase: window.__vesperaController?.state.phase ?? null,
            scrollY: Math.round(scrollY),
            documentScrollHeight: Math.max(
              document.documentElement.scrollHeight,
              document.body?.scrollHeight ?? 0,
            ),
            documentClientHeight: document.documentElement.clientHeight,
            screen: measure({json.dumps(screen_selector)}),
            action: measure({json.dumps(action_selector)}),
          }};
        }})()
        """
    )
    result["label"] = label
    assert result["phase"] == expected_phase, result
    assert result["documentScrollHeight"] <= viewport_height + 1, result
    assert result["documentClientHeight"] == viewport_height, result
    assert abs(result["scrollY"]) <= 1, result
    assert result["screen"], result
    assert result["screen"]["scrollWidth"] <= result["screen"]["clientWidth"] + 1, result
    action = result["action"]
    assert action and action["top"] >= -1, result
    assert action["bottom"] <= viewport_height + 1, result
    return result


def assert_reservation_layout(client: CdpClient, viewport_height: int, label: str) -> dict:
    """Check the rank-invitation banner, cards, and confirm action at 720p."""

    result = assert_action_screen_layout(
        client,
        viewport_height,
        label,
        expected_phase="RESERVATION",
        screen_selector=".reservation-screen",
        action_selector='.reservation-screen [data-action="confirm-reservation"]',
    )
    details = client.evaluate(
        """
        (() => {
          const metric = element => {
            const rect = element.getBoundingClientRect();
            return {
              top: Math.round(rect.top),
              bottom: Math.round(rect.bottom),
              clientWidth: element.clientWidth,
              clientHeight: element.clientHeight,
              scrollWidth: element.scrollWidth,
              scrollHeight: element.scrollHeight,
            };
          };
          const grid = document.querySelector('.reservation-grid');
          const actionBar = document.querySelector('.reservation-screen > .action-bar');
          const banner = document.querySelector('.showcase-guarantee-banner, .showcase-invite-banner');
          return {
            grid: grid ? metric(grid) : null,
            actionBar: actionBar ? metric(actionBar) : null,
            banner: banner ? metric(banner) : null,
            cards: [...document.querySelectorAll('.reservation-card')].map(metric),
          };
        })()
        """
    )
    assert details["grid"] and details["actionBar"] and details["cards"], (label, details)
    assert details["grid"]["bottom"] <= details["actionBar"]["top"] + 1, (label, details)
    assert details["grid"]["scrollWidth"] <= details["grid"]["clientWidth"] + 1, (label, details)
    if details["banner"]:
        assert details["banner"]["scrollWidth"] <= details["banner"]["clientWidth"] + 1, (label, details)
    for card in details["cards"]:
        # The rotated decision stamp intentionally extends past the card edge
        # and is clipped by overflow:hidden; only vertical content must fit.
        assert card["scrollHeight"] <= card["clientHeight"] + 1, (label, card)
    result.update(details)
    return result


def assert_capacity_contract(
    client: CdpClient,
    label: str,
    *,
    expected_service_limit: int,
) -> dict:
    """Cross-check booking growth, physical rooms, and stayover subtraction."""

    result = client.evaluate(
        """
        (() => {
          const controller = window.__vesperaController;
          const metrics = controller.roomCapacitySummary();
          const unlocked = [...metrics.board.unlockedRooms];
          const blocked = [...metrics.board.blockedRooms];
          const usable = unlocked.filter(id => !metrics.board.blockedRooms.has(id));
          const stayoverRooms = [...new Set(
            Object.values(controller.state.stayovers).map(entry => entry.roomId),
          )].filter(id => usable.includes(id));
          const stayoverGuestIds = Object.keys(controller.state.stayovers);
          const starting = controller.data.rooms.filter(room => room.built_from_start !== false).length;
          const base = controller.currentScenario?.capacity
            ?? controller.data.balance?.base_booking_capacity
            ?? starting;
          const increase = controller.data.balance?.booking_capacity_per_expansion_room ?? 1;
          const expectedServiceLimit = base + (unlocked.length - starting) * increase;
          const summary = controller.state.phase === 'RESERVATION'
            ? controller.reservationSummary()
            : null;
          return {
            phase: controller.state.phase,
            currentNight: controller.currentNightNumber,
            currentServiceLimit: controller.currentServiceLimit,
            startingRoomCount: starting,
            builtRoomCount: metrics.builtRoomCount,
            addedRoomCount: metrics.addedRoomCount,
            serviceLimit: metrics.serviceLimit,
            expectedServiceLimit,
            physicalPlacementLimit: metrics.physicalPlacementLimit,
            expectedPhysicalPlacementLimit: usable.length,
            openRoomCount: metrics.openRoomCount,
            expectedOpenRoomCount: usable.length - stayoverRooms.length,
            stayoverRoomIds: metrics.stayoverRoomIds,
            expectedStayoverRoomIds: stayoverRooms,
            stayoverGuestIds,
            blockedRoomIds: blocked,
            summary,
          };
        })()
        """
    )
    result["label"] = label
    assert result["serviceLimit"] == expected_service_limit, result
    assert result["currentServiceLimit"] == expected_service_limit, result
    assert result["serviceLimit"] == result["expectedServiceLimit"], result
    assert result["builtRoomCount"] == result["startingRoomCount"] + result["addedRoomCount"], result
    assert result["physicalPlacementLimit"] == result["expectedPhysicalPlacementLimit"], result
    assert result["openRoomCount"] == result["expectedOpenRoomCount"], result
    assert sorted(result["stayoverRoomIds"]) == sorted(result["expectedStayoverRoomIds"]), result
    if result["summary"] is not None:
        summary = result["summary"]
        assert summary["serviceLimit"] == result["serviceLimit"], result
        assert summary["physicalPlacementLimit"] == result["physicalPlacementLimit"], result
        assert summary["builtRoomCount"] == result["builtRoomCount"], result
        assert summary["openRoomCount"] == result["openRoomCount"], result
        assert summary["stayoverRoomCount"] == len(result["stayoverRoomIds"]), result
        assert summary["placementMargin"] == result["physicalPlacementLimit"] - len(summary["accepted"]), result
        assert len(summary["accepted"]) == len(set(summary["accepted"])), result
        for guest_id in result["stayoverGuestIds"]:
            assert summary["accepted"].count(guest_id) == 1, result
    return result


def assert_reservation_board(
    client: CdpClient,
    viewport_height: int,
    label: str,
    *,
    require_states: tuple[str, ...],
    force_unavailable: bool = False,
) -> dict:
    """Open the room ledger and compare every DOM state with controller data."""

    forced_snapshot = None
    if force_unavailable:
        forced_snapshot = client.evaluate(
            """
            (async () => {
              const controller = window.__vesperaController;
              const capacity = controller.roomCapacitySummary();
              const stayoverRooms = new Set(capacity.stayoverRoomIds);
              const roomId = capacity.usableRoomIds.find(id => !stayoverRooms.has(id));
              if (!roomId) return null;
              const condition = { ...controller.state.roomConditions[roomId] };
              controller.state.roomConditions[roomId] = { cleanliness: 0, durability: 0 };
              const { renderApp } = await import(new URL('./src/render.js', document.baseURI).href);
              renderApp(document.querySelector('#app'), controller);
              return { roomId, condition };
            })()
            """
        )
        assert forced_snapshot, (label, "Could not create an unavailable-room probe")
    client.click('[data-action="open-reservation-board"]')
    wait_for(client, "window.__vesperaController.state.reservationBoardOpen === true")
    placements_before_room_click = controller_state(client)["placements"]
    client.click('.reservation-board-panel article[data-room-id]')
    placements_after_room_click = controller_state(client)["placements"]
    assert placements_after_room_click == placements_before_room_click, (
        label,
        placements_before_room_click,
        placements_after_room_click,
    )
    result = client.evaluate(
        """
        (() => {
          const controller = window.__vesperaController;
          const metrics = controller.roomCapacitySummary();
          const stayoverByRoom = Object.fromEntries(
            Object.entries(controller.state.stayovers).map(([guestId, entry]) => [entry.roomId, guestId]),
          );
          const expected = Object.fromEntries(controller.data.rooms.map(room => {
            const built = metrics.board.unlockedRooms.has(room.id);
            const unavailable = built && metrics.board.blockedRooms.has(room.id);
            const state = !built
              ? 'unbuilt'
              : unavailable
                ? 'unavailable'
                : stayoverByRoom[room.id]
                  ? 'stayover'
                  : 'empty';
            return [room.id, state];
          }));
          const cards = [...document.querySelectorAll(
            '.reservation-board-panel [data-room-id][data-room-state]',
          )].map(element => ({
            roomId: element.dataset.roomId,
            state: element.dataset.roomState,
            text: element.innerText,
          }));
          const actual = Object.fromEntries(cards.map(card => [card.roomId, card.state]));
          const mismatches = Object.entries(expected)
            .filter(([roomId, state]) => actual[roomId] !== state)
            .map(([roomId, state]) => ({ roomId, expected: state, actual: actual[roomId] ?? null }));
          const counts = cards.reduce((result, card) => {
            result[card.state] = (result[card.state] ?? 0) + 1;
            return result;
          }, {});
          const panel = document.querySelector('.reservation-board-panel');
          const rect = panel.getBoundingClientRect();
          const elevatorRows = [...panel.querySelectorAll('.occupancy-floor')].map(row => {
            const elevator = row.querySelector('.elevator-landing.compact');
            const roomA = row.querySelector('.occupancy-room');
            const elevatorRect = elevator?.getBoundingClientRect();
            const roomRect = roomA?.getBoundingClientRect();
            return {
              elevatorPresent: Boolean(elevator),
              gap: elevatorRect && roomRect
                ? Math.round(roomRect.left - elevatorRect.right)
                : null,
            };
          });
          return {
            documentScrollHeight: document.documentElement.scrollHeight,
            scrollY: Math.round(scrollY),
            panel: {
              top: Math.round(rect.top),
              bottom: Math.round(rect.bottom),
              clientHeight: panel.clientHeight,
              scrollHeight: panel.scrollHeight,
            },
            cardCount: cards.length,
            uniqueRoomCount: new Set(cards.map(card => card.roomId)).size,
            expectedRoomCount: controller.data.rooms.length,
            mismatches,
            counts,
            elevatorRows,
          };
        })()
        """
    )
    result["label"] = label
    result["placementsUnchangedAfterRoomClick"] = True
    assert result["documentScrollHeight"] <= viewport_height + 1, result
    assert abs(result["scrollY"]) <= 1, result
    assert result["panel"]["top"] >= 0 and result["panel"]["bottom"] <= viewport_height, result
    assert result["cardCount"] == result["expectedRoomCount"], result
    assert result["uniqueRoomCount"] == result["expectedRoomCount"], result
    assert result["mismatches"] == [], result
    assert len(result["elevatorRows"]) == 3, result
    assert all(row["elevatorPresent"] for row in result["elevatorRows"]), result
    assert all(0 <= row["gap"] <= 10 for row in result["elevatorRows"]), result
    for state in require_states:
        assert result["counts"].get(state, 0) > 0, (state, result)
    client.click('[data-action="close-reservation-board"]')
    wait_for(client, "window.__vesperaController.state.reservationBoardOpen === false")
    if forced_snapshot:
        client.evaluate(
            f"""
            (async () => {{
              const controller = window.__vesperaController;
              controller.state.roomConditions[{json.dumps(forced_snapshot['roomId'])}] =
                {json.dumps(forced_snapshot['condition'])};
              const {{ renderApp }} = await import(new URL('./src/render.js', document.baseURI).href);
              renderApp(document.querySelector('#app'), controller);
              return true;
            }})()
            """
        )
        result["forcedUnavailableRoomId"] = forced_snapshot["roomId"]
    return result


def run(
    url: str,
    port: int,
    screenshot: Path,
    facility_id: str,
    width: int,
    height: int,
    seed: int = DEMO_SEED,
    capture_dir: Path | None = None,
    prefix: str = "",
    targets_json: Path | None = None,
):
    del facility_id  # legacy positional argument; upgrades are now generated and cumulative
    target = debugger_target(port)
    client = CdpClient(target["webSocketDebuggerUrl"])
    capture_dir = (capture_dir or screenshot.parent).resolve()
    target_log: dict[str, list[dict]] = {}
    purchased: list[str] = []
    reservation_routes: dict[str, dict] = {}
    placement_layouts: list[dict] = []
    reservation_layouts: list[dict] = []
    result_layouts: list[dict] = []
    capacity_audits: list[dict] = []
    reservation_board_audits: list[dict] = []
    preopening_copy_audits: list[dict] = []

    def frame(name: str, scroll_target: str | None = None) -> None:
        assert_preopening_copy(client)
        capture_frame(client, capture_dir / f"{prefix}{name}", target_log, scroll_target)

    try:
        client.command("Runtime.enable")
        client.command("Page.enable")
        client.command("Log.enable")
        client.command("Network.enable")
        client.command("Network.setCacheDisabled", {"cacheDisabled": True})
        client.command(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
        )
        # CDP may treat a navigation to the already-open seeded URL as a no-op.
        # Reset first so repeated smoke runs never inherit an interrupted game.
        client.command("Page.navigate", {"url": f"{seeded_url(url, seed)}&test_reset=bootstrap"})
        wait_for(client, "document.readyState !== 'loading'")
        client.command("Page.navigate", {"url": seeded_url(url, seed)})
        wait_for(client, "document.readyState !== 'loading'")
        wait_for(client, "Boolean(window.__vesperaController)", timeout=45.0)
        # Profile knowledge is intentionally persistent in the game, but the
        # deterministic smoke run must begin from an undiscovered handbook.
        client.evaluate("localStorage.clear(); true")
        client.command("Page.navigate", {"url": f"{seeded_url(url, seed)}&test_reset=storage"})
        wait_for(client, "document.readyState !== 'loading'")
        client.command("Page.navigate", {"url": seeded_url(url, seed)})
        wait_for(client, "document.readyState !== 'loading'")
        wait_for(client, "Boolean(window.__vesperaController)", timeout=45.0)
        preopening_copy_audits.append({
            "screen": "title",
            **assert_preopening_copy(
                client,
                "개장 전 초청 영업에",
                "PRE-OPENING INVITATIONAL",
            ),
        })
        frame("title.png")

        client.click('[data-action="open-handbook"]')
        client.click('[data-action="handbook-tab"][data-tab="rank"]')
        require_text(client, "N·R·SR·SSR")
        preopening_copy_audits.append({
            "screen": "handbook",
            **assert_preopening_copy(client, "초청 영업"),
        })
        frame("handbook-ranks.png")
        client.click('[data-action="close-handbook"]')

        client.click('[data-action="start"]')
        tutorial_state = controller_state(client)
        assert tutorial_state["phase"] == "TUTORIAL"
        assert tutorial_state["serviceTimerMs"] is None
        placement_layouts.append(assert_placement_layout(client, height, "tutorial-waiting"))
        tutorial_plan = auto_assign(client)
        placement_layouts.append(assert_placement_layout(client, height, "tutorial-assigned"))
        frame("tutorial.png")
        client.click('[data-action="finish-night"]')

        # Night 1 has no reservation screen.
        state = controller_state(client)
        assert state["phase"] == "PLACEMENT" and state["currentNightIndex"] == 0
        assert 118_000 <= state["serviceTimerMs"] <= 120_000
        capacity_audits.append(assert_capacity_contract(
            client,
            "night1",
            expected_service_limit=5,
        ))
        placement_layouts.append(assert_placement_layout(client, height, "night1-waiting"))
        auto_assign(client)
        placement_layouts.append(assert_placement_layout(client, height, "night1-assigned"))
        frame("night1.png")
        client.click('[data-action="finish-night"]')
        wait_for(client, "window.__vesperaController.state.phase === 'RESULT'")
        no_maximum_reveal(client)
        result_layouts.append(assert_action_screen_layout(
            client,
            height,
            "result1",
            expected_phase="RESULT",
            screen_selector=".result-screen",
            action_selector='.result-screen [data-action="continue-result"]',
        ))
        preopening_copy_audits.append({
            "screen": "result",
            **assert_preopening_copy(client, "PRE-OPENING NIGHT 1 COMPLETE"),
        })
        frame("result1.png", "night-result")

        client.click('[data-action="continue-result"]')
        wait_for(client, "window.__vesperaController.state.phase === 'UPGRADE'")
        frame("upgrade-r.png", "upgrade-offers")
        first_upgrade = choose_upgrade(client, prefer_expansion=True)
        purchased.extend(first_upgrade["chosenIds"])

        # Night 2 reservations and placement.
        wait_for(client, "window.__vesperaController.state.phase === 'RESERVATION'")
        capacity_audits.append(assert_capacity_contract(
            client,
            "night2",
            expected_service_limit=6,
        ))
        reservation_board_audits.append(assert_reservation_board(
            client,
            height,
            "night2",
            require_states=("unbuilt", "empty"),
        ))
        route = choose_reservations(client, "balanced")
        reservation_routes["night2"] = route
        reservation_layouts.append(assert_reservation_layout(client, height, "night2"))
        preopening_copy_audits.append({
            "screen": "reservation",
            **assert_preopening_copy(client, "PRE-OPENING NIGHT 2 OF 5"),
        })
        frame("reservation2.png", "reservation-rank-odds")
        client.click('[data-action="confirm-reservation"]')
        assert controller_state(client)["serviceTimerMs"] is not None
        placement_layouts.append(assert_placement_layout(client, height, "night2-waiting"))
        auto_assign(client)
        placement_layouts.append(assert_placement_layout(client, height, "night2-assigned"))
        client.click('[data-action="finish-night"]')
        wait_for(client, "window.__vesperaController.state.phase === 'RESULT'")

        # Upgrade into Night 3; this seed normally exposes the first expansion.
        client.click('[data-action="continue-result"]')
        wait_for(client, "window.__vesperaController.state.phase === 'UPGRADE'")
        if any(
            upgrade_id.startswith("EXPAND_")
            for upgrade_id in controller_state(client)["currentUpgradeOfferIds"]
        ):
            frame("upgrade-expansion.png", "upgrade-offers")
        second_upgrade = choose_upgrade(client, prefer_expansion=True)
        purchased.extend(second_upgrade["chosenIds"])

        # Night 3 favors an R+ guest when the feasible subset permits it.
        capacity_audits.append(assert_capacity_contract(
            client,
            "night3",
            expected_service_limit=7,
        ))
        reservation_board_audits.append(assert_reservation_board(
            client,
            height,
            "night3",
            require_states=("unbuilt", "empty"),
        ))
        route = choose_reservations(client, "hidden")
        reservation_routes["night3"] = route
        reservation_layouts.append(assert_reservation_layout(client, height, "night3"))
        client.click('[data-action="confirm-reservation"]')
        placement_layouts.append(assert_placement_layout(client, height, "night3-waiting"))
        auto_assign(client)
        placement_layouts.append(assert_placement_layout(client, height, "night3-assigned"))
        client.click('[data-action="finish-night"]')
        wait_for(client, "window.__vesperaController.state.phase === 'RESULT'")
        night3 = controller_state(client)
        assert any(
            item.get("source") == "revisit"
            for score in night3["nightResults"][2]["guestScores"].values()
            for item in score["items"]
        ), "Night 3 should exercise the returning-guest bonus"
        result_layouts.append(assert_action_screen_layout(
            client,
            height,
            "result3-discovery",
            expected_phase="RESULT",
            screen_selector=".result-screen",
            action_selector='.result-screen [data-action="continue-result"]',
        ))
        frame("result3-discovery.png", "hidden-preference-discovery")

        client.click('[data-action="continue-result"]')
        wait_for(client, "window.__vesperaController.state.phase === 'UPGRADE'")
        # Prefer the second-floor expansion and always refresh the expansion frame here.
        if any(
            upgrade_id.startswith("EXPAND_")
            for upgrade_id in controller_state(client)["currentUpgradeOfferIds"]
        ):
            frame("upgrade-expansion.png", "upgrade-offers")
        third_upgrade = choose_upgrade(client, prefer_expansion=True)
        purchased.extend(third_upgrade["chosenIds"])

        # Night 4 keeps the Night 3 stayover locked and favors a same-species group.
        night4_start = controller_state(client)
        assert night4_start["phase"] == "RESERVATION"
        assert night4_start["lockedGuestIds"], "Night 4 should carry a locked two-night guest"
        locked_id = night4_start["lockedGuestIds"][0]
        locked_room = night4_start["placements"][locked_id]
        capacity_audits.append(assert_capacity_contract(
            client,
            "night4",
            expected_service_limit=8,
        ))
        reservation_board_audits.append(assert_reservation_board(
            client,
            height,
            "night4",
            require_states=("stayover", "unavailable", "empty"),
            force_unavailable=True,
        ))
        route = choose_reservations(client, "synergy")
        reservation_routes["night4"] = route
        reservation_layouts.append(assert_reservation_layout(client, height, "night4"))
        client.click('[data-action="confirm-reservation"]')
        placement_layouts.append(assert_placement_layout(client, height, "night4-waiting"))
        plan = auto_assign(client)
        placement_layouts.append(assert_placement_layout(client, height, "night4-assigned"))
        after_assignment = controller_state(client)
        assert after_assignment["placements"][locked_id] == locked_room
        assert any(effect["type"] == "synergy" for effect in plan["groupEffects"]), (
            "The default video route must display a species synergy",
            route,
            plan,
        )
        frame("night4-synergy.png", "species-effects")
        client.click('[data-action="finish-night"]')

        client.click('[data-action="continue-result"]')
        wait_for(client, "window.__vesperaController.state.phase === 'UPGRADE'")
        fourth_upgrade = choose_upgrade(client, prefer_expansion=True)
        purchased.extend(fourth_upgrade["chosenIds"])

        # Night 5 must visibly include the showcase-only SSR invitation.
        wait_for(client, "window.__vesperaController.state.phase === 'RESERVATION'")
        capacity_audits.append(assert_capacity_contract(
            client,
            "night5",
            expected_service_limit=8,
        ))
        reservation_board_audits.append(assert_reservation_board(
            client,
            height,
            "night5",
            require_states=("empty",),
        ))
        require_text(client, "SSR 왕실 특별 초청")
        require_text(client, "최종 등급의 까다로운 요청과 높은 보상이 함께 도착했습니다")
        assert "영구 해금" not in client.body_text()
        route = choose_reservations(client, "ssr")
        reservation_routes["night5"] = route
        assert set(controller_state(client)["specialInviteGuestIds"]) & set(route["chosen"])
        reservation_layouts.append(assert_reservation_layout(client, height, "night5"))
        frame("reservation5-ssr.png", "ssr-invite")
        client.click('[data-action="confirm-reservation"]')
        placement_layouts.append(assert_placement_layout(client, height, "night5-waiting"))
        auto_assign(client)
        placement_layouts.append(assert_placement_layout(client, height, "night5-assigned"))
        frame("night5.png", "hotel-board")
        client.click('[data-action="finish-night"]')
        client.click('[data-action="continue-result"]')
        wait_for(client, "window.__vesperaController.state.phase === 'FINAL'")
        preopening_copy_audits.append({
            "screen": "final",
            **assert_preopening_copy(
                client,
                "PRE-OPENING INVITATIONAL COMPLETE",
                "개장 전 다섯 영업",
            ),
        })
        require_text(client, "수용과 배치, 공사 계약으로 달라진 호텔의 운영 기록입니다")
        assert "영구 해금" not in client.body_text()
        no_maximum_reveal(client)
        result_layouts.append(assert_action_screen_layout(
            client,
            height,
            "final",
            expected_phase="FINAL",
            screen_selector=".final-screen",
            action_selector='.final-screen [data-action="restart"]',
        ))
        frame("final.png", "showcase-final")

        final_state = controller_state(client)
        assert len(final_state["nightResults"]) == 5
        assert final_state["phase"] == "FINAL"
        assert final_state["runSeed"] == seed
        assert final_state["runRecord"]["ending_id"] == "PREOPENING_COMPLETE"
        assert final_state["runRecord"]["outcome"] == "COMPLETE"
        assert final_state["runRecord"]["metrics"]["completed_nights"] == 5
        assert final_state["recordArchiveCount"] >= 1
        assert final_state["discoveredHiddenPreferenceIds"], (
            "The complete seeded route should reveal at least one species x rank preference"
        )
        require_text(client, "ENDING · PREOPENING_COMPLETE")
        require_text(client, "기록 ID")

        # Preserve the old --screenshot contract as a final-frame copy.
        final_source = capture_dir / f"{prefix}final.png"
        if screenshot.resolve() != final_source.resolve():
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            screenshot.write_bytes(final_source.read_bytes())

        if targets_json:
            targets_json.parent.mkdir(parents=True, exist_ok=True)
            targets_json.write_text(
                json.dumps(
                    {
                        "seed": seed,
                        "viewport": {"width": width, "height": height},
                        "frames": target_log,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

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

        return {
            "status": "PASS",
            "seed": seed,
            "viewport": f"{width}x{height}",
            "nights_completed": len(final_state["nightResults"]),
            "owned_upgrades": final_state["ownedUpgradeIds"],
            "expansions": [value for value in final_state["ownedUpgradeIds"] if value.startswith("EXPAND_")],
            "seen_ranks": final_state["seenRankIds"],
            "seen_species": final_state["seenSpeciesIds"],
            "hidden_discoveries": final_state["discoveredHiddenPreferenceIds"],
            "purchased_route": purchased,
            "reservations": reservation_routes,
            "tutorial_assignment": tutorial_plan["placements"],
            "placement_layouts": [
                {
                    "label": item["label"],
                    "document_scroll_height": item["documentScrollHeight"],
                    "action_bottom": item["actionBar"]["bottom"],
                    "board_overflow": max(
                        0,
                        item["boardPanel"]["scrollHeight"] - item["boardPanel"]["clientHeight"],
                    ),
                    "waiting_overflow": max(
                        0,
                        item["waitingGuests"]["scrollHeight"] - item["waitingGuests"]["clientHeight"],
                    ),
                    "detail_scrollable": item["detail"]["scrollHeight"] > item["detail"]["clientHeight"],
                }
                for item in placement_layouts
            ],
            "reservation_layouts": [
                {
                    "label": item["label"],
                    "document_scroll_height": item["documentScrollHeight"],
                    "action_bottom": item["actionBar"]["bottom"],
                    "banner_present": item["banner"] is not None,
                }
                for item in reservation_layouts
            ],
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
            "reservation_board_audits": [
                {
                    "label": item["label"],
                    "room_states": item["counts"],
                    "forced_unavailable_room": item.get("forcedUnavailableRoomId"),
                    "room_click_read_only": item["placementsUnchangedAfterRoomClick"],
                    "panel_bottom": item["panel"]["bottom"],
                    "document_scroll_height": item["documentScrollHeight"],
                }
                for item in reservation_board_audits
            ],
            "preopening_copy_audits": preopening_copy_audits,
            "result_layouts": [
                {
                    "label": item["label"],
                    "document_scroll_height": item["documentScrollHeight"],
                    "action_bottom": item["action"]["bottom"],
                }
                for item in result_layouts
            ],
            "frames": [f"{prefix}{name}" for name in VIDEO_FRAME_NAMES],
            "targets_json": str(targets_json) if targets_json else None,
            "screenshot": str(screenshot),
        }
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--debug-port", type=int, default=9223)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--seed", type=int, default=DEMO_SEED)
    parser.add_argument(
        "--facility",
        choices=sorted(ROUTES),
        default="SECRET_PASSAGE",
        help="Legacy compatibility option; the showcase now buys seeded cumulative upgrades.",
    )
    parser.add_argument(
        "--screenshot",
        type=Path,
        default=ROOT / "artifacts" / "showcase-final.png",
    )
    parser.add_argument(
        "--capture-dir",
        type=Path,
        default=ROOT / "artifacts",
        help="Directory for the complete named five-night frame set.",
    )
    parser.add_argument(
        "--prefix",
        default=None,
        help="Filename prefix. Defaults to showcase- at 1280, or showcase-WIDTH- otherwise.",
    )
    parser.add_argument(
        "--video-assets",
        action="store_true",
        help="Write the exact unprefixed 1280x720 frame names to submission_video/assets.",
    )
    parser.add_argument("--targets-json", type=Path)
    args = parser.parse_args()

    if args.video_assets:
        if (args.width, args.height) != (1280, 720):
            parser.error("--video-assets requires --width 1280 --height 720")
        capture_dir = ROOT / "submission_video" / "assets"
        prefix = ""
        targets_json = args.targets_json or ROOT / "submission_video" / "box_audit" / "targets.json"
    else:
        capture_dir = args.capture_dir
        prefix = args.prefix if args.prefix is not None else (
            "showcase-" if args.width == 1280 else f"showcase-{args.width}-"
        )
        targets_json = args.targets_json

    print(
        json.dumps(
            run(
                args.url,
                args.debug_port,
                args.screenshot,
                args.facility,
                args.width,
                args.height,
                seed=args.seed,
                capture_dir=capture_dir,
                prefix=prefix,
                targets_json=targets_json,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
