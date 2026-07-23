/* Commission one complete tome through a persisted, phase-scoped AI author route. */
import { $, closeModal, esc, modal, paintRange, toast } from "../core/dom.js";
import { prepareStateReset, resumeStateSaves } from "../core/store.js";
import { FORGE_PHASE_NAMES } from "./phases.js";
import { enhanceSelect } from "../ui/menu.js";
import { showResumeChooser } from "./workings.js";
import { apiFetch } from "../core/api-client.js";
import { dispatchCommand } from "../core/commands.js";
import { fieldHead, restartPoint } from "./modal/helpers.js";

// Keep the level names aligned with tools/buildlib/workflow/prompts.py PRIOR_LEVELS.
// The slider is the complete baseline; optional text names concrete experience that can
// tailor transfer without implying adjacent skills.
const PRIOR_KNOWLEDGE_LEVELS = {
  1: ["FROM ZERO", "Nothing is skipped. Setup, first run, terminology, syntax, APIs, and tools are taught one concept family at a time with repeated guided practice."],
  2: ["NEAR ZERO", "Nothing is skipped. The same foundations as Level 1 are taught with less repetition and a moderate pace."],
  3: ["BEGINNER", "Nothing is skipped. Foundations are taught from the ground up; closely related ideas may be combined after their prerequisites are secure."],
  4: ["TRANSFER LEARNER", "General transferable concepts are compressed. Optional Prior Knowledge details can tailor the bridge; subject-specific syntax, tooling, APIs, and unfamiliar semantics are still taught."],
  5: ["GENERALIST", "Basic programming workflow and familiar control or data concepts are compressed. The subject's idioms, tools, APIs, and project conventions are still taught."],
  6: ["ADJACENT", "Nearby subject experience is assumed and receives a brief bridge. Optional Prior Knowledge details can tailor it; subject-specific mechanics, differences, and integration are taught directly."],
  7: ["PRACTITIONER", "Routine fundamentals are assumed and not retaught step by step. Course-specific APIs, constraints, failure modes, and project integration remain."],
  8: ["FLUENT", "Common syntax, setup, and routine workflows are compressed to quick checks. Time shifts to integration, uncommon mechanisms, tradeoffs, and failure handling."],
  9: ["ADVANCED", "Introductory and routine implementation is assumed. Lessons concentrate on internals, architecture, edge cases, diagnostics, and difficult tradeoffs."],
  10: ["EXPERT", "Only relevant non-obvious or project-specific material is taught. The course treats you as a peer, while mastery and final-project evidence remain required."],
};
const PROJECT_SCOPE_LEVELS = {
  1: ["MINIMAL PROOF", "A barely functional proof project: one complete workflow and only the pieces needed to demonstrate the course skills."],
  2: ["SMALL SLICE", "A compact prototype with a few connected features and a clear end-to-end workflow."],
  3: ["COMPLETE SMALL PROJECT", "A coherent small project with several integrated features, persistent state where relevant, and a clear completion condition."],
  4: ["SUBSTANTIAL PROJECT", "A substantial project with deeper functionality, robust behavior, testing, polish, and complete delivery."],
  5: ["FULL-FLEDGED PROJECT", "The broadest feasible finished project: multiple developed subsystems, broad coverage, polished behavior, testing, and packaged delivery where supported."],
};
const MASTERY_LEVELS = {
  1: ["ACQUAINTED", "Can explain core language mechanisms and safely modify guided language examples."],
  2: ["FUNCTIONAL", "Can use the language for familiar small tasks and repair simple faults without step-by-step help."],
  3: ["CAPABLE", "Can transfer language concepts to novel real problems, integrate and debug the result, and justify language-level choices independently."],
  4: ["ADVANCED", "Can use the language across unfamiliar variations, important tradeoffs, internals, and power tools with minimal scaffolding."],
  5: ["EXPERT", "Can architect a substantial solution in the language from goals and constraints, validate it, and defend consequential language and design tradeoffs."],
};
const MASTERY_DEPTH_FLOORS = { 1: 3, 2: 5, 3: 7, 4: 8, 5: 9 };

// Saved routes persist kind/model/effort rather than the display-pool id. Match the exact
// model first so the API and CLI pools stay distinct even when catalogs evolve.
export const matchProvider = (pools, saved) => saved && (
  (pools || []).find((item) => item.kind === saved.kind
    && (item.models || []).some((row) => row[0] === saved.model))
  || (pools || []).find((item) => item.kind === saved.kind));

export function forgeEntry() {
  apiFetch("/api/buildtome/resumable").then((r) => r.json()).then((data) => {
    const workings = data.workings || [];
    workings.length ? showResumeChooser(workings, showForgeModal) : showForgeModal();
  }).catch(() => showForgeModal());
}

function showForgeModal(resume) {
  const currentPhase = resume ? Math.max(1, Math.min(8, Number(resume.phase) || 1)) : 0;
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
  modal(`<h2>THE BINDERY</h2>
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
    <div class="forge-field forge-author-field">${fieldHead("PHASE AUTHORS", "Choose Claude CLI or Codex CLI. Phase 1 and 2 may share one planning session. From Phase 3 onward, every clean phase or section starts a fresh unit session, while validator failures return to the current unit's warm repair session.")}
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
            <div class="forge-validator-label"><b>VALIDATOR AI</b><span>MANDATORY · PHASES 1–2 + EVERY SECTION</span>
              <button type="button" class="forge-help" aria-label="About Validator AI">i<span class="forge-tip">This read-only AI runs after the Phase 1 and Phase 2 mechanical gates, before either transition, then audits teaching completeness, learner independence, and prerequisite completeness after every Phase 3 section clears its mechanical gate. Choose Claude CLI or Codex CLI. Each call receives one bounded, line-citable packet and returns typed defects to the current unit's repair session.</span></button>
            </div>
            <div class="forge-ai-row">
              <div class="forge-ai-choice"><select id="fg-validator-prov" class="cfg-select" aria-label="Validator AI provider"><option value="">LOADING AI…</option></select></div>
              <div class="forge-ai-choice"><select id="fg-validator-model" class="cfg-select" aria-label="Validator AI model" disabled><option value="">—</option></select></div>
              <div class="forge-ai-choice"><select id="fg-validator-eff" class="cfg-select" aria-label="Validator AI effort" disabled><option value="">DEFAULT</option></select></div>
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
        <span class="forge-reviewer-title">THOROUGH REVIEWER AI</span>
        <button type="button" class="forge-help" aria-label="About thorough reviewer AI">i<span class="forge-tip">Choose Claude CLI or Codex CLI. After Phase 8 is clean, this independent AI reads every authored file from beginning to end—no sampling—reviews the entire tome, and fixes anything it sees fit. The harness then repeats strict shipping and live-smoke verification.</span></button>
      </div>
      <label class="forge-reviewer-toggle" for="fg-review-enabled">
        <input id="fg-review-enabled" type="checkbox" aria-controls="fg-review-options">
        <span>ENABLE (OPTIONAL)</span>
      </label>
      <div class="forge-ai-row forge-reviewer-options" id="fg-review-options" aria-hidden="true">
        <div class="forge-ai-choice"><select id="fg-review-prov" class="cfg-select" aria-label="Reviewer agent CLI" disabled><option value="">LOADING CLIS…</option></select></div>
        <div class="forge-ai-choice"><select id="fg-review-model" class="cfg-select" aria-label="Reviewer model" disabled><option value="">—</option></select></div>
        <div class="forge-ai-choice"><select id="fg-review-eff" class="cfg-select" aria-label="Reviewer effort" disabled><option value="">DEFAULT</option></select></div>
      </div>
    </div>`, [["NOT TODAY", "quiet", null]], { sticky: true });

  const root = $("#modal-root");
  $(".modal", root).classList.add("forge-modal");
  const concept = $("#fg-concept", root);
  const dials = ["prior-level", "project-scope", "depth", "mastery"];
  for (const name of dials) {
    const input = $(`#fg-${name}`, root), value = $(`#fg-${name}-val`, root);
    input.oninput = () => { value.textContent = input.value; paintRange(input); };
  }
  const sectionCostLimit = $("#fg-section-cost-limit", root);
  const hasResumeCostLimit = Boolean(resume)
    && Object.prototype.hasOwnProperty.call(resume, "sectionCostLimitUsd");
  const savedCostLimit = localStorage.getItem("binderySectionCostLimitUsd");
  const initialCostLimit = hasResumeCostLimit ? resume.sectionCostLimitUsd : savedCostLimit;
  const numericCostLimit = Number(initialCostLimit);
  sectionCostLimit.value = initialCostLimit === null || initialCostLimit === "unlimited"
    ? sectionCostLimit.max
    : Number.isFinite(numericCostLimit) && numericCostLimit >= 1 && numericCostLimit <= 10
      ? String(numericCostLimit) : "2";
  sectionCostLimit.oninput = () => {
    const unlimited = Number(sectionCostLimit.value) >= Number(sectionCostLimit.max);
    $("#fg-section-cost-limit-val", root).textContent = unlimited
      ? "NO LIMIT"
      : `$${Number(sectionCostLimit.value).toFixed(1).replace(/\.0$/, "")}`;
    paintRange(sectionCostLimit);
  };
  sectionCostLimit.dispatchEvent(new Event("input"));
  const scope = $("#fg-project-scope", root), scopeSummary = $("#fg-project-scope-summary", root),
        depth = $("#fg-depth", root), depthSummary = $("#fg-depth-summary", root),
        mastery = $("#fg-mastery", root), priorLevel = $("#fg-prior-level", root),
        masterySummary = $("#fg-mastery-summary", root),
        priorSummary = $("#fg-prior-level-summary", root);
  const basePriorInput = priorLevel.oninput;
  priorLevel.oninput = () => {
    basePriorInput();
    const [title, summary] = PRIOR_KNOWLEDGE_LEVELS[Number(priorLevel.value)];
    priorSummary.innerHTML = `<b>${esc(title)}</b><span>${esc(summary)}</span>`;
  };
  const baseScopeInput = scope.oninput;
  scope.oninput = () => {
    baseScopeInput();
    const [title, summary] = PROJECT_SCOPE_LEVELS[Number(scope.value)];
    scopeSummary.innerHTML = `<b>${esc(title)}</b><span>${esc(summary)}</span>`;
  };
  const baseMasteryInput = mastery.oninput;
  mastery.oninput = () => {
    baseMasteryInput();
    const level = Number(mastery.value);
    const [title, summary] = MASTERY_LEVELS[level];
    masterySummary.innerHTML = `<b>${esc(title)}</b><span>${esc(summary)}</span>`;
    const floor = MASTERY_DEPTH_FLOORS[level];
    if (!resume && Number(depth.value) < floor) depth.value = String(floor);
    if (!resume) depth.min = String(floor);
    depth.dispatchEvent(new Event("input"));
    depthSummary.textContent = `Mastery ${mastery.value} requires depth ${floor}/10 or higher.`;
  };
  priorLevel.dispatchEvent(new Event("input"));
  scope.dispatchEvent(new Event("input"));
  mastery.dispatchEvent(new Event("input"));

  if (resume) {
    concept.value = resume.concept || "";
    const gate = resume.gate || {};
    $("#fg-prior", root).value = gate.prior_knowledge || "";
    $("#fg-tool-internal", root).checked = gate.tooling === "internal" || gate.tooling === "both";
    $("#fg-tool-external", root).checked = gate.tooling === "external";
    const legacyScope = gate.breadth ? String(Math.max(1, Math.min(5,
      Math.ceil(Number(gate.breadth) / 2)))) : "";
    for (const [name, key, fallback] of [["prior-level", "prior_level", ""],
      ["project-scope", "project_scope", legacyScope],
      ["depth", "depth"], ["mastery", "mastery"]]) {
      const input = $(`#fg-${name}`, root);
      if (gate[key] || fallback) input.value = gate[key] || fallback;
      input.dispatchEvent(new Event("input"));
    }
    [concept, $("#fg-prior", root), $("#fg-prior-level", root),
      $("#fg-tool-internal", root), $("#fg-tool-external", root),
      $("#fg-project-scope", root), $("#fg-depth", root), $("#fg-mastery", root)]
      .forEach((input) => { input.disabled = true; input.closest(".forge-field").classList.add("forge-locked"); });
    $("h2", root).insertAdjacentHTML("afterend", `<p class="forge-resume-line">RESUMING
      <b>${esc(resume.name)}</b> · phase ${resume.phase}/8</p>`);
  }

  const prov = $("#fg-author-prov", root), model = $("#fg-author-model", root),
        effort = $("#fg-author-eff", root),
        prov37 = $("#fg-author-37-prov", root), model37 = $("#fg-author-37-model", root),
        effort37 = $("#fg-author-37-eff", root),
        validatorProv = $("#fg-validator-prov", root),
        validatorModel = $("#fg-validator-model", root),
        validatorEffort = $("#fg-validator-eff", root),
        prov8 = $("#fg-author-8-prov", root), model8 = $("#fg-author-8-model", root),
        effort8 = $("#fg-author-8-eff", root),
        reviewEnabled = $("#fg-review-enabled", root),
        reviewProv = $("#fg-review-prov", root), reviewModel = $("#fg-review-model", root),
        reviewEffort = $("#fg-review-eff", root), reviewOptions = $("#fg-review-options", root),
        resumePhase = resume ? $("#fg-resume-phase", root) : null,
        resumeAck = resume ? $("#fg-resume-ack", root) : null,
        resumeAckWrap = resume ? $("#fg-resume-ack-wrap", root) : null;
  const authorPickers = [
    { key: "phase12", prov, model, effort },
    { key: "phase37", prov: prov37, model: model37, effort: effort37 },
    { key: "phase8", prov: prov8, model: model8, effort: effort8 },
  ];
  const validatorPicker = { prov: validatorProv, model: validatorModel,
    effort: validatorEffort };
  const requiredPickers = [...authorPickers, validatorPicker];
  [prov, model, effort, prov37, model37, effort37, prov8, model8, effort8,
    validatorProv, validatorModel, validatorEffort,
    reviewProv, reviewModel, reviewEffort].forEach(enhanceSelect);
  if (resumePhase) enhanceSelect(resumePhase);
  let providers = [], authorProviders = [], validatorProviders = [], reviewerProviders = [];
  const findProvider = (saved, pool = providers) => matchProvider(pool, saved);
  const fillAuthorEfforts = (picker) => {
    const provider = providers.find((item) => item.id === picker.prov.value);
    const row = provider && (provider.models || []).find((item) => item[0] === picker.model.value);
    const levels = (row && row[3]) || [];
    picker.effort.innerHTML = `<option value="">DEFAULT</option>` + levels.map((level) =>
      `<option value="${esc(level)}">${esc(String(level).toUpperCase())}</option>`).join("");
    picker.effort.disabled = !levels.length;
  };
  const fillAuthorModels = (picker) => {
    const provider = providers.find((item) => item.id === picker.prov.value);
    const rows = (provider && provider.models) || [];
    picker.model.innerHTML = rows.map(([id, label, tag]) => `<option value="${esc(id)}">${esc(label)}${tag ? ` · ${esc(tag)}` : ""}</option>`).join("")
      || `<option value="">NO MODELS REPORTED</option>`;
    picker.model.disabled = !rows.length;
    fillAuthorEfforts(picker);
    syncBegin();
  };
  for (const picker of requiredPickers) {
    picker.prov.onchange = () => fillAuthorModels(picker);
    picker.model.onchange = () => { fillAuthorEfforts(picker); syncBegin(); };
  }

  const fillReviewEfforts = () => {
    const provider = providers.find((item) => item.id === reviewProv.value);
    const row = provider && (provider.models || []).find((item) => item[0] === reviewModel.value);
    const levels = (row && row[3]) || [];
    reviewEffort.innerHTML = `<option value="">DEFAULT</option>` + levels.map((level) =>
      `<option value="${esc(level)}">${esc(String(level).toUpperCase())}</option>`).join("");
    reviewEffort.disabled = !reviewEnabled.checked || !levels.length;
  };
  const fillReviewModels = () => {
    const provider = providers.find((item) => item.id === reviewProv.value);
    const rows = (provider && provider.models) || [];
    reviewModel.innerHTML = rows.map(([id, label, tag]) => `<option value="${esc(id)}">${esc(label)}${tag ? ` · ${esc(tag)}` : ""}</option>`).join("")
      || `<option value="">NO MODELS REPORTED</option>`;
    reviewModel.disabled = !reviewEnabled.checked || !rows.length;
    fillReviewEfforts();
    syncBegin();
  };
  const syncReview = () => {
    const enabled = reviewEnabled.checked;
    reviewOptions.classList.toggle("enabled", enabled);
    reviewOptions.setAttribute("aria-hidden", String(!enabled));
    reviewProv.disabled = !enabled || !providers.length;
    reviewModel.disabled = !enabled || !reviewProv.value;
    fillReviewEfforts();
    syncBegin();
  };
  reviewProv.onchange = fillReviewModels;
  reviewModel.onchange = () => { fillReviewEfforts(); syncBegin(); };
  reviewEnabled.onchange = syncReview;

  const begin = document.createElement("button");
  begin.className = "btn";
  begin.textContent = resume ? "CONTINUE THIS SESSION" : "BEGIN THE WORKING";
  begin.disabled = true;
  $(".modal-actions", root).appendChild(begin);
  const beginLabel = () => resumePhase?.value
    ? `RESTART FROM PHASE ${resumePhase.value}`
    : resume ? "CONTINUE THIS SESSION" : "BEGIN THE WORKING";
  const toolingInputs = [$("#fg-tool-internal", root), $("#fg-tool-external", root)];
  const syncBegin = () => {
    if (begin.dataset.busy) return;
    begin.textContent = beginLabel();
    begin.disabled = requiredPickers.some((picker) => !picker.prov.value || !picker.model.value)
      || !toolingInputs.some((input) => input.checked)
      || (reviewEnabled.checked && (!reviewProv.value || !reviewModel.value))
      || !!(resumePhase?.value && !resumeAck?.checked);
  };
  toolingInputs.forEach((input) => input.addEventListener("change", syncBegin));
  const syncResumePoint = () => {
    if (!resumePhase) return;
    const { phase, section } = restartPoint(resumePhase.value);
    resumeAckWrap.classList.toggle("hidden", !phase);
    $("#fg-resume-ack-text", root).textContent = section
      ? `I understand this erases authored work from section ${section.toUpperCase()} onward.`
      : "I understand this erases authored work from the selected phase onward.";
    syncBegin();
  };
  if (resumePhase) {
    resumePhase.addEventListener("change", () => { resumeAck.checked = false; syncResumePoint(); });
    resumeAck.addEventListener("change", syncBegin);
    syncResumePoint();
  }

  apiFetch("/api/models").then((response) => response.json()).then((data) => {
    providers = (data.bindery || []).filter((item) => item.installed !== false && (item.models || []).length);
    const roleProviders = (role) => providers.filter((item) => (item.roles || []).includes(role));
    authorProviders = roleProviders("author");
    validatorProviders = roleProviders("validator");
    reviewerProviders = roleProviders("reviewer");
    const options = (pool, empty) => pool.map((item) =>
      `<option value="${esc(item.id)}">${esc(item.label)}</option>`).join("")
      || `<option value="">${empty}</option>`;
    const authorOptions = options(authorProviders, "NO AUTHOR CLI FOUND");
    for (const picker of authorPickers) picker.prov.innerHTML = authorOptions;
    validatorPicker.prov.innerHTML = options(validatorProviders, "NO VALIDATOR FOUND");
    reviewProv.innerHTML = options(reviewerProviders, "NO REVIEWER CLI FOUND");
    const legacySaved = resume?.author || JSON.parse(localStorage.getItem("binderyAuthor") || "null");
    const storedAuthors = JSON.parse(localStorage.getItem("binderyAuthors") || "null");
    const savedAuthors = resume?.authors && Object.keys(resume.authors).length
      ? resume.authors : storedAuthors || { phase12: legacySaved, phase37: legacySaved, phase8: legacySaved };
    for (const picker of authorPickers) {
      const saved = savedAuthors?.[picker.key] || legacySaved;
      const match = findProvider(saved, authorProviders);
      if (match) picker.prov.value = match.id;
      fillAuthorModels(picker);
      if (saved?.model && [...picker.model.options].some((option) => option.value === saved.model))
        picker.model.value = saved.model;
      fillAuthorEfforts(picker);
      if (saved?.effort && [...picker.effort.options].some((option) => option.value === saved.effort))
        picker.effort.value = saved.effort;
    }
    const storedValidator = JSON.parse(localStorage.getItem("binderyValidator") || "null");
    const solProvider = validatorProviders.find((item) => item.kind === "codex-cli"
      && (item.models || []).some((row) => row[0] === "gpt-5.6-sol"));
    const recommendedValidator = solProvider
      ? { kind: "codex-cli", model: "gpt-5.6-sol", effort: "high" } : null;
    const priorValidator = resume?.validator || storedValidator;
    // Luna@medium was the old automatic default, not a reviewer-qualified choice. Migrate
    // that exact legacy default while preserving deliberate custom model/effort selections.
    const legacyLunaDefault = priorValidator?.kind === "codex-cli"
      && priorValidator.model === "gpt-5.6-luna"
      && priorValidator.effort === "medium";
    const savedValidator = (!legacyLunaDefault && priorValidator) || recommendedValidator
      || savedAuthors?.phase37 || legacySaved;
    const validatorMatch = findProvider(savedValidator, validatorProviders);
    if (validatorMatch) validatorProv.value = validatorMatch.id;
    fillAuthorModels(validatorPicker);
    if (savedValidator?.model && [...validatorModel.options].some((option) =>
      option.value === savedValidator.model)) validatorModel.value = savedValidator.model;
    fillAuthorEfforts(validatorPicker);
    if (savedValidator?.effort && [...validatorEffort.options].some((option) =>
      option.value === savedValidator.effort)) validatorEffort.value = savedValidator.effort;
    const savedReviewer = resume?.reviewer && resume.reviewer.model
      ? resume.reviewer : JSON.parse(localStorage.getItem("binderyReviewer") || "null");
    reviewEnabled.checked = !!(resume?.reviewer && resume.reviewer.model);
    const reviewMatch = findProvider(savedReviewer, reviewerProviders);
    if (reviewMatch) reviewProv.value = reviewMatch.id;
    fillReviewModels();
    if (savedReviewer?.model && [...reviewModel.options].some((option) => option.value === savedReviewer.model)) reviewModel.value = savedReviewer.model;
    fillReviewEfforts();
    if (savedReviewer?.effort && [...reviewEffort.options].some((option) => option.value === savedReviewer.effort)) reviewEffort.value = savedReviewer.effort;
    syncReview();
    syncBegin();
  }).catch(() => {
    for (const picker of requiredPickers)
      picker.prov.innerHTML = `<option value="">MODEL CENSUS FAILED</option>`;
  });

  begin.onclick = async () => {
    if (requiredPickers.some((picker) => !picker.prov.value || !picker.model.value)) return;
    if (!resume && !concept.value.trim()) { toast("The bindery needs a <b>course concept</b>.", "warn"); return; }
    const internal = $("#fg-tool-internal", root).checked, external = $("#fg-tool-external", root).checked;
    if (!resume && !internal && !external) { toast("Choose a <b>tooling</b> mode before continuing.", "warn"); return; }
    const authors = Object.fromEntries(authorPickers.map((picker) => {
      const provider = providers.find((item) => item.id === picker.prov.value);
      return [picker.key, { kind: provider.kind, model: picker.model.value,
        ...(picker.effort.value ? { effort: picker.effort.value } : {}) }];
    }));
    const author = authors.phase12;
    const sectionCostLimitUsd = Number(sectionCostLimit.value) >= Number(sectionCostLimit.max)
      ? null : Number(sectionCostLimit.value);
    localStorage.setItem(
      "binderySectionCostLimitUsd",
      sectionCostLimitUsd === null ? "unlimited" : String(sectionCostLimitUsd));
    localStorage.setItem("binderyAuthors", JSON.stringify(authors));
    localStorage.setItem("binderyAuthor", JSON.stringify(author));
    const validatorProvider = providers.find((item) => item.id === validatorProv.value);
    const validator = { kind: validatorProvider.kind, model: validatorModel.value,
      ...(validatorEffort.value ? { effort: validatorEffort.value } : {}) };
    localStorage.setItem("binderyValidator", JSON.stringify(validator));
    const reviewerProvider = providers.find((item) => item.id === reviewProv.value);
    const reviewer = reviewEnabled.checked && reviewerProvider && reviewModel.value
      ? { kind: reviewerProvider.kind, model: reviewModel.value,
          ...(reviewEffort.value ? { effort: reviewEffort.value } : {}) }
      : null;
    if (reviewer) localStorage.setItem("binderyReviewer", JSON.stringify(reviewer));
    const tooling = external ? "external" : "internal";
    let resumeId = resume?.id;
    const { phase: restartPhase, section: restartSection } = restartPoint(resumePhase?.value);
    let resetPrepared = false, resetDone = false;
    if (resume && restartPhase) {
      if (!resumeAck.checked) return;
      resetPrepared = window.__ACTIVE_TOME === resume.tome;
      if (resetPrepared) await prepareStateReset();
      begin.dataset.busy = "true"; begin.disabled = true; begin.textContent = "RESTORING THE PHASE BOUNDARY…";
      try {
        const resetResponse = await apiFetch(`/api/buildtome/reset?tome=${encodeURIComponent(resume.tome)}`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tome: resume.tome, phase: restartPhase,
            ...(restartSection ? { section: restartSection } : {}),
            confirm: "reset-tome-build", confirmTome: resume.tome }),
        });
        const reset = await resetResponse.json();
        if (!resetResponse.ok || !reset.ok) throw new Error(reset.error || "the phase restart was refused");
        resetDone = true; resumeId = reset.id;
      } catch (error) {
        if (resetPrepared) resumeStateSaves();
        delete begin.dataset.busy; syncBegin();
        toast("The phase could not be restarted: " + esc(String(error.message || error)), "bad");
        return;
      }
    }
    const payload = resume ? { id: resumeId, ...(restartPhase ? { fromPhase: restartPhase } : {}),
      sectionCostLimitUsd, author, authors, validator, reviewer,
      bindery: { author, authors, validator, reviewer } } : {
      concept: concept.value.trim(), prior_knowledge: $("#fg-prior", root).value.trim(),
      prior_level: $("#fg-prior-level", root).value,
      project_scope: $("#fg-project-scope", root).value,
      depth: $("#fg-depth", root).value, mastery: $("#fg-mastery", root).value,
      tooling, sectionCostLimitUsd, author, authors, validator, reviewer,
      bindery: { author, authors, validator, reviewer },
    };
    begin.dataset.busy = "true"; begin.disabled = true; begin.textContent = "OPENING THE SESSION…";
    try {
      const response = await apiFetch(resume ? "/api/buildtome/resume" : "/api/buildtome", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!data.ok) throw new Error(data.error || "the bindery did not answer");
      localStorage.setItem("buildJob", data.jobId);
      if (resetPrepared) {
        sessionStorage.setItem("openResetBuildJob", data.jobId);
        localStorage.removeItem("activeTome");
        location.reload();
        return;
      }
      closeModal(() => dispatchCommand("forge.open-overlay", data.jobId));
    } catch (error) {
      if (resetDone) {
        sessionStorage.setItem("phaseResetNotice",
          `The tome was reset to Phase ${restartPhase}, but the AI did not start: ${String(error.message || error)}. It remains under Unfinished Workings.`);
        location.reload();
        return;
      }
      delete begin.dataset.busy;
      syncBegin(); toast("The session could not begin: " + esc(String(error.message || error)), "bad");
    }
  };
}
