/* the spell-cast sound — castSigil()'s voice, tuned from global-configs/sigil.toml
   [sound]. A successful cast is one gesture on the WebAudio clock: two partials
   swell and rise for the whole charge, sparkle quickens with it, and the release
   lands as a whoomph, a deep note, and glass ringing away. A miscast is a strained
   rise that dies. */
import { CONFIG, ctx, sfxBus } from "../core.js";
import { castBufs, loadCast, playCast } from "../sources/samples.js";
import { swish, tone } from "../sources/synth.js";

export function sigilCast(ok, options) {
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
export function spellHit(ok, options) {
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
