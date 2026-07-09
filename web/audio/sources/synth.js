/* sfx helpers — the three voices every synthesized one-shot is built from. */
import { ctx, noise, sfxBus } from "../core.js";

export function tone(freq, dur, type, gain, when, slideTo) {
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
export function swish(f0, f1, dur, gain, when, q) {
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
export function bell(f, dur, gain, when) {
  for (const [ratio, g] of [[1, 1], [2.02, 0.42], [2.96, 0.22], [4.2, 0.1]])
    tone(f * ratio, dur * (1 - ratio * 0.12), "sine", gain * g, when);
}
