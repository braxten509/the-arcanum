/* hearthfire — the candle burns: a recorded crackle loop plus a low wind-like
   room tone. The bed fades in on the first user gesture and never restarts. */
import { CONFIG, V, ambBus, crackleG, ctx, noise, windG } from "../core.js";

let candleStarted = false, ambStarted = false;

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

export function setAmbience(on) {
  V.ambOn = on;
  if (!ctx) return;
  if (on && !ambStarted) startAmbience();
  ambBus.gain.setTargetAtTime(on ? 1 : 0, ctx.currentTime, CONFIG.ambience.fade_seconds);
}
