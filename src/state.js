import { calculateNightResult } from "./scoring.js";
import { createBoardState, evaluatePlacement } from "./rules.js";
import { createEmergencyPlan } from "./emergency.js";
import {
  calculateEndlessAudit,
  endlessAuditTarget,
  endlessRiskTier,
} from "./endless.js";
import { createRngState } from "./random.js";
import {
  displayRelicById,
  displayRelicEffectValue,
  generateDisplayRelicOffer,
} from "./relics.js";
import { generateGuestOffer, rankOddsFor } from "./progression.js";
import {
  canPurchaseUpgrade,
  generateUpgradeOffer,
  purchaseUpgrade,
  renovationRoomIds,
} from "./upgrades.js";
import { getGuestRules } from "./data.js";
import { createRunRecord, readRunRecords, storeRunRecord } from "./run.js";
import {
  campaignOperationDescriptor,
  campaignOperationId,
  campaignResultIdentity,
  completeCampaignOperation,
  createCampaignProgress,
  queueCampaignRecovery,
  unlockTrueCampaignExtension,
} from "./campaign-progress.js";
import {
  clearActiveRunSave,
  readActiveRunSave,
  readProfile,
  writeActiveRunSave,
  writeProfile,
} from "./save.js";

export const SERVICE_TIME_LIMIT_MS = 120_000;
export const RELOCATION_TIME_COST_MS = 5_000;

export const PHASES = Object.freeze({
  TITLE: "TITLE",
  NEW_GAME: "NEW_GAME",
  TUTORIAL: "TUTORIAL",
  STORY: "STORY",
  RELIC_OFFER: "RELIC_OFFER",
  ENDLESS_BRIEFING: "ENDLESS_BRIEFING",
  ENDLESS_AUDIT: "ENDLESS_AUDIT",
  DAY_OPENING: "DAY_OPENING",
  RESERVATION: "RESERVATION",
  PLACEMENT: "PLACEMENT",
  RESULT: "RESULT",
  RESULT_REVIEW: "RESULT_REVIEW",
  UPGRADE: "UPGRADE",
  FINAL: "FINAL",
});

const FORMAL_POST_OPERATION_PHASES = Object.freeze([
  PHASES.RESULT,
  PHASES.RESULT_REVIEW,
  PHASES.STORY,
  PHASES.UPGRADE,
  PHASES.FINAL,
]);

function initialRoomConditions(data) {
  return Object.fromEntries(
    data.rooms.map((room) => [room.id, { cleanliness: 100, durability: 100 }]),
  );
}

function unique(values) {
  return [...new Set(values)];
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function clampCondition(value) {
  return Math.max(0, Math.min(100, value));
}

function round2(value) {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

function maxFinite(values) {
  const finite = values
    .filter((value) => value !== null && value !== undefined)
    .map(Number)
    .filter(Number.isFinite);
  return finite.length ? Math.max(...finite) : null;
}

function relationshipPresentations(data, preset = "ALL_FEMALE") {
  return Object.fromEntries((data.campaign?.relationship_role_ids ?? []).map((roleId) => {
    const femaleOnly = roleId === "RELATIONSHIP_WITCH";
    const presentationId = preset === "MALE_CENTERED" && !femaleOnly ? "MALE" : "FEMALE";
    return [roleId, presentationId];
  }));
}

function relationshipProgress(data) {
  return Object.fromEntries((data.campaign?.relationship_role_ids ?? []).map((roleId) => [roleId, {
    epilogue_unlocked: false,
    npc_stage: "GUEST",
    event_count: 0,
    ending_ready: false,
    hotel_dependency: "INDEPENDENT",
  }]));
}

function speciesAffinities(data) {
  return Object.fromEntries((data.campaign?.formal_species ?? []).map((species) => [species.id, 0]));
}

function initialCampaignProgress(data) {
  if (data.prototype_mode?.type !== "FORMAL_CAMPAIGN") return null;
  if (!data.campaign?.formal_progress) {
    throw new Error("FORMAL_CAMPAIGN requires data.campaign.formal_progress");
  }
  return createCampaignProgress(data.campaign.formal_progress);
}

function initialState(data, seed, recordArchiveCount = 0, profile = null) {
  const defaults = data.campaign?.new_game_defaults ?? {};
  return {
    phase: PHASES.TITLE,
    profileId: profile?.profile_id ?? "default",
    currentNightIndex: 0,
    campaignProgress: initialCampaignProgress(data),
    storyNodeId: null,
    playerGenderId: defaults.player_gender_id ?? "MALE",
    relationshipGenderPreset: defaults.relationship_gender_preset ?? "ALL_FEMALE",
    relationshipPresentationIds: relationshipPresentations(
      data,
      defaults.relationship_gender_preset ?? "ALL_FEMALE",
    ),
    greyboxEndingRouteId: defaults.greybox_ending_route_id ?? "NORMAL",
    speciesAffinityById: speciesAffinities(data),
    speciesEndingTriggerIds: [],
    speciesEndingCommitmentId: null,
    relationshipProgressByRole: relationshipProgress(data),
    truthEvidenceCount: 0,
    peaceAllianceComplete: false,
    chapterHurdleFailures: 0,
    endlessSeasonIndex: 0,
    endlessSeasonNightIndex: 0,
    endlessOverallNightIndex: 0,
    endlessCompletedOperations: 0,
    endlessResultHistoryOmittedCount: 0,
    endlessSeasonStartResultIndex: 0,
    endlessAuditTarget: endlessAuditTarget(data, 0),
    endlessAuditPassedCount: 0,
    endlessAuditReport: null,
    endlessAuditHistory: [],
    endlessAuditHistoryOmittedCount: 0,
    endlessBestAuditScore: null,
    endlessLifetimeMetrics: {
      totalIncome: 0,
      reputationDelta: 0,
      acceptedGuests: 0,
      rejectedGuests: 0,
      canceledGuests: 0,
      emergencyNights: 0,
    },
    endlessRunFame: 0,
    endlessRiskTier: endlessRiskTier(data, 0),
    endlessClosed: false,
    endlessClosureReason: null,
    selectedEndingRelationshipRoleId: null,
    gold: 0,
    hotelReputation: 0,
    ownedUpgradeIds: [],
    ownedDisplayRelicIds: [],
    availableDisplayRelicPoolIds: [],
    displayRelicOfferIndex: 0,
    pendingDisplayRelicOffer: null,
    displayRelicTriggerCounts: {},
    displayRelicNightUsageIds: [],
    selectedGuestId: null,
    currentFixedGuestIds: [],
    currentGuestOfferIds: [],
    specialInviteGuestIds: [],
    acceptedGuestIds: [],
    rejectedGuestIds: [],
    applicantDecisions: {},
    placements: {},
    nightResults: [],
    currentRankOdds: { N: 100, R: 0, SR: 0, SSR: 0 },
    currentUpgradeOfferIds: [],
    renovationPurchaseIds: [],
    runSeed: seed >>> 0,
    rngState: createRngState(seed),
    handbookOpen: false,
    handbookTab: "hotel",
    reservationBoardOpen: false,
    serviceTimerMs: null,
    relocationCount: 0,
    emergencyReport: null,
    seenRankIds: unique(["N", ...(profile?.handbook?.seen_rank_ids ?? [])]),
    seenSpeciesIds: unique(profile?.handbook?.seen_species_ids ?? []),
    encounteredGuestIds: unique(profile?.handbook?.encountered_guest_ids ?? []),
    guestHistory: {},
    expectationReputationByGuest: {},
    discoveredHiddenPreferenceIds: unique(profile?.handbook?.discovered_hidden_preference_ids ?? []),
    lastDiscoveries: [],
    stayovers: {},
    lockedGuestIds: [],
    roomConditions: initialRoomConditions(data),
    lastRoomWear: [],
    secretaryPresentationId: null,
    foresightRetryCount: 0,
    foresightDiscoveryIds: [],
    runRecord: null,
    recordArchiveCount,
  };
}

export class GameController {
  constructor(data, options = {}) {
    this.data = data;
    const seed = Number.isFinite(options.seed) ? options.seed : Date.now();
    this.recordStorage = options.storage ?? globalThis.localStorage;
    this.profile = readProfile(this.recordStorage);
    this.state = initialState(data, seed, readRunRecords(this.recordStorage).length, this.profile);
    this.pendingCheckpoint = readActiveRunSave(this.data, this.recordStorage);
    this.stageCheckpoint = this.pendingCheckpoint?.stage_checkpoint
      ? clone(this.pendingCheckpoint.stage_checkpoint)
      : null;
  }

  get totalNights() {
    if (this.isFormalCampaignMode) return this.state.campaignProgress.stageLimit;
    return this.data.prototype_mode?.total_nights ?? this.data.scenarios.length;
  }

  get currentScenario() {
    return this.data.scenarios[this.state.currentNightIndex];
  }

  get currentNightNumber() {
    if (this.isFormalCampaignMode) {
      const progress = this.state.campaignProgress;
      if (FORMAL_POST_OPERATION_PHASES.includes(this.state.phase)) {
        return Math.max(1, progress.completedStageCount);
      }
      return progress.currentStageNumber ?? Math.max(1, progress.completedStageCount);
    }
    return this.isEndlessMode
      ? this.state.endlessSeasonNightIndex + 1
      : this.state.currentNightIndex + 1;
  }

  get endlessSeasonLength() {
    return Number(this.data.endless?.season_length ?? this.totalNights);
  }

  get progressionStage() {
    if (this.isFormalCampaignMode) return this.currentNightNumber;
    return this.isEndlessMode
      ? Math.max(1, this.state.endlessOverallNightIndex + 1)
      : this.currentNightNumber;
  }

  get nextProgressionStage() {
    if (this.isFormalCampaignMode) {
      const progress = this.state.campaignProgress;
      if (FORMAL_POST_OPERATION_PHASES.includes(this.state.phase)) {
        return progress.currentStageNumber ?? progress.completedStageCount + 1;
      }
      const currentStage = progress.currentStageNumber
        ?? Math.max(1, progress.completedStageCount);
      return currentStage + 1;
    }
    return this.isEndlessMode
      ? this.state.endlessCompletedOperations + 1
      : this.currentNightNumber + 1;
  }

  get currentResult() {
    if (this.isFormalCampaignMode) return this.state.nightResults.at(-1) ?? null;
    return this.isEndlessMode
      ? this.state.nightResults.at(-1) ?? null
      : this.state.nightResults[this.state.currentNightIndex] ?? null;
  }

  get currentStoryNode() {
    return this.data.campaign?.story_nodes?.find((node) => node.id === this.state.storyNodeId) ?? null;
  }

  get isScenarioMode() {
    return ["CAMPAIGN", "SCENARIO", "FORMAL_CAMPAIGN"].includes(
      this.data.prototype_mode?.type,
    );
  }

  get isFormalCampaignMode() {
    return this.data.prototype_mode?.type === "FORMAL_CAMPAIGN";
  }

  get isEndlessMode() {
    return this.data.prototype_mode?.type === "ENDLESS";
  }

  get formalCampaignProgressConfig() {
    return this.data.campaign?.formal_progress;
  }

  formalCampaignCurrentStageIndex() {
    const stageNumber = this.state.campaignProgress?.currentStageNumber;
    return Number.isSafeInteger(stageNumber) ? stageNumber - 1 : null;
  }

  hotelContext() {
    return {
      ownedFacilityIds: this.state.ownedUpgradeIds,
      roomConditions: this.state.roomConditions,
      protectedRoomIds: Object.values(this.state.stayovers).map((entry) => entry.roomId),
      guestHistory: this.state.guestHistory,
      hotelReputation: this.state.hotelReputation,
      expectationReputationByGuest: this.state.expectationReputationByGuest,
      stayoverGuestIds: [...this.state.lockedGuestIds],
      discoveredHiddenPreferenceIds: this.state.discoveredHiddenPreferenceIds,
    };
  }

  roomCapacitySummary() {
    const board = createBoardState(this.data, this.hotelContext());
    const startingRoomCount = this.data.rooms.filter((room) => room.built_from_start !== false).length;
    const builtRoomCount = board.unlockedRooms.size;
    const addedRoomCount = Math.max(0, builtRoomCount - startingRoomCount);
    const increasePerRoom = this.data.balance?.booking_capacity_per_expansion_room ?? 1;
    const baseServiceLimit = this.currentScenario?.capacity
      ?? this.data.balance?.base_booking_capacity
      ?? startingRoomCount;
    const serviceLimit = baseServiceLimit + addedRoomCount * increasePerRoom;
    const usableRoomIds = [...board.unlockedRooms].filter((roomId) => !board.blockedRooms.has(roomId));
    const stayoverRoomIds = [...new Set(Object.values(this.state.stayovers).map((entry) => entry.roomId))]
      .filter((roomId) => usableRoomIds.includes(roomId));
    return {
      board,
      startingRoomCount,
      builtRoomCount,
      addedRoomCount,
      serviceLimit,
      usableRoomIds,
      physicalPlacementLimit: usableRoomIds.length,
      stayoverRoomIds,
      openRoomCount: Math.max(0, usableRoomIds.length - stayoverRoomIds.length),
    };
  }

  structuralBoardState() {
    return createBoardState(this.data, {
      ...this.hotelContext(),
      roomConditions: {},
      protectedRoomIds: [],
    });
  }

  get currentServiceLimit() {
    return this.roomCapacitySummary().serviceLimit;
  }

  rememberGuests(guestIds) {
    const ranks = [...this.state.seenRankIds];
    const species = [...this.state.seenSpeciesIds];
    const encountered = [...this.state.encounteredGuestIds];
    for (const guestId of guestIds) {
      const guest = this.data.indexes.guests[guestId];
      if (!guest) continue;
      ranks.push(guest.rank);
      species.push(guest.species);
      encountered.push(guestId);
    }
    this.state.seenRankIds = unique(ranks);
    this.state.seenSpeciesIds = unique(species);
    this.state.encounteredGuestIds = unique(encountered);
  }

  persistProfileKnowledge(options = {}) {
    this.profile = writeProfile({
      ...this.profile,
      handbook: {
        discovered_hidden_preference_ids: unique([
          ...(this.profile.handbook?.discovered_hidden_preference_ids ?? []),
          ...this.state.discoveredHiddenPreferenceIds,
        ]),
        seen_rank_ids: unique([
          ...(this.profile.handbook?.seen_rank_ids ?? []),
          ...this.state.seenRankIds,
        ]),
        seen_species_ids: unique([
          ...(this.profile.handbook?.seen_species_ids ?? []),
          ...this.state.seenSpeciesIds,
        ]),
        encountered_guest_ids: unique([
          ...(this.profile.handbook?.encountered_guest_ids ?? []),
          ...this.state.encounteredGuestIds,
        ]),
      },
      display_relics: {
        unlocked_pool_ids: unique([
          ...(this.profile.display_relics?.unlocked_pool_ids ?? []),
          ...this.state.availableDisplayRelicPoolIds,
        ]),
        seen_ids: unique([
          ...(this.profile.display_relics?.seen_ids ?? []),
          ...(this.state.pendingDisplayRelicOffer?.relicIds ?? []),
          ...this.state.ownedDisplayRelicIds,
        ]),
        acquired_ids: unique([
          ...(this.profile.display_relics?.acquired_ids ?? []),
          ...this.state.ownedDisplayRelicIds,
        ]),
        triggered_ids: unique([
          ...(this.profile.display_relics?.triggered_ids ?? []),
          ...(options.commitRelicTriggers
            ? Object.entries(this.state.displayRelicTriggerCounts)
              .filter(([, count]) => count > 0)
              .map(([id]) => id)
          : []),
        ]),
      },
      endless: options.commitEndlessBest && this.isEndlessMode
        ? {
          best_survived_nights: Math.max(
            Number(this.profile.endless?.best_survived_nights ?? 0),
            Number(this.state.endlessCompletedOperations ?? 0),
          ),
          best_cleared_seasons: Math.max(
            Number(this.profile.endless?.best_cleared_seasons ?? 0),
            Number(this.state.endlessAuditPassedCount ?? 0),
          ),
          best_audit_score: maxFinite([
            this.profile.endless?.best_audit_score,
            this.state.endlessBestAuditScore,
          ]),
          best_run_fame: Math.max(
            Number(this.profile.endless?.best_run_fame ?? 0),
            Number(this.state.endlessRunFame ?? 0),
          ),
        }
        : { ...(this.profile.endless ?? {}) },
    }, this.recordStorage);
    return this.profile;
  }

  start() {
    clearActiveRunSave(this.data, this.recordStorage);
    this.pendingCheckpoint = null;
    this.stageCheckpoint = null;
    if (this.isScenarioMode) {
      const defaults = this.data.campaign?.new_game_defaults ?? {};
      this.state.phase = PHASES.NEW_GAME;
      this.state.playerGenderId = defaults.player_gender_id ?? "MALE";
      this.state.relationshipGenderPreset = defaults.relationship_gender_preset ?? "ALL_FEMALE";
      this.state.relationshipPresentationIds = relationshipPresentations(
        this.data,
        this.state.relationshipGenderPreset,
      );
      this.state.secretaryPresentationId = defaults.secretary_presentation_id ?? "FEMALE";
      this.applyGreyboxEndingRoute(defaults.greybox_ending_route_id ?? "NORMAL");
      return true;
    }
    if (this.isEndlessMode) {
      this.prepareEndlessSeason(0);
      return true;
    }
    this.startTutorial();
    return true;
  }

  hasCheckpoint() {
    return Boolean(this.pendingCheckpoint ?? readActiveRunSave(this.data, this.recordStorage));
  }

  saveCheckpoint() {
    this.persistProfileKnowledge();
    const save = writeActiveRunSave(this.data, this.state, this.stageCheckpoint, this.recordStorage);
    if (save) this.pendingCheckpoint = save;
    return save;
  }

  resumeRun() {
    const save = this.pendingCheckpoint ?? readActiveRunSave(this.data, this.recordStorage);
    if (!save || save.profile_id !== this.profile.profile_id) return false;
    const archiveCount = readRunRecords(this.recordStorage).length;
    this.state = {
      ...initialState(this.data, save.state.runSeed, archiveCount, this.profile),
      ...save.state,
      handbookOpen: false,
      reservationBoardOpen: false,
      runRecord: null,
      recordArchiveCount: archiveCount,
    };
    this.stageCheckpoint = save.stage_checkpoint ? clone(save.stage_checkpoint) : null;
    this.pendingCheckpoint = save;
    return true;
  }

  startTutorial() {
    const tutorialIds = this.data.prototype_mode?.tutorial_guest_ids
      ?? this.data.scenarios[0].fixed_guests.slice(0, 2);
    this.state.phase = PHASES.TUTORIAL;
    this.state.acceptedGuestIds = [...tutorialIds];
    this.state.rejectedGuestIds = [];
    this.state.placements = {};
    this.state.selectedGuestId = tutorialIds[0] ?? null;
    this.state.serviceTimerMs = null;
    this.state.relocationCount = 0;
    this.state.emergencyReport = null;
    this.state.lockedGuestIds = [];
    this.rememberGuests(tutorialIds);
  }

  skipTutorial() {
    if ([PHASES.TITLE, PHASES.TUTORIAL].includes(this.state.phase)) {
      if (this.state.phase === PHASES.TITLE) {
        clearActiveRunSave(this.data, this.recordStorage);
        this.pendingCheckpoint = null;
      }
      this.beginOperatingDay(0);
    }
  }

  startNight1() {
    this.beginOperatingDay(0);
  }

  setSecretaryPresentation(presentationId) {
    if (!["FEMALE", "MALE"].includes(presentationId)) return false;
    if (![PHASES.TITLE, PHASES.NEW_GAME, PHASES.TUTORIAL].includes(this.state.phase)) return false;
    this.state.secretaryPresentationId = presentationId;
    return true;
  }

  setPlayerGender(genderId) {
    if (this.state.phase !== PHASES.NEW_GAME || !["MALE", "FEMALE"].includes(genderId)) return false;
    this.state.playerGenderId = genderId;
    return true;
  }

  setRelationshipGenderPreset(presetId) {
    if (this.state.phase !== PHASES.NEW_GAME) return false;
    if (!["ALL_FEMALE", "MALE_CENTERED", "PER_ROLE"].includes(presetId)) return false;
    this.state.relationshipGenderPreset = presetId;
    this.state.relationshipPresentationIds = relationshipPresentations(this.data, presetId);
    return true;
  }

  setRelationshipRolePresentation(roleId, presentationId) {
    if (this.state.phase !== PHASES.NEW_GAME) return false;
    if (this.state.relationshipGenderPreset !== "PER_ROLE") return false;
    if (!(this.data.campaign?.relationship_role_ids ?? []).includes(roleId)) return false;
    if (!["FEMALE", "MALE"].includes(presentationId)) return false;
    if (roleId === "RELATIONSHIP_WITCH" && presentationId !== "FEMALE") return false;
    this.state.relationshipPresentationIds[roleId] = presentationId;
    return true;
  }

  applyGreyboxEndingRoute(routeId) {
    const route = this.data.campaign?.ending_preview_routes?.find((item) => item.id === routeId);
    if (!route) return false;
    this.state.greyboxEndingRouteId = route.id;
    this.state.speciesAffinityById = {
      ...speciesAffinities(this.data),
      ...(route.species_affinity_by_id ?? {}),
    };
    this.state.speciesEndingTriggerIds = [...(route.species_ending_trigger_ids ?? [])];
    this.state.speciesEndingCommitmentId = route.species_ending_commitment_id ?? null;
    this.state.relationshipProgressByRole = {
      ...relationshipProgress(this.data),
      ...clone(route.relationship_progress_by_role ?? {}),
    };
    this.state.truthEvidenceCount = route.truth_evidence_count ?? 0;
    this.state.peaceAllianceComplete = route.peace_alliance_complete === true;
    this.state.chapterHurdleFailures = route.chapter_hurdle_failures ?? 0;
    this.state.selectedEndingRelationshipRoleId = route.selected_ending_relationship_role_id ?? null;
    return true;
  }

  setGreyboxEndingRoute(routeId) {
    if (this.state.phase !== PHASES.NEW_GAME) return false;
    return this.applyGreyboxEndingRoute(routeId);
  }

  confirmNewGame() {
    if (this.state.phase !== PHASES.NEW_GAME) return false;
    if (!["MALE", "FEMALE"].includes(this.state.playerGenderId)) return false;
    if (!["FEMALE", "MALE"].includes(this.state.secretaryPresentationId)) return false;
    return this.openStoryNode("CAMPAIGN_PROLOGUE");
  }

  openStoryNode(storyNodeId) {
    if (!this.data.campaign?.story_nodes?.some((node) => node.id === storyNodeId)) return false;
    this.state.storyNodeId = storyNodeId;
    this.state.phase = PHASES.STORY;
    this.state.handbookOpen = false;
    this.state.reservationBoardOpen = false;
    this.state.serviceTimerMs = null;
    return true;
  }

  continueStory() {
    if (this.state.phase !== PHASES.STORY || !this.currentStoryNode) return false;
    const continuation = this.currentStoryNode.continuation ?? {};
    const completedStoryId = this.currentStoryNode.id;
    this.state.storyNodeId = null;
    const relicSchedule = this.data.campaign?.display_relic_offer_schedule?.find(
      (entry) => entry.after_story_id === completedStoryId
        && !this.state.ownedDisplayRelicIds.length
        && this.state.displayRelicOfferIndex === 0,
    );
    if (relicSchedule) {
      return this.prepareDisplayRelicOffer(relicSchedule, continuation);
    }
    if (continuation.action === "BEGIN_DAY") {
      const stageIndex = this.isFormalCampaignMode
        ? this.formalCampaignCurrentStageIndex()
        : continuation.night_index ?? this.state.currentNightIndex;
      return stageIndex === null ? false : this.beginOperatingDay(stageIndex);
    }
    if (continuation.action === "OPEN_UPGRADE") return this.prepareNextUpgrade();
    if (continuation.action === "COMPLETE_RUN") {
      this.completeRun();
      return true;
    }
    return false;
  }

  prepareDisplayRelicOffer(schedule, continuation) {
    if ((!this.isScenarioMode && !this.isEndlessMode) || this.state.pendingDisplayRelicOffer) return false;
    const poolIds = unique(schedule.pool_ids ?? ["COMMON"]);
    const offer = generateDisplayRelicOffer(this.data, {
      runSeed: this.state.runSeed,
      offerIndex: this.state.displayRelicOfferIndex,
      poolIds,
      ownedIds: this.state.ownedDisplayRelicIds,
      offerSize: schedule.offer_size ?? 3,
    });
    if (!offer.relicIds.length) return this.resumeAfterDisplayRelicOffer(continuation);
    this.state.availableDisplayRelicPoolIds = unique([
      ...this.state.availableDisplayRelicPoolIds,
      ...poolIds,
    ]);
    this.state.pendingDisplayRelicOffer = {
      scheduleId: schedule.id,
      relicIds: offer.relicIds,
      offerIndex: offer.offerIndex,
      continuation: clone(continuation),
    };
    this.state.phase = PHASES.RELIC_OFFER;
    this.state.handbookOpen = false;
    this.state.reservationBoardOpen = false;
    return true;
  }

  selectDisplayRelic(relicId) {
    const pending = this.state.pendingDisplayRelicOffer;
    if (this.state.phase !== PHASES.RELIC_OFFER || !pending?.relicIds.includes(relicId)) return false;
    if (!displayRelicById(this.data, relicId)) return false;
    const continuation = clone(pending.continuation ?? {});
    this.state.ownedDisplayRelicIds = unique([...this.state.ownedDisplayRelicIds, relicId]);
    this.state.displayRelicOfferIndex += 1;
    this.state.pendingDisplayRelicOffer = null;
    return this.resumeAfterDisplayRelicOffer(continuation);
  }

  skipDisplayRelicOffer() {
    const pending = this.state.pendingDisplayRelicOffer;
    if (this.state.phase !== PHASES.RELIC_OFFER || !pending) return false;
    const continuation = clone(pending.continuation ?? {});
    this.state.displayRelicOfferIndex += 1;
    this.state.pendingDisplayRelicOffer = null;
    return this.resumeAfterDisplayRelicOffer(continuation);
  }

  resumeAfterDisplayRelicOffer(continuation) {
    if (continuation.action === "BEGIN_DAY") {
      const stageIndex = this.isFormalCampaignMode
        ? this.formalCampaignCurrentStageIndex()
        : continuation.night_index ?? this.state.currentNightIndex;
      return stageIndex === null ? false : this.beginOperatingDay(stageIndex);
    }
    if (continuation.action === "OPEN_UPGRADE") return this.prepareNextUpgrade();
    if (continuation.action === "BEGIN_ENDLESS_SEASON") {
      return this.beginEndlessNight(0);
    }
    if (continuation.action === "COMPLETE_RUN") {
      this.completeRun();
      return true;
    }
    return false;
  }

  prepareEndlessSeason(seasonIndex = this.state.endlessSeasonIndex) {
    if (!this.isEndlessMode) return false;
    const resultLimit = Number(this.data.endless?.result_history_limit ?? 20);
    const retainedBeforeSeason = Math.max(0, resultLimit - this.endlessSeasonLength);
    if (this.state.nightResults.length > retainedBeforeSeason) {
      const removed = this.state.nightResults.length - retainedBeforeSeason;
      this.state.nightResults = retainedBeforeSeason > 0
        ? this.state.nightResults.slice(-retainedBeforeSeason)
        : [];
      this.state.endlessResultHistoryOmittedCount += removed;
    }
    this.state.endlessSeasonIndex = seasonIndex;
    this.state.endlessSeasonNightIndex = 0;
    this.state.endlessOverallNightIndex = this.state.endlessCompletedOperations;
    this.state.endlessSeasonStartResultIndex = this.state.nightResults.length;
    this.state.endlessAuditTarget = endlessAuditTarget(
      this.data,
      this.state.endlessAuditPassedCount,
    );
    this.state.endlessRiskTier = endlessRiskTier(
      this.data,
      this.state.endlessAuditPassedCount,
    );
    this.state.endlessAuditReport = null;
    this.state.phase = PHASES.ENDLESS_BRIEFING;
    this.state.handbookOpen = false;
    this.state.reservationBoardOpen = false;
    this.state.serviceTimerMs = null;
    this.stageCheckpoint = null;
    return true;
  }

  startEndlessSeason() {
    if (!this.isEndlessMode || this.state.phase !== PHASES.ENDLESS_BRIEFING) return false;
    const schedule = this.data.endless?.relic_offer;
    if (schedule) {
      return this.prepareDisplayRelicOffer(
        { ...schedule, id: `${schedule.id}_S${this.state.endlessSeasonIndex + 1}` },
        { action: "BEGIN_ENDLESS_SEASON" },
      );
    }
    return this.beginEndlessNight(0);
  }

  beginEndlessNight(seasonNightIndex) {
    if (!this.isEndlessMode) return false;
    const seasonLength = Number(this.data.endless?.season_length ?? this.totalNights);
    if (!Number.isInteger(seasonNightIndex) || seasonNightIndex < 0 || seasonNightIndex >= seasonLength) {
      return false;
    }
    this.state.endlessSeasonNightIndex = seasonNightIndex;
    this.state.endlessOverallNightIndex = this.state.endlessCompletedOperations;
    this.beginNight(seasonNightIndex % this.data.scenarios.length);
    return true;
  }

  beginOperatingDay(index) {
    if (!this.isScenarioMode) {
      this.beginNight(index);
      return true;
    }
    if (!["FEMALE", "MALE"].includes(this.state.secretaryPresentationId)) return false;
    if (this.isFormalCampaignMode) {
      const progress = this.state.campaignProgress;
      if (!Number.isSafeInteger(index) || index < 0 || index !== progress.currentStageNumber - 1) {
        return false;
      }
      const operation = campaignOperationDescriptor(this.formalCampaignProgressConfig, progress);
      if (operation.templateIndex >= this.data.scenarios.length) return false;
      this.state.currentNightIndex = operation.templateIndex;
      this.state.phase = PHASES.DAY_OPENING;
      this.state.handbookOpen = false;
      this.state.reservationBoardOpen = false;
      this.state.serviceTimerMs = null;
      this.stageCheckpoint = clone(this.state);
      return true;
    }
    if (index >= this.data.scenarios.length) {
      this.completeRun();
      return true;
    }
    this.state.currentNightIndex = index;
    this.state.phase = PHASES.DAY_OPENING;
    this.state.handbookOpen = false;
    this.state.reservationBoardOpen = false;
    this.state.serviceTimerMs = null;
    this.stageCheckpoint = clone(this.state);
    return true;
  }

  startDayBusiness() {
    if (this.state.phase !== PHASES.DAY_OPENING) return false;
    if (this.isFormalCampaignMode) {
      return this.beginNight(this.state.currentNightIndex) === true;
    }
    this.beginNight(this.state.currentNightIndex);
    return true;
  }

  beginNight(index) {
    let formalOperation = null;
    if (this.isFormalCampaignMode) {
      formalOperation = campaignOperationDescriptor(
        this.formalCampaignProgressConfig,
        this.state.campaignProgress,
      );
      if (index !== formalOperation.templateIndex) return false;
    } else if (index >= this.data.scenarios.length) {
      this.completeRun();
      return;
    }
    this.state.currentNightIndex = index;
    const scenario = this.currentScenario;
    const stage = this.isFormalCampaignMode
      ? formalOperation.stageNumber
      : this.isEndlessMode
        ? this.state.endlessOverallNightIndex + 1
        : index + 1;
    const stayoverIds = Object.keys(this.state.stayovers);
    const fixedGuestIds = unique([
      ...stayoverIds,
      ...(scenario.fixed_guests ?? []).filter((id) => !stayoverIds.includes(id)),
    ]);
    const fixedPlacements = Object.fromEntries(
      stayoverIds.map((guestId) => [guestId, this.state.stayovers[guestId].roomId]),
    );
    const odds = rankOddsFor(this.data, stage, this.state.hotelReputation);
    let offer = { guestIds: [], specialInviteIds: [], rngState: this.state.rngState };
    if ((scenario.offer_size ?? 0) > 0) {
      offer = generateGuestOffer(
        this.data,
        scenario,
        odds,
        this.state.rngState,
        fixedGuestIds,
      );
    }

    this.state.rngState = offer.rngState;
    this.state.currentFixedGuestIds = fixedGuestIds;
    this.state.currentGuestOfferIds = offer.guestIds;
    this.state.specialInviteGuestIds = offer.specialInviteIds;
    this.state.currentRankOdds = odds;
    this.state.acceptedGuestIds = [...fixedGuestIds];
    this.state.rejectedGuestIds = [];
    this.state.applicantDecisions = {};
    this.state.placements = fixedPlacements;
    this.state.lockedGuestIds = [...stayoverIds];
    for (const guestId of fixedGuestIds) {
      if (!stayoverIds.includes(guestId)) {
        this.state.expectationReputationByGuest[guestId] = this.state.hotelReputation;
      }
    }
    this.state.selectedGuestId = fixedGuestIds.find((id) => !stayoverIds.includes(id)) ?? null;
    this.state.serviceTimerMs = null;
    this.state.relocationCount = 0;
    this.state.displayRelicNightUsageIds = [];
    this.state.emergencyReport = null;
    this.state.currentUpgradeOfferIds = [];
    this.state.renovationPurchaseIds = [];
    this.state.lastRoomWear = [];
    this.state.lastDiscoveries = [];
    this.state.reservationBoardOpen = false;
    this.rememberGuests([...fixedGuestIds, ...offer.guestIds]);

    if (offer.guestIds.length) {
      this.state.phase = PHASES.RESERVATION;
    } else {
      this.startPlacement();
    }
    if (!this.isScenarioMode) this.stageCheckpoint = clone(this.state);
    if (this.isFormalCampaignMode) return true;
  }

  openHandbook(tab = this.state.handbookTab) {
    this.state.reservationBoardOpen = false;
    this.state.handbookOpen = true;
    this.state.handbookTab = tab;
  }

  closeHandbook() {
    this.state.handbookOpen = false;
  }

  openReservationBoard() {
    if (this.state.phase !== PHASES.RESERVATION) return false;
    this.state.handbookOpen = false;
    this.state.reservationBoardOpen = true;
    return true;
  }

  closeReservationBoard() {
    this.state.reservationBoardOpen = false;
  }

  selectHandbookTab(tab) {
    if (["hotel", "species", "rank", "relics", "discoveries"].includes(tab)) {
      this.state.handbookTab = tab;
    }
  }

  isLockedGuest(guestId) {
    return this.state.lockedGuestIds.includes(guestId);
  }

  selectGuest(guestId) {
    if (this.state.acceptedGuestIds.includes(guestId)) {
      this.state.selectedGuestId = guestId;
    }
  }

  placeGuest(guestId, roomId) {
    if (![PHASES.TUTORIAL, PHASES.PLACEMENT].includes(this.state.phase)) return false;
    if (!this.state.acceptedGuestIds.includes(guestId) || this.isLockedGuest(guestId)) return false;
    const board = evaluatePlacement(this.data, [], {}, this.hotelContext()).board;
    if (board.blockedRooms.has(roomId)) return false;
    const occupant = Object.entries(this.state.placements).find(([, value]) => value === roomId)?.[0];
    if (occupant && occupant !== guestId && this.isLockedGuest(occupant)) return false;
    const previousRoom = this.state.placements[guestId];
    const isRelocation = (previousRoom !== undefined && previousRoom !== roomId)
      || Boolean(occupant && occupant !== guestId);
    if (occupant && occupant !== guestId) {
      if (previousRoom) this.state.placements[occupant] = previousRoom;
      else delete this.state.placements[occupant];
    }
    this.state.placements[guestId] = roomId;
    this.state.selectedGuestId = guestId;
    if (isRelocation) this.chargeRelocation();
    return true;
  }

  unplaceGuest(guestId) {
    if (![PHASES.TUTORIAL, PHASES.PLACEMENT].includes(this.state.phase)) return false;
    if (this.isLockedGuest(guestId)) return false;
    const wasPlaced = Boolean(this.state.placements[guestId]);
    delete this.state.placements[guestId];
    this.state.selectedGuestId = guestId;
    if (wasPlaced) this.chargeRelocation();
    return wasPlaced;
  }

  isTimedPlacement() {
    return this.state.phase === PHASES.PLACEMENT;
  }

  chargeRelocation() {
    if (!this.isTimedPlacement() || this.state.serviceTimerMs === null) return false;
    this.state.relocationCount += 1;
    let timeCost = RELOCATION_TIME_COST_MS;
    const relic = this.ownedRelicWithEffect("FIRST_RELOCATION_TIME_REDUCTION");
    if (relic && !this.state.displayRelicNightUsageIds.includes(relic.id)) {
      timeCost = Math.max(0, timeCost - Number(relic.effect_params?.value ?? 0));
      this.state.displayRelicNightUsageIds.push(relic.id);
      this.recordDisplayRelicTrigger(relic.id);
    }
    this.state.serviceTimerMs = Math.max(0, this.state.serviceTimerMs - timeCost);
    if (this.state.serviceTimerMs === 0) this.resolveTimedOutNight();
    return true;
  }

  advanceTimer(elapsedMs) {
    if (!this.isTimedPlacement() || this.state.handbookOpen || this.state.serviceTimerMs === null) return false;
    const before = Math.ceil(this.state.serviceTimerMs / 1000);
    this.state.serviceTimerMs = Math.max(0, this.state.serviceTimerMs - Math.max(0, elapsedMs));
    if (this.state.serviceTimerMs === 0) {
      this.resolveTimedOutNight();
      return true;
    }
    return Math.ceil(this.state.serviceTimerMs / 1000) !== before;
  }

  currentEvaluation() {
    if (![PHASES.TUTORIAL, PHASES.PLACEMENT].includes(this.state.phase)) return null;
    return evaluatePlacement(
      this.data,
      this.state.acceptedGuestIds,
      this.state.placements,
      this.hotelContext(),
    );
  }

  finishNight() {
    if (this.state.phase === PHASES.TUTORIAL) {
      if (!this.currentEvaluation().valid) return false;
      this.beginOperatingDay(0);
      return true;
    }
    if (this.state.phase !== PHASES.PLACEMENT) return false;
    const result = calculateNightResult(
      this.data,
      this.currentScenario,
      this.state.acceptedGuestIds,
      this.state.rejectedGuestIds,
      this.state.placements,
      this.hotelContext(),
    );
    if (!result.valid) return false;
    this.completeNight(result);
    return true;
  }

  applyRoomWearAndStays(result) {
    const nextStayovers = {};
    const wear = [];
    for (const guestId of result.acceptedGuestIds) {
      const guest = this.data.indexes.guests[guestId];
      const roomId = result.placements[guestId];
      if (!guest || !roomId) continue;
      const condition = this.state.roomConditions[roomId] ?? { cleanliness: 100, durability: 100 };
      const wearScale = this.data.balance?.wear_scale ?? 1;
      const cleanlinessLoss = guest.room_wear?.cleanliness
        ?? (guest.cleanliness_impact ?? 1) * wearScale;
      const durabilityLoss = guest.room_wear?.durability
        ?? (guest.durability_impact ?? 0) * wearScale;
      condition.cleanliness = clampCondition(condition.cleanliness - cleanlinessLoss);
      condition.durability = clampCondition(condition.durability - durabilityLoss);
      this.state.roomConditions[roomId] = condition;
      wear.push({ guestId, roomId, cleanlinessLoss, durabilityLoss, ...condition });

      const existing = this.state.stayovers[guestId];
      if (existing && existing.remainingNights > 1) {
        nextStayovers[guestId] = { roomId, remainingNights: existing.remainingNights - 1 };
      } else if (!existing && (guest.stay_nights ?? 1) > 1) {
        nextStayovers[guestId] = { roomId, remainingNights: guest.stay_nights - 1 };
      }
    }
    this.state.stayovers = nextStayovers;
    this.state.expectationReputationByGuest = Object.fromEntries(
      Object.keys(nextStayovers).map((guestId) => [
        guestId,
        this.state.expectationReputationByGuest[guestId] ?? this.state.hotelReputation,
      ]),
    );
    this.state.lastRoomWear = wear;
  }

  prepareFormalCampaignCompletion() {
    if (!this.isFormalCampaignMode) return null;
    const config = this.formalCampaignProgressConfig;
    const progress = this.state.campaignProgress;
    if (this.state.nightResults.length !== progress.completedStageCount) {
      throw new Error("Formal campaign result history is out of sync with campaign progress");
    }
    const operation = campaignOperationDescriptor(config, progress);
    if (operation.templateIndex !== this.state.currentNightIndex) {
      throw new Error("Formal campaign operation does not match the active scenario template");
    }
    const operationId = campaignOperationId(config, this.state.runSeed, operation);
    if (this.state.nightResults.some(
      (entry) => entry?.campaignOperationId === operationId,
    )) {
      throw new Error(`Duplicate formal campaign operation result: ${operationId}`);
    }
    const nextProgress = completeCampaignOperation(config, progress, operation);
    return {
      operation,
      operationId,
      resultIdentity: campaignResultIdentity(config, operation),
      nextProgress,
    };
  }

  completeNight(result) {
    const formalCompletion = this.prepareFormalCampaignCompletion();
    const resolvedResult = this.applyDisplayRelicResultEffects(result);
    if (formalCompletion) {
      resolvedResult.campaignOperationId = formalCompletion.operationId;
      resolvedResult.campaignResultIdentity = clone(formalCompletion.resultIdentity);
      resolvedResult.campaignRecoveryBoundaryStageNumber =
        formalCompletion.operation.recoveryBoundaryStageNumber;
    }
    this.state.gold += resolvedResult.income;
    this.state.hotelReputation += resolvedResult.reputationDelta;
    this.updateGuestHistoryAndDiscoveries(resolvedResult);
    this.applyRoomWearAndStays(resolvedResult);
    if (formalCompletion) {
      this.state.nightResults.push(resolvedResult);
      this.state.campaignProgress = formalCompletion.nextProgress;
    } else if (this.isEndlessMode) {
      this.state.nightResults.push(resolvedResult);
      this.state.endlessCompletedOperations += 1;
      this.state.endlessOverallNightIndex = this.state.endlessCompletedOperations;
      this.state.endlessLifetimeMetrics = {
        totalIncome: this.state.endlessLifetimeMetrics.totalIncome + Number(resolvedResult.income ?? 0),
        reputationDelta: round2(
          this.state.endlessLifetimeMetrics.reputationDelta
          + Number(resolvedResult.reputationDelta ?? 0),
        ),
        acceptedGuests: this.state.endlessLifetimeMetrics.acceptedGuests
          + (resolvedResult.acceptedGuestIds?.length ?? 0),
        rejectedGuests: this.state.endlessLifetimeMetrics.rejectedGuests
          + (resolvedResult.rejectedGuestIds?.length ?? 0),
        canceledGuests: this.state.endlessLifetimeMetrics.canceledGuests
          + (resolvedResult.canceledGuestIds?.length ?? 0),
        emergencyNights: this.state.endlessLifetimeMetrics.emergencyNights
          + (resolvedResult.emergencyReport?.timedOut ? 1 : 0),
      };
    } else this.state.nightResults[this.state.currentNightIndex] = resolvedResult;
    this.state.serviceTimerMs = null;
    this.state.emergencyReport = resolvedResult.emergencyReport;
    this.state.phase = PHASES.RESULT;
  }

  ownedRelicWithEffect(effectId) {
    return this.state.ownedDisplayRelicIds
      .map((id) => displayRelicById(this.data, id))
      .find((relic) => relic?.effect_id === effectId) ?? null;
  }

  recordDisplayRelicTrigger(relicId) {
    this.state.displayRelicTriggerCounts[relicId] = Number(
      this.state.displayRelicTriggerCounts[relicId] ?? 0,
    ) + 1;
  }

  applyDisplayRelicResultEffects(result) {
    const resolved = clone(result);
    resolved.relicTriggers = [...(resolved.relicTriggers ?? [])];
    resolved.relicBonusGold = Number(resolved.relicBonusGold ?? 0);
    const relic = this.ownedRelicWithEffect("NO_CANCELLATION_GOLD_BONUS");
    if (
      relic
      && resolved.valid
      && (resolved.acceptedGuestIds?.length ?? 0) > 0
      && (resolved.canceledGuestIds?.length ?? 0) === 0
    ) {
      const bonus = Number(relic.effect_params?.value ?? 0);
      resolved.income += bonus;
      resolved.relicBonusGold += bonus;
      resolved.relicTriggers.push({ relicId: relic.id, value: bonus });
      this.recordDisplayRelicTrigger(relic.id);
    }
    return resolved;
  }

  updateGuestHistoryAndDiscoveries(result) {
    const known = new Set(this.state.discoveredHiddenPreferenceIds);
    const discoveries = [];
    for (const guestId of result.acceptedGuestIds) {
      const hiddenPreferences = getGuestRules(this.data, guestId).hiddenPreferences ?? [];
      hiddenPreferences.forEach((rule, index) => {
        const hiddenId = rule.id ?? `${guestId}:hidden:${index}`;
        if (known.has(hiddenId)) return;
        known.add(hiddenId);
        discoveries.push({
          hiddenId,
          guestId,
          speciesId: this.data.indexes.guests[guestId].species,
          rankId: this.data.indexes.guests[guestId].rank,
          label: rule.label,
          points: rule.points,
        });
      });
      const satisfaction = result.guestScores[guestId]?.total ?? 0;
      const review = result.guestReviews?.find((item) => item.guestId === guestId);
      const previous = this.state.guestHistory[guestId] ?? {
        visits: 0,
        lastSatisfaction: 0,
        bestSatisfaction: 0,
      };
      const continuingStay = this.isLockedGuest(guestId);
      this.state.guestHistory[guestId] = {
        visits: previous.visits + (continuingStay ? 0 : 1),
        lastSatisfaction: satisfaction,
        bestSatisfaction: Math.max(previous.bestSatisfaction, satisfaction),
        lastReaction: review?.reaction ?? "neutral",
      };
    }
    this.state.discoveredHiddenPreferenceIds = [...known];
    this.state.lastDiscoveries = discoveries;
    result.newDiscoveries = discoveries;
  }

  resolveTimedOutNight() {
    if (!this.isTimedPlacement()) return false;
    const originalPlacements = { ...this.state.placements };
    const plan = createEmergencyPlan(
      this.data,
      this.state.acceptedGuestIds,
      originalPlacements,
      this.hotelContext(),
      { lockedGuestIds: this.state.lockedGuestIds },
    );
    this.state.acceptedGuestIds = [...plan.housedGuestIds];
    this.state.placements = { ...plan.placements };
    this.state.selectedGuestId = plan.housedGuestIds[0] ?? null;
    const emergencyReport = {
      timedOut: true,
      autoAssignedGuestIds: [...plan.autoAssignedGuestIds],
      canceledGuestIds: [...plan.canceledGuestIds],
      relocationCount: this.state.relocationCount,
      keptExisting: plan.keptExisting,
      lockedGuestIds: [...plan.lockedGuestIds],
    };
    const result = calculateNightResult(
      this.data,
      this.currentScenario,
      plan.housedGuestIds,
      this.state.rejectedGuestIds,
      plan.placements,
      this.hotelContext(),
      { canceledGuestIds: plan.canceledGuestIds, emergencyReport },
    );
    if (!result.valid) throw new Error("긴급 배정이 필수 숙박 조건을 만족하지 못했습니다.");
    this.completeNight(result);
    return true;
  }

  continueAfterResult() {
    if (this.state.phase !== PHASES.RESULT) return false;
    if (this.isEndlessMode) {
      const seasonLength = Number(this.data.endless?.season_length ?? this.totalNights);
      if (this.state.endlessSeasonNightIndex + 1 >= seasonLength) {
        return this.finishEndlessSeasonAudit();
      }
      return this.prepareNextUpgrade();
    }
    if (this.currentNightNumber >= this.totalNights) {
      this.completeRun();
      return true;
    }
    const storyNodeId = this.data.campaign?.story_after_nights?.[String(this.currentNightNumber)];
    if (this.isScenarioMode && storyNodeId) return this.openStoryNode(storyNodeId);
    return this.prepareNextUpgrade();
  }

  prepareNextUpgrade() {
    if (!this.isEndlessMode && this.currentNightNumber >= this.totalNights) {
      this.completeRun();
      return true;
    }
    const nextStage = this.nextProgressionStage;
    const offer = generateUpgradeOffer(
      this.data,
      nextStage,
      this.state.hotelReputation,
      this.state.ownedUpgradeIds,
      this.state.gold,
      this.state.rngState,
    );
    this.state.currentUpgradeOfferIds = offer.upgradeIds;
    this.state.renovationPurchaseIds = [];
    this.state.rngState = offer.rngState;
    this.state.phase = PHASES.UPGRADE;
    return true;
  }

  openResultReview() {
    if (!this.isScenarioMode || this.state.phase !== PHASES.RESULT) return false;
    this.state.phase = PHASES.RESULT_REVIEW;
    return true;
  }

  queueFormalCampaignRecovery(boundaryStageNumber) {
    if (
      !this.isFormalCampaignMode
      || ![PHASES.RESULT, PHASES.RESULT_REVIEW].includes(this.state.phase)
    ) return false;
    this.state.campaignProgress = queueCampaignRecovery(
      this.formalCampaignProgressConfig,
      this.state.campaignProgress,
      boundaryStageNumber,
    );
    return true;
  }

  unlockFormalCampaignTrueExtension(gateEvidence) {
    if (
      !this.isFormalCampaignMode
      || ![PHASES.RESULT, PHASES.RESULT_REVIEW].includes(this.state.phase)
    ) return false;
    this.state.campaignProgress = unlockTrueCampaignExtension(
      this.formalCampaignProgressConfig,
      this.state.campaignProgress,
      gateEvidence,
    );
    return true;
  }

  acceptSecretaryReport() {
    if (this.state.phase !== PHASES.RESULT_REVIEW) return false;
    this.state.phase = PHASES.RESULT;
    return this.continueAfterResult();
  }

  restartDayThroughSecretary() {
    if (this.state.phase !== PHASES.RESULT_REVIEW) return false;
    return this.retryCurrentStage();
  }

  retryCurrentStage() {
    if (![PHASES.RESULT, PHASES.RESULT_REVIEW].includes(this.state.phase) || !this.stageCheckpoint) return false;
    const discardedFuture = this.state;
    const rememberedDiscoveries = unique([
      ...(discardedFuture.foresightDiscoveryIds ?? []),
      ...discardedFuture.lastDiscoveries.map((item) => item.hiddenId),
    ]);
    const discoveredPreferenceIds = unique([
      ...this.stageCheckpoint.discoveredHiddenPreferenceIds,
      ...discardedFuture.discoveredHiddenPreferenceIds,
    ]);
    const retryCount = (discardedFuture.foresightRetryCount ?? 0) + 1;
    this.state = {
      ...clone(this.stageCheckpoint),
      discoveredHiddenPreferenceIds: discoveredPreferenceIds,
      foresightRetryCount: retryCount,
      foresightDiscoveryIds: rememberedDiscoveries,
      handbookOpen: false,
      reservationBoardOpen: false,
      runRecord: null,
    };
    return true;
  }

  buyUpgrade(upgradeId) {
    if (this.state.phase !== PHASES.UPGRADE) return false;
    if (!this.state.currentUpgradeOfferIds.includes(upgradeId)) return false;
    const upgrade = this.data.indexes.upgrades[upgradeId];
    if (!upgrade) return false;
    const alreadyContractedKind = this.state.renovationPurchaseIds.some(
      (id) => this.data.indexes.upgrades[id]?.kind === upgrade.kind,
    );
    if (alreadyContractedKind) return false;
    if (!this.canContractUpgrade(upgradeId)) return false;
    const purchase = purchaseUpgrade(
      this.data,
      upgradeId,
      this.state.ownedUpgradeIds,
      this.state.gold,
    );
    if (!purchase.ok) return false;
    this.state.ownedUpgradeIds = purchase.ownedIds;
    this.state.gold = purchase.gold;
    this.state.renovationPurchaseIds.push(upgradeId);
    return true;
  }

  upgradeBlockedByStayover(upgradeId) {
    const upgrade = this.data.indexes.upgrades[upgradeId];
    if (!upgrade) return false;
    const occupiedRooms = new Set(Object.values(this.state.stayovers).map((entry) => entry.roomId));
    return renovationRoomIds(upgrade).some((roomId) => occupiedRooms.has(roomId));
  }

  canContractUpgrade(upgradeId) {
    return canPurchaseUpgrade(this.data, upgradeId, this.state.ownedUpgradeIds)
      && !this.upgradeBlockedByStayover(upgradeId);
  }

  finishUpgrade() {
    if (this.state.phase !== PHASES.UPGRADE) return false;
    if (this.isEndlessMode) {
      return this.beginEndlessNight(this.state.endlessSeasonNightIndex + 1);
    }
    if (this.isFormalCampaignMode) {
      const nextStageIndex = this.formalCampaignCurrentStageIndex();
      if (nextStageIndex === null) {
        this.completeRun();
        return true;
      }
      return this.beginOperatingDay(nextStageIndex);
    }
    this.beginOperatingDay(this.state.currentNightIndex + 1);
    return true;
  }

  finishEndlessSeasonAudit() {
    if (!this.isEndlessMode || this.state.phase !== PHASES.RESULT) return false;
    const report = calculateEndlessAudit(this.data, this.state);
    this.state.endlessAuditReport = clone(report);
    this.state.endlessAuditHistory.push(clone(report));
    this.state.endlessBestAuditScore = maxFinite([
      this.state.endlessBestAuditScore,
      report.score,
    ]);
    const auditHistoryLimit = Number(this.data.endless?.audit_history_limit ?? 12);
    if (this.state.endlessAuditHistory.length > auditHistoryLimit) {
      const removed = this.state.endlessAuditHistory.length - auditHistoryLimit;
      this.state.endlessAuditHistory.splice(0, removed);
      this.state.endlessAuditHistoryOmittedCount += removed;
    }
    if (report.passed) {
      this.state.endlessAuditPassedCount += 1;
      this.state.endlessRunFame += Number(
        this.data.endless?.run_fame?.fame_per_cleared_season ?? 0,
      );
      this.persistProfileKnowledge({ commitRelicTriggers: true, commitEndlessBest: true });
    }
    this.state.phase = PHASES.ENDLESS_AUDIT;
    this.state.serviceTimerMs = null;
    return true;
  }

  advanceEndlessSeason() {
    if (
      !this.isEndlessMode
      || this.state.phase !== PHASES.ENDLESS_AUDIT
      || !this.state.endlessAuditReport?.passed
    ) return false;
    return this.prepareEndlessSeason(this.state.endlessSeasonIndex + 1);
  }

  closeEndlessRun() {
    if (
      !this.isEndlessMode
      || this.state.phase !== PHASES.ENDLESS_AUDIT
      || this.state.endlessAuditReport?.passed !== false
    ) return false;
    this.state.endlessClosed = true;
    this.state.endlessClosureReason = "AUDIT_TARGET_MISSED";
    this.completeRun();
    return true;
  }

  skipUpgrade() {
    return this.finishUpgrade();
  }

  serviceRoom(roomId) {
    if (this.state.phase !== PHASES.UPGRADE) return false;
    if (Object.values(this.state.stayovers).some((entry) => entry.roomId === roomId)) return false;
    if (this.structuralBoardState().blockedRooms.has(roomId)) return false;
    const cost = this.roomServiceCost();
    const condition = this.state.roomConditions[roomId];
    if (!condition || this.state.gold < cost) return false;
    if (condition.cleanliness === 100 && condition.durability === 100) return false;
    this.state.gold -= cost;
    this.state.roomConditions[roomId] = { cleanliness: 100, durability: 100 };
    const relic = this.ownedRelicWithEffect("ROOM_SERVICE_COST_REDUCTION");
    if (relic) this.recordDisplayRelicTrigger(relic.id);
    return true;
  }

  roomServiceCost() {
    const baseCost = this.data.balance?.room_service_cost ?? 8;
    const reduction = displayRelicEffectValue(
      this.data,
      this.state.ownedDisplayRelicIds,
      "ROOM_SERVICE_COST_REDUCTION",
    );
    return Math.max(0, baseCost - reduction);
  }

  setApplicantDecision(guestId, decision) {
    if (!this.state.currentGuestOfferIds.includes(guestId)) return false;
    if (!["accept", "reject"].includes(decision)) return false;
    this.state.applicantDecisions[guestId] = decision;
    return true;
  }

  reservationSummary() {
    const applicants = this.state.currentGuestOfferIds;
    const acceptedApplicants = applicants.filter(
      (id) => this.state.applicantDecisions[id] === "accept",
    );
    const rejectedApplicants = applicants.filter(
      (id) => this.state.applicantDecisions[id] === "reject",
    );
    const pending = applicants.filter((id) => !this.state.applicantDecisions[id]);
    const accepted = unique([...this.state.currentFixedGuestIds, ...acceptedApplicants]);
    const roomCapacity = this.roomCapacitySummary();
    return {
      accepted,
      rejected: rejectedApplicants,
      pending,
      serviceLimit: roomCapacity.serviceLimit,
      physicalPlacementLimit: roomCapacity.physicalPlacementLimit,
      builtRoomCount: roomCapacity.builtRoomCount,
      openRoomCount: roomCapacity.openRoomCount,
      stayoverRoomCount: roomCapacity.stayoverRoomIds.length,
      placementMargin: roomCapacity.physicalPlacementLimit - accepted.length,
      overCapacity: accepted.length > roomCapacity.serviceLimit,
      overPhysicalCapacity: accepted.length > roomCapacity.physicalPlacementLimit,
    };
  }

  startPlacement() {
    this.state.phase = PHASES.PLACEMENT;
    this.state.selectedGuestId = this.state.acceptedGuestIds.find(
      (id) => !this.state.lockedGuestIds.includes(id),
    ) ?? this.state.acceptedGuestIds[0] ?? null;
    this.state.serviceTimerMs = SERVICE_TIME_LIMIT_MS;
    this.state.relocationCount = 0;
    this.state.emergencyReport = null;
  }

  confirmReservation() {
    const summary = this.reservationSummary();
    if (
      summary.pending.length
      || summary.overCapacity
      || summary.overPhysicalCapacity
      || summary.accepted.length === 0
    ) return false;
    this.state.acceptedGuestIds = summary.accepted;
    this.state.rejectedGuestIds = summary.rejected;
    for (const guestId of summary.accepted) {
      if (!this.state.lockedGuestIds.includes(guestId)) {
        this.state.expectationReputationByGuest[guestId] = this.state.hotelReputation;
      }
    }
    this.startPlacement();
    return true;
  }

  restart() {
    const nextSeed = (this.state.runSeed + 1) >>> 0;
    this.persistProfileKnowledge();
    clearActiveRunSave(this.data, this.recordStorage);
    this.pendingCheckpoint = null;
    this.stageCheckpoint = null;
    this.state = initialState(
      this.data,
      nextSeed,
      readRunRecords(this.recordStorage).length,
      this.profile,
    );
  }

  completeRun() {
    if (!this.state.runRecord) {
      this.persistProfileKnowledge({ commitRelicTriggers: true, commitEndlessBest: true });
      this.state.runRecord = createRunRecord(this.data, this.state);
      const records = storeRunRecord(this.state.runRecord, this.recordStorage);
      this.state.recordArchiveCount = records.length;
      clearActiveRunSave(this.data, this.recordStorage);
      this.pendingCheckpoint = null;
      this.stageCheckpoint = null;
    }
    this.state.phase = PHASES.FINAL;
    return this.state.runRecord;
  }
}
