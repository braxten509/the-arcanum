/* The shelf of tomes, the live forge overlay, and the "a hand has faltered" picker.

   POST /api/buildtome starts tools/build_tome.py on the server; the overlay below polls it.
   Leaving the overlay never stops the build — the shelf and localStorage.buildJob reattach. */
import { $, closeModal, dropOverlay, esc, modal, sfx } from "../core/dom.js";
import { forgeEntry, showToolingConflictApproval } from "./forge.js";
import { enhanceSelect } from "../ui/menu.js";
import { forgeActivityKey, forgeActivityOptions, forgeTraceLines } from "./activity.js";

export const FORGE_PHASES = ["Gate", "Concept & arc", "Skeleton & voice", "Sections", "Minigames",
  "Economy pass", "Cosmetics", "Validate", "Student review"];
export const FORGE_PHASE_NAMES = ["Gate", "Concept & arc", "Skeleton & voice", "Sections",
  "Minigames", "Economy", "Cosmetics", "Validate", "Student review"];

let forgeOverlay = null; // the one live progress overlay (null when none)
let forgePoll = 0;       // its status poller — always cleared before the overlay is dropped

export async function fetchActiveBuilds() {
  try { return (await (await fetch("/api/buildtome/active")).json()).jobs || []; }
  catch { return []; }
}

export function showTomePicker() {
  const list = window.TOMES_LIST || [];
  const active = window.__ACTIVE_TOME;
  // drafts (unfinished builds) never sit beside real tomes — they live in the
  // bindery's "Unfinished workings" chooser (forgeEntry) until finished or discarded
  const rows = list.filter((j) => !j.draft).map((j) => `
    <button class="tome-row${j.id === active ? " active" : ""}" data-tome="${esc(j.id)}"${j.id === active ? " disabled" : ""}>
      <div class="jr-top"><span class="jr-name">${esc(j.name || j.id)}</span>
        <span class="jr-tag num">${esc(j.runtime || "")}${j.sectionCount != null ? " · " + j.sectionCount + " chapters" : ""}</span></div>
      <div class="jr-desc dim">${esc(j.description || "")}</div>
      <div class="jr-foot faint">${esc(j.author || "")}${j.id === active ? " · OPEN ON THE DESK" : ""}</div>
    </button>`).join("");
  modal(`<h2>THE SHELF OF TOMES</h2>
    <p class="dim" style="font-size:12px;margin:2px 0 12px">Taking down another tome clears the desk and opens it. Each tome keeps its own progress, purse, and title.</p>
    <div class="tome-list">
      <button class="tome-row forge" id="tome-forge">
        <div class="jr-top"><span class="jr-name">＋ FORGE A NEW TOME</span><span class="jr-tag num">the bindery</span></div>
        <div class="jr-desc dim">Name a course you wish existed; the bindery writes it, chapter by chapter, while you study.</div>
      </button>
      <div id="forge-active" style="display:contents"></div>
      ${rows || '<p class="dim">The shelf is bare. Place a tome folder in /tomes and look again.</p>'}</div>`,
    [["LEAVE THE SHELF", "quiet", null]]);
  $("#tome-forge").onclick = () => closeModal(forgeEntry);
  document.querySelectorAll("#modal-root .tome-row[data-tome]").forEach((b) => {
    b.onclick = () => {
      const id = b.dataset.tome;
      if (id === window.__ACTIVE_TOME) return;
      localStorage.setItem("activeTome", id);
      location.reload();
    };
  });
  // any tome still on the bindery's anvil gets a live row that reopens its progress
  fetchActiveBuilds().then((builds) => {
    const slot = $("#forge-active");
    if (!slot || !builds.length) return;
    slot.innerHTML = builds.map((b) => `
      <button class="tome-row forging" data-job="${esc(b.id)}">
        <div class="jr-top"><span class="jr-name">${esc(b.name || "Untitled")}</span><span class="jr-tag num">being forged</span></div>
        <div class="jr-desc">Phase ${b.phase} / 9 — ${esc(b.phaseTitle || "")}</div>
      </button>`).join("");
    slot.querySelectorAll("[data-job]").forEach((el) => {
      el.onclick = () => {
        const build = builds.find((b) => b.id === el.dataset.job);
        closeModal(() => openBuildOverlay(el.dataset.job, build && build.traceId));
      };
    });
  });
}

// A build worker died and the harness (build_tome --ask-on-death) is blocked on a runner
// choice. Show a [PROVIDER][MODEL][EFFORT] picker over the forge card; POST the pick to
// /api/buildtome/runner and the working resumes from disk. One box per pause (idempotent).
function showRunnerDeath(overlay, jobId, info) {
  const gate = !!info.gate;   // a phase exhausted its gate retries (vs. a runner that died)
  const detail = gate
    ? `phase <b>${info.phase}</b> failed its gates (${esc(info.reason || "retries used")})`
    : `runner <b>${esc(info.dead || "?")}</b> died on <b>phase ${info.phase}</b> (${esc(info.reason || "no exit")})`;
  let box = overlay.querySelector(".runner-death");
  if (box) { const d = box.querySelector(".rd-detail"); if (d) d.innerHTML = detail; return; }
  box = document.createElement("div");
  box.className = "runner-death";
  box.innerHTML = `<div class="grade-card rd-card">
    <div class="faint" style="font-size:11px;letter-spacing:.2em">THE BINDERY // ${gate ? "THE GATES HELD FAST" : "A HAND HAS FALTERED"}</div>
    <h2 style="margin:8px 0 4px;font-family:var(--arch)">${gate ? "This phase would not pass" : "A runner has died"}</h2>
    <p class="rd-detail dim" style="font-size:12.5px;margin:0 0 6px">${detail}</p>
    ${gate ? `<div class="forge-log num" style="height:auto;max-height:150px;margin:0 0 10px">${esc(info.report || "")}</div>` : ""}
    <p class="dim" style="font-size:12px;margin:0 0 14px">${gate
      ? "Give it more tries, and/or hand it to a different model — either way it resumes this phase from the pages already on disk."
      : "Choose the hand that takes up the quill — the working resumes from where it left off on disk."}</p>
    <div class="forge-ai-row">
      <select class="cfg-select rd-prov" style="flex:0 0 auto;width:172px"></select>
      <select class="cfg-select rd-model" style="flex:1 1 auto;min-width:0" disabled><option value="">—</option></select>
      <select class="cfg-select rd-eff" style="flex:0 0 auto;width:104px" disabled><option value="">—</option></select>
    </div>
    ${gate ? `<label class="dim" style="display:flex;align-items:center;gap:8px;margin-top:10px;font-size:12.5px">MORE RETRIES <input class="cfg-select rd-retries" type="number" min="1" max="20" value="3" style="width:76px"></label>` : ""}
    <div class="modal-actions" style="margin-top:16px">
      <button class="btn danger rd-abort">${gate ? "GIVE UP ON THIS TOME" : "ABANDON THE WORKING"}</button>
      <button class="btn rd-resume"${gate ? "" : " disabled"}>${gate ? "RETRY THIS PHASE" : "RESUME THE WORKING"}</button>
    </div></div>`;
  overlay.appendChild(box);
  const prov = box.querySelector(".rd-prov"), model = box.querySelector(".rd-model"),
        eff = box.querySelector(".rd-eff"), resume = box.querySelector(".rd-resume"),
        retriesEl = box.querySelector(".rd-retries");
  let BINDERY = [];
  const fillEff = () => {
    const p = BINDERY.find((x) => x.id === prov.value);
    const m = p && (p.models || []).find((mm) => mm[0] === model.value);
    const lv = (m && m[3]) || [];
    eff.innerHTML = lv.length
      ? `<option value="">DEFAULT</option>` + lv.map((l) => `<option value="${esc(l)}">${esc(l.toUpperCase())}</option>`).join("")
      : `<option value="">—</option>`;
    eff.disabled = !lv.length;
  };
  const fillModel = () => {
    const p = BINDERY.find((x) => x.id === prov.value);
    const ms = (p && p.models) || [];
    // gate pause: a leading blank keeps THIS phase's current model and only adds retries
    const keep = gate ? `<option value="">— keep this phase's model —</option>` : "";
    const opts = ms.length
      ? ms.map(([v, l, tag]) => `<option value="${esc(v)}"${tag ? ` data-suffix="— ${esc(tag)}"` : ""}>${esc(l)}</option>`).join("")
      : "";
    model.innerHTML = (keep + opts) || `<option value="">—</option>`;
    model.disabled = !ms.length && !gate;
    resume.disabled = gate ? false : !ms.length;
    if (gate) model.value = "";  // default to keep-current
    fillEff();
  };
  prov.addEventListener("change", fillModel);
  model.addEventListener("change", fillEff);
  fetch("/api/models").then((r) => r.json()).then((d) => {
    BINDERY = (d.bindery || []).filter((p) => p.installed !== false);
    prov.innerHTML = BINDERY.map((p) => `<option value="${esc(p.id)}">${esc(p.label)}</option>`).join("");
    fillModel();
    try {  // default the provider to the writer pick they used at launch, if it's still offered
      const w = (JSON.parse(localStorage.getItem("binderyRunners") || "{}")).writer;
      if (w && w.prov && [...prov.options].some((o) => o.value === w.prov)) {
        prov.value = w.prov; fillModel();
        if (!gate && w.model && [...model.options].some((o) => o.value === w.model)) { model.value = w.model; fillEff(); }
      }
    } catch (e) { /* ignore */ }
  }).catch(() => {});
  [prov, model, eff].forEach(enhanceSelect);
  resume.onclick = async () => {
    const p = BINDERY.find((x) => x.id === prov.value);
    const switching = !!(p && model.value);        // a model chosen (gate: blank = keep current)
    if (!gate && !switching) return;               // a death MUST pick a replacement runner
    const retries = gate ? Math.max(1, parseInt((retriesEl && retriesEl.value) || "1", 10) || 1) : 0;
    resume.disabled = true; resume.textContent = "TAKING UP THE QUILL...";
    try {
      await fetch("/api/buildtome/runner", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: jobId,
          kind: switching ? p.kind : "", model: switching ? model.value : "",
          effort: switching ? (eff.value || "") : "", retries }) });
    } catch { /* the next poll re-shows the box if the harness is still waiting */ }
    box.remove();  // next poll shows the resumed phase (awaitingRunner gone)
  };
  box.querySelector(".rd-abort").onclick = async () => {
    try { await fetch("/api/buildtome/cancel", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: jobId }) }); } catch { /* poll reports the state */ }
    box.remove();
  };
}

export function openBuildOverlay(jobId, traceId = jobId) {
  if (forgeOverlay) {
    if (forgeOverlay.dataset.job === jobId) { forgeOverlay.classList.remove("hidden"); return; }
    clearInterval(forgePoll); forgeOverlay.remove(); forgeOverlay = null; // stale overlay for another job
  }
  const overlay = document.createElement("div");
  overlay.className = "grade-overlay forge-progress";
  overlay.dataset.job = jobId;
  overlay.innerHTML = `<div class="grade-card">
    <div class="faint" style="font-size:11px;letter-spacing:.2em">THE BINDERY // A TOME IS BEING FORGED</div>
    <div style="font-family:var(--arch);font-size:20px;margin:10px 0 2px" id="fp-name"></div>
    <div id="fp-phase">reattaching to the working…</div>
    <div class="forge-phases">${FORGE_PHASES.map((t, i) => `
      <div class="forge-phase" data-ph="${i}"><span class="num">${i}</span><span>${esc(t)}</span><span class="fp-mark num"></span></div>`).join("")}</div>
    <div class="forge-activity num" id="fp-activity" aria-label="Current forge activity">
      <span class="forge-activity-pulse" aria-hidden="true"></span>
      <span class="forge-activity-kicker" aria-hidden="true">NOW</span>
      <span class="forge-activity-text" id="fp-activity-text">Reattaching to the working…</span>
    </div>
    <div class="forge-trace num" id="fp-trace" aria-label="Live AI tooling trace">
      <div class="forge-trace-head"><span id="fp-trace-source">LIVE AI TOOLING</span><span>LAST 3 CALLS</span></div>
      <div class="forge-trace-lines" id="fp-trace-lines"><div class="forge-trace-empty">Waiting for the AI's next tool call…</div></div>
    </div>
    <div class="dim" style="margin-top:12px;font-size:12px;font-style:italic">a full tome takes a long while — leave, and the bindery works on; the shelf remembers it.</div>
    <div class="modal-actions">
      <button class="btn danger" id="fp-cancel">ABANDON THE WORKING</button>
      <button class="btn quiet" id="fp-leave">LEAVE THE BINDERY (work continues)</button>
    </div></div>`;
  document.body.appendChild(overlay);
  forgeOverlay = overlay;
  $("#fp-leave", overlay).onclick = () => overlay.classList.add("hidden");

  const cbtn = $("#fp-cancel", overlay);
  let armed = 0; // two-step: a stray click must not douse an hour of work
  cbtn.onclick = async () => {
    if (!armed) {
      cbtn.textContent = "CLICK AGAIN TO ABANDON";
      armed = setTimeout(() => { armed = 0; cbtn.textContent = "ABANDON THE WORKING"; }, 4000);
      return;
    }
    clearTimeout(armed);
    cbtn.disabled = true; cbtn.textContent = "DOUSING THE FORGE...";
    try {
      await fetch("/api/buildtome/cancel", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: jobId }) });
    } catch { /* the poll below will report whatever state remains */ }
    tick(); // observe the cancelled state now rather than on the next 3s beat
  };

  // Active-phase line: "Phase 3 / 9 — Sections … — 3/8 — gpt-5.4-mini @high — 12m 04s".
  // sections (X/Y) appears only in split phase 3; runner drops its CLI prefix; the clock
  // is time-in-phase from the server's phaseStartedAt, repainted every second below.
  let lastSt = null, activityIndex = 0, activityKey = "", traceKey = "";
  const phaseLine = (st) => {
    let s = `Phase ${st.phase} / ${st.totalPhases || 9} — ${st.phaseTitle || "…"}`;
    if (st.sections) s += ` — ${st.sections}`;
    if (st.runner) s += ` — ${st.runner.replace(/^(?:claude|codex|antigravity|opencode)-cli\s+/, "")}`;
    if (st.phaseStartedAt) {
      const sec = Math.max(0, Math.round(Date.now() / 1000 - st.phaseStartedAt));
      s += ` — ${Math.floor(sec / 60)}m ${String(sec % 60).padStart(2, "0")}s`;
    }
    return s;
  };
  function paintActivity(st, advance = false) {
    const nextKey = forgeActivityKey(st);
    if (nextKey !== activityKey) {
      activityKey = nextKey;
      activityIndex = 0;
    } else if (advance) {
      activityIndex += 1;
    }
    const options = forgeActivityOptions(st);
    const text = options[activityIndex % options.length] || "The bindery is working";
    const line = $("#fp-activity-text", overlay);
    if (line && line.textContent !== text) line.textContent = text;
  }
  function paintTrace(st) {
    // `toolTrace` comes from the runner's own Codex/Claude JSONL—not forge stdout.
    // Never substitute the harness's edited narration here: the NOW line already owns that.
    const tooling = Array.isArray(st.toolTrace);
    const lines = tooling ? forgeTraceLines(st.toolTrace) : [];
    const nextKey = `${tooling ? "tooling" : "attaching"}\u0000${st.toolProvider || ""}\u0000${lines.join("\u0000")}`;
    if (nextKey === traceKey) return;
    traceKey = nextKey;
    $("#fp-trace-source", overlay).textContent = tooling
      ? `LIVE ${String(st.toolProvider || "AI").toUpperCase()} TOOLING` : "LIVE AI TOOLING";
    const box = $("#fp-trace-lines", overlay);
    box.innerHTML = lines.length
      ? lines.map((line) => `<div class="forge-trace-line" title="${esc(line)}">${esc(line)}</div>`).join("")
      : `<div class="forge-trace-empty">${tooling ? "Waiting for the AI's next tool call…"
        : "Attaching to the current AI's tool log…"}</div>`;
  }
  function paint(st) {
    lastSt = st;
    $("#fp-name", overlay).textContent = st.name || "Untitled";
    $("#fp-phase", overlay).textContent = phaseLine(st);
    overlay.querySelectorAll(".forge-phase").forEach((row) => {
      const i = +row.dataset.ph;
      row.classList.toggle("done", i < st.phase);
      row.classList.toggle("now", i === st.phase);
      $(".fp-mark", row).textContent = i < st.phase ? "✓" : i === st.phase ? "…" : "";
    });
    paintActivity(st);
    paintTrace(st);
  }

  async function finish(st) {
    overlay.classList.remove("hidden"); // surfaces the verdict even if they had left
    const card = $(".grade-card", overlay);
    const close = () => { forgeOverlay = null; dropOverlay(overlay); };
    if (st.status === "error" && String(st.error || "").includes("TOOLING_CONFLICT:")) {
      card.innerHTML = `<div class="faint" style="font-size:11px;letter-spacing:.2em">THE BINDERY // TOOLING APPROVAL REQUIRED</div>
        <h2 style="margin:8px 0 6px">The course needs a different workbench</h2>
        <p class="dim" style="font-size:12.5px">Preparing the exact Tooling change for your approval…</p>`;
      try {
        const data = await (await fetch("/api/buildtome/resumable")).json();
        const working = ((data && data.workings) || []).find((w) =>
          w.toolingConflict && (w.id === st.id || w.tome === st.tome));
        if (working) {
          forgeOverlay = null;
          dropOverlay(overlay, () => showToolingConflictApproval(working));
          return;
        }
      } catch { /* fall through to the normal durable failure card */ }
    }
    if (st.status === "done") {
      sfx("grade");
      card.innerHTML = `<div class="grading-anim">
        <div class="faint" style="font-size:11px;letter-spacing:.2em">THE BINDERY // THE WORK IS DONE</div>
        <div style="font-family:var(--arch);font-size:22px;margin:14px 0 6px">${esc(st.name || st.tome || "")}</div>
        <p class="dim" style="font-size:13px;margin:0 0 6px">Nine phases, written and reviewed. The tome stands bound upon the shelf.</p>
        <div class="modal-actions" style="justify-content:center">
          <button class="btn quiet" id="fp-later">LEAVE IT ON THE SHELF</button>
          <button class="btn" id="fp-open">OPEN IT ON THE DESK</button>
        </div></div>`;
      $("#fp-open", card).onclick = () => { localStorage.setItem("activeTome", st.tome); location.reload(); };
      $("#fp-later", card).onclick = close;
    } else if (st.status === "cancelled") {
      card.innerHTML = `<div class="faint" style="font-size:11px;letter-spacing:.2em">THE BINDERY // THE WORKING WAS ABANDONED</div>
        <h2 style="margin:8px 0 6px">The forge is doused</h2>
        <p class="dim" style="font-size:12.5px">Whatever pages were already struck remain in <span class="num">tomes/${esc(st.tome || "")}</span> and <span class="num">.tome-build/</span> — inspect or delete them at your leisure.</p>
        <div class="modal-actions"><button class="btn quiet" id="fp-close">SO BE IT</button></div>`;
      $("#fp-close", card).onclick = close;
    } else { // "error", or "unknown" (the candle was relit and the record lost)
      const lost = st.status === "unknown";
      card.innerHTML = `<div class="faint" style="font-size:11px;letter-spacing:.2em">THE BINDERY // ${lost ? "THE RECORD IS LOST" : "THE WORKING FAILED"}</div>
        <h2 style="margin:8px 0 6px">${lost ? "The candle was relit" : esc(st.name || "The tome") + " would not bind"}</h2>
        ${lost ? '<p class="dim" style="font-size:12.5px">The desk was restarted and no longer holds this working’s record. If it finished, its tome waits in /tomes.</p>'
      : `<div class="forge-log num" style="height:auto;max-height:180px">${esc(st.error || st.logtail || "no record of the failure")}</div>
        <p class="dim" style="font-size:12.5px;margin-top:12px">Its partial pages remain in <span class="num">tomes/${esc(st.tome || "")}</span> and now appear under Unfinished Workings, ready to resume from Phase ${esc(st.phase ?? "?")}.</p>`}
        <div class="modal-actions"><button class="btn quiet" id="fp-close">SO BE IT</button></div>`;
      $("#fp-close", card).onclick = close;
    }
  }

  async function tick() {
    let st;
    try {
      const [statusResponse, toolingResponse] = await Promise.all([
        fetch("/api/buildtome/status?id=" + encodeURIComponent(jobId)),
        fetch(`/.forge-trace/${encodeURIComponent(traceId)}.json?t=${Date.now()}`, { cache: "no-store" })
          .catch(() => null),
      ]);
      st = await statusResponse.json();
      if (toolingResponse && toolingResponse.ok) {
        const tooling = await toolingResponse.json();
        if (tooling.active && Array.isArray(tooling.lines)) {
          st.toolTrace = tooling.lines;
          st.toolProvider = tooling.provider || "AI";
        }
      }
    } catch { return; }
    if (st.status === "running") {
      paint(st);
      if (st.awaitingRunner) {                          // a worker died; the harness is waiting on us
        overlay.classList.remove("hidden");             // surface it even if they'd left the bindery
        showRunnerDeath(overlay, jobId, st.awaitingRunner);
      } else { const b = overlay.querySelector(".runner-death"); if (b) b.remove(); }
      return;
    }
    { const b = overlay.querySelector(".runner-death"); if (b) b.remove(); }
    clearInterval(forgePoll);
    if (localStorage.getItem("buildJob") === jobId) localStorage.removeItem("buildJob");
    await finish(st);
  }
  // one interval: poll the server every 3rd beat, tick the phase clock on the others
  let beat = 0;
  forgePoll = setInterval(() => {
    if (++beat % 3 === 0) tick();
    else if (lastSt) $("#fp-phase", overlay).textContent = phaseLine(lastSt);
    if (lastSt && beat % 5 === 0) paintActivity(lastSt, true);
  }, 1000);
  tick();
}
