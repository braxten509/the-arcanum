/* The wizard's ledger — the one mutable save state, its autosave, and the ink LED. */
import { BADGES, J, RANKS, TID } from "./config.js";
import { evidenceDefaults, migrateState } from "../mastery/evidence.js";

export let S = null;
let saveTimer = null, savePending = false;
let saveInFlight = null, saveResetting = false;
let loadDefaulted = false; // true when loadState fell back to a fresh default (server empty/unreachable)
// real play, not just settings — mirrors the server's has_progress guard
const hasProgress = (s) => !!(s && (s.earned || s.credits || s.hexesEnabled === false ||
  (s.ex && Object.keys(s.ex).length) || (s.read && Object.keys(s.read).length) ||
  (s.badges && Object.keys(s.badges).length) || (s.fs && Object.keys(s.fs).length) ||
  (s.exerciseEvidence && Object.keys(s.exerciseEvidence).length) ||
  (s.assessmentReceipts && Object.keys(s.assessmentReceipts).length)));

const DEFAULT_STATE = () => {
  const jd = (window.TOME && window.TOME.defaults) || {};
  const dTheme = jd.theme || "vellum", dai = jd.ai || {};
  return {
    v: 2, booted: false, credits: 0, earned: 0, hexesEnabled: true,
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
    ...evidenceDefaults(),
  };
};

export async function loadState() {
  try {
    const r = await fetch("/api/state");
    const data = await r.json();
    loadDefaulted = !Object.keys(data).length;
    S = loadDefaulted ? DEFAULT_STATE() : Object.assign(DEFAULT_STATE(), data);
    S = migrateState(S, { ...(window.TOME || {}), sections: window.SECTIONS || [] });
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

export function save(now) {
  if (saveResetting) return;
  // if our load fell back to a default (server was empty or unreachable), don't
  // let an autosave write that blank state over a real save on disk — hold off
  // until there's actual progress to persist. a real save resumes the moment
  // the wizard earns anything. (server refuses this too, as a backstop.)
  if (loadDefaulted && !hasProgress(S)) return;
  savePending = true;
  setLed("saving");
  clearTimeout(saveTimer);
  const doSave = async () => {
    if (saveResetting) return;
    let request = null;
    try {
      request = fetch("/api/state", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(S) });
      saveInFlight = request;
      await request;
      savePending = false;
      setLed("saved");
    } catch {
      if (!saveResetting) { setLed("error"); setTimeout(() => save(), 3000); }
    } finally {
      if (request && saveInFlight === request) saveInFlight = null;
    }
  };
  if (now) doSave(); else saveTimer = setTimeout(doSave, 700);
}

// A reset must not race the autosave or the beforeunload beacon: first prevent
// new writes, then let any request already accepted by the server finish.
export async function prepareStateReset() {
  saveResetting = true;
  savePending = false;
  clearTimeout(saveTimer);
  if (saveInFlight) {
    try { await saveInFlight; } catch { /* the reset supersedes a failed save */ }
  }
}

export function resumeStateSaves() {
  saveResetting = false;
  setLed("saved");
}
window.addEventListener("beforeunload", () => {
  // sendBeacon bypasses the fetch shim, so scope it to the active tome explicitly
  if (savePending) navigator.sendBeacon("/api/state?tome=" + encodeURIComponent(TID()), new Blob([JSON.stringify(S)], { type: "application/json" }));
});
setInterval(() => { if (savePending) save(true); }, 15000);

export function setLed(mode) {
  const dot = document.getElementById("led-dot"), txt = document.getElementById("led-text");
  dot.className = "led" + (mode === "saving" ? " saving" : mode === "error" ? " error" : "");
  txt.textContent = mode === "saving" ? "INKING…" : mode === "error" ? "RE-INK" : "INK DRY";
}
