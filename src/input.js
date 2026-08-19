export function setupInput(app, controller, rerender) {
  app.addEventListener("click", (event) => {
    const target = event.target.closest("[data-action], [data-guest-id], [data-room-id]");
    if (!target) return;

    const action = target.dataset.action;
    if (action === "open-handbook") controller.openHandbook();
    else if (action === "close-handbook") controller.closeHandbook();
    else if (action === "handbook-tab") controller.selectHandbookTab(target.dataset.tab);
    else if (action === "start") controller.start();
    else if (action === "skip-tutorial") controller.skipTutorial();
    else if (action === "finish-night") controller.finishNight();
    else if (action === "continue-shop") controller.continueToShop();
    else if (action === "buy-facility") controller.buyFacility(target.dataset.facilityId);
    else if (action === "accept") controller.setApplicantDecision(target.dataset.guestId, "accept");
    else if (action === "reject") controller.setApplicantDecision(target.dataset.guestId, "reject");
    else if (action === "confirm-reservation") controller.confirmReservation();
    else if (action === "restart") controller.restart();
    else if (action === "retry-night2") controller.retryNight2();
    else if (action === "unplace") controller.unplaceGuest(target.dataset.guestId);
    else if (target.dataset.guestId) {
      const room = target.closest("[data-room-id]");
      const selected = controller.state.selectedGuestId;
      if (room && selected && selected !== target.dataset.guestId) {
        controller.placeGuest(selected, room.dataset.roomId);
      } else {
        controller.selectGuest(target.dataset.guestId);
      }
    }
    else if (target.dataset.roomId && controller.state.selectedGuestId) {
      controller.placeGuest(controller.state.selectedGuestId, target.dataset.roomId);
    }
    rerender();
  });

  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && controller.state.handbookOpen) {
      controller.closeHandbook();
      rerender();
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
      rerender();
    } else if (waiting) {
      event.preventDefault();
      controller.unplaceGuest(guestId);
      rerender();
    }
  });
}
