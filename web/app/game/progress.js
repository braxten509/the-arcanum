/* Economy, chapter progress, the HUD, the sidebar, and navigation. */
import { ATTEMPT_MULT, BADGES, COMBO_CAP, COMBO_STEP, RANKS, coin, roman } from "../core/config.js";
import { $, esc, ico, sfx, toast } from "../core/dom.js";
import { S, save } from "../core/state.js";
import { renderHome, renderLesson, renderSection, renderShop } from "../ui/views.js";
import { renderFreestyle } from "../bench/workbench.js";

// ------------------------------------------------------------ economy
export function rank() {
  let r = RANKS[0], next = null;
  for (let i = 0; i < RANKS.length; i++) {
    if (S.earned >= RANKS[i][0]) r = RANKS[i];
    else { next = RANKS[i]; break; }
  }
  return { name: r[1], floor: r[0], next };
}

export function addCredits(n, silentToast) {
  if (n === 0) return;
  const before = rank().name;
  S.credits += n;
  if (n > 0) S.earned += n;
  const after = rank().name;
  updateHud();
  if (!silentToast && n > 0) toast(`<b>+${n}</b> ${coin()}`);
  if (before !== after) {
    toast(`YOU RISE // you are now <b>${after}</b>`, "warn");
    grantBadge("rank-" + after.toLowerCase().replace(/\s+/g, "-"), "TITLE: " + after, "Attained the title of " + after + ".");
  }
  save();
}

export function spend(n) {
  if (S.credits < n) { toast(`Your purse is light. Need <b>${n}</b> ${coin()}, have ${S.credits}.`, "bad"); return false; }
  S.credits -= n; updateHud(); save(); return true;
}

export function grantBadge(id, name, desc) {
  if (S.badges[id]) return;
  const b = BADGES[id];
  name = name || (b && b.name) || id;
  desc = desc || (b && b.desc) || "";
  S.badges[id] = { name, desc, at: Date.now() };
  toast(`${ico("seal")} SIGIL PRESSED // <b>${esc(name)}</b>`, "warn");
  if (window.GhostAudio && S.audio.sfx) window.GhostAudio.sfx("badge");
  save();
  if (S.nav && S.nav.view === "home") renderHome(); // the ledger shows sigils live
}

export function attemptMultiplier(a) { return ATTEMPT_MULT[Math.min(a, ATTEMPT_MULT.length - 1)]; }

// ------------------------------------------------------------ progress
export function sectionExercises(sec) {
  const out = [];
  for (const l of sec.lessons) for (const e of l.exercises) out.push(e);
  return out;
}
export function sectionSolvedFrac(sec) {
  const exs = sectionExercises(sec);
  if (!exs.length) return 1;
  return exs.filter((e) => S.ex[e.id] && S.ex[e.id].ok).length / exs.length;
}
export function freestyleUnlocked(sec) { return !!S.spellAll || sectionSolvedFrac(sec) >= 0.7; }
export function fsBest(sid) { return (S.fs[sid] && S.fs[sid].best) || null; }
export function sectionPassed(sec) { const b = fsBest(sec.id); return b && b.total >= 60; }
export function sectionUnlocked(i) { return !!S.spellAll || i === 0 || sectionPassed(window.SECTIONS[i - 1]); }
export function sectionProgress(sec) {
  return sectionSolvedFrac(sec) * 0.7 + (sectionPassed(sec) ? 0.3 : 0);
}
// a lesson is "completed" once every one of its exercises is cracked
// (lessons without exercises count once they've been opened/read)
export function lessonDone(l) {
  return l.exercises && l.exercises.length
    ? l.exercises.every((e) => S.ex[e.id] && S.ex[e.id].ok)
    : !!S.read[l.id];
}

// ------------------------------------------------------------ HUD + sidebar
export function comboBonus() { return Math.min(COMBO_CAP, Math.max(0, (S.stats.streak - 1) * COMBO_STEP)); }

export function updateHud() {
  $("#hud-credits").textContent = S.credits;
  $("#hud-rank").textContent = rank().name;
  const passed = window.SECTIONS.filter(sectionPassed).length;
  $("#side-progress").textContent = passed + "/" + window.SECTIONS.length;
  const combo = $("#hud-combo");
  if (combo) {
    if (S.stats.streak >= 2) {
      combo.classList.remove("hidden");
      combo.textContent = `COMBO x${(1 + comboBonus()).toFixed(2)}`;
    } else combo.classList.add("hidden");
  }
  const bAtk = $("#obj-wand");
  if (bAtk) {
    const d = Math.min(window.ATTACK_TIERS.length, passed);
    bAtk.classList.toggle("locked", d < 1);
    // the tooltip lives on the hit strip: the button itself takes no pointer events
    const wHit = $("#obj-wand .w-hit");
    if (wHit) wHit.title = d < 1 ? "Seal your first chapter before challenging a rival" : `Duel a rival of the ${roman(d)} circle`;
  }
}

export function renderSidebar() {
  const nav = $("#ops-list");
  nav.innerHTML = "";
  window.SECTIONS.forEach((sec, i) => {
    const unlocked = sectionUnlocked(i);
    const passed = sectionPassed(sec);
    const b = document.createElement("button");
    b.className = "op-item" + (unlocked ? "" : " locked") + (S.nav.sec === sec.id && S.nav.view !== "home" && S.nav.view !== "shop" ? " active" : "");
    b.innerHTML = `
      <span class="op-num">${roman(i + 1)}</span>
      <span class="op-name">${esc(sec.short || sec.codename)}</span>
      <span class="op-state">${passed ? ico("check", "done") : unlocked ? "" : ico("lock", "lock")}</span>
      <span class="op-bar"><i style="width:${Math.round(sectionProgress(sec) * 100)}%"></i></span>`;
    b.onclick = () => {
      if (!unlocked) { toast("THE PAGE IS SEALED // finish the previous chapter's Great Working first (grade D or better).", "bad"); return; }
      go("section", sec.id);
    };
    nav.appendChild(b);
  });
  updateHud();
}

// ------------------------------------------------------------ navigation
export function go(view, sec, lesson, pageSound = true) {
  const moved = !S.nav || S.nav.view !== view || S.nav.sec !== (sec || null) || S.nav.lesson !== (lesson || null);
  S.nav = { view, sec: sec || null, lesson: lesson || null };
  save();
  for (const v of document.querySelectorAll(".view")) v.classList.add("hidden");
  // the Great Working unrolls a wider scroll and sweeps the desk clear
  $("#parchment").classList.toggle("wide", view === "freestyle");
  const hudOp = $("#hud-op");
  if (view === "home") { renderHome(); hudOp.textContent = "— your ledger"; }
  else if (view === "shop") { renderShop(); hudOp.textContent = "— the peddler's wares"; }
  else if (view === "section") { renderSection(sec); }
  else if (view === "lesson") { renderLesson(sec, lesson); }
  else if (view === "freestyle") { renderFreestyle(sec); }
  renderSidebar();
  $("#main").scrollTop = 0;
  if (moved && pageSound) sfx("page");
}

export const secById = (id) => window.SECTIONS.find((s2) => s2.id === id);
