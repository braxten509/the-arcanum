/* Spell sigils, verdict motes, and the just-enough TOML reader that tunes them.

   Every cast spells 3–6 letters of the Standard Galactic Alphabet — the
   enchanters' script — out of semi-stable arcane motes that strain against
   the binding, charging white-hot for ~3s, then dissipate in ONE release: each
   mote drifts straight out from its letter's heart, breaking into smaller
   shards as it fades. every mote lights itself; there is no candle-glow
   here. a miscast charges the same — same letters, same colour — then the
   binding breaks: it greys and falls as ash.
   transform/opacity only; gated by the same preference as the candle embers.
   strokes live on a ~3.4x6 grid (y down); a 1-point stroke is a heavy dot.
   every knob below (particles AND sound) is tuned by global-configs/sigil.toml — these
   are the fallback defaults when the file or a key is missing. */
const SIG = {
  letters: { minimum: 3, maximum: 6, scale: 28, spacing: .3 },
  palette: { hue_minimum: 200, hue_maximum: 320, saturation: 85, saturation_miscast: 30 },
  motes: { size_minimum: 4, size_maximum: 6, dot_size: 10, glow: 3 },
  charge: { total_milliseconds: 4000, release_fraction: .75, poses_minimum: 18, poses_maximum: 22, shake: 7, grow: .25 },
  halo: { size: 6, peak_opacity: 1 },
  burst: { distance_minimum: 160, distance_maximum: 400, shards: 2, shard_size: .45 },
  sound: { enabled: true, volume: 100, charge_hertz_from: 110, charge_hertz_to: 440, shimmer: .5, burst_gain: .6, miscast: true },
  fail: { charge_milliseconds: 1100, start: .9, tail: 1.1, gain: 2, fade: .3 }, // miscast: charge_milliseconds, then the break, then how cast-fail.mp3 is played
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
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  // always cast at the true center of the screen; the anchor arg is ignored
  // (ponytail: kept in the signature so the call sites don't need touching)
  const cs = getComputedStyle(document.body);
  // arcane palette: sky-blue → indigo → violet → magenta, one hue per mote;
  // light parchment takes deep inks, dark pages take bright self-lit motes
  const chan = (cs.getPropertyValue("--bg1").match(/[0-9a-f]{2}/gi) || []).slice(0, 3).map((h) => parseInt(h, 16));
  const lightBg = chan.reduce((a2, b2) => a2 + b2, 0) > 380;
  const arcane = (sat) => {
    const hue = (SIG.palette.hue_minimum + Math.random() * (SIG.palette.hue_maximum - SIG.palette.hue_minimum)).toFixed(0);
    return {
      fill: `hsl(${hue} ${sat}% ${(lightBg ? 30 + Math.random() * 12 : 62 + Math.random() * 16).toFixed(0)}%)`,
      glow: `hsl(${hue} ${sat}% ${lightBg ? 46 : 72}% / .85)`,
    };
  };
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
  const piece = (cls, css) => {
    const p = document.createElement("div");
    p.className = cls;
    p.style.cssText = css;
    root.appendChild(p);
    return p;
  };
  const kill = (anim, el2) => { anim.onfinish = () => el2.remove(); };
  const C = "translate(-50%,-50%)"; // every piece self-centers on its left/top
  // semi-stable: a bound mote never quite sits still — a fresh strained pose per keyframe
  const strain = (amp, grow) =>
    `${C} translate(${((Math.random() - .5) * amp).toFixed(1)}px,${((Math.random() - .5) * amp).toFixed(1)}px) scale(${grow})`;

  word.forEach((strokes, li) => {
    const gx = -W / 2 + GW / 2 + li * (GW + GAP); // this letter's heart, relative to root
    // walk each stroke, seeding a mote every `spacing` grid units; lone points are heavy dots
    const pts = [];
    for (const st of strokes) {
      if (st.length === 1) { pts.push([st[0][0], st[0][1], 1]); continue; }
      for (let s2 = 1; s2 < st.length; s2++) {
        const [x1, y1] = st[s2 - 1], [x2, y2] = st[s2];
        const steps = Math.max(1, Math.round(Math.hypot(x2 - x1, y2 - y1) / SIG.letters.spacing));
        for (let k = s2 > 1 ? 1 : 0; k <= steps; k++)
          pts.push([x1 + (x2 - x1) * k / steps, y1 + (y2 - y1) * k / steps, 0]);
      }
    }
    for (const [px2, py2, dot] of pts) {
      const hx = gx + (px2 - 1.7) * SC, hy = (py2 - 3) * SC;
      const sz = dot ? SIG.motes.dot_size : SIG.motes.size_minimum + Math.random() * (SIG.motes.size_maximum - SIG.motes.size_minimum);
      const { fill, glow } = arcane(SIG.palette.saturation); // a miscast starts at the true colour and greys as it falls
      const p = piece("sigil-p", `left:${hx.toFixed(1)}px;top:${hy.toFixed(1)}px;width:${sz.toFixed(1)}px;height:${sz.toFixed(1)}px;background:${fill};box-shadow:0 0 ${(sz * SIG.motes.glow).toFixed(0)}px ${glow}`);
      // keyframe timeline: gather 0–.08 · strain + charge .08–REL · then the
      // working either releases (dissipate) or, on a miscast, snaps (fall).
      // Same charge for both — same letters, same colour — it just fails to hold.
      // NB: options-level easing would warp the WHOLE timeline (WAAPI, unlike
      // CSS), crushing the hold — so every segment eases on its own keyframe
      const frames = [
        { transform: `${C} translate(${((Math.random() - .5) * 50).toFixed(1)}px,${((Math.random() - .5) * 50).toFixed(1)}px) scale(.2)`, opacity: 0, easing: "cubic-bezier(.2,.6,.3,1)" },
        { transform: C, opacity: .9, offset: .08, easing: "ease-in-out" },
      ];
      // the unstable hold: ~20 strained poses per mote, each on its own
      // slightly shifted clock so the letter seethes instead of stepping in
      // unison — and everything escalates with the charge: wider throws,
      // deeper flicker, swelling size, quickening tempo (poses cluster late)
      const nj = SIG.charge.poses_minimum + Math.floor(Math.random() * (SIG.charge.poses_maximum - SIG.charge.poses_minimum + 1));
      // the unstable hold. a miscast caps intensity (gi) at ~60% so it never
      // looks fully bound; the timing still runs the whole hold either way.
      // NB WAAPI needs non-decreasing offsets — with a short charge (small REL)
      // the per-pose jitter can outrun the gap between poses and reverse one,
      // which makes animate() throw and the sigil vanish. clamp each offset to
      // the previous so it can't go backwards. (charge floor ~150ms: below that
      // REL < the .08 gather and even the clamp can't order it — nobody charges
      // that fast.) ponytail: clamp is enough for any sane fail_ms/charge.
      let prevOff = .08;
      for (let j = 1; j <= nj; j++) {
        const g2 = j / nj; // how deep into the hold — timing scales off this
        const gi = ok ? g2 : Math.min(g2, .6); // charge intensity — capped on a miscast
        prevOff = Math.min(REL, Math.max(prevOff, .08 + Math.pow(g2, .7) * (REL - .08) + (j < nj ? (Math.random() - .5) * .012 : 0)));
        frames.push({
          transform: strain(2 + gi * SIG.charge.shake + Math.random() * 2, 1 + gi * SIG.charge.grow),
          opacity: (ok && j === nj) ? 1 : .95 - Math.random() * (.15 + gi * .5),
          offset: prevOff,
          easing: j === nj ? "ease-out" : "ease-in-out",
        });
      }
      if (ok) {
        // ONE release, every mote on the same clock: each drifts straight out
        // from the letter's heart — top rises, bottom sinks, flanks slide wide
        const a2 = Math.atan2(hy, hx - gx) + (Math.random() - .5) * .35;
        const d2 = SIG.burst.distance_minimum + Math.random() * (SIG.burst.distance_maximum - SIG.burst.distance_minimum);
        const dx = Math.cos(a2) * d2, dy = Math.sin(a2) * d2;
        frames.push({ transform: `${C} translate(${dx.toFixed(0)}px,${dy.toFixed(0)}px) scale(.3)`, opacity: 0 });
        kill(p.animate(frames, { duration: E, fill: "both" }), p);
        // the white halo BEHIND each mote: a soft radial glow that charges from
        // nothing to bright through the binding, peaks at release, dies after
        const wg = piece("sigil-p", `left:${hx.toFixed(1)}px;top:${hy.toFixed(1)}px;width:${(sz * SIG.halo.size).toFixed(1)}px;height:${(sz * SIG.halo.size).toFixed(1)}px;background:radial-gradient(circle, rgba(255,255,255,.95), rgba(255,255,255,0) 70%);box-shadow:0 0 ${(sz * SIG.halo.size * 1.5).toFixed(0)}px rgba(255,255,255,.6)`);
        root.insertBefore(wg, p); // halo sits under its mote, never over it
        kill(wg.animate([
          { transform: `${C} scale(.25)`, opacity: 0 },
          { transform: `${C} scale(.35)`, opacity: .08, offset: .08, easing: "ease-in-out" },
          { transform: `${C} scale(.75)`, opacity: .5 * SIG.halo.peak_opacity, offset: (.08 + REL) / 2, easing: "ease-in-out" }, // clearly aglow by mid-charge
          { transform: `${C} scale(1.15)`, opacity: SIG.halo.peak_opacity, offset: REL, easing: "ease-out" },
          { transform: `${C} scale(2.2)`, opacity: 0, offset: REL + (1 - REL) * .72 },
          { transform: `${C} scale(2.2)`, opacity: 0 },
        ], { duration: E, fill: "both" }), wg);
        // mid-flight the mote breaks up: smaller shards peel off where the
        // parent has thinned (~30% of the road out) and scatter on their own.
        // ~1000 animated motes on a 6-letter cast — thin this loop first if a
        // weaker study ever stutters
        for (let s3 = 0; s3 < SIG.burst.shards; s3++) {
          const a3 = a2 + (Math.random() - .5) * .8, d3 = d2 * (.4 + Math.random() * .5);
          const sz3 = sz * SIG.burst.shard_size * (.8 + Math.random() * .4);
          const sx = dx * .36 + Math.cos(a3) * d3, sy = dy * .36 + Math.sin(a3) * d3;
          const sh = piece("sigil-p", `left:${hx.toFixed(1)}px;top:${hy.toFixed(1)}px;width:${sz3.toFixed(1)}px;height:${sz3.toFixed(1)}px;background:${fill};box-shadow:0 0 ${(sz3 * SIG.motes.glow).toFixed(0)}px ${glow}`);
          kill(sh.animate([
            { transform: C, opacity: 0 },
            { transform: `${C} translate(${(dx * .32).toFixed(0)}px,${(dy * .32).toFixed(0)}px)`, opacity: 0, offset: REL + (1 - REL) * .28 },
            { transform: `${C} translate(${(dx * .36).toFixed(0)}px,${(dy * .36).toFixed(0)}px)`, opacity: .85, offset: REL + (1 - REL) * .4, easing: "ease-out" },
            { transform: `${C} translate(${sx.toFixed(0)}px,${sy.toFixed(0)}px) scale(.4)`, opacity: 0 },
          ], { duration: E, fill: "both" }), sh);
        }
      } else {
        // the binding snaps at REL: one last flail, then the letter loses its
        // hold and falls as ash — every mote off the same charge, so they break
        // together, then scatter down on their own
        frames.push({ transform: strain(8, .9), opacity: .55, offset: REL + (1 - REL) * .18, easing: "cubic-bezier(.4,.1,.7,.4)" }); // the grip slips — shrinks and dims, doesn't surge
        frames.push({ transform: strain(5, .95), opacity: .4, offset: REL + (1 - REL) * .42, easing: "ease-in" });
        frames.push({ transform: `${C} translate(${((Math.random() - .5) * 34).toFixed(1)}px,${(40 + Math.random() * 55).toFixed(1)}px) scale(.3)`, opacity: 0 });
        kill(p.animate(frames, { duration: E, fill: "both" }), p);
        // greys as it falls: the true colour holds through the charge, then
        // desaturates to the miscast tint by the time it hits the floor
        p.animate([
          { filter: "saturate(1)" },
          { filter: "saturate(1)", offset: REL, easing: "ease-in" },
          { filter: `saturate(${(SIG.palette.saturation_miscast / SIG.palette.saturation).toFixed(2)})` },
        ], { duration: E, fill: "both" });
      }
    }
  });
  setTimeout(() => root.remove(), E + 800); // sweep whatever the onfinishes missed
}
window.castSigil = castSigil; // console-reachable: lets you audition a palette's sigil colors
