/* Presenting a Great Working to the tower, and the judgement that comes back. */
import { GRADING_LINES, J, SRANK_MULT, coin, graderTitle, langName, persona } from "../core/config.js";
import { $, dropOverlay, esc, ico, modal, sfx, toast } from "../core/dom.js";
import { addCredits, fsBest, grantBadge, renderSidebar, sectionPassed } from "./progress.js";
import { getState, save } from "../core/store.js";
import { sections, tome } from "../core/bootstrap.js";
import { apiFetch } from "../core/api-client.js";
import { dispatchCommand } from "../core/commands.js";
import { go } from "../core/router.js";
import { isEvidenceTome } from "../mastery/policy.js";
import { applyAssessmentReceipt } from "../mastery/evidence.js";
import { assessmentBusy, assessmentEvidenceHtml, submitAssessment } from "../mastery/assessment.js";

const gradingJobs = {}; // sectionId -> jobId while a grade is in flight

export function paintSubmitBtn() {
  const b = $("#b-submit");
  const section = dispatchCommand("working.section");
  if (!b || !section) return;
  const evidence = isEvidenceTome(tome());
  const busy = evidence ? assessmentBusy(`${section.id}.working`) : !!gradingJobs[section.id];
  b.disabled = busy;
  b.innerHTML = busy ? `${ico("upload")} ASSESSING...` : evidence
    ? `${ico("upload")} SUBMIT FOR ASSESSMENT`
    : `${ico("upload")} PRESENT TO ${esc(persona())}`;
}

export async function submitForGrading() {
  const sec = dispatchCommand("working.section");
  if (isEvidenceTome(tome())) return submitEvidenceWorking(sec);
  if (gradingJobs[sec.id]) { toast(`${persona()} already holds this working. One judgement at a time.`, "warn"); return; }
  gradingJobs[sec.id] = "pending";
  paintSubmitBtn();
  await dispatchCommand("working.save", false);
  const overlay = document.createElement("div");
  overlay.className = "grade-overlay";
  overlay.innerHTML = `<div class="grade-card"><div class="grading-anim">
    <div style="font-size:11px;letter-spacing:.2em" class="faint">CARRIED TO THE TOWER OF</div>
    <div style="font-family:var(--arch);font-size:20px;margin:14px 0">${esc(graderTitle())}</div>
    <div class="spinner-line" id="grade-line">${GRADING_LINES[0]}</div>
    <div class="dim" style="margin-top:18px;font-size:12px;font-style:italic">judgement takes a minute or two — it happens in the tower, so feel free to keep working at your desk</div>
    <button class="btn quiet" id="grade-hide" style="margin-top:18px">RETURN TO THE DESK (judgement continues)</button>
  </div></div>`;
  document.body.appendChild(overlay);
  let lineIdx = 0;
  const lineTimer = setInterval(() => {
    lineIdx = (lineIdx + 1) % GRADING_LINES.length;
    const el = $("#grade-line"); if (el) el.textContent = GRADING_LINES[lineIdx];
  }, 5000);
  $("#grade-hide", overlay).onclick = () => overlay.classList.add("hidden");

  getState().stats.subs++; save();

  let jobId = null;
  try {
    const r = await apiFetch("/api/grade", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sectionId: sec.id, sectionTitle: sec.codename + " — " + sec.title,
        brief: sec.freestyle.brief.replace(/<[^>]+>/g, ""),
        rubric: sec.freestyle.rubric,
        files: dispatchCommand("working.files"),
        language: langName(),
        persona: (J().narrative && J().narrative.graderPersona) || "PATCH",
        studentTerm: (J().narrative && J().narrative.studentTerm) || "recruit",
        gradeScale: (J().narrative && J().narrative.gradeScale) || "S|A|B|C|D|F",
        fallbackModel: getState().ai.grader,
        grader: { kind: getState().ai.graderKind, model: getState().ai.graderModel, key: getState().ai.keys[getState().ai.graderKind] || "", command: getState().ai.graderCommand || "" },
      }),
    });
    jobId = (await r.json()).jobId;
    gradingJobs[sec.id] = jobId;
  } catch (err) {
    clearInterval(lineTimer); overlay.remove();
    delete gradingJobs[sec.id];
    paintSubmitBtn();
    toast("The messenger could not reach the tower: " + err, "bad");
    return;
  }

  const poll = setInterval(async () => {
    let st;
    try { st = await (await apiFetch("/api/grade/status?id=" + jobId)).json(); } catch { return; }
    if (st.status === "running") return;
    clearInterval(poll); clearInterval(lineTimer);
    overlay.remove();
    delete gradingJobs[sec.id];
    paintSubmitBtn();
    if (st.status === "error") {
      modal(`<h2>THE TOWER DOES NOT ANSWER</h2><p class="dim">${esc(st.error || "unknown error")}</p><p>Your pages are safe on your desk. Present them again in a minute.</p>`, [["SO BE IT", "quiet"]]);
      return;
    }
    showGradeResult(sec, st.result);
  }, 3000);
}

async function submitEvidenceWorking(sec) {
  if (assessmentBusy(`${sec.id}.working`)) return;
  const rationale = ($("#fs-rationale")?.value || "").trim();
  paintSubmitBtn();
  await dispatchCommand("working.save", false);
  const overlay = document.createElement("div");
  overlay.className = "grade-overlay";
  overlay.innerHTML = `<div class="grade-card assessment-wait"><span class="assessment-kicker">LEARNER WORKSPACE SNAPSHOT</span>
    <h2>Running deterministic evidence first</h2><p class="dim" id="assessment-stage">Preparing an isolated copy of your work…</p></div>`;
  document.body.appendChild(overlay);
  try {
    const receipt = await submitAssessment({
      sectionId: sec.id, rationale,
      onStatus: () => {
        paintSubmitBtn();
        const stage = $("#assessment-stage", overlay);
        if (stage) stage.textContent = "Building, running essential scenarios, then scoring the declared rubric…";
      },
    });
    applyAssessmentReceipt(getState(), receipt.performanceId, receipt);
    getState().fs[sec.id] = Object.assign(getState().fs[sec.id] || {}, { best: {
      total: Number(receipt.weightedTotal || 0), grade: receipt.grade,
      essentialPassed: !!receipt.essentialPassed, independent: !!receipt.independent,
      at: Date.now(), receiptHash: receipt.receiptHash,
    }});
    save();
    overlay.innerHTML = `<div class="grade-card">${assessmentEvidenceHtml(receipt)}
      <div class="modal-actions"><button class="btn" id="assessment-close">RETURN TO THE WORKING</button></div></div>`;
    $("#assessment-close", overlay).onclick = () => dropOverlay(overlay, () => {
      renderSidebar(); paintSubmitBtn();
    });
  } catch (error) {
    overlay.innerHTML = `<div class="grade-card"><span class="assessment-kicker">ASSESSMENT COULD NOT COMPLETE</span>
      <h2>Your workspace is unchanged</h2><p>${esc(error.message || error)}</p>
      <div class="modal-actions"><button class="btn quiet" id="assessment-close">RETURN TO THE WORKING</button></div></div>`;
    $("#assessment-close", overlay).onclick = () => dropOverlay(overlay);
  } finally { paintSubmitBtn(); }
}

function showGradeResult(sec, res) {
  const total = Math.max(0, Math.min(100, Math.round(res.total || 0)));
  const grade = String(res.grade || (total >= 90 ? "A" : total >= 80 ? "B" : total >= 70 ? "C" : total >= 60 ? "D" : "F")).toUpperCase();
  const prev = fsBest(sec.id);
  const prevPts = prev ? prev.awarded || 0 : 0;

  let ptsFull = Math.round(sec.freestyle.reward * (total / 100) * (grade === "S" ? SRANK_MULT : 1));
  const delta = Math.max(0, ptsFull - prevPts);

  const isBest = !prev || total > prev.total;
  if (isBest) {
    getState().fs[sec.id] = Object.assign(getState().fs[sec.id] || {}, { best: { total, grade, awarded: Math.max(ptsFull, prevPts), at: Date.now() } });
  }
  if (delta > 0) addCredits(delta, true);
  if (total >= 70) grantBadge(sec.freestyle.badge.id, sec.freestyle.badge.name, sec.freestyle.badge.desc);
  if (grade === "S") grantBadge(sec.id + "-s-rank", "S-RANK: " + sec.codename, "Flawless execution on " + sec.freestyle.title + ".");
  const allDone = sections().every(sectionPassed);
  if (allDone) grantBadge("ghost-protocol");
  save();

  if (total >= 60) sfx("grade");                                             // the harp answers a passing judgement
  else if (window.GhostAudio && getState().audio.sfx) GhostAudio.spellHit(false);     // a failing one miscasts — no ding
  const overlay = document.createElement("div");
  overlay.className = "grade-overlay";
  overlay.innerHTML = `<div class="grade-card">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:20px">
      <div>
        <div class="faint" style="font-size:11px;letter-spacing:.2em">THE JUDGEMENT // ${esc(sec.codename)}</div>
        <h2 style="margin:6px 0 0">${esc(sec.freestyle.title)}</h2>
        <div class="dim" style="font-size:12px;font-style:italic">weighed by ${esc(res.model || "the tower")}${res.cached ? " · unchanged work — the prior judgement stands" : ""} · weighted total <span class="num">${total}/100</span></div>
      </div>
      <div class="grade-letter ${total < 60 ? "low" : total < 80 ? "mid" : ""}">${esc(grade)}</div>
    </div>
    <div style="margin-top:16px">
      ${(res.scores || []).map((s2) => `
        <div class="crit-row">
          <span>${esc(s2.criterion)}<span class="rubric-desc">${esc(s2.comment || "")}</span></span>
          <span class="meter"><i style="width:${Math.min(100, (s2.score || 0) * 10)}%"></i></span>
          <span class="num dim">${s2.score}/10</span>
        </div>`).join("")}
    </div>
    <div class="grade-feedback">${esc(res.feedback || "")}</div>
    ${res.bestLine ? `<div class="dim" style="font-size:12.5px">${esc(persona())} underlined this line of yours: <code>${esc(res.bestLine)}</code></div>` : ""}
    <div class="grade-rewards">
      ${delta > 0 ? `<span class="tag ac num">+${delta} ${coin().toUpperCase()}</span>` : `<span class="tag">no new ${coin()} (your best still stands)</span>`}
      ${total >= 70 ? `<span class="tag ac">SIGIL: ${esc(sec.freestyle.badge.name)}</span>` : ""}
      ${total >= 60 ? `<span class="tag ac">NEXT CHAPTER UNSEALED</span>` : `<span class="tag warn">SCORE 60+ TO BREAK THE NEXT SEAL</span>`}
    </div>
    <div class="modal-actions">
      <button class="btn quiet" id="gr-close">BACK TO THE DESK</button>
      ${total >= 60 ? `<button class="btn" id="gr-next">TURN THE PAGE ${ico("arrow")}</button>` : ""}
    </div>
  </div>`;
  document.body.appendChild(overlay);
  $("#gr-close", overlay).onclick = () => dropOverlay(overlay, renderSidebar);
  const nx = $("#gr-next", overlay);
  if (nx) nx.onclick = () => dropOverlay(overlay, () => {
    const i = sections().indexOf(sec);
    if (i < sections().length - 1) go("section", sections()[i + 1].id);
    else go("home");
  });
}
