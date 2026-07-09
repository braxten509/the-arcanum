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
          <span class="jr-tag num">phase ${w.phase} · ${esc(FORGE_PHASE_NAMES[w.phase] || "")}</span></div>
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
      closeModal(() => showForgeModal(w));
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

// `resume` (optional) = a working from /api/buildtome/resumable: pre-fills the pickers with
// the models that build used, locks the concept, and continues from where it stopped.
function showForgeModal(resume) {
  // a dial's label + a hover/focus tooltip carrying its guidance, so the modal stays compact
  const fhead = (lbl, tip, up) => `<div class="forge-lbl"><label>${lbl}</label>` +
    `<button type="button" class="forge-help${up ? " forge-help--up" : ""}" aria-label="What this hand does">i<span class="forge-tip">${tip}</span></button></div>`;
  const providersTip = "Providers: Claude / Antigravity / Codex (their own logins), OpenCode CLI (OpenCode Go + FREE models), and Local (your ollama models, run through opencode). The EFFORT box appears only when the chosen model supports one — Claude/Codex on every model, OpenCode per model (only some Go/free models have a variant), Antigravity and Local none.";
  modal(`<h2>THE BINDERY<button type="button" class="forge-help" aria-label="How the model pickers work">i<span class="forge-tip">${providersTip}</span></button></h2>
    <p class="dim" style="font-size:12px;margin:2px 0 16px">Describe the course you wish existed. The bindery names it, chooses the tools it needs, then drafts, writes, and reviews the whole tome — it takes a good while, and you may leave and return as it works.</p>
    <div class="forge-field"><label for="fg-concept">COURSE CONCEPT</label>
      <textarea id="fg-concept" rows="4" placeholder="What should this tome teach? What does the student build by the end?"></textarea></div>
    <div class="forge-field">${fhead("PRIOR KNOWLEDGE", "Two signals for where the course STARTS. The <b>box</b> names WHAT the student already knows (languages / tools). The <b>slider</b> sets HOW MUCH they know about THIS course's subject — where teaching begins: <b>1</b> = absolute zero, so the course's own language/tool is taught from scratch as its own early chapters (nothing assumed, not even the language) · <b>5</b> = knows programming generally but not this exact stack — a brisk language/tooling primer, then the domain · <b>10</b> = already expert in this subject, so skip every fundamental and teach only the sharp edge. When unsure, aim LOW — a skipped fundamental (the language itself) is the worst gap a course can have.")}
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
      </div></div>
    <div id="fg-hands">
    <div class="forge-field">${fhead("THE DRAFTER", "The cheap hand — lays the scaffold: the skeleton, the economy, the cosmetics &amp; the validation pass. The checker guards its work, so spend little here. <b>Effort:</b> low — mechanical scaffolding the validator already guards; high is wasted here.")}
      <div class="forge-ai-row">
        <select id="fg-drafter-prov" class="cfg-select" style="flex:0 0 auto;width:172px"><option value="">PICK A MODEL</option></select>
        <select id="fg-drafter-model" class="cfg-select" style="flex:1 1 auto;min-width:0" disabled><option value="">—</option></select>
        <select id="fg-drafter-eff" class="cfg-select" style="flex:0 0 auto;width:104px" disabled><option value="">—</option></select>
      </div></div>
    <div class="forge-field">${fhead("THE WRITER", "The costly hand — writes what actually teaches: the arc, the lessons &amp; the minigames. This is where the tome lives or dies, so spend here. <b>Effort:</b> medium is the sweet spot for authoring; go high only to make the concept/arc pass reason harder. Low risks shallow lessons and validator retries.")}
      <div class="forge-ai-row">
        <select id="fg-writer-prov" class="cfg-select" style="flex:0 0 auto;width:172px"><option value="">DRAFTER MODEL</option></select>
        <select id="fg-writer-model" class="cfg-select" style="flex:1 1 auto;min-width:0" disabled><option value="">—</option></select>
        <select id="fg-writer-eff" class="cfg-select" style="flex:0 0 auto;width:104px" disabled><option value="">—</option></select>
      </div></div>
    <div class="forge-field">${fhead('THE SECTIONS HAND <span style="font-weight:400;font-style:italic;letter-spacing:0">— phase 3 only</span>', "Sections is the biggest, most cache-heavy phase. <b>Off:</b> a curated shortlist vetted for quality + cheap cache reads. <b>Split by section:</b> each section gets its own worker so context never piles up — pick ANY model without the cache blow-up (a whole-tome reconcile pass still runs at the end for consistency). Overrides the writer for phase 3 only. <b>Effort:</b> medium — bulk authoring; high mostly buys slow think-time, low risks validator retries.")}
      <label class="forge-split-toggle"><input type="checkbox" id="fg-split"> split by section</label>
      <div class="forge-ai-row" id="fg-sec-curated">
        <select id="fg-sections" class="cfg-select" style="flex:1 1 auto;min-width:0"><option value="">WRITER MODEL</option></select>
      </div>
      <div class="forge-ai-row" id="fg-sec-any" style="display:none">
        <select id="fg-sec-prov" class="cfg-select" style="flex:0 0 auto;width:172px"><option value="">PICK A MODEL</option></select>
        <select id="fg-sec-model" class="cfg-select" style="flex:1 1 auto;min-width:0" disabled><option value="">—</option></select>
        <select id="fg-sec-eff" class="cfg-select" style="flex:0 0 auto;width:104px" disabled><option value="">—</option></select>
      </div></div>
    <div class="forge-field">${fhead("THE REVIEWER", "Independent eyes — reads the finished tome cover to cover as a first-time student and fills the gaps (the final review). A model DIFFERENT from the writer here catches what the writer cannot see in its own work. <b>Effort:</b> medium–high — spotting cross-section gaps is genuinely reasoning-work.", true)}
      <div class="forge-ai-row">
        <select id="fg-reviewer-prov" class="cfg-select" style="flex:0 0 auto;width:172px"><option value="">WRITER MODEL</option></select>
        <select id="fg-reviewer-model" class="cfg-select" style="flex:1 1 auto;min-width:0" disabled><option value="">—</option></select>
        <select id="fg-reviewer-eff" class="cfg-select" style="flex:0 0 auto;width:104px" disabled><option value="">—</option></select>
      </div></div>
    </div>`,
    [["NOT TODAY", "quiet", null]]);
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
    for (const el of [$("#fg-concept", root), prior, priorLvl, $("#fg-tool-internal", root),
                      breadth, depth, mastery]) {
      el.closest(".forge-field").classList.add("forge-locked");
    }
  }
  // Each knob is a [PROVIDER][MODEL][EFFORT] cascade fed by /api/models `bindery`
  // ([{id,label,kind,models:[[id,label,tag],…],efforts,installed}]). Pick a provider, its
  // models fill the middle box; the effort box enables only for providers that take one
  // (claude, codex). enhanceSelect's MutationObserver repaints the styled control when we
  // rewrite <option>s on provider change, so re-enhancing isn't needed.
  const knob = (n) => ({ prov: $(`#fg-${n}-prov`, root), model: $(`#fg-${n}-model`, root), eff: $(`#fg-${n}-eff`, root) });
  const K = { drafter: knob("drafter"), writer: knob("writer"), reviewer: knob("reviewer"), sec: knob("sec") };
  let BINDERY = [];
  // Phase 3 (Sections) is the biggest, most cache-heavy phase, so its dial offers only a
  // curated shortlist — strong authoring models with cheap cache reads (per the GLM cost
  // post-mortem). All opencode-go, so one kind; filtered to those actually served. [id, label, note]
  const PHASE3_RECOMMENDED = [
    ["opencode-go/deepseek-v4-pro", "DeepSeek V4 Pro", "best value · cache ≈ free · pro tier"],
    ["opencode-go/qwen3.7-plus",    "Qwen3.7 Plus",    "strong · low cost"],
    ["opencode-go/minimax-m3",      "MiniMax M3",      "capable · low cost"],
    ["opencode-go/kimi-k2.6",       "Kimi K2.6",       "strong coder · mid cost"],
    ["opencode-go/glm-5.2",         "GLM 5.2",         "high quality · pricey cache"],
  ];
  const secSel = $("#fg-sections", root);
  // THE PURSE — CHEAP↔QUALITY slider. Tiers come from harness.toml [quality.*] via
  // /api/models; each is a per-phase runner map applied to the hand knobs. Configure
  // unticked → the slider owns the knobs (hands locked); ticked → knobs free, slider held.
  const qual = $("#fg-quality", root), conf = $("#fg-configure", root);
  let QUALITY = [];
  // Effort is PER-MODEL (row is [id,label,tag,efforts]): some OpenCode models expose a
  // reasoning variant, most don't; claude/codex expose their CLI's levels on every model.
  // So the effort box follows the selected MODEL, not the provider.
  const fillEffort = (k) => {
    const p = BINDERY.find((x) => x.id === k.prov.value);
    const m = p && (p.models || []).find((mm) => mm[0] === k.model.value);
    const levels = (m && m[3]) || [];
    k.eff.innerHTML = levels.length
      ? `<option value="">DEFAULT</option>` + levels.map((l) => `<option value="${esc(l)}">${esc(l.toUpperCase())}</option>`).join("")
      : `<option value="">—</option>`;
    k.eff.disabled = !levels.length;
  };
  const fillKnob = (k) => {
    const p = BINDERY.find((x) => x.id === k.prov.value);
    const models = (p && p.models) || [];
    k.model.innerHTML = models.length
      ? models.map(([v, l, tag]) => `<option value="${esc(v)}"${tag ? ` data-suffix="— ${esc(tag)}"` : ""}>${esc(l)}</option>`).join("")
      : `<option value="">${p ? "(no models found)" : "—"}</option>`;
    k.model.disabled = !models.length;
    fillEffort(k);   // effort follows the now-selected (first) model
  };
  for (const k of Object.values(K)) {
    k.prov.addEventListener("change", () => fillKnob(k));
    k.model.addEventListener("change", () => fillEffort(k));
  }
  // Remember the three picks across opens (localStorage). `restoring` suppresses the save
  // while we replay a saved pick, so the intermediate provider-change (which resets model)
  // doesn't clobber it.
  const SAVE_KEY = "binderyRunners";
  let restoring = false;
  const persist = () => {
    if (restoring) return;
    const snap = { sections: secSel.value, split: $("#fg-split", root).checked,
                   quality: qual.value, configure: conf.checked };
    for (const [n, k] of Object.entries(K)) snap[n] = { prov: k.prov.value, model: k.model.value, eff: k.eff.value };
    try { localStorage.setItem(SAVE_KEY, JSON.stringify(snap)); } catch (e) { /* private mode */ }
  };
  const has = (sel, v) => [...sel.options].some((o) => o.value === v);
  const restoreKnob = (k, s) => {
    if (!s || !s.prov || !has(k.prov, s.prov)) return;
    k.prov.value = s.prov;
    k.prov.dispatchEvent(new Event("change"));          // → fillKnob repopulates model+eff; buttons repaint
    if (s.model && has(k.model, s.model)) { k.model.value = s.model; k.model.dispatchEvent(new Event("change")); }
    if (s.eff && has(k.eff, s.eff)) { k.eff.value = s.eff; k.eff.dispatchEvent(new Event("change")); }
  };
  // Apply one tier pick {kind, model, effort} to a knob. A provider that isn't installed
  // (login CLI absent) leaves the knob untouched — tick Configure and fill it by hand.
  const applyPick = (k, p) => {
    if (!p || !has(k.prov, p.kind)) return;
    k.prov.value = p.kind; k.prov.dispatchEvent(new Event("change"));
    if (has(k.model, p.model)) { k.model.value = p.model; k.model.dispatchEvent(new Event("change")); }
    if (p.effort && has(k.eff, p.effort)) { k.eff.value = p.effort; k.eff.dispatchEvent(new Event("change")); }
  };
  const applyTier = () => {
    const t = QUALITY[qual.value - 1]; if (!t) return;
    const ph = t.phases || {};
    restoring = true;                                  // one persist at the end, not per knob
    applyPick(K.drafter, ph.default);
    applyPick(K.writer, ph["1"]);                      // "1" and "4" share the writer knob
    applyPick(K.reviewer, ph["8"]);
    $("#fg-split", root).checked = !!t.split; toggleSplit();
    if (t.split) applyPick(K.sec, ph["3"]);
    else if (ph["3"] && has(secSel, ph["3"].model)) { secSel.value = ph["3"].model; secSel.dispatchEvent(new Event("change")); }
    restoring = false; persist();
  };
  const syncPurse = () => {
    qual.disabled = conf.checked;
    $("#fg-hands", root).classList.toggle("fq-locked", !conf.checked && QUALITY.length > 0);
    paintRange(qual);   // programmatic value changes don't fire the delegated input repaint
    if (!conf.checked && QUALITY.length) applyTier();  // unticking overwrites with the tier
  };
  // While /api/models + the saved picks load, gray every box out and say "Loading…" — an
  // empty "—" box during the async gap reads as broken. Originals restored the instant the
  // fill runs (each select keeps its placeholder options in dataset.orig).
  const pickers = [secSel, ...Object.values(K).flatMap((k) => [k.prov, k.model, k.eff])];
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
    const provOpts = BINDERY.map((p) => `<option value="${esc(p.id)}">${esc(p.label)}</option>`).join("");
    for (const k of Object.values(K)) { k.prov.insertAdjacentHTML("beforeend", provOpts); fillKnob(k); }
    // Sections dial: only the recommended models opencode actually serves right now.
    const oc = BINDERY.find((p) => p.kind === "opencode-cli");
    const served = new Set((oc ? oc.models : []).map((m) => m[0]));
    secSel.insertAdjacentHTML("beforeend", PHASE3_RECOMMENDED
      .filter(([id]) => served.has(id))
      .map(([id, label, note]) => `<option value="${esc(id)}">${esc(label)} — ${esc(note)}</option>`).join(""));
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
      if (saved.sections && [...secSel.options].some((o) => o.value === saved.sections)) {
        secSel.value = saved.sections; secSel.dispatchEvent(new Event("change"));
      }
      if (saved.split) { $("#fg-split", root).checked = true; toggleSplit(); }
    }
    restoring = false;
    syncPurse();
  }).catch(() => { setLoading(false); toast("Could not reach the bindery's model list — is the server up?", "bad"); });
  for (const k of Object.values(K)) [k.prov, k.model, k.eff].forEach(enhanceSelect);
  for (const k of Object.values(K)) [k.prov, k.model, k.eff].forEach((s) => s.addEventListener("change", persist));
  enhanceSelect(secSel); secSel.addEventListener("change", persist);
  // Split-by-section toggle: off → curated shortlist; on → full any-model cascade.
  const splitBox = $("#fg-split", root);
  const toggleSplit = () => {
    const on = splitBox.checked;
    $("#fg-sec-curated", root).style.display = on ? "none" : "";
    $("#fg-sec-any", root).style.display = on ? "" : "none";
  };
  splitBox.addEventListener("change", () => { toggleSplit(); persist(); });
  toggleSplit();
  qual.addEventListener("input", () => { if (!conf.checked) applyTier(); });
  conf.addEventListener("change", syncPurse);
  const readKnob = (k) => {
    const p = BINDERY.find((x) => x.id === k.prov.value);
    if (!p || !k.model.value) return null;
    const o = { kind: p.kind, model: k.model.value };
    if (k.eff.value) o.effort = k.eff.value;
    return o;
  };
  const begin = document.createElement("button");
  begin.className = "btn"; begin.textContent = resume ? "CONTINUE THE WORKING" : "BEGIN THE WORKING";
  begin.onclick = async () => {
    const concept = $("#fg-concept", root).value.trim();
    if (!resume && !concept) { toast("The bindery needs at least a <b>concept</b>.", "warn"); return; }
    const ti = $("#fg-tool-internal", root).checked, te = $("#fg-tool-external", root).checked;
    if (!resume && !ti && !te) { toast("Pick at least one <b>tooling</b> mode — internal, external, or both.", "warn"); return; }
    const tooling = ti && te ? "both" : te ? "external" : "internal";
    // The drafter drives the structural phases (2, 5, 6, 7) and there is no house default,
    // so it must be chosen or those phases would have no runner.
    if (!readKnob(K.drafter)) { toast("Pick a <b>drafter</b> model — it drives the structural phases (there is no house default).", "warn"); return; }
    begin.disabled = true; begin.textContent = "KINDLING THE FORGE...";
    try {
      const runners = {};
      // Three hands: DRAFTER = the cheap default for the structural phases the validator
      // backstops (2 skeleton, 5 economy, 6 cosmetics, 7 validate). WRITER = the authoring
      // phases that decide teaching quality (1 arc, 3 sections, 4 minigames). REVIEWER =
      // phase 8, the final student read-through — independent eyes on the finished tome.
      // Fallbacks: an empty WRITER drops to the drafter's model; an empty REVIEWER
      // defaults to the WRITER's model, so review still gets the costly hand (just not
      // independent) unless you pick a distinct reviewer.
      const WRITER_PHASES = ["1", "3", "4"];
      const drafter = readKnob(K.drafter), writer = readKnob(K.writer), reviewer = readKnob(K.reviewer);
      if (drafter) runners.default = drafter;
      if (writer) {
        for (const p of WRITER_PHASES) runners[p] = writer;
        runners["8"] = writer;  // reviewer defaults to the writer...
      }
      if (reviewer) runners["8"] = reviewer;  // ...unless a distinct reviewer is chosen
      const splitOn = $("#fg-split", root).checked;   // Sections dial overrides the writer for phase 3
      if (splitOn) {
        const sec = readKnob(K.sec);           // split mode: any model — context stays small per section
        if (sec) runners["3"] = sec;
      } else {
        const sections = $("#fg-sections", root).value;  // single session: curated shortlist only
        if (sections) runners["3"] = { kind: "opencode-cli", model: sections };
      }
      // snapshot the picks so a future resume of this tome can pre-fill them (same shape as
      // the localStorage restore path); the server stores it in the build's launch.json.
      const snap = { split: splitOn, sections: $("#fg-sections", root).value,
                     quality: qual.value, configure: conf.checked };
      for (const [n, k] of Object.entries(K)) snap[n] = { prov: k.prov.value, model: k.model.value, eff: k.eff.value };
      const fromPhase = resume ? parseInt(($("#fg-fromphase", root) || {}).value || "0", 10) : 0;
      const payload = resume
        ? { id: resume.id, runners, sectionsSplit: splitOn, bindery: snap, fromPhase }
        : { concept, prior_knowledge: $("#fg-prior", root).value.trim(), prior_level: priorLvl.value,
            depth: depth.value, breadth: breadth.value, mastery: mastery.value,
            tooling, runners, sectionsSplit: splitOn, bindery: snap };
      const r = await fetch(resume ? "/api/buildtome/resume" : "/api/buildtome", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await r.json();
      if (!data.ok) throw new Error(data.error || "the bindery did not answer");
      localStorage.setItem("buildJob", data.jobId);
      closeModal(() => openBuildOverlay(data.jobId));
    } catch (err) {
      begin.disabled = false; begin.textContent = resume ? "CONTINUE THE WORKING" : "BEGIN THE WORKING";
      toast("The bindery could not begin: " + esc(String(err.message || err)), "bad");
    }
  };
  $(".modal-actions", root).appendChild(begin);
}
