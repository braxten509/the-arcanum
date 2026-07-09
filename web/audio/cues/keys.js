/* keyclick — per-profile writing-implement synth, slight randomness per press.
   Every field is spelled out; the same names appear in audio.toml [keys.<profile>]. */
import { CONFIG, V, ctx, noise, sfxBus } from "../core.js";
import { loadStrokes, penStroke } from "../sources/samples.js";
import { swish, tone } from "../sources/synth.js";

const KEY_PROFILES = {
  quill: { frequency: 2600, jitter: 1400, gain: 0.9, duration: 0.03, resonance: 0.8, deep_frequency: 1100 }, // a sharp nib on vellum
  scribe: { frequency: 700, jitter: 240, gain: 2.0, duration: 0.07, resonance: 0.8, deep_frequency: 400 },   // a heavy reed pen
  chalk: { frequency: 1300, jitter: 500, gain: 0.6, duration: 0.05, resonance: 0.6, deep_frequency: 650 },   // soft slate chalk
  chime: { chime: true },                                                        // enchanted glass keys
  pen: { pen: true },                                                            // a true pen, recorded
};
const LEGACY_PROFILE_NAMES = { clicky: "quill", thock: "scribe", soft: "chalk", beep: "chime" };
let lastClick = 0;

export function setKeys(profile, volPct) {
  profile = LEGACY_PROFILE_NAMES[profile] || profile; // old saves used keyboard-switch names
  if (KEY_PROFILES[profile]) V.keyProfile = profile;
  if (typeof volPct === "number") V.keyVol = volPct / 100;
  if (V.keyProfile === "pen") loadStrokes(); // warm the samples before the first press
}

export function keyclick(key) {
  if (!ctx || V.keyVol <= 0) return;
  const t = ctx.currentTime;
  if (t - lastClick < 0.02) return; // burst guard, caps node churn on key rollover
  lastClick = t;
  const p = Object.assign({}, KEY_PROFILES[V.keyProfile] || KEY_PROFILES.quill, CONFIG.keys[V.keyProfile]); // [keys.<profile>] overrides
  if (p.pen) return penStroke(key);
  if (p.chime) {
    const deep = key === " " || key === "Enter";
    tone(deep ? 660 : 1320 + Math.random() * 330, 0.05, "sine", 0.3 * V.keyVol);
    if (key === "Enter") tone(880, 0.09, "sine", 0.25 * V.keyVol, 0.04);
    if (key === "Backspace") tone(494, 0.06, "sine", 0.25 * V.keyVol, 0, 330);
    return;
  }
  const deep = key === " " || key === "Enter";
  const src = ctx.createBufferSource(); src.buffer = noise();
  const bp = ctx.createBiquadFilter(); bp.type = "bandpass"; bp.Q.value = p.resonance;
  bp.frequency.value = (deep ? p.deep_frequency : p.frequency) + Math.random() * p.jitter;
  const g = ctx.createGain();
  g.gain.setValueAtTime(p.gain * (deep ? 1.3 : 1) * V.keyVol, t);
  g.gain.exponentialRampToValueAtTime(0.001, t + (deep ? p.duration * 1.6 : p.duration));
  src.connect(bp); bp.connect(g); g.connect(sfxBus);
  src.start(t, Math.random() * 0.5, p.duration * 2 + 0.03);
  if (key === "Enter") tone(130, 0.07, "sine", 0.5 * V.keyVol);     // the pen lifts
  if (key === "Backspace") swish(2200, 900, 0.07, 0.5 * V.keyVol);  // scraped away
}
