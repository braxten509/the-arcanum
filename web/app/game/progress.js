/* Economy, chapter progress, the HUD, the sidebar, and navigation. */
import { ATTEMPT_MULT, BADGES, COMBO_CAP, COMBO_STEP, RANKS, coin, roman } from "../core/config.js";
import { $, esc, ico, sfx, toast } from "../core/dom.js";
import { getState, save } from "../core/store.js";
import { isEvidenceTome, lessonResolved, sectionResolution, workingPassed, workingUnlocked } from "../mastery/policy.js";
import { sections, tome } from "../core/bootstrap.js";
import { go } from "../core/router.js";

// ------------------------------------------------------------ economy
export function rank() {
  let r = RANKS[0], next = null;
  for (let i = 0; i < RANKS.length; i++) {
    if (getState().earned >= RANKS[i][0]) r = RANKS[i];
    else { next = RANKS[i]; break; }
  }
  return { name: r[1], floor: r[0], next };
}

export function addCredits(n, silentToast) {
  if (n === 0) return;
  const before = rank().name;
  getState().credits += n;
  if (n > 0) getState().earned += n;
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
  if (getState().credits < n) { toast(`Your purse is light. Need <b>${n}</b> ${coin()}, have ${getState().credits}.`, "bad"); return false; }
  getState().credits -= n; updateHud(); save(); return true;
}

export function grantBadge(id, name, desc) {
  if (getState().badges[id]) return;
  const b = BADGES[id];
  name = name || (b && b.name) || id;
  desc = desc || (b && b.desc) || "";
  getState().badges[id] = { name, desc, at: Date.now() };
  toast(`${ico("seal")} SIGIL PRESSED // <b>${esc(name)}</b>`, "warn");
  if (window.GhostAudio && getState().audio.sfx) window.GhostAudio.sfx("badge");
  save();
  if (getState().nav && getState().nav.view === "home") renderHome(); // the ledger shows sigils live
}

export function attemptMultiplier(a) { return ATTEMPT_MULT[Math.min(a, ATTEMPT_MULT.length - 1)]; }

// ------------------------------------------------------------ progress
export function sectionExercises(sec) {
  const out = [];
  for (const l of sec.lessons) for (const e of l.exercises) out.push(e);
  return out;
}
export function sectionSolvedFrac(sec) {
  if (isEvidenceTome(tome())) return sectionResolution(sec, getState()).fraction;
  const exs = sectionExercises(sec);
  if (!exs.length) return 1;
  return exs.filter((e) => getState().ex[e.id] && getState().ex[e.id].ok).length / exs.length;
}
export function freestyleUnlocked(sec) {
  if (getState().spellAll) return true;
  if (isEvidenceTome(tome())) {
    return workingUnlocked(sec, sections(), getState());
  }
  return sectionSolvedFrac(sec) >= 0.7;
}
export function fsBest(sid) { return (getState().fs[sid] && getState().fs[sid].best) || null; }
export function sectionPassed(sec) {
  const best = fsBest(sec.id);
  return isEvidenceTome(tome()) ? workingPassed(best)
    : !!(best && best.total >= 60 && best.passed !== false);
}
export function sectionUnlocked(i) { return !!getState().spellAll || i === 0 || sectionPassed(sections()[i - 1]); }
export function sectionProgress(sec) {
  const lessonWeight = isEvidenceTome(tome()) ? 0.8 : 0.7;
  return sectionSolvedFrac(sec) * lessonWeight + (sectionPassed(sec) ? 1 - lessonWeight : 0);
}
// a lesson is "completed" once every one of its exercises is cracked
// (lessons without exercises count once they've been opened/read)
export function lessonDone(l) {
  if (isEvidenceTome(tome())) return lessonResolved(l, getState());
  return l.exercises && l.exercises.length
    ? l.exercises.every((e) => getState().ex[e.id] && getState().ex[e.id].ok)
    : !!getState().read[l.id];
}

// ------------------------------------------------------------ HUD + sidebar
export function comboBonus() { return Math.min(COMBO_CAP, Math.max(0, (getState().stats.streak - 1) * COMBO_STEP)); }

export function updateHud() {
  $("#hud-credits").textContent = getState().credits;
  $("#hud-rank").textContent = rank().name;
  const passed = sections().filter(sectionPassed).length;
  $("#side-progress").textContent = passed + "/" + sections().length;
  const combo = $("#hud-combo");
  if (combo) {
    if (getState().stats.streak >= 2) {
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
  sections().forEach((sec, i) => {
    const unlocked = sectionUnlocked(i);
    const passed = sectionPassed(sec);
    const b = document.createElement("button");
    b.className = "op-item" + (unlocked ? "" : " locked") + (getState().nav.sec === sec.id && getState().nav.view !== "home" && getState().nav.view !== "shop" ? " active" : "");
    b.innerHTML = `
      <span class="op-num">${roman(i + 1)}</span>
      <span class="op-name">${esc(sec.short || sec.codename)}</span>
      <span class="op-state">${passed ? ico("check", "done") : unlocked ? "" : ico("lock", "lock")}</span>
      <span class="op-bar"><i style="width:${Math.round(sectionProgress(sec) * 100)}%"></i></span>`;
    b.onclick = () => {
      if (!unlocked) {
        const threshold = isEvidenceTome(tome())
          ? "80/B or better with every essential check green"
          : "grade D or better with every essential requirement and required verification green";
        toast(`THE PAGE IS SEALED // finish the previous chapter's Great Working first (${threshold}).`, "bad");
        return;
      }
      go("section", sec.id);
    };
    nav.appendChild(b);
  });
  updateHud();
}

export const secById = (id) => sections().find((section) => section.id === id);
