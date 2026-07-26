/* THE BINDER — ask a headless AI agent (server-side CLI) to make a change to this
   course, guided by course-configuration-guide.md; validated after.
   The [PROVIDER][MODEL][EFFORT] cascade is the bindery's, fed by /api/models. */
import { $, esc, mdLite, modal, toast } from "../core/dom.js";
import { enhanceSelect } from "../ui/menu.js";
import { apiFetch } from "../core/api-client.js";
import { binderActivity, binderCost, binderTemplate } from "./binder/view.js";
import { binderLedger, REVIEW_FIX_REQUEST } from "./binder/ledger.js";
import { binderRebuild } from "./binder/rebuild.js";

let binderPoll = null;   // one watcher at a time, even across bench visits

export function showBinder() {
  // sticky: the bench holds a typed request, a picked hand, and a selected review — a stray
  // click on the backdrop must never throw all of that away. LEAVE THE BENCH is the way out.
  modal(binderTemplate(), [["LEAVE THE BENCH", "quiet"]], { sticky: true });
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
    try { localStorage.setItem(BD_SAVE, JSON.stringify({ prov: k.prov.value, model: k.model.value, eff: k.eff.value, broad: $("#bd-broad").checked, updateStandard: $("#bd-standard").checked, iterate: $("#bd-iterate").checked, reset: $("#bd-reset").checked, review: $("#bd-review").checked, publish: $("#bd-publish").checked })); } catch (e) { /* private mode */ }
  };
  k.prov.addEventListener("change", fillModels);
  k.model.addEventListener("change", fillEffort);
  // Gray the hand out and say "Loading…" until /api/models answers — an empty "PICK A
  // MODEL" box during the async gap reads as broken (there is nothing to pick yet).
  k.prov.innerHTML = '<option value="">Loading…</option>'; k.prov.disabled = true;
  [k.prov, k.model, k.eff].forEach((s) => { enhanceSelect(s); s.addEventListener("change", persist); });
  const DESC_NARROW = "Name one small flaw in this tome — a typo, a wrong color, a price, a missing line — and the Binder's spirit will re-ink the page. It edits the course itself, so be specific. Ask a question instead and it will just answer, with no edits made.";
  const DESC_BROAD = "Describe a larger rework — recast a chapter, add lessons, retune the economy — and the Binder's spirit will re-ink the tome, editing as many pages as it takes. Say what you want; you can send it back to iterate. Ask a question instead and it will just answer, with no edits made.";
  const ITERATE_HEAD = "The Binder surveys the whole tome against its improvement guide and reworks the weak spots on its own — untaught concepts, thin duel banks, lessons with no readings, shallow answer feedback, flat lessons. ";
  const ITERATE_ADD = "It may add new lessons or append new chapters where the material needs them (additions never touch your progress).";
  // With reset authorized the append-only promise is void: the run may renumber, move, and
  // remove existing chapters and lessons, and progress is keyed to exactly those ids.
  const ITERATE_RESET = "Because you authorized a progress reset, it may restructure freely — adding, renumbering, moving, and removing chapters and lessons — and your progress on this tome will NOT survive.";
  const DESC_ITERATE = () => ITERATE_HEAD + (rs.checked ? ITERATE_RESET : ITERATE_ADD)
    + " Leave the box below empty, or name what to focus on.";
  const DESC_REVIEW = "The Binder reads the whole tome without inking a single page and sets its findings down in the reviews/ ledger. Name what to look for below — or leave it blank for a full survey — and afterwards you may commission the changes it suggests.";
  // Update to Standard is its own complete mandate, so the box below is an optional narrowing
  // of it, exactly as it is under Iterate — say so, or a blank box reads as a missing answer.
  const STANDARD_ADD = " Update to Standard is itself the whole assignment, so the box below is optional — leave it empty and the Binder just brings the tome current.";
  // Publish is a loop, not a bigger version of Broad, so its description says what a round
  // costs. Four rounds is eight AI turns over a whole tome: the priciest thing on this bench.
  const DESC_PUBLISH = "The Binder rounds on the tome until it is fit for strangers. Each round is two separate passes: one reads the whole tome against publisher.md — the publication bar — and writes a verdict to the reviews/ ledger, then a second repairs everything that verdict called blocking. It ends when a survey signs the tome off AND the harness's own shipping gate agrees; a sign-off the gate disagrees with is overruled. Up to 4 rounds, so up to 8 AI turns — the most expensive run on this bench. It never touches your progress. Leave the box below empty, or name what to weigh most.";
  const qBox = $("#binder-q", root);
  const qPlaceholder = qBox.placeholder;   // restore when Iterate is switched off
  const bd = $("#bd-broad", root), it = $("#bd-iterate", root), itWrap = $("#bd-iterate-wrap", root);
  const standard = $("#bd-standard", root), standardWrap = $("#bd-standard-wrap", root);
  const rs = $("#bd-reset", root), rsWarn = $("#bd-reset-warn", root), rsWrap = $("#bd-reset-wrap", root);
  const rv = $("#bd-review", root);
  const pub = $("#bd-publish", root);
  const syncReset = () => { rsWarn.classList.toggle("hidden", !rs.checked); };
  const syncDesc = () => {
    // Publish owns the bench alone. Every other box is cleared as well as hidden — a mode
    // still ticked behind the panel is one the server would have to be trusted to ignore.
    const pubOn = pub.checked;
    if (pubOn) { bd.checked = false; rv.checked = false; standard.checked = false; it.checked = false; rs.checked = false; }
    standardWrap.classList.toggle("hidden", !bd.checked || pubOn);
    itWrap.classList.toggle("hidden", !bd.checked || pubOn);
    rsWrap.classList.toggle("hidden", !bd.checked || pubOn);  // reset only means anything on a broad rework
    if (!bd.checked) { standard.checked = false; it.checked = false; rs.checked = false; }  // broad-only options
    bd.parentElement.classList.toggle("hidden", rv.checked || pubOn);  // Broad and Review are mutually exclusive
    rv.parentElement.classList.toggle("hidden", bd.checked || pubOn);
    syncReset();
    const optional = pubOn || it.checked || rv.checked || standard.checked;
    $("#binder-desc", root).textContent = pubOn ? DESC_PUBLISH
      : (rv.checked ? DESC_REVIEW : it.checked ? DESC_ITERATE() : bd.checked ? DESC_BROAD : DESC_NARROW)
        + (standard.checked && !rv.checked ? STANDARD_ADD : "");
    qBox.placeholder = optional ? "(optional)" : qPlaceholder;
    // The phase rewind throws the tome away and re-runs the pipeline — it has nothing to do
    // with the amendment being set up. Any checked box means one is, so the door stays shut.
    const amending = pubOn || bd.checked || standard.checked || it.checked || rs.checked || rv.checked;
    const rebuild = $("#bd-rebuild", root);
    rebuild.classList.toggle("hidden", amending);
    if (amending) rebuild.open = false;   // never reappear already unfolded
  };
  bd.addEventListener("change", () => { if (bd.checked) rv.checked = false; persist(); syncDesc(); });
  standard.addEventListener("change", () => { persist(); syncDesc(); });
  it.addEventListener("change", () => { persist(); syncDesc(); });
  rv.addEventListener("change", () => { if (rv.checked) bd.checked = false; persist(); syncDesc(); });
  rs.addEventListener("change", () => { persist(); syncDesc(); });   // syncDesc runs syncReset
  pub.addEventListener("change", () => { persist(); syncDesc(); });
  const fillBindery = (d) => {
    BINDERY = (d.bindery || []).filter((p) => p.installed !== false
      && (p.roles || []).includes("author"));
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
    if (s.updateStandard && bd.checked) standard.checked = true;
    if (s.iterate) it.checked = true;
    if (s.reset) rs.checked = true;
    if (s.review && !bd.checked) rv.checked = true;  // Broad and Review are mutually exclusive
    if (s.publish) pub.checked = true;   // syncDesc clears and hides everything above it
    syncDesc(); syncReset();
    restoring = false;
    reattachOrResume();   // BINDERY is loaded now, so a resume card has hands to offer
  };
  // Fetch failures retry quietly before the toast — a hiccup mid-startup is not "server down".
  // fillBindery sits in .then's SUCCESS slot only, so its own errors never trigger the toast.
  const loadModels = (attempt = 0) => {
    apiFetch("/api/models").then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
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
  const SEND_LABEL = "SEND TO THE BINDER";
  sendBtn.className = "btn"; sendBtn.textContent = SEND_LABEL;
  const historyBtn = document.createElement("button");
  // "PAST RUNS", not "PAST REVIEWS": the panel now also holds finished builds, and
  // nobody hunting for what a build cost would think to look under Reviews.
  historyBtn.className = "btn quiet"; historyBtn.textContent = "PAST RUNS";

  const setReviewApplication = (on) => {
    root.classList.toggle("binder-review-application-mode", on);
    if (on) {
      bd.checked = true;
      standard.checked = true;
      it.checked = false;
      rv.checked = false;
      pub.checked = false;   // commissioning a review's findings is not a publish run
    }
    bd.disabled = on;
    standard.disabled = on;
    pub.disabled = on;
    syncDesc(); persist();
  };

  const ledger = binderLedger({
    root, out, historyBtn, qBox, setReviewApplication,
    // The ledger is a reading surface, not a bench: a finished build has nothing left to
    // commission, so the quill goes away while it is open. A SELECTED REVIEW is the one
    // exception — picking one arms the next send — so the ledger hands the button back.
    showSend: (on) => sendBtn.classList.toggle("hidden", !on),
    clearModes: () => { rv.checked = false; it.checked = false; syncDesc(); persist(); },
    // Both cards live here because they draw over the bench and drive its own controls.
    resumeBuild: (setup) => binderResume(setup, true),
    confirm: (opts) => confirmCard(opts),
  });
  historyBtn.onclick = ledger.open;
  binderRebuild(root, () => BINDERY.find((item) => item.id === k.prov.value) || null, k);
  // gray out (and block) every input while the Binder works
  const lock = (on) => {
    const inp = $("#binder-inputs", root);
    if (inp) { inp.style.opacity = on ? ".5" : ""; inp.style.pointerEvents = on ? "none" : ""; }
  };
  const idle = () => {
    lock(false);
    sendBtn.disabled = false; sendBtn.textContent = SEND_LABEL;
    sendBtn.onclick = send; sendBtn.title = "";
    sendBtn.classList.remove("hidden");
    historyBtn.disabled = false;
    $("#binder-q").disabled = false;
    actions.querySelectorAll(".binder-cancel").forEach((b) => b.remove());
  };
  // A bench still holding a finished run's feed, checkboxes, and request will happily send
  // that same run again, so after one completes the quill becomes the way to empty the bench
  // instead. The picked hand survives: it is a saved preference, not part of the run.
  const freshSlate = () => {
    ledger.select(""); ledger.reset();
    setReviewApplication(false);   // gives Broad and Update to Standard back
    [bd, standard, it, rs, rv, pub].forEach((box) => { box.checked = false; });
    qBox.value = "";
    out.innerHTML = ""; out.classList.add("hidden");
    actions.querySelectorAll(".binder-extra").forEach((b) => b.remove());
    idle(); syncDesc(); persist();
    qBox.focus();
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
  // A yes/no card over the bench, for a choice that destroys something. The bench IS the
  // app's one modal, so calling modal() again would replace it and throw away the typed
  // request and the picked hand — hence a scrim card, the same way pickHandCard does it.
  // opts: { tag, title, detail, confirmLabel, onConfirm }
  function confirmCard(opts) {
    root.querySelector(".runner-death")?.remove();
    const host = root.querySelector(".modal-back") || root;
    const box = document.createElement("div");
    box.className = "runner-death";
    box.innerHTML = `<div class="grade-card rd-card">
      <div class="faint" style="font-size:11px;letter-spacing:.2em">${esc(opts.tag)}</div>
      <h2 style="margin:8px 0 4px;font-family:var(--arch)">${esc(opts.title)}</h2>
      <p class="rd-detail dim" style="font-size:12.5px;margin:0 0 4px">${esc(opts.detail || "")}</p>
      <div class="modal-actions" style="margin-top:16px">
        <button class="btn quiet rd-abort">KEEP IT</button>
        <button class="btn danger rd-confirm">${esc(opts.confirmLabel)}</button>
      </div></div>`;
    host.appendChild(box);
    box.querySelector(".rd-abort").onclick = () => box.remove();
    box.querySelector(".rd-confirm").onclick = () => { box.remove(); opts.onConfirm(); };
  }
  // push the chosen hand into the bench cascade, then fire the request off
  const runWithHand = (prov, model, eff) => {
    k.prov.value = prov; k.prov.dispatchEvent(new Event("change"));
    k.model.value = model; k.model.dispatchEvent(new Event("change"));
    if (eff) { k.eff.value = eff; k.eff.dispatchEvent(new Event("change")); }
    send();   // by name: after a finished run the quill's own handler is RESET
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
  // an amendment cut short by a lost server/runner — offered on bench open (see /api/amend/resumable),
  // and on demand from any unfinished run in the ledger. Restores the original request + mode,
  // lets you pick any hand, and runs it again. `fromLedger` only changes the wording and drops
  // the dismiss call: the state file holds the LAST run, which is not the row you clicked.
  function binderResume(st, fromLedger) {
    const mode = st.publish ? "a publish run" : st.review ? "a review" : st.iterate ? "an Iterate pass" : st.broad ? "a broad change" : "a small change";
    const fate = st.status === "error" ? "failed before it finished"
      : st.status === "cancelled" ? "was stopped by you before it finished"
      : "was cut short before it finished";
    pickHandCard({
      tag: "THE BINDER // AN AMENDMENT WAS CUT SHORT",
      title: "Resume the unfinished amendment?",
      detail: `${fromLedger ? `That ${mode}` : `The Binder's last ${mode}`} to this tome ${fate}. Take it up again with the same hand or a new one.`,
      logText: st.request || "(no request recorded — an Iterate survey)",
      actionLabel: "RESUME",
      onPick: (prov, model, eff) => {
        $("#binder-q").value = st.request || "";
        bd.checked = !!(st.broad || st.iterate); it.checked = !!st.iterate; rv.checked = !!st.review;
        standard.checked = !!st.updateStandard;
        rs.checked = !!st.resetOk;
        // Last, and after the others: a publish run is recorded as broad, so syncDesc has to
        // see the publish flag or it restores the run as the plain broad change it is not.
        pub.checked = !!st.publish;
        syncDesc(); syncReset();
        runWithHand(prov, model, eff);
      },
      onDismiss: fromLedger
        ? undefined
        : () => { apiFetch("/api/amend/dismiss", { method: "POST" }).catch(() => {}); },
    });
  }
  // Ask the server whether this tome has an unfinished amendment on record, and offer it.
  // Used on bench open and the moment a run is stopped by hand.
  function offerResume() {
    return apiFetch("/api/amend/resumable").then((r) => r.json()).then((rd) => {
      if (rd && rd.resumable) binderResume(rd.resumable);
    }).catch(() => { /* nothing to resume */ });
  }
  // watch one server-side job. The job outlives this dialog — leaving the bench
  // never stops the Binder; reopening reattaches via /api/amend/current.
  const watch = (jobId, isBroad) => {
    lock(true);
    setReviewApplication(false);
    ledger.reset();
    root.querySelector(".runner-death")?.remove();
    sendBtn.disabled = true; sendBtn.textContent = "THE BINDER WORKS...";
    historyBtn.disabled = true;
    $("#binder-q").disabled = true;
    out.classList.remove("hidden");
    actions.querySelectorAll(".binder-extra, .binder-cancel").forEach((b) => b.remove());
    const cx = document.createElement("button");
    cx.className = "btn danger binder-cancel"; cx.textContent = "STAY THE QUILL";
    cx.title = "Cancel this amendment";
    cx.onclick = async () => {
      cx.disabled = true;
      try {
        const r = await (await apiFetch("/api/amend/cancel", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: jobId }) })).json();
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
      try { st = await (await apiFetch("/api/amend/status?id=" + encodeURIComponent(jobId))).json(); } catch { return; }
      if (st.activity != null) {
        out.innerHTML = binderActivity(st.activity);
        out.scrollTop = out.scrollHeight;
      }
      if (st.status === "running") return;
      clearInterval(binderPoll);
      idle();
      if (st.status === "done") {
        if (st.review) {  // a survey, not an edit — show the findings and ask what to commission
          ledger.select(st.reportPath);
          setReviewApplication(true);
          out.innerHTML = mdLite((st.summary || "(the binder said nothing)")
            + `\n\n── THE SURVEY IS COMPLETE ──\nThe full report is inked at ${st.reportPath || "the reviews/ ledger"}.`
            + "\nWould you have changes made? Describe them above and SEND — the Binder will read its own report first, and the Broad change box governs how far the quill reaches.")
            + binderCost(st.apiCostEstimate);
          qBox.value = REVIEW_FIX_REQUEST; qBox.focus();
          return;
        }
        out.innerHTML = mdLite((st.summary || "(the binder said nothing)")
          + (st.validatorOk === false ? "\n\n⚠ THE CANDLE FINDS FLAWS:\n" + (st.validator || "") : ""))
          + binderCost(st.apiCostEstimate);
        sendBtn.textContent = "RESET"; sendBtn.onclick = freshSlate;
        sendBtn.title = "Clear the bench — feed, request, and boxes — and start a new amendment.";
        const rb = document.createElement("button");
        rb.className = "btn binder-extra"; rb.textContent = "RE-OPEN THE TOME";
        rb.onclick = () => location.reload();
        actions.prepend(rb);
        if (st.validatorOk === false && st.validator) {
          const fx = document.createElement("button");
          fx.className = "btn binder-extra"; fx.textContent = "MEND THE FLAWS";
          fx.onclick = () => {
            $("#binder-q").value = "Fix every ERROR and WARN the validator reports below. Address each one; do not skip any.\n\n" + st.validator;
            send();   // the quill now reads RESET, so the mend has to call the send itself
          };
          actions.prepend(fx);
        }
      } else if (st.status === "cancelled") {
        out.textContent = "THE QUILL IS STAYED — the amendment was cancelled and the tome was restored to how it stood before it began. The request is kept, so it can be taken up again.";
        offerResume();   // stopping mid-stroke is exactly when you want to resume
      } else {  // error / unknown — a real failure or timeout
        const msg = st.error || "unknown error";
        if (isBroad) binderDeath(msg);              // forge-style: pick a new hand and retry
        else out.textContent = "THE QUILL SNAPPED — " + msg;
      }
    }, 2500);
  };
  // A declaration, not an assignment: idle() and the mend button both need it by name, and
  // the quill's own handler is swapped out for RESET once a run finishes.
  async function send() {
    const typedRequest = $("#binder-q").value.trim();
    const q = typedRequest || (ledger.selected() ? REVIEW_FIX_REQUEST : "");
    if (!q && !standard.checked && !it.checked && !rv.checked && !pub.checked) return;   // these modes need no typed request
    const p = BINDERY.find((x) => x.id === k.prov.value);
    if (!p || !k.model.value) { toast("Pick the Binder's <b>model</b> first.", "warn"); return; }
    const isBroad = pub.checked || bd.checked || it.checked || rv.checked;
    out.classList.remove("hidden");
    out.textContent = "the quill is dipped...";
    try {
      const r = await (await apiFetch("/api/amend", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request: q, kind: p.kind, model: k.model.value, effort: k.eff.value || undefined, broad: bd.checked, updateStandard: standard.checked, iterate: it.checked, resetOk: rs.checked, review: rv.checked, publish: pub.checked, reviewPath: (!rv.checked && ledger.selected()) || undefined }),
      })).json();
      if (!r.ok) throw new Error(r.error || "the binder did not answer");
      watch(r.jobId, isBroad);
    } catch (err) {
      out.textContent = "server error: " + err;
    }
  }
  sendBtn.onclick = send;
  actions.prepend(sendBtn, historyBtn);
  // On open: reattach to a job still inking in this server, else offer to resume one a lost
  // server/runner cut short. Runs after the model list loads so the resume card has hands to pick.
  function reattachOrResume() {
    apiFetch("/api/amend/current").then((r) => r.json()).then((d) => {
      if (d.jobId) {
        const q = $("#binder-q");
        if (q && !q.value) q.value = d.request || "";
        out.classList.remove("hidden");
        out.textContent = "the Binder is already at work on this tome — watching that job...";
        watch(d.jobId, !!(d.broad || d.review));
        return;
      }
      offerResume();
    }).catch(() => { /* no reattach; the bench still works */ });
  }
  setTimeout(() => { const f = $("#binder-q"); if (f) f.focus(); }, 50);
}
