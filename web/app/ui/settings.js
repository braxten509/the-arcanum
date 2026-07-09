/* TRIM THE WICK — palette, penmanship, the hearthfire, and every AI hand in your service. */
import { $, applyPen, esc, modal, refreshCoins, toast } from "../core/dom.js";
import { enhanceSelect } from "./menu.js";
import { S, save } from "../core/state.js";

export function showStudySettings() {
  const k = S.audio.keys;
  const OLD_PROF = { clicky: "quill", thock: "scribe", soft: "chalk", beep: "chime" };
  k.profile = OLD_PROF[k.profile] || k.profile;
  const profiles = [
    ["quill", "SHARP QUILL", "a fine nib scratching quick strokes"],
    ["scribe", "SCRIBE'S REED", "a heavy pen, deep and deliberate"],
    ["chalk", "SLATE CHALK", "soft, dusty, unhurried"],
    ["chime", "ENCHANTED GLASS", "each letter rings faintly as it lands"],
    ["pen", "INKED PEN", "true strokes of a real pen, caught on the wind"],
  ];
  // order: Sepia Vellum pinned first, then this tome's own inks, then the other
  // global skins — globals carry a data-suffix the dropdown renders as an italic
  // tag: palette-only ones read as "(theme)", desk-restaging ones as "(skin)"
  const skins = (window.TOME && window.TOME.skins) || [];
  const skinOpt = (s) => [s.id, (s.name || s.id).toUpperCase(), s.css ? "(skin)" : "(theme)"];
  const themeOpts = [
    ...skins.filter((s) => s.id === "vellum").map(skinOpt),
    ...((window.TOME && window.TOME.themes) || [])
    .filter((t) => S.themes && S.themes[t.id]).map((t) => [t.id, (t.name || t.id).toUpperCase(), ""]),
    ...skins.filter((s) => s.id !== "vellum").map(skinOpt)];
  modal(`<h2>TRIM THE WICK</h2>
    <div class="faint" style="font-size:11px;letter-spacing:.14em;margin-top:12px">INK &amp; VELLUM</div>
    <div style="display:flex;align-items:center;gap:10px;margin-top:6px">
      <span class="dim" style="font-size:12px;width:78px">PALETTE</span>
      <select id="as-theme" class="cfg-select" style="flex:1">${themeOpts.map(([id, name, suffix]) =>
        `<option value="${id}"${suffix ? ` data-suffix="${suffix}"` : ""}${S.theme === id ? " selected" : ""}>${name}</option>`).join("")}</select>
    </div>
    <div class="faint" style="font-size:11px;letter-spacing:.14em;margin-top:16px">HANDWRITTEN INK</div>
    <div class="dim" style="font-size:11px;margin-top:4px">Where your own hand shows on the page, in place of the printer's type.</div>
    <label class="choice" style="margin-top:6px"><input type="checkbox" id="as-pen-trials" ${S.pen.trials !== false ? "checked" : ""}><span><b>TRIALS</b> <span class="dim">— the answers you write into a trial</span></span></label>
    <label class="choice" style="margin-top:6px"><input type="checkbox" id="as-pen-drill" ${S.pen.drill !== false ? "checked" : ""}><span><b>COPYING DRILL</b> <span class="dim">— the box you copy incantations into</span></span></label>
    <div class="faint" style="font-size:11px;letter-spacing:.14em;margin-top:12px">THE HEARTHFIRE</div>
    <div style="display:flex;align-items:center;gap:10px;margin-top:6px">
      <span class="dim" style="font-size:12px;width:78px">CRACKLE</span>
      <input type="range" id="as-mvol" class="vol-slider" min="0" max="100" value="${S.audio.volume}" style="flex:1">
      <span class="num dim" id="as-mvol-n" style="width:44px;text-align:right">${S.audio.volume}%</span>
    </div>
    <div style="display:flex;align-items:center;gap:10px;margin-top:6px">
      <span class="dim" style="font-size:12px;width:78px">WIND</span>
      <input type="range" id="as-wvol" class="vol-slider" min="0" max="100" value="${S.audio.wind}" style="flex:1">
      <span class="num dim" id="as-wvol-n" style="width:44px;text-align:right">${S.audio.wind}%</span>
    </div>
    <div class="faint" style="font-size:11px;letter-spacing:.14em;margin-top:16px">YOUR WRITING HAND</div>
    <div class="choices" style="margin-top:6px">${profiles.map(([id, name, d]) =>
      `<label class="choice${k.profile === id ? " sel" : ""}"><input type="radio" name="as-prof" value="${id}"${k.profile === id ? " checked" : ""}><span><b>${name}</b> <span class="dim">— ${d}</span></span></label>`).join("")}
    </div>
    <div style="display:flex;align-items:center;gap:10px;margin-top:8px">
      <span class="dim" style="font-size:12px;width:78px">VOLUME</span>
      <input type="range" id="as-kvol" class="vol-slider" min="0" max="200" value="${k.vol}" style="flex:1">
      <span class="num dim" id="as-kvol-n" style="width:44px;text-align:right">${k.vol}%</span>
    </div>
    <div class="faint" style="font-size:11px;letter-spacing:.14em;margin-top:16px">THE TOUCH OF THINGS</div>
    <div style="display:flex;align-items:center;gap:10px;margin-top:6px">
      <span class="dim" style="font-size:12px;width:78px">VOLUME</span>
      <input type="range" id="as-uvol" class="vol-slider" min="0" max="200" value="${S.audio.ui}" style="flex:1">
      <span class="num dim" id="as-uvol-n" style="width:44px;text-align:right">${S.audio.ui}%</span>
    </div>
    <div class="faint" style="font-size:11px;letter-spacing:.14em;margin-top:16px">THE MAGISTER'S TRUE FORM (GRADER)</div>
    <div style="display:flex;align-items:center;gap:10px;margin-top:6px">
      <span class="dim" style="font-size:12px;width:130px">PROVIDER</span>
      <select id="as-gkind" class="cfg-select" style="flex:1">
        <option value="claude-cli">CLAUDE CLI — your subscription login, no key</option>
        <option value="antigravity-cli">ANTIGRAVITY CLI — your Google login, no key</option>
        <option value="codex-cli">CODEX CLI — your ChatGPT login, no key</option>
        <option value="anthropic">ANTHROPIC API — needs API key</option>
        <option value="openai">OPENAI API — needs API key</option>
        <option value="ollama">LOCAL — Ollama on this rig</option>
        <option value="other">OTHER — custom CLI command</option>
      </select>
    </div>
    <div style="display:flex;align-items:center;gap:10px;margin-top:6px" id="as-gmodel-row">
      <span class="dim" style="font-size:12px;width:130px">MODEL</span>
      <select id="as-gmodel" class="cfg-select" style="flex:1"></select>
    </div>
    <div style="display:flex;align-items:center;gap:10px;margin-top:6px" id="as-gmodel-custom-row">
      <span class="dim" style="font-size:12px;width:130px">CUSTOM MODEL</span>
      <input type="text" id="as-gmodel-custom" class="cfg-select" style="flex:1" placeholder="exact model id" spellcheck="false">
    </div>
    <div style="display:flex;align-items:center;gap:10px;margin-top:6px" id="as-gkey-row">
      <span class="dim" style="font-size:12px;width:130px">API KEY</span>
      <input type="password" id="as-gkey" class="cfg-select" style="flex:1" placeholder="sk-..." spellcheck="false">
    </div>
    <div style="display:flex;align-items:center;gap:10px;margin-top:6px" id="as-gcmd-row">
      <span class="dim" style="font-size:12px;width:130px">COMMAND</span>
      <input type="text" id="as-gcmd" class="cfg-select" style="flex:1" placeholder="e.g. codex exec -" spellcheck="false">
    </div>
    <div class="dim" style="font-size:11px;margin-top:6px" id="as-gcmd-help">Any AI CLI that reads a prompt on stdin and prints the answer. The judgement prompt is piped to its stdin; the JSON verdict is read from stdout. Example: <code>codex exec -</code> or <code>ollama run llama3.1</code>.</div>
    <div class="faint" style="font-size:11px;letter-spacing:.14em;margin-top:16px">SPIRITS IN YOUR SERVICE (ORACLE &amp; STAND-IN)</div>
    <div style="display:flex;align-items:center;gap:10px;margin-top:6px">
      <span class="dim" style="font-size:12px;width:130px">THE ORACLE</span>
      <select id="as-oracle" class="cfg-select" style="flex:1"></select>
    </div>
    <div style="display:flex;align-items:center;gap:10px;margin-top:6px">
      <span class="dim" style="font-size:12px;width:130px">STAND-IN JUDGE</span>
      <select id="as-grader" class="cfg-select" style="flex:1"></select>
    </div>
    <div class="dim" style="font-size:11px;margin-top:6px">Judgement uses the Magister's true form; if the tower does not answer or its patience runs out, the local stand-in judges instead. Keys are kept only in your own ledger on this machine. A stronger local spirit: <code>ollama pull qwen3-coder:30b</code>.</div>`,
    [["THE LIGHT IS RIGHT", ""]]);
  const root = $("#modal-root");
  const themeSel = $("#as-theme", root);
  themeSel.onchange = () => {
    S.theme = themeSel.value;
    document.body.dataset.theme = S.theme;
    window.GhostEditor.setTheme(S.theme);
    refreshCoins();
    save();
  };
  const previewKeys = () => ["v", "e", "r", " ", "Enter"].forEach((key, i) => setTimeout(() => GhostAudio.keyclick(key), i * 90));
  const mvol = $("#as-mvol", root);
  mvol.oninput = () => {
    S.audio.volume = +mvol.value;
    $("#as-mvol-n", root).textContent = S.audio.volume + "%";
    GhostAudio.setVolume(S.audio.volume);
    save();
  };
  const wvol = $("#as-wvol", root);
  wvol.oninput = () => {
    S.audio.wind = +wvol.value;
    $("#as-wvol-n", root).textContent = S.audio.wind + "%";
    GhostAudio.setWind(S.audio.wind);
    save();
  };
  $("#as-pen-trials", root).onchange = (e) => { S.pen.trials = e.target.checked; applyPen(); save(); };
  $("#as-pen-drill", root).onchange = (e) => { S.pen.drill = e.target.checked; applyPen(); save(); };
  root.querySelectorAll("input[name=as-prof]").forEach((r) => (r.onchange = () => {
    k.profile = r.value;
    root.querySelectorAll(".choices .choice").forEach((c) => c.classList.toggle("sel", $("input", c).checked));
    GhostAudio.setKeys(k.profile, k.vol);
    previewKeys();
    save();
  }));
  const kvol = $("#as-kvol", root);
  kvol.oninput = () => {
    k.vol = +kvol.value;
    $("#as-kvol-n", root).textContent = k.vol + "%";
    GhostAudio.setKeys(k.profile, k.vol);
    GhostAudio.keyclick("a");
    save();
  };
  const uvol = $("#as-uvol", root);
  uvol.oninput = () => {
    S.audio.ui = +uvol.value;
    $("#as-uvol-n", root).textContent = S.audio.ui + "%";
    GhostAudio.setUiVol(S.audio.ui);
    GhostAudio.sfx("click");
    save();
  };
  // main grader: provider select + model combo / key / custom command
  const GRADER_DEFAULTS = { "claude-cli": "claude-opus-4-8", "antigravity-cli": "Gemini 3.1 Pro (High)", "codex-cli": "", anthropic: "claude-opus-4-8", openai: "gpt-5.1", ollama: S.ai.grader, other: "" };
  // per-provider model lists come from /api/models — ollama and agy enumerated live,
  // claude/codex from the server's curated lists (those CLIs can't enumerate).
  // "Custom…" always lets you type any id, so a newer model is one keystroke away.
  const CUSTOM = "__custom__";
  const TOME_AI = (window.TOME && window.TOME.defaults && window.TOME.defaults.ai) || {};
  let PROVIDERS = {};
  let ollamaModels = [];
  const gkind = $("#as-gkind", root), gmodelSel = $("#as-gmodel", root), gkey = $("#as-gkey", root);
  const gmodelRow = $("#as-gmodel-row", root), gkeyRow = $("#as-gkey-row", root);
  const gcustomRow = $("#as-gmodel-custom-row", root), gcustom = $("#as-gmodel-custom", root);
  const gcmd = $("#as-gcmd", root), gcmdRow = $("#as-gcmd-row", root), gcmdHelp = $("#as-gcmd-help", root);

  // rebuild the model dropdown for the current provider; select the saved model, else
  // fall to "Custom…" (revealing the text field) so any unlisted id still works
  function fillModelOptions() {
    const kind = S.ai.graderKind, saved = S.ai.graderModel || "";
    const opts = [];
    if (kind === "codex-cli") opts.push(["", "(default — your codex config)"]);
    for (const m of (kind === "ollama" ? ollamaModels : PROVIDERS[kind] || [])) opts.push([m, m]);
    const known = opts.some(([v]) => v === saved);
    opts.push([CUSTOM, "Custom…"]);
    const defModel = kind === (TOME_AI.graderKind || "claude-cli") ? TOME_AI.graderModel : null;
    gmodelSel.innerHTML = opts.map(([v, l]) =>
      `<option value="${esc(v)}"${v && v === defModel ? ' data-suffix="— tome default"' : ""}>${esc(l)}</option>`).join("");
    gmodelSel.value = known ? saved : CUSTOM;
    const isCustom = gmodelSel.value === CUSTOM;
    gcustomRow.style.display = isCustom ? "flex" : "none";
    if (isCustom) gcustom.value = saved;
  }
  const paintGrader = () => {
    const kind = S.ai.graderKind;
    gkind.value = kind;
    const isOther = kind === "other";
    const needsKey = kind === "anthropic" || kind === "openai";
    gmodelRow.style.display = isOther ? "none" : "flex";   // custom command needs no model field
    gkeyRow.style.display = needsKey ? "flex" : "none";
    gcmdRow.style.display = isOther ? "flex" : "none";
    gcmdHelp.style.display = isOther ? "block" : "none";
    if (needsKey) gkey.value = S.ai.keys[kind] || "";
    if (isOther) { gcustomRow.style.display = "none"; gcmd.value = S.ai.graderCommand || ""; }
    else fillModelOptions();
  };
  gkind.onchange = () => {
    S.ai.graderKind = gkind.value;
    S.ai.graderModel = GRADER_DEFAULTS[gkind.value] || "";
    paintGrader(); save();
  };
  gmodelSel.onchange = () => {
    if (gmodelSel.value === CUSTOM) { gcustomRow.style.display = "flex"; gcustom.focus(); S.ai.graderModel = gcustom.value.trim(); }
    else { gcustomRow.style.display = "none"; S.ai.graderModel = gmodelSel.value; }
    save();
  };
  gcustom.onchange = () => { S.ai.graderModel = gcustom.value.trim(); save(); };
  gkey.onchange = () => { S.ai.keys[S.ai.graderKind] = gkey.value.trim(); save(); };
  gcmd.onchange = () => { S.ai.graderCommand = gcmd.value.trim(); save(); };
  paintGrader();
  // The census-fed pickers (MODEL / ORACLE / STAND-IN) gray out and say Loading…
  // until /api/models answers — no snapping into shape mid-look.
  const censusSels = [gmodelSel, $("#as-oracle", root), $("#as-grader", root)];
  const setCensusLoading = (on, msg) => {
    for (const s of censusSels) {
      if (on) { s.innerHTML = `<option value="">${esc(msg || "Loading…")}</option>`; }
      s.disabled = !!on;
    }
    if (on) gcustomRow.style.display = "none"; // no custom field while the census loads; fillModelOptions restores it
  };
  setCensusLoading(true);
  root.querySelectorAll("select.cfg-select").forEach(enhanceSelect);

  // AI model pickers, filled from the server's model census: ollama and agy live,
  // claude/codex curated server-side. The ORACLE may dwell in any installed login
  // CLI or a local ollama spirit; the STAND-IN JUDGE stays local by design — it is
  // the fallback for when the tower is dark.
  fetch("/api/models").then((r) => r.json()).then((d) => {
    const list = d.models || [];
    const inst = d.installed || {};
    PROVIDERS = d.providers || {};
    ollamaModels = list.map((m) => m.name);
    setCensusLoading(false);   // the fills below replace the Loading… placeholders
    if (S.ai.graderKind !== "other") fillModelOptions();  // repaint with the live census
    // THE ORACLE — option values encode "kind:model" (kind ids never contain ':')
    const CLI_TAGS = { "claude-cli": "claude cli", "antigravity-cli": "antigravity cli", "codex-cli": "codex cli" };
    const osel = $("#as-oracle", root);
    const cur = `${S.ai.oracleKind || "ollama"}:${S.ai.oracle}`;
    const defO = `${TOME_AI.oracleKind || "ollama"}:${TOME_AI.oracle || ""}`;
    const oopts = list.map((m) => [`ollama:${m.name}`, m.name, `${m.gb} GB`]);
    for (const [kind, tag] of Object.entries(CLI_TAGS)) {
      if (!inst[kind]) continue; // an absent CLI cannot answer — don't offer its spirits
      for (const m of PROVIDERS[kind] || []) oopts.push([`${kind}:${m}`, m, tag]);
    }
    if (!oopts.some(([v]) => v === cur)) oopts.unshift([cur, S.ai.oracle, "(not installed)"]);
    osel.innerHTML = oopts.map(([v, l, tag]) =>
      `<option value="${esc(v)}" data-suffix="${esc(`— ${tag}${v === defO ? " · tome default" : ""}`)}"${v === cur ? " selected" : ""}>${esc(l)}</option>`).join("");
    osel.onchange = () => {
      const v = osel.value, i = v.indexOf(":");
      S.ai.oracleKind = v.slice(0, i);
      S.ai.oracle = v.slice(i + 1);
      save();
    };
    // THE STAND-IN JUDGE — local ollama models only
    const gsel = $("#as-grader", root);
    const names = list.map((m) => m.name);
    if (!names.includes(S.ai.grader)) names.unshift(S.ai.grader); // keep saved value even if uninstalled
    gsel.innerHTML = names.map((n) => {
      const m = list.find((x) => x.name === n);
      return `<option value="${esc(n)}"${n === S.ai.grader ? " selected" : ""}>${esc(n)}${m ? ` — ${m.gb} GB` : " (not installed)"}</option>`;
    }).join("");
    gsel.onchange = () => { S.ai.grader = gsel.value; save(); };
    if (!d.ok) toast("Could not reach Ollama for the model list.", "warn");
  }).catch(() => setCensusLoading(true, "model list unreachable"));
}
