/* GhostAudio — the sounds of a wizard's study. Pure WebAudio, zero assets.
   No music: a quiet hearthfire-crackle ambience bed (toggleable), plus one-shot
   SFX — wax seals, quill scratches, coin clinks, bell peals, page turns.
   Any synthesized one-shot can be replaced by a recording: name a file in
   global-configs/audio.toml [sound_files] and drop it in sounds/.

   This is the api. Import it for its side effect — it hangs GhostAudio on window,
   which is how the rest of the engine has always reached the sound. */
import { setAmbience } from "./cues/ambience.js";
import { V, configure as configureCore, crackleG, ctx, ensureCtx, windG } from "./core.js";
import { keyclick, setKeys } from "./cues/keys.js";
import { loadCast, loadHex, loadSampleOverrides, playSampleOverride } from "./sources/samples.js";
import { SFX } from "./cues/sfx.js";
import { sigilCast, spellHit } from "./cues/spell.js";

window.GhostAudio = {
  configure(cfg) {
    configureCore(cfg);
    loadSampleOverrides();
  },
  init(prefs) {
    V.ambOn = !!(prefs && prefs.ambience !== false);
    if (prefs && typeof prefs.volume === "number") V.ambVol = prefs.volume / 100;
    if (prefs && typeof prefs.wind === "number") V.windVol = prefs.wind / 100;
    if (prefs && prefs.keys) setKeys(prefs.keys.profile, prefs.keys.vol);
    if (prefs && typeof prefs.ui === "number") V.uiVol = prefs.ui / 100;
    // create the context at load: where autoplay policy allows (Firefox lineage),
    // the keepalive warms the output stream before the session's very first click
    ensureCtx();
    loadSampleOverrides(); // warm shipped/configured UI recordings before their first click
    loadCast(); // warm the spell-cast samples before the first working
    loadHex();  // warm the incoming-hex sample before the first ambush
    if (ctx.state === "suspended") ctx.resume().catch(() => { });
  },
  running() { return !!ctx && ctx.state === "running"; },
  setKeys,
  setUiVol(volPct) { if (typeof volPct === "number") V.uiVol = volPct / 100; },
  setVolume(pct) {
    V.ambVol = pct / 100;
    if (crackleG) crackleG.gain.setTargetAtTime(V.ambVol, ctx.currentTime, 0.1);
  },
  setWind(pct) {
    V.windVol = pct / 100;
    if (windG) windG.gain.setTargetAtTime(V.windVol, ctx.currentTime, 0.1);
  },
  userGesture() {
    ensureCtx();
    if (ctx.state === "suspended") ctx.resume();
    if (V.ambOn) setAmbience(true);
  },
  setAmbience(on) { ensureCtx(); setAmbience(on); },
  sfx(name) {
    if (!ctx) return;
    if (playSampleOverride(name)) return; // a file named in audio.toml [sound_files] replaces the synth voice
    const fn = SFX[name];
    if (fn) fn();
  },
  sigilCast,
  spellHit,
  keyclick,
};
