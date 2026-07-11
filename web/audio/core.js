/* GhostAudio core — the audio context, the buses, the tunable knobs.
   Everything else in audio/ hangs off these. */

// The graph. ensureCtx() assigns these once; importers read them as live
// bindings, so a module that imported `ctx` before boot still sees it appear.
export let ctx = null;
export let ambBus = null, sfxBus = null, ambLp = null;
export let crackleG = null, windG = null;   // per-layer trims inside the ambience bed

// The knobs the API setters turn at runtime. One object, because `export let`
// bindings are read-only to importers — a plain `let ambVol` could not be set
// from index.js. Property writes on V land everywhere.
export const V = { ambOn: true, ambVol: 0.5, windVol: 0.5, keyVol: 1, uiVol: 1, keyProfile: "quill" };

// Tunable knobs, baked defaults. global-configs/audio.toml overrides any of these
// at load (GhostAudio.configure below); a missing file or key keeps the default.
// Read at use time, so a late async load still lands. Every key is spelled out in
// full — the same names appear verbatim in audio.toml.
export const CONFIG = {
  sound_effects: { volume: 100 },
  sample_gain: { cast_release: 1.8, spell_hit_release: 1.3, hex: 1.2, hex_fade_seconds: 0.9, stroke: 0.4 },
  sample_pitch: { peddler_min: 0.95, peddler_max: 1.05, wand_min: 0.86, wand_max: 1.14 },
  ambience: { lowpass_hertz: 4200, fade_seconds: 0.6, room_gain: 0.05, room_lowpass_hertz: 260, wobble_hertz: 0.17, wobble_depth: 0.02 },
  keys: {},
  // Shipped recordings are defaults here as well as in audio.toml so they can
  // begin decoding before the asynchronous config request finishes. The TOML
  // values still win and may replace or disable any of them.
  sound_files: {
    candle: "candle-light-click.mp3",
    green_tome: "green-tome.mp3",
    grimoire: "grimoire-close.mp3",
    ink: "inkwell-glug.mp3",
    letter: "letter-page.mp3",
    notes: "notes-page.mp3",
    orb: "orb-ding.mp3",
    peddler: "coin-pouch.mp3",
    wand: "wand-swish.mp3",
  },
};

export function ensureCtx() {
  if (ctx) return ctx;
  ctx = new (window.AudioContext || window.webkitAudioContext)();

  sfxBus = ctx.createGain();
  sfxBus.gain.value = 0.16 * CONFIG.sound_effects.volume / 100;
  sfxBus.connect(ctx.destination);

  ambBus = ctx.createGain();
  ambBus.gain.value = 0;
  ambLp = ctx.createBiquadFilter();
  ambLp.type = "lowpass"; ambLp.frequency.value = CONFIG.ambience.lowpass_hertz; ambLp.Q.value = 0.4;
  ambBus.connect(ambLp); ambLp.connect(ctx.destination);

  crackleG = ctx.createGain(); crackleG.gain.value = V.ambVol;
  windG = ctx.createGain(); windG.gain.value = V.windVol;
  crackleG.connect(ambBus); windG.connect(ambBus);

  // keepalive: Chromium/PipeWire suspend the output stream on digital silence,
  // swallowing the first short SFX after a quiet spell. An inaudible 30 Hz
  // trickle (-66 dB) keeps the stream warm so the first click always lands.
  const keep = ctx.createOscillator();
  keep.type = "sine"; keep.frequency.value = 30;
  const kg = ctx.createGain(); kg.gain.value = 0.0005;
  keep.connect(kg); kg.connect(ctx.destination);
  keep.start();

  return ctx;
}

// one shared noise buffer feeds keyclicks, the wind bed, and noise-based SFX
let noiseBuf = null;
export function noise() {
  if (!noiseBuf) {
    noiseBuf = ctx.createBuffer(1, ctx.sampleRate, ctx.sampleRate);
    const d = noiseBuf.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  }
  return noiseBuf;
}

// merge global-configs/audio.toml over the baked defaults in CONFIG. The TOML reader
// is flat, so a [keys.quill] table arrives as a section literally named "keys.quill":
// split on "." and nest. Re-apply anything already live (bus trim, ambience lowpass).
export function configure(cfg) {
  if (!cfg) return;
  for (const sec in cfg) {
    const parts = sec.split(".");
    let dst = CONFIG;
    for (let i = 0; i < parts.length - 1; i++) dst = dst[parts[i]] = dst[parts[i]] || {};
    const leaf = parts[parts.length - 1];
    dst[leaf] = Object.assign(dst[leaf] || {}, cfg[sec]);
  }
  if (ctx) {
    if (sfxBus) sfxBus.gain.value = 0.16 * CONFIG.sound_effects.volume / 100;
    if (ambLp) ambLp.frequency.value = CONFIG.ambience.lowpass_hertz;
  }
}
