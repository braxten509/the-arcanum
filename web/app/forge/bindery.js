/* Tome shelf plus the persistent author's interactive workbench. */
import { $, dropOverlay, esc, sfx } from "../core/dom.js";
import { enhanceSelect, shedPixels } from "../ui/menu.js";
import { matchProvider } from "./forge.js";
import { fallbackForgeRunningCost, forgeHarnessValidationState, formatForgeRunningCost,
  formatForgeWeeklyUsage, mergeForgeConversationCosts, mergeForgeTraceLines } from "./trace-lines.js";
import { fallbackCourseControl } from "./course-control.js";
import { apiFetch } from "../core/api-client.js";
import { FORGE_PHASES } from "./phases.js";
import {
  fetchActiveBuilds,
  showTomePicker as renderTomePicker,
} from "./bindery/shelf.js";
import {
  messageStamp, paintCourseControl, phaseLine,
} from "./bindery/presentation.js";

export { fetchActiveBuilds };

let forgeOverlay = null;
let forgePoll = 0;

export function showTomePicker() {
  renderTomePicker(openBuildOverlay);
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
      <div class="forge-session-status"><div class="forge-session-badge" id="fp-session-state">ATTACHING</div>
        <div class="forge-running-cost hidden" id="fp-running-cost" aria-live="polite" aria-atomic="true">
          <button type="button" class="forge-running-cost-total" id="fp-running-cost-toggle" aria-expanded="false" aria-controls="fp-cost-breakdown">
            <span>Running Cost:</span><output id="fp-running-cost-value">$0.00</output></button>
          <em id="fp-weekly-usage">(0.00% weekly usage)</em>
          <div class="forge-cost-breakdown" id="fp-cost-breakdown" role="group" aria-label="Cost breakdown"></div></div></div></header>
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
          <div class="forge-ai-choice"><select id="fp-alt-prov" class="cfg-select" aria-label="Replacement AI provider"></select></div>
          <div class="forge-ai-choice"><select id="fp-alt-model" class="cfg-select" aria-label="Replacement model"></select></div>
          <div class="forge-ai-choice"><select id="fp-alt-eff" class="cfg-select" aria-label="Replacement effort"><option value="">DEFAULT</option></select></div>
        </div>
        <label class="forge-cost-limit hidden" id="fp-alt-cost-wrap">
          <span class="forge-cost-limit-label">SECTION STOP</span>
          <span class="forge-cost-input"><span class="forge-cost-currency" aria-hidden="true">$</span>
            <input id="fp-alt-cost" type="number" step="any" value="2" inputmode="decimal" aria-label="Phase 3 section hard stop in dollars"></span>
        </label>
        <button class="btn" id="fp-alt-resume" type="button">RESUME AUTHOR WITH THIS AI</button>
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
  const costToggle = $("#fp-running-cost-toggle", overlay), costBreakdown = $("#fp-cost-breakdown", overlay);
  let costCloseTimer = 0, costOpenTimer = 0, costBreakdownMarkup = "";
  const prepareCostBreakdown = () => {
    const rows = [...costBreakdown.children];
    const viewport = costBreakdown.getBoundingClientRect();
    const visible = rows.filter((row) => {
      const bounds = row.getBoundingClientRect();
      return bounds.bottom > viewport.top && bounds.top < viewport.bottom;
    });
    visible.forEach((row, index) => {
      row.style.setProperty("--i", index);
      row.style.setProperty("--o", visible.length - 1 - index);
    });
    costBreakdown.style.setProperty("--n", visible.length || 1);
  };
  const closeCostBreakdown = () => {
    if (!costBreakdown.classList.contains("open") || costBreakdown.classList.contains("closing")) return;
    costBreakdown.classList.remove("open");
    costBreakdown.classList.add("closing");
    costToggle.setAttribute("aria-expanded", "false");
    if (!matchMedia("(prefers-reduced-motion: reduce)").matches) {
      shedPixels(costBreakdown, costBreakdown);
    }
    clearTimeout(costCloseTimer);
    clearTimeout(costOpenTimer);
    costCloseTimer = setTimeout(() => costBreakdown.classList.remove("closing"),
      Number(costBreakdown.style.getPropertyValue("--n") || 1) * 30 + 180);
  };
  costToggle.onclick = () => {
    if (costBreakdown.classList.contains("open")) return closeCostBreakdown();
    clearTimeout(costCloseTimer);
    costBreakdown.classList.remove("closing");
    prepareCostBreakdown();
    costBreakdown.classList.add("open", "opening");
    costToggle.setAttribute("aria-expanded", "true");
    clearTimeout(costOpenTimer);
    costOpenTimer = setTimeout(() => costBreakdown.classList.remove("opening"),
      Number(costBreakdown.style.getPropertyValue("--n") || 1) * 34 + 220);
  };
  overlay.addEventListener("pointerdown", (event) => {
    if (!costBreakdown.classList.contains("open")
        || costBreakdown.contains(event.target) || costToggle.contains(event.target)) return;
    closeCostBreakdown();
  });

  const formatTurnTimestamp = (at) => {
    const date = new Date(Number(at) * 1000);
    if (Number.isNaN(date.getTime())) return "TIME UNAVAILABLE";
    return date.toLocaleString([], { month: "short", day: "2-digit", hour: "2-digit",
      minute: "2-digit", second: "2-digit" });
  };
  const turnBreakdownRows = (turns) => {
    const grouped = new Map();
    (Array.isArray(turns) ? turns : []).forEach((turn) => {
      const phase = Number(turn?.phase);
      if (!Number.isInteger(phase) || phase < 1 || phase > 8) return;
      if (!grouped.has(phase)) grouped.set(phase, []);
      grouped.get(phase).push(turn);
    });
    const turnRow = (turn) => {
        const amount = Number(turn?.apiEquivalentUsd);
        const price = Number.isFinite(amount) ? `$${amount.toFixed(2)}` : "UNPRICED";
        return `<div class="forge-cost-turn"><span class="forge-cost-turn-meta">${esc(formatTurnTimestamp(turn?.at))}</span><span class="forge-cost-turn-model">${esc(turn?.model || "Unknown model")}</span><span class="forge-cost-turn-price">${price}</span></div>`;
    };
    const totalLabel = (rows) => {
      const amounts = rows.map((turn) => Number(turn?.apiEquivalentUsd));
      const priced = amounts.filter(Number.isFinite);
      if (!priced.length) return "UNPRICED";
      return `$${priced.reduce((sum, amount) => sum + amount, 0).toFixed(2)}${priced.length < amounts.length ? "+" : ""}`;
    };
    const heading = (kind, label, rows) =>
      `<div class="${kind}"><span>${label}</span><strong>${totalLabel(rows)}</strong></div>`;
    return [...grouped.entries()].sort(([left], [right]) => left - right).flatMap(([phase, phaseTurns]) => {
      const orderedTurns = phaseTurns.sort((left, right) => Number(left?.at || 0) - Number(right?.at || 0));
      if (phase !== 3) return [heading("forge-cost-phase", `PHASE ${phase}`, orderedTurns),
        ...orderedTurns.map(turnRow)];
      const sections = new Map();
      orderedTurns.forEach((turn) => {
        const section = String(turn?.section || "unassigned").toUpperCase();
        if (!sections.has(section)) sections.set(section, []);
        sections.get(section).push(turn);
      });
      return [heading("forge-cost-phase", "PHASE 3", orderedTurns),
        ...[...sections.entries()].sort(([left], [right]) => left.localeCompare(right)).flatMap(([section, sectionTurns]) => [
          heading("forge-cost-section", `SECTION ${esc(section)}`, sectionTurns),
          ...sectionTurns.map(turnRow),
        ])];
    });
  };
  async function post(path, body = {}) {
    const response = await apiFetch(path, { method: "POST", headers: { "Content-Type": "application/json" },
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
        altEff = $("#fp-alt-eff", overlay), altResume = $("#fp-alt-resume", overlay),
        altCostWrap = $("#fp-alt-cost-wrap", overlay), altCost = $("#fp-alt-cost", overlay);
  const storedAltCost = Number(localStorage.getItem("binderySectionCostLimitUsd"));
  altCost.value = Number.isFinite(storedAltCost) && storedAltCost > 0
    ? String(storedAltCost) : "2";
  const validAltCost = () => Number.isFinite(Number(altCost.value))
    && Number(altCost.value) > 0;
  altCost.oninput = () => {
    altCost.dataset.edited = "true";
    altCost.setCustomValidity("");
  };
  altCost.onchange = () => {
    if (validAltCost())
      localStorage.setItem("binderySectionCostLimitUsd", altCost.value);
  };
  let altProviders = null, activeAltProviders = [], altRole = "", sectionBudgetKey = "";
  const fillAltEfforts = () => {
    const provider = activeAltProviders.find((item) => item.id === altProv.value);
    const row = provider && (provider.models || []).find((item) => item[0] === altModel.value);
    const levels = (row && row[3]) || [];
    altEff.innerHTML = `<option value="">DEFAULT</option>` + levels.map((level) =>
      `<option value="${esc(level)}">${esc(String(level).toUpperCase())}</option>`).join("");
    altEff.disabled = !levels.length;
  };
  const fillAltModels = () => {
    const provider = activeAltProviders.find((item) => item.id === altProv.value);
    const rows = (provider && provider.models) || [];
    altModel.innerHTML = rows.map(([id, label, tag]) => `<option value="${esc(id)}">${esc(label)}${tag ? ` · ${esc(tag)}` : ""}</option>`).join("")
      || `<option value="">NO MODELS</option>`;
    altModel.disabled = !rows.length;
    fillAltEfforts();
  };
  altProv.onchange = fillAltModels;
  altModel.onchange = fillAltEfforts;
  async function armAltPicker(current, role) {
    if (altRole === role) return;
    if (!altProviders) {
      try {
        const data = await (await apiFetch("/api/models")).json();
        altProviders = (data.bindery || []).filter((item) => item.installed !== false && (item.models || []).length);
      } catch { return; /* a later failure poll retries */ }
      [altProv, altModel, altEff].forEach(enhanceSelect);
    }
    altRole = role;
    activeAltProviders = altProviders.filter((item) => (item.roles || []).includes(role));
    altProv.innerHTML = activeAltProviders.map((item) => `<option value="${esc(item.id)}">${esc(item.label)}</option>`).join("");
    const match = matchProvider(activeAltProviders, current);
    if (match) altProv.value = match.id;
    fillAltModels();
    if (current?.model && [...altModel.options].some((option) => option.value === current.model)) altModel.value = current.model;
    fillAltEfforts();
    if (current?.effort && [...altEff.options].some((option) => option.value === current.effort)) altEff.value = current.effort;
  }
  altResume.onclick = async () => {
    const provider = activeAltProviders.find((item) => item.id === altProv.value);
    if (!provider || !altModel.value) return;
    if (!altCostWrap.classList.contains("hidden") && !validAltCost()) {
      altCost.setCustomValidity("Enter a positive dollar amount.");
      altCost.reportValidity();
      return;
    }
    altResume.disabled = true;
    const agent = { kind: provider.kind, model: altModel.value, ...(altEff.value ? { effort: altEff.value } : {}) };
    const payload = altRole === "validator" ? { validator: agent } : { author: agent };
    if (!altCostWrap.classList.contains("hidden")) {
      payload.sectionCostLimitUsd = Number(altCost.value);
      localStorage.setItem("binderySectionCostLimitUsd", altCost.value);
    }
    try {
      await post("/api/buildtome/continue", payload);
      fail.classList.add("hidden");
      altRole = ""; // the next failure re-arms from whichever agent is down then
    }
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
    const cost = status.aiRunningCost || status.gptRunningCost
      || fallbackForgeRunningCost(status.conversation, status.logtail);
    const currentTracked = /^(?:gpt-|claude-)/i.test(String(author.model || ""));
    const runningCost = $("#fp-running-cost", overlay);
    runningCost.classList.toggle("hidden", !currentTracked && !cost);
    $("#fp-running-cost-value", overlay).textContent = cost
      ? formatForgeRunningCost(cost) : "$0.00";
    $("#fp-weekly-usage", overlay).textContent = cost?.claudeTurnCount
      ? "(Claude/GPT API-equivalent total)"
      : cost ? formatForgeWeeklyUsage(cost) : "(0.00% weekly usage)";
    const breakdownRows = cost?.turns?.length ? turnBreakdownRows(cost.turns)
      : cost?.breakdown?.length ? cost.breakdown.map((row) =>
      `<div class="forge-cost-row"><span>${esc(row.label)}</span><span>$${Number(row.usd || 0).toFixed(2)}</span></div>`)
      : mergeForgeConversationCosts(status.conversation, status.logtail)
          .filter((row) => String(row.eventKey || "").startsWith("gpt-cost:"))
          .map((row) => `<div class="forge-cost-row">${esc(row.text)}</div>`);
    const nextCostBreakdownMarkup = breakdownRows.length
      ? breakdownRows.join("")
      : `<div class="forge-cost-row dim">No priced turns yet.</div>`;
    if (nextCostBreakdownMarkup !== costBreakdownMarkup) {
      costBreakdown.innerHTML = nextCostBreakdownMarkup;
      costBreakdownMarkup = nextCostBreakdownMarkup;
      if (costBreakdown.classList.contains("open")) prepareCostBreakdown();
    }
    $("#fp-session-id", overlay).textContent = status.sessionId ? `SESSION ${status.sessionId.slice(0, 12)}` : "SESSION STARTING";
    const reviewerActive = status.sessionRole === "reviewer";
    $("#fp-trace-source", overlay).dataset.role = reviewerActive ? "reviewer" : "author";
    pause.textContent = state === "paused" ? `RESUME ${reviewerActive ? "REVIEWER" : "AUTHOR"}`
      : state === "pausing" ? "PAUSING…" : state === "resuming" ? "RESUMING…"
      : state === "validating" ? "VALIDATING…" : `PAUSE ${reviewerActive ? "REVIEWER" : "AUTHOR"}`;
    pause.disabled = state === "pausing" || state === "resuming" || state === "validating";
    const authorDown = state === "paused" && status.sessionError;
    fail.classList.toggle("hidden", !authorDown);
    if (authorDown) {
      // A validator-infrastructure pause still reports role "author": the paid author
      // never ran, so the retry belongs to the validator AI, not the author.
      const downRole = status.sessionGate === "validator-infrastructure" ? "validator"
        : reviewerActive ? "reviewer" : "author";
      failMsg.textContent = status.sessionError;
      const sectionBudget = status.sessionGate === "section-repair-budget";
      altCostWrap.classList.toggle("hidden", !sectionBudget);
      const nextBudgetKey = sectionBudget ? String(status.sessionError || "section-budget") : "";
      if (nextBudgetKey !== sectionBudgetKey) {
        sectionBudgetKey = nextBudgetKey;
        delete altCost.dataset.edited;
      }
      if (sectionBudget && !altCost.dataset.edited && document.activeElement !== altCost)
        altCost.value = String(status.sectionCostLimitUsd ?? 2);
      altResume.textContent = `RESUME ${downRole.toUpperCase()} WITH THIS AI`;
      armAltPicker(downRole === "validator" ? status.sessionValidator : status.sessionAuthor, downRole);
    }
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
    const conversation = mergeForgeConversationCosts(status.conversation, status.logtail);
    const nextConversation = conversation.map((row) => `${row.at}:${row.kind}:${row.text}`).join("\0");
    if (nextConversation !== conversationKey) {
      conversationKey = nextConversation; const box = $("#fp-conversation", overlay);
      const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 50;
      box.innerHTML = conversation.length ? conversation.map((row) => {
        const stamp = messageStamp(row.at);
        const isCost = String(row.eventKey || "").startsWith("gpt-cost:");
        const validationState = forgeHarnessValidationState(row);
        const validationMark = validationState === "pass" ? "✓" : validationState === "fail" ? "×" : "";
        return `<div class="forge-chat ${esc(row.kind)}${isCost ? " cost" : ""}${validationState ? ` validation-${validationState}` : ""}"><div class="forge-chat-meta">
          <span class="forge-chat-role">${isCost ? "COST" : row.kind === "user" ? "YOU" : row.kind === "assistant" ? (row.role === "reviewer" ? "REVIEWER" : "AUTHOR") : row.kind === "harness" ? "HARNESS" : "SESSION"}</span>
          ${stamp ? `<time datetime="${esc(stamp.iso)}">${esc(stamp.label)}</time>` : ""}</div>
          <div class="forge-chat-text">${validationMark ? `<span class="forge-validation-mark" aria-hidden="true">${validationMark}</span>` : ""}<span class="forge-chat-copy">${esc(row.text)}</span></div></div>`;
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
        apiFetch(`/api/buildtome/status?id=${encodeURIComponent(jobId)}`),
        apiFetch(`/.forge-trace/${encodeURIComponent(traceId)}.json?t=${Date.now()}`, { cache: "no-store" }).catch(() => null),
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
              const response = await apiFetch(`/api/tome?tome=${encodeURIComponent(status.tome)}`);
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
