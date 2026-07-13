/* Custom dropdowns, the context menu, and the practice circle by the table's edge.
   Animate: unfurl top→bottom in, retract bottom→top out. */
import { $, closeModal, modal, sfx, toast } from "../core/dom.js";
import { askOracle, oracleContext } from "../bench/oracle.js";
import { addCredits, go } from "../game/progress.js";
import { showStudySettings } from "./settings.js";
import { castSigil } from "../game/sigil.js";
import { prepareStateReset, resumeStateSaves, S, save } from "../core/state.js";
import { showCodeBook } from "./views.js";
import { parseSpellCode } from "./spell-codes.js";

let popOpen = null; // { el, owner, onClose }
export function closePop(instant) {
  if (!popOpen) return;
  const { el, onClose } = popOpen;
  popOpen = null;
  if (onClose) onClose();
  if (instant) return el.remove();
  if (!matchMedia("(prefers-reduced-motion: reduce)").matches) shedPixels(el);
  el.classList.add("closing");
  // item animationends bubble up first; only the container's final fade removes it
  el.addEventListener("animationend", (ev) => { if (ev.animationName === "menu-fade") el.remove(); });
  setTimeout(() => el.remove(), el.childElementCount * 22 + 400); // in case animations are disabled
}
// pixel disintegration: each row sheds a few themed squares as it dissolves (staggered like line-out)
function shedPixels(el) {
  const rows = [...el.children];
  const cs = getComputedStyle(document.body);
  const cols = ["--ac", "--tx", "--line-hi"].map((v) => cs.getPropertyValue(v).trim());
  rows.forEach((row, i) => {
    const r = row.getBoundingClientRect();
    if (!r.width) return;
    const delay = (rows.length - 1 - i) * 30; // bottom rows disintegrate first
    const count = Math.min(8, Math.max(3, Math.round(r.width / 34)));
    for (let k = 0; k < count; k++) {
      const px = document.createElement("div");
      px.className = "pop-particle";
      const sz = 2 + Math.round(Math.random() * 2);
      // opacity:0 until its animation begins — rows dissolve bottom-up, and a top-row
      // particle otherwise sits visible-but-frozen through its whole stagger delay
      px.style.cssText = `left:${r.left + Math.random() * r.width}px;top:${r.top + Math.random() * r.height}px;width:${sz}px;height:${sz}px;background:${cols[k % cols.length]};opacity:0`;
      document.body.appendChild(px);
      const dx = (Math.random() - 0.25) * 44; // biased right — the wipe travels left→right
      const dy = (Math.random() - 0.65) * 38; // biased up
      px.animate(
        [{ transform: "translate(0,0)", opacity: 1 }, { transform: `translate(${dx}px,${dy}px)`, opacity: 0 }],
        { duration: 420 + Math.random() * 260, delay, easing: "cubic-bezier(.2,.6,.3,1)", fill: "forwards" }
      ).onfinish = () => px.remove();
    }
  });
}

// Cast-a-spell codes are intentional debug/practice controls. Progress-shaped changes
// go through the real economy/save paths; random-hex control persists per tome.
function castSpellPrompt() {
  const hexesOn = S.hexesEnabled !== false;
  modal(`<h2>CAST A SPELL</h2><p class="dim">Speak the incantation.</p>
    <input type="text" id="spell-code" style="width:100%" placeholder="the words of the spell" spellcheck="false" autocomplete="off">
    <div class="spell-ledger" aria-label="Known spell codes">
      <div><code>GOLD-X</code><span>add X currency to your purse</span></div>
      <div><code>DISABLE-HEX</code><span>still random incoming hexes</span></div>
      <div><code>ENABLE-HEX</code><span>restore random incoming hexes</span></div>
      <div><code>RESET-PROGRESS</code><span>return this tome to a new beginning</span></div>
      <div><span class="spell-command"><code>UNLOCK-ALL</code> / <code>LOCK-ALL</code></span><span>lift or restore chapter seals</span></div>
      <p>RANDOM HEXES // <b>${hexesOn ? "ENABLED" : "DISABLED"}</b></p>
    </div>`,
    [["LEAVE IT", "quiet"], ["CAST", "", null]]);
  const cast = () => {
    const spell = parseSpellCode($("#spell-code").value);
    closeModal(() => {
      let repaint = false;
      if (spell.kind === "unlock-all") { S.spellAll = true; repaint = true; }
      else if (spell.kind === "lock-all") { delete S.spellAll; repaint = true; }
      else if (spell.kind === "gold") {
        if (!Number.isSafeInteger(S.credits + spell.amount) || !Number.isSafeInteger(S.earned + spell.amount)) {
          toast("THE PURSE REJECTS THE SPELL // that amount is too vast", "bad");
          return castSigil(null, false);
        }
        addCredits(spell.amount);
      }
      else if (spell.kind === "disable-hex") {
        S.hexesEnabled = false;
        save();
        toast("RANDOM HEXES STILLED // rival ambushes are disabled", "warn");
      } else if (spell.kind === "enable-hex") {
        S.hexesEnabled = true;
        save();
        toast("RANDOM HEXES RESTORED // the next rival may strike in 10–15 minutes");
      } else if (spell.kind === "reset-progress") {
        return showResetProgressConfirm();
      } else return castSigil(null, false); // unknown words — the spell fizzles
      castSigil(null, true);
      if (repaint) go(S.nav.view, S.nav.sec, S.nav.lesson); // seals lift/return in place
    });
  };
  document.querySelectorAll("#modal-root .modal-actions .btn")[1].onclick = cast;
  const f = $("#spell-code");
  f.onkeydown = (e) => { if (e.key === "Enter") cast(); };
  setTimeout(() => f.focus(), 50);
}

function showResetProgressConfirm() {
  modal(`<h2>RESET THIS TOME?</h2>
    <div class="reset-warning">
      <p><b>This cannot be undone.</b> The active tome will return to the state of a newly opened book.</p>
      <p>This erases lesson and chapter progress, gold and lifetime earnings, inventory, badges, grades, and files in the internal workbench.</p>
      <p>Reader-wide audio and AI settings remain. A project folder managed in your external editor is never deleted, though you will need to reconnect it.</p>
    </div>`,
    [["KEEP MY PROGRESS", "quiet"], ["RESET THIS TOME", "danger", null]], { sticky: true });
  const reset = document.querySelectorAll("#modal-root .modal-actions .btn")[1];
  reset.onclick = async () => {
    reset.disabled = true;
    reset.textContent = "CASTING…";
    await prepareStateReset();
    closeModal(async () => {
      try {
        await castSigil(null, true);
        const r = await fetch("/api/state/reset", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ confirm: "reset-progress" }),
        });
        const out = await r.json();
        if (!r.ok || !out.ok) throw new Error(out.error || "the reset was refused");
        location.reload();
      } catch (e) {
        resumeStateSaves();
        toast(`THE RESET WAS REFUSED // ${String(e.message || e)}`, "bad");
      }
    });
  };
}

// the practice circle: a chalk ring by the table's edge — click it to audition
// each sigil at the center of the study, no live cast required
const practice = document.createElement("button");
practice.type = "button";
practice.id = "practice-circle";
practice.title = "The practice circle — audition the sigils";
document.body.appendChild(practice);
practice.onclick = () => {
  const r = practice.getBoundingClientRect();
  popMenu([
    { label: "A TRUE CAST", suffix: "— the seal holds", on: () => castSigil(null, true) },
    { label: "A MISCAST", suffix: "— the spell fizzles", on: () => castSigil(null, false) },
    { label: "AN INCOMING HEX", suffix: "— a rival strikes", on: () => sfx("hex") },
    { label: "CAST A SPELL", suffix: "— speak a code", on: castSpellPrompt },
  ], r.left, r.top);
};

export function popMenu(items, x, y, minW) {
  closePop(true);
  const el = document.createElement("div");
  el.className = "pop-menu";
  if (minW) el.style.minWidth = minW + "px";
  for (const it of items) {
    if (it === "-") {
      el.appendChild(Object.assign(document.createElement("div"), { className: "pop-sep" }));
      continue;
    }
    const b = document.createElement("button");
    b.type = "button";
    b.className = "pop-item" + (it.sel ? " sel" : "");
    b.textContent = it.label;
    if (it.suffix) b.append(Object.assign(document.createElement("i"), { className: "dim", textContent: it.suffix }));
    b.disabled = !!it.disabled;
    b.onmousedown = (ev) => ev.preventDefault(); // keep the page's text selection intact
    b.onclick = () => { closePop(); if (it.on) it.on(); };
    el.appendChild(b);
  }
  el.onkeydown = (ev) => {
    if (ev.key !== "ArrowDown" && ev.key !== "ArrowUp") return;
    ev.preventDefault();
    const bs = [...el.querySelectorAll(".pop-item:not(:disabled)")];
    const i = bs.indexOf(document.activeElement);
    bs[(i + (ev.key === "ArrowDown" ? 1 : -1) + bs.length) % bs.length].focus();
  };
  // stagger indices: lines type in top→bottom (--i), dissolve out bottom→top (--o)
  const kids = [...el.children];
  kids.forEach((k, i) => { k.style.setProperty("--i", i); k.style.setProperty("--o", kids.length - 1 - i); });
  el.style.setProperty("--n", kids.length);
  document.body.appendChild(el);
  const r = el.getBoundingClientRect();
  el.style.left = Math.max(4, Math.min(x, innerWidth - r.width - 4)) + "px";
  el.style.top = Math.max(4, Math.min(y, innerHeight - r.height - 4)) + "px";
  popOpen = { el };
  const sel = el.querySelector(".pop-item.sel");
  if (sel) sel.focus();
  return popOpen;
}
// wraps a native <select> in a themed dropdown; the select stays the source of truth
export function enhanceSelect(sel) {
  const wrap = document.createElement("div");
  wrap.className = "dd";
  wrap.style.cssText = sel.style.cssText;
  sel.style.cssText = "";
  sel.parentNode.insertBefore(wrap, sel);
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "dd-btn";
  wrap.append(sel, btn);
  const paint = () => {
    const o = sel.options[sel.selectedIndex];
    btn.textContent = o ? o.text : "";
    if (o && o.dataset.suffix) btn.append(Object.assign(document.createElement("i"), { className: "dim", textContent: o.dataset.suffix }));
    btn.disabled = sel.disabled; // the observer repaints when sel.disabled toggles
  };
  paint();
  sel.addEventListener("change", paint);
  new MutationObserver(paint).observe(sel, { childList: true, subtree: true, attributes: true });
  btn.onclick = () => {
    if (popOpen && popOpen.owner === btn) return closePop();
    const r = btn.getBoundingClientRect();
    const p = popMenu([...sel.options].map((o, i) => ({
      label: o.text, suffix: o.dataset.suffix, sel: i === sel.selectedIndex,
      disabled: o.disabled,
      on: () => {
        if (o.disabled || sel.selectedIndex === i) return;
        sel.selectedIndex = i;
        sel.dispatchEvent(new Event("change"));
      },
    })), r.left, r.bottom + 4, r.width);
    p.owner = btn;
    wrap.classList.add("open");
    p.onClose = () => wrap.classList.remove("open");
  };
}
document.addEventListener("contextmenu", (ev) => {
  if (ev.shiftKey) return; // shift+right-click = browser's native menu
  const t = ev.target;
  if (!(t instanceof Element)) return;
  // ANY of our Monaco editors (workbench, trial pads, hex/duel overlays): contextmenu:false
  // kills monaco's own unthemed menu, so we serve ours here. (handled at document level,
  // not on the editor node — Firefox never fired a node-level capture listener.)
  const med = window.monaco && monaco.editor.getEditors().find((m) => { const n = m.getDomNode(); return n && n.contains(t); });
  if (med) {
    ev.preventDefault();
    const hasSel = !med.getSelection().isEmpty();
    const ro = med.getOption(monaco.editor.EditorOption.readOnly);
    popMenu([
      { label: "CUT", disabled: ro || !hasSel, on: () => { med.focus(); med.trigger("ctx", "editor.action.clipboardCutAction"); } },
      { label: "COPY", disabled: !hasSel, on: () => { med.focus(); med.trigger("ctx", "editor.action.clipboardCopyAction"); } },
      { label: "PASTE", disabled: ro, on: async () => {
        med.focus(); // anchor the browser's paste-confirm on the editor
        let txt = "";
        try { txt = await navigator.clipboard.readText(); } // Firefox pops a confirm here and steals focus
        catch { return toast("The browser guards its clipboard — press Ctrl+V to paste.", "warn"); }
        med.focus();
        if (txt) med.trigger("keyboard", "paste", { text: txt });
      } },
      "-",
      { label: "SELECT ALL", on: () => { med.focus(); med.trigger("ctx", "editor.action.selectAll"); } },
      { label: "COMMAND PALETTE", on: () => { med.focus(); med.trigger("ctx", "editor.action.quickCommand"); } },
      "-",
      { label: hasSel ? "ASK THE ORACLE ABOUT THIS" : "CONSULT THE ORACLE", on: () => {
        const c = oracleContext();
        askOracle(c.label, c.detail, hasSel ? med.getModel().getValueInRange(med.getSelection()).trim() : "");
      } },
    ], ev.clientX, ev.clientY);
    return;
  }
  if (t.closest(".monaco-editor, [contenteditable]")) return; // unowned monaco (tooltips, widgets) or rich-text: leave native
  const field = t.closest("textarea, input[type=text], input[type=password], input:not([type])");
  if (field) {
    ev.preventDefault();
    const ro = field.readOnly || field.disabled;
    const hasSel = field.selectionStart !== field.selectionEnd;
    // where pasting is barred (typing drills mark themselves data-nopaste),
    // PASTE is not offered at all — a dead native paste prompt teaches nothing
    const items = [
      { label: "CUT", disabled: ro || !hasSel, on: () => { field.focus(); document.execCommand("cut"); } },
      { label: "COPY", disabled: !hasSel, on: () => { field.focus(); document.execCommand("copy"); } },
    ];
    if (!field.dataset.nopaste) items.push(
      { label: "PASTE", disabled: ro, on: async () => {
        const s = field.selectionStart, e = field.selectionEnd; // capture before the read prompt
        field.focus(); // anchor the browser's paste-confirm on the field
        let txt = "";
        try { txt = await navigator.clipboard.readText(); }
        catch { return toast("The browser guards its clipboard — press Ctrl+V to paste.", "warn"); }
        if (!txt) return;
        field.focus(); // refocus AFTER read — Firefox's paste-confirm button steals focus
        field.setRangeText(txt, s, e, "end");
        field.dispatchEvent(new Event("input", { bubbles: true }));
      } });
    items.push(
      "-",
      { label: "SELECT ALL", disabled: !field.value, on: () => { field.focus(); field.select(); } });
    popMenu(items, ev.clientX, ev.clientY);
    return;
  }
  ev.preventDefault();
  const selTxt = String(getSelection() || "");
  const sel = selTxt.trim();
  popMenu([
    { label: "COPY", disabled: !selTxt, on: () => navigator.clipboard && navigator.clipboard.writeText(selTxt).catch(() => {}) },
    { label: "SELECT ALL", on: () => getSelection().selectAllChildren(t.closest("pre, .ex-body, #main") || document.body) },
    "-",
    { label: sel ? "ASK THE ORACLE ABOUT THIS" : "CONSULT THE ORACLE", on: () => { const c = oracleContext(); askOracle(c.label, c.detail, sel); } },
    { label: "OPEN THE GRIMOIRE", on: () => showCodeBook() },
    { label: "THE PEDDLER", on: () => go("shop") },
    "-",
    { label: "TRIM THE WICK (SETTINGS)", on: () => showStudySettings() },
  ], ev.clientX, ev.clientY);
});
document.addEventListener("mousedown", (ev) => {
  if (popOpen && !popOpen.el.contains(ev.target) && !(popOpen.owner && popOpen.owner.contains(ev.target))) closePop();
}, true);
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && popOpen) { ev.stopPropagation(); closePop(); }
}, true);
addEventListener("scroll", () => closePop(), true);
addEventListener("resize", () => closePop());
window.popMenu = popMenu; // editor.js serves monaco right-clicks through this
