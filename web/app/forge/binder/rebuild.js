/* THE DESTRUCTIVE REBUILD — the phase rewind folded away at the bottom of the bench.
   It shares the bench's modal and its picked hand and nothing else: an amendment edits the
   tome that exists, this one throws part of it away and re-runs the authoring pipeline over
   the wreckage. Kept apart so the bench above never has to think about it. */
import { $, toast } from "../../core/dom.js";
import { prepareStateReset, resumeStateSaves } from "../../core/store.js";
import { enhanceSelect } from "../../ui/menu.js";
import { apiFetch } from "../../core/api-client.js";

const CONSEQUENCES = {
  1: "The approved arc and the entire authored tome will be erased. The AI starts again at Concept & arc.",
  2: "The approved arc is kept. The authored tome is replaced by a fresh Phase 2 skeleton.",
  3: "The arc and Phase 2 shell are kept. Every authored section is replaced by fresh Phase 3 placeholders.",
  4: "The arc and sections are kept. Minigames and every later phase are rebuilt.",
  5: "Sections and minigames are kept. Economy, cosmetics, validation, and review are rebuilt.",
  6: "Authored course content and economy are kept. Cosmetics, validation, and review are rebuilt.",
  7: "Authored content is kept. Shipping validation and student review run again, and their completion evidence is cleared.",
  8: "The validated tome is kept. Student review is marked incomplete and runs again against it.",
};

/* root: the bench modal. hand(): the picked provider row, or null. k: the cascade selects. */
export function binderRebuild(root, hand, k) {
  const phaseReset = $("#bd-phase", root), phaseAck = $("#bd-phase-ack", root),
        phaseAckWrap = $("#bd-phase-ack-wrap", root), phaseWarn = $("#bd-phase-warn", root),
        phaseGo = $("#bd-phase-go", root), phaseError = $("#bd-phase-error", root);
  enhanceSelect(phaseReset);
  const syncPhaseReset = () => {
    const phase = Number(phaseReset.value || 0), selected = !!phase;
    phaseWarn.classList.toggle("hidden", !selected);
    phaseAckWrap.classList.toggle("hidden", !selected);
    if (selected) phaseWarn.textContent = `${CONSEQUENCES[phase]} All learner progress, grades, and internal workbench files for this tome are erased. An external project folder is never deleted.`;
    else phaseWarn.textContent = "";
    phaseGo.disabled = !selected || !phaseAck.checked;
    phaseError.classList.add("hidden");
  };
  phaseReset.addEventListener("change", () => { phaseAck.checked = false; syncPhaseReset(); });
  phaseAck.addEventListener("change", syncPhaseReset);
  phaseGo.onclick = async () => {
    const phase = Number(phaseReset.value || 0);
    const provider = hand();
    if (!provider || !k.model.value) {
      toast("Pick the rebuilding AI's <b>model</b> first.", "warn");
      return;
    }
    if (!phase || !phaseAck.checked) return;
    phaseGo.disabled = true; phaseGo.textContent = "RESETTING THE TOME…";
    phaseError.classList.add("hidden");
    await prepareStateReset();
    let resetDone = false;
    try {
      const response = await apiFetch("/api/buildtome/reset", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phase, confirm: "reset-tome-build",
          confirmTome: window.__ACTIVE_TOME }),
      });
      const reset = await response.json();
      if (!response.ok || !reset.ok) throw new Error(reset.error || "the phase reset was refused");
      resetDone = true; phaseGo.textContent = "OPENING THE REBUILD…";
      const author = { kind: provider.kind, model: k.model.value,
        ...(k.eff.value ? { effort: k.eff.value } : {}) };
      try {
        const resumeResponse = await apiFetch("/api/buildtome/resume", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: reset.id, fromPhase: phase, author, bindery: { author } }),
        });
        const resumed = await resumeResponse.json();
        if (!resumeResponse.ok || !resumed.ok) throw new Error(resumed.error || "the rebuild did not start");
        localStorage.setItem("buildJob", resumed.jobId);
        sessionStorage.setItem("openResetBuildJob", resumed.jobId);
      } catch (error) {
        sessionStorage.setItem("phaseResetNotice",
          `The tome was reset to Phase ${phase}, but the AI did not start: ${String(error.message || error)}. It remains under Unfinished Workings.`);
      }
      localStorage.removeItem("activeTome");
      location.reload();
    } catch (error) {
      if (resetDone) {
        sessionStorage.setItem("phaseResetNotice", String(error.message || error));
        localStorage.removeItem("activeTome"); location.reload(); return;
      }
      resumeStateSaves();
      phaseGo.textContent = "RESET AND REBUILD"; syncPhaseReset();
      phaseError.textContent = String(error.message || error);
      phaseError.classList.remove("hidden");
    }
  };
}
