/* ARCANUM game engine — the wizard's study. Tomes are tomes; this is the desk they rest on.
   Boot, wiring, and the ambient life of the study. */
import "../audio/index.js";  // first: hangs GhostAudio on window before any module below reads it
import { BOOT_LINES, J, applyTomeConfig } from "./core/config.js";
import { fetchActiveBuilds, openBuildOverlay, showTomePicker } from "./forge/bindery.js";
import { showBinder } from "./forge/binder.js";
import { $, applyPen, esc, paintRange, refreshCoins, sfx, toast } from "./core/dom.js";
import { initiateAttack, intrusionEligible, startIntrusion } from "./game/duel.js";
import { backfillReview } from "./game/exercise.js";
import "./ui/menu.js";
import { askOracle, grabSelection, oracleContext, paintOracleBtn, showOracleLog } from "./bench/oracle.js";
import { renderSidebar, secById } from "./game/progress.js";
import { showStudySettings } from "./ui/settings.js";
import { burst, setLastCastAt } from "./game/sigil.js";
import { getState, loadState, save } from "./core/store.js";
import "./ui/tooltip.js";
import { renderHome, renderLesson, renderSection, renderShop, showCodeBook } from "./ui/views.js";
import { collectFiles, currentWorkbench, currentWorking, renderFreestyle, saveWorkspace, workbenchHasFiles } from "./bench/workbench.js";
import { bootstrapCatalog, tome } from "./core/bootstrap.js";
import { apiFetch } from "./core/api-client.js";
import { registerCommand } from "./core/commands.js";
import { go, registerRoute, registerSidebar } from "./core/router.js";
import { renderMasteryLab } from "./mastery/lab.js";

async function bootSequence() {
  const boot = $("#boot"), txt = $("#boot-text");
  boot.classList.remove("hidden");
  let skip = false;
  $("#boot-skip").onclick = () => { skip = true; };
  for (const line of BOOT_LINES) {
    if (skip) break;
    for (let i = 0; i <= line.length; i += 2) {
      if (skip) break;
      txt.textContent = txt.textContent.split("\n").slice(0, -1).concat(line.slice(0, i)).join("\n");
      await new Promise((r) => setTimeout(r, 8));
    }
    txt.textContent = txt.textContent.split("\n").slice(0, -1).concat(line).join("\n") + "\n";
    await new Promise((r) => setTimeout(r, skip ? 0 : 120));
  }
  await new Promise((r) => setTimeout(r, skip ? 0 : 600));
  boot.classList.add("hidden");
  getState().booted = true; save();
}

async function init() {
  await window.tomeReady;   // the active tome's data must be present before we render
  bootstrapCatalog();
  const visualConfig = applyTomeConfig();
  $("#side-ops-label").textContent = visualConfig.opsLabel;
  registerCommand("settings.open", showStudySettings);
  registerCommand("forge.open-overlay", openBuildOverlay);
  registerCommand("oracle.context", oracleContext);
  registerCommand("oracle.ask", askOracle);
  registerCommand("working.files", collectFiles);
  registerCommand("working.section", currentWorking);
  registerCommand("working.save", saveWorkspace);
  registerCommand("working.open", renderFreestyle);
  registerRoute("home", () => { renderHome(); $("#hud-op").textContent = "— your ledger"; });
  registerRoute("shop", () => { renderShop(); $("#hud-op").textContent = "— the peddler's wares"; });
  registerRoute("section", (section) => renderSection(section));
  registerRoute("lesson", (section, lesson) => renderLesson(section, lesson));
  registerRoute("freestyle", (section) => renderFreestyle(section));
  registerRoute("mastery-lab", (nodeId) => renderMasteryLab(nodeId));
  registerSidebar(renderSidebar);
  await loadState();
  backfillReview(); // enroll recall items solved before spaced review (or its time clock) existed
  document.body.dataset.theme = getState().theme || (tome().defaults && tome().defaults.theme) || "vellum";
  refreshCoins();   // the HUD purse is inked in index.html; re-ink it for the active palette
  window.GhostEditor.boot(() => {
    const out = {};
    for (const [p2, m] of currentWorkbench().models) out[p2] = m.getValue();
    return out;
  });

  // the tools of the study
  const bAsk = $("#obj-orb");
  let askSel = "";
  bAsk.onpointerdown = () => { askSel = grabSelection(); };
  bAsk.onclick = () => { const c = oracleContext(); askOracle(c.label, c.detail, askSel); };
  $("#obj-notes").onclick = showOracleLog;
  $("#obj-quill").onclick = showBinder;
  $("#obj-grimoire").onclick = showCodeBook;
  // These desk objects already voice themselves on pointer-down. Suppress the
  // generic navigation page-turn or it layers in only when the view changes.
  $("#obj-satchel").onclick = () => go("shop", null, null, false);
  $("#obj-letter").onclick = () => go("home", null, null, false);
  $("#obj-tomes").onclick = showTomePicker;
  $("#obj-wand").onclick = initiateAttack;
  $("#candle").onclick = showStudySettings;
  $("#hud-settings").onclick = () => { sfx("click"); showStudySettings(); };
  // brand the spine from the tome narrative
  const logoEl = $(".logo");
  if (logoEl && J().narrative && J().narrative.logo) logoEl.textContent = J().narrative.logo;
  paintOracleBtn();
  $("#hud-credits-btn").onclick = () => go("shop");
  $("#hud-rank-btn").onclick = () => go("home");

  // the tower window: lift your eyes from the ledger to the sky above the desk.
  // The wall's sky follows the study's clock through eight watches of the day.
  const wall = $("#wall");
  const skyPhase = () => {
    const h = new Date().getHours();
    // ponytail: fixed civil hours; a solar calculation could drift these with the seasons
    if (h < 4) return "midnight";
    if (h < 6) return "early-morning";
    if (h < 8) return "sunrise";
    if (h < 11) return "morning";
    if (h < 15) return "midday";
    if (h < 18) return "late-afternoon";
    if (h < 20) return "sunset";
    if (h < 23) return "early-night";
    return "midnight";
  };
  const paintSky = () => { wall.dataset.phase = skyPhase(); };
  paintSky();
  setInterval(paintSky, 60000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) paintSky(); });
  const lookVertical = (up) => {
    document.body.classList.toggle("looking-up", up);
    wall.inert = !up;
    (up ? $("#wall-down") : $("#hud-lookup")).focus({ preventScroll: true });
  };
  $("#hud-lookup").onclick = () => lookVertical(true);
  $("#wall-down").onclick = () => lookVertical(false);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && document.body.classList.contains("looking-up")) lookVertical(false);
  });

  // audio: init prefs, start the hearthfire on the first user gesture (autoplay policy)
  if (window.GhostAudio) {
    GhostAudio.init(getState().audio);
    const kick = () => { GhostAudio.userGesture(); document.removeEventListener("pointerdown", kick); document.removeEventListener("keydown", kick); };
    document.addEventListener("pointerdown", kick);
    document.addEventListener("keydown", kick);
    // warm the audio stream on the first mouse MOVEMENT, so it's open before the first click
    const warm = () => { GhostAudio.userGesture(); if (GhostAudio.running()) document.removeEventListener("pointermove", warm); };
    document.addEventListener("pointermove", warm);
    const bAmb = $("#hud-ambience"), bSfx = $("#hud-sfx");
    const paint = () => {
      bAmb.style.opacity = getState().audio.ambience ? "1" : ".35";
      bSfx.style.opacity = getState().audio.sfx ? "1" : ".35";
      bAmb.title = getState().audio.ambience ? "The hearthfire crackles (click to bank it)" : "The hearthfire is banked (click to stoke it)";
      bSfx.title = getState().audio.sfx ? "The study makes its little sounds" : "The study is silent";
    };
    bAmb.onclick = () => { getState().audio.ambience = !getState().audio.ambience; GhostAudio.setAmbience(getState().audio.ambience); paint(); save(); };
    bSfx.onclick = () => { getState().audio.sfx = !getState().audio.sfx; paint(); save(); if (getState().audio.sfx) GhostAudio.sfx("tick"); };
    paint();
  }

  applyPen(); // set the handwritten-ink body classes + code-editor font from saved prefs

  // candle embers: the flame sheds warm motes that drift up and die
  const flameEl = document.querySelector("#candle .c-wick-anchor");
  const liveFlame = document.querySelector("#candle .c-live-flame");
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");

  // Each flicker rolls a fresh lean, stretch, brightness, and duration so the
  // flame never falls into a visible loop.
  const rand = (min, max) => min + Math.random() * (max - min);
  let flamePose = { angle: 0, x: 0, y: 0, sx: 1, sy: 1, opacity: .96 };
  const flickerFlame = () => {
    if (!liveFlame || reduced.matches) return;
    const to = {
      angle: rand(-5.5, 5.5),
      x: rand(-1, 1),
      y: rand(-1.8, .5),
      sx: rand(.94, 1.06),
      sy: rand(.95, 1.14),
      opacity: rand(.93, 1),
    };
    const frame = (v) => ({
      transform: `translate(${v.x}px, ${v.y}px) rotate(${45 + v.angle}deg) scale(${v.sx}, ${v.sy})`,
      opacity: v.opacity,
    });
    const motion = liveFlame.animate([frame(flamePose), frame(to)], {
      duration: rand(480, 920),
      easing: "ease-in-out",
      fill: "forwards",
    });
    motion.onfinish = () => {
      flamePose = to;
      flickerFlame();
    };
  };
  flickerFlame();

  setInterval(() => {
    if (document.hidden || reduced.matches || !flameEl) return;
    if ($("#parchment").classList.contains("wide")) return; // the desk is swept during the Great Working
    const r = flameEl.getBoundingClientRect();
    if (!r.width) return;
    const em = document.createElement("div");
    em.className = "ember";
    const sz = 2 + Math.random() * 2.5;
    em.style.cssText = `left:${r.left + r.width / 2 + (Math.random() - 0.5) * 10}px;top:${r.top + 4}px;width:${sz}px;height:${sz}px`;
    document.body.appendChild(em);
    em.animate(
      [
        { transform: "translate(0,0)", opacity: 0.9 },
        { transform: `translate(${(Math.random() - 0.35) * 46}px, ${-(46 + Math.random() * 80)}px)`, opacity: 0 },
      ],
      { duration: 1900 + Math.random() * 1600, easing: "cubic-bezier(.2,.5,.4,1)", fill: "forwards" }
    ).onfinish = () => em.remove();
  }, 360);

  // click feedback by region: a multiple-choice pick, a fingertip on the parchment, or a
  // knock on the wooden desk. mousedown so it lands on press and catches right-clicks (button 2).
  document.addEventListener("mousedown", (e) => {
    if (e.button !== 0 && e.button !== 2) return;
    const t = e.target;
    if (!t.closest) return;
    let kind, material = true;
    const obj = t.closest("[data-sfx]");
    if (t.closest(".choice")) kind = "pick";              // marking a multiple-choice option
    else if (obj) { kind = obj.dataset.sfx; material = false; } // a desk object with its own voice
    else if (t.closest(".b-check, #b-run")) {               // CAST press: no feedback here — the verdict throws the motes and the voice.
      kind = "cast"; material = false;                      // remember where the button sat, in case the verdict removes it before bursting
      const r = t.closest(".b-check, #b-run").getBoundingClientRect();
      setLastCastAt({ x: r.left + r.width / 2, y: r.top + r.height / 2 });
    }
    else if (t.closest("#term, .forge-log, .forge-workbench")) kind = "stone"; // dark work surfaces: a mineral tap, chips fly
    else if (t.closest("#parchment")) kind = "click";     // anywhere on the parchment
    else if (t.closest(".modal, .grade-card")) kind = "click"; // a parchment card (bindery / forge / grade) — dust like the page, buttons included
    else if (t.closest("button")) { kind = "click"; material = false; } // HUD buttons OUTSIDE parchment: tick only (before the wood catch, so the header bar's buttons don't knock)
    // The bare HUD has pointer-events:none so overhanging props remain clickable.
    // Its empty wood therefore targets #shell rather than #hud; catch that only
    // after every specific object, control, modal, and parchment surface above.
    else if (t.closest("#table, #hud, #shell")) kind = "wood";
    else return;
    sfx(kind);
    if (material) burst(e.clientX, e.clientY, kind);
  });

  // keep every slider's ink fill in sync as it's dragged (one listener covers all sliders, anywhere)
  document.addEventListener("input", (e) => {
    if (e.target.matches && e.target.matches('input[type="range"]')) paintRange(e.target);
  });

  // Ctrl+S saves the workbench instead of opening the browser dialog
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "s") {
      e.preventDefault();
      if (getState().nav.view === "freestyle" && workbenchHasFiles()) saveWorkspace(true);
      else toast("No scroll is unrolled — there is nothing to blot.", "warn");
    }
  }, true);

  // typing SFX: one delegated listener covers drill boxes, inputs, and Monaco's inputarea.
  // capture phase — Monaco stopPropagation()s command keys (Backspace etc.) before they'd bubble here
  document.addEventListener("keydown", (e) => {
    if (!getState().audio.sfx || !window.GhostAudio) return;
    const t = e.target;
    if (!t.matches || !t.matches("textarea, input[type=text]")) return;
    if (e.key.length === 1 || ["Enter", "Backspace", "Tab", "Delete"].includes(e.key)) GhostAudio.keyclick(e.key);
  }, true);

  if (!getState().booted) await bootSequence();
  $("#shell").classList.remove("hidden");
  const resetBuildJob = sessionStorage.getItem("openResetBuildJob");
  const resetNotice = sessionStorage.getItem("phaseResetNotice");
  sessionStorage.removeItem("openResetBuildJob");
  sessionStorage.removeItem("phaseResetNotice");
  if (resetNotice) toast(esc(resetNotice), "bad");
  if (resetBuildJob) setTimeout(() => openBuildOverlay(resetBuildJob), 0);

  // hex scheduler: one rival's hex per ~10-15 min of visible, active study
  const intrusionDelay = () => (600 + Math.random() * 300) * 1000;
  let intrusionNextAt = Date.now() + intrusionDelay();
  setInterval(() => {
    if (document.hidden) { intrusionNextAt = Math.max(intrusionNextAt, Date.now() + 60000); return; }
    // A disabled scheduler continually moves its deadline forward. Re-enabling therefore
    // starts a fresh 10–15 minute window instead of releasing an attack that became overdue.
    if (getState().hexesEnabled === false) { intrusionNextAt = Date.now() + intrusionDelay(); return; }
    if (Date.now() < intrusionNextAt || !intrusionEligible()) return;
    intrusionNextAt = Date.now() + intrusionDelay();
    if (getState().inv.vpn > 0) {
      getState().inv.vpn--;
      sfx("tick");
      toast(`Your CLOAK OF UNSEEING turned a rival's hex aside (${getState().inv.vpn} charges left)`, "warn");
      save();
      return;
    }
    startIntrusion();
  }, 30000);

  const nav = getState().nav || { view: "home" };
  const validSec = nav.sec && secById(nav.sec);
  const validLab = nav.sec && (tome().masteryLabs || []).some(
    (entry) => (entry.masteryLab || {}).nodeId === nav.sec);
  if (nav.view === "lesson" && validSec && validSec.lessons.some((l) => l.id === nav.lesson)) go("lesson", nav.sec, nav.lesson);
  else if ((nav.view === "section" || nav.view === "freestyle") && validSec) go(nav.view, nav.sec);
  else if (nav.view === "mastery-lab" && validLab) go("mastery-lab", nav.sec);
  else if (nav.view === "shop") go("shop");
  else go("home");

  // health check
  try {
    const h = await (await apiFetch("/api/health")).json();
    const rtName = (tome().runtime && tome().runtime.name) || "custom";
    const rtOk = (h.runtimes || {})[rtName];
    if (!rtOk) toast(`THE FORGE IS COLD: ${rtName} was not found — CAST THE SPELL will fail.`, "warn");
    if (!h.claude) toast("THE TOWER IS DARK: claude CLI not found — the Magister cannot judge.", "warn");
  } catch { /* server just started; fine */ }

  // a tome may still be on the bindery's anvil from a previous visit — offer the way back
  fetchActiveBuilds().then(async (builds) => {
    const hint = localStorage.getItem("buildJob");
    if (builds.length) {
      const b = builds.find((x) => x.id === hint) || builds[0];
      toast(`The bindery is still forging <b>${esc(b.name || b.tome)}</b> — Phase ${b.phase}/9. The shelf of tomes holds its progress.`, "warn");
    } else if (hint) {
      try {
        const st = await (await apiFetch("/api/buildtome/status?id=" + encodeURIComponent(hint))).json();
        if (st.status === "done") toast(`The bindery finished <b>${esc(st.name || st.tome || "your tome")}</b> — it waits on the shelf.`, "warn");
        else if (st.status === "error") toast("The last working in the bindery failed — its partial pages remain in /tomes.", "bad");
      } catch { /* server unreachable; the shelf will tell them later */ }
      localStorage.removeItem("buildJob");
    }
  });
}

init();
