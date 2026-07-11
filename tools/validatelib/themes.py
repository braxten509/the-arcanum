"""The 22-ink theme palette contract + palette distinctness."""
import colorsys
import os
import re

from . import SKINS_DIR, THEME_VARS, COIN_FACES, err, global_skin_ids, load_toml, warn


def _hex_hsl(value):
    """#rgb/#rrggbb -> (hue 0-360, sat 0-1, light 0-1), or None if not a hex color."""
    m = re.fullmatch(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", str(value).strip())
    if not m:
        return None
    hx = m.group(1)
    if len(hx) == 3:
        hx = "".join(c * 2 for c in hx)
    r, g, b = (int(hx[i:i + 2], 16) / 255 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360, s, l


def check_themes(m, label):
    """Returns (theme_ids, granted_earned_id) — check_shop needs both joints."""
    themes = m.get("themes", [])
    if not isinstance(themes, list) or not themes:
        err(label, "[[themes]] — at least one signature palette is required")
        return set(), None
    theme_ids, earned_ids = set(), set()
    for th in themes:
        if not isinstance(th, dict):
            err(label, "[[themes]] entries must be tables")
            continue
        tid = th.get("id")
        if not tid:
            err(label, "[[themes]] entry is missing id")
        else:
            theme_ids.add(tid)
            if th.get("earned") is True:
                earned_ids.add(tid)
        coin = th.get("coin")
        if coin is not None and coin not in COIN_FACES:
            err(label, f"[[themes]] {tid!r}: coin {coin!r} is not a known coin face — "
                       "pick one of: " + ", ".join(sorted(COIN_FACES)))
        present = set(th.get("vars", {}) or {})
        missing = THEME_VARS - present
        if missing:
            err(label, f"[[themes]] {tid!r}: missing theme var(s): "
                       + ", ".join(sorted(missing)))
        extra = present - THEME_VARS
        if extra:
            warn(label, f"[[themes]] {tid!r}: unknown theme var(s): " + ", ".join(sorted(extra)))
        # `candle` is consumed as rgba(var(--candle), .x), so it MUST be a bare
        # "r, g, b" triple — a hex like "#39ff14" makes rgba(#39ff14, .x), invalid
        # CSS, and the whole candlelight glow silently fails to render.
        candle = str((th.get("vars", {}) or {}).get("candle", "")).strip()
        if candle and not re.fullmatch(r"\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}", candle):
            err(label, f"[[themes]] {tid!r}: candle must be a bare \"r, g, b\" triple (e.g. "
                       f'"255, 172, 66"), not {candle!r} — it is used as rgba(var(--candle), …), '
                       "so a hex or rgb() wrapper renders no candlelight")
        # bg1 is the PARCHMENT — the page the student reads on. Paper is warm or
        # near-neutral; a cool hue may carry only a whisper of tint. Calibration: the
        # reference night palettes (midnight h252, starlit h229) sit at 6–7% chroma and
        # pass; the true-sight build shipped purple paper (h274 at 16% chroma) under a
        # contract that says bg1 = parchment. Chroma = sat scaled by distance from
        # black/white, so a pale ice or deep night tint stays legal — dye does not.
        bg1 = (th.get("vars", {}) or {}).get("bg1", "")
        hsl = _hex_hsl(bg1)
        if hsl:
            h, s, l = hsl
            chroma = s * (1 - abs(2 * l - 1))
            if not (10 <= h <= 95) and chroma > 0.10:
                warn("content", f"[[themes]] {tid!r}: bg1 {bg1!r} is the parchment but reads "
                     f"hue {round(h)}° at {round(chroma * 100)}% chroma — dyed paper, not "
                     "parchment. Paper is warm (hue 10–95°) or near-neutral; keep a cool "
                     "tint under 10% chroma (the reference night palettes run 6–7%). Put "
                     "the theme's color in bg0, the panels, and the accents — not the page")

    if len(theme_ids) < 3:
        warn(label, f"only {len(theme_ids)} theme palette(s) — spec wants 3–5 distinct "
                    "palettes (a signature default, 2–3 purchasable, optionally 1 earned)")

    defaults = m.get("defaults", {})
    dtheme = defaults.get("theme") if isinstance(defaults, dict) else None
    if dtheme is not None and dtheme not in theme_ids and dtheme not in global_skin_ids():
        err(label, f"[defaults] theme {dtheme!r} is neither a [[themes]] id in this "
                   "tome nor a global skin id under skins/")

    earned_ref = (m.get("progression", {}) or {}).get("earnedTheme", {})
    granted = None
    if isinstance(earned_ref, dict) and earned_ref.get("id"):
        granted = earned_ref["id"]
        if granted not in theme_ids:
            err(label, f"[progression.earnedTheme] id {granted!r} has no matching [[themes]] entry")
        elif granted not in earned_ids:
            err(label, f"[progression.earnedTheme] id {granted!r} must mark that theme earned = true")
    # the reverse direction: an earned = true palette nothing grants is dead content —
    # it can never appear in the picker, and the atk-ice badge chain dangles with it.
    orphans = earned_ids - ({granted} if granted else set())
    if orphans:
        err(label, f"theme(s) {sorted(orphans)} are earned = true but no [progression.earnedTheme] "
                   "grants them — unobtainable dead content (wire [progression.earnedTheme] to one, "
                   "or drop the earned flag)")
    return theme_ids, granted


def _var_rgb(s):
    """A theme var as an (r, g, b) tuple — hex (#rgb/#rrggbb) or the candle's
    bare "r, g, b" triple. None for rgba() washes and anything unparseable."""
    s = str(s).strip()
    m = re.fullmatch(r"(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})", s)
    if m:
        return tuple(int(g) for g in m.groups())
    s = s.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if re.fullmatch(r"[0-9a-fA-F]{6}", s):
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    return None


def _palette_dist(a, b):
    """Mean per-channel distance (0–255) across the vars parseable in both
    palettes. Calibration: an untouched scaffold palette is 0 from Sepia Vellum;
    the shipped genuinely-distinct palettes measure 11+ from it and each other."""
    tot, n = 0, 0
    for k in THEME_VARS:
        ra, rb = _var_rgb(a.get(k, "")), _var_rgb(b.get(k, ""))
        if ra and rb:
            tot += sum(abs(x - y) for x, y in zip(ra, rb)) / 3
            n += 1
    return tot / n if n else None


# below this mean channel distance two palettes read as the same look
PALETTE_MIN_DIST = 8


def check_theme_distinctness(m, label):
    """Every palette must be measurably distinct from the global Sepia Vellum
    baseline AND from this tome's other palettes. The scaffold's placeholder
    vars ARE vellum's values — a run that keeps them ships a replica renamed
    (the hex-forge failure). Hard-gate 'content' WARNs (--strict fails them)."""
    vell, _ = load_toml(os.path.join(SKINS_DIR, "vellum", "skin.toml"))
    vell_vars = (vell or {}).get("vars", {})
    themes = [t for t in (m.get("themes") or []) if isinstance(t, dict)]
    for i, th in enumerate(themes):
        tv = th.get("vars", {}) or {}
        d = _palette_dist(tv, vell_vars)
        if d is not None and d < PALETTE_MIN_DIST:
            warn("content", f"[[themes]] {th.get('id')!r} is a near-copy of the global Sepia "
                 f"Vellum palette (mean channel distance {d:.1f} < {PALETTE_MIN_DIST}) — the "
                 "scaffold placeholder IS vellum; design this course's own palette (all 22 vars)")
        for other in themes[i + 1:]:
            d2 = _palette_dist(tv, other.get("vars", {}) or {})
            if d2 is not None and d2 < PALETTE_MIN_DIST:
                warn("content", f"[[themes]] {th.get('id')!r} and {other.get('id')!r} are "
                     f"near-identical (mean channel distance {d2:.1f} < {PALETTE_MIN_DIST}) — "
                     "palettes must differ in paper tint, accent ink, and candle")
