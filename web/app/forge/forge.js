/* THE BINDERY's front door: resume an unfinished working, or commission a new tome. */
import { $, closeModal, esc, modal, paintRange, toast } from "../core/dom.js";
import { FORGE_PHASE_NAMES, openBuildOverlay } from "./bindery.js";
import { enhanceSelect } from "../ui/menu.js";

// "Forge a new tome": if the bindery left any tome mid-forge, offer to resume (or discard)
// one first; otherwise go straight to the bindery.
export function forgeEntry() {
  fetch("/api/buildtome/resumable").then((r) => r.json()).then((d) => {
    const workings = (d && d.workings) || [];
    workings.length ? showResumeChooser(workings) : showForgeModal();
  }).catch(() => showForgeModal());
}

function showResumeChooser(workings) {
  const row = (w) => `
    <div class="tome-row resume-row">
      <button class="resume-pick" data-id="${esc(w.id)}">
        <div class="jr-top"><span class="jr-name">${esc(w.name)}</span>
          <span class="jr-tag num">${w.toolingConflict ? "TOOLING CONFLICT" : `phase ${w.phase} · ${esc(FORGE_PHASE_NAMES[w.phase] || "")}`}</span></div>
        <div class="jr-desc dim">${esc(w.concept || "(no concept recorded)")}</div>
      </button>
      <button class="resume-trash" data-id="${esc(w.id)}" aria-label="Discard this working entirely" title="Discard this working entirely">🗑</button>
    </div>`;
  modal(`<h2>UNFINISHED WORKINGS</h2>
    <p class="dim" style="font-size:12px;margin:2px 0 12px">The bindery left these tomes mid-forge. Resume one to review its models and continue where it stopped, or discard it. Starting a new tome leaves them untouched.</p>
    <div class="tome-list">${workings.map(row).join("")}</div>`,
    [["START A NEW TOME", "", () => showForgeModal()], ["NOT TODAY", "quiet", null]]);
  const root = $("#modal-root");
  root.querySelectorAll(".resume-pick").forEach((b) => {
    b.onclick = () => {
      const w = workings.find((x) => x.id === b.dataset.id);
      closeModal(() => (w.toolingConflict ? showToolingConflictApproval(w) : showForgeModal(w)));
    };
  });
  root.querySelectorAll(".resume-trash").forEach((b) => {
    b.onclick = async (e) => {
      e.stopPropagation();
      b.disabled = true;
      try {
        const res = await fetch("/api/buildtome/discard", { method: "POST",
          headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: b.dataset.id }) });
        const d = await res.json();
        if (!d.ok) throw new Error(d.error || "discard failed");
        const left = workings.filter((x) => x.id !== b.dataset.id);
        closeModal(() => (left.length ? showResumeChooser(left) : showForgeModal()));
      } catch (err) {
        b.disabled = false;
        toast("Could not discard: " + esc(String(err.message || err)), "bad");
      }
    };
  });
}

export function showToolingConflictApproval(working) {
  const current = String(((working.gate || {}).tooling) || "unknown").toLowerCase();
  const required = String(working.requiredTooling || "").toLowerCase();
  const labels = {
    internal: "INTERNAL — every required action stays in the browser",
    external: "EXTERNAL — the complete real-tool workflow is taught",
    both: "BOTH — browser workbenches plus the complete real-tool workflow",
  };
  const reason = working.toolingConflictReason ||
    "The selected Tooling cannot deliver the promised artifact.";
  const proposal = required && labels[required]
    ? `<p>Phase 1 requires <b>${esc(labels[required])}</b>.</p>
       <p>Approve changing Tooling from <b>${esc(current)}</b> to <b>${esc(required)}</b>?
       Approval restarts Phase 1; all other gate answers remain locked.</p>`
    : `<p>Phase 1 did not record one safe replacement mode. This working cannot resume
       until its tooling requirement is made explicit.</p>`;
  const actions = required && labels[required]
    ? [[`APPROVE ${required.toUpperCase()}`, "", () => approveToolingConflict(working, required)],
       ["CANCEL", "quiet", null]]
    : [["CLOSE", "quiet", null]];
  modal(`<h2>TOOLING APPROVAL REQUIRED</h2>
    <p class="dim" style="font-size:12px;margin:2px 0 12px">${esc(reason)}</p>
    ${proposal}`, actions, { sticky: true });
}

async function approveToolingConflict(working, required) {
  const bindery = working.bindery || {};
  const pick = (value) => value && value.prov && value.model
    ? { kind: value.prov, model: value.model, ...(value.eff ? { effort: value.eff } : {}) }
    : null;
  const drafter = pick(bindery.drafter), writer = pick(bindery.writer),
        sections = pick(bindery.sec), reviewer = pick(bindery.reviewer);
  const runners = { ...(working.runners || {}) };
  if (!Object.keys(runners).length) { // compatibility with launch records made before runners were persisted
    if (drafter) runners.default = drafter;
    if (writer) { runners["1"] = writer; runners["4"] = writer; }
    if (sections) runners["3"] = sections;
    if (reviewer) runners["8"] = reviewer;
  }
  try {
    const response = await fetch("/api/buildtome/resume", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: working.id, tooling: required, fromPhase: 1,
        runners, bindery }),
    });
    const data = await response.json();
    if (!data.ok) throw new Error(data.error || "the bindery did not accept the change");
    localStorage.setItem("buildJob", data.jobId);
    openBuildOverlay(data.jobId);
  } catch (err) {
    toast("The Tooling change was not applied: " + esc(String(err.message || err)), "bad");
  }
}

// `resume` (optional) = a working from /api/buildtome/resumable: pre-fills the pickers with
// the models that build used, locks the concept, and continues from where it stopped.
function showForgeModal(resume) {
  // a dial's label + a hover/focus tooltip carrying its guidance, so the modal stays compact
  const fhead = (lbl, tip, up) => `<div class="forge-lbl"><label>${lbl}</label>` +
    `<button type="button" class="forge-help${up ? " forge-help--up" : ""}" aria-label="What this hand does">i<span class="forge-tip">${tip}</span></button></div>`;
  const providersTip = "Providers: Claude / Antigravity / Codex (their own logins), OpenCode CLI (OpenCode Go + FREE models), and Local (your ollama models, run through opencode). Selectable models show researched tome-authoring <b>power X/10</b>; this measures capability, not value. Gray models say <b>(insufficient)</b> when capability, evidence, context, or endpoint reliability falls below the complete-hand bar, and <b>(wasteful)</b> when the model is capable but overpriced for that hand or dominated by a better-value choice. Unsupported, too-low, and wastefully-high effort levels are simply gray. Antigravity carries effort in the model name; Local has no effort switch.";
  modal(`<h2>THE BINDERY<button type="button" class="forge-help" aria-label="How the model pickers work">i<span class="forge-tip">${providersTip}</span></button></h2>
    <p class="dim" style="font-size:12px;margin:2px 0 16px">Describe the course you wish existed. The bindery names it, chooses the tools it needs, then drafts, writes, and reviews the whole tome — it takes a good while, and you may leave and return as it works.</p>
    <div class="forge-field"><label for="fg-concept">COURSE CONCEPT</label>
      <textarea id="fg-concept" rows="4" placeholder="What should this tome teach? What does the student build by the end?"></textarea></div>
    <div class="forge-field">${fhead("PRIOR KNOWLEDGE", "Two signals set where the course STARTS. The <b>box</b> exhaustively lists WHAT the student can already do; nearby skills are not assumed. The <b>slider</b> sets subject experience: <b>1</b> zero · <b>2</b> near zero, with full foundations but less repetition · <b>3</b> beginner · <b>4</b> transfer learner · <b>5</b> generalist · <b>6</b> adjacent experience · <b>7</b> practitioner · <b>8</b> fluent · <b>9</b> advanced · <b>10</b> peer expert. Higher levels may compress only what their boundary explicitly permits; course-specific and uncommon material is still introduced before use.")}
      <input type="text" id="fg-prior" placeholder="what the student can already do (languages / tools)">
      <div class="forge-depth" style="margin-top:8px"><input type="range" id="fg-prior-level" min="1" max="10" step="1" value="5">
        <span class="forge-depth-val num" id="fg-prior-level-val">5</span></div></div>
    <div class="forge-field"><label>TOOLING</label>
      <div class="forge-tooling">
        <label class="forge-check"><input type="checkbox" id="fg-tool-internal" checked> Internal <i class="dim">— in-browser only</i></label>
        <label class="forge-check"><input type="checkbox" id="fg-tool-external"> External <i class="dim">— real tools taught</i></label>
      </div>
      <div class="faint" style="font-size:11px;font-style:italic">both = internal &amp; external tools available; the bindery picks which workbenches run externally</div></div>
    <div class="forge-field">${fhead("BREADTH", "How much of the topic's surface makes the section list — <b>1</b> = the one tight path to the objective · <b>10</b> = the whole territory, side-paths included.")}
      <div class="forge-depth"><input type="range" id="fg-breadth" min="1" max="10" step="1" value="5">
        <span class="forge-depth-val num" id="fg-breadth-val">5</span></div></div>
    <div class="forge-field">${fhead("LESSON DEPTH", "How deep each lesson digs — <b>1</b> = just use it · <b>10</b> = internals, edge cases, why it works.")}
      <div class="forge-depth"><input type="range" id="fg-depth" min="1" max="10" step="1" value="5">
        <span class="forge-depth-val num" id="fg-depth-val">5</span></div></div>
    <div class="forge-field">${fhead("MASTERY", "Where the course ENDS — each tick writes concrete sample objectives into the build plan. <b>1</b> acquainted: read, follow &amp; tweak examples · <b>2</b> functional: everyday basics unaided · <b>3</b> capable: real problems, real choices (recursion, data-structure tradeoffs) · <b>4</b> advanced: idioms &amp; internals · <b>5</b> expert: the deep end.")}
      <div class="forge-depth"><input type="range" id="fg-mastery" min="1" max="5" step="1" value="3">
        <span class="forge-depth-val num" id="fg-mastery-val">3</span></div></div>
    <div class="forge-field fq-wait" id="fg-purse">${fhead("THE PURSE", "Five preconfigured mixes of models, cheapest competent hands on the left, the best mix (no wasted effort) on the right. Tick <b>Configure</b> to unlock the hands below and pick models yourself — the slider's picks stay as a starting point. Untick it and the slider takes over again, overwriting your picks. Tiers that use the claude/codex/antigravity logins leave a hand untouched if that CLI isn't installed.")}
      <div class="forge-quality">
        <label class="forge-check" style="margin:0;flex:0 0 auto"><input type="checkbox" id="fg-configure" disabled> Configure</label>
        <span class="fq-word">CHEAP</span>
        <input type="range" id="fg-quality" min="1" max="5" step="1" value="3" disabled>
        <span class="fq-word">QUALITY</span>
      </div>
      <div class="fq-summary"><b id="fg-quality-name">loading model mix…</b><span id="fg-quality-blurb"></span></div></div>
    <div id="fg-hands">
    <div class="forge-field">${fhead("THE DRAFTER", "The lower-cost hand — lays the scaffold, economy, and cosmetics, then owns the whole-tome validation pass. Mechanical checks help, but the final pass still requires judgment. Both underpowered models and premium flagships that add cost without a useful gain are gray. <b>Effort:</b> use the lowest level that remains selectable; compact models may require high.")}
      <div class="forge-ai-row">
        <select id="fg-drafter-prov" class="cfg-select" style="flex:0 0 auto;width:172px"><option value="">PICK A MODEL</option></select>
        <select id="fg-drafter-model" class="cfg-select" style="flex:1 1 auto;min-width:0" disabled><option value="">—</option></select>
        <select id="fg-drafter-eff" class="cfg-select" style="flex:0 0 auto;width:104px" disabled><option value="">—</option></select>
      </div></div>
    <div class="forge-field">${fhead("THE WRITER", "The planning hand — designs the complete learning arc and authors its minigames. The Sections hand below writes the lessons themselves. A weak arc cannot be repaired mechanically, so spend enough here. <b>Effort:</b> use the lowest selectable level; serious reasoning models begin at medium or high.")}
      <div class="forge-ai-row">
        <select id="fg-writer-prov" class="cfg-select" style="flex:0 0 auto;width:172px"><option value="">PICK A MODEL</option></select>
        <select id="fg-writer-model" class="cfg-select" style="flex:1 1 auto;min-width:0" disabled><option value="">—</option></select>
        <select id="fg-writer-eff" class="cfg-select" style="flex:0 0 auto;width:104px" disabled><option value="">—</option></select>
      </div></div>
    <div class="forge-field">${fhead('THE SECTIONS HAND <span style="font-weight:400;font-style:italic;letter-spacing:0">— phase 3 only</span>', "Sections is the biggest, most cache-heavy and output-heavy phase. It writes all teaching prose, examples, exercises, and cumulative project changes, so premium flagships are gray when a cheaper frontier author meets the same bar. This hand overrides the Writer for phase 3.")}
      <div class="forge-ai-row">
        <select id="fg-sec-prov" class="cfg-select" style="flex:0 0 auto;width:172px"><option value="">PICK A MODEL</option></select>
        <select id="fg-sec-model" class="cfg-select" style="flex:1 1 auto;min-width:0" disabled><option value="">—</option></select>
        <select id="fg-sec-eff" class="cfg-select" style="flex:0 0 auto;width:104px" disabled><option value="">—</option></select>
      </div></div>
    <div class="forge-field">${fhead("THE REVIEWER", "Independent eyes — reads the finished tome cover to cover as a first-time student and fills the gaps (the final review). A model DIFFERENT from the writer here catches what the writer cannot see in its own work. <b>Effort:</b> medium–high — spotting cross-section gaps is genuinely reasoning-work.", true)}
      <div class="forge-ai-row">
        <select id="fg-reviewer-prov" class="cfg-select" style="flex:0 0 auto;width:172px"><option value="">PICK A MODEL</option></select>
        <select id="fg-reviewer-model" class="cfg-select" style="flex:1 1 auto;min-width:0" disabled><option value="">—</option></select>
        <select id="fg-reviewer-eff" class="cfg-select" style="flex:0 0 auto;width:104px" disabled><option value="">—</option></select>
      </div></div>
    </div>`,
    [["NOT TODAY", "quiet", null]], { sticky: true });
  const root = $("#modal-root");
  $(".modal", root).classList.add("forge-modal");   // roomier dialog for the three-box rows
  if (resume) {
    const c = $("#fg-concept", root);
    c.value = resume.concept || ""; c.readOnly = true;   // concept is fixed once a working exists
    // "restart from" picker: defaults to the auto-detected phase, but lets the operator force
    // an earlier one (it re-runs from the pages on disk; at/before phase 3 it re-authors every
    // section — the way to redo a section that failed but got skipped on resume).
    // Default is "continue" (value 0 = no override → server auto-resumes and KEEPS phase-3
    // section progress). Picking an explicit phase forces a redo from there (wipes the done-set
    // at/before phase 3) — so it never re-runs finished sections unless you ask it to.
    const phaseOpts = `<option value="0" selected>continue where it left off (phase ${resume.phase})</option>`
      + FORGE_PHASE_NAMES.map((nm, i) => i >= 1
        ? `<option value="${i}">redo from phase ${i} — ${esc(nm)}</option>` : "").join("");
    $("h2", root).insertAdjacentHTML("afterend",
      `<p class="dim" style="font-size:12px;margin:2px 0 12px">Resuming <b>${esc(resume.name)}</b> — <select id="fg-fromphase" style="display:inline-flex;vertical-align:middle;min-width:190px">${phaseOpts}</select>. Redoing at/before phase 3 re-authors every section. Review or change the models below, then continue.</p>`);
    enhanceSelect($("#fg-fromphase", root));   // themed dropdown, like every other select in the app
  }
  const depth = $("#fg-depth", root), depthVal = $("#fg-depth-val", root);
  depth.oninput = () => { depthVal.textContent = depth.value; };  // --fill is handled globally (paintRange + the live listener)
  const breadth = $("#fg-breadth", root), breadthVal = $("#fg-breadth-val", root);
  breadth.oninput = () => { breadthVal.textContent = breadth.value; };
  const mastery = $("#fg-mastery", root), masteryVal = $("#fg-mastery-val", root);
  mastery.oninput = () => { masteryVal.textContent = mastery.value; };
  const priorLvl = $("#fg-prior-level", root), priorLvlVal = $("#fg-prior-level-val", root);
  priorLvl.oninput = () => { priorLvlVal.textContent = priorLvl.value; };
  if (resume) {
    // Phase 0 already ran: everything the gate consumed (concept → mastery) is fixed.
    // Show the working's real answers, grayed — only the model hands stay live.
    const g = resume.gate || {};
    const prior = $("#fg-prior", root);
    prior.value = g.prior_knowledge || "";
    $("#fg-tool-internal", root).checked = g.tooling === "internal" || g.tooling === "both";
    $("#fg-tool-external", root).checked = g.tooling === "external" || g.tooling === "both";
    const setDial = (el, valEl, v) => {
      if (v && !isNaN(+v)) { el.value = +v; valEl.textContent = el.value; paintRange(el); }
    };
    setDial(priorLvl, priorLvlVal, g.prior_level);
    setDial(breadth, breadthVal, g.breadth);
    setDial(depth, depthVal, g.depth);
    setDial(mastery, masteryVal, g.mastery);
    const lockedGate = [$("#fg-concept", root), prior, priorLvl,
                        $("#fg-tool-internal", root), breadth, depth, mastery];
    for (const el of lockedGate) {
      el.closest(".forge-field").classList.add("forge-locked");
    }
  }
  // Each row is [id,label,tag,efforts,guidance]. Guidance is role-specific, so the same
  // cheap model can remain selectable for the Drafter while appearing insufficient for
  // Reviewer; raw model power remains independent of that role/value judgment.
  const knob = (n, role) => ({ role, prov: $(`#fg-${n}-prov`, root),
    model: $(`#fg-${n}-model`, root), eff: $(`#fg-${n}-eff`, root) });
  const K = { drafter: knob("drafter", "drafter"), writer: knob("writer", "writer"),
    reviewer: knob("reviewer", "reviewer"), sec: knob("sec", "sections") };
  let BINDERY = [];
  // THE PURSE — CHEAP↔QUALITY slider. Tiers come from harness.toml [quality.*] via
  // /api/models; each is a per-phase runner map applied to the hand knobs. Configure
  // unticked → the slider owns the knobs (hands locked); ticked → knobs free, slider held.
  const qual = $("#fg-quality", root), conf = $("#fg-configure", root);
  let QUALITY = [];
  const modelRow = (k) => {
    const p = BINDERY.find((x) => x.id === k.prov.value);
    return p && (p.models || []).find((m) => m[0] === k.model.value);
  };
  // Older, already-running servers return four-column model rows. Treat those
  // rows as usable until the server can be restarted and supply policy data.
  const advised = (row, role) => !!(row && (!row[4] || (row[4].advised && row[4].advised[role])));
  const providerHasAdvised = (provider, role) =>
    !!(provider && (provider.models || []).some((row) => advised(row, role)));
  const providerReason = (provider, role) => {
    const reasons = new Set((provider && provider.models || []).map((row) =>
      row[4] && row[4].reason && row[4].reason[role]).filter(Boolean));
    return reasons.size === 1 ? [...reasons][0] : "no selectable models";
  };
  // Every supported effort remains visible. Only the role/model combinations assessed as
  // useful are selectable; disabled entries need no verbose suffix in the narrow box.
  const fillEffort = (k) => {
    const row = modelRow(k), levels = (row && row[3]) || [];
    const allowed = new Set(row && !row[4]
      ? levels
      : ((row && row[4] && row[4].efforts && row[4].efforts[k.role]) || []));
    k.eff.innerHTML = levels.length ? levels.map((level) =>
      `<option value="${esc(level)}"${allowed.has(level) ? "" : " disabled"}>${esc(level.toUpperCase())}</option>`).join("")
      : `<option value="">—</option>`;
    const first = [...k.eff.options].find((o) => !o.disabled);
    if (first) k.eff.value = first.value;
    k.eff.disabled = !levels.length || !first;
  };
  const fillKnob = (k) => {
    const p = BINDERY.find((x) => x.id === k.prov.value);
    const models = (p && p.models) || [];
    k.model.innerHTML = models.length
      ? models.map((row) => {
        const [v, l, tag] = row, guidance = row[4], ok = advised(row, k.role);
        const power = guidance && Number.isInteger(guidance.power) ? guidance.power : null;
        const reason = guidance && guidance.reason && guidance.reason[k.role];
        const note = ok ? (power == null ? "" : ` · power ${power}/10`)
          : ` (${reason === "wasteful" ? "wasteful" : "insufficient"})`;
        return `<option value="${esc(v)}"${ok ? "" : " disabled"}${tag ? ` data-suffix="— ${esc(tag)}"` : ""}>${esc(l)}${note}</option>`;
      }).join("")
      : `<option value="">${p ? "(no models found)" : "—"}</option>`;
    const first = [...k.model.options].find((o) => !o.disabled);
    if (first) k.model.value = first.value;
    else if (models.length) {
      // A stale saved provider may have no model valid for this hand. Keep every
      // researched choice visible in the DOM, but never present one as selected.
      k.model.insertAdjacentHTML("afterbegin", '<option value="" selected>NO SELECTABLE MODELS</option>');
      k.model.value = "";
    }
    k.model.disabled = !first;
    fillEffort(k);
  };
  for (const k of Object.values(K)) {
    k.prov.addEventListener("change", () => fillKnob(k));
    k.model.addEventListener("change", () => fillEffort(k));
  }
  // Remember the four picks across opens (localStorage). `restoring` suppresses the save
  // while we replay a saved pick, so the intermediate provider-change (which resets model)
  // doesn't clobber it.
  const SAVE_KEY = "binderyRunners";
  let restoring = false;
  const persist = () => {
    if (restoring) return;
    const snap = { quality: qual.value, configure: conf.checked };
    for (const [n, k] of Object.entries(K)) snap[n] = { prov: k.prov.value, model: k.model.value, eff: k.eff.value };
    try { localStorage.setItem(SAVE_KEY, JSON.stringify(snap)); } catch (e) { /* private mode */ }
  };
  const hasEnabled = (sel, v) => [...sel.options].some((o) => o.value === v && !o.disabled);
  const restoreKnob = (k, s) => {
    if (!s || !s.prov || !hasEnabled(k.prov, s.prov)) return;
    k.prov.value = s.prov;
    k.prov.dispatchEvent(new Event("change"));          // → fillKnob repopulates model+eff; buttons repaint
    if (s.model && hasEnabled(k.model, s.model)) { k.model.value = s.model; k.model.dispatchEvent(new Event("change")); }
    if (s.eff && hasEnabled(k.eff, s.eff)) { k.eff.value = s.eff; k.eff.dispatchEvent(new Event("change")); }
  };
  // Apply one tier pick {kind, model, effort} to a knob. A provider that isn't installed
  // (login CLI absent) leaves the knob untouched — tick Configure and fill it by hand.
  const applyPick = (k, p) => {
    if (!p || !hasEnabled(k.prov, p.kind)) return false;
    k.prov.value = p.kind; k.prov.dispatchEvent(new Event("change"));
    if (!hasEnabled(k.model, p.model)) return false;
    k.model.value = p.model; k.model.dispatchEvent(new Event("change"));
    if (p.effort && hasEnabled(k.eff, p.effort)) { k.eff.value = p.effort; k.eff.dispatchEvent(new Event("change")); }
    return !p.effort || k.eff.value === p.effort;
  };
  const paintTier = () => {
    const tier = QUALITY[qual.value - 1];
    $("#fg-quality-name", root).textContent = tier ? `${qual.value} · ${String(tier.label || tier.id).toUpperCase()}` : "";
    $("#fg-quality-blurb", root).textContent = tier ? tier.blurb || "" : "";
  };
  const applyTier = () => {
    const t = QUALITY[qual.value - 1]; if (!t) return;
    const ph = t.phases || {};
    restoring = true;                                  // one persist at the end, not per knob
    applyPick(K.drafter, ph.default);
    applyPick(K.writer, ph["1"]);                      // "1" and "4" share the writer knob
    applyPick(K.reviewer, ph["8"]);
    applyPick(K.sec, ph["3"]);
    paintTier();
    restoring = false; persist();
  };
  const syncPurse = () => {
    qual.disabled = conf.checked;
    $("#fg-hands", root).classList.toggle("fq-locked", !conf.checked && QUALITY.length > 0);
    paintRange(qual);   // programmatic value changes don't fire the delegated input repaint
    paintTier();
    if (!conf.checked && QUALITY.length) applyTier();  // unticking overwrites with the tier
  };
  // While /api/models + the saved picks load, gray every box out and say "Loading…" — an
  // empty "—" box during the async gap reads as broken. Originals restored the instant the
  // fill runs (each select keeps its placeholder options in dataset.orig).
  const pickers = Object.values(K).flatMap((k) => [k.prov, k.model, k.eff]);
  const setLoading = (on) => {
    for (const s of pickers) {
      if (on) {
        if (s.dataset.orig == null) s.dataset.orig = s.innerHTML;
        s.innerHTML = '<option value="">Loading…</option>';
        s.disabled = true;
      } else if (s.dataset.orig != null) {
        s.innerHTML = s.dataset.orig; delete s.dataset.orig; s.disabled = false;
      }
    }
  };
  setLoading(true);
  fetch("/api/models").then((r) => r.json()).then((d) => {
    setLoading(false);   // restore placeholders + re-enable; fillKnob re-disables model/eff as needed
    BINDERY = (d.bindery || []).filter((p) => p.installed !== false);
    for (const k of Object.values(K)) {
      const provOpts = BINDERY.map((p) => {
        const ok = providerHasAdvised(p, k.role);
        return `<option value="${esc(p.id)}"${ok ? "" : " disabled"}>${esc(p.label)}${ok ? "" : ` (${providerReason(p, k.role)})`}</option>`;
      }).join("");
      k.prov.insertAdjacentHTML("beforeend", provOpts);
      fillKnob(k);
    }
    QUALITY = d.quality || [];
    // the purse renders grayed from the first paint (no pop-in); tiers arriving ungray
    // it and snap the slider to the saved tier — no tiers at all hides it entirely
    if (QUALITY.length) { $("#fg-purse", root).classList.remove("fq-wait"); conf.disabled = false; }
    else $("#fg-purse", root).style.display = "none";
    restoring = true;
    // Resume pre-fills from the working's saved models; a fresh forge from the last-used set.
    let saved = resume ? (resume.bindery || {}) : {};
    if (!resume) { try { saved = JSON.parse(localStorage.getItem(SAVE_KEY) || "{}"); } catch (e) { /* ignore */ } }
    // No tiers served → the purse stays hidden and the hands are always free (as before).
    // A resume snapshot from before the purse existed carries no `configure` — treat it as
    // configured so the models the working actually used show, not the slider's picks.
    conf.checked = !QUALITY.length || !!saved.configure || (!!resume && saved.configure === undefined);
    if (saved.quality >= 1 && saved.quality <= QUALITY.length) qual.value = saved.quality;
    if (conf.checked) {   // hand-picked models restore; otherwise the slider re-derives them
      for (const [n, k] of Object.entries(K)) restoreKnob(k, saved[n]);
      // One-time compatibility with the old curated Sections dropdown.
      if (!saved.sec && saved.sections) {
        const provider = BINDERY.find((p) => (p.models || []).some((m) => m[0] === saved.sections));
        if (provider) restoreKnob(K.sec, { prov: provider.id, model: saved.sections });
      }
    }
    restoring = false;
    syncPurse();
    persist();  // scrub any saved provider/model that policy now makes unselectable
    syncBegin();
  }).catch(() => { setLoading(false); syncBegin(); toast("Could not reach the bindery's model list — is the server up?", "bad"); });
  for (const k of Object.values(K)) [k.prov, k.model, k.eff].forEach(enhanceSelect);
  for (const k of Object.values(K)) [k.prov, k.model, k.eff].forEach((s) => s.addEventListener("change", persist));
  qual.addEventListener("input", () => { if (!conf.checked) applyTier(); });
  conf.addEventListener("change", syncPurse);
  const readKnob = (k) => {
    const p = BINDERY.find((x) => x.id === k.prov.value);
    const row = modelRow(k);
    if (!p || !k.model.value || !advised(row, k.role)) return null;
    const o = { kind: p.kind, model: k.model.value };
    const effortOption = [...k.eff.options].find((opt) => opt.value === k.eff.value);
    if ((row[3] || []).length && (!k.eff.value || !effortOption || effortOption.disabled)) return null;
    if (k.eff.value && effortOption && !effortOption.disabled) o.effort = k.eff.value;
    return o;
  };
  const begin = document.createElement("button");
  begin.className = "btn"; begin.textContent = resume ? "CONTINUE THE WORKING" : "BEGIN THE WORKING";
  begin.disabled = true;
  const syncBegin = () => {
    if (begin.dataset.busy === "true") return;
    const ready = Object.values(K).every((k) => readKnob(k));
    begin.disabled = !ready;
    begin.title = ready ? "" : "Choose a selectable model and effort for every hand";
  };
  for (const k of Object.values(K)) {
    [k.prov, k.model, k.eff].forEach((s) => s.addEventListener("change", syncBegin));
  }
  begin.onclick = async () => {
    const concept = $("#fg-concept", root).value.trim();
    if (!resume && !concept) { toast("The bindery needs at least a <b>concept</b>.", "warn"); return; }
    const ti = $("#fg-tool-internal", root).checked, te = $("#fg-tool-external", root).checked;
    if (!resume && !ti && !te) { toast("Pick at least one <b>tooling</b> mode — internal, external, or both.", "warn"); return; }
    const tooling = ti && te ? "both" : te ? "external" : "internal";
    const picks = { drafter: readKnob(K.drafter), writer: readKnob(K.writer),
      sections: readKnob(K.sec), reviewer: readKnob(K.reviewer) };
    const missing = Object.entries(picks).find(([, pick]) => !pick);
    if (missing) { toast(`Pick a selectable <b>${missing[0]}</b> model and effort.`, "warn"); return; }
    begin.dataset.busy = "true"; begin.disabled = true; begin.textContent = "KINDLING THE FORGE...";
    try {
      const runners = {};
      // Four explicit hands: no cheap fallback can silently inherit a harder role.
      runners.default = picks.drafter;
      runners["1"] = picks.writer;
      runners["4"] = picks.writer;
      runners["3"] = picks.sections;
      runners["8"] = picks.reviewer;
      // snapshot the picks so a future resume of this tome can pre-fill them (same shape as
      // the localStorage restore path); the server stores it in the build's launch.json.
      const snap = { quality: qual.value, configure: conf.checked };
      for (const [n, k] of Object.entries(K)) snap[n] = { prov: k.prov.value, model: k.model.value, eff: k.eff.value };
      const fromPhase = resume ? parseInt(($("#fg-fromphase", root) || {}).value || "0", 10) : 0;
      const payload = resume
        ? { id: resume.id, runners, bindery: snap, fromPhase }
        : { concept, prior_knowledge: $("#fg-prior", root).value.trim(), prior_level: priorLvl.value,
            depth: depth.value, breadth: breadth.value, mastery: mastery.value,
            tooling, runners, bindery: snap };
      const r = await fetch(resume ? "/api/buildtome/resume" : "/api/buildtome", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await r.json();
      if (!data.ok) throw new Error(data.error || "the bindery did not answer");
      localStorage.setItem("buildJob", data.jobId);
      closeModal(() => openBuildOverlay(data.jobId));
    } catch (err) {
      delete begin.dataset.busy;
      begin.textContent = resume ? "CONTINUE THE WORKING" : "BEGIN THE WORKING";
      syncBegin();
      toast("The bindery could not begin: " + esc(String(err.message || err)), "bad");
    }
  };
  $(".modal-actions", root).appendChild(begin);
}
