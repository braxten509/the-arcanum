/* The trials: every exercise type, the spaced-review round, and answer checking. */
import { HINT_COST, coin, gp, roman, runLabel } from "../core/config.js";
import { $, esc, ico, modal, sfx, toast } from "../core/dom.js";
import { codePad, firstDiff, normCode } from "./code.js";
import { askOracle, oracleContext } from "../bench/oracle.js";
import { addCredits, attemptMultiplier, comboBonus, grantBadge, lessonDone, spend, updateHud } from "./progress.js";
import { burst, castSigil, lastCastAt } from "./sigil.js";
import { S, save } from "../core/state.js";

const EX_LABEL = { mc: "CHOOSE WISELY", fill: "COMPLETE THE RUNE", text: "SPEAK THE WORD", type: "COPYING DRILL", write: "INSCRIPTION" };

// ------------------------------------------------------------ SPACED REVIEW
// Retrieval practice of already-solved recall items, resurfaced on a Leitner
// schedule with TWO clocks: lessons completed (a self-paced course's natural
// clock) and wall time (so long absences and a finished tome still surface
// review). An item is due when EITHER clock runs out; a successful recall
// re-stamps both. type/write are no-decay skill drills already, so review
// covers only mc/fill/text. A hit pushes the item further out; a miss brings
// it right back.
const REVIEWABLE = new Set(["mc", "fill", "text"]);
const REVIEW_STEPS = [1, 2, 4, 8, 16]; // Leitner intervals: lessons-completed units AND days
const DAY = 86400000;
export const GATE_MIN = 5; // due items before the gate bars a doorway
const lessonsCompleted = () => window.SECTIONS.reduce((n, s) => n + s.lessons.filter(lessonDone).length, 0);
function scheduleReview(st, ok) {
  st.box = ok ? Math.min((st.box || 1) + 1, REVIEW_STEPS.length) : 1;
  st.due = lessonsCompleted() + REVIEW_STEPS[st.box - 1];
  st.dueT = Date.now() + REVIEW_STEPS[st.box - 1] * DAY;
}
export function reviewDue() {
  const clock = lessonsCompleted(), now = Date.now(), out = [];
  for (const sec of window.SECTIONS)
    for (const l of sec.lessons)
      for (const e of (l.exercises || [])) {
        if (!REVIEWABLE.has(e.type)) continue;
        const st = S.ex[e.id];
        if (st && st.ok && ((st.due != null && st.due <= clock) || (st.dueT != null && st.dueT <= now))) out.push({ e, st });
      }
  return out.sort((a, b) => (a.st.due || 0) - (b.st.due || 0));
}
// One-time repair: recall items solved before spaced review existed (or before
// the time clock existed) were never fully enrolled. Stamp them "last recalled
// now" on the shortest leash so they start cycling.
export function backfillReview() {
  const clock = lessonsCompleted(), now = Date.now();
  let changed = false;
  for (const sec of window.SECTIONS)
    for (const l of sec.lessons)
      for (const e of (l.exercises || [])) {
        if (!REVIEWABLE.has(e.type)) continue;
        const st = S.ex[e.id];
        if (!st || !st.ok) continue;
        if (st.due == null) { st.box = 1; st.due = clock + REVIEW_STEPS[0]; changed = true; }
        if (st.dueT == null) { st.dueT = now + REVIEW_STEPS[(st.box || 1) - 1] * DAY; changed = true; }
      }
  if (changed) save();
}
// The gate: a doorway (new lesson's trials, a chapter's project) calls this
// instead of proceeding directly. Under GATE_MIN due it opens at once; at or
// above, one review round (max 8 items) must be completed first — closing the
// overlay early keeps the door shut.
export function reviewGate(onPass) {
  if (reviewDue().length < GATE_MIN) { onPass(); return; }
  startReview(onPass);
}
// a banner shown wherever review is due; caller wires #btn-review to startReview
export function reviewBanner() {
  const n = reviewDue().length;
  if (!n) return "";
  return `<div id="review-cta" style="display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;margin:0 0 18px;padding:13px 16px;border:1px solid var(--line-hi);border-radius:var(--rad);background:var(--ac-bg)">
    <div><b>${ico("bell")} SPACED REVIEW</b> <span class="dim" style="font-size:12.5px">${n} concept${n > 1 ? "s you have" : " you have"} learned ${n > 1 ? "are" : "is"} due to be re-forged — quick recall keeps them from fading.</span></div>
    <button class="btn" id="btn-review">${ico("scroll")} BEGIN REVIEW (${n})</button></div>`;
}
export function wireReview(v) { const b = $("#btn-review", v); if (b) b.onclick = () => startReview(); }

export function startReview(onPass) {
  const due = reviewDue().slice(0, 8); // a short round; the rest surface next time
  if (!due.length) { toast("Nothing is due for review — your seals hold.", "ok"); if (onPass) onPass(); return; }
  const graded = new Set(); // grade each item once per round, on its first outcome
  let passed = false;
  const overlay = document.createElement("div");
  overlay.className = "grade-overlay review-overlay";
  overlay.innerHTML = `<div class="grade-card" style="max-width:780px;width:min(780px,94vw);max-height:88vh;display:flex;flex-direction:column">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px">
      <div>
        <div class="faint" style="font-size:11px;letter-spacing:.2em">✦ SPACED REVIEW // RE-FORGE WHAT YOU HAVE LEARNED</div>
        <h2 style="margin:6px 0 0">THE MASTER CALLS BACK OLD LESSONS</h2>
        <div class="dim" style="font-size:12.5px;margin-top:4px">${onPass ? "The Master bars the way until these seals are re-forged. " : ""}Answer from memory. No coin, no penalty — recall is its own rent. <span id="rv-count" class="num"></span></div>
      </div>
      <button class="btn quiet" id="rv-close">${onPass ? "TURN BACK" : "CLOSE"}</button>
    </div>
    <div class="review-scroll" style="overflow:auto;margin-top:14px;flex:1;display:flex;flex-direction:column;gap:14px"></div>`;
  const scroll = $(".review-scroll", overlay);
  const closeBtn = $("#rv-close", overlay);
  const updateCount = () => { const c = $("#rv-count", overlay); if (c) c.textContent = `${graded.size}/${due.length} re-forged`; };
  due.forEach(({ e, st }, i) => {
    scroll.appendChild(exerciseEl(e, i, true, (ok) => {
      if (graded.has(e.id)) return;
      graded.add(e.id);
      scheduleReview(st, ok);
      S.stats.reviews = (S.stats.reviews || 0) + 1;
      save(); updateCount();
      if (graded.size >= due.length) {
        passed = true;
        toast("Review complete — the old seals are re-forged.", "ok");
        if (onPass) { closeBtn.className = "btn"; closeBtn.textContent = "CONTINUE — THE WAY IS OPEN"; }
      }
    }));
  });
  updateCount();
  document.body.appendChild(overlay);
  closeBtn.onclick = () => { overlay.remove(); if (passed && onPass) onPass(); };
}

export function exerciseEl(e, idx, redo, onReview) {
  const st = S.ex[e.id] || (S.ex[e.id] = { a: 0, ok: false, pts: 0, hint: false, reps: 0 });
  if (st.reps === undefined) st.reps = 0;
  redo = !!redo && st.ok; // recast-for-sport: a passed trial made interactive again — transient, touches no state
  const wrap = document.createElement("div");
  wrap.className = "exercise" + (st.ok ? " solved" : "");
  const noDecay = e.type === "type" || e.type === "write"; // practice is safe: no point decay, no combo reset
  const mult = noDecay ? 1 : attemptMultiplier(st.a);
  const worth = Math.round(e.points * mult);
  const totalReps = e.reps || 1;

  wrap.innerHTML = `
    <div class="ex-head">
      <span>TRIAL ${roman(idx + 1)} // ${EX_LABEL[e.type] || "SPEAK THE WORD"}${e.type === "type" && totalReps > 1 && !st.ok ? ` — PASS ${st.reps + 1}/${totalReps}` : ""}</span>
      <span class="ex-pts num">${redo ? "FOR SPORT — NOTHING OWED, NOTHING EARNED" : st.ok ? `+${st.pts} EARNED` : `WORTH ${worth}${gp()}${mult < 1 ? " (diminished)" : ""}`}</span>
    </div>
    <div class="ex-body">
      <p class="prompt">${e.prompt}</p>
      ${e.code ? `<pre><code></code></pre>` : ""}
      ${e.expect && e.type === "write" ? `<div class="lab-expect"><span class="faint" style="font-size:10.5px;letter-spacing:.14em">TARGET OUTPUT</span><pre><code></code></pre></div>` : ""}
      <div class="ex-input"></div>
    </div>
    <div class="ex-hint hidden"></div>
    <div class="ex-why hidden"></div>
    <div class="ex-foot">
      <span class="ex-verdict"></span>
      <span style="display:flex;gap:8px">
        ${!st.ok && e.hint ? `<button class="btn quiet b-hint">${ico("bulb")} WHISPERED HINT (${HINT_COST}${gp()})</button>` : ""}
        ${!st.ok ? `<button class="btn quiet b-orc" title="the candle's hint is the author's fixed nudge; the Oracle is a living spirit you can question">${ico("orb")} ASK THE ORACLE</button>` : ""}
        ${!st.ok && S.inv.skip > 0 ? `<button class="btn quiet b-skip">${ico("scroll")} SCROLL OF REVELATION</button>` : ""}
        ${st.ok && !redo ? `<button class="btn quiet b-redo">RECAST FOR SPORT</button>` : ""}
        ${redo && !onReview ? `<button class="btn quiet b-done">MARK COMPLETE</button>` : ""}
        ${!st.ok || redo ? `<button class="btn b-check">${e.type === "write" ? "INSCRIBE + CAST" : "CAST"}</button>` : ""}
      </span>
    </div>`;

  if (e.code) $("pre code", wrap).textContent = e.code;
  if (e.expect && e.type === "write") $(".lab-expect pre code", wrap).textContent = e.expect;
  const input = $(".ex-input", wrap);
  let getAnswer = () => "";

  if (st.ok && !redo) {
    input.innerHTML = `<div class="dim" style="font-size:13px">${ico("check")} Passed${st.skipped ? " (by scroll)" : ""}. ${e.explain ? esc(e.explain) : ""}</div>`;
    $(".ex-verdict", wrap).className = "ex-verdict ok";
    $(".ex-verdict", wrap).textContent = "THE SEAL HOLDS";
  } else if (e.type === "mc") {
    input.innerHTML = `<div class="choices">${e.choices.map((c, i) =>
      `<label class="choice"><input type="radio" name="${e.id}" value="${i}"><span>${esc(c)}</span></label>`).join("")}</div>`;
    input.querySelectorAll(".choice").forEach((c) => c.addEventListener("click", () => {
      input.querySelectorAll(".choice").forEach((x) => x.classList.remove("sel"));
      c.classList.add("sel");
    }));
    getAnswer = () => { const r = input.querySelector("input:checked"); return r ? +r.value : -1; };
  } else if (e.type === "type") {
    input.innerHTML = `<textarea class="drill-box" data-nopaste="1" rows="${Math.max(2, (e.code || "").split("\n").length + 1)}" spellcheck="false" placeholder="copy it out by hand — the hand remembers what the eye forgets; conjured paste is barred"></textarea>`;
    const box = $("textarea", input);
    box.addEventListener("paste", (ev) => { ev.preventDefault(); toast("No pasting by sorcery. The quill only, apprentice.", "warn"); });
    box.addEventListener("drop", (ev) => ev.preventDefault());
    box.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); $(".b-check", wrap).click(); }
      if (ev.key === "Tab") { ev.preventDefault(); const s0 = box.selectionStart; box.setRangeText("    ", s0, box.selectionEnd, "end"); }
    });
    getAnswer = () => box.value;
  } else if (e.type === "write") {
    input.innerHTML = `
      <div class="code-pad"></div>
      ${e.stdin ? `<div class="faint" style="font-size:11px;margin-top:4px">STDIN fed to your program: <code>${esc(e.stdin.replace(/\n/g, "\\n"))}</code></div>` : ""}
      <pre class="lab-out hidden"></pre>`;
    let pe = null;
    window.GhostEditor.monacoReady.then(() => {
      pe = codePad($(".code-pad", input), e.starter || "",
        () => { const b = $(".b-check", wrap); if (b) b.click(); });
    });
    getAnswer = () => (pe ? pe.getValue() : "");
  } else {
    input.innerHTML = `<div class="ex-answer-row"><input type="text" placeholder="${e.type === "fill" ? "what completes the rune?" : "write your answer"}" spellcheck="false"></div>`;
    const field = $("input", input);
    field.addEventListener("keydown", (ev) => { if (ev.key === "Enter") $(".b-check", wrap).click(); });
    getAnswer = () => field.value;
  }

  const verdict = $(".ex-verdict", wrap);

  // the spell's voice with no charge; the cursor already threw its motes on the CAST press.
  // only a run inscription (write) earns the full drawn sigil — trials stay quick.
  const spellVoice = (ok) => { if (window.GhostAudio && S.audio.sfx) window.GhostAudio.spellHit(ok); };
  const castFeedback = (ok) => {
    if (e.type === "write") return castSigil($(".b-check", wrap) || wrap, ok); // the inscription: the full sigil is drawn
    spellVoice(ok);                                                            // a trial: the spell's voice, no charge...
    const btn = $(".b-check", wrap);                                           // ...and motes burst from the button's heart —
    const r = btn && btn.isConnected ? btn.getBoundingClientRect() : null;     // gone already? burst where it sat when pressed
    const pt = r ? { x: r.left + r.width / 2, y: r.top + r.height / 2 } : lastCastAt;
    if (pt) burst(pt.x, pt.y, ok ? "cast" : "miscast");                        // radial on a hit, sinking + faded on a miss
  };

  function solve() {
    if (redo) { // for sport: the seal already stands — full flourish, no coin, no stats, no save
      castFeedback(true);
      if (onReview) { // a clean recall: grade it and condense to the solved row
        onReview(true);
        wrap.replaceWith(exerciseEl(e, idx));
        return;
      }
      verdict.className = "ex-verdict ok";
      verdict.textContent = "THE SEAL HOLDS — A CLEAN RECAST";
      return;
    }
    const bonus = noDecay ? 0 : comboBonus();
    // recompute — the render-time `mult` goes stale when miss() bumps st.a without re-rendering
    const liveMult = noDecay ? 1 : attemptMultiplier(st.a);
    const pts = Math.round(e.points * liveMult * (1 + bonus) * (S.inv.x2 > 0 ? 2 : 1));
    if (S.inv.x2 > 0) S.inv.x2--;
    st.ok = true; st.pts = pts; S.stats.correct++;
    if (REVIEWABLE.has(e.type)) scheduleReview(st, true); // enroll this recall item in spaced review
    if (!noDecay) {
      S.stats.streak++;
      S.stats.bestStreak = Math.max(S.stats.bestStreak || 0, S.stats.streak);
      if (S.stats.streak === 10) grantBadge("combo-10");
    }
    addCredits(pts, true);
    castFeedback(true);
    toast(`THE SEAL HOLDS // <b>+${pts}</b> ${coin()}${bonus > 0 ? ` <span class="dim">(chant x${(1 + bonus).toFixed(2)})</span>` : ""}${S.inv.x2 > 0 ? ` (catalyst: ${S.inv.x2} left)` : ""}`);
    wrap.replaceWith(exerciseEl(e, idx));
  }

  function miss(msg) {
    if (redo) { // for sport: no penalty, no stats — the original seal is untouched
      castFeedback(false);
      verdict.className = "ex-verdict no";
      verdict.textContent = msg || (onReview ? "FADED — study it once more; it will come back around" : "NOT QUITE — BUT YOUR SEAL ALREADY STANDS; RECAST AT LEISURE");
      if (e.whyWrong) { const w = $(".ex-why", wrap); if (w) { w.classList.remove("hidden"); w.textContent = "WHY IT FAILED :: " + e.whyWrong; } }
      if (onReview) onReview(false);
      return;
    }
    S.stats.wrong++;
    castFeedback(false);
    if (noDecay) {
      verdict.className = "ex-verdict no";
      verdict.textContent = msg || "NOT QUITE — study it and try again (drills carry no penalty)";
    } else if (S.inv.firewall > 0) {
      S.inv.firewall--;
      verdict.className = "ex-verdict no";
      verdict.textContent = `MISCAST — YOUR WARD ABSORBED IT (${S.inv.firewall} charges left)`;
    } else {
      st.a++;
      S.stats.streak = 0;
      updateHud();
      verdict.className = "ex-verdict no";
      verdict.textContent = `THE SPELL FIZZLES — now worth ${Math.round(e.points * attemptMultiplier(st.a))}${gp()}`;
      $(".ex-pts", wrap).textContent = `WORTH ${Math.round(e.points * attemptMultiplier(st.a))}${gp()} (diminished)`;
    }
    // elaborated feedback: turn the mistake into a micro-lesson (author-supplied)
    if (e.whyWrong) {
      const w = $(".ex-why", wrap);
      if (w) { w.classList.remove("hidden"); w.textContent = "WHY IT FAILED :: " + e.whyWrong; }
    }
    save();
  }

  const bCheck = $(".b-check", wrap);
  if (bCheck) bCheck.onclick = async () => {
    const ans = getAnswer();
    if (ans === -1 || String(ans).trim() === "") { verdict.className = "ex-verdict no"; verdict.textContent = "THE PAGE IS BLANK"; return; }

    if (e.type === "type") {
      const diff = firstDiff(ans, e.code);
      if (diff) {
        miss(`LINE ${diff.line}: expected «${diff.expected}» got «${diff.got}»${diff.hint}`);
        return;
      }
      if (redo) { solve(); return; } // a recast is a single pass — the reps ladder stays untouched
      st.reps++;
      if (st.reps < totalReps) {
        sfx("tick");
        castFeedback(true);
        save();
        toast(`PASS ${st.reps}/${totalReps} COMPLETE // again — from memory, not from looking`);
        const fresh = exerciseEl(e, idx);
        wrap.replaceWith(fresh);
        const ta = fresh.querySelector("textarea");
        if (ta) ta.focus();     // keep the operator's hands where they were
      } else solve();
      return;
    }

    if (e.type === "write") {
      bCheck.disabled = true; bCheck.textContent = "INSCRIBING...";
      const out = $(".lab-out", wrap);
      out.classList.remove("hidden");
      out.textContent = runLabel() + " — the forge takes your inscription...";
      let data;
      try {
        const r = await fetch("/api/runsnippet", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code: ans, stdin: e.stdin || "" }),
        });
        data = await r.json();
      } catch (err) { data = { ok: false, output: "server error: " + err }; }
      bCheck.disabled = false; bCheck.textContent = "INSCRIBE + CAST";
      out.textContent = data.output || "(the stone stays silent)";
      if (!data.ok) { miss("THE FORGE REJECTED IT — read its complaint, mend the inscription, cast again (no penalty)"); return; }
      const pass = e.expectRe ? new RegExp(e.expectRe, "m").test(data.output) : normCode(data.output) === normCode(e.expect || "");
      if (pass) solve();
      else {
        const d = e.expectRe ? null : firstDiff(data.output, e.expect || "");
        miss(d ? `IT CASTS, BUT LINE ${d.line} differs: expected «${d.expected}» got «${d.got}»${d.hint}` : "IT CASTS, BUT THE UTTERANCE DOES NOT MATCH THE TARGET");
      }
      return;
    }

    if (checkAnswer(e, ans)) solve();
    else {
      miss();
      if (e.type === "mc") {
        const selEl = input.querySelector(".choice.sel");
        if (selEl) { selEl.classList.add("wrong"); setTimeout(() => selEl.classList.remove("wrong"), 900); }
      }
    }
  };

  const bRedo = $(".b-redo", wrap);
  if (bRedo) bRedo.onclick = () => wrap.replaceWith(exerciseEl(e, idx, true));
  const bDone = $(".b-done", wrap);
  if (bDone) bDone.onclick = () => wrap.replaceWith(exerciseEl(e, idx));

  const bHint = $(".b-hint", wrap);
  if (bHint) bHint.onclick = () => {
    const reveal = () => {
      st.hint = true;
      const h = $(".ex-hint", wrap);
      h.classList.remove("hidden");
      h.textContent = "THE CANDLE WHISPERS :: " + e.hint;
      bHint.remove(); save();
    };
    if (st.hint) { reveal(); return; }
    modal(`<h2>BUY A WHISPERED HINT?</h2><p class="dim">The candle knows, but it charges: <b>${HINT_COST}</b> ${coin()} (you have <span class="num">${S.credits}</span>).</p>`,
      [["KEEP YOUR COIN", "quiet"], [`PAY ${HINT_COST}${gp()}`, "", () => { if (spend(HINT_COST)) reveal(); }]]);
  };

  // the Oracle, aimed at THIS trial: same scrying economy as the lesson-level
  // button, but the spirit sees the trial's prompt, code, target, and the
  // student's current attempt (hints stay distinct: fixed authored nudges).
  const bOrc = $(".b-orc", wrap);
  if (bOrc) bOrc.onclick = () => {
    const c = oracleContext();
    const plain = document.createElement("div");
    plain.innerHTML = e.prompt || "";
    let detail = `${c.detail}\n\nTHE TRIAL THE STUDENT IS ASKING ABOUT (${EX_LABEL[e.type] || "SPEAK THE WORD"}):\n${plain.textContent.trim()}`;
    if (e.code) detail += `\n\nCODE SHOWN WITH THE TRIAL:\n${e.code}`;
    if (e.type === "write" && e.expect) detail += `\n\nREQUIRED OUTPUT:\n${e.expect}`;
    const draft = getAnswer();
    if (typeof draft === "string" && draft.trim() && draft.trim() !== (e.starter || "").trim())
      detail += `\n\nSTUDENT'S CURRENT ATTEMPT:\n${draft.slice(0, 3000)}`;
    askOracle(`${c.label} / TRIAL ${roman(idx + 1)}`, detail, "");
  };

  const bSkip = $(".b-skip", wrap);
  if (bSkip) bSkip.onclick = () => {
    modal(`<h2>UNROLL A SCROLL OF REVELATION?</h2><p class="dim">The answer writes itself; the trial is sealed at its full ${e.points}${gp()}. You carry ${S.inv.skip}.</p>`,
      [["NOT YET", "quiet"], ["UNROLL IT", "", () => {
        S.inv.skip--; st.ok = true; st.skipped = true; st.pts = e.points;
        addCredits(e.points, true);
        toast(`THE SCROLL BURNS AS IT READS ITSELF // <b>+${e.points}</b> ${coin()}`);
        wrap.replaceWith(exerciseEl(e, idx));
      }]]);
  };

  return wrap;
}

function normalize(s2) {
  return String(s2).trim().toLowerCase().replace(/\s+/g, " ").replace(/;$/, "").replace(/^["']|["']$/g, "");
}
function checkAnswer(e, ans) {
  if (e.type === "mc") return ans === e.answer;
  const norm = normalize(ans);
  const targets = [e.answer].concat(e.accept || []).map(normalize);
  return targets.includes(norm);
}
