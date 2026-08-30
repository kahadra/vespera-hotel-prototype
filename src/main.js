import { loadGameData } from "./data.js";
import { setupInput } from "./input.js";
import { renderApp, renderFatalError } from "./render.js";
import { GameController } from "./state.js";

const app = document.querySelector("#app");

function runtimeStorage() {
  const desktop = globalThis.vesperaDesktop;
  if (!desktop) return globalThis.localStorage;
  if (desktop.platform !== "electron" || desktop.storageReady !== true || !desktop.storage) {
    throw new Error(desktop.storageError ?? "데스크톱 파일 저장소를 초기화하지 못했습니다.");
  }
  return desktop.storage;
}

async function boot() {
  try {
    const params = new URLSearchParams(window.location.search);
    const requestedMode = params.get("mode");
    const data = await loadGameData({ mode: requestedMode });
    const requestedSeed = Number(params.get("seed"));
    const controller = new GameController(data, {
      seed: Number.isFinite(requestedSeed) && requestedSeed > 0 ? requestedSeed : Date.now(),
      storage: runtimeStorage(),
    });
    const rerender = () => renderApp(app, controller);
    setupInput(app, controller, rerender);
    window.__vesperaController = controller;
    window.addEventListener("pagehide", () => controller.saveCheckpoint());
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
