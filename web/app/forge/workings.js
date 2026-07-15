/* Resume or discard stopped single-author workings. */
import { $, closeModal, esc, modal, toast } from "../core/dom.js";
import { FORGE_PHASE_NAMES } from "./bindery.js";


export function showResumeChooser(workings, showForgeModal) {
  const row = (working) => `<div class="tome-row resume-row">
    <button class="resume-pick" data-id="${esc(working.id)}">
      <div class="jr-top"><span class="jr-name">${esc(working.name)}</span>
        <span class="jr-tag num">phase ${working.phase}/8 · ${esc(FORGE_PHASE_NAMES[working.phase] || "")}</span></div>
      <div class="jr-desc dim">${esc(working.concept || "(no concept recorded)")}</div>
      <div class="jr-foot faint">${working.author?.model ? `resume ${esc(working.author.model)}, or choose any other AI` : "choose an AI to continue from disk"}</div>
    </button>
    <button class="resume-trash" data-id="${esc(working.id)}" aria-label="Discard this working" title="Discard this working">🗑</button>
  </div>`;
  modal(`<h2>UNFINISHED WORKINGS</h2>
    <p class="dim" style="font-size:12px;margin:2px 0 12px">Continue with the same AI session when available, or choose another CLI model to read the saved pages and take over.</p>
    <div class="tome-list">${workings.map(row).join("")}</div>`,
    [["START A NEW TOME", "", () => showForgeModal()], ["NOT TODAY", "quiet", null]]);
  const root = $("#modal-root");
  root.querySelectorAll(".resume-pick").forEach((button) => {
    button.onclick = () => {
      const working = workings.find((item) => item.id === button.dataset.id);
      closeModal(() => showForgeModal(working));
    };
  });
  root.querySelectorAll(".resume-trash").forEach((button) => {
    button.onclick = async (event) => {
      event.stopPropagation(); button.disabled = true;
      try {
        const response = await fetch("/api/buildtome/discard", { method: "POST",
          headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: button.dataset.id }) });
        const data = await response.json();
        if (!data.ok) throw new Error(data.error || "discard failed");
        const left = workings.filter((item) => item.id !== button.dataset.id);
        closeModal(() => left.length ? showResumeChooser(left, showForgeModal) : showForgeModal());
      } catch (error) {
        button.disabled = false;
        toast("Could not discard: " + esc(String(error.message || error)), "bad");
      }
    };
  });
}
