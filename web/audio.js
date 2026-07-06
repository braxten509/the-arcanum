/* GhostAudio — the sounds of a wizard's study. Pure WebAudio, zero assets.
   No music: a quiet hearthfire-crackle ambience bed (toggleable), plus one-shot
   SFX — wax seals, quill scratches, coin clinks, bell peals, page turns.
   Any synthesized one-shot can be replaced by a recording: name a file in
   global-configs/audio.toml [sound_files] and drop it in sounds/. */
(function () {
  "use strict";

  let ctx = null;
  let ambBus = null, sfxBus = null, ambLp = null;
  let crackleG = null, windG = null;   // per-layer trims inside the ambience bed
  let ambOn = true, ambStarted = false;
  let ambVol = 0.5, windVol = 0.5;

  // Tunable knobs, baked defaults. global-configs/audio.toml overrides any of these
  // at load (GhostAudio.configure below); a missing file or key keeps the default.
  // Read at use time, so a late async load still lands. Every key is spelled out in
  // full — the same names appear verbatim in audio.toml.
  const CONFIG = {
    sound_effects: { volume: 100 },
    sample_gain: { cast_release: 1.8, spell_hit_release: 1.3, hex: 1.2, hex_fade_seconds: 0.9, stroke: 0.4 },
    ambience: { lowpass_hertz: 4200, fade_seconds: 0.6, room_gain: 0.05, room_lowpass_hertz: 260, wobble_hertz: 0.17, wobble_depth: 0.02 },
    keys: {},
    sound_files: {}, // sound name -> filename in sounds/; a named file replaces that synthesized voice
  };

  function ensureCtx() {
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

    crackleG = ctx.createGain(); crackleG.gain.value = ambVol;
    windG = ctx.createGain(); windG.gain.value = windVol;
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
  function noise() {
    if (!noiseBuf) {
      noiseBuf = ctx.createBuffer(1, ctx.sampleRate, ctx.sampleRate);
      const d = noiseBuf.getChannelData(0);
      for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    }
    return noiseBuf;
  }

  // ------------------------------------------------------------- hearthfire
  // The candle burns: a recorded crackle loop plus a low wind-like room tone.
  let candleStarted = false;

  async function startCandle() {
    if (candleStarted) return;
    candleStarted = true;
    try {
      const raw = await (await fetch("sounds/candle.mp3")).arrayBuffer();
      const b = await ctx.decodeAudioData(raw);
      // Trim mp3 encoder padding, then crossfade the tail into the head so the
      // loop seam is inaudible: out[i] starts at S[fade], and the final `fade`
      // samples melt (equal-power) from the tail into the head it loops back to.
      const sr = b.sampleRate;
      const trim = Math.floor(sr * 0.05), fade = Math.floor(sr * 2);
      const N = b.length - trim * 2, L = N - fade;
      const out = ctx.createBuffer(b.numberOfChannels, L, sr);
      for (let c = 0; c < b.numberOfChannels; c++) {
        const s = b.getChannelData(c), d = out.getChannelData(c);
        for (let i = 0; i < L; i++) d[i] = s[trim + fade + i];
        for (let i = 0; i < fade; i++) {
          const a = (i / fade) * Math.PI / 2;
          d[L - fade + i] = d[L - fade + i] * Math.cos(a) + s[trim + i] * Math.sin(a);
        }
      }
      const src = ctx.createBufferSource();
      src.buffer = out; src.loop = true;
      src.connect(crackleG);
      src.start(ctx.currentTime, Math.random() * L / sr); // wake into a random moment of the fire
    } catch { /* no candle file / decode failure: the wind alone still plays */ }
  }

  function startAmbience() {
    if (ambStarted || !ctx) return;
    ambStarted = true;
    // room tone: brown-ish noise, heavily lowpassed, barely there
    const src = ctx.createBufferSource();
    src.buffer = noise(); src.loop = true; src.playbackRate.value = 0.35;
    const lp = ctx.createBiquadFilter();
    lp.type = "lowpass"; lp.frequency.value = CONFIG.ambience.room_lowpass_hertz; lp.Q.value = 0.5;
    const g = ctx.createGain(); g.gain.value = CONFIG.ambience.room_gain;
    // slow warmth wobble, like flamelight
    const wobble = ctx.createOscillator(); wobble.frequency.value = CONFIG.ambience.wobble_hertz;
    const wobbleGain = ctx.createGain(); wobbleGain.gain.value = CONFIG.ambience.wobble_depth;
    wobble.connect(wobbleGain); wobbleGain.connect(g.gain);
    src.connect(lp); lp.connect(g); g.connect(windG);
    src.start(); wobble.start();
    startCandle();
  }

  function setAmbience(on) {
    ambOn = on;
    if (!ctx) return;
    if (on && !ambStarted) startAmbience();
    ambBus.gain.setTargetAtTime(on ? 1 : 0, ctx.currentTime, CONFIG.ambience.fade_seconds);
  }

  // ------------------------------------------------------------- sfx helpers
  function tone(freq, dur, type, gain, when, slideTo) {
    const t = ctx.currentTime + (when || 0);
    const o = ctx.createOscillator(); o.type = type || "sine"; o.frequency.setValueAtTime(freq, t);
    if (slideTo) o.frequency.exponentialRampToValueAtTime(slideTo, t + dur);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(gain || 0.5, t + 0.008);
    g.gain.exponentialRampToValueAtTime(0.001, t + dur);
    o.connect(g); g.connect(sfxBus);
    o.start(t); o.stop(t + dur + 0.05);
  }
  // a burst of filtered noise: paper, cloth, scratches, fizzles
  function swish(f0, f1, dur, gain, when, q) {
    const t = ctx.currentTime + (when || 0);
    const src = ctx.createBufferSource(); src.buffer = noise();
    const bp = ctx.createBiquadFilter();
    bp.type = "bandpass"; bp.Q.value = q || 0.9;
    bp.frequency.setValueAtTime(f0, t);
    bp.frequency.exponentialRampToValueAtTime(f1, t + dur);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(gain, t + dur * 0.2);
    g.gain.exponentialRampToValueAtTime(0.001, t + dur);
    src.connect(bp); bp.connect(g); g.connect(sfxBus);
    src.start(t, Math.random() * 0.5, dur + 0.05);
  }
  // a struck bell: fundamental + inharmonic partials, long ring
  function bell(f, dur, gain, when) {
    for (const [ratio, g] of [[1, 1], [2.02, 0.42], [2.96, 0.22], [4.2, 0.1]])
      tone(f * ratio, dur * (1 - ratio * 0.12), "sine", gain * g, when);
  }

  // ---- sample overrides: any synthesized one-shot can be replaced by a recording
  // named in audio.toml [sound_files]. Drop the file in sounds/, name it, refresh.
  const sampleBuffers = {};       // filename -> decoded AudioBuffer
  const sampleFetchStarted = {};  // filename -> true once we have begun fetching it
  function loadSampleFile(filename) {
    if (!filename || sampleFetchStarted[filename] || !ctx) return;
    sampleFetchStarted[filename] = true;
    fetch("sounds/" + filename).then((response) => response.arrayBuffer())
      .then((raw) => ctx.decodeAudioData(raw))
      .then((buffer) => { sampleBuffers[filename] = buffer; })
      .catch(() => {}); // missing/undecodable: the synthesized voice keeps playing
  }
  // true when a configured file replaced the sound; false to fall back to the synth
  function playSampleOverride(name) {
    const filename = CONFIG.sound_files[name];
    if (!filename) return false;
    loadSampleFile(filename);
    const buffer = sampleBuffers[filename];
    if (!buffer) return false; // configured but not decoded yet — the synth stands in this once
    const source = ctx.createBufferSource(); source.buffer = buffer;
    const gainNode = ctx.createGain(); gainNode.gain.value = 1; // the master SFX volume applies via the bus
    source.connect(gainNode); gainNode.connect(sfxBus);
    source.start(ctx.currentTime);
    return true;
  }

  // ---- pen-stroke hand: one of several real stroke recordings, chosen at random
  // per press. drop more stroke-N.mp3 files in sounds/ and add them to the list.
  const DEFAULT_STROKE_FILES = ["stroke-1.mp3", "stroke-2.mp3", "stroke-3.mp3", "stroke-4.mp3", "stroke-5.mp3", "stroke-6.mp3", "stroke-7.mp3"];
  let strokeBufs = [], strokesLoading = false, lastPen = 0;
  function loadStrokes() {
    if (strokeBufs.length || strokesLoading || !ctx) return;
    strokesLoading = true;
    Promise.all((CONFIG.keys.stroke_files || DEFAULT_STROKE_FILES).map((f) =>
      fetch("sounds/" + f).then((r) => r.arrayBuffer()).then((raw) => ctx.decodeAudioData(raw))
    )).then((bufs) => { strokeBufs = bufs; })
      .catch(() => { strokesLoading = false; }); // any missing/undecodable file: silent
  }
  function penStroke(key) {
    loadStrokes();
    if (!strokeBufs.length) return; // first press or two may land before decode; fine
    const t = ctx.currentTime;
    if (t - lastPen < 0.09) return; // let a stroke breathe before the next begins
    lastPen = t;
    const buf = strokeBufs[(Math.random() * strokeBufs.length) | 0];
    const src = ctx.createBufferSource(); src.buffer = buf;
    const g = ctx.createGain();
    const level = CONFIG.sample_gain.stroke * keyVol; // samples are peak-normalized to -1 dBFS on disk; this keeps headroom
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(level, t + 0.004); // short attack, no start click; sample plays out whole
    src.connect(g); g.connect(sfxBus);
    src.start(t);
  }

  // ---- spell-cast samples: a real rising charge, then the release. The charge
  // recording is a long build (~20s) whose loudness climbs to a peak at its end,
  // so we play only its final `chargeSeconds` — the climax lands on the release.
  // These are already recordings — to change them, replace the files in sounds/.
  let castBufs = null, castLoading = false;
  function loadCast() {
    if (castBufs || castLoading || !ctx) return;
    castLoading = true;
    Promise.all(["cast-charge.mp3", "cast-release.mp3", "cast-fail.mp3"].map((f) =>
      fetch("sounds/" + f).then((r) => r.arrayBuffer()).then((raw) => ctx.decodeAudioData(raw))
    )).then(([charge, release, fail]) => { castBufs = { charge, release, fail }; })
      .catch(() => { castLoading = false; }); // missing/undecodable: the synth cast still plays
  }
  // returns false until the samples finish decoding, so the first cast of a
  // session (before decode lands) gracefully falls back to the synth voice
  function playCast(chargeSeconds, volume) {
    if (!castBufs) return false;
    const t = ctx.currentTime;
    // the charge: its climactic tail, faded out over the last 40ms so the cut
    // at release is clean (the release hit masks it anyway)
    const cb = castBufs.charge, play = Math.min(chargeSeconds, cb.duration);
    const cs = ctx.createBufferSource(); cs.buffer = cb;
    const cg = ctx.createGain();
    cg.gain.setValueAtTime(0.08 * volume, t);                            // starts hushed
    cg.gain.exponentialRampToValueAtTime(1.1 * volume, t + play - 0.04); // swells to loud by the release
    cg.gain.linearRampToValueAtTime(0.0001, t + play);                   // clean cut into the release
    cs.connect(cg); cg.connect(sfxBus);
    cs.start(t, cb.duration - play, play);
    // the release: the spell lands as the sigil dissipates, chargeSeconds in
    const rs = ctx.createBufferSource(); rs.buffer = castBufs.release;
    const rg = ctx.createGain(); rg.gain.value = CONFIG.sample_gain.cast_release * volume;
    rs.connect(rg); rg.connect(sfxBus);
    rs.start(t + chargeSeconds);
    return true;
  }

  // ---- incoming hex: a rival's spell blasted at the study, a real recording
  let hexBuf = null, hexLoading = false;
  function loadHex() {
    if (hexBuf || hexLoading || !ctx) return;
    hexLoading = true;
    fetch("sounds/hex-incoming.mp3").then((r) => r.arrayBuffer()).then((raw) => ctx.decodeAudioData(raw))
      .then((b) => { hexBuf = b; })
      .catch(() => { hexLoading = false; }); // missing/undecodable: the alarm toll stands in
  }

  // ---- keyclick: per-profile writing-implement synth, slight randomness per press.
  // Every field is spelled out; the same names appear in audio.toml [keys.<profile>].
  const KEY_PROFILES = {
    quill: { frequency: 2600, jitter: 1400, gain: 0.9, duration: 0.03, resonance: 0.8, deep_frequency: 1100 }, // a sharp nib on vellum
    scribe: { frequency: 700, jitter: 240, gain: 2.0, duration: 0.07, resonance: 0.8, deep_frequency: 400 },   // a heavy reed pen
    chalk: { frequency: 1300, jitter: 500, gain: 0.6, duration: 0.05, resonance: 0.6, deep_frequency: 650 },   // soft slate chalk
    chime: { chime: true },                                                        // enchanted glass keys
    pen: { pen: true },                                                            // a true pen, recorded
  };
  const LEGACY_PROFILE_NAMES = { clicky: "quill", thock: "scribe", soft: "chalk", beep: "chime" };
  let keyProfile = "quill", keyVol = 1, uiVol = 1;
  let lastClick = 0;
  function keyclick(key) {
    if (!ctx || keyVol <= 0) return;
    const t = ctx.currentTime;
    if (t - lastClick < 0.02) return; // burst guard, caps node churn on key rollover
    lastClick = t;
    const p = Object.assign({}, KEY_PROFILES[keyProfile] || KEY_PROFILES.quill, CONFIG.keys[keyProfile]); // [keys.<profile>] overrides
    if (p.pen) return penStroke(key);
    if (p.chime) {
      const deep = key === " " || key === "Enter";
      tone(deep ? 660 : 1320 + Math.random() * 330, 0.05, "sine", 0.3 * keyVol);
      if (key === "Enter") tone(880, 0.09, "sine", 0.25 * keyVol, 0.04);
      if (key === "Backspace") tone(494, 0.06, "sine", 0.25 * keyVol, 0, 330);
      return;
    }
    const deep = key === " " || key === "Enter";
    const src = ctx.createBufferSource(); src.buffer = noise();
    const bp = ctx.createBiquadFilter(); bp.type = "bandpass"; bp.Q.value = p.resonance;
    bp.frequency.value = (deep ? p.deep_frequency : p.frequency) + Math.random() * p.jitter;
    const g = ctx.createGain();
    g.gain.setValueAtTime(p.gain * (deep ? 1.3 : 1) * keyVol, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + (deep ? p.duration * 1.6 : p.duration));
    src.connect(bp); bp.connect(g); g.connect(sfxBus);
    src.start(t, Math.random() * 0.5, p.duration * 2 + 0.03);
    if (key === "Enter") tone(130, 0.07, "sine", 0.5 * keyVol);     // the pen lifts
    if (key === "Backspace") swish(2200, 900, 0.07, 0.5 * keyVol);  // scraped away
  }

  const SFX = {
    // correct/wrong dings removed — the sigil/spell cast is the sole success/miss cue now
    tick: () => { swish(2600, 1600, 0.05, 0.5); },                     // a quill tick (sound switched on)
    buy: () => {                                                        // coins into the pouch
      tone(2093, 0.06, "sine", 0.3); tone(2637, 0.05, "sine", 0.2, 0.01);
      tone(1865, 0.07, "sine", 0.28, 0.09); tone(2349, 0.06, "sine", 0.18, 0.1);
      swish(3000, 1400, 0.1, 0.2, 0.16);
    },
    badge: () => { bell(659, 0.9, 0.22); bell(880, 0.8, 0.18, 0.34); },  // the tower bell answers
    grade: () => {
      [392, 494, 587, 740, 880].forEach((f, i) => {         // a harp ascends
        tone(f, 0.34, "triangle", 0.2, i * 0.08);
        tone(f * 2, 0.2, "sine", 0.07, i * 0.08 + 0.02);
      });
    },
    boot: () => { swish(200, 1900, 0.5, 0.28); tone(90, 0.3, "sine", 0.3, 0.1); }, // the candle catches
    alarm: () => { bell(196, 1.1, 0.3); tone(233, 0.8, "sine", 0.1, 0.05); bell(196, 1.1, 0.28, 0.6); }, // a low toll
    hex: () => {                                                        // a rival's hex swells toward you
      loadHex();
      if (!hexBuf) return SFX.alarm(); // strike lands before the decode: the toll stands in
      const src = ctx.createBufferSource(); src.buffer = hexBuf;
      const g = ctx.createGain();
      const t = ctx.currentTime, peak = CONFIG.sample_gain.hex, fade = CONFIG.sample_gain.hex_fade_seconds || 0;
      if (fade > 0) {                                                  // swell in from near-silence — no jump-scare
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(peak, t + fade);
      } else {
        g.gain.value = peak;
      }
      src.connect(g); g.connect(sfxBus);
      src.start(t);
    },
    click: () => { swish(900, 400, 0.045, 0.9 * uiVol); },               // a fingertip on parchment
    pick: () => {                                                        // a multiple-choice answer is marked
      swish(1500, 620, 0.05, 0.4 * uiVol);
      tone(784, 0.06, "sine", 0.16 * uiVol, 0.015);                     // G5
      tone(1175, 0.09, "sine", 0.13 * uiVol, 0.05);                     // D6, a fifth up — "yes, that one"
    },
    wood: () => {                                                        // a knuckle on the wooden desk
      tone(210, 0.09, "triangle", 0.6 * uiVol, 0, 130);
      tone(150, 0.13, "sine", 0.42 * uiVol, 0, 90);                     // low body, quick damp
      swish(3000, 900, 0.016, 0.28 * uiVol);                            // the dry surface tick
    },
    stone: () => {                                                       // a fingertip taps the speaking stone
      tone(1040, 0.04, "triangle", 0.45 * uiVol, 0, 660);               // the hard mineral tick — brighter than wood
      tone(310, 0.07, "sine", 0.34 * uiVol, 0, 220);                    // the slab's dense, short body
      swish(5200, 2600, 0.028, 0.2 * uiVol);                            // granite grit
    },
    saved: () => {                                                        // the quill scratches, then rests
      swish(1900, 1000, 0.12, 0.5); swish(2100, 900, 0.09, 0.4, 0.13);
      tone(1046, 0.07, "sine", 0.14, 0.24);
    },
    page: () => { swish(480, 2400, 0.2, 0.4, 0, 0.6); swish(900, 300, 0.12, 0.25, 0.14); }, // a page turns
    orb: () => {                                                        // a fingertip rings the crystal
      tone(1568, 0.55, "sine", 0.26 * uiVol);                          // G6, a clear glass ring
      tone(2349, 0.5, "sine", 0.13 * uiVol, 0.01);                     // D7 partial
      tone(3136, 0.42, "sine", 0.07 * uiVol, 0.02);                    // G7 shimmer
      swish(6500, 3200, 0.06, 0.05 * uiVol);                           // the faint glassy hiss
    },
    candle: () => {                                                     // a breath stirs the flame
      swish(680, 230, 0.24, 0.34 * uiVol, 0, 0.5);                     // the low whoosh of the flame bending
      swish(2600, 1300, 0.08, 0.11 * uiVol, 0.03);                     // the wick's dry crackle
    },
    peddler: () => {                                                    // the peddler's pouch shifts, coins within
      swish(1200, 480, 0.14, 0.28 * uiVol, 0, 0.5);                    // the leather satchel rustles
      tone(2093, 0.06, "sine", 0.16 * uiVol, 0.05);                    // a coin taps
      tone(1760, 0.07, "sine", 0.13 * uiVol, 0.11);                    // another settles
    },
  };

  // ---------------------------------------------------- the spell-cast sound
  // castSigil()'s voice, tuned from global-configs/sigil.toml [sound]. A successful cast
  // is one gesture on the WebAudio clock: two partials swell and rise for the
  // whole charge, sparkle quickens with it, and the release lands as a whoomph,
  // a deep note, and glass ringing away. A miscast is a strained rise that dies.
  function sigilCast(ok, options) {
    if (!ctx || !options || options.enabled === false) return;
    const volume = (typeof options.volume === "number" ? options.volume : 100) / 100;
    if (volume <= 0) return;
    const chargeSeconds = options.charge_seconds || 3;
    loadCast();
    if (ok && playCast(chargeSeconds, volume)) return; // real recordings; synth below is the fallback
    if (!ok) {
      if (options.miscast === false) return;
      if (castBufs) {
        // the fail sound (cast-fail.mp3): skip its silent attack so it's heard at
        // once, then play through the charge stall and the fall. all tunable from
        // sigil.toml [fail]; the charge length is [fail] charge_milliseconds.
        const fail = options.fail || {};
        const fb = castBufs.fail, t = ctx.currentTime;
        const lead = fail.start ?? 0.9;            // seconds of the clip's silent attack to skip
        const level = (fail.gain ?? 2.0) * volume; // loudness, x the [sound] volume
        const fade = fail.fade ?? 0.3;             // tail fade-out, seconds
        const play = Math.min((options.charge_seconds || 1.1) + (fail.tail ?? 1.1), fb.duration - lead); // charge + tail
        const fs = ctx.createBufferSource(); fs.buffer = fb;
        const fg = ctx.createGain();
        fg.gain.setValueAtTime(0.0001, t);
        fg.gain.linearRampToValueAtTime(level, t + 0.03); // quick fade-in, no click from the mid-buffer start
        fg.gain.setValueAtTime(level, t + Math.max(0.04, play - fade));
        fg.gain.linearRampToValueAtTime(0.0001, t + play); // fade the tail, don't cut
        fs.connect(fg); fg.connect(sfxBus);
        fs.start(t, lead, play);
        return;
      }
      tone(160, chargeSeconds * .7, "sawtooth", .1 * volume, 0, 90); // the binding strains...
      swish(1100, 240, chargeSeconds * .8, .4 * volume, chargeSeconds * .3); // ...and fizzles out
      return;
    }
    const t = ctx.currentTime;
    for (const [multiplier, relativeGain] of [[1, .2], [1.5, .08]]) { // the rising bind, root + fifth
      const oscillator = ctx.createOscillator();
      oscillator.type = "sine";
      oscillator.frequency.setValueAtTime((options.charge_hertz_from || 110) * multiplier, t);
      oscillator.frequency.exponentialRampToValueAtTime((options.charge_hertz_to || 440) * multiplier, t + chargeSeconds);
      const gainNode = ctx.createGain();
      gainNode.gain.setValueAtTime(.001, t);
      gainNode.gain.exponentialRampToValueAtTime(relativeGain * volume, t + chargeSeconds); // swells with the charge
      gainNode.gain.exponentialRampToValueAtTime(.001, t + chargeSeconds + .3);
      oscillator.connect(gainNode); gainNode.connect(sfxBus);
      oscillator.start(t); oscillator.stop(t + chargeSeconds + .35);
    }
    const shimmerCount = Math.round(24 * (options.shimmer ?? .5)); // sparkle, clustering late like the poses
    for (let index = 0; index < shimmerCount; index++) {
      const atTime = chargeSeconds * Math.pow(Math.random(), .55);
      tone(1400 + Math.random() * 2400, .06, "sine", .11 * volume * (.3 + atTime / chargeSeconds), atTime);
    }
    const burstGain = (options.burst_gain ?? .6) * volume; // the release
    swish(2800, 240, .7, burstGain, chargeSeconds, .7);
    tone(62, .5, "sine", .8 * burstGain, chargeSeconds, 40);
    for (let index = 0; index < 6; index++) // shards ring away as the motes dissipate
      tone(1980 - index * 230, .12, "sine", .1 * volume, chargeSeconds + .06 + index * .07);
  }

  // the cast's release with no charge — quick trials get the spell's voice, not its build-up
  function spellHit(ok, options) {
    if (!ctx) return;
    options = options || {};
    const volume = (typeof options.volume === "number" ? options.volume : 100) / 100;
    if (volume <= 0) return;
    const t = ctx.currentTime;
    if (ok) {
      loadCast();
      if (castBufs) {                               // the real release recording, on its own
        const rs = ctx.createBufferSource(); rs.buffer = castBufs.release;
        const rg = ctx.createGain(); rg.gain.value = CONFIG.sample_gain.spell_hit_release * volume;
        rs.connect(rg); rg.connect(sfxBus);
        rs.start(t);
        return;
      }
      const burstGain = .5 * volume;                // synth release: whoomph, low note, glass ringing away
      swish(2800, 240, .5, burstGain, 0, .7);
      tone(62, .45, "sine", .7 * burstGain, 0, 40);
      for (let index = 0; index < 6; index++) tone(1980 - index * 230, .12, "sine", .1 * volume, .06 + index * .07);
      return;
    }
    swish(1100, 240, .28, .34 * volume);            // miscast: a short strained fizzle, no charge
    tone(150, .26, "sawtooth", .1 * volume, 0, 90);
  }

  // ---------------------------------------------------------------- api
  // merge global-configs/audio.toml over the baked defaults in CONFIG. The TOML reader
  // is flat, so a [keys.quill] table arrives as a section literally named "keys.quill":
  // split on "." and nest. Re-apply anything already live (bus trim, ambience lowpass).
  function configure(cfg) {
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

  window.GhostAudio = {
    configure,
    init(prefs) {
      ambOn = !!(prefs && prefs.ambience !== false);
      if (prefs && typeof prefs.volume === "number") ambVol = prefs.volume / 100;
      if (prefs && typeof prefs.wind === "number") windVol = prefs.wind / 100;
      if (prefs && prefs.keys) this.setKeys(prefs.keys.profile, prefs.keys.vol);
      if (prefs && typeof prefs.ui === "number") uiVol = prefs.ui / 100;
      // create the context at load: where autoplay policy allows (Firefox lineage),
      // the keepalive warms the output stream before the session's very first click
      ensureCtx();
      loadCast(); // warm the spell-cast samples before the first working
      loadHex();  // warm the incoming-hex sample before the first ambush
      if (ctx.state === "suspended") ctx.resume().catch(() => { });
    },
    running() { return !!ctx && ctx.state === "running"; },
    setKeys(profile, volPct) {
      profile = LEGACY_PROFILE_NAMES[profile] || profile; // old saves used keyboard-switch names
      if (KEY_PROFILES[profile]) keyProfile = profile;
      if (typeof volPct === "number") keyVol = volPct / 100;
      if (keyProfile === "pen") loadStrokes(); // warm the samples before the first press
    },
    setUiVol(volPct) { if (typeof volPct === "number") uiVol = volPct / 100; },
    setVolume(pct) {
      ambVol = pct / 100;
      if (crackleG) crackleG.gain.setTargetAtTime(ambVol, ctx.currentTime, 0.1);
    },
    setWind(pct) {
      windVol = pct / 100;
      if (windG) windG.gain.setTargetAtTime(windVol, ctx.currentTime, 0.1);
    },
    userGesture() {
      ensureCtx();
      if (ctx.state === "suspended") ctx.resume();
      if (ambOn) setAmbience(true);
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
})();
