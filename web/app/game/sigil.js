/* Spell sigils, verdict motes, and the just-enough TOML reader that tunes them.

   Every cast spells 3–6 letters of the Standard Galactic Alphabet — the
   enchanters' script — as connected fractures of unstable living aether.
   Their geometry snaps and forks under the binding, charging white-hot
   for ~3s, then
   dissipates in ONE release. A miscast charges the same — same letters, same
   colour — then the binding breaks: it greys and falls as ash.
   The paths animate through SVG geometry, transform, and opacity; gated by the
   same preference as the candle embers.
   strokes live on a ~3.4x6 grid (y down); a 1-point stroke becomes a hooked spark.
   every knob below (particles AND sound) is tuned by global-configs/sigil.toml — these
   are the fallback defaults when the file or a key is missing. */
const SIG = {
  letters: { minimum: 3, maximum: 6, scale: 28, spacing: .62 },
  palette: { saturation: 78, saturation_miscast: 30 },
  lightning: { width_minimum: 4.8, width_maximum: 7.2, glow_width: 21, jitter: 9.5, cadence_milliseconds: 44, success_cadence_start_milliseconds: 72, success_cadence_peak_milliseconds: 24, success_jitter_peak: 1.85, forks_minimum: 0, forks_maximum: 2, fork_length_minimum: 10, fork_length_maximum: 27, fork_energy: 1.35 },
  charge: { total_milliseconds: 4000, release_fraction: .75, poses_minimum: 18, poses_maximum: 22, shake: 7, grow: .25 },
  burst: { distance_minimum: 160, distance_maximum: 400, particle_size: 1.7, shards: 2, shard_size: .45 },
  sound: { enabled: true, volume: 100, charge_hertz_from: 110, charge_hertz_to: 440, shimmer: .5, burst_gain: .6, miscast: true },
  fail: { charge_milliseconds: 1200, start: .9, tail: 1.1, gain: 2, fade: .3, fall_distance_minimum: 300, fall_distance_maximum: 660, spread: 42, particles_per_node: 8, particle_size: .42 }, // miscast: charge, then instantly crumble into fine ash
};
window.SIGIL_CFG = SIG; // console-reachable: poke values live, then castSigil()
// a just-enough TOML reader — [section], key = number | bool | "string" | [array].
// shared by sigil.toml and particles.toml. sections merge onto the target object,
// so a partial file overrides only the keys it names; the rest keep their defaults.
function readToml(txt, into) {
  const val = (raw) => {
    raw = raw.trim();
    if (raw === "true") return true;
    if (raw === "false") return false;
    if (raw[0] === '"') return raw.slice(1, -1);
    if (raw[0] === "[") return raw.slice(1, -1).split(",").map(val).filter((x) => x !== "" && !(typeof x === "number" && Number.isNaN(x)));
    const n = parseFloat(raw);
    return Number.isNaN(n) ? raw : n;
  };
  let sec = null;
  for (let line of txt.split("\n")) {
    line = line.replace(/^\s*#.*$/, "").replace(/\s#.*$/, "").trim(); // drop # comments, but not the # inside "quoted" hex colors
    if (!line) continue;
    const h = line.match(/^\[(.+)\]$/);
    if (h) { sec = into[h[1]] = into[h[1]] || {}; continue; }
    const kv = line.match(/^([\w-]+)\s*=\s*(.+)$/);
    if (kv && sec) sec[kv[1]] = val(kv[2]);
  }
  return into;
}
const loadToml = (file, into) => fetch(file).then((r) => r.text()).then((t) => readToml(t, into)).catch(() => {}); // missing file: baked defaults stand
loadToml("global-configs/sigil.toml", SIG);
const GALACTIC = {
  a: [[[0, 6], [1.1, 6], [1.1, 1.5], [1.5, .4], [2.5, .4], [3, 1.1], [3, 2.5]]],
  b: [[[1.4, 0], [1.4, 1.4], [3.4, 4.9], [0, 4.9]]],
  c: [[[1.6, .5]], [[1, 2.7], [1.6, 2.1], [1.6, 6]]],
  d: [[[.2, .4], [2.8, .4]], [[.2, 1.3], [3.3, 3.1]]],
  e: [[[.6, .3], [.6, 5], [3, 5]], [[2.8, .6]]],
  f: [[[0, .4], [3.2, .4]], [[.4, 1.7]], [[1.6, 1.7]], [[2.8, 1.7]]],
  g: [[[2.1, .3], [2.1, 5.7]], [[.6, 3], [2.1, 3]]],
  h: [[[0, .4], [3.4, .4]], [[.4, 1.7], [3, 1.7]], [[1.7, 1.7], [1.7, 5.6]]],
  i: [[[1.7, 0], [1.7, 2.2]], [[1.7, 3.5], [1.7, 5.7]]],
  j: [[[1.7, 0], [1.7, 1]], [[1.7, 2.1], [1.7, 3.1]], [[1.7, 4.2], [1.7, 6]]],
  k: [[[1.7, .2], [1.7, 5.6]], [[.4, 2.9]], [[3, 2.9]]],
  l: [[[.9, .2], [.9, 5.6]], [[2.7, 1.5]], [[2.7, 3.3]]],
  m: [[[.6, .5]], [[3, .3], [3, 4.9], [.7, 4.9]]],
  n: [[[.6, .6]], [[2.9, .4], [2.6, 1.6], [1, 5.8]]],
  o: [[[.2, .4], [2.9, .4], [.9, 5.7]]],
  p: [[[.8, .6]], [[.8, 1.9], [.8, 5.7]], [[2.6, .2], [2.6, 4]], [[2.6, 5.5]]],
  q: [[[2, .5]], [[1.8, 1.8], [.5, 1.8], [.5, 5.6], [3.2, 5.6]]],
  r: [[[.6, 1.6]], [[2.8, 1.6]], [[.6, 3.7]], [[2.8, 3.7]]],
  s: [[[2.4, .3], [2.4, 2.5], [1, 3.4], [1, 5.7]]],
  t: [[[.3, .4], [2.9, .4], [2.9, 2.8]], [[2.9, 4.8]]],
  u: [[[1.5, .4]], [[2.7, .4]], [[.2, 2.1], [3.2, 2.1]], [[.2, 3.7], [3.2, 3.7]]],
  v: [[[1.7, .4], [1.7, 3]], [[.6, 3], [2.8, 3]], [[.2, 4.6], [3.2, 4.6]]],
  w: [[[1.7, 1.6]], [[.4, 3.6]], [[3, 3.6]]],
  x: [[[.6, .8]], [[2.9, .8], [.9, 5.6]]],
  y: [[[1, .4], [1, 5.6]], [[2.4, .4], [2.4, 5.6]]],
  z: [[[.5, 5.6], [.5, 1.5], [1.7, .3], [2.9, 1.5], [2.9, 5.6]]],
};
// verdict/cursor motes: a burst of short-lived divs, tinted and thrown by the material struck.
// ponytail: ~a dozen–thirty per burst, removed on finish; cap concurrency if click-spam ever bites.
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
export let lastCastAt = null; // where the CAST button sat when pressed — the burst's anchor if the verdict re-renders it away
export const setLastCastAt = (pt) => { lastCastAt = pt; };
const PCL = {
  pick:    { count: 7,  colors: ["var(--ac-dim)", "#e3c059"], size: [2, 4], rise: 30, spread: 30, drift: -14, glow: 1, round: 1, lifetime_milliseconds: 620, easing: "cubic-bezier(.2,.6,.3,1)" }, // an enchanted glint
  click:   { count: 5,  colors: ["#fff8e2", "var(--bg3)", "var(--line-hi)"], size: [1.5, 3.5], rise: 16, spread: 34, drift: 8, glow: 0, round: 1, lifetime_milliseconds: 720, easing: "cubic-bezier(.2,.6,.3,1)" }, // disturbed dust
  wood:    { count: 6,  colors: ["#8a5a24", "#6b4413", "#3d2b17"], size: [1.5, 3.5], rise: 8, spread: 26, drift: 34, glow: 0, round: 0, lifetime_milliseconds: 560, easing: "cubic-bezier(.4,0,.7,1)" }, // chips that fall
  stone:   { count: 8,  colors: ["#b9b9c0", "#8f8f98", "#6f6f76"], size: [1.5, 3.5], rise: 10, spread: 30, drift: 40, glow: 0, round: 0, lifetime_milliseconds: 600, easing: "cubic-bezier(.4,0,.7,1)" }, // pale granite chips struck off the slab, falling
  cast:    { count: 46, colors: ["#7c3aed", "#4f46e5", "#a21caf", "#c026d3", "#d946ef"], size: [3.5, 8], mode: "radial", distance: [16, 118], glow: 1, round: 1, start_opacity: 1, lifetime_milliseconds: 780, easing: "cubic-bezier(.1,.75,.3,1)" }, // a true cast: a dense spray of vivid arcane motes blasts out in every direction
  miscast: { count: 30, colors: ["#8b6fb0", "#6f6a94", "#a98a6b", "#7d6f86"], size: [3, 6.5], mode: "fall", spread: 40, rise: 26, drift: 52, glow: 1, round: 1, start_opacity: .9, lifetime_milliseconds: 1000, easing: "cubic-bezier(.35,.02,.7,1)" }, // a miscast: dimmed arcane motes rain down and fade, the working coming apart
};
export function burst(x, y, kind) {
  if (reducedMotion.matches) return;
  const spec = PCL[kind]; if (!spec) return;
  for (let index = 0; index < spec.count; index++) {
    const particle = document.createElement("div");
    particle.className = "pcl";
    const size = spec.size[0] + Math.random() * (spec.size[1] - spec.size[0]);
    const color = spec.colors[(Math.random() * spec.colors.length) | 0];
    particle.style.cssText = `left:${x}px;top:${y}px;width:${size}px;height:${size}px;` +
      (spec.glow ? `background:radial-gradient(circle,${color},transparent 70%);border-radius:50%;`
                 : `background:${color};border-radius:${spec.round ? "50%" : "1px"};`);
    let offsetX, offsetY;
    if (spec.mode === "radial") {                    // blast out in every direction from the heart
      const angle = Math.random() * Math.PI * 2, flightDistance = spec.distance[0] + Math.random() * (spec.distance[1] - spec.distance[0]);
      offsetX = Math.cos(angle) * flightDistance; offsetY = Math.sin(angle) * flightDistance;
    } else if (spec.mode === "fall") {               // sink and fade — the binding comes apart
      offsetX = (Math.random() - 0.5) * spec.spread * 2;
      offsetY = spec.rise * (0.4 + Math.random()) + spec.drift;
    } else {                                          // the fan: dust lifts, chips fall
      offsetX = (Math.random() - 0.5) * spec.spread * 2;
      offsetY = -spec.rise * (0.4 + Math.random()) + spec.drift;
    }
    document.body.appendChild(particle);
    particle.animate(
      [{ transform: "translate(-50%,-50%) scale(1)", opacity: spec.start_opacity ?? 0.9 },
       { transform: `translate(calc(-50% + ${offsetX}px), calc(-50% + ${offsetY}px)) scale(.4)`, opacity: 0 }],
      { duration: spec.lifetime_milliseconds + Math.random() * 200, easing: spec.easing, fill: "forwards" }
    ).onfinish = () => particle.remove();
  }
}
loadToml("global-configs/particles.toml", PCL); // cast/miscast (and pick/click/wood) burst knobs, tweakable without a rebuild
const AUD = {}; loadToml("global-configs/audio.toml", AUD).then(() => window.GhostAudio && GhostAudio.configure(AUD)); // sound knobs, same deal

export function castSigil(anchor, ok) {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return Promise.resolve();
  // always cast at the true center of the screen; the anchor arg is ignored
  // (ponytail: kept in the signature so the call sites don't need touching)
  const cs = getComputedStyle(document.body);
  // Four inks belong to the active theme. Every main fracture carries the full
  // set along its length; forks and released motes pick individual inks from it.
  // The fallbacks keep old third-party tomes legible while the validator nudges
  // authored palettes onto the restored four-ink contract.
  const themeInk = (name, fallback) => cs.getPropertyValue(name).trim() || fallback;
  const sigilInks = [
    themeInk("--sigil-1", "#f7ffff"),
    themeInk("--sigil-2", themeInk("--ac-dim", "#62e8ff")),
    themeInk("--sigil-3", themeInk("--ac", "#00aee8")),
    themeInk("--sigil-4", themeInk("--info", "#315fff")),
  ];
  const keys = Object.keys(GALACTIC);
  const word = []; // min–max distinct letters; a miscast musters only one
  const nL = Math.min(26, SIG.letters.minimum + Math.floor(Math.random() * (SIG.letters.maximum - SIG.letters.minimum + 1))); // a miscast musters the same letters — it just fails to hold them
  for (let i = 0; i < nL; i++)
    word.push(GALACTIC[keys.splice(Math.floor(Math.random() * keys.length), 1)[0]]);
  // px per grid unit → letters stand ~6x this tall, squeezed to fit narrow studies
  const SC = Math.min(SIG.letters.scale, (innerWidth - 60) / (word.length * 3.4 + (word.length - 1) * 1.8));
  const GW = 3.4 * SC, GAP = SC * 1.8, W = word.length * GW + (word.length - 1) * GAP;
  const cx = Math.max(W / 2 + 16, Math.min(innerWidth / 2, innerWidth - W / 2 - 16));
  const cy = Math.max(3 * SC + 16, Math.min(innerHeight / 2, innerHeight - 3 * SC - 16));
  const root = document.createElement("div");
  root.className = "sigil";
  root.style.cssText = `left:${cx}px;top:${cy}px`;
  document.body.appendChild(root);
  const failMs = SIG.fail.charge_milliseconds || 1100;       // miscast: charge this long, then the binding breaks
  const E = ok ? SIG.charge.total_milliseconds : failMs + 1300; // whole life: gather → charge → release/fail → dissipate/fall
  const REL = ok ? SIG.charge.release_fraction : failMs / E;  // the fraction where the working lets go — or snaps
  if (window.GhostAudio) GhostAudio.sigilCast(ok, { ...SIG.sound, fail: SIG.fail, charge_seconds: E * REL / 1000 });
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.classList.add("sigil-lightning");
  svg.setAttribute("aria-hidden", "true");
  root.appendChild(svg);
  const defs = document.createElementNS(NS, "defs");
  svg.appendChild(defs);
  const castToken = Math.random().toString(36).slice(2);
  let spectrumIndex = 0;
  const sigilSpectrum = (rotation = 0) => {
    const gradient = document.createElementNS(NS, "linearGradient");
    const id = `sigil-spectrum-${castToken}-${spectrumIndex++}`;
    gradient.id = id;
    gradient.setAttribute("x1", "0%"); gradient.setAttribute("y1", "0%");
    gradient.setAttribute("x2", "100%"); gradient.setAttribute("y2", "100%");
    sigilInks.forEach((_, index) => {
      const stop = document.createElementNS(NS, "stop");
      stop.setAttribute("offset", `${index * 100 / 3}%`);
      stop.setAttribute("stop-color", sigilInks[(index + rotation) % sigilInks.length]);
      gradient.appendChild(stop);
    });
    defs.appendChild(gradient);
    return `url(#${id})`;
  };
  const liveStrokes = [];
  const runningAnimations = [];
  const releaseTimers = [];
  const lightningPath = (nodes, phase, intensity = 1) => {
    const displaced = nodes.map((pt, index) => {
      const before = nodes[Math.max(0, index - 1)], after = nodes[Math.min(nodes.length - 1, index + 1)];
      const dx = after[0] - before[0], dy = after[1] - before[1], length = Math.hypot(dx, dy) || 1;
      const edge = index === 0 || index === nodes.length - 1;
      // A different transverse throw on every cadence creates large, sharp
      // elbows. Keeping the endpoints nearly bound preserves the glyph.
      const signed = Math.sin(index * 9.73 + phase * 3.17) * .45 + (Math.random() - .5) * 1.1;
      const throw2 = (edge ? .08 : 1) * SIG.lightning.jitter * intensity * signed;
      const along = edge ? 0 : (Math.random() - .5) * SIG.lightning.jitter * intensity * .22;
      const x = pt[0] - dy / length * throw2 + dx / length * along;
      const y = pt[1] + dx / length * throw2 + dy / length * along;
      return [x, y];
    });
    if (displaced.length < 2) return "";
    return displaced.map(([x, y], index) => `${index ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  };
  const forkNodes = (nodes) => {
    if (nodes.length < 3) return null;
    const run = nodes.slice(1).reduce((total, point, index) => total + Math.hypot(point[0] - nodes[index][0], point[1] - nodes[index][1]), 0);
    if (run < 74) return null; // short glyph strokes stay clean, like isolated sparks
    const index = Math.max(1, Math.min(nodes.length - 2, Math.floor(nodes.length * (.3 + Math.random() * .4))));
    const start = nodes[index], before = nodes[index - 1], after = nodes[index + 1];
    const angle = Math.atan2(after[1] - before[1], after[0] - before[0])
      + (Math.random() < .5 ? -1 : 1) * (.58 + Math.random() * .55);
    const length = SIG.lightning.fork_length_minimum
      + Math.random() * (SIG.lightning.fork_length_maximum - SIG.lightning.fork_length_minimum);
    const bend = angle + (Math.random() - .5) * .45;
    return [
      start,
      [start[0] + Math.cos(angle) * length * .48, start[1] + Math.sin(angle) * length * .48],
      [start[0] + Math.cos(bend) * length, start[1] + Math.sin(bend) * length],
    ];
  };
  const svgPath = (cls, color, width) => {
    const path = document.createElementNS(NS, "path");
    path.setAttribute("class", cls);
    path.setAttribute("stroke", color);
    path.setAttribute("stroke-width", width.toFixed(1));
    svg.appendChild(path);
    return path;
  };
  const releaseParticle = (x, y, radius, color, glow, frames, duration, easing = "cubic-bezier(.16,.7,.28,1)") => {
    const mote = document.createElementNS(NS, "circle");
    mote.setAttribute("class", "sigil-release-mote");
    mote.setAttribute("cx", x.toFixed(1));
    mote.setAttribute("cy", y.toFixed(1));
    mote.setAttribute("r", radius.toFixed(1));
    mote.setAttribute("fill", color);
    mote.style.filter = `drop-shadow(0 0 ${(radius * 2.2).toFixed(1)}px ${glow})`;
    svg.appendChild(mote);
    const animation = mote.animate(frames, { duration, fill: "both", easing });
    runningAnimations.push(animation);
    animation.onfinish = () => mote.remove();
  };
  const dissolveStroke = (nodes, gx, width) => {
    if (!root.isConnected) return;
    const flightMs = E * (1 - REL) + 260;
    for (const [x, y] of nodes) {
      const fill = sigilInks[(Math.random() * sigilInks.length) | 0];
      const glow = sigilInks[2 + ((Math.random() * 2) | 0)];
      const angle = Math.atan2(y, x - gx) + (Math.random() - .5) * .34;
      const distance = SIG.burst.distance_minimum + Math.random() * (SIG.burst.distance_maximum - SIG.burst.distance_minimum);
      const dx = Math.cos(angle) * distance, dy = Math.sin(angle) * distance;
      const radius = Math.max(1.4, width * SIG.burst.particle_size * (.75 + Math.random() * .45) / 2);
      releaseParticle(x, y, radius, fill, glow, [
        { transform: "translate(0,0) scale(1)", opacity: .96 },
        { transform: `translate(${(dx * .3).toFixed(1)}px,${(dy * .3).toFixed(1)}px) scale(.82)`, opacity: .9, offset: .3 },
        { transform: `translate(${dx.toFixed(1)}px,${dy.toFixed(1)}px) scale(.18)`, opacity: 0 },
      ], flightMs);
      // As before, each released mote sheds smaller fragments partway through
      // its flight. They begin invisibly on the parent's road, then peel away.
      for (let shard = 0; shard < SIG.burst.shards; shard++) {
        const shardAngle = angle + (Math.random() - .5) * .9;
        const shardDistance = distance * (.42 + Math.random() * .42);
        const sx = dx * .34 + Math.cos(shardAngle) * shardDistance;
        const sy = dy * .34 + Math.sin(shardAngle) * shardDistance;
        releaseParticle(x, y, radius * SIG.burst.shard_size * (.75 + Math.random() * .4), fill, glow, [
          { transform: "translate(0,0) scale(.5)", opacity: 0 },
          { transform: `translate(${(dx * .3).toFixed(1)}px,${(dy * .3).toFixed(1)}px) scale(.5)`, opacity: 0, offset: .28 },
          { transform: `translate(${(dx * .36).toFixed(1)}px,${(dy * .36).toFixed(1)}px) scale(1)`, opacity: .78, offset: .38 },
          { transform: `translate(${sx.toFixed(1)}px,${sy.toFixed(1)}px) scale(.16)`, opacity: 0 },
        ], flightMs);
      }
    }
  };
  const crumbleStroke = (nodes, width) => {
    if (!root.isConnected) return;
    const fallMs = E * (1 - REL) + 360;
    for (const [x, y] of nodes) {
      for (let fleck = 0; fleck < SIG.fail.particles_per_node; fleck++) {
        const ink = sigilInks[(Math.random() * sigilInks.length) | 0];
        const ash = `color-mix(in srgb, ${ink} 42%, #777 58%)`;
        const dx = (Math.random() - .5) * SIG.fail.spread * 2;
        const dy = SIG.fail.fall_distance_minimum
          + Math.random() * (SIG.fail.fall_distance_maximum - SIG.fail.fall_distance_minimum);
        const radius = Math.max(.55, width * SIG.fail.particle_size * (.55 + Math.random() * .5) / 2);
        releaseParticle(x, y, radius, ash, "rgba(170,175,180,.3)", [
          { transform: `translate(${((Math.random() - .5) * 4).toFixed(1)}px,${((Math.random() - .5) * 3).toFixed(1)}px) scale(1)`, opacity: .76 },
          { transform: `translate(${(dx * .16).toFixed(1)}px,-${(2 + Math.random() * 5).toFixed(1)}px) scale(.86)`, opacity: .7, offset: .14 },
          { transform: `translate(${(dx * .5).toFixed(1)}px,${(dy * .34).toFixed(1)}px) scale(.54)`, opacity: .48, offset: .5 },
          { transform: `translate(${dx.toFixed(1)}px,${dy.toFixed(1)}px) scale(.1)`, opacity: 0 },
        ], fallMs * (.82 + Math.random() * .3), "cubic-bezier(.42,.02,.82,.62)");
      }
    }
  };

  word.forEach((strokes, li) => {
    const gx = -W / 2 + GW / 2 + li * (GW + GAP); // this letter's heart, relative to root
    // Resample every glyph stroke into one connected curve. A one-point mark
    // becomes a small crescent flourish instead of a circular mote.
    for (const st of strokes) {
      const pts = [];
      if (st.length === 1) {
        const [x, y] = st[0];
        pts.push([x - .22, y + .12], [x - .12, y - .2], [x + .16, y - .18], [x + .22, y + .08], [x, y + .2]);
      } else {
        for (let s2 = 1; s2 < st.length; s2++) {
          const [x1, y1] = st[s2 - 1], [x2, y2] = st[s2];
          const steps = Math.max(2, Math.round(Math.hypot(x2 - x1, y2 - y1) / SIG.letters.spacing));
          for (let k = s2 > 1 ? 1 : 0; k <= steps; k++)
            pts.push([x1 + (x2 - x1) * k / steps, y1 + (y2 - y1) * k / steps]);
        }
      }
      const nodes = pts.map(([x, y]) => [gx + (x - 1.7) * SC, (y - 3) * SC]);
      const width = SIG.lightning.width_minimum + Math.random() * (SIG.lightning.width_maximum - SIG.lightning.width_minimum);
      const rotation = spectrumIndex % sigilInks.length;
      const spectrum = sigilSpectrum(rotation);
      const whiteHalo = svgPath("sigil-white-halo", "rgba(255,255,255,.96)", SIG.lightning.glow_width * .72);
      const veil = svgPath("sigil-aether-veil", spectrum, SIG.lightning.glow_width * 2.25);
      const aura = svgPath("sigil-lightning-aura", spectrum, SIG.lightning.glow_width);
      const line = svgPath("sigil-lightning-line", spectrum, width);
      const hot = svgPath("sigil-lightning-hot", "rgba(255,255,255,.88)", Math.max(1.7, width * .42));
      const phase = Math.random() * Math.PI * 2;
      const firstD = lightningPath(nodes, phase, .35);
      whiteHalo.setAttribute("d", firstD); veil.setAttribute("d", firstD); aura.setAttribute("d", firstD); line.setAttribute("d", firstD); hot.setAttribute("d", firstD);
      const group = document.createElementNS(NS, "g");
      svg.insertBefore(group, whiteHalo);
      // The colored bloom spreads furthest back. The white corona sits directly
      // beneath the solid spectrum so parchment cannot tint it away.
      group.append(veil, aura, whiteHalo, line, hot);
      const halos = [{ path: whiteHalo, width: SIG.lightning.glow_width }];
      const geometries = [{ nodes, paths: [whiteHalo, veil, aura, line, hot], energy: 1 }];
      const forkCount = Math.floor(SIG.lightning.forks_minimum + Math.random() * (SIG.lightning.forks_maximum - SIG.lightning.forks_minimum + 1));
      for (let fork = 0; fork < forkCount; fork++) {
        const branch = forkNodes(nodes);
        if (!branch) continue;
        const forkInk = sigilInks[(rotation + fork + 1) % sigilInks.length];
        const forkHalo = svgPath("sigil-white-halo sigil-lightning-fork", "rgba(255,255,255,.94)", SIG.lightning.glow_width * .38);
        const forkAura = svgPath("sigil-lightning-aura sigil-lightning-fork", forkInk, SIG.lightning.glow_width * .62);
        const forkLine = svgPath("sigil-lightning-line sigil-lightning-fork", forkInk, width * .68);
        const forkHot = svgPath("sigil-lightning-hot sigil-lightning-fork", "rgba(255,255,255,.82)", Math.max(.8, width * .22));
        const forkD = lightningPath(branch, phase + fork * .7, .22);
        forkHalo.setAttribute("d", forkD); forkAura.setAttribute("d", forkD); forkLine.setAttribute("d", forkD); forkHot.setAttribute("d", forkD);
        group.append(forkAura, forkHalo, forkLine, forkHot);
        halos.push({ path: forkHalo, width: SIG.lightning.glow_width * .62 });
        geometries.push({ nodes: branch, paths: [forkHalo, forkAura, forkLine, forkHot], energy: SIG.lightning.fork_energy });
      }
      liveStrokes.push({ geometries, phase });

      const frames = [
        { transform: `translate(${((Math.random() - .5) * 50).toFixed(1)}px,${((Math.random() - .5) * 50).toFixed(1)}px) scale(.25)`, opacity: 0, easing: "cubic-bezier(.2,.6,.3,1)" },
        { transform: "translate(0,0) scale(1)", opacity: .92, offset: .08, easing: "ease-in-out" },
      ];
      const nj = Math.max(8, Math.round((SIG.charge.poses_minimum + SIG.charge.poses_maximum) / 2));
      let prevOff = .08;
      for (let j = 1; j <= nj; j++) {
        const g2 = j / nj, gi = ok ? g2 : Math.min(g2, .6);
        prevOff = Math.min(REL, Math.max(prevOff, .08 + Math.pow(g2, .7) * (REL - .08)));
        frames.push({
          transform: `translate(${((Math.random() - .5) * (2 + gi * SIG.charge.shake)).toFixed(1)}px,${((Math.random() - .5) * (2 + gi * SIG.charge.shake)).toFixed(1)}px) scale(${(1 + gi * SIG.charge.grow * .22).toFixed(3)})`,
          opacity: (ok && j === nj) ? 1 : .68 + Math.random() * .3,
          offset: prevOff,
          easing: j === nj ? "ease-out" : "ease-in-out",
        });
      }
      if (ok) {
        // The living fracture holds through the charge, then gives its shape to
        // the old mote-and-shard release instead of flying away as a whole.
        frames.push({ transform: "translate(0,0) scale(1.03)", opacity: 1, offset: REL });
        frames.push({ transform: "translate(0,0) scale(.98)", opacity: 0, offset: Math.min(.99, REL + .055), easing: "ease-out" });
        frames.push({ transform: "translate(0,0) scale(.98)", opacity: 0 });
        releaseTimers.push(setTimeout(() => dissolveStroke(nodes, gx, width), E * REL));
      } else {
        // The binding snaps in place. The paths themselves vanish; their shape
        // is handed to falling ash particles instead of dropping as whole letters.
        frames.push({ transform: "translate(0,2px) scale(.98)", opacity: .12, offset: Math.min(.99, REL + .045), easing: "ease-out" });
        frames.push({ transform: "translate(0,2px) scale(.98)", opacity: 0 });
        const crumbleNodes = geometries.flatMap((geometry) => geometry.nodes);
        releaseTimers.push(setTimeout(() => crumbleStroke(crumbleNodes, width), E * REL));
        group.animate([
          { filter: "saturate(1)" },
          { filter: "saturate(1)", offset: REL, easing: "ease-in" },
          { filter: `saturate(${(SIG.palette.saturation_miscast / SIG.palette.saturation).toFixed(2)})` },
        ], { duration: E, fill: "both" });
      }
      const motion = group.animate(frames, { duration: E, fill: "both" });
      const current = hot.animate([
        { opacity: .72 },
        { opacity: 1 },
        { opacity: .58 },
        { opacity: .94 },
      ], { duration: 180 + Math.random() * 160, iterations: Infinity, easing: "steps(3, end)" });
      const breath = aura.animate([
        { opacity: .18 },
        { opacity: .52 },
        { opacity: .24 },
      ], { duration: 900 + Math.random() * 650, iterations: Infinity, easing: "ease-in-out" });
      const haloAnimations = halos.map(({ path, width: haloWidth }) => path.animate([
        { opacity: 0, strokeWidth: `${(haloWidth * .34).toFixed(1)}px` },
        { opacity: .12, strokeWidth: `${(haloWidth * .52).toFixed(1)}px`, offset: .08 },
        { opacity: ok ? .42 : .3, strokeWidth: `${(haloWidth * .88).toFixed(1)}px`, offset: Math.max(.08, REL * .55), easing: "ease-in" },
        { opacity: ok ? .94 : .62, strokeWidth: `${(haloWidth * 1.5).toFixed(1)}px`, offset: REL, easing: "ease-out" },
        { opacity: 0, strokeWidth: `${(haloWidth * 1.76).toFixed(1)}px`, offset: Math.min(1, REL + (1 - REL) * .24) },
        { opacity: 0, strokeWidth: `${(haloWidth * 1.76).toFixed(1)}px` },
      ], { duration: E, fill: "both" }));
      runningAnimations.push(motion, current, breath, ...haloAnimations);
      motion.onfinish = () => {
        current.cancel(); breath.cancel();
        for (const animation of haloAnimations) animation.cancel();
        group.remove();
      };
    }
  });

  let raf = 0, lastJolt = -Infinity;
  const started = performance.now();
  const writhe = (now) => {
    const elapsed = now - started;
    if (elapsed < E && root.isConnected) {
      const charge = Math.min(1, elapsed / Math.max(1, E * REL));
      const successSurge = Math.pow(charge, 1.65);
      const cadence = ok
        ? SIG.lightning.success_cadence_start_milliseconds
          + (SIG.lightning.success_cadence_peak_milliseconds - SIG.lightning.success_cadence_start_milliseconds) * successSurge
        : SIG.lightning.cadence_milliseconds;
      if (now - lastJolt >= cadence) {
        // A successful binding begins readable, then becomes violently unstable
        // as release approaches. Miscasts retain their shorter, steadier charge.
        const intensity = ok
          ? .2 + successSurge * (SIG.lightning.success_jitter_peak - .2)
          : .32 + charge * .68;
        for (const stroke of liveStrokes) {
          stroke.phase += .28 + Math.random() * .22;
          for (const geometry of stroke.geometries) {
            const d = lightningPath(geometry.nodes, stroke.phase, intensity * geometry.energy);
            for (const path of geometry.paths) path.setAttribute("d", d);
          }
        }
        lastJolt = now;
      }
      raf = requestAnimationFrame(writhe);
    }
  };
  raf = requestAnimationFrame(writhe);
  return new Promise((resolve) => {
    setTimeout(() => {
      cancelAnimationFrame(raf);
      for (const timer of releaseTimers) clearTimeout(timer);
      for (const animation of runningAnimations) animation.cancel();
      root.remove();
      resolve();
    }, E + 800); // sweep whatever the onfinishes missed, then report a complete cast
  });
}
window.castSigil = castSigil; // console-reachable: lets you audition a palette's sigil colors
