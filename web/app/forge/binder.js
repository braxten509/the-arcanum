/* THE BINDER — ask a headless AI agent (server-side CLI) to make a change to this
   course, guided by course-configuration-guide.md; validated after.
   The [PROVIDER][MODEL][EFFORT] cascade is the bindery's, fed by /api/models. */
import { $, esc, mdLite, modal, toast } from "../core/dom.js";
import { prepareStateReset, resumeStateSaves } from "../core/state.js";
import { enhanceSelect } from "../ui/menu.js";

let binderPoll = null;   // one watcher at a time, even across bench visits

export function showBinder() {
  modal(`<h2>THE BINDER</h2>
    <p class="dim" id="binder-desc">Name one small flaw in this tome — a typo, a wrong color, a price, a missing line —
    and the Binder's spirit will re-ink the page. It edits the course itself, so be specific. Ask a question instead and it will just answer, with no edits made.</p>
    <div id="binder-inputs">
    <textarea id="binder-q" rows="3" style="width:100%" placeholder="e.g. the s02-l03 hint has a typo · make the signature theme's accent more copper · rename the SLAG SHIELD to CINDER WARD"></textarea>
    <div style="display:flex;align-items:center;gap:20px;margin-top:10px;flex-wrap:wrap">
      <label class="forge-check" style="margin:0"><input type="checkbox" id="bd-broad"> Broad change</label>
      <label class="forge-check" style="margin:0" title="The Binder reads the tome without changing it and writes its findings to the reviews/ ledger."><input type="checkbox" id="bd-review"> Review</label>
      <label class="forge-check hidden" id="bd-iterate-wrap" style="margin:0"><input type="checkbox" id="bd-iterate"> Iterate</label>
      <label class="forge-check hidden" id="bd-reset-wrap" style="margin:0" title="Lets the Binder add, remove, reorder, or rename chapters and lessons — restructuring the tome. This RESETS all player progress for this tome."><input type="checkbox" id="bd-reset"> Okay to reset progress?</label>
    </div>
    <p class="hidden" id="bd-reset-warn" style="color:var(--bad,#c66);font-size:11.5px;margin:6px 0 0">⚠ The Binder may restructure this tome — every artificer's progress on it will be reset.</p>
    <div class="forge-field" style="margin-top:10px"><label>THE BINDER'S HAND</label>
      <div class="forge-ai-row">
        <div class="forge-ai-choice"><select id="bd-prov" class="cfg-select" aria-label="Binder agent CLI"><option value="">PICK A MODEL</option></select></div>
        <div class="forge-ai-choice"><select id="bd-model" class="cfg-select" aria-label="Binder model" disabled><option value="">—</option></select></div>
        <div class="forge-ai-choice"><select id="bd-eff" class="cfg-select" aria-label="Binder effort" disabled><option value="">—</option></select></div>
      </div></div>
    <details class="binder-rebuild" id="bd-rebuild">
      <summary><span>RESET THE BUILD TO A PHASE</span><b>DESTRUCTIVE</b></summary>
      <div class="binder-rebuild-body">
        <div class="binder-rebuild-pick">
          <label for="bd-phase">START THE REBUILD AT</label>
          <select id="bd-phase" class="cfg-select">
            <option value="">CHOOSE PHASE</option>
            <option value="1">1 · CONCEPT &amp; ARC</option>
            <option value="2">2 · SKELETON &amp; VOICE</option>
            <option value="3">3 · SECTIONS</option>
            <option value="4">4 · MINIGAMES</option>
            <option value="5">5 · ECONOMY</option>
            <option value="6">6 · COSMETICS</option>
            <option value="7">7 · VALIDATE</option>
            <option value="8">8 · STUDENT REVIEW</option>
          </select>
        </div>
        <div class="binder-rebuild-consequence hidden" id="bd-phase-warn" aria-live="polite"></div>
        <label class="binder-rebuild-ack hidden" id="bd-phase-ack-wrap">
          <input type="checkbox" id="bd-phase-ack">
          <span>I understand that learner progress and later tome work will be erased.</span>
        </label>
        <button class="btn danger binder-rebuild-go" id="bd-phase-go" type="button" disabled>RESET AND REBUILD</button>
        <div class="binder-rebuild-error hidden" id="bd-phase-error" role="alert"></div>
      </div>
    </details>
    </div>
    <div id="binder-a" class="hidden" style="margin-top:12px;padding:12px;border:1px solid var(--line-hi);border-left:2px solid var(--ac-dim);border-radius:3px;font-size:12.5px;white-space:pre-wrap;max-height:45vh;overflow-y:auto"></div>`,
    [["LEAVE THE BENCH", "quiet"]]);
  const root = $("#modal-root");
  $(".modal", root).classList.add("wide");   // room for the validator's report and the button row
  const k = { prov: $("#bd-prov", root), model: $("#bd-model", root), eff: $("#bd-eff", root) };
  let BINDERY = [];
  const fillEffort = () => {   // effort follows the selected MODEL (row is [id,label,tag,efforts])
    const p = BINDERY.find((x) => x.id === k.prov.value);
    const m = p && (p.models || []).find((mm) => mm[0] === k.model.value);
    const levels = (m && m[3]) || [];
    k.eff.innerHTML = levels.length
      ? `<option value="">DEFAULT</option>` + levels.map((l) => `<option value="${esc(l)}">${esc(l.toUpperCase())}</option>`).join("")
      : `<option value="">—</option>`;
    k.eff.disabled = !levels.length;
  };
  const fillModels = () => {
    const p = BINDERY.find((x) => x.id === k.prov.value);
    const models = (p && p.models) || [];
    k.model.innerHTML = models.length
      ? models.map(([v, l, tag]) => `<option value="${esc(v)}"${tag ? ` data-suffix="— ${esc(tag)}"` : ""}>${esc(l)}</option>`).join("")
      : `<option value="">${p ? "(no models found)" : "—"}</option>`;
    k.model.disabled = !models.length;
    fillEffort();
  };
  const BD_SAVE = "binderRunner";
  let restoring = false;
  const persist = () => {
    if (restoring) return;
    try { localStorage.setItem(BD_SAVE, JSON.stringify({ prov: k.prov.value, model: k.model.value, eff: k.eff.value, broad: $("#bd-broad").checked, iterate: $("#bd-iterate").checked, reset: $("#bd-reset").checked, review: $("#bd-review").checked })); } catch (e) { /* private mode */ }
  };
  k.prov.addEventListener("change", fillModels);
  k.model.addEventListener("change", fillEffort);
  // Gray the hand out and say "Loading…" until /api/models answers — an empty "PICK A
  // MODEL" box during the async gap reads as broken (there is nothing to pick yet).
  k.prov.innerHTML = '<option value="">Loading…</option>'; k.prov.disabled = true;
  [k.prov, k.model, k.eff].forEach((s) => { enhanceSelect(s); s.addEventListener("change", persist); });
  const DESC_NARROW = "Name one small flaw in this tome — a typo, a wrong color, a price, a missing line — and the Binder's spirit will re-ink the page. It edits the course itself, so be specific. Ask a question instead and it will just answer, with no edits made.";
  const DESC_BROAD = "Describe a larger rework — recast a chapter, add lessons, retune the economy — and the Binder's spirit will re-ink the tome, editing as many pages as it takes. Say what you want; you can send it back to iterate. Ask a question instead and it will just answer, with no edits made.";
  const DESC_ITERATE = "The Binder surveys the whole tome against its improvement guide and reworks the weak spots on its own — untaught concepts, thin duel banks, lessons with no readings, shallow answer feedback, flat lessons. It may add new lessons or append new chapters where the material needs them (additions never touch your progress). Leave the box below empty, or name what to focus on.";
  const DESC_REVIEW = "The Binder reads the whole tome without inking a single page and sets its findings down in the reviews/ ledger. Name what to look for below — or leave it blank for a full survey — and afterwards you may commission the changes it suggests.";
  const qBox = $("#binder-q", root);
  const qPlaceholder = qBox.placeholder;   // restore when Iterate is switched off
  const bd = $("#bd-broad", root), it = $("#bd-iterate", root), itWrap = $("#bd-iterate-wrap", root);
  const rs = $("#bd-reset", root), rsWarn = $("#bd-reset-warn", root), rsWrap = $("#bd-reset-wrap", root);
  const rv = $("#bd-review", root);
  const syncReset = () => { rsWarn.classList.toggle("hidden", !rs.checked); };
  const syncDesc = () => {
    itWrap.classList.toggle("hidden", !bd.checked);
    rsWrap.classList.toggle("hidden", !bd.checked);  // reset only means anything on a broad rework
    if (!bd.checked) { it.checked = false; rs.checked = false; }  // Iterate/reset only exist inside Broad
    bd.parentElement.classList.toggle("hidden", rv.checked);  // Broad and Review are mutually exclusive
    rv.parentElement.classList.toggle("hidden", bd.checked);
    syncReset();
    $("#binder-desc", root).textContent = rv.checked ? DESC_REVIEW : it.checked ? DESC_ITERATE : bd.checked ? DESC_BROAD : DESC_NARROW;
    qBox.placeholder = it.checked || rv.checked ? "(optional)" : qPlaceholder;
  };
  bd.addEventListener("change", () => { if (bd.checked) rv.checked = false; persist(); syncDesc(); });
  it.addEventListener("change", () => { persist(); syncDesc(); });
  rv.addEventListener("change", () => { if (rv.checked) bd.checked = false; persist(); syncDesc(); });
  rs.addEventListener("change", () => { persist(); syncReset(); });
  const fillBindery = (d) => {
    BINDERY = (d.bindery || []).filter((p) => p.installed !== false);
    k.prov.innerHTML = '<option value="">PICK A MODEL</option>' + BINDERY.map((p) => `<option value="${esc(p.id)}">${esc(p.label)}</option>`).join("");
    k.prov.disabled = false;
    const has = (sel, v) => [...sel.options].some((o) => o.value === v);
    let s = {}; try { s = JSON.parse(localStorage.getItem(BD_SAVE) || "{}"); } catch (e) { /* ignore */ }
    restoring = true;
    if (s.prov && has(k.prov, s.prov)) {
      k.prov.value = s.prov; k.prov.dispatchEvent(new Event("change"));
      if (s.model && has(k.model, s.model)) { k.model.value = s.model; k.model.dispatchEvent(new Event("change")); }
      if (s.eff && has(k.eff, s.eff)) { k.eff.value = s.eff; k.eff.dispatchEvent(new Event("change")); }
    }
    if (s.broad) bd.checked = true;
    if (s.iterate) it.checked = true;
    if (s.reset) rs.checked = true;
    if (s.review && !bd.checked) rv.checked = true;  // Broad and Review are mutually exclusive
    syncDesc(); syncReset();
    restoring = false;
    reattachOrResume();   // BINDERY is loaded now, so a resume card has hands to offer
  };
  // Fetch failures retry quietly before the toast — a hiccup mid-startup is not "server down".
  // fillBindery sits in .then's SUCCESS slot only, so its own errors never trigger the toast.
  const loadModels = (attempt = 0) => {
    fetch("/api/models").then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(fillBindery, () => {
        if (attempt < 2) { setTimeout(() => loadModels(attempt + 1), 800 * (attempt + 1)); return; }
        k.prov.innerHTML = '<option value="">—</option>'; k.prov.disabled = true;
        toast("Could not reach the model list — is the server up?", "bad");
      });
  };
  loadModels();
  const actions = $("#modal-root .modal-actions");
  const out = $("#binder-a", root);
  const sendBtn = document.createElement("button");
  sendBtn.className = "btn"; sendBtn.textContent = "SEND TO THE BINDER";
  const phaseReset = $("#bd-phase", root), phaseAck = $("#bd-phase-ack", root),
        phaseAckWrap = $("#bd-phase-ack-wrap", root), phaseWarn = $("#bd-phase-warn", root),
        phaseGo = $("#bd-phase-go", root), phaseError = $("#bd-phase-error", root);
  const phaseConsequences = {
    1: "The approved arc and the entire authored tome will be erased. The AI starts again at Concept & arc.",
    2: "The approved arc is kept. The authored tome is replaced by a fresh Phase 2 skeleton.",
    3: "The arc and Phase 2 shell are kept. Every authored section is replaced by fresh Phase 3 placeholders.",
    4: "The arc and sections are kept. Minigames and every later phase are rebuilt.",
    5: "Sections and minigames are kept. Economy, cosmetics, validation, and review are rebuilt.",
    6: "Authored course content and economy are kept. Cosmetics, validation, and review are rebuilt.",
    7: "Authored content is kept. Shipping validation and student review run again, and their completion evidence is cleared.",
    8: "The validated tome is kept. Student review is marked incomplete and runs again against it.",
  };
  enhanceSelect(phaseReset);
  const syncPhaseReset = () => {
    const phase = Number(phaseReset.value || 0), selected = !!phase;
    phaseWarn.classList.toggle("hidden", !selected);
    phaseAckWrap.classList.toggle("hidden", !selected);
    if (selected) phaseWarn.textContent = `${phaseConsequences[phase]} All learner progress, grades, and internal workbench files for this tome are erased. An external project folder is never deleted.`;
    else phaseWarn.textContent = "";
    phaseGo.disabled = !selected || !phaseAck.checked;
    phaseError.classList.add("hidden");
  };
  phaseReset.addEventListener("change", () => { phaseAck.checked = false; syncPhaseReset(); });
  phaseAck.addEventListener("change", syncPhaseReset);
  phaseGo.onclick = async () => {
    const phase = Number(phaseReset.value || 0);
    const provider = BINDERY.find((item) => item.id === k.prov.value);
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
      const response = await fetch("/api/buildtome/reset", {
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
        const resumeResponse = await fetch("/api/buildtome/resume", {
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
  // gray out (and block) every input while the Binder works
  const lock = (on) => {
    const inp = $("#binder-inputs", root);
    if (inp) { inp.style.opacity = on ? ".5" : ""; inp.style.pointerEvents = on ? "none" : ""; }
  };
  const idle = () => {
    lock(false);
    sendBtn.disabled = false; sendBtn.textContent = "SEND TO THE BINDER";
    $("#binder-q").disabled = false;
    actions.querySelectorAll(".binder-cancel").forEach((b) => b.remove());
  };
  // Forge-style "pick a hand and re-run" card, shared by two moments: a broad run whose hand
  // DIED mid-work, and a cut-short amendment offered for RESUME when the bench opens. Both just
  // re-run a request over the tome as it stands on disk, with whatever hand you choose.
  // opts: { tag, title, detail, logText, actionLabel, onPick(prov,model,eff), onDismiss? }
  function pickHandCard(opts) {
    root.querySelector(".runner-death")?.remove();
    const host = root.querySelector(".modal-back") || root;  // absolute inset:0 needs the fixed backdrop as its positioned parent, and z-index:2 must sit inside it to clear the modal
    const box = document.createElement("div");
    box.className = "runner-death";
    box.innerHTML = `<div class="grade-card rd-card">
      <div class="faint" style="font-size:11px;letter-spacing:.2em">${esc(opts.tag)}</div>
      <h2 style="margin:8px 0 4px;font-family:var(--arch)">${esc(opts.title)}</h2>
      <p class="rd-detail dim" style="font-size:12.5px;margin:0 0 8px">${esc(opts.detail || "")}</p>
      ${opts.logText ? `<div class="forge-log num" style="height:auto;max-height:150px;margin:0 0 10px">${esc(opts.logText)}</div>` : ""}
      <p class="dim" style="font-size:12px;margin:0 0 14px">Choose the hand that takes up the quill — it re-runs the request over the tome as it stands on disk.</p>
      <div class="forge-ai-row">
        <div class="forge-ai-choice"><select class="cfg-select rd-prov" aria-label="Replacement Binder agent CLI"></select></div>
        <div class="forge-ai-choice"><select class="cfg-select rd-model" aria-label="Replacement Binder model" disabled><option value="">—</option></select></div>
        <div class="forge-ai-choice"><select class="cfg-select rd-eff" aria-label="Replacement Binder effort" disabled><option value="">—</option></select></div>
      </div>
      <div class="modal-actions" style="margin-top:16px">
        <button class="btn quiet rd-abort">LEAVE IT</button>
        <button class="btn rd-resume" disabled>${esc(opts.actionLabel)}</button>
      </div></div>`;
    host.appendChild(box);
    const prov = box.querySelector(".rd-prov"), model = box.querySelector(".rd-model"),
          eff = box.querySelector(".rd-eff"), resume = box.querySelector(".rd-resume");
    const fillEff = () => {
      const p = BINDERY.find((x) => x.id === prov.value);
      const m = p && (p.models || []).find((mm) => mm[0] === model.value);
      const lv = (m && m[3]) || [];
      eff.innerHTML = lv.length ? `<option value="">DEFAULT</option>` + lv.map((l) => `<option value="${esc(l)}">${esc(l.toUpperCase())}</option>`).join("") : `<option value="">—</option>`;
      eff.disabled = !lv.length;
    };
    const fillModel = () => {
      const p = BINDERY.find((x) => x.id === prov.value);
      const ms = (p && p.models) || [];
      model.innerHTML = ms.length ? ms.map(([v, l, tag]) => `<option value="${esc(v)}"${tag ? ` data-suffix="— ${esc(tag)}"` : ""}>${esc(l)}</option>`).join("") : `<option value="">—</option>`;
      model.disabled = !ms.length; resume.disabled = !ms.length;
      fillEff();
    };
    prov.addEventListener("change", fillModel);
    model.addEventListener("change", fillEff);
    prov.innerHTML = BINDERY.map((p) => `<option value="${esc(p.id)}">${esc(p.label)}</option>`).join("");
    if (k.prov.value && [...prov.options].some((o) => o.value === k.prov.value)) prov.value = k.prov.value;  // default to the bench's current hand
    fillModel();
    if (k.model.value && [...model.options].some((o) => o.value === k.model.value)) { model.value = k.model.value; fillEff(); }
    [prov, model, eff].forEach(enhanceSelect);
    box.querySelector(".rd-abort").onclick = () => { box.remove(); opts.onDismiss && opts.onDismiss(); };
    resume.onclick = () => {
      if (!model.value) return;
      box.remove();
      opts.onPick(prov.value, model.value, eff.value);
    };
  }
  // push the chosen hand into the bench cascade, then fire the request off
  const runWithHand = (prov, model, eff) => {
    k.prov.value = prov; k.prov.dispatchEvent(new Event("change"));
    k.model.value = model; k.model.dispatchEvent(new Event("change"));
    if (eff) { k.eff.value = eff; k.eff.dispatchEvent(new Event("change")); }
    sendBtn.onclick();
  };
  function binderDeath(info) {
    pickHandCard({
      tag: "THE BINDER // A HAND HAS FALTERED",
      title: "The Binder's hand died",
      detail: (info || "").split("\n")[0] || "the runner exited",
      logText: info || "no record of the failure",
      actionLabel: "TRY AGAIN",
      onPick: runWithHand,
    });
  }
  // an amendment cut short by a lost server/runner — offered on bench open (see /api/amend/resumable).
  // Restores the original request + mode, lets you pick any hand, and runs it again.
  function binderResume(st) {
    const mode = st.review ? "a review" : st.iterate ? "an Iterate pass" : st.broad ? "a broad change" : "a small change";
    pickHandCard({
      tag: "THE BINDER // AN AMENDMENT WAS CUT SHORT",
      title: "Resume the unfinished amendment?",
      detail: `The Binder's last ${mode} to this tome ${st.status === "error" ? "failed before it finished" : "was cut short before it finished"}. Take it up again with the same hand or a new one.`,
      logText: st.request || "(no request recorded — an Iterate survey)",
      actionLabel: "RESUME",
      onPick: (prov, model, eff) => {
        $("#binder-q").value = st.request || "";
        bd.checked = !!(st.broad || st.iterate); it.checked = !!st.iterate; rv.checked = !!st.review; syncDesc();
        rs.checked = !!st.resetOk; syncReset();
        runWithHand(prov, model, eff);
      },
      onDismiss: () => { fetch("/api/amend/dismiss", { method: "POST" }).catch(() => {}); },
    });
  }
  // watch one server-side job. The job outlives this dialog — leaving the bench
  // never stops the Binder; reopening reattaches via /api/amend/current.
  const watch = (jobId, isBroad) => {
    lock(true);
    root.querySelector(".runner-death")?.remove();
    sendBtn.disabled = true; sendBtn.textContent = "THE BINDER WORKS...";
    $("#binder-q").disabled = true;
    out.classList.remove("hidden");
    actions.querySelectorAll(".binder-extra, .binder-cancel").forEach((b) => b.remove());
    const cx = document.createElement("button");
    cx.className = "btn danger binder-cancel"; cx.textContent = "STAY THE QUILL";
    cx.title = "Cancel this amendment";
    cx.onclick = async () => {
      cx.disabled = true;
      try {
        const r = await (await fetch("/api/amend/cancel", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: jobId }) })).json();
        if (!r.ok) throw new Error(r.error || "the server would not stay the quill");
      } catch (e) {
        toast("Could not cancel: " + esc(String(e.message || e)) + " — if the server predates this button, restart it.", "bad");
        cx.disabled = false;
      }
    };
    actions.prepend(cx);
    clearInterval(binderPoll);
    binderPoll = setInterval(async () => {
      let st;
      try { st = await (await fetch("/api/amend/status?id=" + encodeURIComponent(jobId))).json(); } catch { return; }
      if (isBroad && st.logtail != null) { out.innerHTML = mdLite(st.logtail || "the binder works…"); out.scrollTop = out.scrollHeight; }
      if (st.status === "running") return;
      clearInterval(binderPoll);
      idle();
      if (st.status === "done") {
        if (st.review) {  // a survey, not an edit — show the findings and ask what to commission
          lastReview = st.reportPath || "";
          rv.checked = false; syncDesc(); persist();
          out.innerHTML = mdLite((st.summary || "(the binder said nothing)")
            + `\n\n── THE SURVEY IS COMPLETE ──\nThe full report is inked at ${st.reportPath || "the reviews/ ledger"}.`
            + "\nWould you have changes made? Describe them above and SEND — the Binder will read its own report first, and the Broad change box governs how far the quill reaches.");
          qBox.value = ""; qBox.focus();
          return;
        }
        out.innerHTML = mdLite((st.summary || "(the binder said nothing)")
          + (st.validatorOk === false ? "\n\n⚠ THE CANDLE FINDS FLAWS:\n" + (st.validator || "") : ""));
        const rb = document.createElement("button");
        rb.className = "btn binder-extra"; rb.textContent = "RE-OPEN THE TOME";
        rb.onclick = () => location.reload();
        actions.prepend(rb);
        if (st.validatorOk === false && st.validator) {
          const fx = document.createElement("button");
          fx.className = "btn binder-extra"; fx.textContent = "MEND THE FLAWS";
          fx.onclick = () => {
            $("#binder-q").value = "Fix every ERROR and WARN the validator reports below. Address each one; do not skip any.\n\n" + st.validator;
            sendBtn.onclick();
          };
          actions.prepend(fx);
        }
      } else if (st.status === "cancelled") {
        out.textContent = "THE QUILL IS STAYED — the amendment was cancelled. A half-inked edit may remain; ask the Binder again if the page looks wrong.";
      } else {  // error / unknown — a real failure or timeout
        const msg = st.error || st.logtail || "unknown error";
        if (isBroad) binderDeath(msg);              // forge-style: pick a new hand and retry
        else out.textContent = "THE QUILL SNAPPED — " + msg;
      }
    }, 2500);
  };
  let lastReview = "";   // reviews/ path of the survey this bench just ran — fed to the next change
  sendBtn.onclick = async () => {
    const q = $("#binder-q").value.trim();
    if (!q && !it.checked && !rv.checked) return;   // Iterate/Review need no request; the guide drives them
    const p = BINDERY.find((x) => x.id === k.prov.value);
    if (!p || !k.model.value) { toast("Pick the Binder's <b>model</b> first.", "warn"); return; }
    const isBroad = bd.checked || it.checked || rv.checked;
    out.classList.remove("hidden");
    out.textContent = "the quill is dipped...";
    try {
      const r = await (await fetch("/api/amend", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request: q, kind: p.kind, model: k.model.value, effort: k.eff.value || undefined, broad: bd.checked, iterate: it.checked, resetOk: rs.checked, review: rv.checked, reviewPath: (!rv.checked && lastReview) || undefined }),
      })).json();
      if (!r.ok) throw new Error(r.error || "the binder did not answer");
      watch(r.jobId, isBroad);
    } catch (err) {
      out.textContent = "server error: " + err;
    }
  };
  actions.prepend(sendBtn);
  // On open: reattach to a job still inking in this server, else offer to resume one a lost
  // server/runner cut short. Runs after the model list loads so the resume card has hands to pick.
  function reattachOrResume() {
    fetch("/api/amend/current").then((r) => r.json()).then((d) => {
      if (d.jobId) {
        const q = $("#binder-q");
        if (q && !q.value) q.value = d.request || "";
        out.classList.remove("hidden");
        out.textContent = "the Binder is already at work on this tome — watching that job...";
        watch(d.jobId, !!(d.broad || d.review));
        return;
      }
      fetch("/api/amend/resumable").then((r) => r.json()).then((rd) => {
        if (rd && rd.resumable) binderResume(rd.resumable);
      }).catch(() => { /* nothing to resume */ });
    }).catch(() => { /* no reattach; the bench still works */ });
  }
  setTimeout(() => { const f = $("#binder-q"); if (f) f.focus(); }, 50);
}
