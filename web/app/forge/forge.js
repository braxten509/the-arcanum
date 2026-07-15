/* Commission one complete tome from one persistent, freely chosen AI author. */
import { $, closeModal, esc, modal, paintRange, toast } from "../core/dom.js";
import { openBuildOverlay } from "./bindery.js";
import { enhanceSelect } from "../ui/menu.js";
import { showResumeChooser } from "./workings.js";

export function forgeEntry() {
  fetch("/api/buildtome/resumable").then((r) => r.json()).then((data) => {
    const workings = data.workings || [];
    workings.length ? showResumeChooser(workings, showForgeModal) : showForgeModal();
  }).catch(() => showForgeModal());
}

function fieldHead(label, help) {
  return `<div class="forge-lbl"><label>${label}</label><button type="button" class="forge-help"
    aria-label="About ${esc(label)}">i<span class="forge-tip">${help}</span></button></div>`;
}

function showForgeModal(resume) {
  modal(`<h2>THE BINDERY</h2>
    <p class="dim forge-intro">One AI holds the quill from the course arc through the final
      student review. You can watch its tools, pause it, and speak into the same session.</p>
    <div class="forge-field"><label for="fg-concept">COURSE CONCEPT</label>
      <textarea id="fg-concept" rows="4" placeholder="What should this teach, and what should the learner build?"></textarea></div>
    <div class="forge-field">${fieldHead("PRIOR KNOWLEDGE", "List only what the learner already knows. The level controls pacing; it never invents prerequisites.")}
      <input id="fg-prior" type="text" placeholder="languages, tools, or none">
      <div class="forge-depth"><input id="fg-prior-level" type="range" min="1" max="10" value="5"><span id="fg-prior-level-val" class="forge-depth-val num">5</span></div></div>
    <div class="forge-field"><label>TOOLING</label><div class="forge-tooling">
      <label class="forge-check"><input id="fg-tool-internal" type="checkbox" checked> Internal <i class="dim">browser workbench</i></label>
      <label class="forge-check"><input id="fg-tool-external" type="checkbox"> External <i class="dim">real tools taught</i></label>
    </div></div>
    <div class="forge-dials">
      <div class="forge-field">${fieldHead("BREADTH", "How much of the topic enters the course.")}<div class="forge-depth"><input id="fg-breadth" type="range" min="1" max="10" value="5"><span id="fg-breadth-val" class="forge-depth-val num">5</span></div></div>
      <div class="forge-field">${fieldHead("LESSON DEPTH", "How far each included mechanism is explained and debugged.")}<div class="forge-depth"><input id="fg-depth" type="range" min="1" max="10" value="5"><span id="fg-depth-val" class="forge-depth-val num">5</span></div></div>
      <div class="forge-field">${fieldHead("MASTERY", "Where the learner finishes: acquainted through expert.")}<div class="forge-depth"><input id="fg-mastery" type="range" min="1" max="5" value="3"><span id="fg-mastery-val" class="forge-depth-val num">3</span></div></div>
    </div>
    <div class="forge-field forge-author-field">${fieldHead("THE AUTHOR", "Choose freely from every installed agent CLI and every model it exposes. Keeping the same provider and model preserves its resumable session. Choosing another on a stopped working starts a fresh session that reads the existing pages.")}
      <div class="forge-ai-row">
        <div class="forge-ai-choice"><select id="fg-author-prov" class="cfg-select" aria-label="Author agent CLI"><option value="">LOADING CLIS…</option></select></div>
        <div class="forge-ai-choice"><select id="fg-author-model" class="cfg-select" aria-label="Author model" disabled><option value="">—</option></select></div>
        <div class="forge-ai-choice"><select id="fg-author-eff" class="cfg-select" aria-label="Author effort" disabled><option value="">DEFAULT</option></select></div>
      </div>
    </div>`, [["NOT TODAY", "quiet", null]], { sticky: true });

  const root = $("#modal-root");
  $(".modal", root).classList.add("forge-modal");
  const concept = $("#fg-concept", root);
  const dials = ["prior-level", "breadth", "depth", "mastery"];
  for (const name of dials) {
    const input = $(`#fg-${name}`, root), value = $(`#fg-${name}-val`, root);
    input.oninput = () => { value.textContent = input.value; paintRange(input); };
  }

  if (resume) {
    concept.value = resume.concept || "";
    const gate = resume.gate || {};
    $("#fg-prior", root).value = gate.prior_knowledge || "";
    $("#fg-tool-internal", root).checked = gate.tooling === "internal" || gate.tooling === "both";
    $("#fg-tool-external", root).checked = gate.tooling === "external" || gate.tooling === "both";
    for (const [name, key] of [["prior-level", "prior_level"], ["breadth", "breadth"],
      ["depth", "depth"], ["mastery", "mastery"]]) {
      const input = $(`#fg-${name}`, root);
      if (gate[key]) input.value = gate[key];
      input.dispatchEvent(new Event("input"));
    }
    [concept, $("#fg-prior", root), $("#fg-prior-level", root),
      $("#fg-tool-internal", root), $("#fg-tool-external", root),
      $("#fg-breadth", root), $("#fg-depth", root), $("#fg-mastery", root)]
      .forEach((input) => { input.disabled = true; input.closest(".forge-field").classList.add("forge-locked"); });
    $("h2", root).insertAdjacentHTML("afterend", `<p class="forge-resume-line">RESUMING
      <b>${esc(resume.name)}</b> · phase ${resume.phase}/8</p>`);
  }

  const prov = $("#fg-author-prov", root), model = $("#fg-author-model", root),
        effort = $("#fg-author-eff", root);
  [prov, model, effort].forEach(enhanceSelect);
  let providers = [];
  const fillEfforts = () => {
    const provider = providers.find((item) => item.id === prov.value);
    const row = provider && (provider.models || []).find((item) => item[0] === model.value);
    const levels = (row && row[3]) || [];
    effort.innerHTML = `<option value="">DEFAULT</option>` + levels.map((level) =>
      `<option value="${esc(level)}">${esc(String(level).toUpperCase())}</option>`).join("");
    effort.disabled = !levels.length;
  };
  const fillModels = () => {
    const provider = providers.find((item) => item.id === prov.value);
    const rows = (provider && provider.models) || [];
    model.innerHTML = rows.map(([id, label, tag]) => `<option value="${esc(id)}">${esc(label)}${tag ? ` · ${esc(tag)}` : ""}</option>`).join("")
      || `<option value="">NO MODELS REPORTED</option>`;
    model.disabled = !rows.length;
    fillEfforts();
    syncBegin();
  };
  prov.onchange = fillModels;
  model.onchange = () => { fillEfforts(); syncBegin(); };

  const begin = document.createElement("button");
  begin.className = "btn";
  begin.textContent = resume ? "CONTINUE THIS SESSION" : "BEGIN THE WORKING";
  begin.disabled = true;
  $(".modal-actions", root).appendChild(begin);
  const syncBegin = () => {
    if (begin.dataset.busy) return;
    begin.disabled = !prov.value || !model.value;
  };

  fetch("/api/models").then((response) => response.json()).then((data) => {
    providers = (data.bindery || []).filter((item) => item.installed !== false && (item.models || []).length);
    prov.innerHTML = providers.map((item) => `<option value="${esc(item.id)}">${esc(item.label)}</option>`).join("")
      || `<option value="">NO AGENT CLI FOUND</option>`;
    const saved = resume?.author || JSON.parse(localStorage.getItem("binderyAuthor") || "null");
    const match = saved && providers.find((item) => item.kind === saved.kind || item.id === saved.prov);
    if (match) prov.value = match.id;
    fillModels();
    if (saved?.model && [...model.options].some((option) => option.value === saved.model)) model.value = saved.model;
    fillEfforts();
    if (saved?.effort && [...effort.options].some((option) => option.value === saved.effort)) effort.value = saved.effort;
    syncBegin();
  }).catch(() => { prov.innerHTML = `<option value="">MODEL CENSUS FAILED</option>`; });

  begin.onclick = async () => {
    const provider = providers.find((item) => item.id === prov.value);
    if (!provider || !model.value) return;
    if (!resume && !concept.value.trim()) { toast("The bindery needs a <b>course concept</b>.", "warn"); return; }
    const internal = $("#fg-tool-internal", root).checked, external = $("#fg-tool-external", root).checked;
    if (!resume && !internal && !external) { toast("Choose at least one <b>tooling</b> mode.", "warn"); return; }
    const author = { kind: provider.kind, model: model.value, ...(effort.value ? { effort: effort.value } : {}) };
    localStorage.setItem("binderyAuthor", JSON.stringify(author));
    const tooling = internal && external ? "both" : external ? "external" : "internal";
    const payload = resume ? { id: resume.id, author, bindery: { author } } : {
      concept: concept.value.trim(), prior_knowledge: $("#fg-prior", root).value.trim(),
      prior_level: $("#fg-prior-level", root).value, breadth: $("#fg-breadth", root).value,
      depth: $("#fg-depth", root).value, mastery: $("#fg-mastery", root).value,
      tooling, author, bindery: { author },
    };
    begin.dataset.busy = "true"; begin.disabled = true; begin.textContent = "OPENING THE SESSION…";
    try {
      const response = await fetch(resume ? "/api/buildtome/resume" : "/api/buildtome", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!data.ok) throw new Error(data.error || "the bindery did not answer");
      localStorage.setItem("buildJob", data.jobId);
      closeModal(() => openBuildOverlay(data.jobId));
    } catch (error) {
      delete begin.dataset.busy; begin.textContent = resume ? "CONTINUE THIS SESSION" : "BEGIN THE WORKING";
      syncBegin(); toast("The session could not begin: " + esc(String(error.message || error)), "bad");
    }
  };
}
