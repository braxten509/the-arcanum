/* Tome shelf and active-build launcher. */
import { $, closeModal, esc, modal } from "../../core/dom.js";
import { activeTome, tomeList } from "../../core/bootstrap.js";
import { apiFetch } from "../../core/api-client.js";
import { forgeEntry } from "../forge.js";

export async function fetchActiveBuilds({ failClosed = false } = {}) {
  try {
    const response = await apiFetch("/api/buildtome/active");
    const builds = (await response.json()).jobs || [];
    return await Promise.all(builds.map(async (build) => {
      try {
        const statusResponse = await apiFetch(
          `/api/buildtome/status?id=${encodeURIComponent(build.id)}`);
        const status = await statusResponse.json();
        return { ...build, ...status, id: build.id };
      } catch {
        return build;
      }
    }));
  } catch (error) {
    if (failClosed) throw error;
    return [];
  }
}

export function showTomePicker(openBuildOverlay) {
  const list = tomeList();
  const active = activeTome();
  const rows = list.filter((tome) => !tome.draft).map((tome) => `
    <button class="tome-row${tome.id === active ? " active" : ""}" data-tome="${esc(tome.id)}"${tome.id === active ? " disabled" : ""}>
      <div class="jr-top"><span class="jr-name">${esc(tome.name || tome.id)}</span><span class="jr-tag num">${esc(tome.runtime || "")}${tome.sectionCount != null ? ` · ${tome.sectionCount} chapters` : ""}</span></div>
      <div class="jr-desc dim">${esc(tome.description || "")}</div><div class="jr-foot faint">${esc(tome.author || "")}</div>
    </button>`).join("");
  modal(`<h2>THE SHELF OF TOMES</h2><p class="dim shelf-intro">Choose a tome, or open a live author session.</p>
    <div class="tome-list"><button class="tome-row forge checking" id="tome-forge" disabled aria-busy="true">
      <div class="jr-top"><span class="jr-name">＋ FORGE A NEW TOME</span><span class="jr-tag num" id="tome-forge-state">checking bindery</span></div>
      <div class="jr-desc dim" id="tome-forge-note">Checking whether another tome is currently being forged.</div>
    </button><div id="forge-active" style="display:contents"></div>${rows || '<p class="dim">The shelf is bare.</p>'}</div>`,
  [["LEAVE THE SHELF", "quiet", null]]);
  const forgeButton = $("#tome-forge");
  const forgeState = $("#tome-forge-state");
  const forgeNote = $("#tome-forge-note");
  const activeSlot = $("#forge-active");
  forgeButton.onclick = () => {
    if (!forgeButton.disabled) closeModal(forgeEntry);
  };
  document.querySelectorAll(
    "#modal-root .tome-row[data-tome]").forEach((button) => {
      button.onclick = () => {
        localStorage.setItem("activeTome", button.dataset.tome);
        location.reload();
      };
    });
  const refreshActiveBuilds = async () => {
    if (!forgeButton.isConnected) return;
    try {
      const builds = await fetchActiveBuilds({ failClosed: true });
      if (!forgeButton.isConnected) return;
      const busy = builds.length > 0;
      forgeButton.disabled = busy;
      forgeButton.classList.toggle("busy", busy);
      forgeButton.classList.remove("checking");
      forgeButton.setAttribute("aria-busy", "false");
      forgeState.textContent = busy ? "author busy" : "single author";
      forgeNote.textContent = busy
        ? "Finish or abandon the current working before forging another tome."
        : "Route the key phase ranges to chosen AIs, watch their tools, and guide the working.";
      activeSlot.innerHTML = builds.map((build) => `
        <button class="tome-row forging" data-job="${esc(build.id)}" data-trace="${esc(build.traceId || build.id)}" data-state="${esc(build.interactionState || "running")}">
          <div class="jr-top"><span class="jr-name">${esc(build.name || "Untitled")}</span><span class="jr-tag num">${esc(build.interactionState || "authoring")}</span></div>
          <div class="jr-desc">Phase ${build.phase || 1} / 8 — ${esc(build.phaseTitle || "starting")}</div>
        </button>`).join("");
      activeSlot.querySelectorAll("[data-job]").forEach((button) => {
        button.onclick = () => closeModal(
          () => openBuildOverlay(button.dataset.job, button.dataset.trace));
      });
    } catch {
      if (!forgeButton.isConnected) return;
      forgeButton.disabled = true;
      forgeButton.classList.add("checking");
      forgeButton.setAttribute("aria-busy", "true");
      forgeState.textContent = "status unavailable";
      forgeNote.textContent =
        "The bindery must confirm no tome is active before starting another.";
    }
    if (forgeButton.isConnected) setTimeout(refreshActiveBuilds, 3000);
  };
  refreshActiveBuilds();
}
