/* Tome loader — runs before the game engine. Picks the active tome, fetches its
   assembled data (sections, attacks, economy, themes, music, narrative…), publishes it on
   window, injects the theme palettes, and exposes window.tomeReady for app.js to await. */
(function () {
  "use strict";

  function injectThemes(themes, skins) {
    const varsBlock = (t) => `body[data-theme="${t.id}"]{${Object.entries(t.vars || {}).map(([k, v]) => `--${k}:${v};`).join("")}}`;
    const blocks = [];
    for (const t of themes || []) blocks.push(varsBlock(t));
    // global skins: palette vars like a theme, plus optional structural CSS (already
    // scoped by the skin author to body[data-theme="<id>"]) injected verbatim
    for (const s of skins || []) { blocks.push(varsBlock(s)); if (s.css) blocks.push(s.css); }
    if (!blocks.length) return;
    const css = blocks.join("\n");
    let el = document.getElementById("tome-themes");
    if (!el) {
      el = document.createElement("style");
      el.id = "tome-themes";
      document.head.appendChild(el);
    }
    el.textContent = css;
  }

  function applyMeta(meta, narrative) {
    document.title = (narrative && narrative.title) || meta.name || "ARCANUM";
    const glyph = (meta.favicon || "✦").slice(0, 2);
    const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><rect width='16' height='16' fill='%23241609'/><text x='2' y='12' font-family='serif' font-size='11' fill='%23e3c059'>${glyph.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")}</text></svg>`;
    let link = document.querySelector("link[rel=icon]");
    if (!link) { link = document.createElement("link"); link.rel = "icon"; document.head.appendChild(link); }
    link.href = "data:image/svg+xml," + encodeURIComponent(svg);
  }

  window.tomeReady = (async function () {
    let list = [];
    try {
      list = (await (await fetch("/api/tomes")).json()).tomes || [];
    } catch (e) { /* offline / no tomes — resolve to whatever the server gives */ }
    window.TOMES_LIST = list;

    const params = new URLSearchParams(location.search);
    let active = params.get("tome") || localStorage.getItem("activeTome");
    if (!list.find((j) => j.id === active)) active = list.length ? list[0].id : "verisearch";
    localStorage.setItem("activeTome", active);
    window.__ACTIVE_TOME = active;

    const j = await (await fetch("/api/tome?tome=" + encodeURIComponent(active))).json();
    if (j && j.meta && j.meta.id) window.__ACTIVE_TOME = j.meta.id;
    window.TOME = j;
    window.SECTIONS = j.sections || [];
    window.ATTACK_TIERS = j.attacks || [];
    injectThemes(j.themes, j.skins);
    applyMeta(j.meta || {}, j.narrative || {});
    return j;
  })();

  // helper used by the engine for every per-tome API call
  window.tid = function () { return window.__ACTIVE_TOME || "verisearch"; };
})();
