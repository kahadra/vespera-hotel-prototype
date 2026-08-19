import { calculateNightResult } from "./scoring.js";
import { createBoardState, evaluatePlacement } from "./rules.js";
import { createEmergencyPlan } from "./emergency.js";
import { createRngState } from "./random.js";
import { generateGuestOffer, rankOddsFor } from "./progression.js";
import {
  canPurchaseUpgrade,
  generateUpgradeOffer,
  purchaseUpgrade,
  renovationRoomIds,
} from "./upgrades.js";
import { getGuestRules } from "./data.js";

export const SERVICE_TIME_LIMIT_MS = 120_000;
export const RELOCATION_TIME_COST_MS = 5_000;

export const PHASES = Object.freeze({
  TITLE: "TITLE",
  TUTORIAL: "TUTORIAL",
  RESERVATION: "RESERVATION",
  PLACEMENT: "PLACEMENT",
  RESULT: "RESULT",
  UPGRADE: "UPGRADE",
  FINAL: "FINAL",
});

function initialRoomConditions(data) {
  return Object.fromEntries(
    data.rooms.map((room) => [room.id, { cleanliness: 100, durability: 100 }]),
  );
}

function unique(values) {
  return [...new Set(values)];
}

function clampCondition(value) {
  return Math.max(0, Math.min(100, value));
}

function initialState(data, seed) {
  return {
    phase: PHASES.TITLE,
    currentNightIndex: 0,
    gold: 0,
    hotelReputation: 0,
    ownedUpgradeIds: [],
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
    seenRankIds: ["N"],
    seenSpeciesIds: [],
    guestHistory: {},
    discoveredHiddenPreferenceIds: [],
    lastDiscoveries: [],
    stayovers: {},
    lockedGuestIds: [],
    roomConditions: initialRoomConditions(data),
    lastRoomWear: [],
  };
}

export class GameController {
  constructor(data, options = {}) {
    this.data = data;
    const seed = Number.isFinite(options.seed) ? options.seed : Date.now();
    this.state = initialState(data, seed);
  }

  get totalNights() {
    return this.data.prototype_mode?.total_nights ?? this.data.scenarios.length;
  }

  get currentScenario() {
    return this.data.scenarios[this.state.currentNightIndex];
  }

  get currentNightNumber() {
    return this.state.currentNightIndex + 1;
  }

  get currentResult() {
    return this.state.nightResults[this.state.currentNightIndex] ?? null;
  }

  hotelContext() {
    return {
      ownedFacilityIds: this.state.ownedUpgradeIds,
      roomConditions: this.state.roomConditions,
      protectedRoomIds: Object.values(this.state.stayovers).map((entry) => entry.roomId),
      guestHistory: this.state.guestHistory,
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
    for (const guestId of guestIds) {
      const guest = this.data.indexes.guests[guestId];
      if (!guest) continue;
      ranks.push(guest.rank);
      species.push(guest.species);
    }
    this.state.seenRankIds = unique(ranks);
    this.state.seenSpeciesIds = unique(species);
  }

  start() {
    this.startTutorial();
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
      this.beginNight(0);
    }
  }

  startNight1() {
    this.beginNight(0);
  }

  beginNight(index) {
    if (index >= this.data.scenarios.length) {
      this.state.phase = PHASES.FINAL;
      return;
    }
    this.state.currentNightIndex = index;
    const scenario = this.currentScenario;
    const stage = index + 1;
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
    this.state.selectedGuestId = fixedGuestIds.find((id) => !stayoverIds.includes(id)) ?? null;
    this.state.serviceTimerMs = null;
    this.state.relocationCount = 0;
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
    if (["hotel", "species", "rank", "discoveries"].includes(tab)) {
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
    this.state.serviceTimerMs = Math.max(0, this.state.serviceTimerMs - RELOCATION_TIME_COST_MS);
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
      this.beginNight(0);
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
    this.state.lastRoomWear = wear;
  }

  completeNight(result) {
    this.state.gold += result.income;
    this.state.hotelReputation += result.reputationDelta;
    this.updateGuestHistoryAndDiscoveries(result);
    this.applyRoomWearAndStays(result);
    this.state.nightResults[this.state.currentNightIndex] = result;
    this.state.serviceTimerMs = null;
    this.state.emergencyReport = result.emergencyReport;
    this.state.phase = PHASES.RESULT;
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
    if (this.currentNightNumber >= this.totalNights) {
      this.state.phase = PHASES.FINAL;
      return true;
    }
    const nextStage = this.currentNightNumber + 1;
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
    this.beginNight(this.state.currentNightIndex + 1);
    return true;
  }

  skipUpgrade() {
    return this.finishUpgrade();
  }

  serviceRoom(roomId) {
    if (this.state.phase !== PHASES.UPGRADE) return false;
    if (Object.values(this.state.stayovers).some((entry) => entry.roomId === roomId)) return false;
    if (this.structuralBoardState().blockedRooms.has(roomId)) return false;
    const cost = this.data.balance?.room_service_cost ?? 8;
    const condition = this.state.roomConditions[roomId];
    if (!condition || this.state.gold < cost) return false;
    if (condition.cleanliness === 100 && condition.durability === 100) return false;
    this.state.gold -= cost;
    this.state.roomConditions[roomId] = { cleanliness: 100, durability: 100 };
    return true;
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
    this.startPlacement();
    return true;
  }

  restart() {
    const nextSeed = (this.state.runSeed + 1) >>> 0;
    this.state = initialState(this.data, nextSeed);
  }
}
