/* Tome config — every tunable the active Tome may override, plus the neutral fallbacks.
   Importing this installs the tome-scoping fetch shim. */
import { $ } from "./dom.js";
import { S } from "./state.js";

// every /api/* request is transparently scoped to the active tome
export const TID = () => (window.tid ? window.tid() : "verisearch");
const _fetch = window.fetch.bind(window);
window.fetch = (url, opts) => {
  if (typeof url === "string" && url.startsWith("/api/") && !/[?&]tome=/.test(url)) {
    url += (url.includes("?") ? "&" : "?") + "tome=" + encodeURIComponent(TID());
  }
  return _fetch(url, opts);
};

// ------------- tome config: neutral fallbacks only — every tome provides its own
// (a tome that omits a table gets these minimal defaults, never another course's content)
export let RANKS = [[0, "APPRENTICE"]];
export let SHOP = [];
// the five engine power-ups, generic flavor — a tome overrides these by id (see applyTomeConfig)
const DEFAULT_CONSUMABLES = [
  { id: "firewall", kind: "consumable", name: "WARD OF ABSORPTION", cost: 450, charges: 5, ico: "shield", desc: "While it holds a charge, a wrong answer costs you no credits." },
  { id: "x2", kind: "consumable", name: "DOUBLING CATALYST", cost: 600, ico: "zap", desc: "Your next 20 correct answers pay double credits." },
  { id: "skip", kind: "consumable", name: "SCROLL OF REVELATION", cost: 700, ico: "scroll", desc: "Instantly solves one trial at full points." },
  { id: "vpn", kind: "consumable", name: "CLOAK OF UNSEEING", cost: 800, charges: 3, ico: "cloak", desc: "Deflects one incoming hex per charge." },
  { id: "xray", kind: "consumable", name: "SCRYING LENS", cost: 500, ico: "eye", desc: "Reveals the grader's private notes for one Great Working." },
];
export let HINT_COST = 75;
export let ORACLE_COST = 10;
export let ATTEMPT_MULT = [1, 0.6, 0.3], COMBO_STEP = 0.05, COMBO_CAP = 0.5, SRANK_MULT = 1.5;
export let ATK_STAKE_PER = 20, ATK_WIN_PER = 15, BLACKICE_N = 10, BLACKICE_CAP = 2;
export let BADGES = {};
export let EARNED_THEME = null;   // {id,name,desc} — an exclusive theme unlocked via attack wins

// narrative + progression tunables, read by the modules that render them
export let GRADING_LINES = [
  "your pages are carried up the tower stair...",
  "the work is weighed against the chart...",
  "the judgement is being written...",
];
export let BOOT_LINES = [
  "A match is struck. The candle takes the flame.",
  "The tome on the desk falls open to where you left it.",
  "Take up your quill.",
];
export let INTRUSION_TIERS = [];  // tomes define [[progression.intrusionTiers]]; none = no hexes
export let ATK_TIME = 180;
export let ATK_STAGE_AT = [0, 60, 120]; // seconds elapsed when each directive arms

// pull every tunable from the active Tome (falls back to the defaults above)
export function applyTomeConfig() {
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

export const J = () => window.TOME || {};
export const persona = () => (J().narrative && J().narrative.graderPersona) || "THE MAGISTER";
// the tower's name plate: names the grader ACTUALLY selected in settings, not the
// tome's flavor text — "OPUS 4.8 // MAGISTER THORNE", "QWEN3:14B // MAGISTER THORNE"
const GRADER_KIND_NAME = { "claude-cli": "CLAUDE", "antigravity-cli": "ANTIGRAVITY", "codex-cli": "CODEX", "opencode-cli": "OPENCODE", anthropic: "ANTHROPIC", openai: "OPENAI", ollama: "OLLAMA", other: "A CUSTOM SCRIBE" };
export function graderTitle() {
  const m = ((S && S.ai && S.ai.graderModel) || "").replace(/^claude-/, "").replace(/-(\d+)-(\d+)$/, " $1.$2").replace(/-/g, " ");
  const who = (m || GRADER_KIND_NAME[S && S.ai && S.ai.graderKind] || "THE TOWER").toUpperCase();
  return `${who} // ${persona()}`;
}
export const coin = () => (J().narrative && J().narrative.currency) || "coin";      // "80 coin"
export const gp = () => (J().narrative && J().narrative.currencyShort) || "gp";     // "80gp"
const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX"];
export const roman = (n) => ROMAN[n - 1] || String(n);
export const projName = () => (J().runtime && J().runtime.project) || "Verisearch";
export const entryFile = () => (J().runtime && J().runtime.entryFile) || "Program.cs";
export const newFileExt = () => (J().runtime && J().runtime.newFileExt) || ".cs";
export const langName = () => (J().runtime && J().runtime.language) || (J().runtime && J().runtime.name) || "code";
export const editorLang = () => (J().runtime && J().runtime.editorLang) || "plaintext";
// the command shown in run/compile flavor text — from TOML, never guessed from the language
export const runLabel = () => {
  const r = J().runtime || {};
  return r.runLabel || (r.command ? [...r.command, r.entryFile || ""].join(" ").trim() : "dotnet run");
};
// external-editor mode: the student builds in their OWN IDE at a folder THEY choose,
// and CAST/PRESENT operate on that folder. A course can REQUIRE external mode via
// [runtime] externalWorkspace = true (a real toolchain, e.g. a Gradle mod), but the
// folder is always the student's — the tome never hardwires a path. Any tome can also
// be switched to external mode by the student via S.workspace (read after boot).
export const externalByAuthor = () => !!(J().runtime && J().runtime.externalWorkspace);
export const externalMode = () => externalByAuthor() || !!(S && S.workspace && S.workspace.enabled);
export const externalDir = () => (S && S.workspace && S.workspace.dir) || "";
// the files a fresh project needs (entry file, plus a project marker like a .csproj) —
// for the workbench file list and for seeding a student's own folder. `location` is set
// only when the file must live in a specific subdirectory of the project.
export function requiredFiles() {
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
