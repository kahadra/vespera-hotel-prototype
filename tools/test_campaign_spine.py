from __future__ import annotations

import argparse
import json
import urllib.parse

from smoke_browser import CdpClient, debugger_target, wait_for


def campaign_url(base_url: str, seed: int) -> str:
    parsed = urllib.parse.urlparse(base_url)
    query = urllib.parse.parse_qs(parsed.query)
    query["mode"] = ["campaign"]
    query["seed"] = [str(seed)]
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query, doseq=True)))


def state(client: CdpClient):
    return client.evaluate("JSON.parse(JSON.stringify(window.__vesperaController.state))")


def render_live(client: CdpClient):
    return client.evaluate(
        "import('./src/render.js').then(({renderApp}) => { renderApp(document.querySelector('#app'), window.__vesperaController); return true; })"
    )


def action_layout(client: CdpClient, selector: str):
    encoded = json.dumps(selector)
    return client.evaluate(
        f"""
        (() => {{
          const action = document.querySelector({encoded});
          const rect = action?.getBoundingClientRect();
          return {{
            document_scroll_height: document.documentElement.scrollHeight,
            action_bottom: rect ? Math.round(rect.bottom) : null,
            viewport_height: innerHeight,
          }};
        }})()
        """
    )


def synthetic_result(day: int, income: int, reputation: int):
    return {
        "valid": True,
        "placementScore": 0,
        "reputationDelta": reputation,
        "baseFees": income,
        "tips": 0,
        "income": income,
        "grade": "GREYBOX",
        "acceptedGuestIds": ["G01_LUNE"],
        "rejectedGuestIds": [],
        "canceledGuestIds": [],
        "placements": {},
        "guestScores": {},
        "guestReviews": [],
        "emergencyReport": None,
        "testDay": day,
    }


def run(base_url: str, debug_port: int, seed: int):
    target = debugger_target(debug_port)
    client = CdpClient(target["webSocketDebuggerUrl"])
    url = campaign_url(base_url, seed)
    chapter_story_ids: list[str] = []
    try:
        client.command("Runtime.enable")
        client.command("Page.enable")
        client.command(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1280, "height": 720, "deviceScaleFactor": 1, "mobile": False},
        )
        client.command("Page.navigate", {"url": "about:blank"})
        wait_for(client, "document.readyState === 'complete'")
        client.command("Page.navigate", {"url": url})
        wait_for(client, "Boolean(window.__vesperaController)")
        client.evaluate("localStorage.clear()")
        client.command("Page.navigate", {"url": url})
        wait_for(client, "Boolean(window.__vesperaController)")

        initial = state(client)
        assert initial["phase"] == "TITLE", initial
        assert client.evaluate("window.__vesperaController.data.prototype_mode.type") == "CAMPAIGN"
        assert "상속 유지 조건" in client.body_text()

        client.click('[data-action="start"]')
        new_game = state(client)
        assert new_game["phase"] == "NEW_GAME", new_game
        assert "새 인간 지배인과 호텔의 표현" in client.body_text()
        new_game_layout = action_layout(client, '[data-action="confirm-new-game"]')
        assert new_game_layout["document_scroll_height"] <= 720, new_game_layout
        assert new_game_layout["action_bottom"] <= 720, new_game_layout

        client.click('[data-action="set-greybox-ending-route"][data-route-id="TRUE_VAMPIRE"]')
        assert state(client)["greyboxEndingRouteId"] == "TRUE_VAMPIRE"
        client.click('[data-action="set-greybox-ending-route"][data-route-id="NORMAL"]')
        assert state(client)["greyboxEndingRouteId"] == "NORMAL"
        client.click('[data-action="set-player-gender"][data-gender-id="FEMALE"]')
        client.click('[data-action="set-secretary-presentation"][data-presentation-id="MALE"]')
        client.click('[data-action="set-relationship-preset"][data-preset-id="PER_ROLE"]')
        client.click('[data-action="set-relationship-role"][data-role-id="RELATIONSHIP_VAMPIRE"][data-presentation-id="MALE"]')
        client.click('[data-action="confirm-new-game"]')
        prologue = state(client)
        assert prologue["phase"] == "STORY", prologue
        assert prologue["storyNodeId"] == "CAMPAIGN_PROLOGUE", prologue
        assert "베스페라의 새 인간 지배인" in client.body_text()
        story_layout = action_layout(client, '[data-action="continue-story"]')
        assert story_layout["document_scroll_height"] <= 720, story_layout
        assert story_layout["action_bottom"] <= 720, story_layout

        mode_isolation_before_reload = client.evaluate(
            "({ campaign: Boolean(localStorage.getItem('vespera.hotel.active-run.v2.campaign')), showcase: Boolean(localStorage.getItem('vespera.hotel.active-run.v2.showcase')) })"
        )
        assert mode_isolation_before_reload == {"campaign": True, "showcase": False}, mode_isolation_before_reload

        client.command("Page.navigate", {"url": "about:blank"})
        wait_for(client, "document.readyState === 'complete'")
        client.command("Page.navigate", {"url": url})
        wait_for(client, "Boolean(window.__vesperaController)")
        assert state(client)["phase"] == "TITLE"
        assert client.evaluate("window.__vesperaController.hasCheckpoint()") is True
        client.click('[data-action="resume"]')
        resumed = state(client)
        assert resumed["phase"] == "STORY", resumed
        assert resumed["playerGenderId"] == "FEMALE", resumed
        assert resumed["secretaryPresentationId"] == "MALE", resumed
        assert resumed["relationshipPresentationIds"]["RELATIONSHIP_VAMPIRE"] == "MALE", resumed
        assert resumed["relationshipPresentationIds"]["RELATIONSHIP_WITCH"] == "FEMALE", resumed

        client.click('[data-action="continue-story"]')
        relic_offer = state(client)
        assert relic_offer["phase"] == "RELIC_OFFER", relic_offer
        assert len(relic_offer["pendingDisplayRelicOffer"]["relicIds"]) == 3, relic_offer
        first_relic_offer_ids = relic_offer["pendingDisplayRelicOffer"]["relicIds"]
        assert "DISPLAY_RELIC_UNBLEMISHED_LEDGER" in first_relic_offer_ids, first_relic_offer_ids

        client.command("Page.navigate", {"url": "about:blank"})
        wait_for(client, "document.readyState === 'complete'")
        client.command("Page.navigate", {"url": url})
        wait_for(client, "Boolean(window.__vesperaController)")
        client.click('[data-action="resume"]')
        reloaded_relic_offer = state(client)
        assert reloaded_relic_offer["phase"] == "RELIC_OFFER", reloaded_relic_offer
        assert reloaded_relic_offer["pendingDisplayRelicOffer"]["relicIds"] == first_relic_offer_ids
        relic_offer_layout = action_layout(client, '[data-action="select-display-relic"]')
        assert relic_offer_layout["document_scroll_height"] <= 720, relic_offer_layout
        assert relic_offer_layout["action_bottom"] <= 720, relic_offer_layout
        client.click('[data-action="select-display-relic"][data-relic-id="DISPLAY_RELIC_UNBLEMISHED_LEDGER"]')
        assert state(client)["phase"] == "DAY_OPENING"
        assert state(client)["ownedDisplayRelicIds"] == ["DISPLAY_RELIC_UNBLEMISHED_LEDGER"]
        client.click('[data-action="open-handbook"]')
        client.click('[data-action="handbook-tab"][data-tab="relics"]')
        assert "전시품 도감" in client.body_text()
        assert "무흠 장부" in client.body_text()
        assert "이번 캠페인 보유" in client.body_text()
        client.click('[data-action="close-handbook"]')

        for day in range(1, 6):
            client.click('[data-action="start-day-business"]')
            assert state(client)["phase"] in {"RESERVATION", "PLACEMENT"}
            result = synthetic_result(day, income=20, reputation=1)
            client.evaluate(
                f"window.__vesperaController.completeNight({json.dumps(result, ensure_ascii=False)})"
            )
            render_live(client)
            assert state(client)["phase"] == "RESULT"
            client.click('[data-action="open-result-review"]')
            assert state(client)["phase"] == "RESULT_REVIEW"
            if day == 5:
                client.evaluate(
                    "window.__vesperaController.state.discoveredHiddenPreferenceIds.push('VAMPIRE:R:QUIET')"
                )
            client.click('[data-action="accept-secretary-report"]')
            current = state(client)
            if day in {2, 4}:
                assert current["phase"] == "STORY", current
                chapter_story_ids.append(current["storyNodeId"])
                client.click('[data-action="continue-story"]')
                current = state(client)
            if day < 5:
                assert current["phase"] == "UPGRADE", current
                client.click('[data-action="finish-upgrade"]')
                assert state(client)["phase"] == "DAY_OPENING"

        final = state(client)
        assert final["phase"] == "FINAL", final
        assert final["runRecord"]["outcome"] == "COMPLETE", final["runRecord"]
        assert final["runRecord"]["ending_id"] == "NORMAL_STEWARDSHIP", final["runRecord"]
        assert final["runRecord"]["ending_tier"] == "NORMAL", final["runRecord"]
        assert final["runRecord"]["schema_version"] == 6, final["runRecord"]
        assert final["runRecord"]["player_gender_id"] == "FEMALE", final["runRecord"]
        assert len(final["runRecord"]["relationship_epilogues"]) == 2, final["runRecord"]
        assert "베스페라의 평범한 인간 지배인" in client.body_text()
        final_layout = action_layout(client, '[data-action="restart"]')
        assert final_layout["document_scroll_height"] <= 720, final_layout
        assert final_layout["action_bottom"] <= 720, final_layout
        profile_after_success = client.evaluate(
            "JSON.parse(localStorage.getItem('vespera.hotel.profile.v1'))"
        )
        assert profile_after_success["schema_version"] == 1, profile_after_success
        assert "VAMPIRE:R:QUIET" in profile_after_success["handbook"]["discovered_hidden_preference_ids"]
        assert "DISPLAY_RELIC_UNBLEMISHED_LEDGER" in profile_after_success["display_relics"]["triggered_ids"]
        assert client.evaluate("Boolean(localStorage.getItem('vespera.hotel.active-run.v2.campaign'))") is False

        contracts = client.evaluate(
            """
            (async () => {
              const [{ GameController }, saveModule] = await Promise.all([
                import('./src/state.js'),
                import('./src/save.js'),
              ]);
              const campaignData = window.__vesperaController.data;
              const memoryStorage = () => {
                const values = new Map();
                return {
                  getItem: key => values.has(key) ? values.get(key) : null,
                  setItem: (key, value) => values.set(key, value),
                  removeItem: key => values.delete(key),
                  keys: () => [...values.keys()],
                };
              };
              const failureStorage = memoryStorage();
              const failure = new GameController(campaignData, { seed: 777, storage: failureStorage });
              failure.start();
              failure.confirmNewGame();
              failure.continueStory();
              failure.selectDisplayRelic(failure.state.pendingDisplayRelicOffer.relicIds[0]);
              const fake = day => ({
                valid: true,
                placementScore: 0,
                reputationDelta: -1,
                baseFees: 0,
                tips: 0,
                income: 0,
                grade: 'GREYBOX',
                acceptedGuestIds: [],
                rejectedGuestIds: [],
                canceledGuestIds: [],
                placements: {},
                guestScores: {},
                guestReviews: [],
                emergencyReport: null,
                testDay: day,
              });
              for (let day = 1; day <= 5; day += 1) {
                failure.startDayBusiness();
                failure.completeNight(fake(day));
                failure.openResultReview();
                failure.acceptSecretaryReport();
                if (failure.state.phase === 'STORY') failure.continueStory();
                if (failure.state.phase === 'UPGRADE') failure.finishUpgrade();
              }

              const routeOutcomes = {};
              for (const routeId of [
                'BAD',
                'NORMAL',
                'SPECIES_VAMPIRE',
                'SPECIES_HEROINE_VAMPIRE',
                'TRUE_VAMPIRE',
                'TRUE_HAREM',
              ]) {
                const route = new GameController(campaignData, {
                  seed: 900 + Object.keys(routeOutcomes).length,
                  storage: memoryStorage(),
                });
                route.start();
                route.setGreyboxEndingRoute(routeId);
                route.state.nightResults = Array.from({ length: 5 }, (_, index) => ({
                  ...fake(index + 1),
                  income: 20,
                  reputationDelta: 1,
                }));
                route.state.gold = 100;
                route.state.hotelReputation = 5;
                route.completeRun();
                routeOutcomes[routeId] = {
                  endingId: route.state.runRecord?.ending_id,
                  endingTier: route.state.runRecord?.ending_tier,
                  epilogueCount: route.state.runRecord?.relationship_epilogues?.length ?? 0,
                  selectedRoleId: route.state.runRecord?.relationship_role_id ?? null,
                  managerOutcomeId: route.state.runRecord?.manager_outcome?.id ?? null,
                };
              }

              const dreamDemonOutcomes = {};
              for (const [label, affinities] of Object.entries({
                blocked: { DREAM_DEMON: 6, HUMAN: 3, VAMPIRE: 2 },
                unlocked: { DREAM_DEMON: 6, HUMAN: 3, VAMPIRE: 3 },
              })) {
                const dreamRoute = new GameController(campaignData, {
                  seed: 950 + Object.keys(dreamDemonOutcomes).length,
                  storage: memoryStorage(),
                });
                dreamRoute.start();
                dreamRoute.state.nightResults = Array.from({ length: 5 }, (_, index) => ({
                  ...fake(index + 1),
                  income: 20,
                  reputationDelta: 1,
                }));
                dreamRoute.state.gold = 100;
                dreamRoute.state.hotelReputation = 5;
                dreamRoute.state.speciesAffinityById = affinities;
                dreamRoute.state.speciesEndingTriggerIds = ['DREAM_DEMON'];
                dreamRoute.state.speciesEndingCommitmentId = 'DREAM_DEMON';
                dreamRoute.completeRun();
                dreamDemonOutcomes[label] = {
                  endingId: dreamRoute.state.runRecord?.ending_id,
                  otherSpeciesAllies: dreamRoute.state.runRecord?.metrics?.dream_demon_other_species_allies,
                  networkReady: dreamRoute.state.runRecord?.metrics?.dream_demon_other_species_network,
                  managerOutcomeId: dreamRoute.state.runRecord?.manager_outcome?.id ?? null,
                };
              }

              const showcaseData = {
                ...campaignData,
                campaign: undefined,
                prototype_mode: { ...campaignData.prototype_mode, type: 'SHOWCASE' },
              };
              const legacyStorage = memoryStorage();
              const legacySource = new GameController(showcaseData, { seed: 888, storage: legacyStorage });
              legacySource.start();
              const legacySave = saveModule.createRunSave(showcaseData, legacySource.state, null);
              legacySave.schema_version = 3;
              delete legacySave.profile_id;
              delete legacySave.state.profileId;
              legacyStorage.setItem(saveModule.ACTIVE_RUN_STORAGE_KEY, JSON.stringify(legacySave));
              const migrated = new GameController(showcaseData, { seed: 999, storage: legacyStorage });
              const legacyDetected = migrated.hasCheckpoint();
              const legacyResumed = migrated.resumeRun();

              const deterministicA = new GameController(campaignData, { seed: 1234, storage: memoryStorage() });
              deterministicA.start();
              deterministicA.confirmNewGame();
              deterministicA.continueStory();
              const deterministicB = new GameController(campaignData, { seed: 1234, storage: memoryStorage() });
              deterministicB.start();
              deterministicB.confirmNewGame();
              deterministicB.continueStory();
              const deterministicRelicOffer = JSON.stringify(deterministicA.state.pendingDisplayRelicOffer.relicIds)
                === JSON.stringify(deterministicB.state.pendingDisplayRelicOffer.relicIds);
              const skippedRelicOffer = deterministicB.skipDisplayRelicOffer();
              const skipReachedOpening = deterministicB.state.phase === 'DAY_OPENING'
                && deterministicB.state.ownedDisplayRelicIds.length === 0;

              const effects = new GameController(campaignData, { seed: 1235, storage: memoryStorage() });
              effects.start();
              effects.confirmNewGame();
              effects.continueStory();
              effects.selectDisplayRelic('DISPLAY_RELIC_DAWN_BELL');
              effects.state.phase = 'PLACEMENT';
              effects.state.serviceTimerMs = 120000;
              effects.chargeRelocation();
              const dawnBellTimer = effects.state.serviceTimerMs;
              const dawnBellTriggers = effects.state.displayRelicTriggerCounts.DISPLAY_RELIC_DAWN_BELL;

              effects.state.ownedDisplayRelicIds = ['DISPLAY_RELIC_SILVER_MAINTENANCE_KIT'];
              effects.state.phase = 'UPGRADE';
              effects.state.gold = 20;
              effects.state.roomConditions['F1-A'] = { cleanliness: 80 };
              const serviceCost = effects.roomServiceCost();
              const serviced = effects.serviceRoom('F1-A');
              const serviceGold = effects.state.gold;

              effects.state.ownedDisplayRelicIds = ['DISPLAY_RELIC_UNBLEMISHED_LEDGER'];
              effects.state.currentNightIndex = 0;
              effects.state.nightResults = [];
              effects.state.gold = 0;
              effects.completeNight({ ...fake(1), acceptedGuestIds: ['G01_LUNE'] });
              const ledgerIncome = effects.state.nightResults[0].income;
              const ledgerBonus = effects.state.nightResults[0].relicBonusGold;
              const relicSave = saveModule.createRunSave(campaignData, deterministicA.state, null);
              const relicSavePreserved = JSON.stringify(relicSave?.state?.pendingDisplayRelicOffer?.relicIds)
                === JSON.stringify(deterministicA.state.pendingDisplayRelicOffer.relicIds);

              const retryStorage = memoryStorage();
              const retryRelic = new GameController(campaignData, { seed: 1236, storage: retryStorage });
              retryRelic.start();
              retryRelic.confirmNewGame();
              retryRelic.continueStory();
              retryRelic.selectDisplayRelic('DISPLAY_RELIC_UNBLEMISHED_LEDGER');
              retryRelic.completeNight({ ...fake(1), acceptedGuestIds: ['G01_LUNE'] });
              retryRelic.saveCheckpoint();
              const retryProfileBefore = saveModule.readProfile(retryStorage);
              const retryTriggerNotCommitted = !retryProfileBefore.display_relics.triggered_ids
                .includes('DISPLAY_RELIC_UNBLEMISHED_LEDGER');
              const retryRestored = retryRelic.retryCurrentStage();
              const retryTriggerRolledBack = !retryRelic.state.displayRelicTriggerCounts
                .DISPLAY_RELIC_UNBLEMISHED_LEDGER;

              const recordFailureStorage = memoryStorage();
              const campaignSaveKey = 'vespera.hotel.active-run.v2.campaign';
              const recordKey = 'vespera.hotel.run-records.v1';
              const originalSetItem = recordFailureStorage.setItem;
              const recordFailure = new GameController(campaignData, {
                seed: 1237,
                storage: recordFailureStorage,
              });
              recordFailure.start();
              recordFailure.confirmNewGame();
              const recordFailureSave = recordFailure.saveCheckpoint();
              const activeSaveBeforeFailure = recordFailureStorage.getItem(campaignSaveKey);
              recordFailureStorage.setItem = (key, value) => {
                if (key === recordKey) throw new Error('injected record write failure');
                return originalSetItem(key, value);
              };
              let recordFailureCode = null;
              try {
                recordFailure.completeRun();
              } catch (error) {
                recordFailureCode = error.code ?? null;
              }
              const recordFailureReloaded = new GameController(campaignData, {
                seed: 9999,
                storage: recordFailureStorage,
              });
              const recordFailureCheckpointDetected = recordFailureReloaded.hasCheckpoint();
              const recordFailureResumed = recordFailureReloaded.resumeRun();

              return {
                failurePhase: failure.state.phase,
                failureOutcome: failure.state.runRecord?.outcome,
                failureEndingId: failure.state.runRecord?.ending_id,
                routeOutcomes,
                dreamDemonOutcomes,
                campaignKeyCleared: !failureStorage.getItem('vespera.hotel.active-run.v2.campaign'),
                profileStored: Boolean(failureStorage.getItem('vespera.hotel.profile.v1')),
                legacyDetected,
                legacyResumed,
                legacyPhase: migrated.state.phase,
                legacyProfileId: migrated.state.profileId,
                deterministicRelicOffer,
                skippedRelicOffer,
                skipReachedOpening,
                relicSavePhase: relicSave?.state?.phase,
                relicSavePreserved,
                dawnBellTimer,
                dawnBellTriggers,
                serviceCost,
                serviced,
                serviceGold,
                ledgerIncome,
                ledgerBonus,
                retryTriggerNotCommitted,
                retryRestored,
                retryTriggerRolledBack,
                recordFailureCode,
                recordFailureSaveCreated: Boolean(recordFailureSave),
                recordFailureActiveSavePreserved: recordFailureStorage.getItem(campaignSaveKey)
                  === activeSaveBeforeFailure,
                recordFailureArchiveCount: JSON.parse(recordFailureStorage.getItem(recordKey) ?? '[]').length,
                recordFailureRunRecordDeferred: recordFailure.state.runRecord === null,
                recordFailureCheckpointDetected,
                recordFailureResumed,
                recordFailureResumedPhase: recordFailureReloaded.state.phase,
                recordFailureResumedSeed: recordFailureReloaded.state.runSeed,
              };
            })()
            """
        )
        assert contracts == {
            "failurePhase": "FINAL",
            "failureOutcome": "FAILURE",
            "failureEndingId": "BAD_OPERATIONAL",
            "routeOutcomes": {
                "BAD": {"endingId": "BAD_CHAPTER_HURDLE", "endingTier": "BAD", "epilogueCount": 2, "selectedRoleId": None, "managerOutcomeId": None},
                "NORMAL": {"endingId": "NORMAL_STEWARDSHIP", "endingTier": "NORMAL", "epilogueCount": 2, "selectedRoleId": None, "managerOutcomeId": None},
                "SPECIES_VAMPIRE": {"endingId": "SPECIES_VAMPIRE", "endingTier": "SPECIES", "epilogueCount": 1, "selectedRoleId": None, "managerOutcomeId": "OPTIONAL_VAMPIRE_TRANSFORMATION"},
                "SPECIES_HEROINE_VAMPIRE": {"endingId": "SPECIES_HEROINE_VAMPIRE", "endingTier": "SPECIES_HEROINE", "epilogueCount": 1, "selectedRoleId": "RELATIONSHIP_VAMPIRE", "managerOutcomeId": "OPTIONAL_VAMPIRE_TRANSFORMATION"},
                "TRUE_VAMPIRE": {"endingId": "TRUE_PEACE", "endingTier": "TRUE", "epilogueCount": 5, "selectedRoleId": "RELATIONSHIP_VAMPIRE", "managerOutcomeId": None},
                "TRUE_HAREM": {"endingId": "TRUE_HAREM", "endingTier": "TRUE_HAREM", "epilogueCount": 5, "selectedRoleId": None, "managerOutcomeId": None},
            },
            "dreamDemonOutcomes": {
                "blocked": {"endingId": "NORMAL_STEWARDSHIP", "otherSpeciesAllies": 1, "networkReady": 0, "managerOutcomeId": None},
                "unlocked": {"endingId": "SPECIES_DREAM_DEMON", "otherSpeciesAllies": 2, "networkReady": 1, "managerOutcomeId": "OPTIONAL_DREAM_DEMON_REINCARNATION"},
            },
            "campaignKeyCleared": True,
            "profileStored": True,
            "legacyDetected": True,
            "legacyResumed": True,
            "legacyPhase": "TUTORIAL",
            "legacyProfileId": "default",
            "deterministicRelicOffer": True,
            "skippedRelicOffer": True,
            "skipReachedOpening": True,
            "relicSavePhase": "RELIC_OFFER",
            "relicSavePreserved": True,
            "dawnBellTimer": 117000,
            "dawnBellTriggers": 1,
            "serviceCost": 5,
            "serviced": True,
            "serviceGold": 15,
            "ledgerIncome": 3,
            "ledgerBonus": 3,
            "retryTriggerNotCommitted": True,
            "retryRestored": True,
            "retryTriggerRolledBack": True,
            "recordFailureCode": "RUN_RECORD_WRITE_FAILED",
            "recordFailureSaveCreated": True,
            "recordFailureActiveSavePreserved": True,
            "recordFailureArchiveCount": 0,
            "recordFailureRunRecordDeferred": True,
            "recordFailureCheckpointDetected": True,
            "recordFailureResumed": True,
            "recordFailureResumedPhase": "STORY",
            "recordFailureResumedSeed": 1237,
        }, contracts

        return {
            "status": "PASS",
            "mode": "CAMPAIGN",
            "seed": seed,
            "new_game": {
                "player_gender": resumed["playerGenderId"],
                "secretary_presentation": resumed["secretaryPresentationId"],
                "relationship_preset": resumed["relationshipGenderPreset"],
                "witch_locked_female": resumed["relationshipPresentationIds"]["RELATIONSHIP_WITCH"] == "FEMALE",
            },
            "resume_phase": resumed["phase"],
            "chapter_story_ids": chapter_story_ids,
            "success_ending": final["runRecord"]["ending_id"],
            "failure_ending": contracts["failureEndingId"],
            "ending_routes": contracts["routeOutcomes"],
            "dream_demon_network": contracts["dreamDemonOutcomes"],
            "profile_schema": profile_after_success["schema_version"],
            "run_record_schema": final["runRecord"]["schema_version"],
            "mode_save_isolation": mode_isolation_before_reload,
            "display_relic": {
                "offer_ids": first_relic_offer_ids,
                "owned_id": final["runRecord"]["owned_display_relic_ids"][0],
                "trigger_count": final["runRecord"]["display_relic_trigger_counts"]["DISPLAY_RELIC_UNBLEMISHED_LEDGER"],
            },
            "legacy_showcase_save_migrated": contracts["legacyResumed"],
            "layout_1280x720": {
                "new_game": new_game_layout,
                "story": story_layout,
                "relic_offer": relic_offer_layout,
                "final": final_layout,
            },
        }
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8767/index.html")
    parser.add_argument("--debug-port", type=int, default=9230)
    parser.add_argument("--seed", type=int, default=4242)
    args = parser.parse_args()
    print(json.dumps(run(args.url, args.debug_port, args.seed), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
