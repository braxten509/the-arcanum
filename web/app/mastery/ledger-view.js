import { esc } from "../core/dom.js";
import { evidenceCounts, sectionResolution } from "./policy.js";
import { ledgerRows, ledgerState } from "./ledger.js";

export function masteryLabs(tome) {
  return Array.isArray(tome && tome.masteryLabs) ? tome.masteryLabs : [];
}

export function labsForSection(tome, sectionId) {
  return masteryLabs(tome).filter((entry) =>
    String((entry.masteryLab || {}).nodeId || "").startsWith(`${sectionId}.`));
}

export function masteryPanelHtml(tome, sections, state) {
  if (!tome.masteryEvidence) return "";
  const counts = evidenceCounts(state);
  const resolutions = (sections || []).map((section) => sectionResolution(section, state));
  const resolved = resolutions.reduce((total, row) => total + row.resolved, 0);
  const required = resolutions.reduce((total, row) => total + row.required, 0);
  const rows = ledgerRows(state);
  const labs = masteryLabs(tome);
  return `<section class="mastery-ledger" aria-labelledby="mastery-ledger-title">
    <header><div><span class="assessment-kicker">MASTERY ${Number(tome.masteryEvidence.level || 1)}</span>
      <h2 id="mastery-ledger-title">Evidence ledger</h2></div><span class="mastery-state">${esc(state.masteryStatus || "learning")}</span></header>
    <div class="mastery-metrics">
      <div><span>REQUIRED LESSON WORK</span><b>${resolved}/${required} resolved</b></div>
      <div><span>INDEPENDENT EVIDENCE</span><b>${counts.demonstrated}/${counts.total} demonstrated</b></div>
      <div><span>REVIEW DUE</span><b>${counts.due} capabilities due</b></div>
      <div><span>MASTERY STATUS</span><b>${esc(state.masteryStatus || "learning")}</b></div>
    </div>
    ${labs.length ? `<div class="mastery-lab-list"><h3>STANDALONE MASTERY LABS</h3>${labs.map((entry) => {
      const lab = entry.masteryLab || {};
      const receipt = state.assessmentReceipts && state.assessmentReceipts[lab.performanceId];
      return `<button class="mastery-lab-row" data-mastery-lab="${esc(lab.nodeId)}"><span><b>${esc(lab.title)}</b>
        <small>${esc(lab.performanceKind || "performance")} · ${esc(lab.aidPolicy || "cold")} aids</small></span>
        <strong>${receipt ? (receipt.essentialPassed ? esc(receipt.grade || "PASS") : "INCOMPLETE") : "BEGIN"}</strong></button>`;
    }).join("")}</div>` : ""}
    <div class="evidence-table"><div class="evidence-head"><span>CAPABILITY</span><span>CURRENT EVIDENCE</span></div>
      ${rows.length ? rows.map((row) => `<div class="evidence-row"><code>${esc(row.label)}</code><span data-state="${esc(ledgerState(row))}">${esc(ledgerState(row))}</span></div>`).join("")
        : '<p class="dim">Capability evidence appears as you reach evidence-bearing work.</p>'}</div>
  </section>`;
}

export function sectionLabsHtml(tome, sectionId, state) {
  const labs = labsForSection(tome, sectionId);
  if (!labs.length) return "";
  return `<section class="section-mastery-labs"><span class="assessment-kicker">INDEPENDENT PERFORMANCE</span><h2>MASTERY LABS</h2>
    ${labs.map((entry) => { const lab = entry.masteryLab || {}; const done = state.assessmentReceipts?.[lab.performanceId];
      return `<button class="mastery-lab-row" data-mastery-lab="${esc(lab.nodeId)}"><span><b>${esc(lab.title)}</b><small>${esc((lab.cognitiveTasks || []).join(" · "))}</small></span><strong>${done ? esc(done.grade || "DONE") : "OPEN"}</strong></button>`;
    }).join("")}</section>`;
}
