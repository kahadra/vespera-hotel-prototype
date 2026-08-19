import { calculateNightResult } from "./scoring.js";
import { evaluatePlacement } from "./rules.js";

export const PHASES = Object.freeze({
  TITLE: "TITLE",
  NIGHT1_PLACEMENT: "NIGHT1_PLACEMENT",
  NIGHT1_RESULT: "NIGHT1_RESULT",
  FACILITY_SHOP: "FACILITY_SHOP",
  NIGHT2_RESERVATION: "NIGHT2_RESERVATION",
  NIGHT2_PLACEMENT: "NIGHT2_PLACEMENT",
  FINAL_RESULT: "FINAL_RESULT",
});

function initialState() {
  return {
    phase: PHASES.TITLE,
    gold: 0,
    hotelReputation: 0,
    selectedFacilityId: null,
    selectedGuestId: null,
    acceptedGuestIds: [],
    rejectedGuestIds: [],
    applicantDecisions: {},
    placements: {},
    night1Result: null,
    night2Result: null,
    night2Checkpoint: null,
    runSeed: 1,
    handbookOpen: false,
    handbookTab: "hotel",
  };
}

export class GameController {
  constructor(data) {
    this.data = data;
    this.state = initialState();
  }

  get night1() {
    return this.data.indexes.scenarios.NIGHT_1;
  }

  get night2() {
    return this.data.indexes.scenarios.NIGHT_2;
  }

  get currentScenario() {
    return this.state.phase.startsWith("NIGHT1") ? this.night1 : this.night2;
  }

  start() {
    this.state.phase = PHASES.NIGHT1_PLACEMENT;
    this.state.acceptedGuestIds = [...this.night1.fixed_guests];
    this.state.rejectedGuestIds = [];
    this.state.placements = {};
    this.state.selectedGuestId = this.state.acceptedGuestIds[0];
  }

  openHandbook(tab = this.state.handbookTab) {
    this.state.handbookOpen = true;
    this.state.handbookTab = tab;
  }

  closeHandbook() {
    this.state.handbookOpen = false;
  }

  selectHandbookTab(tab) {
    if (["hotel", "species", "rank", "discoveries"].includes(tab)) {
      this.state.handbookTab = tab;
    }
  }

  selectGuest(guestId) {
    if (this.state.acceptedGuestIds.includes(guestId)) {
      this.state.selectedGuestId = guestId;
    }
  }

  placeGuest(guestId, roomId) {
    if (!this.state.acceptedGuestIds.includes(guestId)) return;
    const occupant = Object.entries(this.state.placements).find(([, value]) => value === roomId)?.[0];
    const previousRoom = this.state.placements[guestId];
    if (occupant && occupant !== guestId) {
      if (previousRoom) this.state.placements[occupant] = previousRoom;
      else delete this.state.placements[occupant];
    }
    this.state.placements[guestId] = roomId;
    this.state.selectedGuestId = guestId;
  }

  unplaceGuest(guestId) {
    delete this.state.placements[guestId];
    this.state.selectedGuestId = guestId;
  }

  currentEvaluation() {
    if (![PHASES.NIGHT1_PLACEMENT, PHASES.NIGHT2_PLACEMENT].includes(this.state.phase)) {
      return null;
    }
    return evaluatePlacement(
      this.data,
      this.state.acceptedGuestIds,
      this.state.placements,
      this.state.selectedFacilityId,
    );
  }

  finishNight() {
    const scenario = this.state.phase === PHASES.NIGHT1_PLACEMENT ? this.night1 : this.night2;
    const result = calculateNightResult(
      this.data,
      scenario,
      this.state.acceptedGuestIds,
      this.state.rejectedGuestIds,
      this.state.placements,
      this.state.selectedFacilityId,
    );
    if (!result.valid) return false;

    this.state.gold += result.income;
    this.state.hotelReputation += result.reputationDelta;
    if (this.state.phase === PHASES.NIGHT1_PLACEMENT) {
      this.state.night1Result = result;
      this.state.phase = PHASES.NIGHT1_RESULT;
    } else {
      this.state.night2Result = result;
      this.state.phase = PHASES.FINAL_RESULT;
    }
    return true;
  }

  continueToShop() {
    if (this.state.phase === PHASES.NIGHT1_RESULT) this.state.phase = PHASES.FACILITY_SHOP;
  }

  buyFacility(facilityId) {
    const facility = this.data.indexes.facilities[facilityId];
    if (!facility || this.state.gold < facility.cost) return false;
    this.state.gold -= facility.cost;
    this.state.selectedFacilityId = facilityId;
    this.state.phase = PHASES.NIGHT2_RESERVATION;
    this.state.acceptedGuestIds = [...this.night2.fixed_guests];
    this.state.rejectedGuestIds = [];
    this.state.applicantDecisions = {};
    this.state.placements = {};
    this.state.selectedGuestId = null;
    this.state.night2Checkpoint = {
      gold: this.state.gold,
      hotelReputation: this.state.hotelReputation,
      selectedFacilityId: facilityId,
    };
    return true;
  }

  setApplicantDecision(guestId, decision) {
    if (!this.night2.applicants.includes(guestId)) return;
    if (!["accept", "reject"].includes(decision)) return;
    this.state.applicantDecisions[guestId] = decision;
  }

  reservationSummary() {
    const acceptedApplicants = this.night2.applicants.filter(
      (id) => this.state.applicantDecisions[id] === "accept",
    );
    const rejectedApplicants = this.night2.applicants.filter(
      (id) => this.state.applicantDecisions[id] === "reject",
    );
    const pending = this.night2.applicants.filter(
      (id) => !this.state.applicantDecisions[id],
    );
    const accepted = [...this.night2.fixed_guests, ...acceptedApplicants];
    return {
      accepted,
      rejected: rejectedApplicants,
      pending,
      overCapacity: accepted.length > this.night2.capacity,
    };
  }

  confirmReservation() {
    const summary = this.reservationSummary();
    if (summary.pending.length || summary.overCapacity) return false;
    this.state.acceptedGuestIds = summary.accepted;
    this.state.rejectedGuestIds = summary.rejected;
    this.state.phase = PHASES.NIGHT2_PLACEMENT;
    this.state.placements = {};
    this.state.selectedGuestId = summary.accepted[0] ?? null;
    return true;
  }

  restart() {
    this.state = initialState();
  }

  retryNight2() {
    const checkpoint = this.state.night2Checkpoint;
    if (!checkpoint) return;
    this.state.gold = checkpoint.gold;
    this.state.hotelReputation = checkpoint.hotelReputation;
    this.state.selectedFacilityId = checkpoint.selectedFacilityId;
    this.state.phase = PHASES.NIGHT2_RESERVATION;
    this.state.acceptedGuestIds = [...this.night2.fixed_guests];
    this.state.rejectedGuestIds = [];
    this.state.applicantDecisions = {};
    this.state.placements = {};
    this.state.selectedGuestId = null;
    this.state.night2Result = null;
  }
}
