/* The pages of the tome: your ledger, a chapter, a lesson, the peddler's table,
   and the grimoire of every incantation you have mastered. */
import { BLACKICE_CAP, BLACKICE_N, EARNED_THEME, J, RANKS, SHOP, SRANK_MULT, coin, gp, persona, roman } from "../core/config.js";
import { $, esc, ico, modal, refreshCoins, sfx, toast } from "../core/dom.js";
import { atkQualifying } from "../game/duel.js";
import { GATE_MIN, exerciseEl, reviewBanner, reviewDue, reviewGate, startReview, wireReview } from "../game/exercise.js";
import { askOracle, grabSelection } from "../bench/oracle.js";
import { freestyleUnlocked, fsBest, lessonDone, rank, secById, sectionExercises, sectionPassed, sectionSolvedFrac, sectionUnlocked, spend } from "../game/progress.js";
import { getState, save } from "../core/store.js";
import { sections, tome } from "../core/bootstrap.js";
import { go } from "../core/router.js";
import { masteryPanelHtml, sectionLabsHtml } from "../mastery/ledger-view.js";
import { exerciseEvidence, isEvidenceTome, requiredExercises, workingStatus } from "../mastery/policy.js";

// ------------------------------------------------------------ HOME
export function renderHome() {
  const v = $("#view-home");
  v.classList.remove("hidden");
  const r = rank();
  const nextSec = sections().find((sec, i) => sectionUnlocked(i) && !sectionPassed(sec));
  const badges = Object.entries(getState().badges).sort((a, b2) => a[1].at - b2[1].at);
  const pct = r.next ? Math.min(100, Math.round(((getState().earned - r.floor) / (r.next[0] - r.floor)) * 100)) : 100;

  v.innerHTML = `
    <div class="crumb">${esc((J().narrative && J().narrative.logo) || "ARCANUM")} — your ledger</div>
    <div class="objective-block">
      <div class="ob-label">THE GREAT WORK</div>
      <p class="ob-text">${esc((J().narrative && J().narrative.objective) || "")}</p>
    </div>
    <div class="home-grid">
      <div>
        <div class="rank-block">
          <div class="faint" style="font-size:11px;letter-spacing:.18em">YOUR TITLE</div>
          <div class="rank-name">${r.name}</div>
          <div class="rank-next">
            ${r.next
              ? `<span class="dim" style="font-size:12.5px">next: ${r.next[1]} at <span class="num">${r.next[0]}</span> lifetime ${coin()} (<span class="num">${getState().earned}</span> earned)</span><div class="meter"><i style="width:${pct}%"></i></div>`
              : `<span class="dim">The highest title. Even the candle bows a little.</span>`}
          </div>
        </div>
        <div class="stat-row"><span>TITLES EARNED</span><b class="num">${RANKS.filter((x) => getState().earned >= x[0]).length} / ${RANKS.length}</b></div>
        <div class="stat-row"><span>${coin().toUpperCase()} IN YOUR PURSE</span><b class="num">${getState().credits}</b></div>
        <div class="stat-row"><span>LIFETIME EARNED</span><b class="num">${getState().earned}</b></div>
        <div class="stat-row"><span>TRIALS PASSED</span><b class="num">${Object.values(getState().ex).filter((e) => e.ok).length}</b></div>
        <div class="stat-row"><span>MISCASTS SURVIVED</span><b class="num">${getState().stats.wrong}</b></div>
        <div class="stat-row"><span>SPELLS CAST</span><b class="num">${getState().stats.runs}</b></div>
        <div class="stat-row"><span>WORKINGS PRESENTED</span><b class="num">${getState().stats.subs}</b></div>
        <div class="stat-row"><span>CHAPTERS SEALED</span><b class="num">${sections().filter(sectionPassed).length} / ${sections().length}</b></div>
        <div class="stat-row"><span>HEXES BROKEN</span><b class="num">${getState().stats.intrusionW || 0} / ${(getState().stats.intrusionW || 0) + (getState().stats.intrusionL || 0)}</b></div>
        <div class="stat-row"><span>DUELS WON</span><b class="num">${getState().stats.atkW || 0} / ${(getState().stats.atkW || 0) + (getState().stats.atkL || 0)}</b></div>
        <div class="stat-row"><span>REVIEWS RE-FORGED</span><b class="num">${getState().stats.reviews || 0}</b></div>
        ${EARNED_THEME ? `<div class="stat-row"><span>${esc(EARNED_THEME.name)} PROGRESS</span><b class="num">${getState().themes[EARNED_THEME.id] ? "WON" : atkQualifying() + " / " + BLACKICE_N}</b></div>` : ""}
        ${nextSec ? `
        <div class="continue-strip">
          <div>
            <div class="faint" style="font-size:11px;letter-spacing:.14em">THE WORK CONTINUES</div>
            <b>${esc(nextSec.codename)}</b> <span class="dim">— ${esc(nextSec.title)}</span>
          </div>
          <button class="btn" id="btn-continue">TAKE UP THE QUILL ${ico("arrow")}</button>
        </div>` : `
        <div class="continue-strip"><div><b>${esc((J().narrative && J().narrative.completeText) || "THE GREAT WORK IS COMPLETE.")}</b> <span class="dim">The artifact is real, and it is yours. Carry it into the world.</span></div></div>`}
      </div>
      <div>
        <h2 style="margin-top:0">YOUR SATCHEL</h2>
        ${SHOP.filter((s2) => s2.kind === "consumable").map((item) => `<div class="stat-row"><span>${ico(item.ico)} ${item.name}</span><b class="num">${getState().inv[item.id] || 0}</b></div>`).join("")}
        <h2>SIGILS <span class="dim num" style="font-weight:400">(${badges.length})</span></h2>
        <div class="badge-grid cascade">
          ${badges.length ? badges.map(([id, b2], i) => `
            <div class="badge earned" style="--i:${i}">${ico("seal", "b-ico")}
              <span class="b-name">${esc(b2.name)}</span>
              <span class="b-desc">${esc(b2.desc || "")}</span>
            </div>`).join("") : `<div class="dim" style="grid-column:1/-1">No sigils pressed yet. Complete a chapter's Great Working to earn your first.</div>`}
        </div>
      </div>
    </div>
    ${masteryPanelHtml(tome(), sections(), getState())}`;
  const cont = $("#btn-continue");
  if (cont) cont.onclick = () => go("section", nextSec.id);
  v.querySelectorAll("[data-mastery-lab]").forEach((button) =>
    button.onclick = () => go("mastery-lab", button.dataset.masteryLab));
}

// ------------------------------------------------------------ SECTION
export function renderSection(sid) {
  const sec = secById(sid);
  const v = $("#view-section");
  v.classList.remove("hidden");
  $("#hud-op").textContent = "— " + sec.codename.toLowerCase();
  const frac = sectionSolvedFrac(sec);
  const fsOpen = freestyleUnlocked(sec);
  const best = fsBest(sid);
  const evidenceMode = isEvidenceTome(tome());
  const workingLabel = workingStatus(best, fsOpen);

  v.innerHTML = `
    <div class="crumb"><button data-nav="home">LEDGER</button> / ${esc(sec.codename)}</div>
    ${reviewBanner()}
    <div class="sec-head">
      <div class="sec-codename">${esc(sec.codename)}</div>
      <h1>${esc(sec.title)}</h1>
      <div class="dim" style="font-size:12.5px;font-style:italic">WHAT YOU WILL FORGE: ${esc(sec.build)}</div>
      <p class="sec-brief">${sec.brief}</p>
    </div>
    <h2>THE MASTER'S LESSONS <span class="dim" style="font-family:var(--fell);font-size:12.5px;letter-spacing:0">(study each, then face its trials for ${coin()})</span></h2>
    <div class="lesson-list cascade">
      ${sec.lessons.map((l, i) => {
        const exercises = evidenceMode ? requiredExercises(l) : l.exercises;
        const total = exercises.length;
        const done = evidenceMode
          ? exercises.filter((exercise) => exerciseEvidence(getState(), exercise).resolved).length
          : exercises.filter((e) => getState().ex[e.id] && getState().ex[e.id].ok).length;
        const pts = l.exercises.reduce((a, e) => a + e.points, 0);
        return `<button class="lesson-row" data-lesson="${l.id}" style="--i:${i}">
          <span class="l-num">${roman(i + 1)}</span>
          <span>${esc(l.title)}</span>
          <span class="l-pts num">${evidenceMode ? `${done}/${total} resolved` : `${done}/${total} · ${pts}${gp()}`}</span>
          <span class="l-state">${done === total && total > 0 ? ico("check") : ""}</span>
        </button>`;
      }).join("")}
    </div>
    <div class="freestyle-cta ${fsOpen ? "ready" : ""}">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap">
        <div>
          <div class="sec-codename" style="letter-spacing:.18em">THE GREAT WORKING</div>
          <b>${esc(sec.freestyle.title)}</b>
          <div class="dim" style="font-size:12.5px;margin-top:4px">
            ${fsOpen
              ? (best ? `${evidenceMode ? "Working status" : "Best judgement"}: <b class="num">${esc(workingLabel)} (${best.total}/100)</b> — ${evidenceMode ? "every essential behavior must remain green" : "present it again to improve"}.` : evidenceMode ? `Working status: <b>ready</b> — submit an isolated snapshot for deterministic evidence and a B-or-better assessment.` : `The scroll awaits. Write real code, be judged by ${esc(persona())}, earn up to <span class="num">${Math.round(sec.freestyle.reward * SRANK_MULT)}</span> ${coin()}.`)
              : evidenceMode ? `Working status: <b>${esc(workingLabel)}</b> — resolve every required activity and clear due review before assessment.`
              : `SEALED — pass <span class="num">${Math.ceil(sectionExercises(sec).length * 0.7)}</span> of <span class="num">${sectionExercises(sec).length}</span> trials to break the seal (<span class="num">${Math.round(frac * 100)}%</span> done, need 70%).`}
          </div>
        </div>
        <button class="btn ${fsOpen ? "" : "quiet"}" id="btn-fs" ${fsOpen ? "" : "disabled"}>${ico("scroll")} UNROLL THE SCROLL</button>
      </div>
    </div>
    ${sectionLabsHtml(tome(), sid, getState())}`;
  v.querySelectorAll("[data-lesson]").forEach((b) => (b.onclick = () => go("lesson", sid, b.dataset.lesson)));
  $("[data-nav=home]", v).onclick = () => go("home");
  wireReview(v);
  const fsBtn = $("#btn-fs", v);
  if (fsBtn && fsOpen) fsBtn.onclick = () => reviewGate(() => go("freestyle", sid));
  v.querySelectorAll("[data-mastery-lab]").forEach((button) =>
    button.onclick = () => go("mastery-lab", button.dataset.masteryLab));
}

// ------------------------------------------------------------ LESSON
export function renderLesson(sid, lid) {
  const sec = secById(sid);
  const li = sec.lessons.findIndex((l2) => l2.id === lid);
  const l = sec.lessons[li];
  const v = $("#view-lesson");
  v.classList.remove("hidden");
  $("#hud-op").textContent = "— " + sec.codename.toLowerCase() + ", lesson " + roman(li + 1).toLowerCase();
  getState().read[lid] = true;
  const projectSteps = (l.artifactSteps || []).map((step) => {
    const before = step.mode === "replace" && step.find != null
      ? `<div class="artifact-code-label">FIND EXACTLY</div><pre><code>${esc(step.find)}</code></pre>` : "";
    const after = step.content != null
      ? `<div class="artifact-code-label">${step.mode === "replace" ? "REPLACE WITH" : "CONTENT"}</div><pre><code>${esc(step.content)}</code></pre>` : "";
    const workChecks = Array.isArray(step.checks) ? step.checks : [];
    const checks = workChecks.length
      ? `<div class="artifact-code-label">PROVE IT</div><ul>${workChecks.map((check) => `<li>${esc(check)}</li>`).join("")}</ul>` : "";
    const mode = step.mode === "author" ? "YOU BUILD" : (step.mode || "edit");
    return `<article class="artifact-step"><div class="artifact-step-head"><b>${esc(step.path || "")}</b><span>${esc(mode)}</span></div>
      <p>${esc(step.instruction || "")}</p>${before}${after}${checks}</article>`;
  }).join("");
  const assetGuides = (sec.assets || []).filter((asset) => asset.lesson === lid).map((asset) => `
    <article class="asset-guide"><div class="artifact-step-head"><b>${esc(asset.kind || "ASSET")} // ${esc(asset.destination || "")}</b><span>YOU SOURCE IT</span></div>
      <p>${esc(asset.sourceGuidance || "")}</p><p><b>LICENSE:</b> ${esc(asset.licenseGuidance || "")}</p>
      <div class="asset-sources">${(asset.sources || []).map((source) => `<a href="${esc(source.url)}" target="_blank" rel="noopener">${esc(source.label)} <span>(${esc(source.license)})</span></a>`).join("")}</div>
    </article>`).join("");

  v.innerHTML = `
    <div class="crumb"><button data-nav="home">LEDGER</button> / <button data-nav="sec">${esc(sec.codename)}</button> / LESSON ${roman(li + 1)}</div>
    <h1>${esc(l.title)}</h1>
    <div class="lesson-body">${l.body}</div>
    ${projectSteps ? `<section class="artifact-steps"><h2>${ico("scroll")} THE PROJECT LEDGER</h2>${projectSteps}</section>` : ""}
    ${assetGuides ? `<section class="artifact-steps"><h2>${ico("book")} HUMAN-SOURCED MATERIALS</h2><p class="dim">The tome does not create media. Choose and license these materials yourself, then place them at the exact paths shown.</p>${assetGuides}</section>` : ""}
    ${l.readings && l.readings.length ? `
    <div class="readings">
      <h2 style="margin-top:0">${ico("book")} THE MORTAL LIBRARY</h2>
      ${l.readings.map((r) => `<div class="r-item"><span class="tag${r.essential ? " ac" : ""}">${r.essential ? "ESSENTIAL" : "OPTIONAL"}</span><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.label)}</a></div>`).join("")}
    </div>` : ""}
    <div style="display:flex;justify-content:space-between;align-items:center;gap:12px">
      <h2>THE TRIALS</h2>
      <button class="btn quiet" id="b-oracle">${ico("orb")} CONSULT THE ORACLE (${getState().inv.oracle || 0})</button>
    </div>
    <div id="ex-list"></div>
    <div class="lesson-nav">
      ${li > 0 ? `<button class="btn quiet" data-go="${sec.lessons[li - 1].id}">← PREVIOUS LESSON</button>` : `<span></span>`}
      ${li < sec.lessons.length - 1 ? `<button class="btn ghost" data-go="${sec.lessons[li + 1].id}">NEXT LESSON →</button>` : `<button class="btn ghost" data-nav="sec2">BACK TO THE CHAPTER →</button>`}
    </div>`;

  $("[data-nav=home]", v).onclick = () => go("home");
  $("[data-nav=sec]", v).onclick = () => go("section", sid);
  v.querySelectorAll("[data-go]").forEach((b) => (b.onclick = () => go("lesson", sid, b.dataset.go)));
  const b2 = $("[data-nav=sec2]", v); if (b2) b2.onclick = () => go("section", sid);

  const exList = $("#ex-list", v);
  const fillTrials = () => l.exercises.forEach((e, i) => exList.appendChild(exerciseEl(e, i)));
  // the review gate: a lesson with unpassed trials is barred while a real
  // backlog of old seals is due — the body and readings above stay free
  const fresh = l.exercises.some((e) => !(getState().ex[e.id] && getState().ex[e.id].ok));
  const nDue = reviewDue().length;
  if (fresh && nDue >= GATE_MIN) {
    exList.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;padding:16px;border:1px solid var(--line-hi);border-radius:var(--rad);background:var(--ac-bg)">
      <div><b>${ico("bell")} THE MASTER BARS THE TRIALS</b> <span class="dim" style="font-size:12.5px">${nDue} old seals are fading — re-forge ${Math.min(8, nDue)} of them and the way opens.</span></div>
      <button class="btn" id="btn-gate">${ico("scroll")} BEGIN REVIEW</button></div>`;
    $("#btn-gate", v).onclick = () => startReview(() => { exList.innerHTML = ""; fillTrials(); });
  } else fillTrials();

  const bo = $("#b-oracle", v);
  let boSel = "";
  bo.onpointerdown = () => { boSel = grabSelection(); };
  bo.onclick = () => askOracle(`${sec.codename} / ${l.title}`, `${sec.codename} — ${sec.title} / lesson: ${l.title}`, boSel);
  save();
}

// ------------------------------------------------------------ code book
export function showCodeBook() {
  const scratch = document.createElement("div");
  const ops = [];
  for (const sec of sections()) {
    const lessons = [];
    for (const l of sec.lessons || []) {
      if (!lessonDone(l)) continue;
      scratch.innerHTML = l.body || "";
      const blocks = [...scratch.querySelectorAll("pre")].map((p) => p.textContent.trim()).filter(Boolean);
      blocks.push(...(l.artifactSteps || []).map((step) => step.content || "").filter(Boolean));
      lessons.push({ title: l.title, blocks });
    }
    if (lessons.length) ops.push({ sec, lessons });
  }
  const body = ops.map(({ sec, lessons }) => `
    <div class="cb-op">
      <div class="cb-op-head">${esc(sec.codename)} — ${esc(sec.title)} <span class="num dim">${lessons.length}/${sec.lessons.length} lessons</span></div>
      ${lessons.map((l) => `
        <div class="cb-lesson">
          <div class="cb-lesson-title">${ico("check")}<span>${esc(l.title)}</span></div>
          ${l.blocks.map((b) => `<pre class="cb-code">${esc(b)}</pre>`).join("")
            || '<div class="dim" style="font-size:12px">Theory alone — no incantations in this lesson.</div>'}
        </div>`).join("")}
    </div>`).join("");
  modal(`<h2>GRIMOIRE OF LEARNED INCANTATIONS</h2>
    <p class="dim" style="font-size:12px;margin:2px 0 12px">Every incantation and pattern from the lessons you have mastered, indexed by chapter.</p>
    <div class="cb-scroll">${body || '<p class="dim">The grimoire is empty. Pass every trial in a lesson and its incantations are copied in.</p>'}</div>`,
    [["CLOSE THE GRIMOIRE", "quiet"]]);
  $(".modal").classList.add("wide");
}

// ------------------------------------------------------------ SHOP
export function renderShop() {
  const v = $("#view-shop");
  v.classList.remove("hidden");
  v.innerHTML = `
    <div class="crumb"><button data-nav="home">LEDGER</button> / THE PEDDLER</div>
    <h1>THE PEDDLER'S WARES</h1>
    <p class="dim">A hooded figure spreads a cloth of curiosities across the corner of your table. Spend the ${coin()} your trials have earned. No refunds — the peddler has already forgotten your face.</p>
    <div class="shop-grid cascade">
      ${SHOP.map((item, i) => {
        const owned = item.kind === "theme" ? getState().themes[item.theme] : null;
        const invCount = item.kind === "consumable" ? (getState().inv[item.id] || 0) : 0;
        const active = item.kind === "theme" && getState().theme === item.theme;
        return `<div class="shop-item" style="--i:${i}">
          ${ico(item.kind === "theme" ? "ink" : item.ico, "s-ico")}
          <span class="s-name">${item.name}</span>
          ${item.kind === "theme"
            ? (owned
              ? `<button class="btn ${active ? "quiet" : "ghost"}" data-equip="${item.theme}" ${active ? "disabled" : ""}>${active ? "IN USE" : "USE THIS INK"}</button>`
              : `<button class="btn ghost" data-buy="${item.id}"><span class="num">${item.cost}</span>${gp()}</button>`)
            : `<button class="btn ghost" data-buy="${item.id}"><span class="num">${item.cost}</span>${gp()}</button>`}
          <span class="s-desc">${item.desc}</span>
          ${item.kind === "consumable" ? `<span class="s-own num">in your satchel: ${item.charges ? `${invCount} charges` : invCount}</span>` : ""}
        </div>`;
      }).join("")}
      ${EARNED_THEME ? `<div class="shop-item" style="--i:${SHOP.length};${getState().themes[EARNED_THEME.id] ? "" : "opacity:.55"}">
        ${ico(getState().themes[EARNED_THEME.id] ? "ink" : "lock", "s-ico")}
        <span class="s-name">${esc(EARNED_THEME.name)}</span>
        ${getState().themes[EARNED_THEME.id]
          ? `<button class="btn ${getState().theme === EARNED_THEME.id ? "quiet" : "ghost"}" data-equip="${esc(EARNED_THEME.id)}" ${getState().theme === EARNED_THEME.id ? "disabled" : ""}>${getState().theme === EARNED_THEME.id ? "IN USE" : "USE THIS INK"}</button>`
          : `<button class="btn ghost" disabled>NOT FOR SALE</button>`}
        <span class="s-desc">${getState().themes[EARNED_THEME.id]
          ? esc(EARNED_THEME.desc || "")
          : `The peddler will not name a price. Win ${BLACKICE_N} qualifying SPELL DUELS to claim it (at most ${BLACKICE_CAP} counted per circle). Progress: ${atkQualifying()}/${BLACKICE_N}.`}</span>
      </div>` : ""}
    </div>`;
  $("[data-nav=home]", v).onclick = () => go("home");
  v.querySelectorAll("[data-buy]").forEach((b) => (b.onclick = () => {
    const item = SHOP.find((x) => x.id === b.dataset.buy);
    modal(`<h2>BUY ${esc(item.name)}?</h2><p class="dim">${item.desc}</p><p>The peddler asks <b class="num">${item.cost}</b>${gp()} — your purse holds <span class="num">${getState().credits}</span>${gp()}.</p>`,
      [["WALK AWAY", "quiet"], ["SHAKE ON IT", "", () => {
        if (!spend(item.cost)) return;
        if (item.kind === "theme") { getState().themes[item.theme] = true; toast(`The ink and vellum are yours. Put them to use from the peddler's table.`); }
        else { getState().inv[item.id] = (getState().inv[item.id] || 0) + (item.charges || 1); toast(`<b>${esc(item.name)}</b> slipped into your satchel.`); }
        sfx("peddler"); // same voice as the satchel desk object
        save(); renderShop();
      }]]);
  }));
  v.querySelectorAll("[data-equip]").forEach((b) => (b.onclick = () => {
    getState().theme = b.dataset.equip;
    document.body.dataset.theme = getState().theme;
    window.GhostEditor.setTheme(getState().theme);
    refreshCoins();
    save(); renderShop();
  }));
}
