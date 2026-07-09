/* The one-shot voices, by name. GhostAudio.sfx("page") reaches in here — unless
   audio.toml [sound_files] named a recording for that key, which wins. */
import { CONFIG, V, ctx, sfxBus } from "../core.js";
import { hexBuf, loadHex } from "../sources/samples.js";
import { bell, swish, tone } from "../sources/synth.js";

export const SFX = {
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
  click: () => { swish(900, 400, 0.045, 0.9 * V.uiVol); },               // a fingertip on parchment
  pick: () => {                                                        // a multiple-choice answer is marked
    swish(1500, 620, 0.05, 0.4 * V.uiVol);
    tone(784, 0.06, "sine", 0.16 * V.uiVol, 0.015);                     // G5
    tone(1175, 0.09, "sine", 0.13 * V.uiVol, 0.05);                     // D6, a fifth up — "yes, that one"
  },
  wood: () => {                                                        // a knuckle on the wooden desk
    tone(210, 0.09, "triangle", 0.6 * V.uiVol, 0, 130);
    tone(150, 0.13, "sine", 0.42 * V.uiVol, 0, 90);                     // low body, quick damp
    swish(3000, 900, 0.016, 0.28 * V.uiVol);                            // the dry surface tick
  },
  stone: () => {                                                       // a fingertip taps the speaking stone
    tone(1040, 0.04, "triangle", 0.45 * V.uiVol, 0, 660);               // the hard mineral tick — brighter than wood
    tone(310, 0.07, "sine", 0.34 * V.uiVol, 0, 220);                    // the slab's dense, short body
    swish(5200, 2600, 0.028, 0.2 * V.uiVol);                            // granite grit
  },
  saved: () => {                                                        // the quill scratches, then rests
    swish(1900, 1000, 0.12, 0.5); swish(2100, 900, 0.09, 0.4, 0.13);
    tone(1046, 0.07, "sine", 0.14, 0.24);
  },
  page: () => { swish(480, 2400, 0.2, 0.4, 0, 0.6); swish(900, 300, 0.12, 0.25, 0.14); }, // a page turns
  orb: () => {                                                        // a fingertip rings the crystal
    tone(1568, 0.55, "sine", 0.26 * V.uiVol);                          // G6, a clear glass ring
    tone(2349, 0.5, "sine", 0.13 * V.uiVol, 0.01);                     // D7 partial
    tone(3136, 0.42, "sine", 0.07 * V.uiVol, 0.02);                    // G7 shimmer
    swish(6500, 3200, 0.06, 0.05 * V.uiVol);                           // the faint glassy hiss
  },
  candle: () => {                                                     // a breath stirs the flame
    swish(680, 230, 0.24, 0.34 * V.uiVol, 0, 0.5);                     // the low whoosh of the flame bending
    swish(2600, 1300, 0.08, 0.11 * V.uiVol, 0.03);                     // the wick's dry crackle
  },
  peddler: () => {                                                    // the peddler's pouch shifts, coins within
    swish(1200, 480, 0.14, 0.28 * V.uiVol, 0, 0.5);                    // the leather satchel rustles
    tone(2093, 0.06, "sine", 0.16 * V.uiVol, 0.05);                    // a coin taps
    tone(1760, 0.07, "sine", 0.13 * V.uiVol, 0.11);                    // another settles
  },
};
