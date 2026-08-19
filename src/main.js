import { loadGameData } from "./data.js";
import { setupInput } from "./input.js";
import { renderApp, renderFatalError } from "./render.js";
import { GameController } from "./state.js";

const app = document.querySelector("#app");

async function boot() {
  try {
    const data = await loadGameData();
    const requestedSeed = Number(new URLSearchParams(window.location.search).get("seed"));
    const controller = new GameController(data, {
      seed: Number.isFinite(requestedSeed) && requestedSeed > 0 ? requestedSeed : Date.now(),
    });
    const rerender = () => renderApp(app, controller);
    setupInput(app, controller, rerender);
    window.__vesperaController = controller;
    rerender();
    let lastTick = performance.now();
    window.setInterval(() => {
      const now = performance.now();
      const elapsed = now - lastTick;
      lastTick = now;
      if (controller.advanceTimer(elapsed)) rerender();
    }, 200);
  } catch (error) {
    console.error(error);
    renderFatalError(app, error);
  }
}

boot();
