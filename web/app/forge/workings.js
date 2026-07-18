/* Resume or discard stopped single-author workings. */
import { $, closeModal, esc, ico, modal, toast } from "../core/dom.js";
import { FORGE_PHASE_NAMES } from "./bindery.js";


export function showResumeChooser(workings, showForgeModal) {
  const row = (working) => `<div class="tome-row resume-row">
    <button class="resume-pick" data-id="${esc(working.id)}">
      <div class="jr-top"><span class="jr-name">${esc(working.name)}</span>
        <span class="jr-tag num">phase ${working.phase}/8 · ${esc(FORGE_PHASE_NAMES[working.phase] || "")}</span></div>
      <div class="jr-desc dim">${esc(working.concept || "(no concept recorded)")}</div>
      <div class="jr-foot faint">${working.author?.model ? `resume ${esc(working.author.model)}, or choose any other AI` : "choose an AI to continue from disk"}</div>
    </button>
    <button class="resume-discard" data-id="${esc(working.id)}" aria-label="Delete draft tome" title="Delete draft tome">${ico("x")}</button>
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
  root.querySelectorAll(".resume-discard").forEach((button) => {
    button.onclick = (event) => {
      event.stopPropagation();
      const working = workings.find((item) => item.id === button.dataset.id);
      if (working) showDiscardConfirm(working, workings, showForgeModal);
    };
  });
}

function showDiscardConfirm(working, workings, showForgeModal) {
  modal(`<h2>DELETE THIS DRAFT TOME?</h2>
    <div class="reset-warning">
      <p><b>Are you sure?</b> This permanently deletes <b>${esc(working.name)}</b> and its saved authoring work.</p>
      <p>A project folder managed in your external editor is never deleted.</p>
    </div>`,
  [["KEEP THIS DRAFT", "quiet", () => showResumeChooser(workings, showForgeModal)],
    ["DELETE DRAFT", "danger", null]], { sticky: true });

  const root = $("#modal-root");
  const discard = $(".modal-actions .btn.danger", root);
  discard.onclick = async () => {
    discard.disabled = true;
    discard.textContent = "DELETING…";
    try {
      const response = await fetch("/api/buildtome/discard", { method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: working.id, confirm: "discard-draft", confirmWorking: working.id }) });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || "discard failed");
      const left = workings.filter((item) => item.id !== working.id);
      closeModal(() => left.length ? showResumeChooser(left, showForgeModal) : showForgeModal());
    } catch (error) {
      discard.disabled = false;
      discard.textContent = "DELETE DRAFT";
      toast("Could not discard: " + esc(String(error.message || error)), "bad");
    }
  };
}
