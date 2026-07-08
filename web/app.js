/* ARCANUM game engine — the wizard's study. Tomes are tomes; this is the desk they rest on. */
(function () {
  "use strict";

  // every /api/* request is transparently scoped to the active tome
  const TID = () => (window.tid ? window.tid() : "verisearch");
  const _fetch = window.fetch.bind(window);
  window.fetch = (url, opts) => {
    if (typeof url === "string" && url.startsWith("/api/") && !/[?&]tome=/.test(url)) {
      url += (url.includes("?") ? "&" : "?") + "tome=" + encodeURIComponent(TID());
    }
    return _fetch(url, opts);
  };

  // ------------- tome config: neutral fallbacks only — every tome provides its own
  // (a tome that omits a table gets these minimal defaults, never another course's content)
  let RANKS = [[0, "APPRENTICE"]];
  let SHOP = [];
  // the five engine power-ups, generic flavor — a tome overrides these by id (see applyTomeConfig)
  const DEFAULT_CONSUMABLES = [
    { id: "firewall", kind: "consumable", name: "WARD OF ABSORPTION", cost: 450, charges: 5, ico: "shield", desc: "While it holds a charge, a wrong answer costs you no credits." },
    { id: "x2", kind: "consumable", name: "DOUBLING CATALYST", cost: 600, ico: "zap", desc: "Your next 20 correct answers pay double credits." },
    { id: "skip", kind: "consumable", name: "SCROLL OF REVELATION", cost: 700, ico: "scroll", desc: "Instantly solves one trial at full points." },
    { id: "vpn", kind: "consumable", name: "CLOAK OF UNSEEING", cost: 800, charges: 3, ico: "cloak", desc: "Deflects one incoming hex per charge." },
    { id: "xray", kind: "consumable", name: "SCRYING LENS", cost: 500, ico: "eye", desc: "Reveals the grader's private notes for one Great Working." },
  ];
  let HINT_COST = 75;
  let ORACLE_COST = 10;
  let ATTEMPT_MULT = [1, 0.6, 0.3], COMBO_STEP = 0.05, COMBO_CAP = 0.5, SRANK_MULT = 1.5;
  let ATK_STAKE_PER = 20, ATK_WIN_PER = 15, BLACKICE_N = 10, BLACKICE_CAP = 2;
  let BADGES = {};
  let EARNED_THEME = null;   // {id,name,desc} — an exclusive theme unlocked via attack wins

  // pull every tunable from the active Tome (falls back to the defaults above)
  function applyTomeConfig() {
    const j = window.TOME || {}, e = j.economy || {}, n = j.narrative || {}, p = j.progression || {};
    if (e.ranks) RANKS = e.ranks;
    // the five engine power-ups always exist (mechanics never break); a tome reflavors them by id,
    // and any it omits fall back to these generic defaults. oracle stays opt-in (needs a mentor model).
    const shop = Array.isArray(j.shop) ? j.shop.slice() : [];
    const have = new Set(shop.filter((s2) => s2.kind === "consumable").map((s2) => s2.id));
    const themeAt = shop.findIndex((s2) => s2.kind === "theme");          // keep defaults among the consumables, before themes
    DEFAULT_CONSUMABLES.forEach((d) => { if (!have.has(d.id)) shop.splice(themeAt < 0 ? shop.length : themeAt, 0, { ...d }); });
    shop.forEach((s2) => { if (s2.id === "x2") s2.charges = 20; });        // x2 charge count is engine-fixed at 20 (tome-proof) — a tome's own value is ignored
    SHOP = shop;
    if (e.hintCost != null) HINT_COST = e.hintCost;
    if (e.oracleCost != null) ORACLE_COST = e.oracleCost;
    if (e.attemptMultipliers) ATTEMPT_MULT = e.attemptMultipliers;
    if (e.comboStep != null) COMBO_STEP = e.comboStep;
    if (e.comboCap != null) COMBO_CAP = e.comboCap;
    if (e.sRankMultiplier != null) SRANK_MULT = e.sRankMultiplier;
    if (e.attackStakePerDiff != null) ATK_STAKE_PER = e.attackStakePerDiff;
    if (e.attackWinPerDiff != null) ATK_WIN_PER = e.attackWinPerDiff;
    if (n.gradingLines) GRADING_LINES = n.gradingLines;
    if (n.opsLabel) $("#side-ops-label").textContent = n.opsLabel;
    if (n.bootLines) BOOT_LINES = n.bootLines.map((l) => l.replace("{N}", String((window.SECTIONS || []).length)));
    if (p.intrusionTiers) INTRUSION_TIERS = p.intrusionTiers;
    if (p.attackTime != null) ATK_TIME = p.attackTime;
    if (p.attackStages) ATK_STAGE_AT = p.attackStages;
    if (p.blackIceThreshold != null) BLACKICE_N = p.blackIceThreshold;
    if (p.blackIcePerDiffCap != null) BLACKICE_CAP = p.blackIcePerDiffCap;
    BADGES = {};
    for (const b of (j.badges || [])) BADGES[b.id] = b;
    EARNED_THEME = p.earnedTheme || null;
  }
  const J = () => window.TOME || {};
  const persona = () => (J().narrative && J().narrative.graderPersona) || "THE MAGISTER";
  // the tower's name plate: names the grader ACTUALLY selected in settings, not the
  // tome's flavor text — "OPUS 4.8 // MAGISTER THORNE", "QWEN3:14B // MAGISTER THORNE"
  const GRADER_KIND_NAME = { "claude-cli": "CLAUDE", "antigravity-cli": "ANTIGRAVITY", "codex-cli": "CODEX", anthropic: "ANTHROPIC", openai: "OPENAI", ollama: "OLLAMA", other: "A CUSTOM SCRIBE" };
  function graderTitle() {
    const m = ((S && S.ai && S.ai.graderModel) || "").replace(/^claude-/, "").replace(/-(\d+)-(\d+)$/, " $1.$2").replace(/-/g, " ");
    const who = (m || GRADER_KIND_NAME[S && S.ai && S.ai.graderKind] || "THE TOWER").toUpperCase();
    return `${who} // ${persona()}`;
  }
  const coin = () => (J().narrative && J().narrative.currency) || "coin";      // "80 coin"
  const gp = () => (J().narrative && J().narrative.currencyShort) || "gp";     // "80gp"
  const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX"];
  const roman = (n) => ROMAN[n - 1] || String(n);
  const projName = () => (J().runtime && J().runtime.project) || "Verisearch";
  const entryFile = () => (J().runtime && J().runtime.entryFile) || "Program.cs";
  const newFileExt = () => (J().runtime && J().runtime.newFileExt) || ".cs";
  const langName = () => (J().runtime && J().runtime.language) || (J().runtime && J().runtime.name) || "code";
  const editorLang = () => (J().runtime && J().runtime.editorLang) || "plaintext";
  // the command shown in run/compile flavor text — from TOML, never guessed from the language
  const runLabel = () => {
    const r = J().runtime || {};
    return r.runLabel || (r.command ? [...r.command, r.entryFile || ""].join(" ").trim() : "dotnet run");
  };
  // external-editor mode: the student builds in their OWN IDE at a folder THEY choose,
  // and CAST/PRESENT operate on that folder. A course can REQUIRE external mode via
  // [runtime] externalWorkspace = true (a real toolchain, e.g. a Gradle mod), but the
  // folder is always the student's — the tome never hardwires a path. Any tome can also
  // be switched to external mode by the student via S.workspace (read after boot).
  const externalByAuthor = () => !!(J().runtime && J().runtime.externalWorkspace);
  const externalMode = () => externalByAuthor() || !!(S && S.workspace && S.workspace.enabled);
  const externalDir = () => (S && S.workspace && S.workspace.dir) || "";
  // the files a fresh project needs (entry file, plus a project marker like a .csproj) —
  // for the workbench file list and for seeding a student's own folder. `location` is set
  // only when the file must live in a specific subdirectory of the project.
  function requiredFiles() {
    const r = J().runtime || {};
    const entry = r.entryFile || "Program.cs";
    const out = [{ path: entry, desc: "your program’s entry point — the file that runs" }];
    const pf = (r.projectFile || entry).replace("{project}", r.project || "Project");
    if (pf !== entry) out.push({ path: pf, desc: "the project file — needed to build and run" });
    return out.map((f) => {
      const slash = f.path.lastIndexOf("/");
      const rel = f.path; // full relative path — what the server needs to fetch the file's content
      return slash > 0
        ? { rel, path: f.path.slice(slash + 1), location: f.path.slice(0, slash), desc: f.desc }
        : { rel, path: f.path, desc: f.desc };
    });
  }

  // ------------------------------------------------------------ state
  let S = null;
  let saveTimer = null, savePending = false;
  let loadDefaulted = false; // true when loadState fell back to a fresh default (server empty/unreachable)
  // real play, not just settings — mirrors the server's has_progress guard
  const hasProgress = (s) => !!(s && (s.earned || s.credits ||
    (s.ex && Object.keys(s.ex).length) || (s.read && Object.keys(s.read).length) ||
    (s.badges && Object.keys(s.badges).length) || (s.fs && Object.keys(s.fs).length)));

  const DEFAULT_STATE = () => {
    const jd = (window.TOME && window.TOME.defaults) || {};
    const dTheme = jd.theme || "vellum", dai = jd.ai || {};
    return {
      v: 1, booted: false, credits: 0, earned: 0,
      ex: {}, read: {}, fs: {},
      inv: { oracle: 0, skip: 0, firewall: 0, x2: 0, xray: 0, vpn: 0 },
      oracleLog: [],
      themes: { [dTheme]: true }, theme: dTheme,
      audio: { ambience: true, sfx: true, volume: 42, wind: 42, keys: { profile: "quill", vol: 100 }, ui: 100 },
      pen: { trials: true, drill: true }, // handwritten font on the surfaces you type into

      ai: { oracle: dai.oracle || "llama3.1:8b", oracleKind: dai.oracleKind || "ollama", grader: dai.grader || "qwen2.5:14b", graderKind: dai.graderKind || "claude-cli", graderModel: dai.graderModel || "claude-opus-4-8", graderCommand: dai.graderCommand || "", keys: { anthropic: "", openai: "" } },
      badges: {}, stats: { correct: 0, wrong: 0, runs: 0, subs: 0, streak: 0, bestStreak: 0, intrusionW: 0, intrusionL: 0, atkW: 0, atkL: 0, atkWins: {}, reviews: 0 },
      buffers: {}, nav: { view: "home", sec: null, lesson: null },
      workspace: { enabled: false, dir: "" }, // student opt-in: build in your own editor at this dir instead of the built-in workbench
    };
  };

  async function loadState() {
    try {
      const r = await fetch("/api/state");
      const data = await r.json();
      loadDefaulted = !Object.keys(data).length;
      S = loadDefaulted ? DEFAULT_STATE() : Object.assign(DEFAULT_STATE(), data);
      S.inv = Object.assign(DEFAULT_STATE().inv, S.inv);
      S.stats = Object.assign(DEFAULT_STATE().stats, S.stats);
      // saves from before the wind had its own slider: it used to ride the crackle volume
      if (S.audio && S.audio.wind === undefined && typeof S.audio.volume === "number") S.audio.wind = S.audio.volume;
      S.audio = Object.assign(DEFAULT_STATE().audio, S.audio);
      S.pen = Object.assign(DEFAULT_STATE().pen, S.pen);
      S.ai = Object.assign(DEFAULT_STATE().ai, S.ai);
      S.ai.keys = Object.assign(DEFAULT_STATE().ai.keys, S.ai.keys);
      S.workspace = Object.assign(DEFAULT_STATE().workspace, S.workspace);
      // saves from the old terminal era: carry the music toggle over to the hearthfire,
      // and re-home anyone equipped with a theme that no longer exists
      if (S.audio.ambience === undefined && S.audio.music !== undefined) S.audio.ambience = !!S.audio.music;
      const known = new Set([...(J().themes || []), ...(J().skins || [])].map((t) => t.id));
      if (!known.has(S.theme)) S.theme = DEFAULT_STATE().theme;
      S.themes[DEFAULT_STATE().theme] = true;
      // sigils pressed under an older telling keep their ids; re-read name/desc from today's registry
      const reg = Object.assign({}, BADGES);
      for (const sec of window.SECTIONS || []) if (sec.freestyle && sec.freestyle.badge) reg[sec.freestyle.badge.id] = sec.freestyle.badge;
      for (const [id, b] of Object.entries(S.badges || {})) if (reg[id]) { b.name = reg[id].name; b.desc = reg[id].desc; }
      // title sigils from the terminal era: same coin thresholds, new names — carry them across
      const OLD_RANK_FLOOR = { "rank-script-kiddie": 0, "rank-code-monkey": 400, "rank-shell-jockey": 1000, "rank-packet-rat": 2000, "rank-cipherpunk": 3500, "rank-netrunner": 5000, "rank-black-hat": 6800, "rank-root-daemon": 9000, "rank-gh0st": 12000 };
      for (const [id, floor] of Object.entries(OLD_RANK_FLOOR)) {
        if (!S.badges[id]) continue;
        const r = RANKS.find((x) => x[0] === floor);
        const old = S.badges[id];
        delete S.badges[id];
        if (!r) continue;
        const nid = "rank-" + r[1].toLowerCase().replace(/\s+/g, "-");
        S.badges[nid] = { name: "TITLE: " + r[1], desc: "Attained the title of " + r[1] + ".", at: old.at };
      }
    } catch { S = DEFAULT_STATE(); loadDefaulted = true; }
  }

  function save(now) {
    // if our load fell back to a default (server was empty or unreachable), don't
    // let an autosave write that blank state over a real save on disk — hold off
    // until there's actual progress to persist. a real save resumes the moment
    // the wizard earns anything. (server refuses this too, as a backstop.)
    if (loadDefaulted && !hasProgress(S)) return;
    savePending = true;
    setLed("saving");
    clearTimeout(saveTimer);
    const doSave = async () => {
      try {
        await fetch("/api/state", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(S) });
        savePending = false;
        setLed("saved");
      } catch { setLed("error"); setTimeout(() => save(), 3000); }
    };
    if (now) doSave(); else saveTimer = setTimeout(doSave, 700);
  }
  window.addEventListener("beforeunload", () => {
    // sendBeacon bypasses the fetch shim, so scope it to the active tome explicitly
    if (savePending) navigator.sendBeacon("/api/state?tome=" + encodeURIComponent(TID()), new Blob([JSON.stringify(S)], { type: "application/json" }));
  });
  setInterval(() => { if (savePending) save(true); }, 15000);

  function setLed(mode) {
    const dot = document.getElementById("led-dot"), txt = document.getElementById("led-text");
    dot.className = "led" + (mode === "saving" ? " saving" : mode === "error" ? " error" : "");
    txt.textContent = mode === "saving" ? "INKING…" : mode === "error" ? "RE-INK" : "INK DRY";
  }

  // ------------------------------------------------------------ helpers
  const $ = (sel, root) => (root || document).querySelector(sel);
  const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  const ICONS = {
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
  const refreshCoins = () => document.querySelectorAll("svg.ico-coin").forEach((el) => { el.innerHTML = coinGlyph(); });
  const ico = (name, cls) => `<svg viewBox="0 0 16 16" class="ico ${name === "coin" ? "ico-coin " : ""}${cls || ""}">${(name === "coin" ? coinGlyph() : ICONS[name]) || ""}</svg>`;

  function toast(html, kind) {
    const t = document.createElement("div");
    t.className = "toast" + (kind ? " " + kind : "");
    t.innerHTML = html;
    $("#toasts").appendChild(t);
    setTimeout(() => { t.style.opacity = "0"; t.style.transition = "opacity .4s"; setTimeout(() => t.remove(), 400); }, 4200);
  }

  // penmanship: the text answers and the copying-drill box wear a written hand (both plain
  // HTML fields, styled by body class). code editors (Monaco) stay monospace — cursive reads
  // rough there, since Monaco assumes fixed-width metrics.
  function applyPen() {
    const p = S.pen || (S.pen = { trials: true, drill: true });
    document.body.classList.toggle("pen-trials", p.trials !== false);
    document.body.classList.toggle("pen-drill", p.drill !== false);
  }

  // play the dialog's exit animation, then clear and run `then` (which may open the next modal)
  function closeModal(then) {
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
  function dropOverlay(el, then) {
    el.classList.add("closing");
    let done = false;
    const finish = () => { if (done) return; done = true; el.remove(); if (then) then(); };
    (el.firstElementChild || el).addEventListener("animationend", finish, { once: true });
    setTimeout(finish, 300);
  }
  // every range slider fills ink left of the thumb — paint its --fill (0-100%) from the value.
  // Live drags are caught by a delegated listener (setup); this seeds the initial fill on render.
  const paintRange = (el) => el.style.setProperty("--fill", (el.value - el.min) / (el.max - el.min) * 100 + "%");

  function modal(html, actions) {
    const root = $("#modal-root");
    root.innerHTML = `<div class="modal-back"><div class="modal">${html}<div class="modal-actions"></div></div></div>`;
    const act = $(".modal-actions", root);
    for (const [label, cls, fn] of actions) {
      const b = document.createElement("button");
      b.className = "btn " + cls; b.textContent = label;
      b.onclick = () => closeModal(fn);
      act.appendChild(b);
    }
    $(".modal-back", root).addEventListener("click", (e) => { if (e.target.classList.contains("modal-back")) closeModal(); });
    root.querySelectorAll('input[type="range"]').forEach(paintRange);   // seed every slider's fill
  }

  function showTomePicker() {
    const list = window.TOMES_LIST || [];
    const active = window.__ACTIVE_TOME;
    // drafts (unfinished builds) never sit beside real tomes — they live in the
    // bindery's "Unfinished workings" chooser (forgeEntry) until finished or discarded
    const rows = list.filter((j) => !j.draft).map((j) => `
      <button class="tome-row${j.id === active ? " active" : ""}" data-tome="${esc(j.id)}"${j.id === active ? " disabled" : ""}>
        <div class="jr-top"><span class="jr-name">${esc(j.name || j.id)}</span>
          <span class="jr-tag num">${esc(j.runtime || "")}${j.sectionCount != null ? " · " + j.sectionCount + " chapters" : ""}</span></div>
        <div class="jr-desc dim">${esc(j.description || "")}</div>
        <div class="jr-foot faint">${esc(j.author || "")}${j.id === active ? " · OPEN ON THE DESK" : ""}</div>
      </button>`).join("");
    modal(`<h2>THE SHELF OF TOMES</h2>
      <p class="dim" style="font-size:12px;margin:2px 0 12px">Taking down another tome clears the desk and opens it. Each tome keeps its own progress, purse, and title.</p>
      <div class="tome-list">
        <button class="tome-row forge" id="tome-forge">
          <div class="jr-top"><span class="jr-name">＋ FORGE A NEW TOME</span><span class="jr-tag num">the bindery</span></div>
          <div class="jr-desc dim">Name a course you wish existed; the bindery writes it, chapter by chapter, while you study.</div>
        </button>
        <div id="forge-active" style="display:contents"></div>
        ${rows || '<p class="dim">The shelf is bare. Place a tome folder in /tomes and look again.</p>'}</div>`,
      [["LEAVE THE SHELF", "quiet", null]]);
    $("#tome-forge").onclick = () => closeModal(forgeEntry);
    document.querySelectorAll("#modal-root .tome-row[data-tome]").forEach((b) => {
      b.onclick = () => {
        const id = b.dataset.tome;
        if (id === window.__ACTIVE_TOME) return;
        localStorage.setItem("activeTome", id);
        location.reload();
      };
    });
    // any tome still on the bindery's anvil gets a live row that reopens its progress
    fetchActiveBuilds().then((builds) => {
      const slot = $("#forge-active");
      if (!slot || !builds.length) return;
      slot.innerHTML = builds.map((b) => `
        <button class="tome-row forging" data-job="${esc(b.id)}">
          <div class="jr-top"><span class="jr-name">${esc(b.name || "Untitled")}</span><span class="jr-tag num">being forged</span></div>
          <div class="jr-desc">Phase ${b.phase} / 9 — ${esc(b.phaseTitle || "")}</div>
        </button>`).join("");
      slot.querySelectorAll("[data-job]").forEach((el) => {
        el.onclick = () => { const id = el.dataset.job; closeModal(() => openBuildOverlay(id)); };
      });
    });
  }

  // ------------------------------------------------------------ the bindery (forge a new tome)
  // POST /api/buildtome starts tools/build_tome.py on the server; the overlay below polls it.
  // Leaving the overlay never stops the build — the shelf and localStorage.buildJob reattach.
  const FORGE_PHASES = ["Gate", "Concept & arc", "Skeleton & voice", "Sections", "Minigames",
    "Economy pass", "Cosmetics", "Validate", "Student review"];
  let forgeOverlay = null; // the one live progress overlay (null when none)
  let forgePoll = 0;       // its status poller — always cleared before the overlay is dropped

  async function fetchActiveBuilds() {
    try { return (await (await fetch("/api/buildtome/active")).json()).jobs || []; }
    catch { return []; }
  }

  const FORGE_PHASE_NAMES = ["Gate", "Concept & arc", "Skeleton & voice", "Sections",
    "Minigames", "Economy", "Cosmetics", "Validate", "Student review"];

  // "Forge a new tome": if the bindery left any tome mid-forge, offer to resume (or discard)
  // one first; otherwise go straight to the bindery.
  function forgeEntry() {
    fetch("/api/buildtome/resumable").then((r) => r.json()).then((d) => {
      const workings = (d && d.workings) || [];
      workings.length ? showResumeChooser(workings) : showForgeModal();
    }).catch(() => showForgeModal());
  }

  function showResumeChooser(workings) {
    const row = (w) => `
      <div class="tome-row resume-row">
        <button class="resume-pick" data-id="${esc(w.id)}">
          <div class="jr-top"><span class="jr-name">${esc(w.name)}</span>
            <span class="jr-tag num">phase ${w.phase} · ${esc(FORGE_PHASE_NAMES[w.phase] || "")}</span></div>
          <div class="jr-desc dim">${esc(w.concept || "(no concept recorded)")}</div>
        </button>
        <button class="resume-trash" data-id="${esc(w.id)}" aria-label="Discard this working entirely" title="Discard this working entirely">🗑</button>
      </div>`;
    modal(`<h2>UNFINISHED WORKINGS</h2>
      <p class="dim" style="font-size:12px;margin:2px 0 12px">The bindery left these tomes mid-forge. Resume one to review its models and continue where it stopped, or discard it. Starting a new tome leaves them untouched.</p>
      <div class="tome-list">${workings.map(row).join("")}</div>`,
      [["START A NEW TOME", "", () => showForgeModal()], ["NOT TODAY", "quiet", null]]);
    const root = $("#modal-root");
    root.querySelectorAll(".resume-pick").forEach((b) => {
      b.onclick = () => {
        const w = workings.find((x) => x.id === b.dataset.id);
        closeModal(() => showForgeModal(w));
      };
    });
    root.querySelectorAll(".resume-trash").forEach((b) => {
      b.onclick = async (e) => {
        e.stopPropagation();
        b.disabled = true;
        try {
          const res = await fetch("/api/buildtome/discard", { method: "POST",
            headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: b.dataset.id }) });
          const d = await res.json();
          if (!d.ok) throw new Error(d.error || "discard failed");
          const left = workings.filter((x) => x.id !== b.dataset.id);
          closeModal(() => (left.length ? showResumeChooser(left) : showForgeModal()));
        } catch (err) {
          b.disabled = false;
          toast("Could not discard: " + esc(String(err.message || err)), "bad");
        }
      };
    });
  }

  // `resume` (optional) = a working from /api/buildtome/resumable: pre-fills the pickers with
  // the models that build used, locks the concept, and continues from where it stopped.
  function showForgeModal(resume) {
    // a dial's label + a hover/focus tooltip carrying its guidance, so the modal stays compact
    const fhead = (lbl, tip, up) => `<div class="forge-lbl"><label>${lbl}</label>` +
      `<button type="button" class="forge-help${up ? " forge-help--up" : ""}" aria-label="What this hand does">i<span class="forge-tip">${tip}</span></button></div>`;
    const providersTip = "Providers: Claude / Antigravity / Codex (their own logins), OpenCode CLI (OpenCode Go + FREE models), and Local (your ollama models, run through opencode). The EFFORT box appears only when the chosen model supports one — Claude/Codex on every model, OpenCode per model (only some Go/free models have a variant), Antigravity and Local none.";
    modal(`<h2>THE BINDERY<button type="button" class="forge-help" aria-label="How the model pickers work">i<span class="forge-tip">${providersTip}</span></button></h2>
      <p class="dim" style="font-size:12px;margin:2px 0 16px">Describe the course you wish existed. The bindery names it, chooses the tools it needs, then drafts, writes, and reviews the whole tome — it takes a good while, and you may leave and return as it works.</p>
      <div class="forge-field"><label for="fg-concept">COURSE CONCEPT</label>
        <textarea id="fg-concept" rows="4" placeholder="What should this tome teach? What does the student build by the end?"></textarea></div>
      <div class="forge-field"><label for="fg-prior">PRIOR KNOWLEDGE</label>
        <input type="text" id="fg-prior" placeholder="what the student can already do (languages / tools)"></div>
      <div class="forge-field"><label>TOOLING</label>
        <div class="forge-tooling">
          <label class="forge-check"><input type="checkbox" id="fg-tool-internal" checked> Internal <i class="dim">— in-browser only</i></label>
          <label class="forge-check"><input type="checkbox" id="fg-tool-external"> External <i class="dim">— real tools taught</i></label>
        </div>
        <div class="faint" style="font-size:11px;font-style:italic">both = internal &amp; external tools available; the bindery picks which workbenches run externally</div></div>
      <div class="forge-field">${fhead("BREADTH", "How much of the topic's surface makes the section list — <b>1</b> = the one tight path to the objective · <b>10</b> = the whole territory, side-paths included.")}
        <div class="forge-depth"><input type="range" id="fg-breadth" min="1" max="10" step="1" value="5">
          <span class="forge-depth-val num" id="fg-breadth-val">5</span></div></div>
      <div class="forge-field">${fhead("LESSON DEPTH", "How deep each lesson digs — <b>1</b> = just use it · <b>10</b> = internals, edge cases, why it works.")}
        <div class="forge-depth"><input type="range" id="fg-depth" min="1" max="10" step="1" value="5">
          <span class="forge-depth-val num" id="fg-depth-val">5</span></div></div>
      <div class="forge-field">${fhead("MASTERY", "Where the course ENDS — each tick writes concrete sample objectives into the build plan. <b>1</b> acquainted: read, follow &amp; tweak examples · <b>2</b> functional: everyday basics unaided · <b>3</b> capable: real problems, real choices (recursion, data-structure tradeoffs) · <b>4</b> advanced: idioms &amp; internals · <b>5</b> expert: the deep end.")}
        <div class="forge-depth"><input type="range" id="fg-mastery" min="1" max="5" step="1" value="3">
          <span class="forge-depth-val num" id="fg-mastery-val">3</span></div></div>
      <div class="forge-field fq-wait" id="fg-purse">${fhead("THE PURSE", "Five preconfigured mixes of models, cheapest competent hands on the left, the best mix (no wasted effort) on the right. Tick <b>Configure</b> to unlock the hands below and pick models yourself — the slider's picks stay as a starting point. Untick it and the slider takes over again, overwriting your picks. Tiers that use the claude/codex/antigravity logins leave a hand untouched if that CLI isn't installed.")}
        <div class="forge-quality">
          <label class="forge-check" style="margin:0;flex:0 0 auto"><input type="checkbox" id="fg-configure" disabled> Configure</label>
          <span class="fq-word">CHEAP</span>
          <input type="range" id="fg-quality" min="1" max="5" step="1" value="3" disabled>
          <span class="fq-word">QUALITY</span>
        </div></div>
      <div id="fg-hands">
      <div class="forge-field">${fhead("THE DRAFTER", "The cheap hand — lays the scaffold: the skeleton, the economy, the cosmetics &amp; the validation pass. The checker guards its work, so spend little here. <b>Effort:</b> low — mechanical scaffolding the validator already guards; high is wasted here.")}
        <div class="forge-ai-row">
          <select id="fg-drafter-prov" class="cfg-select" style="flex:0 0 auto;width:172px"><option value="">PICK A MODEL</option></select>
          <select id="fg-drafter-model" class="cfg-select" style="flex:1 1 auto;min-width:0" disabled><option value="">—</option></select>
          <select id="fg-drafter-eff" class="cfg-select" style="flex:0 0 auto;width:104px" disabled><option value="">—</option></select>
        </div></div>
      <div class="forge-field">${fhead("THE WRITER", "The costly hand — writes what actually teaches: the arc, the lessons &amp; the minigames. This is where the tome lives or dies, so spend here. <b>Effort:</b> medium is the sweet spot for authoring; go high only to make the concept/arc pass reason harder. Low risks shallow lessons and validator retries.")}
        <div class="forge-ai-row">
          <select id="fg-writer-prov" class="cfg-select" style="flex:0 0 auto;width:172px"><option value="">DRAFTER MODEL</option></select>
          <select id="fg-writer-model" class="cfg-select" style="flex:1 1 auto;min-width:0" disabled><option value="">—</option></select>
          <select id="fg-writer-eff" class="cfg-select" style="flex:0 0 auto;width:104px" disabled><option value="">—</option></select>
        </div></div>
      <div class="forge-field">${fhead('THE SECTIONS HAND <span style="font-weight:400;font-style:italic;letter-spacing:0">— phase 3 only</span>', "Sections is the biggest, most cache-heavy phase. <b>Off:</b> a curated shortlist vetted for quality + cheap cache reads. <b>Split by section:</b> each section gets its own worker so context never piles up — pick ANY model without the cache blow-up (a whole-tome reconcile pass still runs at the end for consistency). Overrides the writer for phase 3 only. <b>Effort:</b> medium — bulk authoring; high mostly buys slow think-time, low risks validator retries.")}
        <label class="forge-split-toggle"><input type="checkbox" id="fg-split"> split by section</label>
        <div class="forge-ai-row" id="fg-sec-curated">
          <select id="fg-sections" class="cfg-select" style="flex:1 1 auto;min-width:0"><option value="">WRITER MODEL</option></select>
        </div>
        <div class="forge-ai-row" id="fg-sec-any" style="display:none">
          <select id="fg-sec-prov" class="cfg-select" style="flex:0 0 auto;width:172px"><option value="">PICK A MODEL</option></select>
          <select id="fg-sec-model" class="cfg-select" style="flex:1 1 auto;min-width:0" disabled><option value="">—</option></select>
          <select id="fg-sec-eff" class="cfg-select" style="flex:0 0 auto;width:104px" disabled><option value="">—</option></select>
        </div></div>
      <div class="forge-field">${fhead("THE REVIEWER", "Independent eyes — reads the finished tome cover to cover as a first-time student and fills the gaps (the final review). A model DIFFERENT from the writer here catches what the writer cannot see in its own work. <b>Effort:</b> medium–high — spotting cross-section gaps is genuinely reasoning-work.", true)}
        <div class="forge-ai-row">
          <select id="fg-reviewer-prov" class="cfg-select" style="flex:0 0 auto;width:172px"><option value="">WRITER MODEL</option></select>
          <select id="fg-reviewer-model" class="cfg-select" style="flex:1 1 auto;min-width:0" disabled><option value="">—</option></select>
          <select id="fg-reviewer-eff" class="cfg-select" style="flex:0 0 auto;width:104px" disabled><option value="">—</option></select>
        </div></div>
      </div>`,
      [["NOT TODAY", "quiet", null]]);
    const root = $("#modal-root");
    $(".modal", root).classList.add("forge-modal");   // roomier dialog for the three-box rows
    if (resume) {
      const c = $("#fg-concept", root);
      c.value = resume.concept || ""; c.readOnly = true;   // concept is fixed once a working exists
      // "restart from" picker: defaults to the auto-detected phase, but lets the operator force
      // an earlier one (it re-runs from the pages on disk; at/before phase 3 it re-authors every
      // section — the way to redo a section that failed but got skipped on resume).
      const phaseOpts = FORGE_PHASE_NAMES.map((nm, i) => i >= 1
        ? `<option value="${i}"${i === resume.phase ? " selected" : ""}>phase ${i} — ${esc(nm)}</option>` : "").join("");
      $("h2", root).insertAdjacentHTML("afterend",
        `<p class="dim" style="font-size:12px;margin:2px 0 12px">Resuming <b>${esc(resume.name)}</b> from <select id="fg-fromphase" style="display:inline-flex;vertical-align:middle;min-width:190px">${phaseOpts}</select> — earlier is a forced redo. Review or change the models below, then continue.</p>`);
      enhanceSelect($("#fg-fromphase", root));   // themed dropdown, like every other select in the app
    }
    const depth = $("#fg-depth", root), depthVal = $("#fg-depth-val", root);
    depth.oninput = () => { depthVal.textContent = depth.value; };  // --fill is handled globally (paintRange + the live listener)
    const breadth = $("#fg-breadth", root), breadthVal = $("#fg-breadth-val", root);
    breadth.oninput = () => { breadthVal.textContent = breadth.value; };
    const mastery = $("#fg-mastery", root), masteryVal = $("#fg-mastery-val", root);
    mastery.oninput = () => { masteryVal.textContent = mastery.value; };
    if (resume) {
      // Phase 0 already ran: everything the gate consumed (concept → mastery) is fixed.
      // Show the working's real answers, grayed — only the model hands stay live.
      const g = resume.gate || {};
      const prior = $("#fg-prior", root);
      prior.value = g.prior_knowledge || "";
      $("#fg-tool-internal", root).checked = g.tooling === "internal" || g.tooling === "both";
      $("#fg-tool-external", root).checked = g.tooling === "external" || g.tooling === "both";
      const setDial = (el, valEl, v) => {
        if (v && !isNaN(+v)) { el.value = +v; valEl.textContent = el.value; paintRange(el); }
      };
      setDial(breadth, breadthVal, g.breadth);
      setDial(depth, depthVal, g.depth);
      setDial(mastery, masteryVal, g.mastery);
      for (const el of [$("#fg-concept", root), prior, $("#fg-tool-internal", root),
                        breadth, depth, mastery]) {
        el.closest(".forge-field").classList.add("forge-locked");
      }
    }
    // Each knob is a [PROVIDER][MODEL][EFFORT] cascade fed by /api/models `bindery`
    // ([{id,label,kind,models:[[id,label,tag],…],efforts,installed}]). Pick a provider, its
    // models fill the middle box; the effort box enables only for providers that take one
    // (claude, codex). enhanceSelect's MutationObserver repaints the styled control when we
    // rewrite <option>s on provider change, so re-enhancing isn't needed.
    const knob = (n) => ({ prov: $(`#fg-${n}-prov`, root), model: $(`#fg-${n}-model`, root), eff: $(`#fg-${n}-eff`, root) });
    const K = { drafter: knob("drafter"), writer: knob("writer"), reviewer: knob("reviewer"), sec: knob("sec") };
    let BINDERY = [];
    // Phase 3 (Sections) is the biggest, most cache-heavy phase, so its dial offers only a
    // curated shortlist — strong authoring models with cheap cache reads (per the GLM cost
    // post-mortem). All opencode-go, so one kind; filtered to those actually served. [id, label, note]
    const PHASE3_RECOMMENDED = [
      ["opencode-go/deepseek-v4-pro", "DeepSeek V4 Pro", "best value · cache ≈ free · pro tier"],
      ["opencode-go/qwen3.7-plus",    "Qwen3.7 Plus",    "strong · low cost"],
      ["opencode-go/minimax-m3",      "MiniMax M3",      "capable · low cost"],
      ["opencode-go/kimi-k2.6",       "Kimi K2.6",       "strong coder · mid cost"],
      ["opencode-go/glm-5.2",         "GLM 5.2",         "high quality · pricey cache"],
    ];
    const secSel = $("#fg-sections", root);
    // THE PURSE — CHEAP↔QUALITY slider. Tiers come from harness.toml [quality.*] via
    // /api/models; each is a per-phase runner map applied to the hand knobs. Configure
    // unticked → the slider owns the knobs (hands locked); ticked → knobs free, slider held.
    const qual = $("#fg-quality", root), conf = $("#fg-configure", root);
    let QUALITY = [];
    // Effort is PER-MODEL (row is [id,label,tag,efforts]): some OpenCode models expose a
    // reasoning variant, most don't; claude/codex expose their CLI's levels on every model.
    // So the effort box follows the selected MODEL, not the provider.
    const fillEffort = (k) => {
      const p = BINDERY.find((x) => x.id === k.prov.value);
      const m = p && (p.models || []).find((mm) => mm[0] === k.model.value);
      const levels = (m && m[3]) || [];
      k.eff.innerHTML = levels.length
        ? `<option value="">DEFAULT</option>` + levels.map((l) => `<option value="${esc(l)}">${esc(l.toUpperCase())}</option>`).join("")
        : `<option value="">—</option>`;
      k.eff.disabled = !levels.length;
    };
    const fillKnob = (k) => {
      const p = BINDERY.find((x) => x.id === k.prov.value);
      const models = (p && p.models) || [];
      k.model.innerHTML = models.length
        ? models.map(([v, l, tag]) => `<option value="${esc(v)}"${tag ? ` data-suffix="— ${esc(tag)}"` : ""}>${esc(l)}</option>`).join("")
        : `<option value="">${p ? "(no models found)" : "—"}</option>`;
      k.model.disabled = !models.length;
      fillEffort(k);   // effort follows the now-selected (first) model
    };
    for (const k of Object.values(K)) {
      k.prov.addEventListener("change", () => fillKnob(k));
      k.model.addEventListener("change", () => fillEffort(k));
    }
    // Remember the three picks across opens (localStorage). `restoring` suppresses the save
    // while we replay a saved pick, so the intermediate provider-change (which resets model)
    // doesn't clobber it.
    const SAVE_KEY = "binderyRunners";
    let restoring = false;
    const persist = () => {
      if (restoring) return;
      const snap = { sections: secSel.value, split: $("#fg-split", root).checked,
                     quality: qual.value, configure: conf.checked };
      for (const [n, k] of Object.entries(K)) snap[n] = { prov: k.prov.value, model: k.model.value, eff: k.eff.value };
      try { localStorage.setItem(SAVE_KEY, JSON.stringify(snap)); } catch (e) { /* private mode */ }
    };
    const has = (sel, v) => [...sel.options].some((o) => o.value === v);
    const restoreKnob = (k, s) => {
      if (!s || !s.prov || !has(k.prov, s.prov)) return;
      k.prov.value = s.prov;
      k.prov.dispatchEvent(new Event("change"));          // → fillKnob repopulates model+eff; buttons repaint
      if (s.model && has(k.model, s.model)) { k.model.value = s.model; k.model.dispatchEvent(new Event("change")); }
      if (s.eff && has(k.eff, s.eff)) { k.eff.value = s.eff; k.eff.dispatchEvent(new Event("change")); }
    };
    // Apply one tier pick {kind, model, effort} to a knob. A provider that isn't installed
    // (login CLI absent) leaves the knob untouched — tick Configure and fill it by hand.
    const applyPick = (k, p) => {
      if (!p || !has(k.prov, p.kind)) return;
      k.prov.value = p.kind; k.prov.dispatchEvent(new Event("change"));
      if (has(k.model, p.model)) { k.model.value = p.model; k.model.dispatchEvent(new Event("change")); }
      if (p.effort && has(k.eff, p.effort)) { k.eff.value = p.effort; k.eff.dispatchEvent(new Event("change")); }
    };
    const applyTier = () => {
      const t = QUALITY[qual.value - 1]; if (!t) return;
      const ph = t.phases || {};
      restoring = true;                                  // one persist at the end, not per knob
      applyPick(K.drafter, ph.default);
      applyPick(K.writer, ph["1"]);                      // "1" and "4" share the writer knob
      applyPick(K.reviewer, ph["8"]);
      $("#fg-split", root).checked = !!t.split; toggleSplit();
      if (t.split) applyPick(K.sec, ph["3"]);
      else if (ph["3"] && has(secSel, ph["3"].model)) { secSel.value = ph["3"].model; secSel.dispatchEvent(new Event("change")); }
      restoring = false; persist();
    };
    const syncPurse = () => {
      qual.disabled = conf.checked;
      $("#fg-hands", root).classList.toggle("fq-locked", !conf.checked && QUALITY.length > 0);
      paintRange(qual);   // programmatic value changes don't fire the delegated input repaint
      if (!conf.checked && QUALITY.length) applyTier();  // unticking overwrites with the tier
    };
    // While /api/models + the saved picks load, gray every box out and say "Loading…" — an
    // empty "—" box during the async gap reads as broken. Originals restored the instant the
    // fill runs (each select keeps its placeholder options in dataset.orig).
    const pickers = [secSel, ...Object.values(K).flatMap((k) => [k.prov, k.model, k.eff])];
    const setLoading = (on) => {
      for (const s of pickers) {
        if (on) {
          if (s.dataset.orig == null) s.dataset.orig = s.innerHTML;
          s.innerHTML = '<option value="">Loading…</option>';
          s.disabled = true;
        } else if (s.dataset.orig != null) {
          s.innerHTML = s.dataset.orig; delete s.dataset.orig; s.disabled = false;
        }
      }
    };
    setLoading(true);
    fetch("/api/models").then((r) => r.json()).then((d) => {
      setLoading(false);   // restore placeholders + re-enable; fillKnob re-disables model/eff as needed
      BINDERY = (d.bindery || []).filter((p) => p.installed !== false);
      const provOpts = BINDERY.map((p) => `<option value="${esc(p.id)}">${esc(p.label)}</option>`).join("");
      for (const k of Object.values(K)) { k.prov.insertAdjacentHTML("beforeend", provOpts); fillKnob(k); }
      // Sections dial: only the recommended models opencode actually serves right now.
      const oc = BINDERY.find((p) => p.kind === "opencode-cli");
      const served = new Set((oc ? oc.models : []).map((m) => m[0]));
      secSel.insertAdjacentHTML("beforeend", PHASE3_RECOMMENDED
        .filter(([id]) => served.has(id))
        .map(([id, label, note]) => `<option value="${esc(id)}">${esc(label)} — ${esc(note)}</option>`).join(""));
      QUALITY = d.quality || [];
      // the purse renders grayed from the first paint (no pop-in); tiers arriving ungray
      // it and snap the slider to the saved tier — no tiers at all hides it entirely
      if (QUALITY.length) { $("#fg-purse", root).classList.remove("fq-wait"); conf.disabled = false; }
      else $("#fg-purse", root).style.display = "none";
      restoring = true;
      // Resume pre-fills from the working's saved models; a fresh forge from the last-used set.
      let saved = resume ? (resume.bindery || {}) : {};
      if (!resume) { try { saved = JSON.parse(localStorage.getItem(SAVE_KEY) || "{}"); } catch (e) { /* ignore */ } }
      // No tiers served → the purse stays hidden and the hands are always free (as before).
      // A resume snapshot from before the purse existed carries no `configure` — treat it as
      // configured so the models the working actually used show, not the slider's picks.
      conf.checked = !QUALITY.length || !!saved.configure || (!!resume && saved.configure === undefined);
      if (saved.quality >= 1 && saved.quality <= QUALITY.length) qual.value = saved.quality;
      if (conf.checked) {   // hand-picked models restore; otherwise the slider re-derives them
        for (const [n, k] of Object.entries(K)) restoreKnob(k, saved[n]);
        if (saved.sections && [...secSel.options].some((o) => o.value === saved.sections)) {
          secSel.value = saved.sections; secSel.dispatchEvent(new Event("change"));
        }
        if (saved.split) { $("#fg-split", root).checked = true; toggleSplit(); }
      }
      restoring = false;
      syncPurse();
    }).catch(() => { setLoading(false); toast("Could not reach the bindery's model list — is the server up?", "bad"); });
    for (const k of Object.values(K)) [k.prov, k.model, k.eff].forEach(enhanceSelect);
    for (const k of Object.values(K)) [k.prov, k.model, k.eff].forEach((s) => s.addEventListener("change", persist));
    enhanceSelect(secSel); secSel.addEventListener("change", persist);
    // Split-by-section toggle: off → curated shortlist; on → full any-model cascade.
    const splitBox = $("#fg-split", root);
    const toggleSplit = () => {
      const on = splitBox.checked;
      $("#fg-sec-curated", root).style.display = on ? "none" : "";
      $("#fg-sec-any", root).style.display = on ? "" : "none";
    };
    splitBox.addEventListener("change", () => { toggleSplit(); persist(); });
    toggleSplit();
    qual.addEventListener("input", () => { if (!conf.checked) applyTier(); });
    conf.addEventListener("change", syncPurse);
    const readKnob = (k) => {
      const p = BINDERY.find((x) => x.id === k.prov.value);
      if (!p || !k.model.value) return null;
      const o = { kind: p.kind, model: k.model.value };
      if (k.eff.value) o.effort = k.eff.value;
      return o;
    };
    const begin = document.createElement("button");
    begin.className = "btn"; begin.textContent = resume ? "CONTINUE THE WORKING" : "BEGIN THE WORKING";
    begin.onclick = async () => {
      const concept = $("#fg-concept", root).value.trim();
      if (!resume && !concept) { toast("The bindery needs at least a <b>concept</b>.", "warn"); return; }
      const ti = $("#fg-tool-internal", root).checked, te = $("#fg-tool-external", root).checked;
      if (!resume && !ti && !te) { toast("Pick at least one <b>tooling</b> mode — internal, external, or both.", "warn"); return; }
      const tooling = ti && te ? "both" : te ? "external" : "internal";
      // The drafter drives the structural phases (2, 5, 6, 7) and there is no house default,
      // so it must be chosen or those phases would have no runner.
      if (!readKnob(K.drafter)) { toast("Pick a <b>drafter</b> model — it drives the structural phases (there is no house default).", "warn"); return; }
      begin.disabled = true; begin.textContent = "KINDLING THE FORGE...";
      try {
        const runners = {};
        // Three hands: DRAFTER = the cheap default for the structural phases the validator
        // backstops (2 skeleton, 5 economy, 6 cosmetics, 7 validate). WRITER = the authoring
        // phases that decide teaching quality (1 arc, 3 sections, 4 minigames). REVIEWER =
        // phase 8, the final student read-through — independent eyes on the finished tome.
        // Fallbacks: an empty WRITER drops to the drafter's model; an empty REVIEWER
        // defaults to the WRITER's model, so review still gets the costly hand (just not
        // independent) unless you pick a distinct reviewer.
        const WRITER_PHASES = ["1", "3", "4"];
        const drafter = readKnob(K.drafter), writer = readKnob(K.writer), reviewer = readKnob(K.reviewer);
        if (drafter) runners.default = drafter;
        if (writer) {
          for (const p of WRITER_PHASES) runners[p] = writer;
          runners["8"] = writer;  // reviewer defaults to the writer...
        }
        if (reviewer) runners["8"] = reviewer;  // ...unless a distinct reviewer is chosen
        const splitOn = $("#fg-split", root).checked;   // Sections dial overrides the writer for phase 3
        if (splitOn) {
          const sec = readKnob(K.sec);           // split mode: any model — context stays small per section
          if (sec) runners["3"] = sec;
        } else {
          const sections = $("#fg-sections", root).value;  // single session: curated shortlist only
          if (sections) runners["3"] = { kind: "opencode-cli", model: sections };
        }
        // snapshot the picks so a future resume of this tome can pre-fill them (same shape as
        // the localStorage restore path); the server stores it in the build's launch.json.
        const snap = { split: splitOn, sections: $("#fg-sections", root).value,
                       quality: qual.value, configure: conf.checked };
        for (const [n, k] of Object.entries(K)) snap[n] = { prov: k.prov.value, model: k.model.value, eff: k.eff.value };
        const fromPhase = resume ? parseInt(($("#fg-fromphase", root) || {}).value || resume.phase, 10) : 0;
        const payload = resume
          ? { id: resume.id, runners, sectionsSplit: splitOn, bindery: snap, fromPhase }
          : { concept, prior_knowledge: $("#fg-prior", root).value.trim(),
              depth: depth.value, breadth: breadth.value, mastery: mastery.value,
              tooling, runners, sectionsSplit: splitOn, bindery: snap };
        const r = await fetch(resume ? "/api/buildtome/resume" : "/api/buildtome", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await r.json();
        if (!data.ok) throw new Error(data.error || "the bindery did not answer");
        localStorage.setItem("buildJob", data.jobId);
        closeModal(() => openBuildOverlay(data.jobId));
      } catch (err) {
        begin.disabled = false; begin.textContent = resume ? "CONTINUE THE WORKING" : "BEGIN THE WORKING";
        toast("The bindery could not begin: " + esc(String(err.message || err)), "bad");
      }
    };
    $(".modal-actions", root).appendChild(begin);
  }

  // A build worker died and the harness (build_tome --ask-on-death) is blocked on a runner
  // choice. Show a [PROVIDER][MODEL][EFFORT] picker over the forge card; POST the pick to
  // /api/buildtome/runner and the working resumes from disk. One box per pause (idempotent).
  function showRunnerDeath(overlay, jobId, info) {
    const gate = !!info.gate;   // a phase exhausted its gate retries (vs. a runner that died)
    const detail = gate
      ? `phase <b>${info.phase}</b> failed its gates (${esc(info.reason || "retries used")})`
      : `runner <b>${esc(info.dead || "?")}</b> died on <b>phase ${info.phase}</b> (${esc(info.reason || "no exit")})`;
    let box = overlay.querySelector(".runner-death");
    if (box) { const d = box.querySelector(".rd-detail"); if (d) d.innerHTML = detail; return; }
    box = document.createElement("div");
    box.className = "runner-death";
    box.innerHTML = `<div class="grade-card rd-card">
      <div class="faint" style="font-size:11px;letter-spacing:.2em">THE BINDERY // ${gate ? "THE GATES HELD FAST" : "A HAND HAS FALTERED"}</div>
      <h2 style="margin:8px 0 4px;font-family:var(--arch)">${gate ? "This phase would not pass" : "A runner has died"}</h2>
      <p class="rd-detail dim" style="font-size:12.5px;margin:0 0 6px">${detail}</p>
      ${gate ? `<div class="forge-log num" style="height:auto;max-height:150px;margin:0 0 10px">${esc(info.report || "")}</div>` : ""}
      <p class="dim" style="font-size:12px;margin:0 0 14px">${gate
        ? "Give it more tries, and/or hand it to a different model — either way it resumes this phase from the pages already on disk."
        : "Choose the hand that takes up the quill — the working resumes from where it left off on disk."}</p>
      <div class="forge-ai-row">
        <select class="cfg-select rd-prov" style="flex:0 0 auto;width:172px"></select>
        <select class="cfg-select rd-model" style="flex:1 1 auto;min-width:0" disabled><option value="">—</option></select>
        <select class="cfg-select rd-eff" style="flex:0 0 auto;width:104px" disabled><option value="">—</option></select>
      </div>
      ${gate ? `<label class="dim" style="display:flex;align-items:center;gap:8px;margin-top:10px;font-size:12.5px">MORE RETRIES <input class="cfg-select rd-retries" type="number" min="1" max="20" value="3" style="width:76px"></label>` : ""}
      <div class="modal-actions" style="margin-top:16px">
        <button class="btn danger rd-abort">${gate ? "GIVE UP ON THIS TOME" : "ABANDON THE WORKING"}</button>
        <button class="btn rd-resume"${gate ? "" : " disabled"}>${gate ? "RETRY THIS PHASE" : "RESUME THE WORKING"}</button>
      </div></div>`;
    overlay.appendChild(box);
    const prov = box.querySelector(".rd-prov"), model = box.querySelector(".rd-model"),
          eff = box.querySelector(".rd-eff"), resume = box.querySelector(".rd-resume"),
          retriesEl = box.querySelector(".rd-retries");
    let BINDERY = [];
    const fillEff = () => {
      const p = BINDERY.find((x) => x.id === prov.value);
      const m = p && (p.models || []).find((mm) => mm[0] === model.value);
      const lv = (m && m[3]) || [];
      eff.innerHTML = lv.length
        ? `<option value="">DEFAULT</option>` + lv.map((l) => `<option value="${esc(l)}">${esc(l.toUpperCase())}</option>`).join("")
        : `<option value="">—</option>`;
      eff.disabled = !lv.length;
    };
    const fillModel = () => {
      const p = BINDERY.find((x) => x.id === prov.value);
      const ms = (p && p.models) || [];
      // gate pause: a leading blank keeps THIS phase's current model and only adds retries
      const keep = gate ? `<option value="">— keep this phase's model —</option>` : "";
      const opts = ms.length
        ? ms.map(([v, l, tag]) => `<option value="${esc(v)}"${tag ? ` data-suffix="— ${esc(tag)}"` : ""}>${esc(l)}</option>`).join("")
        : "";
      model.innerHTML = (keep + opts) || `<option value="">—</option>`;
      model.disabled = !ms.length && !gate;
      resume.disabled = gate ? false : !ms.length;
      if (gate) model.value = "";  // default to keep-current
      fillEff();
    };
    prov.addEventListener("change", fillModel);
    model.addEventListener("change", fillEff);
    fetch("/api/models").then((r) => r.json()).then((d) => {
      BINDERY = (d.bindery || []).filter((p) => p.installed !== false);
      prov.innerHTML = BINDERY.map((p) => `<option value="${esc(p.id)}">${esc(p.label)}</option>`).join("");
      fillModel();
      try {  // default the provider to the writer pick they used at launch, if it's still offered
        const w = (JSON.parse(localStorage.getItem("binderyRunners") || "{}")).writer;
        if (w && w.prov && [...prov.options].some((o) => o.value === w.prov)) {
          prov.value = w.prov; fillModel();
          if (!gate && w.model && [...model.options].some((o) => o.value === w.model)) { model.value = w.model; fillEff(); }
        }
      } catch (e) { /* ignore */ }
    }).catch(() => {});
    [prov, model, eff].forEach(enhanceSelect);
    resume.onclick = async () => {
      const p = BINDERY.find((x) => x.id === prov.value);
      const switching = !!(p && model.value);        // a model chosen (gate: blank = keep current)
      if (!gate && !switching) return;               // a death MUST pick a replacement runner
      const retries = gate ? Math.max(1, parseInt((retriesEl && retriesEl.value) || "1", 10) || 1) : 0;
      resume.disabled = true; resume.textContent = "TAKING UP THE QUILL...";
      try {
        await fetch("/api/buildtome/runner", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: jobId,
            kind: switching ? p.kind : "", model: switching ? model.value : "",
            effort: switching ? (eff.value || "") : "", retries }) });
      } catch { /* the next poll re-shows the box if the harness is still waiting */ }
      box.remove();  // next poll shows the resumed phase (awaitingRunner gone)
    };
    box.querySelector(".rd-abort").onclick = async () => {
      try { await fetch("/api/buildtome/cancel", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: jobId }) }); } catch { /* poll reports the state */ }
      box.remove();
    };
  }

  function openBuildOverlay(jobId) {
    if (forgeOverlay) {
      if (forgeOverlay.dataset.job === jobId) { forgeOverlay.classList.remove("hidden"); return; }
      clearInterval(forgePoll); forgeOverlay.remove(); forgeOverlay = null; // stale overlay for another job
    }
    const overlay = document.createElement("div");
    overlay.className = "grade-overlay";
    overlay.dataset.job = jobId;
    overlay.innerHTML = `<div class="grade-card">
      <div class="faint" style="font-size:11px;letter-spacing:.2em">THE BINDERY // A TOME IS BEING FORGED</div>
      <div style="font-family:var(--arch);font-size:20px;margin:10px 0 2px" id="fp-name"></div>
      <div id="fp-phase">reattaching to the working…</div>
      <div class="forge-phases">${FORGE_PHASES.map((t, i) => `
        <div class="forge-phase" data-ph="${i}"><span class="num">${i}</span><span>${esc(t)}</span><span class="fp-mark num"></span></div>`).join("")}</div>
      <div class="forge-log num" id="fp-log"></div>
      <div class="dim" style="margin-top:12px;font-size:12px;font-style:italic">a full tome takes a long while — leave, and the bindery works on; the shelf remembers it.</div>
      <div class="modal-actions">
        <button class="btn danger" id="fp-cancel">ABANDON THE WORKING</button>
        <button class="btn quiet" id="fp-leave">LEAVE THE BINDERY (work continues)</button>
      </div></div>`;
    document.body.appendChild(overlay);
    forgeOverlay = overlay;
    $("#fp-leave", overlay).onclick = () => overlay.classList.add("hidden");

    const cbtn = $("#fp-cancel", overlay);
    let armed = 0; // two-step: a stray click must not douse an hour of work
    cbtn.onclick = async () => {
      if (!armed) {
        cbtn.textContent = "CLICK AGAIN TO ABANDON";
        armed = setTimeout(() => { armed = 0; cbtn.textContent = "ABANDON THE WORKING"; }, 4000);
        return;
      }
      clearTimeout(armed);
      cbtn.disabled = true; cbtn.textContent = "DOUSING THE FORGE...";
      try {
        await fetch("/api/buildtome/cancel", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: jobId }) });
      } catch { /* the poll below will report whatever state remains */ }
      tick(); // observe the cancelled state now rather than on the next 3s beat
    };

    // Active-phase line: "Phase 3 / 9 — Sections … — 3/8 — gpt-5.4-mini @high — 12m 04s".
    // sections (X/Y) appears only in split phase 3; runner drops its CLI prefix; the clock
    // is time-in-phase from the server's phaseStartedAt, repainted every second below.
    let lastSt = null;
    const phaseLine = (st) => {
      let s = `Phase ${st.phase} / ${st.totalPhases || 9} — ${st.phaseTitle || "…"}`;
      if (st.sections) s += ` — ${st.sections}`;
      if (st.runner) s += ` — ${st.runner.replace(/^(?:claude|codex|antigravity|opencode)-cli\s+/, "")}`;
      if (st.phaseStartedAt) {
        const sec = Math.max(0, Math.round(Date.now() / 1000 - st.phaseStartedAt));
        s += ` — ${Math.floor(sec / 60)}m ${String(sec % 60).padStart(2, "0")}s`;
      }
      return s;
    };
    function paint(st) {
      lastSt = st;
      $("#fp-name", overlay).textContent = st.name || "Untitled";
      $("#fp-phase", overlay).textContent = phaseLine(st);
      overlay.querySelectorAll(".forge-phase").forEach((row) => {
        const i = +row.dataset.ph;
        row.classList.toggle("done", i < st.phase);
        row.classList.toggle("now", i === st.phase);
        $(".fp-mark", row).textContent = i < st.phase ? "✓" : i === st.phase ? "…" : "";
      });
      const log = $("#fp-log", overlay);
      if (log.textContent !== (st.logtail || "")) {
        log.textContent = st.logtail || "";
        log.scrollTop = log.scrollHeight;
      }
    }

    function finish(st) {
      overlay.classList.remove("hidden"); // surfaces the verdict even if they had left
      const card = $(".grade-card", overlay);
      const close = () => { forgeOverlay = null; dropOverlay(overlay); };
      if (st.status === "done") {
        sfx("grade");
        card.innerHTML = `<div class="grading-anim">
          <div class="faint" style="font-size:11px;letter-spacing:.2em">THE BINDERY // THE WORK IS DONE</div>
          <div style="font-family:var(--arch);font-size:22px;margin:14px 0 6px">${esc(st.name || st.tome || "")}</div>
          <p class="dim" style="font-size:13px;margin:0 0 6px">Nine phases, written and reviewed. The tome stands bound upon the shelf.</p>
          <div class="modal-actions" style="justify-content:center">
            <button class="btn quiet" id="fp-later">LEAVE IT ON THE SHELF</button>
            <button class="btn" id="fp-open">OPEN IT ON THE DESK</button>
          </div></div>`;
        $("#fp-open", card).onclick = () => { localStorage.setItem("activeTome", st.tome); location.reload(); };
        $("#fp-later", card).onclick = close;
      } else if (st.status === "cancelled") {
        card.innerHTML = `<div class="faint" style="font-size:11px;letter-spacing:.2em">THE BINDERY // THE WORKING WAS ABANDONED</div>
          <h2 style="margin:8px 0 6px">The forge is doused</h2>
          <p class="dim" style="font-size:12.5px">Whatever pages were already struck remain in <span class="num">tomes/${esc(st.tome || "")}</span> and <span class="num">.tome-build/</span> — inspect or delete them at your leisure.</p>
          <div class="modal-actions"><button class="btn quiet" id="fp-close">SO BE IT</button></div>`;
        $("#fp-close", card).onclick = close;
      } else { // "error", or "unknown" (the candle was relit and the record lost)
        const lost = st.status === "unknown";
        card.innerHTML = `<div class="faint" style="font-size:11px;letter-spacing:.2em">THE BINDERY // ${lost ? "THE RECORD IS LOST" : "THE WORKING FAILED"}</div>
          <h2 style="margin:8px 0 6px">${lost ? "The candle was relit" : esc(st.name || "The tome") + " would not bind"}</h2>
          ${lost ? '<p class="dim" style="font-size:12.5px">The desk was restarted and no longer holds this working’s record. If it finished, its tome waits in /tomes.</p>'
        : `<div class="forge-log num" style="height:auto;max-height:180px">${esc(st.error || st.logtail || "no record of the failure")}</div>
          <p class="dim" style="font-size:12.5px;margin-top:12px">Its partial pages remain in <span class="num">tomes/${esc(st.tome || "")}</span> and <span class="num">.tome-build/</span> — resume by hand with <span class="num">tools/build_tome.py --from-phase</span>, or delete them.</p>`}
          <div class="modal-actions"><button class="btn quiet" id="fp-close">SO BE IT</button></div>`;
        $("#fp-close", card).onclick = close;
      }
    }

    async function tick() {
      let st;
      try { st = await (await fetch("/api/buildtome/status?id=" + encodeURIComponent(jobId))).json(); } catch { return; }
      if (st.status === "running") {
        paint(st);
        if (st.awaitingRunner) {                          // a worker died; the harness is waiting on us
          overlay.classList.remove("hidden");             // surface it even if they'd left the bindery
          showRunnerDeath(overlay, jobId, st.awaitingRunner);
        } else { const b = overlay.querySelector(".runner-death"); if (b) b.remove(); }
        return;
      }
      { const b = overlay.querySelector(".runner-death"); if (b) b.remove(); }
      clearInterval(forgePoll);
      if (localStorage.getItem("buildJob") === jobId) localStorage.removeItem("buildJob");
      finish(st);
    }
    // one interval: poll the server every 3rd beat, tick the phase clock on the others
    let beat = 0;
    forgePoll = setInterval(() => {
      if (++beat % 3 === 0) tick();
      else if (lastSt) $("#fp-phase", overlay).textContent = phaseLine(lastSt);
    }, 1000);
    tick();
  }

  // ------------------------------------------------------------ economy
  function rank() {
    let r = RANKS[0], next = null;
    for (let i = 0; i < RANKS.length; i++) {
      if (S.earned >= RANKS[i][0]) r = RANKS[i];
      else { next = RANKS[i]; break; }
    }
    return { name: r[1], floor: r[0], next };
  }

  function addCredits(n, silentToast) {
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

  function spend(n) {
    if (S.credits < n) { toast(`Your purse is light. Need <b>${n}</b> ${coin()}, have ${S.credits}.`, "bad"); return false; }
    S.credits -= n; updateHud(); save(); return true;
  }

  function grantBadge(id, name, desc) {
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

  function attemptMultiplier(a) { return ATTEMPT_MULT[Math.min(a, ATTEMPT_MULT.length - 1)]; }

  // ------------------------------------------------------------ progress
  function sectionExercises(sec) {
    const out = [];
    for (const l of sec.lessons) for (const e of l.exercises) out.push(e);
    return out;
  }
  function sectionSolvedFrac(sec) {
    const exs = sectionExercises(sec);
    if (!exs.length) return 1;
    return exs.filter((e) => S.ex[e.id] && S.ex[e.id].ok).length / exs.length;
  }
  function freestyleUnlocked(sec) { return sectionSolvedFrac(sec) >= 0.7; }
  function fsBest(sid) { return (S.fs[sid] && S.fs[sid].best) || null; }
  function sectionPassed(sec) { const b = fsBest(sec.id); return b && b.total >= 60; }
  function sectionUnlocked(i) { return i === 0 || sectionPassed(window.SECTIONS[i - 1]); }
  function sectionProgress(sec) {
    return sectionSolvedFrac(sec) * 0.7 + (sectionPassed(sec) ? 0.3 : 0);
  }

  // ------------------------------------------------------------ HUD + sidebar
  function comboBonus() { return Math.min(COMBO_CAP, Math.max(0, (S.stats.streak - 1) * COMBO_STEP)); }

  function updateHud() {
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
      $("#obj-wand-d").textContent = d < 1 ? "" : `CIRCLE ${roman(d)}`;
      bAtk.title = d < 1 ? "Seal your first chapter before challenging a rival" : `Duel a rival of the ${roman(d)} circle`;
    }
  }

  function renderSidebar() {
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
  function go(view, sec, lesson) {
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
    if (moved) sfx("page");
  }

  const secById = (id) => window.SECTIONS.find((s2) => s2.id === id);

  // ------------------------------------------------------------ HOME
  function renderHome() {
    const v = $("#view-home");
    v.classList.remove("hidden");
    const r = rank();
    const nextSec = window.SECTIONS.find((sec, i) => sectionUnlocked(i) && !sectionPassed(sec));
    const badges = Object.entries(S.badges).sort((a, b2) => a[1].at - b2[1].at);
    const pct = r.next ? Math.min(100, Math.round(((S.earned - r.floor) / (r.next[0] - r.floor)) * 100)) : 100;

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
                ? `<span class="dim" style="font-size:12.5px">next: ${r.next[1]} at <span class="num">${r.next[0]}</span> lifetime ${coin()} (<span class="num">${S.earned}</span> earned)</span><div class="meter"><i style="width:${pct}%"></i></div>`
                : `<span class="dim">The highest title. Even the candle bows a little.</span>`}
            </div>
          </div>
          <div class="stat-row"><span>TITLES EARNED</span><b class="num">${RANKS.filter((x) => S.earned >= x[0]).length} / ${RANKS.length}</b></div>
          <div class="stat-row"><span>${coin().toUpperCase()} IN YOUR PURSE</span><b class="num">${S.credits}</b></div>
          <div class="stat-row"><span>LIFETIME EARNED</span><b class="num">${S.earned}</b></div>
          <div class="stat-row"><span>TRIALS PASSED</span><b class="num">${Object.values(S.ex).filter((e) => e.ok).length}</b></div>
          <div class="stat-row"><span>MISCASTS SURVIVED</span><b class="num">${S.stats.wrong}</b></div>
          <div class="stat-row"><span>SPELLS CAST</span><b class="num">${S.stats.runs}</b></div>
          <div class="stat-row"><span>WORKINGS PRESENTED</span><b class="num">${S.stats.subs}</b></div>
          <div class="stat-row"><span>CHAPTERS SEALED</span><b class="num">${window.SECTIONS.filter(sectionPassed).length} / ${window.SECTIONS.length}</b></div>
          <div class="stat-row"><span>HEXES BROKEN</span><b class="num">${S.stats.intrusionW || 0} / ${(S.stats.intrusionW || 0) + (S.stats.intrusionL || 0)}</b></div>
          <div class="stat-row"><span>DUELS WON</span><b class="num">${S.stats.atkW || 0} / ${(S.stats.atkW || 0) + (S.stats.atkL || 0)}</b></div>
          <div class="stat-row"><span>REVIEWS RE-FORGED</span><b class="num">${S.stats.reviews || 0}</b></div>
          ${EARNED_THEME ? `<div class="stat-row"><span>${esc(EARNED_THEME.name)} PROGRESS</span><b class="num">${S.themes[EARNED_THEME.id] ? "WON" : atkQualifying() + " / " + BLACKICE_N}</b></div>` : ""}
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
          ${SHOP.filter((s2) => s2.kind === "consumable").map((item) => `<div class="stat-row"><span>${ico(item.ico)} ${item.name}</span><b class="num">${S.inv[item.id] || 0}</b></div>`).join("")}
          <h2>SIGILS <span class="dim num" style="font-weight:400">(${badges.length})</span></h2>
          <div class="badge-grid cascade">
            ${badges.length ? badges.map(([id, b2], i) => `
              <div class="badge earned" style="--i:${i}">${ico("seal", "b-ico")}
                <span class="b-name">${esc(b2.name)}</span>
                <span class="b-desc">${esc(b2.desc || "")}</span>
              </div>`).join("") : `<div class="dim" style="grid-column:1/-1">No sigils pressed yet. Complete a chapter's Great Working to earn your first.</div>`}
          </div>
        </div>
      </div>`;
    const cont = $("#btn-continue");
    if (cont) cont.onclick = () => go("section", nextSec.id);
  }

  // ------------------------------------------------------------ SECTION
  function renderSection(sid) {
    const sec = secById(sid);
    const v = $("#view-section");
    v.classList.remove("hidden");
    $("#hud-op").textContent = "— " + sec.codename.toLowerCase();
    const frac = sectionSolvedFrac(sec);
    const fsOpen = freestyleUnlocked(sec);
    const best = fsBest(sid);

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
          const total = l.exercises.length;
          const done = l.exercises.filter((e) => S.ex[e.id] && S.ex[e.id].ok).length;
          const pts = l.exercises.reduce((a, e) => a + e.points, 0);
          return `<button class="lesson-row" data-lesson="${l.id}" style="--i:${i}">
            <span class="l-num">${roman(i + 1)}</span>
            <span>${esc(l.title)}</span>
            <span class="l-pts num">${done}/${total} · ${pts}${gp()}</span>
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
                ? (best ? `Best judgement: <b class="num">${esc(best.grade)} (${best.total}/100)</b> — present it again to improve.` : `The scroll awaits. Write real code, be judged by ${esc(persona())}, earn up to <span class="num">${Math.round(sec.freestyle.reward * SRANK_MULT)}</span> ${coin()}.`)
                : `SEALED — pass <span class="num">${Math.ceil(sectionExercises(sec).length * 0.7)}</span> of <span class="num">${sectionExercises(sec).length}</span> trials to break the seal (<span class="num">${Math.round(frac * 100)}%</span> done, need 70%).`}
            </div>
          </div>
          <button class="btn ${fsOpen ? "" : "quiet"}" id="btn-fs" ${fsOpen ? "" : "disabled"}>${ico("scroll")} UNROLL THE SCROLL</button>
        </div>
      </div>`;
    v.querySelectorAll("[data-lesson]").forEach((b) => (b.onclick = () => go("lesson", sid, b.dataset.lesson)));
    $("[data-nav=home]", v).onclick = () => go("home");
    wireReview(v);
    const fsBtn = $("#btn-fs", v);
    if (fsBtn && fsOpen) fsBtn.onclick = () => go("freestyle", sid);
  }

  // ------------------------------------------------------------ LESSON
  function renderLesson(sid, lid) {
    const sec = secById(sid);
    const li = sec.lessons.findIndex((l2) => l2.id === lid);
    const l = sec.lessons[li];
    const v = $("#view-lesson");
    v.classList.remove("hidden");
    $("#hud-op").textContent = "— " + sec.codename.toLowerCase() + ", lesson " + roman(li + 1).toLowerCase();
    S.read[lid] = true;

    v.innerHTML = `
      <div class="crumb"><button data-nav="home">LEDGER</button> / <button data-nav="sec">${esc(sec.codename)}</button> / LESSON ${roman(li + 1)}</div>
      <h1>${esc(l.title)}</h1>
      <div class="lesson-body">${l.body}</div>
      ${l.readings && l.readings.length ? `
      <div class="readings">
        <h2 style="margin-top:0">${ico("book")} THE MORTAL LIBRARY</h2>
        ${l.readings.map((r) => `<div class="r-item"><span class="tag">OPTIONAL</span><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.label)}</a></div>`).join("")}
      </div>` : ""}
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px">
        <h2>THE TRIALS</h2>
        <button class="btn quiet" id="b-oracle">${ico("orb")} CONSULT THE ORACLE (${S.inv.oracle || 0})</button>
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
    l.exercises.forEach((e, i) => exList.appendChild(exerciseEl(e, i)));

    const bo = $("#b-oracle", v);
    let boSel = "";
    bo.onpointerdown = () => { boSel = grabSelection(); };
    bo.onclick = () => askOracle(`${sec.codename} / ${l.title}`, `${sec.codename} — ${sec.title} / lesson: ${l.title}`, boSel);
    save();
  }

  // what the operator has highlighted right now: Monaco selection, textarea/input selection, or page text.
  // call from pointerdown — by click time the browser has already collapsed document selections.
  function grabSelection() {
    if (S.nav && S.nav.view === "freestyle" && ed && ed.getModel()) {
      const s2 = ed.getSelection();
      if (s2 && !s2.isEmpty()) return ed.getModel().getValueInRange(s2);
    }
    const ae = document.activeElement;
    if (ae && (ae.tagName === "TEXTAREA" || ae.tagName === "INPUT") && ae.selectionStart !== ae.selectionEnd)
      return ae.value.slice(ae.selectionStart, ae.selectionEnd);
    return String(window.getSelection()).trim();
  }

  // context for a global oracle ask, based on where the operator currently is
  function oracleContext() {
    const nav = S.nav || {};
    const sec = nav.sec && secById(nav.sec);
    let label = "global", detail = `no specific lesson open — general ${langName()} question`;
    if (nav.view === "lesson" && sec) {
      const l = sec.lessons.find((x) => x.id === nav.lesson);
      label = `${sec.codename} / ${l ? l.title : ""}`;
      detail = `${sec.codename} — ${sec.title}` + (l ? ` / lesson: ${l.title}` : "");
    } else if (nav.view === "freestyle" && sec) {
      label = `${sec.codename} / freestyle`;
      detail = `${sec.codename} — ${sec.title} / freestyle build: ${sec.build}`;
      const m = activeFile && models[activeFile];
      if (activeFile && activeFile.endsWith(newFileExt()) && m && !m.isDisposed())
        detail += `\n\nSTUDENT'S CURRENT FILE (${activeFile}):\n${m.getValue()}`;
    } else if (sec) {
      label = sec.codename;
      detail = `${sec.codename} — ${sec.title}`;
    }
    return { label, detail };
  }

  function paintOracleBtn() {
    const n = `(${S.inv.oracle || 0})`;
    const side = $("#obj-orb-n"); if (side) side.textContent = n;
    const ob = $("#b-oracle"); if (ob) ob.innerHTML = `${ico("orb")} CONSULT THE ORACLE ${n}`;
  }

  function askOracle(label, detail, selection) {
    if ((S.inv.oracle || 0) < 1) {
      modal(`<h2>WAKE THE ORACLE?</h2>
        <p class="dim">One question whispered into the crystal — an AI spirit dwelling in this very machine (Ollama). Each scrying answers a single question.</p>
        <p>The orb demands: <b class="num">${ORACLE_COST}</b>${gp()} — your purse holds <span class="num">${S.credits}</span>${gp()}.</p>`,
        [["LET IT SLEEP", "quiet"], [`PAY (${ORACLE_COST}${gp()})`, "", () => {
          if (!spend(ORACLE_COST)) return;
          S.inv.oracle = (S.inv.oracle || 0) + 1;
          sfx("buy"); save(); paintOracleBtn();
          askOracle(label, detail, selection);
        }]]);
      return;
    }
    modal(`<h2>CONSULT THE ORACLE</h2>
      <p class="dim">One question to the spirit in the crystal. Consumes one scrying — you hold ${S.inv.oracle}.</p>
      ${selection ? `<div class="faint" style="font-size:10.5px;letter-spacing:.14em;margin-bottom:4px">THE ORB REFLECTS YOUR SELECTION</div>
      <pre style="max-height:110px;overflow:auto;margin:0 0 10px;padding:8px;border:1px solid var(--line-hi);border-radius:3px;font-family:var(--mono);font-size:12px"><code></code></pre>` : ""}
      <textarea id="oracle-q" rows="3" style="width:100%" placeholder="e.g. why does ReadLine return null? what's the difference between var and int?"></textarea>
      <div id="oracle-a" class="hidden" style="margin-top:12px;padding:12px;border:1px solid var(--line-hi);border-left:2px solid var(--ac-dim);border-radius:3px;font-size:13px;white-space:pre-wrap;max-height:45vh;overflow-y:auto"></div>`,
      [["COVER THE ORB", "quiet"]]);
    if (selection) $("#modal-root pre code").textContent = selection.slice(0, 600);
    const actions = $("#modal-root .modal-actions");
    const askBtn = document.createElement("button");
    askBtn.className = "btn"; askBtn.textContent = "ASK (1 SCRYING)";
    askBtn.onclick = async () => {
      const q = $("#oracle-q").value.trim();
      if (!q) return;
      askBtn.disabled = true; askBtn.textContent = "THE MISTS SWIRL...";
      $("#oracle-q").disabled = true;
      const out = $("#oracle-a");
      out.classList.remove("hidden");
      out.textContent = "gazing into the glass...";
      let data;
      try {
        const r = await fetch("/api/oracle", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question: q,
            model: S.ai.oracle,
            kind: S.ai.oracleKind || "ollama",
            language: langName(),
            context: detail + (selection ? `\n\nTHE STUDENT HIGHLIGHTED THIS TEXT (their question likely refers to it):\n${selection.slice(0, 2000)}` : ""),
          }),
        });
        data = await r.json();
      } catch (err) { data = { ok: false, answer: "server error: " + err }; }
      out.textContent = data.answer;
      if (data.ok) {
        (S.oracleLog = S.oracleLog || []).push({ q, a: data.answer, ctx: label, at: Date.now() });
        S.inv.oracle--;
        save();
        paintOracleBtn();
        askBtn.remove();   // one question per scrying — pay again for the next
      } else {
        askBtn.disabled = false; askBtn.textContent = "ASK (1 SCRYING)";
        $("#oracle-q").disabled = false;
      }
    };
    actions.prepend(askBtn);
    setTimeout(() => { const f = $("#oracle-q"); if (f) f.focus(); }, 50);
  }

  function showOracleLog() {
    const rows = (S.oracleLog || []).slice().reverse().map((e) =>
      `<div style="margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid var(--line)">
        <div class="dim" style="font-size:11px">${new Date(e.at).toLocaleString()} — ${esc(e.ctx || "")}</div>
        <div style="margin:6px 0"><b>&gt; ${esc(e.q)}</b></div>
        <div style="white-space:pre-wrap;font-size:12.5px">${esc(e.a)}</div>
      </div>`).join("");
    modal(`<h2>THE ORACLE'S NOTES</h2>
      <div style="max-height:60vh;overflow-y:auto">${rows || '<p class="dim">The pages are blank. Consult the Oracle and its answers will be copied down here.</p>'}</div>`,
      [["SET THE NOTES DOWN", "quiet"]]);
  }

  // ------------------------------------------------------------ the Binder
  // ask a headless AI agent (server-side CLI) to make a small change to this
  // course — guided by course-configuration-guide.md; validated after.
  // The [PROVIDER][MODEL][EFFORT] cascade is the bindery's, fed by /api/models.
  let binderPoll = null;   // one watcher at a time, even across bench visits
  function showBinder() {
    modal(`<h2>THE BINDER</h2>
      <p class="dim">Name one small flaw in this tome — a typo, a wrong color, a price, a missing line —
      and the Binder's spirit will re-ink the page. It edits the course itself, so be specific.</p>
      <textarea id="binder-q" rows="3" style="width:100%" placeholder="e.g. the s02-l03 hint has a typo · make the signature theme's accent more copper · rename the SLAG SHIELD to CINDER WARD"></textarea>
      <div class="forge-field" style="margin-top:10px"><label>THE BINDER'S HAND</label>
        <div class="forge-ai-row">
          <select id="bd-prov" class="cfg-select" style="flex:0 0 auto;width:172px"><option value="">PICK A MODEL</option></select>
          <select id="bd-model" class="cfg-select" style="flex:1 1 auto;min-width:0" disabled><option value="">—</option></select>
          <select id="bd-eff" class="cfg-select" style="flex:0 0 auto;width:104px" disabled><option value="">—</option></select>
        </div></div>
      <div id="binder-a" class="hidden" style="margin-top:12px;padding:12px;border:1px solid var(--line-hi);border-left:2px solid var(--ac-dim);border-radius:3px;font-size:12.5px;white-space:pre-wrap;max-height:45vh;overflow-y:auto"></div>`,
      [["LEAVE THE BENCH", "quiet"]]);
    const root = $("#modal-root");
    $(".modal", root).classList.add("wide");   // room for the validator's report and the button row
    const k = { prov: $("#bd-prov", root), model: $("#bd-model", root), eff: $("#bd-eff", root) };
    let BINDERY = [];
    const fillEffort = () => {   // effort follows the selected MODEL (row is [id,label,tag,efforts])
      const p = BINDERY.find((x) => x.id === k.prov.value);
      const m = p && (p.models || []).find((mm) => mm[0] === k.model.value);
      const levels = (m && m[3]) || [];
      k.eff.innerHTML = levels.length
        ? `<option value="">DEFAULT</option>` + levels.map((l) => `<option value="${esc(l)}">${esc(l.toUpperCase())}</option>`).join("")
        : `<option value="">—</option>`;
      k.eff.disabled = !levels.length;
    };
    const fillModels = () => {
      const p = BINDERY.find((x) => x.id === k.prov.value);
      const models = (p && p.models) || [];
      k.model.innerHTML = models.length
        ? models.map(([v, l, tag]) => `<option value="${esc(v)}"${tag ? ` data-suffix="— ${esc(tag)}"` : ""}>${esc(l)}</option>`).join("")
        : `<option value="">${p ? "(no models found)" : "—"}</option>`;
      k.model.disabled = !models.length;
      fillEffort();
    };
    const BD_SAVE = "binderRunner";
    let restoring = false;
    const persist = () => {
      if (restoring) return;
      try { localStorage.setItem(BD_SAVE, JSON.stringify({ prov: k.prov.value, model: k.model.value, eff: k.eff.value })); } catch (e) { /* private mode */ }
    };
    k.prov.addEventListener("change", fillModels);
    k.model.addEventListener("change", fillEffort);
    [k.prov, k.model, k.eff].forEach((s) => { enhanceSelect(s); s.addEventListener("change", persist); });
    fetch("/api/models").then((r) => r.json()).then((d) => {
      BINDERY = (d.bindery || []).filter((p) => p.installed !== false);
      k.prov.insertAdjacentHTML("beforeend", BINDERY.map((p) => `<option value="${esc(p.id)}">${esc(p.label)}</option>`).join(""));
      const has = (sel, v) => [...sel.options].some((o) => o.value === v);
      let s = {}; try { s = JSON.parse(localStorage.getItem(BD_SAVE) || "{}"); } catch (e) { /* ignore */ }
      restoring = true;
      if (s.prov && has(k.prov, s.prov)) {
        k.prov.value = s.prov; k.prov.dispatchEvent(new Event("change"));
        if (s.model && has(k.model, s.model)) { k.model.value = s.model; k.model.dispatchEvent(new Event("change")); }
        if (s.eff && has(k.eff, s.eff)) { k.eff.value = s.eff; k.eff.dispatchEvent(new Event("change")); }
      }
      restoring = false;
    }).catch(() => { toast("Could not reach the model list — is the server up?", "bad"); });
    const actions = $("#modal-root .modal-actions");
    const out = $("#binder-a", root);
    const sendBtn = document.createElement("button");
    sendBtn.className = "btn"; sendBtn.textContent = "SEND TO THE BINDER";
    const idle = () => {
      sendBtn.disabled = false; sendBtn.textContent = "SEND TO THE BINDER";
      $("#binder-q").disabled = false;
      actions.querySelectorAll(".binder-cancel").forEach((b) => b.remove());
    };
    // watch one server-side job. The job outlives this dialog — leaving the bench
    // never stops the Binder; reopening reattaches via /api/amend/current.
    const watch = (jobId) => {
      sendBtn.disabled = true; sendBtn.textContent = "THE BINDER WORKS...";
      $("#binder-q").disabled = true;
      out.classList.remove("hidden");
      actions.querySelectorAll(".binder-extra, .binder-cancel").forEach((b) => b.remove());
      const cx = document.createElement("button");
      cx.className = "btn quiet binder-cancel"; cx.textContent = "STAY THE QUILL";
      cx.title = "Cancel this amendment";
      cx.onclick = async () => {
        cx.disabled = true;
        out.textContent = "snuffing the quill...";
        try {
          const r = await (await fetch("/api/amend/cancel", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: jobId }) })).json();
          if (!r.ok) throw new Error(r.error || "the server would not stay the quill");
        } catch (e) {
          toast("Could not cancel: " + esc(String(e.message || e)) + " — if the server predates this button, restart it.", "bad");
          out.textContent = "the binder works on...";
          cx.disabled = false;
        }
      };
      actions.prepend(cx);
      clearInterval(binderPoll);
      binderPoll = setInterval(async () => {
        let st;
        try { st = await (await fetch("/api/amend/status?id=" + encodeURIComponent(jobId))).json(); } catch { return; }
        if (st.status === "running") return;
        clearInterval(binderPoll);
        idle();
        if (st.status === "done") {
          out.textContent = (st.summary || "(the binder said nothing)")
            + (st.validatorOk === false ? "\n\n⚠ THE CANDLE FINDS FLAWS:\n" + (st.validator || "") : "");
          const rb = document.createElement("button");
          rb.className = "btn binder-extra"; rb.textContent = "RE-OPEN THE TOME";
          rb.onclick = () => location.reload();
          actions.prepend(rb);
          if (st.validatorOk === false && st.validator) {
            const fx = document.createElement("button");
            fx.className = "btn binder-extra"; fx.textContent = "MEND THE FLAWS";
            fx.onclick = () => {
              $("#binder-q").value = "Fix every ERROR and WARN the validator reports below. Address each one; do not skip any.\n\n" + st.validator;
              sendBtn.onclick();
            };
            actions.prepend(fx);
          }
        } else if (st.status === "cancelled") {
          out.textContent = "THE QUILL IS STAYED — the amendment was cancelled. A half-inked edit may remain; ask the Binder again if the page looks wrong.";
        } else {
          out.textContent = "THE QUILL SNAPPED — " + (st.error || "unknown error");
        }
      }, 2500);
    };
    sendBtn.onclick = async () => {
      const q = $("#binder-q").value.trim();
      if (!q) return;
      const p = BINDERY.find((x) => x.id === k.prov.value);
      if (!p || !k.model.value) { toast("Pick the Binder's <b>model</b> first.", "warn"); return; }
      out.classList.remove("hidden");
      out.textContent = "the quill is dipped...";
      try {
        const r = await (await fetch("/api/amend", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ request: q, kind: p.kind, model: k.model.value, effort: k.eff.value || undefined }),
        })).json();
        if (!r.ok) throw new Error(r.error || "the binder did not answer");
        if (r.existing) out.textContent = "the Binder is already at work on this tome — watching that job...";
        watch(r.jobId);
      } catch (err) {
        out.textContent = "server error: " + err;
      }
    };
    actions.prepend(sendBtn);
    // a job begun on an earlier visit is still inking — reattach to it
    fetch("/api/amend/current").then((r) => r.json()).then((d) => {
      if (!d.jobId) return;
      const q = $("#binder-q");
      if (q && !q.value) q.value = d.request || "";
      out.textContent = "the Binder is already at work on this tome — watching that job...";
      watch(d.jobId);
    }).catch(() => { /* no reattach; the bench still works */ });
    setTimeout(() => { const f = $("#binder-q"); if (f) f.focus(); }, 50);
  }

  // ------------------------------------------------------------ code book
  // a lesson is "completed" once every one of its exercises is cracked
  // (lessons without exercises count once they've been opened/read)
  function lessonDone(l) {
    return l.exercises && l.exercises.length
      ? l.exercises.every((e) => S.ex[e.id] && S.ex[e.id].ok)
      : !!S.read[l.id];
  }

  function showCodeBook() {
    const scratch = document.createElement("div");
    const ops = [];
    for (const sec of window.SECTIONS) {
      const lessons = [];
      for (const l of sec.lessons || []) {
        if (!lessonDone(l)) continue;
        scratch.innerHTML = l.body || "";
        const blocks = [...scratch.querySelectorAll("pre")].map((p) => p.textContent.trim()).filter(Boolean);
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

  // normalize code for typing-drill / lab-output comparison:
  // trims line ends, collapses internal whitespace runs, drops blank lines
  function normCode(s2) {
    return String(s2).split("\n").map((l) => l.trim().replace(/\s+/g, " ")).filter((l) => l !== "").join("\n");
  }
  function firstDiff(a, b) {
    const A = normCode(a).split("\n"), B = normCode(b).split("\n");
    for (let i = 0; i < Math.max(A.length, B.length); i++) {
      if (A[i] !== B[i]) {
        const got = A[i] || "(missing line)", expected = B[i] || "(nothing — extra line)";
        let col = 0;
        while (col < Math.min(got.length, expected.length) && got[col] === expected[col]) col++;
        const name = (c) => c === undefined ? "(end of line)" : c === "0" ? "'0' (zero)" : c === "O" ? "'O' (letter O)" : c === "l" ? "'l' (lowercase L)" : c === "1" ? "'1' (one)" : `'${c}'`;
        return { line: i + 1, expected, got, hint: A[i] && B[i] ? ` — first difference at char ${col + 1}: expected ${name(expected[col])} got ${name(got[col])}` : "" };
      }
    }
    return null;
  }
  const sfx = (n) => { if (window.GhostAudio && S.audio.sfx) window.GhostAudio.sfx(n); };

  // ---- inline monaco pads: full C# intellisense anywhere code is typed (labs, intrusion defense).
  // the completion provider in editor.js is registered per-language, so every pad gets it free.
  const pads = [];
  function codePad(host, value, onCtrlEnter) {
    for (let i = pads.length - 1; i >= 0; i--) // sweep editors whose DOM is gone
      if (!pads[i].host.isConnected) { pads[i].ed.dispose(); pads.splice(i, 1); }
    host.style.height = Math.min(30, Math.max(12, value.split("\n").length + 4)) * 22 + 26 + "px";
    const pe = window.GhostEditor.create(host, S.theme);
    pe.setValue(value);
    if (onCtrlEnter) pe.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, onCtrlEnter);
    pads.push({ host, ed: pe });

    // real compiler squiggles: on idle, build the snippet server-side and underline errors/warnings
    let timer = null, busy = false, again = false;
    const diag = async () => {
      if (busy) { again = true; return; }
      busy = true;
      let data = null;
      try {
        const r = await fetch("/api/snippetdiag", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code: pe.getValue() }),
        });
        data = await r.json();
      } catch { /* server hiccup — keep existing markers */ }
      busy = false;
      if (again) { again = false; timer = setTimeout(diag, 200); return; }
      const m = pe.getModel();
      if (!data || !data.ok || !m || m.isDisposed()) return;
      monaco.editor.setModelMarkers(m, "paddiag", (data.diags || []).map((d) => {
        const w = m.getWordAtPosition({ lineNumber: d.line, column: d.col });
        return {
          severity: d.sev === "error" ? monaco.MarkerSeverity.Error : monaco.MarkerSeverity.Warning,
          message: `${d.code}: ${d.msg}`,
          startLineNumber: d.line, startColumn: d.col,
          endLineNumber: d.line, endColumn: w ? w.endColumn : d.col + 1,
        };
      }));
    };
    pe.getModel().onDidChangeContent(() => { clearTimeout(timer); timer = setTimeout(diag, 1500); });
    return pe;
  }

  const EX_LABEL = { mc: "CHOOSE WISELY", fill: "COMPLETE THE RUNE", text: "SPEAK THE WORD", type: "COPYING DRILL", write: "INSCRIPTION" };

  // ------------------------------------------------------------ SPACED REVIEW
  // Retrieval practice of already-solved recall items, resurfaced on a Leitner
  // schedule keyed to lessons completed (a self-paced course's natural clock, not
  // the wall). type/write are no-decay skill drills already, so review covers only
  // mc/fill/text. A hit pushes the item further out; a miss brings it right back.
  const REVIEWABLE = new Set(["mc", "fill", "text"]);
  const REVIEW_STEPS = [1, 2, 4, 8, 16]; // Leitner intervals, in lessons-completed units
  const lessonsCompleted = () => window.SECTIONS.reduce((n, s) => n + s.lessons.filter(lessonDone).length, 0);
  function scheduleReview(st, ok) {
    st.box = ok ? Math.min((st.box || 1) + 1, REVIEW_STEPS.length) : 1;
    st.due = lessonsCompleted() + REVIEW_STEPS[st.box - 1];
  }
  function reviewDue() {
    const clock = lessonsCompleted(), out = [];
    for (const sec of window.SECTIONS)
      for (const l of sec.lessons)
        for (const e of (l.exercises || [])) {
          if (!REVIEWABLE.has(e.type)) continue;
          const st = S.ex[e.id];
          if (st && st.ok && st.due != null && st.due <= clock) out.push({ e, st });
        }
    return out.sort((a, b) => a.st.due - b.st.due);
  }
  // a banner shown wherever review is due; caller wires #btn-review to startReview
  function reviewBanner() {
    const n = reviewDue().length;
    if (!n) return "";
    return `<div id="review-cta" style="display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;margin:0 0 18px;padding:13px 16px;border:1px solid var(--line-hi);border-radius:var(--rad);background:var(--ac-bg)">
      <div><b>${ico("bell")} SPACED REVIEW</b> <span class="dim" style="font-size:12.5px">${n} concept${n > 1 ? "s you have" : " you have"} learned ${n > 1 ? "are" : "is"} due to be re-forged — quick recall keeps them from fading.</span></div>
      <button class="btn" id="btn-review">${ico("scroll")} BEGIN REVIEW (${n})</button></div>`;
  }
  function wireReview(v) { const b = $("#btn-review", v); if (b) b.onclick = startReview; }

  function startReview() {
    const due = reviewDue().slice(0, 8); // a short round; the rest surface next time
    if (!due.length) { toast("Nothing is due for review — your seals hold.", "ok"); return; }
    const graded = new Set(); // grade each item once per round, on its first outcome
    const overlay = document.createElement("div");
    overlay.className = "grade-overlay review-overlay";
    overlay.innerHTML = `<div class="grade-card" style="max-width:780px;width:min(780px,94vw);max-height:88vh;display:flex;flex-direction:column">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px">
        <div>
          <div class="faint" style="font-size:11px;letter-spacing:.2em">✦ SPACED REVIEW // RE-FORGE WHAT YOU HAVE LEARNED</div>
          <h2 style="margin:6px 0 0">THE MASTER CALLS BACK OLD LESSONS</h2>
          <div class="dim" style="font-size:12.5px;margin-top:4px">Answer from memory. No coin, no penalty — recall is its own rent. <span id="rv-count" class="num"></span></div>
        </div>
        <button class="btn quiet" id="rv-close">CLOSE</button>
      </div>
      <div class="review-scroll" style="overflow:auto;margin-top:14px;flex:1;display:flex;flex-direction:column;gap:14px"></div>`;
    const scroll = $(".review-scroll", overlay);
    const updateCount = () => { const c = $("#rv-count", overlay); if (c) c.textContent = `${graded.size}/${due.length} re-forged`; };
    due.forEach(({ e, st }, i) => {
      scroll.appendChild(exerciseEl(e, i, true, (ok) => {
        if (graded.has(e.id)) return;
        graded.add(e.id);
        scheduleReview(st, ok);
        S.stats.reviews = (S.stats.reviews || 0) + 1;
        save(); updateCount();
        if (graded.size >= due.length) toast("Review complete — the old seals are re-forged.", "ok");
      }));
    });
    updateCount();
    document.body.appendChild(overlay);
    $("#rv-close", overlay).onclick = () => overlay.remove();
  }

  function exerciseEl(e, idx, redo, onReview) {
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
          ${redo ? `<button class="btn quiet b-done">MARK COMPLETE</button>` : ""}
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
        verdict.className = "ex-verdict ok";
        verdict.textContent = onReview ? "RECALLED CLEAN — the seal is re-forged" : "THE SEAL HOLDS — A CLEAN RECAST";
        if (onReview) onReview(true);
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

  // ------------------------------------------------------------ FREESTYLE
  let ed = null;               // monaco editor instance
  let models = {};             // path -> monaco model
  let activeFile = null;
  let fsSection = null;

  async function renderFreestyle(sid) {
    const sec = secById(sid);
    fsSection = sec;
    const v = $("#view-freestyle");
    v.classList.remove("hidden");
    $("#hud-op").textContent = "— the great working";
    const best = fsBest(sid);
    const xrayOn = S.fs[sid] && S.fs[sid].xray;

    v.innerHTML = `
      <div id="fs-wrap">
        ${reviewBanner()}
        <div class="fs-top">
          <div>
            <span class="crumb" style="margin:0"><button data-nav="sec">${esc(sec.codename)}</button> / THE GREAT WORKING</span>
            <div class="fs-title">${esc(sec.freestyle.title)}</div>
          </div>
          <div class="fs-actions">
            ${best ? `<span class="tag ac num">BEST: ${esc(best.grade)} ${best.total}/100</span>` : ""}
            ${externalMode()
              ? (externalDir()
                  ? `<button class="btn quiet" id="b-openext" title="Open ${esc(externalDir())} in your file explorer">${ico("file")} OPEN IN FILE EXPLORER</button><button class="btn quiet" id="b-extern" title="${esc(externalDir())}">${ico("quill")} EDITOR PATH</button>`
                  : `<button class="btn" id="b-extern">${ico("file")} CHOOSE PROJECT FOLDER</button>`)
              : `<button class="btn quiet" id="b-extern">${ico("file")} USE MY OWN EDITOR</button>`}
            ${!externalMode() && (J().runtime && J().runtime.packages) !== false ? `<button class="btn quiet" id="b-pkg">${ico("pkg")} REAGENTS</button>` : ""}
            ${!externalMode() ? `<button class="btn quiet" id="b-save">${ico("quill")} BLOT THE PAGE</button>` : ""}
            <button class="btn ghost" id="b-run">${ico("play")} CAST THE SPELL</button>
            <button class="btn" id="b-submit">${ico("upload")} PRESENT TO ${esc(persona())}</button>
          </div>
        </div>
        <div id="fs-cols">
          <div id="fs-left" class="${externalMode() ? "ext" : ""}">
            ${externalMode() ? `
            <div id="ext-panel">
              <div class="ext-head">${ico("file")} YOU'RE EDITING IN YOUR OWN EDITOR</div>
              <div class="ext-grid${externalByAuthor() || !externalDir() ? " solo" : ""}">
                <div class="ext-main">
                  ${externalDir() ? `
                  <p>Open and build this project in your own IDE (IntelliJ, VS Code, and so on):</p>
                  <div class="ext-dir"><code>${esc(externalDir())}</code></div>
                  <p><b>CAST THE SPELL</b> runs that folder via <code>${esc(runLabel())}</code>, and <b>PRESENT TO ${esc(persona())}</b> sends the whole folder for judgement. Both read your folder directly — the workbench never edits or resets it. Save in your own editor before you cast or present.</p>
                  <div class="ext-buttons">
                    ${externalByAuthor() ? "" : `<button class="btn quiet" id="b-seed">${ico("file")} PLACE STARTER FILES</button>`}
                    <button class="btn quiet" id="b-extern2">${ico("quill")} CHANGE FOLDER</button>
                    ${externalByAuthor() ? "" : `<button class="btn quiet" id="b-builtin">${ico("quill")} SWITCH BACK TO THE BUILT-IN EDITOR</button>`}
                  </div>`
                  : `
                  <p>${externalByAuthor()
                      ? "This course is built in your own project — there is no built-in editor. Follow the setup lessons to create the project folder, then point the workbench at it:"
                      : "Point the workbench at a folder you build in with your own IDE (IntelliJ, VS Code, a real project):"}</p>
                  <div class="ext-buttons">
                    <button class="btn" id="b-choose">${ico("file")} CHOOSE PROJECT FOLDER</button>
                    ${externalByAuthor() ? "" : `<button class="btn quiet" id="b-builtin">${ico("quill")} USE THE BUILT-IN EDITOR INSTEAD</button>`}
                  </div>
                  <p class="dim">An absolute path to a folder that already exists. The engine only reads it — it never edits, scaffolds, or resets your project.</p>`}
                </div>
                ${externalByAuthor() || !externalDir() ? "" : `
                <div class="ext-files">
                  <h4>THIS PROJECT NEEDS</h4>
                  <ul class="sf-grid">
                    ${requiredFiles().map((f) => `<li class="sf-item" data-rel="${esc(f.rel)}" title="View the starter contents"><code>${esc(f.path)}</code>${f.location ? ` <span class="dim">in <code>${esc(f.location)}/</code></span>` : ""}<span class="ext-fdesc">${esc(f.desc)}</span><span class="sf-view">${ico("eye")} view starter code</span></li>`).join("")}
                  </ul>
                  <p class="dim">Placed in your folder when you chose it. Missing any, or want them fresh? Use <b>PLACE STARTER FILES</b>.</p>
                </div>`}
              </div>
            </div>` : `
            <div id="file-tabs"></div>
            <div id="editor-host"></div>`}
            <div id="term">
              <div class="term-head"><span>THE SPEAKING STONE</span><button class="btn quiet" id="b-clear" style="height:22px;padding:0 8px;font-size:10px">WIPE</button></div>
              <div class="term-stdin">
                <span class="stdin-label">WHISPER (STDIN)</span>
                <input type="text" id="stdin-box" placeholder="whispered to your spell as it runs — separate lines with \\n  (e.g.  hello\\nquit)" spellcheck="false">
              </div>
              <pre id="term-out">The speaking stone is set into the desk. CAST THE SPELL runs your work via ${esc(runLabel())}; the stone repeats what it says.</pre>
            </div>
          </div>
          <div id="fs-right">
            <h3>THE COMMISSION</h3>
            <div class="fs-brief">${sec.freestyle.brief.replace(/<ul>[\s\S]*?<\/ul>/, "")}</div>
            ${(sec.freestyle.brief.match(/<ul>[\s\S]*?<\/ul>/) || []).map((u) =>
              `<h3 style="margin-top:18px">IT MUST</h3><div class="fs-brief">${u}</div>`).join("")}
            <h3 style="margin-top:18px">THE JUDGEMENT CHART <span class="dim" style="letter-spacing:0;font-style:italic">(${esc(persona())} weighs against exactly this)</span></h3>
            <table class="rubric-table">
              ${sec.freestyle.rubric.map((r) => `<tr><td class="rw num">${r.weight}%</td><td><b>${esc(r.criterion)}</b><span class="rubric-desc">${esc(r.desc)}</span></td></tr>`).join("")}
            </table>
            <h3 style="margin-top:18px">PAYMENT</h3>
            <div style="font-size:12.5px" class="dim">
              Base <span class="num">${sec.freestyle.reward}</span>${gp()} scaled by the judgement. An S pays <span class="num">${Math.round(sec.freestyle.reward * SRANK_MULT)}</span>${gp()}.
              A C (70+) presses the <b>${esc(sec.freestyle.badge.name)}</b> sigil. A D (60+) unseals the next chapter.
              Presenting again pays only the improvement over your best.
            </div>
            ${sec.freestyle.xray ? (xrayOn
              ? `<h3 style="margin-top:18px">SCRYING LENS <span class="tag warn">HELD TO THE PAGE</span></h3><p style="font-size:12.5px" class="dim">${sec.freestyle.xray}</p>`
              : `<button class="btn quiet" id="b-xray" style="margin-top:16px">${ico("eye")} RAISE THE SCRYING LENS (${S.inv.xray || 0} owned)</button>`) : ""}
          </div>
        </div>
      </div>`;

    $("[data-nav=sec]", v).onclick = () => go("section", sid);
    wireReview(v);

    // xray
    const bx = $("#b-xray", v);
    if (bx) bx.onclick = () => {
      if ((S.inv.xray || 0) < 1) { toast("You carry no Scrying Lens. The peddler grinds them.", "bad"); return; }
      modal(`<h2>RAISE THE SCRYING LENS?</h2><p class="dim">The lens shatters after one use — but ${esc(persona())}'s private judging notes for this working stay revealed forever.</p>`,
        [["LOWER IT", "quiet"], ["LOOK THROUGH", "", () => { S.inv.xray--; (S.fs[sid] = S.fs[sid] || {}).xray = true; save(); renderFreestyle(sid); }]]);
    };

    // external-editor mode: no built-in editor. The student edits in their own IDE
    // and CAST/PRESENT operate on their folder — the server resolves the directory,
    // so we send no buffers (collectFiles() is [] with no models, never clobbering it).
    if (externalMode()) {
      if (ed) { ed.dispose(); ed = null; }
      for (const m of Object.values(models)) m.dispose();
      models = {}; activeFile = null;
      // a required-external course starts with no folder chosen — CAST/PRESENT
      // must send the student to pick one, never run against the scaffolded dir.
      const needFolder = () => { if (externalDir()) return false; toast("Choose your project folder first.", "warn"); externalEditorModal(sid); return true; };
      $("#b-run", v).onclick = () => { if (!needFolder()) runProject(); };
      $("#b-submit", v).onclick = () => { if (!needFolder()) submitForGrading(); };
      $("#b-clear", v).onclick = () => { $("#term-out").textContent = ""; };
      const be = $("#b-extern", v); if (be) be.onclick = () => externalEditorModal(sid);
      const be2 = $("#b-extern2", v); if (be2) be2.onclick = () => externalEditorModal(sid);
      const bc = $("#b-choose", v); if (bc) bc.onclick = () => externalEditorModal(sid);
      const bo = $("#b-openext", v); if (bo) bo.onclick = () => openExternalFolder(externalDir());
      const bs = $("#b-seed", v); if (bs) bs.onclick = () => seedWorkspace(externalDir(), "");
      const bb = $("#b-builtin", v); if (bb) bb.onclick = () => {
        S.workspace = { enabled: false, dir: (S.workspace && S.workspace.dir) || "" };
        save(); renderFreestyle(sid);
      };
      v.querySelectorAll(".sf-item").forEach((li) => li.onclick = () => openStarterFile(li.dataset.rel));
      paintSubmitBtn();
      return;
    }

    // load workspace + editor
    await window.GhostEditor.monacoReady;
    const host = $("#editor-host", v);
    host.innerHTML = "";
    if (ed) { ed.dispose(); ed = null; }
    for (const m of Object.values(models)) m.dispose();
    models = {};
    ed = window.GhostEditor.create(host, S.theme);

    let files = [];
    try {
      const r = await fetch("/api/workspace");
      const data = await r.json();
      if (!data.exists) {
        termPrint(`No workshop yet — laying out a fresh one for ${projName()}...`);
        const sr = await fetch("/api/scaffold", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
        const sd = await sr.json();
        termPrint(sd.ok ? `The workshop stands: ${projName()} (${entryFile()} is yours to inscribe).` : "THE SCAFFOLDING COLLAPSED: " + (sd.error || ""), !sd.ok);
        const r2 = await fetch("/api/workspace");
        files = (await r2.json()).files || [];
      } else files = data.files || [];
    } catch (err) { termPrint("Could not reach server: " + err, true); }

    // merge crash-recovered buffers over disk state
    const byPath = {};
    for (const f of files) byPath[f.path] = f.content;
    for (const [p2, c] of Object.entries(S.buffers)) byPath[p2] = c;
    if (!Object.keys(byPath).length) byPath[entryFile()] = (J().runtime && J().runtime.starterCode) || 'Console.WriteLine("Verisearch v0.1");\n';

    window.GhostEditor._getAllBuffers = () => {
      const out = {};
      for (const [p2, m] of Object.entries(models)) out[p2] = m.getValue();
      return out;
    };

    for (const [p2, content] of Object.entries(byPath)) addFileModel(p2, content);
    const first = Object.keys(models).find((p2) => p2.endsWith(newFileExt())) || Object.keys(models)[0];
    switchFile(first);
    renderTabs();
    scheduleDiagnostics();

    // actions
    $("#b-save", v).onclick = () => saveWorkspace(true);
    $("#b-clear", v).onclick = () => { $("#term-out").textContent = ""; }; // (stone tap + chips come from the material delegate in init)
    $("#b-run", v).onclick = runProject;
    $("#b-submit", v).onclick = submitForGrading;
    if ($("#b-pkg", v)) $("#b-pkg", v).onclick = () => packageModal(sec);
    if ($("#b-extern", v)) $("#b-extern", v).onclick = () => externalEditorModal(sid);
    paintSubmitBtn(); // a grade may still be in flight from before a re-render
  }

  // seed the tome's starter files into the student's own folder. mode: "" checks first
  // (seeds silently if nothing is there, else prompts), "missing" adds only absent files,
  // "force" overwrites. Returns true if anything was placed.
  async function seedWorkspace(dir, mode) {
    if (!dir) return false;
    let d;
    try {
      const r = await fetch("/api/seedworkspace", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dir, mode: mode || "" }),
      });
      d = await r.json();
    } catch (e) { toast("Could not reach the forge to place files: " + e, "bad"); return false; }
    if (d.ok) {
      const placed = d.seeded || [];
      if (placed.length) { toast(`Starter files placed: ${placed.map((f) => `<code>${esc(f)}</code>`).join(" ")}`); sfx("saved"); }
      else toast("Your folder already has every starter file.");
      return true;
    }
    if (d.conflicts && d.conflicts.length) {
      const present = d.conflicts, missing = d.missing || [];
      const list = (arr) => `<ul style="margin:6px 0 0;padding-left:18px;font-family:var(--mono);font-size:12.5px">${arr.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>`;
      return await new Promise((resolve) => {
        const actions = [["KEEP MINE", "quiet", () => resolve(false)]];
        if (missing.length) actions.push(["ADD MISSING", "", () => { seedWorkspace(dir, "missing").then(resolve); }]);
        actions.push(["OVERWRITE", missing.length ? "quiet" : "", () => { seedWorkspace(dir, "force").then(resolve); }]);
        modal(`<h2>FILES ALREADY IN YOUR FOLDER</h2>
          <p class="dim">Your folder already holds ${present.length === 1 ? "this starter file" : "these starter files"}:</p>
          ${list(present)}
          ${missing.length ? `<p class="dim" style="margin-top:12px">Your folder is still missing:</p>${list(missing)}` : ""}
          <p class="dim" style="margin-top:12px">${missing.length
            ? "<b>Add missing</b> writes only what's absent and leaves your files alone. <b>Overwrite</b> replaces them all with the tome's fresh starter files."
            : "Overwrite them with the tome's fresh starter files, or keep your own?"}</p>`,
          actions);
      });
    }
    toast("Could not place starter files: " + (d.error || "unknown"), "bad");
    return false;
  }

  // show the starter contents of one required file, with a copy button
  async function openStarterFile(rel) {
    if (!rel) return;
    modal(`<h2>${esc(rel)}</h2>
      <p class="dim">The starter contents for this file — copy it into your own editor.</p>
      <pre id="sf-pre" style="max-height:52vh;overflow:auto;margin:10px 0 0;padding:12px 14px;border:1px solid var(--line-hi);border-radius:var(--rad);background:var(--bg2);font-family:var(--mono);font-size:12.5px;white-space:pre"><code>loading…</code></pre>`,
      [["CLOSE", "quiet"]]);
    const copyBtn = document.createElement("button");
    copyBtn.className = "btn"; copyBtn.textContent = "COPY";
    const actions = $("#modal-root .modal-actions"); if (actions) actions.prepend(copyBtn);
    let content = "";
    try {
      const r = await fetch("/api/starterfile?path=" + encodeURIComponent(rel));
      const j = await r.json();
      content = j.ok ? (j.content || "(this file has no starter content)") : ("(" + (j.error || "could not load") + ")");
    } catch (e) { content = "(could not load: " + e + ")"; }
    const code = $("#modal-root #sf-pre code"); if (code) code.textContent = content;
    copyBtn.onclick = () => {
      navigator.clipboard.writeText(content)
        .then(() => { copyBtn.textContent = "COPIED ✓"; setTimeout(() => { copyBtn.textContent = "COPY"; }, 1200); })
        .catch(() => toast("The browser blocked the clipboard — select and copy manually.", "warn"));
    };
  }

  // open the external project folder in the OS file explorer (server runs on the same machine)
  async function openExternalFolder(dir) {
    if (!dir) return;
    try {
      const r = await fetch("/api/openpath", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ dir }) });
      const d = await r.json();
      if (!d.ok) toast("Could not open the folder: " + (d.error || "unknown"), "bad");
    } catch (e) { toast("Could not open the folder: " + e, "bad"); }
  }

  // pick a folder the student builds in with their own editor; validated server-side
  function externalEditorModal(sid) {
    const cur = (S.workspace && S.workspace.dir) || externalDir() || "";
    modal(`<h2>USE YOUR OWN EDITOR</h2>
      <p class="dim">Point the workbench at a folder you build in your own IDE (IntelliJ, VS Code, a real project). <b>CAST</b> and <b>PRESENT</b> then run and grade that folder instead of the built-in editor — the engine only reads it, and never edits, scaffolds, or resets your project.</p>
      <input type="text" id="ext-dir" style="width:100%" placeholder="/home/you/projects/MyBuild" value="${esc(cur)}" spellcheck="false">
      <div id="ext-msg" class="dim" style="font-size:12px;margin-top:8px">An absolute path to a folder that already exists.</div>`,
      [["CANCEL", "quiet"], ["USE THIS FOLDER", "", null]]);
    const btns = document.querySelectorAll("#modal-root .modal-actions .btn");
    const useBtn = btns[btns.length - 1];
    useBtn.onclick = async () => {
      const dir = $("#ext-dir").value.trim();
      const msg = $("#ext-msg");
      if (!dir) { msg.textContent = "Enter a folder path."; return; }
      msg.textContent = "checking the path...";
      try {
        const r = await fetch("/api/checkdir?path=" + encodeURIComponent(dir));
        const d = await r.json();
        if (!d.abs) { msg.textContent = "Use an ABSOLUTE path (it must start with / )."; return; }
        if (!d.isdir) { msg.textContent = "No folder exists there — create it first, or fix the path."; return; }
      } catch (e) { msg.textContent = "Could not check the path: " + e; return; }
      S.workspace = { enabled: true, dir };
      save();
      closeModal(() => { renderFreestyle(sid); seedWorkspace(dir, ""); });
    };
    setTimeout(() => { const f = $("#ext-dir"); if (f) f.focus(); }, 50);
  }

  function addFileModel(path, content) {
    const lang = path.endsWith(newFileExt()) ? editorLang() : path.endsWith(".csproj") ? "xml" : path.endsWith(".json") ? "json" : path.match(/\.ya?ml$/) ? "yaml" : "plaintext";
    const m = monaco.editor.createModel(content, lang);
    m.onDidChangeContent(() => {
      S.buffers[path] = m.getValue();
      save();
      const tab = document.querySelector(`.ftab[data-path="${CSS.escape(path)}"] .dirty`);
      if (tab) tab.classList.remove("hidden");
      if (path.endsWith(newFileExt()) || path.endsWith(".csproj")) scheduleDiagnostics();
    });
    models[path] = m;
  }

  // real compiler squiggles: on idle, build the workspace server-side and mark CS errors/warnings
  let diagTimer = null, diagBusy = false, diagAgain = false;
  function scheduleDiagnostics() {
    clearTimeout(diagTimer);
    diagTimer = setTimeout(runDiagnostics, 1500);
  }
  async function runDiagnostics() {
    const live = Object.entries(models).filter(([, m]) => !m.isDisposed());
    if (!window.monaco || !live.length) return;
    if (diagBusy) { diagAgain = true; return; }
    diagBusy = true;
    let data = null;
    try {
      const r = await fetch("/api/diagnostics", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ files: live.map(([path, m]) => ({ path, content: m.getValue() })) }),
      });
      data = await r.json();
    } catch { /* server hiccup — keep existing markers */ }
    diagBusy = false;
    if (diagAgain) { diagAgain = false; scheduleDiagnostics(); }
    if (!data || !data.ok) return;
    const byFile = {};
    for (const d of data.diags || []) (byFile[d.file] = byFile[d.file] || []).push(d);
    for (const [path, m] of live) {
      if (m.isDisposed()) continue;
      monaco.editor.setModelMarkers(m, "ghostdiag", (byFile[path] || []).map((d) => {
        const w = m.getWordAtPosition({ lineNumber: d.line, column: d.col });
        return {
          severity: d.sev === "error" ? monaco.MarkerSeverity.Error : monaco.MarkerSeverity.Warning,
          message: `${d.code}: ${d.msg}`,
          startLineNumber: d.line, startColumn: d.col,
          endLineNumber: d.line, endColumn: w ? w.endColumn : d.col + 1,
        };
      }));
    }
  }

  function renderTabs() {
    const tabs = $("#file-tabs");
    if (!tabs) return;
    tabs.innerHTML = "";
    for (const p2 of Object.keys(models).sort()) {
      const t = document.createElement("button");
      t.className = "ftab" + (p2 === activeFile ? " active" : "");
      t.dataset.path = p2;
      t.innerHTML = `${esc(p2)}<span class="dirty ${S.buffers[p2] !== undefined ? "" : "hidden"}"></span>`;
      t.onclick = () => switchFile(p2);
      tabs.appendChild(t);
    }
    const plus = document.createElement("button");
    plus.className = "ftab-new"; plus.textContent = "+"; plus.title = "New file";
    plus.onclick = () => {
      modal(`<h2>A FRESH LEAF</h2><p class="dim">Its name within the ${esc(projName())} folio, e.g. <code>module${esc(newFileExt())}</code></p><input type="text" id="nf-name" style="width:100%" placeholder="MyFile${esc(newFileExt())}">`,
        [["LEAVE IT", "quiet"], ["CUT THE LEAF", "", null]]);
      const nfBtn = document.querySelectorAll("#modal-root .modal-actions .btn")[1];
      nfBtn.onclick = () => {
        const name = $("#nf-name").value.trim();
        closeModal(() => {
          if (!name || models[name]) return;
          addFileModel(name, name.endsWith(".cs") ? `namespace ${projName()};\n\n` : "");
          S.buffers[name] = models[name].getValue();
          switchFile(name); save();
        });
      };
      setTimeout(() => { const f = $("#nf-name"); if (f) f.focus(); }, 50);
    };
    tabs.appendChild(plus);
  }

  function switchFile(path) {
    if (!models[path]) return;
    activeFile = path;
    ed.setModel(models[path]);
    renderTabs();
    ed.focus();
  }

  function collectFiles() {
    return Object.entries(models).map(([path, m]) => ({ path, content: m.getValue() }));
  }

  async function saveWorkspace(announce) {
    try {
      await fetch("/api/workspace", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ files: collectFiles() }) });
      S.buffers = {}; save();
      document.querySelectorAll(".ftab .dirty").forEach((d) => d.classList.add("hidden"));
      if (announce) { toast("The ink is dry — your pages are safe on disk."); sfx("saved"); }
    } catch (err) { toast("The ink would not take: " + err, "bad"); }
  }

  function termPrint(text, isErr) {
    const out = $("#term-out");
    if (!out) return;
    const span = document.createElement("span");
    span.className = isErr ? "t-err" : "";
    span.textContent = text + "\n";
    out.appendChild(span);
    out.scrollTop = out.scrollHeight;
  }

  async function runProject() {
    const btn = $("#b-run"), sub = $("#b-submit");
    let running = true;
    // the button stays clickable: hovering it flips it into a CANCEL control while the run is live.
    // mousemove (not just mouseenter) because the pointer is already ON the button right after clicking it.
    const started = Date.now();
    btn.textContent = "CASTING...";
    const showCancel = () => { if (running && Date.now() - started > 700) btn.textContent = "BREAK THE CHANT?"; };
    btn.onmouseenter = showCancel;
    btn.onmousemove = showCancel;
    btn.onmouseleave = () => { if (running) btn.textContent = "CASTING..."; };
    btn.onclick = () => { if (running) fetch("/api/runcancel", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }); };
    if (sub) sub.disabled = true;
    clearTimeout(diagTimer); // don't let a queued diagnostics build contend with this run
    termPrint("$ " + runLabel() + "    // " + new Date().toLocaleTimeString());
    S.stats.runs++; save();
    try {
      const stdin = ($("#stdin-box").value || "").replace(/\\n/g, "\n");
      const r = await fetch("/api/run", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ files: collectFiles(), stdin }),
      });
      const data = await r.json();
      S.buffers = {}; save();
      document.querySelectorAll(".ftab .dirty").forEach((d) => d.classList.add("hidden"));
      termPrint(data.output || "(the stone stays silent)", !data.ok);
      termPrint(data.ok ? "── the spell completed, exit 0 ──" : "── the casting failed ──", !data.ok);
      castSigil(null, data.ok); // the workbench run earns the full drawn sigil
    } catch (err) { termPrint("THE STONE CANNOT REACH THE FORGE: " + err, true); }
    running = false;
    btn.onmouseenter = btn.onmousemove = btn.onmouseleave = null;
    btn.onclick = runProject;
    btn.innerHTML = `${ico("play")} CAST THE SPELL`;
    paintSubmitBtn(); // re-enable only if no grade job is in flight
    scheduleDiagnostics(); // the run just built everything — refresh squiggles off the warm cache
  }

  function packageModal(sec) {
    const suggested = sec.freestyle.packages || [];
    modal(`<h2>REAGENTS (NUGET PACKAGES)</h2>
      <p class="dim">Rarer components, measured into your ${esc(projName())} folio via <code>dotnet add package</code>.</p>
      ${suggested.length ? `<p style="font-size:12.5px">The commission calls for: ${suggested.map((p2) => `<code>${esc(p2)}</code>`).join(" ")}</p>` : ""}
      <input type="text" id="pkg-name" style="width:100%" placeholder="${suggested[0] || "Package.Name"}" value="${suggested[0] || ""}">
      <pre id="pkg-out" class="dim" style="font-family:var(--mono);font-size:11px;max-height:160px;overflow:auto;margin-top:10px"></pre>`,
      [["CLOSE THE CABINET", "quiet"]]);
    const actions = $(".modal-actions");
    const installBtn = document.createElement("button");
    installBtn.className = "btn"; installBtn.textContent = "MEASURE IT IN";
    installBtn.onclick = async () => {
      const name = $("#pkg-name").value.trim();
      if (!name) return;
      installBtn.disabled = true; installBtn.textContent = "DECANTING...";
      try {
        const r = await fetch("/api/addpackage", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ package: name }) });
        const data = await r.json();
        $("#pkg-out").textContent = data.output || "";
        toast(data.ok ? `Reagent <b>${esc(name)}</b> is in the folio.` : "The reagent refused the flask — read the residue.", data.ok ? "" : "bad");
      } catch (err) { $("#pkg-out").textContent = String(err); }
      installBtn.disabled = false; installBtn.textContent = "MEASURE IT IN";
    };
    actions.prepend(installBtn);
  }

  // ------------------------------------------------------------ grading
  const gradingJobs = {}; // sectionId -> jobId while a grade is in flight

  function paintSubmitBtn() {
    const b = $("#b-submit");
    if (!b || !fsSection) return;
    const busy = !!gradingJobs[fsSection.id];
    b.disabled = busy;
    b.innerHTML = busy ? `${ico("upload")} BEING JUDGED...` : `${ico("upload")} PRESENT TO ${esc(persona())}`;
  }

  let GRADING_LINES = [
    "your pages are carried up the tower stair...",
    "the work is weighed against the chart...",
    "the judgement is being written...",
  ];

  async function submitForGrading() {
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

  // ------------------------------------------------------------ HEX DEFENSE
  // random hexes: inscribe a real working counter-spell against the sandglass or bleed coin.
  // stdlib-only challenges — the snippet sandbox has no packages.
  let INTRUSION_TIERS = [];  // tomes define [[progression.intrusionTiers]]; none = no hexes

  function intrusionEligible() {
    return S.booted && !$("#modal-root").firstChild && !document.querySelector(".grade-overlay")
      && window.SECTIONS.some((sec) => sec.lessons.some(lessonDone));
  }

  function startIntrusion() {
    const passed = window.SECTIONS.filter(sectionPassed).length;
    const unlocked = INTRUSION_TIERS.filter((t) => t.min <= passed);
    if (!unlocked.length) return;
    const tier = Math.random() < 0.7 ? unlocked[unlocked.length - 1] : unlocked[Math.floor(Math.random() * unlocked.length)];
    const ch = tier.pool[Math.floor(Math.random() * tier.pool.length)];
    sfx("hex"); // the rival's blast streaks in (the alarm toll stands in until the sample decodes)

    const overlay = document.createElement("div");
    overlay.className = "grade-overlay";
    overlay.innerHTML = `<div class="grade-card" style="border-color:var(--bad,#8e2f23)">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:20px">
        <div>
          <div class="faint" style="font-size:11px;letter-spacing:.2em;color:var(--bad,#8e2f23)">✦ A HEX STREAKS TOWARD YOUR STUDY // COUNTER-SPELL REQUIRED</div>
          <h2 style="margin:6px 0 0">${esc(ch.t)}</h2>
          <div class="dim" style="font-size:12.5px;margin-top:4px">${esc(ch.brief)} Inscribe a working counter-spell before the sandglass empties or bleed ${coin()}.</div>
        </div>
        <div class="num" id="hk-clock" style="font-size:26px;font-weight:700"></div>
      </div>
      <div class="lab-expect" style="margin-top:12px"><span class="faint" style="font-size:10.5px;letter-spacing:.14em">THE COUNTER-SPELL MUST UTTER, EXACTLY</span><pre><code></code></pre></div>
      <div class="code-pad"></div>
      <pre class="lab-out hidden"></pre>
      <div class="modal-actions">
        <button class="btn quiet" id="hk-abandon">YIELD (TAKE THE HIT)</button>
        <button class="btn" id="hk-submit">INSCRIBE + CAST</button>
      </div>
    </div>`;
    $(".lab-expect pre code", overlay).textContent = ch.expect;
    document.body.appendChild(overlay);
    let hkEd = null;
    window.GhostEditor.monacoReady.then(() => {
      hkEd = codePad($(".code-pad", overlay), ch.starter, () => $("#hk-submit", overlay).click());
      hkEd.focus();
    });

    const endAt = Date.now() + tier.time * 1000;
    let inFlight = false, expired = false, done = false;
    const clock = $("#hk-clock", overlay);
    const tick = setInterval(() => {
      const left = Math.max(0, endAt - Date.now());
      const s2 = Math.ceil(left / 1000);
      clock.textContent = `${Math.floor(s2 / 60)}:${String(s2 % 60).padStart(2, "0")}`;
      if (s2 <= 10) clock.style.color = "var(--bad, #f43)";
      if (left <= 0) {
        clearInterval(tick);
        expired = true;
        // ponytail: submission in flight at the buzzer still counts — dotnet latency isn't the player's fault
        if (inFlight) clock.textContent = "VERIFYING";
        else finish(false);
      }
    }, 250);

    function finish(won) {
      if (done) return;
      done = true;
      clearInterval(tick);
      castSigil($(".grade-card", overlay) || overlay, won);
      overlay.remove();
      if (won) {
        S.stats.intrusionW = (S.stats.intrusionW || 0) + 1;
        sfx("grade");
        toast(`THE HEX SHATTERS ON YOUR DOORSTEP // <b>+${tier.bounty}</b> ${coin()} bounty.`);
        addCredits(tier.bounty, true);
        grantBadge("first-defense");
      } else {
        S.stats.intrusionL = (S.stats.intrusionL || 0) + 1;
        if (S.inv.firewall > 0) {
          S.inv.firewall--;
          toast(`STRUCK — YOUR WARD ABSORBED IT (${S.inv.firewall} charges left)`, "warn");
        } else {
          const loss = Math.min(S.credits, Math.max(5, Math.round(S.credits * 0.10)));
          S.credits -= loss;
          S.stats.streak = 0;
          updateHud();
          toast(`THE HEX LANDS // <b>-${loss}</b> ${coin()} torn from your purse. Your chant is broken.`, "bad");
        }
        save();
      }
    }

    $("#hk-abandon", overlay).onclick = () => finish(false);
    const bSub = $("#hk-submit", overlay);
    bSub.onclick = async () => {
      if (inFlight || done || (expired && !inFlight)) return;
      inFlight = true;
      bSub.disabled = true; bSub.textContent = "INSCRIBING...";
      const out = $(".lab-out", overlay);
      out.classList.remove("hidden");
      out.textContent = runLabel() + " — the counter-spell takes shape...";
      let data;
      try {
        const r = await fetch("/api/runsnippet", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code: hkEd ? hkEd.getValue() : "", stdin: "" }),
        });
        data = await r.json();
      } catch (err) { data = { ok: false, output: "server error: " + err }; }
      inFlight = false;
      bSub.disabled = false; bSub.textContent = "INSCRIBE + CAST";
      if (done) return;
      const pass = data.ok && normCode(data.output) === normCode(ch.expect);
      if (pass) { finish(true); return; }
      if (expired) { finish(false); return; }
      out.textContent = data.output || "(the stone stays silent)";
      const d = data.ok ? firstDiff(data.output, ch.expect) : null;
      toast(d ? `LINE ${d.line}: expected «${esc(d.expected)}» got «${esc(d.got)}»` : "THE FORGE REJECTED IT — read its complaint, mend, cast again", "warn");
    };
  }

  // ------------------------------------------------------------ SPELL DUEL
  // player-initiated duel: 3:00 sandglass, further demands arm at 1:00 and 2:00, judged
  // against whatever was armed when submit was clicked. No coin for winning — wins bank
  // toward the exclusive earned theme (10 qualifying: max 2 per circle, final circle uncapped).
  // Losing/yielding/timing out forfeits a 20×circle stake and breaks the chant.
  let ATK_TIME = 180;
  let ATK_STAGE_AT = [0, 60, 120]; // seconds elapsed when each directive arms

  const attackDiff = () => Math.min(window.ATTACK_TIERS.length, window.SECTIONS.filter(sectionPassed).length);

  function atkQualifying() {
    let q = 0;
    for (const [d, w] of Object.entries(S.stats.atkWins || {}))
      q += (+d === window.ATTACK_TIERS.length ? w : Math.min(BLACKICE_CAP, w)); // per-difficulty cap, final difficulty uncapped
    return q;
  }

  function initiateAttack() {
    if (document.querySelector(".grade-overlay") || $("#modal-root").firstChild) return;
    const d = attackDiff();
    if (d < 1) { toast("THE WAND STAYS COLD // seal your first chapter before challenging a rival.", "bad"); return; }
    const stake = Math.min(S.credits, ATK_STAKE_PER * d);
    const earnedUnlocked = EARNED_THEME && S.themes[EARNED_THEME.id];
    const prize = (!EARNED_THEME || earnedUnlocked)
      ? `every 2nd victory at this circle pays <b>${ATK_WIN_PER * d}</b> ${coin()}`
      : `${BLACKICE_N} qualifying victories win the <b>${EARNED_THEME.name}</b> ink (${atkQualifying()}/${BLACKICE_N}, at most ${BLACKICE_CAP} counted per circle)`;
    modal(`<h2 style="color:var(--bad)">SPELL DUEL // A RIVAL OF THE ${roman(d)} CIRCLE</h2>
      <p class="dim">3:00 in the sandglass. The rival's first hex strikes at once — two more hexes arm at
      1:00 and 2:00, and your counter is judged against whatever hex is live when you cast. Win: no purse, but
      ${prize}. Lose, yield, or let the glass run out: a <b class="num" style="color:var(--bad)">-${stake}</b> ${coin()} stake
      and your chant breaks. Wards give no shelter in a duel. Once wands are drawn, there is no walking away.</p>`,
      [["DECLINE", "quiet", null], ["DRAW YOUR WAND", "danger", () => startAttack(d, stake)]]);
  }

  function startAttack(d, stake) {
    const tier = window.ATTACK_TIERS[d - 1];
    const ch = tier.pool[Math.floor(Math.random() * tier.pool.length)];
    sfx("hex"); // the rival opens with a hex hurled at your study

    const overlay = document.createElement("div");
    overlay.className = "grade-overlay";
    overlay.innerHTML = `<div class="grade-card" style="border-color:var(--bad,#8e2f23)">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:20px">
        <div>
          <div class="faint" style="font-size:11px;letter-spacing:.2em;color:var(--bad,#8e2f23)">✦ WANDS DRAWN // THE ${roman(d)} CIRCLE // STAKE ${stake}${gp()}</div>
          <h2 style="margin:6px 0 0">${esc(ch.t)}</h2>
          <ol id="atk-objs" class="dim" style="font-size:12.5px;margin:6px 0 0;padding-left:18px">
            <li>${esc(ch.stages[0].brief)}</li>
            <li class="faint">SEALED HEX — arms at T+1:00</li>
            <li class="faint">SEALED HEX — arms at T+2:00</li>
          </ol>
        </div>
        <div class="num" id="atk-clock" style="font-size:26px;font-weight:700"></div>
      </div>
      <div class="lab-expect" style="margin-top:12px"><span class="faint" style="font-size:10.5px;letter-spacing:.14em">THE RIVAL'S HEX — CAST THIS EXACT COUNTER TO TURN IT (CURRENTLY ARMED)</span><pre><code></code></pre></div>
      <div class="code-pad"></div>
      <pre class="lab-out hidden"></pre>
      <div class="modal-actions">
        <button class="btn quiet" id="atk-abandon">YIELD (FORFEIT THE STAKE)</button>
        <button class="btn" id="atk-submit">INSCRIBE + CAST</button>
      </div>
    </div>`;
    const expectEl = $(".lab-expect pre code", overlay);
    expectEl.textContent = ch.stages[0].expect;
    document.body.appendChild(overlay);
    let atkEd = null;
    window.GhostEditor.monacoReady.then(() => {
      atkEd = codePad($(".code-pad", overlay), ch.starter, () => $("#atk-submit", overlay).click());
      atkEd.focus();
    });

    const startAt = Date.now();
    const endAt = startAt + ATK_TIME * 1000;
    const stageAt = (ms) => ms >= ATK_STAGE_AT[2] * 1000 ? 2 : ms >= ATK_STAGE_AT[1] * 1000 ? 1 : 0;
    let shownStage = 0, inFlight = false, expired = false, done = false;
    const clock = $("#atk-clock", overlay);
    const tick = setInterval(() => {
      const st = stageAt(Date.now() - startAt);
      if (st > shownStage) {
        shownStage = st;
        const li = $("#atk-objs", overlay).children[st];
        li.classList.remove("faint");
        li.textContent = ch.stages[st].brief;
        expectEl.textContent = ch.stages[st].expect;
        sfx("hex"); // the rival presses — another hex streaks in
        toast(`THE RIVAL PRESSES THE HEX // a ${st + 1}${st === 1 ? "nd" : "rd"} hex strikes — your counter must grow to turn it`, "warn");
      }
      const left = Math.max(0, endAt - Date.now());
      const s2 = Math.ceil(left / 1000);
      clock.textContent = `${Math.floor(s2 / 60)}:${String(s2 % 60).padStart(2, "0")}`;
      if (s2 <= 10) clock.style.color = "var(--bad, #f43)";
      if (left <= 0) {
        clearInterval(tick);
        expired = true;
        // submission in flight at the buzzer still counts — dotnet latency isn't the player's fault
        if (inFlight) clock.textContent = "VERIFYING";
        else finish(false);
      }
    }, 250);

    function finish(won) {
      if (done) return;
      done = true;
      clearInterval(tick);
      castSigil($(".grade-card", overlay) || overlay, won);
      overlay.remove();
      if (won) {
        S.stats.atkW = (S.stats.atkW || 0) + 1;
        S.stats.atkWins = S.stats.atkWins || {};
        S.stats.atkWins[d] = (S.stats.atkWins[d] || 0) + 1;
        sfx("grade");
        toast(`THE RIVAL LOWERS THEIR WAND // a duel of the ${roman(d)} circle is yours.`);
        const q = atkQualifying();
        if (q >= 1) grantBadge("atk-1");
        if (q >= 5) grantBadge("atk-5");
        if (q >= BLACKICE_N && EARNED_THEME && !S.themes[EARNED_THEME.id]) {
          S.themes[EARNED_THEME.id] = true;
          grantBadge("atk-ice");
          toast(`WON, NOT BOUGHT // <b>${EARNED_THEME.name}</b> — equip it at the peddler's table.`, "warn");
        } else if (EARNED_THEME && S.themes[EARNED_THEME.id] && S.stats.atkWins[d] % 2 === 0) {
          addCredits(ATK_WIN_PER * d); // post-theme trickle: every 2nd win at the current circle pays
        }
        save();
      } else {
        S.stats.atkL = (S.stats.atkL || 0) + 1;
        const loss = Math.min(S.credits, stake);
        S.credits -= loss;
        S.stats.streak = 0;
        updateHud();
        toast(`THE DUEL IS LOST // your <b>-${loss}</b> ${coin()} stake is forfeit. Your chant is broken.`, "bad");
        save();
      }
    }

    $("#atk-abandon", overlay).onclick = () => finish(false);
    const bSub = $("#atk-submit", overlay);
    bSub.onclick = async () => {
      if (inFlight || done || (expired && !inFlight)) return;
      const lockedStage = stageAt(Date.now() - startAt); // judged against what was armed at cast time
      inFlight = true;
      bSub.disabled = true; bSub.textContent = "INSCRIBING...";
      const out = $(".lab-out", overlay);
      out.classList.remove("hidden");
      out.textContent = runLabel() + " — your riposte takes shape...";
      let data;
      try {
        const r = await fetch("/api/runsnippet", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code: atkEd ? atkEd.getValue() : "", stdin: "" }),
        });
        data = await r.json();
      } catch (err) { data = { ok: false, output: "server error: " + err }; }
      inFlight = false;
      bSub.disabled = false; bSub.textContent = "INSCRIBE + CAST";
      if (done) return;
      const expect = ch.stages[lockedStage].expect;
      const pass = data.ok && normCode(data.output) === normCode(expect);
      if (pass) { finish(true); return; }
      if (expired) { finish(false); return; }
      out.textContent = data.output || "(the stone stays silent)";
      const df = data.ok ? firstDiff(data.output, expect) : null;
      toast(df ? `LINE ${df.line}: expected «${esc(df.expected)}» got «${esc(df.got)}»` : "THE FORGE REJECTED IT — read its complaint, mend, cast again", "warn");
    };
  }

  // ------------------------------------------------------------ SHOP
  function renderShop() {
    const v = $("#view-shop");
    v.classList.remove("hidden");
    v.innerHTML = `
      <div class="crumb"><button data-nav="home">LEDGER</button> / THE PEDDLER</div>
      <h1>THE PEDDLER'S WARES</h1>
      <p class="dim">A hooded figure spreads a cloth of curiosities across the corner of your table. Spend the ${coin()} your trials have earned. No refunds — the peddler has already forgotten your face.</p>
      <div class="shop-grid cascade">
        ${SHOP.map((item, i) => {
          const owned = item.kind === "theme" ? S.themes[item.theme] : null;
          const invCount = item.kind === "consumable" ? (S.inv[item.id] || 0) : 0;
          const active = item.kind === "theme" && S.theme === item.theme;
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
        ${EARNED_THEME ? `<div class="shop-item" style="--i:${SHOP.length};${S.themes[EARNED_THEME.id] ? "" : "opacity:.55"}">
          ${ico(S.themes[EARNED_THEME.id] ? "ink" : "lock", "s-ico")}
          <span class="s-name">${esc(EARNED_THEME.name)}</span>
          ${S.themes[EARNED_THEME.id]
            ? `<button class="btn ${S.theme === EARNED_THEME.id ? "quiet" : "ghost"}" data-equip="${esc(EARNED_THEME.id)}" ${S.theme === EARNED_THEME.id ? "disabled" : ""}>${S.theme === EARNED_THEME.id ? "IN USE" : "USE THIS INK"}</button>`
            : `<button class="btn ghost" disabled>NOT FOR SALE</button>`}
          <span class="s-desc">${S.themes[EARNED_THEME.id]
            ? esc(EARNED_THEME.desc || "")
            : `The peddler will not name a price. Win ${BLACKICE_N} qualifying SPELL DUELS to claim it (at most ${BLACKICE_CAP} counted per circle). Progress: ${atkQualifying()}/${BLACKICE_N}.`}</span>
        </div>` : ""}
      </div>`;
    $("[data-nav=home]", v).onclick = () => go("home");
    v.querySelectorAll("[data-buy]").forEach((b) => (b.onclick = () => {
      const item = SHOP.find((x) => x.id === b.dataset.buy);
      modal(`<h2>BUY ${esc(item.name)}?</h2><p class="dim">${item.desc}</p><p>The peddler asks <b class="num">${item.cost}</b>${gp()} — your purse holds <span class="num">${S.credits}</span>${gp()}.</p>`,
        [["WALK AWAY", "quiet"], ["SHAKE ON IT", "", () => {
          if (!spend(item.cost)) return;
          if (item.kind === "theme") { S.themes[item.theme] = true; toast(`The ink and vellum are yours. Put them to use from the peddler's table.`); }
          else { S.inv[item.id] = (S.inv[item.id] || 0) + (item.charges || 1); toast(`<b>${esc(item.name)}</b> slipped into your satchel.`); }
          sfx("buy");
          save(); renderShop();
        }]]);
    }));
    v.querySelectorAll("[data-equip]").forEach((b) => (b.onclick = () => {
      S.theme = b.dataset.equip;
      document.body.dataset.theme = S.theme;
      window.GhostEditor.setTheme(S.theme);
      refreshCoins();
      save(); renderShop();
    }));
  }

  // ------------------------------------------------------------ pop menus
  // Custom dropdowns + context menu. Animate: unfurl top→bottom in, retract bottom→top out.
  let popOpen = null; // { el, owner, onClose }
  function closePop(instant) {
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

  // ------------------------------------------------------------ spell sigils
  // every cast spells 3–6 letters of the Standard Galactic Alphabet — the
  // enchanters' script — out of semi-stable arcane motes that strain against
  // the binding, charging white-hot for ~3s, then dissipate in ONE release: each
  // mote drifts straight out from its letter's heart, breaking into smaller
  // shards as it fades. every mote lights itself; there is no candle-glow
  // here. a miscast charges the same — same letters, same colour — then the
  // binding breaks: it greys and falls as ash.
  // transform/opacity only; gated by the same preference as the candle embers.
  // strokes live on a ~3.4x6 grid (y down); a 1-point stroke is a heavy dot.
  // every knob below (particles AND sound) is tuned by global-configs/sigil.toml — these
  // are the fallback defaults when the file or a key is missing.
  const SIG = {
    letters: { minimum: 3, maximum: 6, scale: 28, spacing: .3 },
    palette: { hue_minimum: 200, hue_maximum: 320, saturation: 85, saturation_miscast: 30 },
    motes: { size_minimum: 4, size_maximum: 6, dot_size: 10, glow: 3 },
    charge: { total_milliseconds: 4000, release_fraction: .75, poses_minimum: 18, poses_maximum: 22, shake: 7, grow: .25 },
    halo: { size: 6, peak_opacity: 1 },
    burst: { distance_minimum: 160, distance_maximum: 400, shards: 2, shard_size: .45 },
    sound: { enabled: true, volume: 100, charge_hertz_from: 110, charge_hertz_to: 440, shimmer: .5, burst_gain: .6, miscast: true },
    fail: { charge_milliseconds: 1100, start: .9, tail: 1.1, gain: 2, fade: .3 }, // miscast: charge_milliseconds, then the break, then how cast-fail.mp3 is played
  };
  window.SIGIL_CFG = SIG; // console-reachable: poke values live, then castSigil()
  // a just-enough TOML reader — [section], key = number | bool | "string" | [array].
  // shared by sigil.toml and particles.toml. sections merge onto the target object,
  // so a partial file overrides only the keys it names; the rest keep their defaults.
  function readToml(txt, into) {
    const val = (raw) => {
      raw = raw.trim();
      if (raw === "true") return true;
      if (raw === "false") return false;
      if (raw[0] === '"') return raw.slice(1, -1);
      if (raw[0] === "[") return raw.slice(1, -1).split(",").map(val).filter((x) => x !== "" && !(typeof x === "number" && Number.isNaN(x)));
      const n = parseFloat(raw);
      return Number.isNaN(n) ? raw : n;
    };
    let sec = null;
    for (let line of txt.split("\n")) {
      line = line.replace(/^\s*#.*$/, "").replace(/\s#.*$/, "").trim(); // drop # comments, but not the # inside "quoted" hex colors
      if (!line) continue;
      const h = line.match(/^\[(.+)\]$/);
      if (h) { sec = into[h[1]] = into[h[1]] || {}; continue; }
      const kv = line.match(/^([\w-]+)\s*=\s*(.+)$/);
      if (kv && sec) sec[kv[1]] = val(kv[2]);
    }
    return into;
  }
  const loadToml = (file, into) => fetch(file).then((r) => r.text()).then((t) => readToml(t, into)).catch(() => {}); // missing file: baked defaults stand
  loadToml("global-configs/sigil.toml", SIG);
  const GALACTIC = {
    a: [[[0, 6], [1.1, 6], [1.1, 1.5], [1.5, .4], [2.5, .4], [3, 1.1], [3, 2.5]]],
    b: [[[1.4, 0], [1.4, 1.4], [3.4, 4.9], [0, 4.9]]],
    c: [[[1.6, .5]], [[1, 2.7], [1.6, 2.1], [1.6, 6]]],
    d: [[[.2, .4], [2.8, .4]], [[.2, 1.3], [3.3, 3.1]]],
    e: [[[.6, .3], [.6, 5], [3, 5]], [[2.8, .6]]],
    f: [[[0, .4], [3.2, .4]], [[.4, 1.7]], [[1.6, 1.7]], [[2.8, 1.7]]],
    g: [[[2.1, .3], [2.1, 5.7]], [[.6, 3], [2.1, 3]]],
    h: [[[0, .4], [3.4, .4]], [[.4, 1.7], [3, 1.7]], [[1.7, 1.7], [1.7, 5.6]]],
    i: [[[1.7, 0], [1.7, 2.2]], [[1.7, 3.5], [1.7, 5.7]]],
    j: [[[1.7, 0], [1.7, 1]], [[1.7, 2.1], [1.7, 3.1]], [[1.7, 4.2], [1.7, 6]]],
    k: [[[1.7, .2], [1.7, 5.6]], [[.4, 2.9]], [[3, 2.9]]],
    l: [[[.9, .2], [.9, 5.6]], [[2.7, 1.5]], [[2.7, 3.3]]],
    m: [[[.6, .5]], [[3, .3], [3, 4.9], [.7, 4.9]]],
    n: [[[.6, .6]], [[2.9, .4], [2.6, 1.6], [1, 5.8]]],
    o: [[[.2, .4], [2.9, .4], [.9, 5.7]]],
    p: [[[.8, .6]], [[.8, 1.9], [.8, 5.7]], [[2.6, .2], [2.6, 4]], [[2.6, 5.5]]],
    q: [[[2, .5]], [[1.8, 1.8], [.5, 1.8], [.5, 5.6], [3.2, 5.6]]],
    r: [[[.6, 1.6]], [[2.8, 1.6]], [[.6, 3.7]], [[2.8, 3.7]]],
    s: [[[2.4, .3], [2.4, 2.5], [1, 3.4], [1, 5.7]]],
    t: [[[.3, .4], [2.9, .4], [2.9, 2.8]], [[2.9, 4.8]]],
    u: [[[1.5, .4]], [[2.7, .4]], [[.2, 2.1], [3.2, 2.1]], [[.2, 3.7], [3.2, 3.7]]],
    v: [[[1.7, .4], [1.7, 3]], [[.6, 3], [2.8, 3]], [[.2, 4.6], [3.2, 4.6]]],
    w: [[[1.7, 1.6]], [[.4, 3.6]], [[3, 3.6]]],
    x: [[[.6, .8]], [[2.9, .8], [.9, 5.6]]],
    y: [[[1, .4], [1, 5.6]], [[2.4, .4], [2.4, 5.6]]],
    z: [[[.5, 5.6], [.5, 1.5], [1.7, .3], [2.9, 1.5], [2.9, 5.6]]],
  };
  // verdict/cursor motes: a burst of short-lived divs, tinted and thrown by the material struck.
  // ponytail: ~a dozen–thirty per burst, removed on finish; cap concurrency if click-spam ever bites.
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
  let lastCastAt = null; // where the CAST button sat when pressed — the burst's anchor if the verdict re-renders it away
  const PCL = {
    pick:    { count: 7,  colors: ["var(--ac-dim)", "#e3c059"], size: [2, 4], rise: 30, spread: 30, drift: -14, glow: 1, round: 1, lifetime_milliseconds: 620, easing: "cubic-bezier(.2,.6,.3,1)" }, // an enchanted glint
    click:   { count: 5,  colors: ["#fff8e2", "var(--bg3)", "var(--line-hi)"], size: [1.5, 3.5], rise: 16, spread: 34, drift: 8, glow: 0, round: 1, lifetime_milliseconds: 720, easing: "cubic-bezier(.2,.6,.3,1)" }, // disturbed dust
    wood:    { count: 6,  colors: ["#8a5a24", "#6b4413", "#3d2b17"], size: [1.5, 3.5], rise: 8, spread: 26, drift: 34, glow: 0, round: 0, lifetime_milliseconds: 560, easing: "cubic-bezier(.4,0,.7,1)" }, // chips that fall
    stone:   { count: 8,  colors: ["#b9b9c0", "#8f8f98", "#6f6f76"], size: [1.5, 3.5], rise: 10, spread: 30, drift: 40, glow: 0, round: 0, lifetime_milliseconds: 600, easing: "cubic-bezier(.4,0,.7,1)" }, // pale granite chips struck off the slab, falling
    cast:    { count: 46, colors: ["#7c3aed", "#4f46e5", "#a21caf", "#c026d3", "#d946ef"], size: [3.5, 8], mode: "radial", distance: [16, 118], glow: 1, round: 1, start_opacity: 1, lifetime_milliseconds: 780, easing: "cubic-bezier(.1,.75,.3,1)" }, // a true cast: a dense spray of vivid arcane motes blasts out in every direction
    miscast: { count: 30, colors: ["#8b6fb0", "#6f6a94", "#a98a6b", "#7d6f86"], size: [3, 6.5], mode: "fall", spread: 40, rise: 26, drift: 52, glow: 1, round: 1, start_opacity: .9, lifetime_milliseconds: 1000, easing: "cubic-bezier(.35,.02,.7,1)" }, // a miscast: dimmed arcane motes rain down and fade, the working coming apart
  };
  function burst(x, y, kind) {
    if (reducedMotion.matches) return;
    const spec = PCL[kind]; if (!spec) return;
    for (let index = 0; index < spec.count; index++) {
      const particle = document.createElement("div");
      particle.className = "pcl";
      const size = spec.size[0] + Math.random() * (spec.size[1] - spec.size[0]);
      const color = spec.colors[(Math.random() * spec.colors.length) | 0];
      particle.style.cssText = `left:${x}px;top:${y}px;width:${size}px;height:${size}px;` +
        (spec.glow ? `background:radial-gradient(circle,${color},transparent 70%);border-radius:50%;`
                   : `background:${color};border-radius:${spec.round ? "50%" : "1px"};`);
      let offsetX, offsetY;
      if (spec.mode === "radial") {                    // blast out in every direction from the heart
        const angle = Math.random() * Math.PI * 2, flightDistance = spec.distance[0] + Math.random() * (spec.distance[1] - spec.distance[0]);
        offsetX = Math.cos(angle) * flightDistance; offsetY = Math.sin(angle) * flightDistance;
      } else if (spec.mode === "fall") {               // sink and fade — the binding comes apart
        offsetX = (Math.random() - 0.5) * spec.spread * 2;
        offsetY = spec.rise * (0.4 + Math.random()) + spec.drift;
      } else {                                          // the fan: dust lifts, chips fall
        offsetX = (Math.random() - 0.5) * spec.spread * 2;
        offsetY = -spec.rise * (0.4 + Math.random()) + spec.drift;
      }
      document.body.appendChild(particle);
      particle.animate(
        [{ transform: "translate(-50%,-50%) scale(1)", opacity: spec.start_opacity ?? 0.9 },
         { transform: `translate(calc(-50% + ${offsetX}px), calc(-50% + ${offsetY}px)) scale(.4)`, opacity: 0 }],
        { duration: spec.lifetime_milliseconds + Math.random() * 200, easing: spec.easing, fill: "forwards" }
      ).onfinish = () => particle.remove();
    }
  }
  loadToml("global-configs/particles.toml", PCL); // cast/miscast (and pick/click/wood) burst knobs, tweakable without a rebuild
  const AUD = {}; loadToml("global-configs/audio.toml", AUD).then(() => window.GhostAudio && GhostAudio.configure(AUD)); // sound knobs, same deal

  function castSigil(anchor, ok) {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    // always cast at the true center of the screen; the anchor arg is ignored
    // (ponytail: kept in the signature so the call sites don't need touching)
    const cs = getComputedStyle(document.body);
    // arcane palette: sky-blue → indigo → violet → magenta, one hue per mote;
    // light parchment takes deep inks, dark pages take bright self-lit motes
    const chan = (cs.getPropertyValue("--bg1").match(/[0-9a-f]{2}/gi) || []).slice(0, 3).map((h) => parseInt(h, 16));
    const lightBg = chan.reduce((a2, b2) => a2 + b2, 0) > 380;
    const arcane = (sat) => {
      const hue = (SIG.palette.hue_minimum + Math.random() * (SIG.palette.hue_maximum - SIG.palette.hue_minimum)).toFixed(0);
      return {
        fill: `hsl(${hue} ${sat}% ${(lightBg ? 30 + Math.random() * 12 : 62 + Math.random() * 16).toFixed(0)}%)`,
        glow: `hsl(${hue} ${sat}% ${lightBg ? 46 : 72}% / .85)`,
      };
    };
    const keys = Object.keys(GALACTIC);
    const word = []; // min–max distinct letters; a miscast musters only one
    const nL = Math.min(26, SIG.letters.minimum + Math.floor(Math.random() * (SIG.letters.maximum - SIG.letters.minimum + 1))); // a miscast musters the same letters — it just fails to hold them
    for (let i = 0; i < nL; i++)
      word.push(GALACTIC[keys.splice(Math.floor(Math.random() * keys.length), 1)[0]]);
    // px per grid unit → letters stand ~6x this tall, squeezed to fit narrow studies
    const SC = Math.min(SIG.letters.scale, (innerWidth - 60) / (word.length * 3.4 + (word.length - 1) * 1.8));
    const GW = 3.4 * SC, GAP = SC * 1.8, W = word.length * GW + (word.length - 1) * GAP;
    const cx = Math.max(W / 2 + 16, Math.min(innerWidth / 2, innerWidth - W / 2 - 16));
    const cy = Math.max(3 * SC + 16, Math.min(innerHeight / 2, innerHeight - 3 * SC - 16));
    const root = document.createElement("div");
    root.className = "sigil";
    root.style.cssText = `left:${cx}px;top:${cy}px`;
    document.body.appendChild(root);
    const failMs = SIG.fail.charge_milliseconds || 1100;       // miscast: charge this long, then the binding breaks
    const E = ok ? SIG.charge.total_milliseconds : failMs + 1300; // whole life: gather → charge → release/fail → dissipate/fall
    const REL = ok ? SIG.charge.release_fraction : failMs / E;  // the fraction where the working lets go — or snaps
    if (window.GhostAudio) GhostAudio.sigilCast(ok, { ...SIG.sound, fail: SIG.fail, charge_seconds: E * REL / 1000 });
    const piece = (cls, css) => {
      const p = document.createElement("div");
      p.className = cls;
      p.style.cssText = css;
      root.appendChild(p);
      return p;
    };
    const kill = (anim, el2) => { anim.onfinish = () => el2.remove(); };
    const C = "translate(-50%,-50%)"; // every piece self-centers on its left/top
    // semi-stable: a bound mote never quite sits still — a fresh strained pose per keyframe
    const strain = (amp, grow) =>
      `${C} translate(${((Math.random() - .5) * amp).toFixed(1)}px,${((Math.random() - .5) * amp).toFixed(1)}px) scale(${grow})`;

    word.forEach((strokes, li) => {
      const gx = -W / 2 + GW / 2 + li * (GW + GAP); // this letter's heart, relative to root
      // walk each stroke, seeding a mote every `spacing` grid units; lone points are heavy dots
      const pts = [];
      for (const st of strokes) {
        if (st.length === 1) { pts.push([st[0][0], st[0][1], 1]); continue; }
        for (let s2 = 1; s2 < st.length; s2++) {
          const [x1, y1] = st[s2 - 1], [x2, y2] = st[s2];
          const steps = Math.max(1, Math.round(Math.hypot(x2 - x1, y2 - y1) / SIG.letters.spacing));
          for (let k = s2 > 1 ? 1 : 0; k <= steps; k++)
            pts.push([x1 + (x2 - x1) * k / steps, y1 + (y2 - y1) * k / steps, 0]);
        }
      }
      for (const [px2, py2, dot] of pts) {
        const hx = gx + (px2 - 1.7) * SC, hy = (py2 - 3) * SC;
        const sz = dot ? SIG.motes.dot_size : SIG.motes.size_minimum + Math.random() * (SIG.motes.size_maximum - SIG.motes.size_minimum);
        const { fill, glow } = arcane(SIG.palette.saturation); // a miscast starts at the true colour and greys as it falls
        const p = piece("sigil-p", `left:${hx.toFixed(1)}px;top:${hy.toFixed(1)}px;width:${sz.toFixed(1)}px;height:${sz.toFixed(1)}px;background:${fill};box-shadow:0 0 ${(sz * SIG.motes.glow).toFixed(0)}px ${glow}`);
        // keyframe timeline: gather 0–.08 · strain + charge .08–REL · then the
        // working either releases (dissipate) or, on a miscast, snaps (fall).
        // Same charge for both — same letters, same colour — it just fails to hold.
        // NB: options-level easing would warp the WHOLE timeline (WAAPI, unlike
        // CSS), crushing the hold — so every segment eases on its own keyframe
        const frames = [
          { transform: `${C} translate(${((Math.random() - .5) * 50).toFixed(1)}px,${((Math.random() - .5) * 50).toFixed(1)}px) scale(.2)`, opacity: 0, easing: "cubic-bezier(.2,.6,.3,1)" },
          { transform: C, opacity: .9, offset: .08, easing: "ease-in-out" },
        ];
        // the unstable hold: ~20 strained poses per mote, each on its own
        // slightly shifted clock so the letter seethes instead of stepping in
        // unison — and everything escalates with the charge: wider throws,
        // deeper flicker, swelling size, quickening tempo (poses cluster late)
        const nj = SIG.charge.poses_minimum + Math.floor(Math.random() * (SIG.charge.poses_maximum - SIG.charge.poses_minimum + 1));
        // the unstable hold. a miscast caps intensity (gi) at ~60% so it never
        // looks fully bound; the timing still runs the whole hold either way.
        // NB WAAPI needs non-decreasing offsets — with a short charge (small REL)
        // the per-pose jitter can outrun the gap between poses and reverse one,
        // which makes animate() throw and the sigil vanish. clamp each offset to
        // the previous so it can't go backwards. (charge floor ~150ms: below that
        // REL < the .08 gather and even the clamp can't order it — nobody charges
        // that fast.) ponytail: clamp is enough for any sane fail_ms/charge.
        let prevOff = .08;
        for (let j = 1; j <= nj; j++) {
          const g2 = j / nj; // how deep into the hold — timing scales off this
          const gi = ok ? g2 : Math.min(g2, .6); // charge intensity — capped on a miscast
          prevOff = Math.min(REL, Math.max(prevOff, .08 + Math.pow(g2, .7) * (REL - .08) + (j < nj ? (Math.random() - .5) * .012 : 0)));
          frames.push({
            transform: strain(2 + gi * SIG.charge.shake + Math.random() * 2, 1 + gi * SIG.charge.grow),
            opacity: (ok && j === nj) ? 1 : .95 - Math.random() * (.15 + gi * .5),
            offset: prevOff,
            easing: j === nj ? "ease-out" : "ease-in-out",
          });
        }
        if (ok) {
          // ONE release, every mote on the same clock: each drifts straight out
          // from the letter's heart — top rises, bottom sinks, flanks slide wide
          const a2 = Math.atan2(hy, hx - gx) + (Math.random() - .5) * .35;
          const d2 = SIG.burst.distance_minimum + Math.random() * (SIG.burst.distance_maximum - SIG.burst.distance_minimum);
          const dx = Math.cos(a2) * d2, dy = Math.sin(a2) * d2;
          frames.push({ transform: `${C} translate(${dx.toFixed(0)}px,${dy.toFixed(0)}px) scale(.3)`, opacity: 0 });
          kill(p.animate(frames, { duration: E, fill: "both" }), p);
          // the white halo BEHIND each mote: a soft radial glow that charges from
          // nothing to bright through the binding, peaks at release, dies after
          const wg = piece("sigil-p", `left:${hx.toFixed(1)}px;top:${hy.toFixed(1)}px;width:${(sz * SIG.halo.size).toFixed(1)}px;height:${(sz * SIG.halo.size).toFixed(1)}px;background:radial-gradient(circle, rgba(255,255,255,.95), rgba(255,255,255,0) 70%);box-shadow:0 0 ${(sz * SIG.halo.size * 1.5).toFixed(0)}px rgba(255,255,255,.6)`);
          root.insertBefore(wg, p); // halo sits under its mote, never over it
          kill(wg.animate([
            { transform: `${C} scale(.25)`, opacity: 0 },
            { transform: `${C} scale(.35)`, opacity: .08, offset: .08, easing: "ease-in-out" },
            { transform: `${C} scale(.75)`, opacity: .5 * SIG.halo.peak_opacity, offset: (.08 + REL) / 2, easing: "ease-in-out" }, // clearly aglow by mid-charge
            { transform: `${C} scale(1.15)`, opacity: SIG.halo.peak_opacity, offset: REL, easing: "ease-out" },
            { transform: `${C} scale(2.2)`, opacity: 0, offset: REL + (1 - REL) * .72 },
            { transform: `${C} scale(2.2)`, opacity: 0 },
          ], { duration: E, fill: "both" }), wg);
          // mid-flight the mote breaks up: smaller shards peel off where the
          // parent has thinned (~30% of the road out) and scatter on their own.
          // ~1000 animated motes on a 6-letter cast — thin this loop first if a
          // weaker study ever stutters
          for (let s3 = 0; s3 < SIG.burst.shards; s3++) {
            const a3 = a2 + (Math.random() - .5) * .8, d3 = d2 * (.4 + Math.random() * .5);
            const sz3 = sz * SIG.burst.shard_size * (.8 + Math.random() * .4);
            const sx = dx * .36 + Math.cos(a3) * d3, sy = dy * .36 + Math.sin(a3) * d3;
            const sh = piece("sigil-p", `left:${hx.toFixed(1)}px;top:${hy.toFixed(1)}px;width:${sz3.toFixed(1)}px;height:${sz3.toFixed(1)}px;background:${fill};box-shadow:0 0 ${(sz3 * SIG.motes.glow).toFixed(0)}px ${glow}`);
            kill(sh.animate([
              { transform: C, opacity: 0 },
              { transform: `${C} translate(${(dx * .32).toFixed(0)}px,${(dy * .32).toFixed(0)}px)`, opacity: 0, offset: REL + (1 - REL) * .28 },
              { transform: `${C} translate(${(dx * .36).toFixed(0)}px,${(dy * .36).toFixed(0)}px)`, opacity: .85, offset: REL + (1 - REL) * .4, easing: "ease-out" },
              { transform: `${C} translate(${sx.toFixed(0)}px,${sy.toFixed(0)}px) scale(.4)`, opacity: 0 },
            ], { duration: E, fill: "both" }), sh);
          }
        } else {
          // the binding snaps at REL: one last flail, then the letter loses its
          // hold and falls as ash — every mote off the same charge, so they break
          // together, then scatter down on their own
          frames.push({ transform: strain(8, .9), opacity: .55, offset: REL + (1 - REL) * .18, easing: "cubic-bezier(.4,.1,.7,.4)" }); // the grip slips — shrinks and dims, doesn't surge
          frames.push({ transform: strain(5, .95), opacity: .4, offset: REL + (1 - REL) * .42, easing: "ease-in" });
          frames.push({ transform: `${C} translate(${((Math.random() - .5) * 34).toFixed(1)}px,${(40 + Math.random() * 55).toFixed(1)}px) scale(.3)`, opacity: 0 });
          kill(p.animate(frames, { duration: E, fill: "both" }), p);
          // greys as it falls: the true colour holds through the charge, then
          // desaturates to the miscast tint by the time it hits the floor
          p.animate([
            { filter: "saturate(1)" },
            { filter: "saturate(1)", offset: REL, easing: "ease-in" },
            { filter: `saturate(${(SIG.palette.saturation_miscast / SIG.palette.saturation).toFixed(2)})` },
          ], { duration: E, fill: "both" });
        }
      }
    });
    setTimeout(() => root.remove(), E + 800); // sweep whatever the onfinishes missed
  }
  window.castSigil = castSigil; // console-reachable: lets you audition a palette's sigil colors

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
    ], r.left, r.top);
  };

  function popMenu(items, x, y, minW) {
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
  function enhanceSelect(sel) {
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
        on: () => {
          if (sel.selectedIndex === i) return;
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

  // ------------------------------------------------------------ study settings
  function showStudySettings() {
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

  // ------------------------------------------------------------ boot
  let BOOT_LINES = [
    "A match is struck. The candle takes the flame.",
    "The tome on the desk falls open to where you left it.",
    "Take up your quill.",
  ];

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
    S.booted = true; save();
  }

  // ------------------------------------------------------------ init
  async function init() {
    await window.tomeReady;   // the active tome's data must be present before we render
    applyTomeConfig();
    await loadState();
    document.body.dataset.theme = S.theme || (window.TOME.defaults && window.TOME.defaults.theme) || "vellum";
    refreshCoins();   // the HUD purse is inked in index.html; re-ink it for the active palette
    window.GhostEditor.boot(() => {
      const out = {};
      for (const [p2, m] of Object.entries(models)) out[p2] = m.getValue();
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
    $("#obj-satchel").onclick = () => go("shop");
    $("#obj-letter").onclick = () => go("home");
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

    // audio: init prefs, start the hearthfire on the first user gesture (autoplay policy)
    if (window.GhostAudio) {
      GhostAudio.init(S.audio);
      const kick = () => { GhostAudio.userGesture(); document.removeEventListener("pointerdown", kick); document.removeEventListener("keydown", kick); };
      document.addEventListener("pointerdown", kick);
      document.addEventListener("keydown", kick);
      // warm the audio stream on the first mouse MOVEMENT, so it's open before the first click
      const warm = () => { GhostAudio.userGesture(); if (GhostAudio.running()) document.removeEventListener("pointermove", warm); };
      document.addEventListener("pointermove", warm);
      const bAmb = $("#hud-ambience"), bSfx = $("#hud-sfx");
      const paint = () => {
        bAmb.style.opacity = S.audio.ambience ? "1" : ".35";
        bSfx.style.opacity = S.audio.sfx ? "1" : ".35";
        bAmb.title = S.audio.ambience ? "The hearthfire crackles (click to bank it)" : "The hearthfire is banked (click to stoke it)";
        bSfx.title = S.audio.sfx ? "The study makes its little sounds" : "The study is silent";
      };
      bAmb.onclick = () => { S.audio.ambience = !S.audio.ambience; GhostAudio.setAmbience(S.audio.ambience); paint(); save(); };
      bSfx.onclick = () => { S.audio.sfx = !S.audio.sfx; paint(); save(); if (S.audio.sfx) GhostAudio.sfx("tick"); };
      paint();
    }

    applyPen(); // set the handwritten-ink body classes + code-editor font from saved prefs

    // candle embers: the flame sheds warm motes that drift up and die
    const flameEl = document.querySelector("#candle .c-flame");
    const reduced = matchMedia("(prefers-reduced-motion: reduce)");
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
    }, 640);

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
        lastCastAt = { x: r.left + r.width / 2, y: r.top + r.height / 2 };
      }
      else if (t.closest("#term, .forge-log")) kind = "stone"; // the speaking stone & the forge log box: a mineral tap, chips fly
      else if (t.closest("#parchment")) kind = "click";     // anywhere on the parchment
      else if (t.closest(".modal, .grade-card")) kind = "click"; // a parchment card (bindery / forge / grade) — dust like the page, buttons included
      else if (t.closest("button")) { kind = "click"; material = false; } // HUD buttons OUTSIDE parchment: tick only (before the wood catch, so the header bar's buttons don't knock)
      else if (t.closest("#table, #hud")) kind = "wood";    // the wooden desk — incl. the header strip above the parchment (title + empty space)
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
        if (S.nav.view === "freestyle" && Object.keys(models).length) saveWorkspace(true);
        else toast("No scroll is unrolled — there is nothing to blot.", "warn");
      }
    }, true);

    // typing SFX: one delegated listener covers drill boxes, inputs, and Monaco's inputarea.
    // capture phase — Monaco stopPropagation()s command keys (Backspace etc.) before they'd bubble here
    document.addEventListener("keydown", (e) => {
      if (!S.audio.sfx || !window.GhostAudio) return;
      const t = e.target;
      if (!t.matches || !t.matches("textarea, input[type=text]")) return;
      if (e.key.length === 1 || ["Enter", "Backspace", "Tab", "Delete"].includes(e.key)) GhostAudio.keyclick(e.key);
    }, true);

    if (!S.booted) await bootSequence();
    $("#shell").classList.remove("hidden");

    // hex scheduler: one rival's hex per ~10-15 min of visible, active study
    const intrusionDelay = () => (600 + Math.random() * 300) * 1000;
    let intrusionNextAt = Date.now() + intrusionDelay();
    setInterval(() => {
      if (document.hidden) { intrusionNextAt = Math.max(intrusionNextAt, Date.now() + 60000); return; }
      if (Date.now() < intrusionNextAt || !intrusionEligible()) return;
      intrusionNextAt = Date.now() + intrusionDelay();
      if (S.inv.vpn > 0) {
        S.inv.vpn--;
        sfx("tick");
        toast(`Your CLOAK OF UNSEEING turned a rival's hex aside (${S.inv.vpn} charges left)`, "warn");
        save();
        return;
      }
      startIntrusion();
    }, 30000);

    const nav = S.nav || { view: "home" };
    const validSec = nav.sec && secById(nav.sec);
    if (nav.view === "lesson" && validSec && validSec.lessons.some((l) => l.id === nav.lesson)) go("lesson", nav.sec, nav.lesson);
    else if ((nav.view === "section" || nav.view === "freestyle") && validSec) go(nav.view, nav.sec);
    else if (nav.view === "shop") go("shop");
    else go("home");

    // health check
    try {
      const h = await (await fetch("/api/health")).json();
      const rtName = (window.TOME.runtime && window.TOME.runtime.name) || "custom";
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
          const st = await (await fetch("/api/buildtome/status?id=" + encodeURIComponent(hint))).json();
          if (st.status === "done") toast(`The bindery finished <b>${esc(st.name || st.tome || "your tome")}</b> — it waits on the shelf.`, "warn");
          else if (st.status === "error") toast("The last working in the bindery failed — its partial pages remain in /tomes.", "bad");
        } catch { /* server unreachable; the shelf will tell them later */ }
        localStorage.removeItem("buildJob");
      }
    });
  }

  init();
})();

/* ---- global tooltips: every [title] becomes a themed parchment scrap ---- */
(() => {
  const tip = document.createElement("div");
  tip.id = "tip";
  document.body.appendChild(tip);
  let timer = 0, current = null, armed = null;

  // Move title -> data-tip so the native tooltip never appears; re-reads on every
  // hover, so code that reassigns el.title keeps working untouched.
  const text = (el) => {
    if (el.hasAttribute("title")) {
      const t = el.getAttribute("title");
      el.dataset.tip = t;
      el.removeAttribute("title");
      if (!el.hasAttribute("aria-label") && !el.textContent.trim()) el.setAttribute("aria-label", t);
    }
    return el.dataset.tip || "";
  };

  function show(el) {
    const t = text(el);
    if (!t) return;
    current = el;
    tip.textContent = t;
    tip.classList.remove("below", "show");
    tip.style.left = "0px"; tip.style.top = "0px"; // measure unclamped
    const r = el.getBoundingClientRect();
    const w = tip.offsetWidth, h = tip.offsetHeight;
    const cx = r.left + r.width / 2;
    const x = Math.max(8, Math.min(cx - w / 2, innerWidth - w - 8));
    let y = r.top - h - 9;
    if (y < 8) { y = r.bottom + 9; tip.classList.add("below"); }
    tip.style.left = x + "px"; tip.style.top = y + "px";
    tip.style.setProperty("--tip-x", Math.max(10, Math.min(cx - x, w - 10)) + "px");
    tip.classList.add("show");
  }

  function hide() {
    clearTimeout(timer);
    current = armed = null;
    tip.classList.remove("show");
  }

  document.addEventListener("mouseover", (e) => {
    const el = e.target.closest("[title], [data-tip]");
    if (!el || el === current || el === armed) return;
    clearTimeout(timer);
    armed = el;
    timer = setTimeout(() => show(el), 350);
  });
  document.addEventListener("mouseout", (e) => {
    const el = e.target.closest("[title], [data-tip]");
    if (el && !el.contains(e.relatedTarget)) hide();
  });
  document.addEventListener("focusin", (e) => {
    const el = e.target.closest("[title], [data-tip]");
    if (el) show(el);
  });
  document.addEventListener("focusout", hide);
  document.addEventListener("mousedown", hide);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") hide(); });
  addEventListener("scroll", hide, true);
})();
