"""The 22-ink theme palette contract + palette distinctness."""
import colorsys
import os
import re

from . import REPO, SKINS_DIR, THEME_VARS, COIN_FACES, err, global_skin_ids, load_toml, warn


SIGIL_KEYS = ("sigil-1", "sigil-2", "sigil-3", "sigil-4")


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
            warn(label, f"[[themes]] {tid!r}: unknown theme var(s): " + ", ".join(sorted(extra)),
                 phase=6)
        for key in SIGIL_KEYS:
            value = (th.get("vars", {}) or {}).get(key)
            if value is not None and _hex_hsl(value) is None:
                err(label, f"[[themes]] {tid!r}: {key} must be a hex color (#rgb or #rrggbb), "
                           f"not {value!r}")
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
                     "the theme's color in bg0, the panels, and the accents — not the page",
                     phase=6)

    if len(theme_ids) < 3:
        warn(label, f"only {len(theme_ids)} theme palette(s) — spec wants 3–5 distinct "
                    "palettes (a signature default, 2–3 purchasable, optionally 1 earned)",
             phase=6)

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


def _sigil_fingerprint(theme):
    """An order-independent, normalized fingerprint for a theme's four sigil inks.

    Reordering the same colors between core/body/bloom/fringe must not evade the
    cross-tome uniqueness rule. Missing or invalid colors are handled by the
    ordinary theme contract and skipped here to avoid duplicate diagnostics.
    """
    values = [_var_rgb((theme.get("vars", {}) or {}).get(key, "")) for key in SIGIL_KEYS]
    return tuple(sorted(values)) if all(value is not None for value in values) else None


def _themes_from_tome(tome_dir):
    """Read only a tome's theme bank, whether split or inline."""
    split = os.path.join(tome_dir, "themes.toml")
    source = split if os.path.isfile(split) else os.path.join(tome_dir, "tome.toml")
    data, problem = load_toml(source)
    if problem or not isinstance(data, dict):
        return []
    themes = data.get("themes", [])
    return themes if isinstance(themes, list) else []


def check_sigil_palette_uniqueness(m, tome_path, label, tomes_root=None):
    """Hard-error identical four-ink sigil sets at the owning Phase 6 gate.

    Platform skins under skins/ are intentionally outside this scan: global
    themes may share a sigil set with any tome. Fingerprints are color sets, so
    merely shuffling the same four colors between sigil-1…sigil-4 still collides.
    """
    root = os.path.realpath(tomes_root or os.path.join(REPO, "tomes"))
    current_path = os.path.realpath(tome_path)
    current_id = os.path.basename(current_path)
    current = [theme for theme in (m.get("themes", []) or []) if isinstance(theme, dict)]

    others = []
    try:
        entries = sorted(os.scandir(root), key=lambda entry: entry.name)
    except OSError:
        entries = []
    for entry in entries:
        if not entry.is_dir() or os.path.realpath(entry.path) == current_path:
            continue
        for theme in _themes_from_tome(entry.path):
            if isinstance(theme, dict):
                others.append((entry.name, theme))

    # Include sibling palettes in the current tome as well: a four-ink set may
    # appear only once among authored tome themes, regardless of folder.
    records = [(current_id, theme) for theme in current] + others
    for theme in current:
        fingerprint = _sigil_fingerprint(theme)
        if fingerprint is None:
            continue
        duplicates = []
        for other_index, (other_tome, other) in enumerate(records):
            if other_tome == current_id and other is theme:
                continue
            if _sigil_fingerprint(other) == fingerprint:
                duplicates.append(f"{other_tome}/{other.get('id', '?')}")
        if duplicates:
            colors = ", ".join(str((theme.get("vars", {}) or {}).get(key)) for key in SIGIL_KEYS)
            err(label, f"[[themes]] {theme.get('id')!r}: sigil color set [{colors}] duplicates "
                       f"{', '.join(sorted(set(duplicates)))} — every authored tome theme must "
                       "change at least one of sigil-1…sigil-4; global skin themes are exempt",
                phase=6)


# Below this mean channel distance two palettes read as the same look. The
# default palette carries a tome's first impression, so it must clear a
# slightly stronger Vellum-distance floor than optional variants.
PALETTE_MIN_DIST = 8
DEFAULT_PALETTE_MIN_DIST = 10


def check_theme_distinctness(m, label):
    """Every palette must be measurably distinct from the global Sepia Vellum
    baseline AND from this tome's other palettes. The scaffold's placeholder
    vars ARE vellum's values — a run that keeps them ships a replica renamed
    (the hex-forge failure). These warnings hard-gate in their owning Phase 6."""
    vell, _ = load_toml(os.path.join(SKINS_DIR, "vellum", "skin.toml"))
    vell_vars = (vell or {}).get("vars", {})
    themes = [t for t in (m.get("themes") or []) if isinstance(t, dict)]
    defaults = m.get("defaults", {}) if isinstance(m.get("defaults"), dict) else {}
    default_id = defaults.get("theme")
    for i, th in enumerate(themes):
        tv = th.get("vars", {}) or {}
        d = _palette_dist(tv, vell_vars)
        floor = DEFAULT_PALETTE_MIN_DIST if th.get("id") == default_id else PALETTE_MIN_DIST
        if d is not None and d < floor:
            role = "default " if th.get("id") == default_id else ""
            warn("content", f"[[themes]] {th.get('id')!r} is a near-copy of the global Sepia "
                 f"Vellum palette ({role}mean channel distance {d:.1f} < {floor}) — the "
                 "scaffold placeholder IS vellum; design this course's own palette (all 22 vars)",
                 phase=6)
        for other in themes[i + 1:]:
            d2 = _palette_dist(tv, other.get("vars", {}) or {})
            if d2 is not None and d2 < PALETTE_MIN_DIST:
                warn("content", f"[[themes]] {th.get('id')!r} and {other.get('id')!r} are "
                     f"near-identical (mean channel distance {d2:.1f} < {PALETTE_MIN_DIST}) — "
                     "palettes must differ in paper tint, accent ink, and candle", phase=6)
