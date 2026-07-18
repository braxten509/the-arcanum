/* Dedicated isolated mastery-lab route. */
import { WorkbenchSession } from "../bench/session.js";
import { apiJson, postJson } from "../core/api-client.js";
import { tome } from "../core/bootstrap.js";
import { dispatchCommand } from "../core/commands.js";
import { editorLang } from "../core/config.js";
import { $, esc, modal, toast } from "../core/dom.js";
import { go } from "../core/router.js";
import { getState, save } from "../core/store.js";
import { applyAssessmentReceipt } from "./evidence.js";
import { assessmentEvidenceHtml, performanceForNode, submitAssessment } from "./assessment.js";
import { syncVariantAssignment } from "./variants.js";
import { deriveMasteryStatus } from "./policy.js";

let session = null;
let routeToken = 0;

function languageFor(path) {
  const extension = String(path || "").split(".").pop();
  if (extension === "json") return "json";
  if (extension === "md") return "markdown";
  if (extension === "xml" || extension === "csproj") return "xml";
  return editorLang();
}

function renderTabs(root) {
  const tabs = $("#lab-file-tabs", root);
  tabs.innerHTML = session ? [...session.models.keys()].map((path) =>
    `<button class="ftab${path === session.activePath ? " active" : ""}" data-lab-file="${esc(path)}">${esc(path)}</button>`).join("") : "";
  tabs.querySelectorAll("[data-lab-file]").forEach((button) =>
    button.onclick = () => session.switchTo(button.dataset.labFile));
}

function publicChecksHtml(result) {
  return `<div class="lab-public-result" data-passed="${result.ok ? "true" : "false"}">
    <b>${result.ok ? "PUBLIC CHECKS PASSED" : "PUBLIC CHECKS NEED WORK"}</b>
    ${(result.checks || []).map((check) => `<div><span>${check.passed ? "PASS" : "FAIL"}</span><code>${esc(check.id)}</code></div>`).join("")}
    ${result.output ? `<pre>${esc(result.output)}</pre>` : ""}</div>`;
}

export async function renderMasteryLab(nodeId) {
  const token = ++routeToken;
  const root = $("#view-mastery-lab");
  root.classList.remove("hidden");
  root.innerHTML = `<div class="lab-loading"><span class="assessment-kicker">ISOLATED MASTERY LAB</span><h1>Assigning a verified variant…</h1></div>`;
  $("#hud-op").textContent = "— independent mastery lab";
  try {
    const data = await apiJson(`/api/mastery-lab?nodeId=${encodeURIComponent(nodeId)}`);
    if (token !== routeToken) return;
    const lab = data.lab || {}, challenge = data.challenge || {}, assignment = data.assignment || {};
    syncVariantAssignment(getState(), assignment); save();
    const sectionId = String(nodeId).split(".", 1)[0];
    const canAsk = ["learning", "limited"].includes(challenge.aidPolicy || lab.aidPolicy);
    root.innerHTML = `<div class="mastery-lab-shell">
      <header class="mastery-lab-head"><div><div class="crumb"><button id="lab-back">${esc(sectionId.toUpperCase())}</button> / MASTERY LAB</div>
        <span class="assessment-kicker">${esc(lab.performanceKind || "INDEPENDENT PERFORMANCE")}</span><h1>${esc(challenge.title || lab.title)}</h1></div>
        <div class="lab-assignment"><span>ASSIGNMENT</span><code>${esc(assignment.variantId)}</code><small>attempt ${Number(assignment.attempt || 1)}</small></div></header>
      <div class="mastery-lab-grid"><section class="lab-editor-panel"><div id="lab-file-tabs"></div><div id="lab-editor-host"></div>
        <div class="lab-console"><div class="term-head"><span>PUBLIC CHECKS</span></div><div id="lab-output">Run checks whenever you want. They do not issue mastery evidence.</div></div></section>
      <aside class="lab-brief-panel"><div class="lab-policy"><span>AID POLICY</span><b>${esc(challenge.aidPolicy || lab.aidPolicy || "cold")}</b></div>
        <p>${esc(challenge.brief || "")}</p><h3>PUBLIC REQUIREMENTS</h3><ol>${(challenge.requirements || []).map((requirement) =>
          `<li><code>${esc(requirement.id || "requirement")}</code><span>${esc(requirement.text || requirement)}</span>${requirement.essential !== false ? "<b>ESSENTIAL</b>" : ""}</li>`).join("")}</ol>
        ${(challenge.publicExamples || []).length ? `<h3>PUBLIC EXAMPLES</h3><pre>${esc(JSON.stringify(challenge.publicExamples, null, 2))}</pre>` : ""}
        <label class="rationale-field"><span>RATIONALE / DEFENSE${lab.rationaleRequired ? " · REQUIRED" : ""}</span><textarea id="lab-rationale" rows="6" placeholder="${esc(challenge.rationalePrompt || "Explain your choices and tradeoffs.")}"></textarea></label>
        <p class="lab-refresh-note">Refreshing keeps this exact assignment. A new variant is issued only when you choose retry.</p>
        <div class="lab-actions">${canAsk ? '<button class="btn quiet" id="lab-oracle">CONSULT THE ORACLE</button>' : ""}<button class="btn quiet" id="lab-run">RUN PUBLIC CHECKS</button><button class="btn" id="lab-submit">SUBMIT EVIDENCE</button></div>
        <button class="lab-retry" id="lab-retry">ABANDON THIS ATTEMPT AND TRY A NEW VARIANT</button></aside></div></div>`;
    $("#lab-back", root).onclick = () => go("section", sectionId);
    await window.GhostEditor.monacoReady;
    if (token !== routeToken) return;
    if (session) session.dispose();
    session = new WorkbenchSession("mastery-lab");
    session.onActive = () => renderTabs(root);
    session.mount($("#lab-editor-host", root), data.files || [], languageFor, getState().theme);
    renderTabs(root);
    $("#lab-run", root).onclick = async () => {
      const button = $("#lab-run", root); button.disabled = true; button.textContent = "RUNNING…";
      try {
        const result = await postJson("/api/mastery-lab/run", { nodeId, files: session.files() });
        $("#lab-output", root).innerHTML = publicChecksHtml(result);
      } catch (error) { $("#lab-output", root).textContent = error.message || error; }
      finally { button.disabled = false; button.textContent = "RUN PUBLIC CHECKS"; }
    };
    $("#lab-submit", root).onclick = async () => {
      const rationale = $("#lab-rationale", root).value.trim();
      if (lab.rationaleRequired && !rationale) { toast("Write the required rationale before submitting.", "warn"); return; }
      const button = $("#lab-submit", root); button.disabled = true; button.textContent = "ASSESSING…";
      try {
        await postJson("/api/mastery-lab/workspace", { nodeId, files: session.files() });
        const receipt = await submitAssessment({ nodeId, rationale });
        applyAssessmentReceipt(getState(), receipt.performanceId, receipt);
        getState().masteryLabs[nodeId] = { receiptHash: receipt.receiptHash, grade: receipt.grade,
          essentialPassed: receipt.essentialPassed, independent: receipt.independent, at: Date.now() };
        const required = (tome().masteryEvidence?.performances || []).map((row) => row.id);
        getState().masteryStatus = deriveMasteryStatus(getState(), required);
        save();
        $("#lab-output", root).innerHTML = assessmentEvidenceHtml(receipt);
        button.textContent = receipt.essentialPassed ? "EVIDENCE RECORDED" : "TRY A NEW VARIANT";
        button.disabled = !!receipt.essentialPassed;
      } catch (error) { $("#lab-output", root).textContent = error.message || error; button.disabled = false; button.textContent = "SUBMIT EVIDENCE"; }
    };
    const oracle = $("#lab-oracle", root);
    if (oracle) oracle.onclick = async () => {
      await postJson("/api/mastery/support", { nodeId, kind: "oracle" });
      dispatchCommand("oracle.ask", `MASTERY LAB / ${challenge.title || lab.title}`,
        `${challenge.brief || ""}\n\nPUBLIC REQUIREMENTS:\n${(challenge.requirements || []).map((row) => row.text || row).join("\n")}`, "");
    };
    $("#lab-retry", root).onclick = () => modal(`<h2>ABANDON THIS VARIANT?</h2><p>Your files for <code>${esc(assignment.variantId)}</code> remain in the local evidence area, but this attempt will no longer be active. A different verified variant will be assigned.</p>`,
      [["KEEP WORKING", "quiet"], ["ASSIGN A NEW VARIANT", "", async () => {
        await postJson("/api/mastery-lab/retry", { nodeId }); renderMasteryLab(nodeId);
      }]]);
  } catch (error) {
    root.innerHTML = `<div class="lab-loading"><span class="assessment-kicker">MASTERY LAB UNAVAILABLE</span><h1>The assignment could not be opened</h1><p>${esc(error.message || error)}</p></div>`;
  }
}
