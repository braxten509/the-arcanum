/* Recordings: the sounds that are played, not synthesized. Every loader fails
   soft — a missing or undecodable file leaves the synth voice standing. */
import { CONFIG, V, ctx, sfxBus } from "../core.js";

// ---- sample overrides: any synthesized one-shot can be replaced by a recording
// named in audio.toml [sound_files]. Drop the file in sounds/, name it, refresh.
const sampleBuffers = {};       // filename -> decoded AudioBuffer
const sampleFetchStarted = {};  // filename -> true once we have begun fetching it
const sampleFailed = {};        // filename -> true when fetch/decode failed; only then may the synth stand in
function loadSampleFile(filename) {
  if (!filename || sampleFetchStarted[filename] || !ctx) return;
  sampleFetchStarted[filename] = true;
  fetch("sounds/" + filename).then((response) => response.arrayBuffer())
    .then((raw) => ctx.decodeAudioData(raw))
    .then((buffer) => { sampleBuffers[filename] = buffer; })
    .catch(() => { sampleFailed[filename] = true; }); // missing/undecodable: later clicks may use the synth
}
export function loadSampleOverrides() {
  Object.values(CONFIG.sound_files).forEach(loadSampleFile);
}
// true when a configured file replaced the sound; false to fall back to the synth
export function playSampleOverride(name) {
  const filename = CONFIG.sound_files[name];
  if (!filename) return false;
  loadSampleFile(filename);
  const buffer = sampleBuffers[filename];
  // A configured recording owns this cue even while it is decoding. Returning
  // true suppresses the synth during that brief window instead of leaking the
  // wrong voice; a genuine load failure restores the synth on later clicks.
  if (!buffer) return !sampleFailed[filename];
  const source = ctx.createBufferSource(); source.buffer = buffer;
  const pitchMin = Number(CONFIG.sample_pitch && CONFIG.sample_pitch[name + "_min"]);
  const pitchMax = Number(CONFIG.sample_pitch && CONFIG.sample_pitch[name + "_max"]);
  if (Number.isFinite(pitchMin) && Number.isFinite(pitchMax) && pitchMax >= pitchMin)
    source.playbackRate.value = pitchMin + Math.random() * (pitchMax - pitchMin);
  const gainNode = ctx.createGain(); gainNode.gain.value = 1; // the master SFX volume applies via the bus
  source.connect(gainNode); gainNode.connect(sfxBus);
  source.start(ctx.currentTime);
  return true;
}

// ---- pen-stroke hand: one of several real stroke recordings, chosen at random
// per press. drop more stroke-N.mp3 files in sounds/ and add them to the list.
const DEFAULT_STROKE_FILES = ["stroke-1.mp3", "stroke-2.mp3", "stroke-3.mp3", "stroke-4.mp3", "stroke-5.mp3", "stroke-6.mp3", "stroke-7.mp3"];
let strokeBufs = [], strokesLoading = false, lastPen = 0;
export function loadStrokes() {
  if (strokeBufs.length || strokesLoading || !ctx) return;
  strokesLoading = true;
  Promise.all((CONFIG.keys.stroke_files || DEFAULT_STROKE_FILES).map((f) =>
    fetch("sounds/" + f).then((r) => r.arrayBuffer()).then((raw) => ctx.decodeAudioData(raw))
  )).then((bufs) => { strokeBufs = bufs; })
    .catch(() => { strokesLoading = false; }); // any missing/undecodable file: silent
}
export function penStroke(key) {
  loadStrokes();
  if (!strokeBufs.length) return; // first press or two may land before decode; fine
  const t = ctx.currentTime;
  if (t - lastPen < 0.09) return; // let a stroke breathe before the next begins
  lastPen = t;
  const buf = strokeBufs[(Math.random() * strokeBufs.length) | 0];
  const src = ctx.createBufferSource(); src.buffer = buf;
  const g = ctx.createGain();
  const level = CONFIG.sample_gain.stroke * V.keyVol; // samples are peak-normalized to -1 dBFS on disk; this keeps headroom
  g.gain.setValueAtTime(0, t);
  g.gain.linearRampToValueAtTime(level, t + 0.004); // short attack, no start click; sample plays out whole
  src.connect(g); g.connect(sfxBus);
  src.start(t);
}

// ---- spell-cast samples: a real rising charge, then the release. The charge
// recording is a long build (~20s) whose loudness climbs to a peak at its end,
// so we play only its final `chargeSeconds` — the climax lands on the release.
// These are already recordings — to change them, replace the files in sounds/.
export let castBufs = null;
let castLoading = false;
export function loadCast() {
  if (castBufs || castLoading || !ctx) return;
  castLoading = true;
  Promise.all(["cast-charge.mp3", "cast-release.mp3", "cast-fail.mp3"].map((f) =>
    fetch("sounds/" + f).then((r) => r.arrayBuffer()).then((raw) => ctx.decodeAudioData(raw))
  )).then(([charge, release, fail]) => { castBufs = { charge, release, fail }; })
    .catch(() => { castLoading = false; }); // missing/undecodable: the synth cast still plays
}
// returns false until the samples finish decoding, so the first cast of a
// session (before decode lands) gracefully falls back to the synth voice
export function playCast(chargeSeconds, volume) {
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
export let hexBuf = null;
let hexLoading = false;
export function loadHex() {
  if (hexBuf || hexLoading || !ctx) return;
  hexLoading = true;
  fetch("sounds/hex-incoming.mp3").then((r) => r.arrayBuffer()).then((raw) => ctx.decodeAudioData(raw))
    .then((b) => { hexBuf = b; })
    .catch(() => { hexLoading = false; }); // missing/undecodable: the alarm toll stands in
}
