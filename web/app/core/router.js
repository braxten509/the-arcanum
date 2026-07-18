/* Route registry and the one navigation side-effect boundary. */
import { $, sfx } from "./dom.js";
import { getState, save } from "./store.js";

const routes = new Map();
let renderSidebar = () => {};

export function registerRoute(name, renderer) {
  if (routes.has(name)) throw new Error(`duplicate frontend route: ${name}`);
  routes.set(name, renderer);
}

export function registerSidebar(renderer) {
  renderSidebar = renderer;
}

export function go(view, sec = null, lesson = null, pageSound = true) {
  const renderer = routes.get(view);
  if (!renderer) throw new Error(`frontend route is not registered: ${view}`);
  const prior = getState().nav || {};
  const moved = prior.view !== view || prior.sec !== sec || prior.lesson !== lesson;
  getState().nav = { view, sec, lesson };
  save();
  for (const element of document.querySelectorAll(".view")) element.classList.add("hidden");
  $("#parchment").classList.toggle("wide", view === "freestyle" || view === "mastery-lab");
  renderer(sec, lesson);
  renderSidebar();
  $("#main").scrollTop = 0;
  if (moved && pageSound) sfx("page");
}

export function resetRoutesForTest() {
  routes.clear();
  renderSidebar = () => {};
}
