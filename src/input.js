export function setupInput(app, controller, rerender, options = {}) {
  app.addEventListener("change", (event) => {
    const input = event.target.closest("[data-formal-repayment-input]");
    if (!input) return;
    const changed = controller.setFormalCampaignRepayment(Number(input.value));
    if (!changed) input.value = String(controller.state.campaignSelectedRepayment);
    controller.saveCheckpoint();
    const operating = controller.formalCampaignOperatingForecast();
    if (operating) {
      for (const field of [
        "nextUpkeep",
        "cashOnHand",
        "pendingExpense",
        "minimumIncomeRequired",
      ]) {
        const value = app.querySelector(`[data-formal-operating-value="${field}"]`);
        if (value) value.textContent = `${operating[field]}G`;
      }
    }
    const repayment = controller.formalCampaignRepaymentForecast();
    const repaymentCopy = app.querySelector("[data-formal-repayment-forecast]");
    if (repaymentCopy && repayment) {
      repaymentCopy.textContent = ` 다음 허들 ${repayment.nextCheckpointStage}일 · 남은 목표 ${repayment.remainingAmount}G`;
    }
  });

  app.addEventListener("click", (event) => {
    const target = event.target.closest("[data-action], [data-guest-id]");
    if (!target) return;

    const action = target.dataset.action;
    if (action === "return-mode-hub" && options.onReturnToModeHub) {
      options.onReturnToModeHub();
      return;
    }
    if (action === "open-handbook") controller.openHandbook(target.dataset.tab);
    else if (action === "close-handbook") controller.closeHandbook();
    else if (action === "open-reservation-board") controller.openReservationBoard();
    else if (action === "close-reservation-board") controller.closeReservationBoard();
    else if (action === "handbook-tab") controller.selectHandbookTab(target.dataset.tab);
    else if (action === "resume") controller.resumeRun();
    else if (action === "start") controller.start();
    else if (action === "set-player-gender") controller.setPlayerGender(target.dataset.genderId);
    else if (action === "set-secretary-presentation") controller.setSecretaryPresentation(target.dataset.presentationId);
    else if (action === "set-relationship-preset") controller.setRelationshipGenderPreset(target.dataset.presetId);
    else if (action === "set-relationship-role") controller.setRelationshipRolePresentation(target.dataset.roleId, target.dataset.presentationId);
    else if (action === "set-greybox-ending-route") controller.setGreyboxEndingRoute(target.dataset.routeId);
    else if (action === "confirm-new-game") controller.confirmNewGame();
    else if (action === "continue-story") controller.continueStory();
    else if (action === "select-display-relic") controller.selectDisplayRelic(target.dataset.relicId);
    else if (action === "skip-display-relic") controller.skipDisplayRelicOffer();
    else if (action === "skip-tutorial") controller.skipTutorial();
    else if (action === "start-day-business") controller.startDayBusiness();
    else if (action === "start-endless-season") controller.startEndlessSeason();
    else if (action === "advance-endless-season") controller.advanceEndlessSeason();
    else if (action === "close-endless-run") controller.closeEndlessRun();
    else if (action === "finish-night") controller.finishNight();
    else if (action === "continue-result") controller.continueAfterResult();
    else if (action === "retry-stage") controller.retryCurrentStage();
    else if (action === "open-result-review") controller.openResultReview();
    else if (action === "accept-secretary-report") controller.acceptSecretaryReport();
    else if (action === "restart-day-through-secretary") controller.restartDayThroughSecretary();
    else if (action === "buy-upgrade") controller.buyUpgrade(target.dataset.upgradeId);
    else if (action === "select-facility-room") controller.selectFacilityInstallationRoom(target.dataset.roomId);
    else if (action === "confirm-facility-installation") controller.confirmFacilityInstallation();
    else if (action === "cancel-facility-installation") controller.cancelFacilityInstallation();
    else if (action === "finish-upgrade") controller.finishUpgrade();
    else if (action === "skip-upgrade") controller.skipUpgrade();
    else if (action === "service-room") controller.serviceRoom(target.dataset.roomId);
    else if (action === "accept-stayover-cleaning-request") controller.resolveStayoverCleaningRequest(true);
    else if (action === "reject-stayover-cleaning-request") controller.resolveStayoverCleaningRequest(false);
    else if (action === "accept") controller.setApplicantDecision(target.dataset.guestId, "accept");
    else if (action === "reject") controller.setApplicantDecision(target.dataset.guestId, "reject");
    else if (action === "confirm-reservation") controller.confirmReservation();
    else if (action === "restart") controller.restart();
    else if (target.dataset.guestId) {
      controller.selectGuest(target.dataset.guestId);
    }
    controller.saveCheckpoint();
    rerender();
  });

  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      if (controller.state.pendingFacilityInstallation) {
        controller.cancelFacilityInstallation();
        controller.saveCheckpoint();
        rerender();
      } else if (controller.state.reservationBoardOpen) {
        controller.closeReservationBoard();
        rerender();
      } else if (controller.state.handbookOpen) {
        controller.closeHandbook();
        rerender();
      }
    }
  });

  app.addEventListener("dragstart", (event) => {
    const guest = event.target.closest("[data-drag-guest]");
    if (!guest) return;
    event.dataTransfer.setData("text/plain", guest.dataset.dragGuest);
    event.dataTransfer.effectAllowed = "move";
  });

  app.addEventListener("dragover", (event) => {
    if (event.target.closest("[data-room-id], [data-waiting-zone]")) event.preventDefault();
  });

  app.addEventListener("drop", (event) => {
    const guestId = event.dataTransfer.getData("text/plain");
    if (!guestId) return;
    const room = event.target.closest("[data-room-id]");
    const waiting = event.target.closest("[data-waiting-zone]");
    if (room) {
      event.preventDefault();
      controller.placeGuest(guestId, room.dataset.roomId);
      controller.saveCheckpoint();
      rerender();
    } else if (waiting) {
      event.preventDefault();
      controller.unplaceGuest(guestId);
      controller.saveCheckpoint();
      rerender();
    }
  });
}
