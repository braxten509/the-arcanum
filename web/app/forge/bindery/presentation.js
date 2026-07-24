/* Pure presentation helpers for the persistent author overlay. */
import { $, esc } from "../../core/dom.js";
import { formatCourseBlockers } from "../course-control.js";

export function phaseLine(status, interactionState) {
  let line =
    `Phase ${status.phase || 1} / 8 — ${status.phaseTitle || "starting"}`;
  const section = status.sectionProgress;
  if (Number(status.phase) === 3 && section?.section)
    line += ` — ${section.section} · ${section.index}/${section.total} · ${section.state}`;
  const active = ["running", "starting", "resuming"].includes(
    interactionState);
  if (active && status.phaseState) line += ` — ${status.phaseState}`;
  else if (interactionState) line += ` — ${interactionState}`;
  if (active && status.activityStartedAt) {
    const seconds = Math.max(
      0, Math.floor(Date.now() / 1000 - status.activityStartedAt));
    line +=
      ` — ${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`;
  }
  return line;
}

export function paintCourseControl(overlay, control, sessionUsage) {
  const panel = $("#fp-course-control", overlay);
  if (!control?.spine?.length) {
    panel.classList.add("hidden");
    return;
  }
  panel.classList.remove("hidden");
  const compactTokens = (value) => Number(value || 0) >= 1000000
    ? `${(Number(value) / 1000000).toFixed(1)}M`
    : Number(value || 0) >= 1000
      ? `${(Number(value) / 1000).toFixed(1)}K`
      : String(Number(value || 0));
  const usage = sessionUsage || {};
  const hasSessionUsage = [
    "inputTokens", "freshInputTokens", "cachedInputTokens",
    "cacheWriteTokens", "outputTokens",
  ].some((key) => Number(usage[key] || 0) > 0);
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

export function messageStamp(value) {
  const raw = Number(value);
  if (!Number.isFinite(raw)) return null;
  const date = new Date(raw < 1e12 ? raw * 1000 : raw);
  if (Number.isNaN(date.getTime())) return null;
  return {
    iso: date.toISOString(),
    label: date.toLocaleTimeString([], {
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    }),
  };
}
