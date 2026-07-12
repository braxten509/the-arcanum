/* The small tools of the study: selectors, escaping, icons, toasts, modals, sfx. */
import { S } from "./state.js";

export const $ = (sel, root) => (root || document).querySelector(sel);
export const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
// minimal markdown renderer for LLM prose replies (headers, bold/italic, code, lists, links)
export const mdLite = (s) => {
  const inline = (t) => esc(t)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, "<em>$1</em>")
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  const lines = String(s || "").replace(/\r\n/g, "\n").split("\n");
  let html = "", inList = false, inCode = false;
  const closeList = () => { if (inList) { html += "</ul>"; inList = false; } };
  for (const line of lines) {
    if (/^```/.test(line)) { inCode = !inCode; html += inCode ? "<pre><code>" : "</code></pre>"; continue; }
    if (inCode) { html += esc(line) + "\n"; continue; }
    const h = line.match(/^(#{1,4})\s+(.*)/);
    if (h) { closeList(); html += `<h${h[1].length + 2}>${inline(h[2])}</h${h[1].length + 2}>`; continue; }
    const li = line.match(/^[-*]\s+(.*)/);
    if (li) { if (!inList) { html += "<ul>"; inList = true; } html += `<li>${inline(li[1])}</li>`; continue; }
    closeList();
    if (!line.trim()) continue;
    html += `<p>${inline(line)}</p>`;
  }
  closeList();
  return html;
};

export const ICONS = {
  check: '<path d="M2.5 8.5l3.5 3.5 7.5-8" fill="none" stroke="currentColor" stroke-width="1.8"/>',
  lock: '<rect x="3.5" y="7" width="9" height="6.5" rx="1" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" fill="none" stroke="currentColor" stroke-width="1.4"/>',
  play: '<path d="M4.5 3l8 5-8 5z" fill="currentColor"/>',
  save: '<path d="M3 3h8l2 2v8H3zM5 3v3h5V3M5 13V9h6v4" fill="none" stroke="currentColor" stroke-width="1.3"/>',
  zap: '<path d="M9 1.5L3.5 9H7l-1 5.5L11.5 7H8z" fill="none" stroke="currentColor" stroke-width="1.3"/>',
  star: '<path d="M8 2l1.8 3.6 4 .6-2.9 2.8.7 4L8 11.1 4.4 13l.7-4L2.2 6.2l4-.6z" fill="none" stroke="currentColor" stroke-width="1.3"/>',
  chip: '<rect x="4" y="4" width="8" height="8" rx="1" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M6 1.5v2.5M10 1.5v2.5M6 12v2.5M10 12v2.5M1.5 6H4M1.5 10H4M12 6h2.5M12 10h2.5" stroke="currentColor" stroke-width="1.2"/>',
  eye: '<path d="M1.5 8s2.5-4.5 6.5-4.5S14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z" fill="none" stroke="currentColor" stroke-width="1.3"/><circle cx="8" cy="8" r="2" fill="none" stroke="currentColor" stroke-width="1.3"/>',
  bulb: '<path d="M8 1.5a4.5 4.5 0 0 1 2.5 8.2c-.6.4-.9 1-.9 1.8h-3.2c0-.8-.3-1.4-.9-1.8A4.5 4.5 0 0 1 8 1.5z" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M6.5 13.5h3" stroke="currentColor" stroke-width="1.3"/>',
  shield: '<path d="M8 1.5l5.5 2v4c0 3.5-2.4 6-5.5 7-3.1-1-5.5-3.5-5.5-7v-4z" fill="none" stroke="currentColor" stroke-width="1.3"/>',
  swatch: '<rect x="2" y="2" width="12" height="12" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M2 9.5L9.5 2M6 14l8-8" stroke="currentColor" stroke-width="1.2"/>',
  music: '<path d="M5.5 12.5V4l7-1.5V11" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="4" cy="12.5" r="1.8" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="11" cy="11" r="1.8" fill="none" stroke="currentColor" stroke-width="1.4"/>',
  file: '<path d="M4 1.5h5.5l3 3V14.5H4z" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M9.5 1.5v3h3" fill="none" stroke="currentColor" stroke-width="1.3"/>',
  award: '<circle cx="8" cy="6" r="4" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M5.5 9.5L4.5 14.5 8 12.5l3.5 2-1-5" fill="none" stroke="currentColor" stroke-width="1.3"/>',
  upload: '<path d="M8 11V2.5M4.5 6L8 2.5 11.5 6M3 13.5h10" fill="none" stroke="currentColor" stroke-width="1.5"/>',
  pkg: '<path d="M8 1.5l5.5 3v7l-5.5 3-5.5-3v-7z" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M2.5 4.5L8 7.5l5.5-3M8 7.5v6.5" fill="none" stroke="currentColor" stroke-width="1.2"/>',
  book: '<path d="M2.5 2.5h4.5a1.5 1.5 0 0 1 1 .5 1.5 1.5 0 0 1 1-.5h4.5v10.5H9a1 1 0 0 0-1 .7 1 1 0 0 0-1-.7H2.5z" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M8 3v10" stroke="currentColor" stroke-width="1.2"/>',
  x: '<path d="M3.5 3.5l9 9M12.5 3.5l-9 9" stroke="currentColor" stroke-width="1.6"/>',
  arrow: '<path d="M2.5 8h11M9.5 4l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.5"/>',
  terminal: '<rect x="1.5" y="2.5" width="13" height="11" rx="1" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M4 6l2.5 2L4 10M8 10.5h4" fill="none" stroke="currentColor" stroke-width="1.3"/>',
  quill: '<path d="M13.5 2.5c-4 .5-7.5 2.5-9 6l-1.5 4.5 4.5-1.5c3.5-1.5 5.5-5 6-9z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M3.5 12.5L9 7" stroke="currentColor" stroke-width="1.2"/>',
  scroll: '<path d="M4.5 2.5h8a1.5 1.5 0 0 1 0 3h-1v7.5a1.5 1.5 0 0 1-3 0V4a1.5 1.5 0 0 0-1.5-1.5H4.5a1.5 1.5 0 0 0 0 3h1" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M10 13.5H3.5a1.5 1.5 0 0 1 0-3H8" fill="none" stroke="currentColor" stroke-width="1.3"/>',
  cloak: '<path d="M8 1.5c-3 1.5-4.5 4-4.5 7.5v5.5l2.5-1.5 2 1.5 2-1.5 2.5 1.5V9c0-3.5-1.5-6-4.5-7.5z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M5 0.9h6" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>',
  coin: '<circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M8 4.8l.9 1.8 2 .3-1.4 1.4.3 2L8 9.4l-1.8.9.3-2L5.1 6.9l2-.3z" fill="none" stroke="currentColor" stroke-width="1"/>',
  flame: '<path d="M8 1.5c.5 2.5 3.8 3.7 3.8 7a3.8 3.8 0 0 1-7.6 0c0-1.6.8-2.6 1.6-3.6.1 1 .5 1.7 1.2 2.1C7 5.2 7.2 3.2 8 1.5z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>',
  bell: '<path d="M8 1.5c2.6 0 4 1.8 4 4.2 0 2.8 1 3.7 1.8 4.4H2.2C3 9.4 4 8.5 4 5.7c0-2.4 1.4-4.2 4-4.2z" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M6.5 12.5a1.5 1.5 0 0 0 3 0" fill="none" stroke="currentColor" stroke-width="1.3"/>',
  orb: '<circle cx="8" cy="7" r="5" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M5 13.5h6M6 5a3 3 0 0 1 2-1" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>',
  wand: '<path d="M2.5 13.5L10 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><path d="M11.5 1.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z" fill="none" stroke="currentColor" stroke-width="1"/>',
  seal: '<circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="8" cy="8" r="2.2" fill="none" stroke="currentColor" stroke-width="1.2"/>',
  ink: '<path d="M5 2.5h6v3l1.5 2v6h-9v-6L5 5.5z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M5 5.5h6" stroke="currentColor" stroke-width="1.2"/>',
};
// coin faces a palette may pick (themes.toml / skin.toml: coin = "<name>").
// All sit inside the same r5.5 circle as the default star so they swap cleanly.
const COIN_ICONS = {
  star: ICONS.coin,
  rune: '<circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M6.8 4.8v6.4M6.8 5.6l2.7 1.6M6.8 8.2l2.7 1.6" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>',
  gem: '<path d="M5 2.5h6L13.5 6 8 13.5 2.5 6z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M2.5 6h11M5 2.5L8 6l3-3.5M8 6v7.5" fill="none" stroke="currentColor" stroke-width="1"/>',
  holed: '<circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" stroke-width="1.4"/><rect x="6.2" y="6.2" width="3.6" height="3.6" fill="none" stroke="currentColor" stroke-width="1.1"/>',
  serpent: '<circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M5.4 10.3c1.7 1 3.2.2 3.1-.9-.1-1-1.9-1-1.9-2.1 0-1 1.4-1.5 2.9-.7" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/><circle cx="10.1" cy="6.2" r=".7" fill="currentColor"/>',
  sun: '<circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="8" cy="8" r="1.8" fill="none" stroke="currentColor" stroke-width="1.1"/><path d="M8 4.4v-1M8 12.6v-1M4.4 8h-1M12.6 8h-1M5.5 5.5l-.7-.7M11.2 11.2l-.7-.7M10.5 5.5l.7-.7M4.8 11.2l.7-.7" stroke="currentColor" stroke-width="1" stroke-linecap="round"/>',
  bolt: '<circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M8.8 4.4L6.4 8.4h1.7L7 11.6l3-4.2H8.3l1.4-3z" fill="none" stroke="currentColor" stroke-width="1" stroke-linejoin="round"/>',
  eye: '<circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M4.8 8c.9-1.4 2-2.1 3.2-2.1S10.3 6.6 11.2 8c-.9 1.4-2 2.1-3.2 2.1S5.7 9.4 4.8 8z" fill="none" stroke="currentColor" stroke-width="1"/><circle cx="8" cy="8" r=".9" fill="currentColor"/>',
};
// the active palette (tome theme or global skin) may name its coin face
const coinGlyph = () => {
  const id = document.body.dataset.theme;
  const bank = [...((window.TOME && window.TOME.themes) || []), ...((window.TOME && window.TOME.skins) || [])];
  const t = bank.find((x) => x.id === id);
  return (t && COIN_ICONS[t.coin]) || ICONS.coin;
};
export const refreshCoins = () => document.querySelectorAll("svg.ico-coin").forEach((el) => { el.innerHTML = coinGlyph(); });
export const ico = (name, cls) => `<svg viewBox="0 0 16 16" class="ico ${name === "coin" ? "ico-coin " : ""}${cls || ""}">${(name === "coin" ? coinGlyph() : ICONS[name]) || ""}</svg>`;

export const sfx = (n) => { if (window.GhostAudio && S.audio.sfx) window.GhostAudio.sfx(n); };

export function toast(html, kind) {
  const t = document.createElement("div");
  t.className = "toast" + (kind ? " " + kind : "");
  t.innerHTML = html;
  $("#toasts").appendChild(t);
  setTimeout(() => { t.style.opacity = "0"; t.style.transition = "opacity .4s"; setTimeout(() => t.remove(), 400); }, 4200);
}

// penmanship: the text answers and the copying-drill box wear a written hand (both plain
// HTML fields, styled by body class). code editors (Monaco) stay monospace — cursive reads
// rough there, since Monaco assumes fixed-width metrics.
export function applyPen() {
  const p = S.pen || (S.pen = { trials: true, drill: true });
  document.body.classList.toggle("pen-trials", p.trials !== false);
  document.body.classList.toggle("pen-drill", p.drill !== false);
}

// play the dialog's exit animation, then clear and run `then` (which may open the next modal)
export function closeModal(then) {
  const root = $("#modal-root");
  const back = $(".modal-back", root);
  if (!back) { if (then) then(); return; }
  const box = $(".modal", back);
  back.classList.add("closing");
  if (box) box.classList.add("closing");
  let done = false;
  const finish = () => { if (done) return; done = true; root.innerHTML = ""; if (then) then(); };
  (box || back).addEventListener("animationend", finish, { once: true });
  setTimeout(finish, 320); // fallback if animations are disabled
}
// exit animation for a free-standing overlay (grade/result cards), then remove + run `then`
export function dropOverlay(el, then) {
  el.classList.add("closing");
  let done = false;
  const finish = () => { if (done) return; done = true; el.remove(); if (then) then(); };
  (el.firstElementChild || el).addEventListener("animationend", finish, { once: true });
  setTimeout(finish, 300);
}
// every range slider fills ink left of the thumb — paint its --fill (0-100%) from the value.
// Live drags are caught by a delegated listener (setup); this seeds the initial fill on render.
export const paintRange = (el) => el.style.setProperty("--fill", (el.value - el.min) / (el.max - el.min) * 100 + "%");

export function modal(html, actions, opts) {
  const root = $("#modal-root");
  root.innerHTML = `<div class="modal-back"><div class="modal">${html}<div class="modal-actions"></div></div></div>`;
  const act = $(".modal-actions", root);
  for (const [label, cls, fn] of actions) {
    const b = document.createElement("button");
    b.className = "btn " + cls; b.textContent = label;
    b.onclick = () => closeModal(fn);
    act.appendChild(b);
  }
  // sticky: a stray click outside the card must not discard what's typed inside it
  if (!(opts && opts.sticky)) $(".modal-back", root).addEventListener("click", (e) => { if (e.target.classList.contains("modal-back")) closeModal(); });
  root.querySelectorAll('input[type="range"]').forEach(paintRange);   // seed every slider's fill
}
