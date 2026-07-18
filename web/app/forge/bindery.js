/* Tome shelf plus the persistent author's interactive workbench. */
import { $, closeModal, dropOverlay, esc, modal, sfx } from "../core/dom.js";
import { enhanceSelect } from "../ui/menu.js";
import { forgeEntry } from "./forge.js";
import { mergeForgeTraceLines } from "./trace-lines.js";
import { fallbackCourseControl, formatCourseBlockers } from "./course-control.js";

export const FORGE_PHASES = ["Concept & arc", "Skeleton & voice", "Sections", "Minigames",
  "Economy", "Cosmetics", "Validate", "Student review"];
export const FORGE_PHASE_NAMES = ["", ...FORGE_PHASES];

let forgeOverlay = null;
let forgePoll = 0;

export async function fetchActiveBuilds({ failClosed = false } = {}) {
  try {
    const builds = (await (await fetch("/api/buildtome/active")).json()).jobs || [];
    return await Promise.all(builds.map(async (build) => {
      try {
        const status = await (await fetch(`/api/buildtome/status?id=${encodeURIComponent(build.id)}`)).json();
        return { ...build, ...status, id: build.id };
      } catch { return build; }
    }));
  }
  catch (error) {
    if (failClosed) throw error;
    return [];
  }
}

export function showTomePicker() {
  const list = window.TOMES_LIST || [], active = window.__ACTIVE_TOME;
  const rows = list.filter((tome) => !tome.draft).map((tome) => `
    <button class="tome-row${tome.id === active ? " active" : ""}" data-tome="${esc(tome.id)}"${tome.id === active ? " disabled" : ""}>
      <div class="jr-top"><span class="jr-name">${esc(tome.name || tome.id)}</span><span class="jr-tag num">${esc(tome.runtime || "")}${tome.sectionCount != null ? ` · ${tome.sectionCount} chapters` : ""}</span></div>
      <div class="jr-desc dim">${esc(tome.description || "")}</div><div class="jr-foot faint">${esc(tome.author || "")}</div>
    </button>`).join("");
  modal(`<h2>THE SHELF OF TOMES</h2><p class="dim shelf-intro">Choose a tome, or open a live author session.</p>
    <div class="tome-list"><button class="tome-row forge checking" id="tome-forge" disabled aria-busy="true">
      <div class="jr-top"><span class="jr-name">＋ FORGE A NEW TOME</span><span class="jr-tag num" id="tome-forge-state">checking bindery</span></div>
      <div class="jr-desc dim" id="tome-forge-note">Checking whether another tome is currently being forged.</div>
    </button><div id="forge-active" style="display:contents"></div>${rows || '<p class="dim">The shelf is bare.</p>'}</div>`,
    [["LEAVE THE SHELF", "quiet", null]]);
  const forgeButton = $("#tome-forge"), forgeState = $("#tome-forge-state"),
        forgeNote = $("#tome-forge-note"), activeSlot = $("#forge-active");
  forgeButton.onclick = () => { if (!forgeButton.disabled) closeModal(forgeEntry); };
  document.querySelectorAll("#modal-root .tome-row[data-tome]").forEach((button) => {
    button.onclick = () => { localStorage.setItem("activeTome", button.dataset.tome); location.reload(); };
  });
  const refreshActiveBuilds = async () => {
    if (!forgeButton.isConnected) return;
    try {
      const builds = await fetchActiveBuilds({ failClosed: true });
      if (!forgeButton.isConnected) return;
      const busy = builds.length > 0;
      forgeButton.disabled = busy;
      forgeButton.classList.toggle("busy", busy);
      forgeButton.classList.remove("checking");
      forgeButton.setAttribute("aria-busy", "false");
      forgeState.textContent = busy ? "author busy" : "single author";
      forgeNote.textContent = busy
        ? "Finish or abandon the current working before forging another tome."
        : "Route the key phase ranges to chosen AIs, watch their tools, and guide the working.";
      activeSlot.innerHTML = builds.map((build) => `<button class="tome-row forging" data-job="${esc(build.id)}" data-trace="${esc(build.traceId || build.id)}" data-state="${esc(build.interactionState || "running")}">
      <div class="jr-top"><span class="jr-name">${esc(build.name || "Untitled")}</span><span class="jr-tag num">${esc(build.interactionState || "authoring")}</span></div>
      <div class="jr-desc">Phase ${build.phase || 1} / 8 — ${esc(build.phaseTitle || "starting")}</div></button>`).join("");
      activeSlot.querySelectorAll("[data-job]").forEach((button) => {
      button.onclick = () => closeModal(() => openBuildOverlay(button.dataset.job, button.dataset.trace));
      });
    } catch {
      if (!forgeButton.isConnected) return;
      forgeButton.disabled = true;
      forgeButton.classList.add("checking");
      forgeButton.setAttribute("aria-busy", "true");
      forgeState.textContent = "status unavailable";
      forgeNote.textContent = "The bindery must confirm no tome is active before starting another.";
    }
    if (forgeButton.isConnected) setTimeout(refreshActiveBuilds, 3000);
  };
  refreshActiveBuilds();
}

function phaseLine(status, interactionState) {
  let line = `Phase ${status.phase || 1} / 8 — ${status.phaseTitle || "starting"}`;
  const section = status.sectionProgress;
  if (Number(status.phase) === 3 && section?.section)
    line += ` — ${section.section} · ${section.index}/${section.total} · ${section.state}`;
  const active = ["running", "starting", "resuming"].includes(interactionState);
  if (active && status.phaseState) line += ` — ${status.phaseState}`;
  else if (interactionState) line += ` — ${interactionState}`;
  if (active && status.activityStartedAt) {
    const seconds = Math.max(0, Math.floor(Date.now() / 1000 - status.activityStartedAt));
    line += ` — ${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`;
  }
  return line;
}

function paintCourseControl(overlay, control, sessionUsage) {
  const panel = $("#fp-course-control", overlay);
  if (!control?.spine?.length) { panel.classList.add("hidden"); return; }
  panel.classList.remove("hidden");
  const compactTokens = (value) => Number(value || 0) >= 1000000
    ? `${(Number(value) / 1000000).toFixed(1)}M`
    : Number(value || 0) >= 1000 ? `${(Number(value) / 1000).toFixed(1)}K` : String(Number(value || 0));
  const usage = sessionUsage || {};
  const hasSessionUsage = ["inputTokens", "freshInputTokens", "cachedInputTokens",
    "cacheWriteTokens", "outputTokens"].some((key) => Number(usage[key] || 0) > 0);
  const usageText = hasSessionUsage
    ? ` · ${compactTokens(usage.freshInputTokens)} FRESH · ${compactTokens(usage.cachedInputTokens)} CACHED · ${compactTokens(usage.cacheWriteTokens)} WRITE · ${compactTokens(usage.outputTokens)} OUT`
    : "";
  const summary = control.fallback
    ? `SECTION MAP · ${control.currentIndex || 1}/${control.spine.length} · STATUS FALLBACK`
    : `${control.openObligations || 0} OBLIGATIONS OPEN · ${control.dueObligations || 0} DUE NOW`;
  $("#fp-course-summary", panel).textContent = summary + usageText;
  $("#fp-course-spine", panel).innerHTML = control.spine.map((row) =>
    `<div class="forge-course-row${row.id === control.currentSection ? " current" : ""}" data-status="${esc(row.status)}"
      aria-label="${esc(row.id)} ${esc(row.statusLabel)}: ${esc(row.title)}">
      <span class="forge-course-mark" aria-hidden="true">${esc(row.mark)}</span><span class="num">${esc(row.id)}</span>
      <span class="forge-course-title">${esc(row.title)}</span><span class="forge-course-milestone">${esc(row.milestone)}</span></div>`).join("");
  const blockers = Array.isArray(control.blockers) ? control.blockers : [];
  const blockerBox = $("#fp-course-blockers", panel);
  const blockerText = formatCourseBlockers(blockers);
  blockerBox.classList.toggle("hidden", !blockerText);
  blockerBox.textContent = blockerText;
}

function messageStamp(value) {
  const raw = Number(value);
  if (!Number.isFinite(raw)) return null;
  const date = new Date(raw < 1e12 ? raw * 1000 : raw);
  if (Number.isNaN(date.getTime())) return null;
  return {
    iso: date.toISOString(),
    label: date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
  };
}

export function openBuildOverlay(jobId, traceId = jobId) {
  if (forgeOverlay) {
    if (forgeOverlay.dataset.job === jobId) { forgeOverlay.classList.remove("hidden"); return; }
    clearInterval(forgePoll); forgeOverlay.remove();
  }
  const overlay = document.createElement("div");
  overlay.className = "grade-overlay forge-progress";
  overlay.dataset.job = jobId;
  overlay.innerHTML = `<div class="grade-card forge-session-card">
    <header class="forge-session-head"><div><div class="faint forge-kicker">THE BINDERY // SINGLE AUTHOR</div>
      <h2 id="fp-name">Reattaching…</h2><div class="forge-session-meta"><div id="fp-phase">Phase 1 / 8 — starting</div>
        <div class="forge-session-model"><span>MODEL</span><strong id="fp-model">ATTACHING…</strong></div></div></div>
      <div class="forge-session-badge" id="fp-session-state">ATTACHING</div></header>
    <div class="forge-phases">${FORGE_PHASES.map((title, index) => `<div class="forge-phase" data-ph="${index + 1}">
      <span class="num">${index + 1}</span><span>${esc(title)}</span><span class="fp-mark num"></span></div>`).join("")}</div>
    <section class="forge-course-control hidden" id="fp-course-control" aria-label="Harness course control">
      <div class="forge-course-head"><span>COURSE CONTROL</span><span id="fp-course-summary" class="num"></span></div>
      <div class="forge-course-spine" id="fp-course-spine"></div>
      <div class="forge-course-blockers hidden" id="fp-course-blockers" role="status"></div>
    </section>
    <div class="forge-workbench">
      <section class="forge-terminal-panel"><div class="forge-panel-head"><span id="fp-trace-source">AUTHOR TOOL HISTORY</span><span id="fp-trace-count">0 CALLS</span></div>
        <div class="forge-terminal num" id="fp-trace-lines"><div class="forge-trace-empty">Attaching to the author's session log…</div></div></section>
      <section class="forge-chat-panel"><div class="forge-panel-head"><span>CONVERSATION</span><span id="fp-session-id">NO SESSION ID YET</span></div>
        <div class="forge-conversation" id="fp-conversation"><div class="forge-chat-empty">The author's messages and your guidance will appear here.</div></div>
        <form class="forge-composer" id="fp-composer"><textarea id="fp-message" rows="3" placeholder="Guide the author in this same session…"></textarea>
          <div class="forge-composer-actions"><span class="faint">Ctrl + Enter to send</span><div class="forge-console-actions">
            <button class="forge-console-btn" id="fp-pause" type="button">PAUSE AUTHOR</button>
            <button class="forge-console-btn primary" id="fp-send" type="submit">SEND</button></div></div></form></section>
    </div>
    <div class="forge-fail-bar hidden" id="fp-fail">
      <div class="forge-fail-msg" id="fp-fail-msg"></div>
      <div class="forge-fail-controls">
        <div class="forge-ai-row">
          <div class="forge-ai-choice"><select id="fp-alt-prov" class="cfg-select" aria-label="Replacement agent CLI"></select></div>
          <div class="forge-ai-choice"><select id="fp-alt-model" class="cfg-select" aria-label="Replacement model"></select></div>
          <div class="forge-ai-choice"><select id="fp-alt-eff" class="cfg-select" aria-label="Replacement effort"><option value="">DEFAULT</option></select></div>
        </div>
        <div class="forge-console-actions"><button class="forge-console-btn" id="fp-alt-resume" type="button">RESUME WITH THIS AI</button></div>
      </div>
    </div>
    <div class="forge-session-actions"><button class="btn danger" id="fp-cancel">ABANDON</button>
      <div><button class="btn quiet" id="fp-leave">LEAVE · WORK CONTINUES</button></div></div>
  </div>`;
  document.body.appendChild(overlay); forgeOverlay = overlay;
  $("#fp-leave", overlay).onclick = () => overlay.classList.add("hidden");

  let lastStatus = null, retainedTooling = null, conversationKey = "", traceKey = "",
      armed = 0, pauseTransition = "";
  let fallbackKey = "", fallbackControl = null;
  const pause = $("#fp-pause", overlay), composer = $("#fp-composer", overlay),
        message = $("#fp-message", overlay);
  async function post(path, body = {}) {
    const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: jobId, ...body }) });
    const data = await response.json();
    if (!data.ok) throw new Error(data.error || "request failed");
    return data;
  }
  pause.onclick = async () => {
    pauseTransition = lastStatus?.interactionState === "paused" ? "resume" : "pause";
    pause.disabled = true;
    pause.textContent = pauseTransition === "pause" ? "PAUSING…" : "RESUMING…";
    try {
      if (pauseTransition === "resume") await post("/api/buildtome/continue");
      else await post("/api/buildtome/pause");
    } catch (error) {
      pauseTransition = "";
      pause.disabled = false;
      pause.title = String(error.message || error);
    }
    tick();
  };
  composer.onsubmit = async (event) => {
    event.preventDefault(); const text = message.value.trim(); if (!text) return;
    const send = $("#fp-send", overlay); send.disabled = true;
    try { await post("/api/buildtome/message", { text }); message.value = ""; }
    catch (error) { message.setCustomValidity(String(error.message || error)); message.reportValidity(); }
    finally { send.disabled = false; }
  };
  message.onkeydown = (event) => {
    if (event.ctrlKey && event.key === "Enter") composer.requestSubmit();
    else message.setCustomValidity("");
  };
  const fail = $("#fp-fail", overlay), failMsg = $("#fp-fail-msg", overlay),
        altProv = $("#fp-alt-prov", overlay), altModel = $("#fp-alt-model", overlay),
        altEff = $("#fp-alt-eff", overlay), altResume = $("#fp-alt-resume", overlay);
  let altProviders = null;
  const fillAltEfforts = () => {
    const provider = (altProviders || []).find((item) => item.id === altProv.value);
    const row = provider && (provider.models || []).find((item) => item[0] === altModel.value);
    const levels = (row && row[3]) || [];
    altEff.innerHTML = `<option value="">DEFAULT</option>` + levels.map((level) =>
      `<option value="${esc(level)}">${esc(String(level).toUpperCase())}</option>`).join("");
    altEff.disabled = !levels.length;
  };
  const fillAltModels = () => {
    const provider = (altProviders || []).find((item) => item.id === altProv.value);
    const rows = (provider && provider.models) || [];
    altModel.innerHTML = rows.map(([id, label, tag]) => `<option value="${esc(id)}">${esc(label)}${tag ? ` · ${esc(tag)}` : ""}</option>`).join("")
      || `<option value="">NO MODELS</option>`;
    altModel.disabled = !rows.length;
    fillAltEfforts();
  };
  altProv.onchange = fillAltModels;
  altModel.onchange = fillAltEfforts;
  async function armAltPicker(current) {
    if (altProviders) return;
    try {
      const data = await (await fetch("/api/models")).json();
      altProviders = (data.bindery || []).filter((item) => item.installed !== false && (item.models || []).length);
    } catch { return; /* a later failure poll retries */ }
    [altProv, altModel, altEff].forEach(enhanceSelect);
    altProv.innerHTML = altProviders.map((item) => `<option value="${esc(item.id)}">${esc(item.label)}</option>`).join("");
    const match = current && altProviders.find((item) => item.kind === current.kind);
    if (match) altProv.value = match.id;
    fillAltModels();
    if (current?.model && [...altModel.options].some((option) => option.value === current.model)) altModel.value = current.model;
    fillAltEfforts();
    if (current?.effort && [...altEff.options].some((option) => option.value === current.effort)) altEff.value = current.effort;
  }
  altResume.onclick = async () => {
    const provider = (altProviders || []).find((item) => item.id === altProv.value);
    if (!provider || !altModel.value) return;
    altResume.disabled = true;
    const author = { kind: provider.kind, model: altModel.value, ...(altEff.value ? { effort: altEff.value } : {}) };
    try { await post("/api/buildtome/continue", { author }); fail.classList.add("hidden"); }
    catch (error) { altResume.title = String(error.message || error); }
    finally { altResume.disabled = false; }
    tick();
  };

  const cancel = $("#fp-cancel", overlay);
  cancel.onclick = async () => {
    if (!armed) {
      cancel.textContent = "CLICK AGAIN TO ABANDON";
      armed = setTimeout(() => { armed = 0; cancel.textContent = "ABANDON"; }, 4000); return;
    }
    clearTimeout(armed); cancel.disabled = true;
    try { await post("/api/buildtome/cancel"); } catch { /* status polling resolves it */ }
    tick();
  };

  function paint(status, tooling) {
    lastStatus = status;
    $("#fp-name", overlay).textContent = status.name || status.tome || "Untitled";
    const reportedState = String(status.interactionState || "running");
    if ((pauseTransition === "pause" && reportedState === "paused")
        || (pauseTransition === "resume" && reportedState === "running")) pauseTransition = "";
    const state = pauseTransition === "pause" ? "pausing"
      : pauseTransition === "resume" ? "resuming" : reportedState;
    const phase = $("#fp-phase", overlay);
    phase.textContent = phaseLine(status, state);
    phase.dataset.state = state;
    const author = status.sessionAuthor || {};
    $("#fp-model", overlay).textContent = author.model
      ? `${author.model}${author.effort ? ` · ${String(author.effort).toUpperCase()} EFFORT` : ""}`
      : status.runner || "ATTACHING…";
    $("#fp-session-state", overlay).textContent = state.toUpperCase();
    $("#fp-session-state", overlay).dataset.state = state;
    $("#fp-session-id", overlay).textContent = status.sessionId ? `SESSION ${status.sessionId.slice(0, 12)}` : "SESSION STARTING";
    const reviewerActive = status.sessionRole === "reviewer";
    $("#fp-trace-source", overlay).dataset.role = reviewerActive ? "reviewer" : "author";
    pause.textContent = state === "paused" ? `RESUME ${reviewerActive ? "REVIEWER" : "AUTHOR"}`
      : state === "pausing" ? "PAUSING…" : state === "resuming" ? "RESUMING…"
      : state === "validating" ? "VALIDATING…" : `PAUSE ${reviewerActive ? "REVIEWER" : "AUTHOR"}`;
    pause.disabled = state === "pausing" || state === "resuming" || state === "validating";
    const authorDown = state === "paused" && status.sessionError;
    fail.classList.toggle("hidden", !authorDown);
    if (authorDown) { failMsg.textContent = status.sessionError; armAltPicker(status.sessionAuthor); }
    overlay.querySelectorAll(".forge-phase").forEach((row) => {
      const phase = Number(row.dataset.ph), current = Number(status.phase || 1);
      row.classList.toggle("done", phase < current || (phase === current && status.phaseState === "complete"));
      row.classList.toggle("now", phase === current && status.phaseState !== "complete");
      $(".fp-mark", row).textContent = phase < current || (phase === current && status.phaseState === "complete") ? "✓" : phase === current ? "•" : "";
    });
    paintCourseControl(overlay, status.courseControl, tooling?.usage);
    const traceAnchor = Number(tooling?.updatedAt) * 1000 || Date.now();
    const lines = mergeForgeTraceLines(tooling?.lines, status.logtail, traceAnchor);
    const nextTrace = lines.join("\0");
    if (nextTrace !== traceKey) {
      traceKey = nextTrace; const terminal = $("#fp-trace-lines", overlay);
      terminal.innerHTML = lines.length ? lines.map((line) =>
        `<div class="forge-terminal-line">${esc(line)}</div>`).join("")
        : `<div class="forge-trace-empty">Waiting for the author's first tool call…</div>`;
      terminal.scrollTop = terminal.scrollHeight;
      $("#fp-trace-source", overlay).textContent = `${String(tooling?.provider || (reviewerActive ? "REVIEWER" : "AUTHOR")).toUpperCase()} TOOL HISTORY`;
      $("#fp-trace-count", overlay).textContent = `${lines.length} CALL${lines.length === 1 ? "" : "S"}`;
    }
    const conversation = Array.isArray(status.conversation) ? status.conversation : [];
    const nextConversation = conversation.map((row) => `${row.at}:${row.kind}:${row.text}`).join("\0");
    if (nextConversation !== conversationKey) {
      conversationKey = nextConversation; const box = $("#fp-conversation", overlay);
      const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 50;
      box.innerHTML = conversation.length ? conversation.map((row) => {
        const stamp = messageStamp(row.at);
        return `<div class="forge-chat ${esc(row.kind)}"><div class="forge-chat-meta">
          <span class="forge-chat-role">${row.kind === "user" ? "YOU" : row.kind === "assistant" ? (row.role === "reviewer" ? "REVIEWER" : "AUTHOR") : row.kind === "harness" ? "HARNESS" : "SESSION"}</span>
          ${stamp ? `<time datetime="${esc(stamp.iso)}">${esc(stamp.label)}</time>` : ""}</div>
          <div class="forge-chat-text">${esc(row.text)}</div></div>`;
      }).join("") : `<div class="forge-chat-empty">Waiting for the author…</div>`;
      if (nearBottom) box.scrollTop = box.scrollHeight;
    }
  }

  async function finish(status) {
    clearInterval(forgePoll); overlay.classList.remove("hidden");
    if (localStorage.getItem("buildJob") === jobId) localStorage.removeItem("buildJob");
    const card = $(".grade-card", overlay), close = () => { forgeOverlay = null; dropOverlay(overlay); };
    if (status.status === "done") {
      sfx("grade"); card.innerHTML = `<div class="grading-anim"><div class="faint forge-kicker">THE BINDERY // COMPLETE</div>
        <h2>${esc(status.name || status.tome || "The tome")}</h2><p>${status.sessionRole === "reviewer"
          ? "Eight authoring phases, a thorough independent review of every file, and clean shipping gates."
          : "Eight phases, phase-routed author sessions, and clean shipping gates."}</p>
        <div class="modal-actions"><button class="btn quiet" id="fp-later">LEAVE ON THE SHELF</button><button class="btn" id="fp-open">OPEN THE TOME</button></div></div>`;
      $("#fp-open", card).onclick = () => { localStorage.setItem("activeTome", status.tome); location.reload(); };
      $("#fp-later", card).onclick = close;
    } else {
      card.innerHTML = `<div class="faint forge-kicker">THE BINDERY // ${status.status === "cancelled" ? "ABANDONED" : "SESSION STOPPED"}</div>
        <h2>${status.status === "cancelled" ? "The working was abandoned" : "The author session stopped"}</h2>
        <p class="dim">The pages and session record remain available under Unfinished Workings.</p>
        ${status.error ? `<pre class="forge-log">${esc(status.error)}</pre>` : ""}<div class="modal-actions"><button class="btn quiet" id="fp-close">CLOSE</button></div>`;
      $("#fp-close", card).onclick = close;
    }
  }

  async function tick() {
    try {
      const [statusResponse, traceResponse] = await Promise.all([
        fetch(`/api/buildtome/status?id=${encodeURIComponent(jobId)}`),
        fetch(`/.forge-trace/${encodeURIComponent(traceId)}.json?t=${Date.now()}`, { cache: "no-store" }).catch(() => null),
      ]);
      const status = await statusResponse.json();
      const tooling = traceResponse?.ok ? await traceResponse.json() : null;
      if (tooling?.lines?.length || !retainedTooling) retainedTooling = tooling;
      if (status.status === "running") {
        if (!status.courseControl && Number(status.phase) === 3 && status.tome) {
          const progress = status.sectionProgress || {};
          const key = `${status.tome}:${progress.section || ""}:${progress.index || 0}:${progress.total || 0}`;
          if (key !== fallbackKey) {
            fallbackKey = key; fallbackControl = null;
            try {
              const response = await fetch(`/api/tome?tome=${encodeURIComponent(status.tome)}`);
              if (response.ok) fallbackControl = fallbackCourseControl(await response.json(), status);
            } catch { /* the next status change retries */ }
          }
          status.courseControl = fallbackControl;
        }
        paint(status, retainedTooling);
      }
      else await finish(status);
    } catch { /* a later poll may reattach */ }
  }
  forgePoll = setInterval(tick, 2000); tick();
}
