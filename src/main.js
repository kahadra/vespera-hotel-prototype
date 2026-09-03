import { loadGameData } from "./data.js";
import { setupInput } from "./input.js";
import {
  renderApp,
  renderFatalError,
  renderModeHub,
} from "./render.js";
import {
  browserHubUrl,
  browserModeUrl,
  desktopHubUrl,
  desktopModeUrl,
  DESKTOP_MODE_OPTIONS,
  isDesktopModeId,
  readDesktopModeSummaries,
} from "./mode-hub.js";
import { readActiveRunSave } from "./save.js";
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

function isDesktopRuntime() {
  return globalThis.vesperaDesktop?.platform === "electron";
}

function runtimeModeUrl(modeId) {
  return isDesktopRuntime()
    ? desktopModeUrl(window.location.href, modeId)
    : browserModeUrl(window.location.href, modeId);
}

function runtimeHubUrl() {
  return isDesktopRuntime()
    ? desktopHubUrl(window.location.href)
    : browserHubUrl(window.location.href);
}

function navigateToMode(modeId) {
  window.location.assign(runtimeModeUrl(modeId));
}

function navigateToModeHub() {
  window.location.replace(runtimeHubUrl());
}

async function bootModeHub(storage) {
  const validatedCheckpoints = new Map(await Promise.all(
    DESKTOP_MODE_OPTIONS.map(async (option) => {
      const data = await loadGameData({ mode: option.id });
      return [option.id, readActiveRunSave(data, storage)];
    }),
  ));
  const modes = readDesktopModeSummaries(storage, validatedCheckpoints);
  renderModeHub(app, modes);
  app.addEventListener("click", (event) => {
    const target = event.target.closest("[data-mode-id]");
    if (!target) return;
    navigateToMode(target.dataset.modeId);
  });
  window.__vesperaModeHub = Object.freeze({
    modes: Object.freeze(modes.map((mode) => Object.freeze({ ...mode }))),
    open: navigateToMode,
  });
}

async function boot() {
  try {
    const params = new URLSearchParams(window.location.search);
    const requestedMode = params.get("mode");
    const requestedScope = params.get("scope");
    const storage = runtimeStorage();
    if (!isDesktopModeId(requestedMode)) {
      await bootModeHub(storage);
      return;
    }
    const data = await loadGameData({ mode: requestedMode, scope: requestedScope });
    const requestedSeed = Number(params.get("seed"));
    const controller = new GameController(data, {
      seed: Number.isFinite(requestedSeed) && requestedSeed > 0 ? requestedSeed : Date.now(),
      storage,
    });
    const rerender = () => renderApp(app, controller);
    setupInput(app, controller, rerender, {
      onReturnToModeHub: navigateToModeHub,
    });
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
