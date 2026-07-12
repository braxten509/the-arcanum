/* Presenting a Great Working to the tower, and the judgement that comes back. */
import { GRADING_LINES, J, SRANK_MULT, coin, graderTitle, langName, persona } from "../core/config.js";
import { $, dropOverlay, esc, ico, modal, sfx, toast } from "../core/dom.js";
import { addCredits, fsBest, go, grantBadge, renderSidebar, sectionPassed } from "./progress.js";
import { S, save } from "../core/state.js";
import { collectFiles, fsSection, saveWorkspace } from "../bench/workbench.js";

const gradingJobs = {}; // sectionId -> jobId while a grade is in flight

export function paintSubmitBtn() {
  const b = $("#b-submit");
  if (!b || !fsSection) return;
  const busy = !!gradingJobs[fsSection.id];
  b.disabled = busy;
  b.innerHTML = busy ? `${ico("upload")} BEING JUDGED...` : `${ico("upload")} PRESENT TO ${esc(persona())}`;
}

export async function submitForGrading() {
  const sec = fsSection;
  if (gradingJobs[sec.id]) { toast(`${persona()} already holds this working. One judgement at a time.`, "warn"); return; }
  gradingJobs[sec.id] = "pending";
  paintSubmitBtn();
  await saveWorkspace(false);
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

  S.stats.subs++; save();

  let jobId = null;
  try {
    const r = await fetch("/api/grade", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sectionId: sec.id, sectionTitle: sec.codename + " — " + sec.title,
        brief: sec.freestyle.brief.replace(/<[^>]+>/g, ""),
        rubric: sec.freestyle.rubric,
        files: collectFiles(),
        language: langName(),
        persona: (J().narrative && J().narrative.graderPersona) || "PATCH",
        studentTerm: (J().narrative && J().narrative.studentTerm) || "recruit",
        gradeScale: (J().narrative && J().narrative.gradeScale) || "S|A|B|C|D|F",
        fallbackModel: S.ai.grader,
        grader: { kind: S.ai.graderKind, model: S.ai.graderModel, key: S.ai.keys[S.ai.graderKind] || "", command: S.ai.graderCommand || "" },
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
    try { st = await (await fetch("/api/grade/status?id=" + jobId)).json(); } catch { return; }
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

function showGradeResult(sec, res) {
  const total = Math.max(0, Math.min(100, Math.round(res.total || 0)));
  const grade = String(res.grade || (total >= 90 ? "A" : total >= 80 ? "B" : total >= 70 ? "C" : total >= 60 ? "D" : "F")).toUpperCase();
  const prev = fsBest(sec.id);
  const prevPts = prev ? prev.awarded || 0 : 0;

  let ptsFull = Math.round(sec.freestyle.reward * (total / 100) * (grade === "S" ? SRANK_MULT : 1));
  const delta = Math.max(0, ptsFull - prevPts);

  const isBest = !prev || total > prev.total;
  if (isBest) {
    S.fs[sec.id] = Object.assign(S.fs[sec.id] || {}, { best: { total, grade, awarded: Math.max(ptsFull, prevPts), at: Date.now() } });
  }
  if (delta > 0) addCredits(delta, true);
  if (total >= 70) grantBadge(sec.freestyle.badge.id, sec.freestyle.badge.name, sec.freestyle.badge.desc);
  if (grade === "S") grantBadge(sec.id + "-s-rank", "S-RANK: " + sec.codename, "Flawless execution on " + sec.freestyle.title + ".");
  const allDone = window.SECTIONS.every(sectionPassed);
  if (allDone) grantBadge("ghost-protocol");
  save();

  if (total >= 60) sfx("grade");                                             // the harp answers a passing judgement
  else if (window.GhostAudio && S.audio.sfx) GhostAudio.spellHit(false);     // a failing one miscasts — no ding
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
    const i = window.SECTIONS.indexOf(sec);
    if (i < window.SECTIONS.length - 1) go("section", window.SECTIONS[i + 1].id);
    else go("home");
  });
}
