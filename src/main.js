import { loadGameData } from "./data.js";
import { setupInput } from "./input.js";
import { renderApp, renderFatalError } from "./render.js";
import { GameController } from "./state.js";

const app = document.querySelector("#app");

async function boot() {
  try {
    const data = await loadGameData();
    const controller = new GameController(data);
    const rerender = () => renderApp(app, controller);
    setupInput(app, controller, rerender);
    rerender();
  } catch (error) {
    console.error(error);
    renderFatalError(app, error);
  }
}

boot();

