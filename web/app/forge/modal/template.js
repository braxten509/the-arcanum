/* The Bindery launch-form markup, split out of forge.js to keep each file lean. */
import { esc } from "../../core/dom.js";
import { FORGE_PHASE_NAMES } from "../phases.js";
import { fieldHead } from "./helpers.js";

export function forgeModalMarkup(resume, currentPhase) {
  const resumeField = resume ? `<div class="forge-field forge-resume-field">
      <label for="fg-resume-phase">RESUME FROM</label>
      <select id="fg-resume-phase" class="cfg-select" aria-label="Resume or restart phase">
        <option value="">RESUME FROM CURRENT · PHASE ${currentPhase} · ${esc(FORGE_PHASE_NAMES[currentPhase] || "")}</option>
        ${Array.from({ length: currentPhase }, (_, index) => index + 1).map((phase) =>
          `<option value="${phase}">RESTART FROM PHASE ${phase} · ${esc(FORGE_PHASE_NAMES[phase] || "")}</option>`).join("")}
        ${(currentPhase === 3 ? resume.sections || [] : []).map((section) =>
          `<option value="3:${esc(section.id)}">RESTART FROM PHASE 3 · SECTION ${esc(String(section.id).toUpperCase())} · ${esc(section.title || "")}</option>`).join("")}
      </select>
      <label class="forge-resume-ack hidden" id="fg-resume-ack-wrap"><input type="checkbox" id="fg-resume-ack">
        <span id="fg-resume-ack-text">I understand this erases authored work from the selected phase onward.</span></label>
    </div>` : "";
  return `<h2>THE BINDERY</h2>
    <p class="dim forge-intro">Choose who owns the foundational arc, the main construction,
      and the final student review. Phase 1–2 may stay warm together; later validated units start
      fresh while failed units keep their repair session.</p>
    <div class="forge-field"><label for="fg-concept">COURSE CONCEPT</label>
      <textarea id="fg-concept" rows="4" placeholder="What should this teach, and what should the learner build?"></textarea></div>
    <div class="forge-field">${fieldHead("PRIOR KNOWLEDGE (OPTIONAL)", "The slider is the complete starting baseline. Add languages or tools only to account for specific transferable experience; written details never imply nearby skills. Start 1 uses low-density lessons, Start 2 uses moderate density, and Start 3 permits dense related material after prerequisites are secure.")}
      <input id="fg-prior" type="text" placeholder="Optional: languages or tools you already know">
      <div class="forge-depth"><input id="fg-prior-level" type="range" min="1" max="10" value="5" aria-label="Prior knowledge level" aria-describedby="fg-prior-level-summary"><span id="fg-prior-level-val" class="forge-depth-val num">5</span></div>
      <p class="forge-prior-summary" id="fg-prior-level-summary" aria-live="polite" aria-atomic="true"></p></div>
    <div class="forge-field"><label>TOOLING</label><div class="forge-tooling">
      <label class="forge-check"><input id="fg-tool-internal" name="fg-tooling" value="internal" type="radio"> Internal <i class="dim">browser workbench</i></label>
      <label class="forge-check"><input id="fg-tool-external" name="fg-tooling" value="external" type="radio"> External <i class="dim">real tools taught</i></label>
    </div></div>
    <div class="forge-dials">
      <div class="forge-field">${fieldHead("LANGUAGE MASTERY", "How independently and broadly the learner can use the declared implementation language at the end. The project is the cumulative practice and proof vehicle, not the mastery target.")}<div class="forge-depth"><input id="fg-mastery" type="range" min="1" max="5" value="3" aria-label="Language mastery" aria-describedby="fg-mastery-summary"><span id="fg-mastery-val" class="forge-depth-val num">3</span></div><p class="forge-dial-summary" id="fg-mastery-summary" aria-live="polite" aria-atomic="true"></p></div>
      <div class="forge-field">${fieldHead("LESSON DEPTH", "How far each included mechanism is explained and debugged. Language Mastery enforces a minimum floor.")}<div class="forge-depth"><input id="fg-depth" type="range" min="1" max="10" value="7" aria-label="Lesson depth" aria-describedby="fg-depth-summary"><span id="fg-depth-val" class="forge-depth-val num">7</span></div><p class="forge-dial-summary" id="fg-depth-summary"></p></div>
      <div class="forge-field">${fieldHead("PROJECT SCOPE", "How large, complete, and polished the finished project should be. It does not reduce language coverage.")}<div class="forge-depth"><input id="fg-project-scope" type="range" min="1" max="5" value="3" aria-label="Project scope" aria-describedby="fg-project-scope-summary"><span id="fg-project-scope-val" class="forge-depth-val num">3</span></div><p class="forge-dial-summary" id="fg-project-scope-summary" aria-live="polite"></p></div>
      <div class="forge-field">${fieldHead("SECTION HARD STOP", "Pause before another paid Phase 3 repair once a Codex-authored section reaches this API-equivalent cost. Move the slider fully right to disable the cap. Claude-authored sections receive twice the numeric allowance.")}<div class="forge-depth"><input id="fg-section-cost-limit" type="range" min="1" max="10.5" step="0.5" value="2" aria-label="Phase 3 section hard stop" aria-describedby="fg-section-cost-limit-summary"><span id="fg-section-cost-limit-val" class="forge-depth-val forge-cost-depth-val num">$2</span></div><p class="forge-dial-summary" id="fg-section-cost-limit-summary">Per section · Rightmost is no limit · Claude numeric limit is 2×</p></div>
    </div>
    ${resumeField}
    <div class="forge-field forge-author-field">${fieldHead("PHASE AUTHORS", "Choose Claude CLI, Codex CLI, OpenCode Go, or the approved OpenRouter route. Phase 1 and 2 may share one planning session. From Phase 3 onward, every clean phase or section starts a fresh unit session, while validator failures return to the current unit's warm repair session.")}
      <div class="forge-author-route">
        <div class="forge-author-route-label"><b>PHASES 1–2</b><span>ARC + SKELETON</span></div>
        <div class="forge-ai-row">
        <div class="forge-ai-choice"><select id="fg-author-prov" class="cfg-select" aria-label="Author agent CLI"><option value="">LOADING CLIS…</option></select></div>
        <div class="forge-ai-choice"><select id="fg-author-model" class="cfg-select" aria-label="Author model" disabled><option value="">—</option></select></div>
        <div class="forge-ai-choice"><select id="fg-author-eff" class="cfg-select" aria-label="Author effort" disabled><option value="">DEFAULT</option></select></div>
        </div>
      </div>
      <div class="forge-author-route">
        <div class="forge-author-route-label"><b>PHASES 3–7</b><span>BUILD + VALIDATE</span></div>
        <div class="forge-author-route-stack">
          <div class="forge-ai-row">
            <div class="forge-ai-choice"><select id="fg-author-37-prov" class="cfg-select" aria-label="Phases 3 through 7 author agent CLI"><option value="">LOADING CLIS…</option></select></div>
            <div class="forge-ai-choice"><select id="fg-author-37-model" class="cfg-select" aria-label="Phases 3 through 7 author model" disabled><option value="">—</option></select></div>
            <div class="forge-ai-choice"><select id="fg-author-37-eff" class="cfg-select" aria-label="Phases 3 through 7 author effort" disabled><option value="">DEFAULT</option></select></div>
          </div>
          <div class="forge-validator-route">
            <div class="forge-validator-label"><b>VALIDATOR AI</b><span>PHASES 1–2 MANDATORY · SECTIONS: ONE PASS</span>
              <button type="button" class="forge-help" aria-label="About Validator AI"><span class="forge-help-mark" aria-hidden="true">i</span><span class="forge-tip">This read-only AI runs after the Phase 1 and Phase 2 mechanical gates, before either transition. For Phase 3 sections, Single Pass runs one advisory audit — the author gets a single repair turn, then mechanical-only. Single Gate runs that audit too, but its findings must be met: each resubmission the AI verifies only those findings, never new ones, for up to three rounds — after that the section continues as long as the mechanical validator passes. Uncheck both to rely on mechanical checks plus the Phase-8 reviewer. Choose Claude CLI, Codex CLI, OpenCode Go, or the approved OpenRouter route.</span></button>
            </div>
            <div class="forge-ai-row">
              <div class="forge-ai-choice"><select id="fg-validator-prov" class="cfg-select" aria-label="Validator AI provider"><option value="">LOADING AI…</option></select></div>
              <div class="forge-ai-choice"><select id="fg-validator-model" class="cfg-select" aria-label="Validator AI model" disabled><option value="">—</option></select></div>
              <div class="forge-ai-choice"><select id="fg-validator-eff" class="cfg-select" aria-label="Validator AI effort" disabled><option value="">DEFAULT</option></select></div>
            </div>
            <div class="forge-validator-modes">
              <label class="forge-check"><input id="fg-section-ai-pass" type="checkbox"> Single pass <i class="dim">one advisory run, then mechanical-only</i></label>
              <label class="forge-check"><input id="fg-section-ai-gate" type="checkbox"> Single gate <i class="dim">findings must be met; up to 3 verify runs, then mechanical-only</i></label>
            </div>
          </div>
        </div>
      </div>
      <div class="forge-author-route">
        <div class="forge-author-route-label"><b>PHASE 8</b><span>STUDENT REVIEW</span></div>
        <div class="forge-ai-row">
          <div class="forge-ai-choice"><select id="fg-author-8-prov" class="cfg-select" aria-label="Phase 8 author agent CLI"><option value="">LOADING CLIS…</option></select></div>
          <div class="forge-ai-choice"><select id="fg-author-8-model" class="cfg-select" aria-label="Phase 8 author model" disabled><option value="">—</option></select></div>
          <div class="forge-ai-choice"><select id="fg-author-8-eff" class="cfg-select" aria-label="Phase 8 author effort" disabled><option value="">DEFAULT</option></select></div>
        </div>
      </div>
    </div>
    <div class="forge-field forge-reviewer-field">
      <div class="forge-reviewer-head">
        <span class="forge-reviewer-title">REVIEW &amp; PUBLICATION AI</span>
        <button type="button" class="forge-help" aria-label="About the review and publication AI"><span class="forge-help-mark" aria-hidden="true">i</span><span class="forge-tip">Choose Claude CLI, Codex CLI, OpenCode Go, or the approved OpenRouter route. After Phase 8 is clean, this independent AI reads every authored file from beginning to end—no sampling—reviews the entire tome, and fixes anything it sees fit. The harness then repeats strict shipping, every per-section gate, and live-smoke verification. Once all of those pass, a separate read-only survey measures the tome against publisher.md and must sign it off before the build is called done; anything it calls blocking comes back here for repair, up to three times. Turn this off and the tome is built but never judged fit to publish.</span></button>
      </div>
      <label class="forge-reviewer-toggle" for="fg-review-enabled">
        <input id="fg-review-enabled" type="checkbox" aria-controls="fg-review-options">
        <span>ENABLE</span>
      </label>
      <div class="forge-ai-row forge-reviewer-options" id="fg-review-options" aria-hidden="true">
        <div class="forge-ai-choice"><select id="fg-review-prov" class="cfg-select" aria-label="Reviewer agent CLI" disabled><option value="">LOADING CLIS…</option></select></div>
        <div class="forge-ai-choice"><select id="fg-review-model" class="cfg-select" aria-label="Reviewer model" disabled><option value="">—</option></select></div>
        <div class="forge-ai-choice"><select id="fg-review-eff" class="cfg-select" aria-label="Reviewer effort" disabled><option value="">DEFAULT</option></select></div>
      </div>
    </div>`;
}
