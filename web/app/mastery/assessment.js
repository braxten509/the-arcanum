/* Shared async assessment client and learner-safe evidence presentation. */
import { apiJson, postJson } from "../core/api-client.js";
import { esc } from "../core/dom.js";

const activeJobs = new Map();

export function assessmentBusy(nodeId) {
  return activeJobs.has(nodeId);
}

export function performanceForNode(tome, nodeId) {
  return ((tome && tome.masteryEvidence && tome.masteryEvidence.performances) || [])
    .find((performance) => performance.nodeId === nodeId) || null;
}

const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

export async function submitAssessment({ sectionId = "", nodeId = "", rationale = "", onStatus }) {
  const resolvedNode = nodeId || `${sectionId}.working`;
  if (activeJobs.has(resolvedNode)) return activeJobs.get(resolvedNode);
  const task = (async () => {
    const started = await postJson("/api/assessment", {
      ...(sectionId ? { sectionId } : { nodeId }), rationale,
    });
    if (!started.jobId) throw new Error("assessment did not return a job id");
    onStatus?.("running");
    while (true) {
      await wait(1000);
      const status = await apiJson(`/api/assessment/status?id=${encodeURIComponent(started.jobId)}`);
      onStatus?.(status.status);
      if (status.status === "done") return status.result;
      if (status.status === "error") throw new Error(status.error || "assessment failed");
      if (status.status === "cancelled" || status.status === "unknown") {
        throw new Error(`assessment ${status.status}`);
      }
    }
  })();
  activeJobs.set(resolvedNode, task);
  onStatus?.("queued");
  try { return await task; }
  finally { activeJobs.delete(resolvedNode); }
}

function checkLabel(check) {
  if (check.kind === "build") return "BUILD";
  if (check.kind === "cold-launch") return "COLD LAUNCH";
  if (check.kind === "package") return "PACKAGE";
  return String(check.id || check.kind || "BEHAVIOR").replace(/[-_]/g, " ").toUpperCase();
}

export function assessmentEvidenceHtml(receipt) {
  const checks = receipt.checks || [];
  const failedRequirements = [...new Set(checks.filter((check) => !check.passed)
    .flatMap((check) => check.requirementIds || []))];
  const verdict = receipt.essentialPassed
    ? `${esc(receipt.grade || "B")} · ${Number(receipt.weightedTotal || 0)}/100`
    : "INCOMPLETE";
  return `<section class="assessment-result" data-passed="${receipt.essentialPassed ? "true" : "false"}">
    <header><div><span class="assessment-kicker">DETERMINISTIC EVIDENCE</span>
      <h2>${verdict}</h2></div><span class="assessment-independence">${receipt.independent
        ? "INDEPENDENT EVIDENCE"
        : receipt.supportUsed ? "COMPLETED WITH SUPPORT" : "EVIDENCE NOT YET INDEPENDENT"}</span></header>
    <div class="assessment-checks">${checks.map((check) => `<div class="assessment-check ${check.passed ? "passed" : "failed"}">
      <span class="assessment-mark">${check.passed ? "PASS" : "FAIL"}</span><b>${esc(checkLabel(check))}</b>
      ${(check.problems || []).length ? `<p>${esc(check.problems.join(" "))}</p>` : ""}</div>`).join("")
      || '<p class="dim">No deterministic checks were reported.</p>'}</div>
    ${failedRequirements.length ? `<div class="assessment-failures"><b>FAILED PUBLIC REQUIREMENTS</b><ul>${failedRequirements.map(
      (id) => `<li><code>${esc(id)}</code></li>`).join("")}</ul></div>` : ""}
    ${(receipt.scores || []).length ? `<div class="assessment-qualitative"><span class="assessment-kicker">QUALITATIVE REVIEW</span>${receipt.scores.map(
      (score) => `<div><b>${esc(score.criterion || score.id)}</b><span>${Number(score.score || 0)}/10</span><p>${esc(score.comment || "")}</p></div>`).join("")}</div>` : ""}
    ${receipt.feedback ? `<p class="assessment-feedback">${esc(receipt.feedback)}</p>` : ""}
  </section>`;
}
