#!/usr/bin/env python3
"""validate_tome.py — hold a tome up to the candlelight before you ship it.

Machine-checks one tome folder against the rules in TOME-AUTHORING.md: does the
TOML parse, do the ids line up, does every palette carry all 18 inks, do the
rubric weights sum true. One finding per line; a tome with any ERROR is not done.

    python3 tools/validate_tome.py tomes/<id>

Exit 0 = clean (WARNs allowed). Exit 1 = at least one ERROR. Stdlib only.
"""
import argparse
import colorsys
import os
import re
import subprocess
import sys
import tempfile

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    sys.exit("validate_tome.py needs Python 3.11+ (the tomllib module).")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIMES_DIR = os.path.join(REPO, "global-configs", "runtimes")
SKINS_DIR = os.path.join(REPO, "skins")

sys.path.insert(0, REPO)
import tome_layout  # noqa: E402 — shared split-tome layout, in lockstep with server.py

# The 18-ink theme contract (TOME-AUTHORING.md § [[themes]], mirrored in
# web/style.css's "Theme palettes are injected" vellum block). Every palette
# MUST define exactly these.
THEME_VARS = {
    "bg0", "bg1", "bg2", "bg3", "line", "line-hi",
    "tx", "tx-dim", "tx-faint", "ac", "ac-dim", "ac-bg",
    "warn", "bad", "info", "slab", "slab-tx", "candle",
}
EXERCISE_TYPES = {"mc", "text", "fill", "type", "write"}
# Coin faces a palette may pick (app.js COIN_ICONS; TOME-AUTHORING.md § [[themes]])
COIN_FACES = {"star", "rune", "gem", "holed", "serpent", "sun", "bolt", "eye"}
# The six engine consumable mechanics (§ [[shop]]). Any other consumable id
# renders in the shop but does nothing — a WARN, never an ERROR.
CONSUMABLE_IDS = {"firewall", "x2", "skip", "vpn", "xray", "oracle"}
# The five power-ups every tome MUST stock (each reflavored + filled). oracle is an
# optional 6th — it needs a [runtime] oracle model, so it isn't required.
REQUIRED_CONSUMABLES = {"firewall", "x2", "skip", "vpn", "xray"}
# consumables whose strength is the number of charges — a lone charge makes a dud ward.
MULTI_CHARGE = {"firewall", "vpn"}
META_REQUIRED = ["id", "name", "description", "author", "version", "favicon"]
ID_RE = re.compile(r"[A-Za-z0-9_-]+")
# TOME-WORKFLOW Phase 7 treats these WARN classes as hard gates; --strict enforces that.
HARD_GATE_LABELS = {"anti-template", "content"}
# scaffolding text that must not survive to a finished tome (TODO/FIXME exact-case —
# lowercase "todo" appears in honest prose; lorem any case)
PLACEHOLDER_RE = re.compile(r"\bTODO\b|\bFIXME\b|(?i:lorem ipsum)")

_findings = []  # (level, file_label, msg)


def err(label, msg):
    _findings.append(("ERROR", label, msg))


def warn(label, msg):
    _findings.append(("WARN", label, msg))


def rel(path):
    """Label a path relative to the repo root when possible, else as given."""
    try:
        r = os.path.relpath(path, REPO)
        return r if not r.startswith("..") else path
    except ValueError:
        return path


def load_toml(path):
    """Parse a TOML file. Returns (data, error_message)."""
    try:
        with open(path, "rb") as f:
            return tomllib.load(f), None
    except FileNotFoundError:
        return None, "file not found"
    except tomllib.TOMLDecodeError as e:
        return None, "does not parse as TOML 1.0: " + str(e)
    except OSError as e:
        return None, "could not read: " + str(e)


def norm_lines(s):
    """Engine output normalization: trim line ends, collapse internal whitespace
    runs to one space, drop blank lines. Used for the attack append invariant."""
    out = []
    for line in str(s).splitlines():
        line = " ".join(line.split())
        if line:
            out.append(line)
    return out


def global_skin_ids():
    """Ids of the platform skins under skins/<id>/skin.toml (e.g. vellum)."""
    ids = set()
    try:
        for name in os.listdir(SKINS_DIR):
            if os.path.isfile(os.path.join(SKINS_DIR, name, "skin.toml")):
                ids.add(name)
    except OSError:
        pass
    ids.add("vellum")  # the baseline global skin always exists
    return ids


def runtime_resolves(name):
    """True if global-configs/runtimes/<name>.toml exists (mirrors the engine's
    lang_config lookup in runtimes/__init__.py)."""
    if not name or not ID_RE.fullmatch(name):
        return False
    return os.path.isfile(os.path.join(RUNTIMES_DIR, name + ".toml"))


def lang_config(name):
    """The language TOML's keys, or {} if it is missing/unparseable."""
    if not runtime_resolves(name):
        return {}
    data, _ = load_toml(os.path.join(RUNTIMES_DIR, name + ".toml"))
    return data or {}


# --------------------------------------------------------------------------- checks

def check_layout(tome_path, m):
    """Every file in the tome folder must be accounted for by the layout contract
    (tome_layout.py's docstring). This is the gate the true-sight build proved missing:
    a botched rename left an entire pre-rename tome NESTED inside the new one, plus it
    catches scratch files, backups, and section folders the manifest no longer lists —
    all invisible to checks that only read manifest-declared files. Returns the
    legitimate .toml paths so the placeholder sweep reads exactly the shipped files."""
    content = m.get("content", {}) if isinstance(m.get("content"), dict) else {}
    sections = {str(s) for s in (content.get("sections") or [])}
    attacks_name = str(content.get("attacks") or "generated/attacks.toml").replace(os.sep, "/")
    fixed = {"tome.toml", "themes.toml", "shop.toml", "badges.toml", "intrusions.toml",
             "attacks_src.toml", "attacks.toml", attacks_name,
             "generated/README.md"}  # the tooling's DO-NOT-EDIT marker for generated/

    def legit(p):
        if p in fixed:
            return True
        flat = re.fullmatch(r"sections/([A-Za-z0-9_-]+)\.toml", p)
        if flat:
            return flat.group(1) in sections
        deep = re.fullmatch(r"sections/([A-Za-z0-9_-]+)/(?:(?:section|freestyle)\.toml|lessons/[^/]+\.toml)", p)
        return bool(deep) and deep.group(1) in sections

    legit_tomls, stray = [], []
    for dirpath, dirs, files in os.walk(tome_path):
        rd = os.path.relpath(dirpath, tome_path).replace(os.sep, "/")
        if rd == ".":
            rd = ""
        # save/ is the engine's runtime state (student saves + workspace) — never validated
        dirs[:] = [d for d in dirs if not (rd == "" and d == "save")]
        if rd and "tome.toml" in files:
            err(rel(tome_path), f"an entire tome is nested at {rd!r} (it carries its own tome.toml) "
                                "— the debris of a botched rename (`mv old-dir existing-dir` moves "
                                "INTO it); delete the embedded copy")
            dirs[:] = []  # one finding for the subtree, not fifty
            continue
        for name in sorted(files):
            p = f"{rd}/{name}" if rd else name
            if legit(p):
                if p.endswith(".toml"):
                    legit_tomls.append(os.path.join(dirpath, name))
            else:
                stray.append(p)
    if stray:
        shown = ", ".join(stray[:8]) + (f" (+{len(stray) - 8} more)" if len(stray) > 8 else "")
        err(rel(tome_path), f"unexpected file(s) outside the tome layout: {shown} — a tome ships "
                            "only the layout-contract files (tome_layout.py); scratch files, "
                            "backups, and sections missing from [content].sections must go")
    return legit_tomls


def check_placeholders(toml_files):
    """Scaffolding sweep: a finished tome carries no TODO/FIXME/lorem strings. WARN
    class 'content' so it hard-gates at Phase 7 (--strict) without blocking the
    scaffold phases, which legitimately leave TODOs for later phases to fill."""
    for path in toml_files:
        data, e = load_toml(path)
        if e:
            continue  # unparseable files are reported by their own checks
        hits = []

        def scan(v, at):
            if isinstance(v, str):
                if PLACEHOLDER_RE.search(v):
                    hits.append(at or "(top level)")
            elif isinstance(v, dict):
                for k, x in v.items():
                    scan(x, f"{at}.{k}" if at else k)
            elif isinstance(v, list):
                for i, x in enumerate(v):
                    scan(x, f"{at}[{i}]")

        scan(data, "")
        if hits:
            warn("content", f"{rel(path)}: {len(hits)} string(s) still carry TODO/FIXME/placeholder "
                            f"text (first at {hits[0]}) — clear every bit of scaffolding before "
                            "calling the tome done")


def engine_badge_ids():
    """The badge ids the engine hard-grants — the literal grantBadge(\"...\") calls in
    web/app.js (streaks, defenses, duel wins, completion). Scraped live so the contract
    can't drift; variable-id calls (freestyle badges) don't match and don't belong here."""
    try:
        with open(os.path.join(REPO, "web", "app.js"), encoding="utf-8") as f:
            js = f.read()
    except OSError:
        return set()  # validator run without the web app checked out — skip the contract
    # the literal must be the WHOLE first argument — grantBadge("rank-" + …) builds a
    # dynamic id and carries its own name/desc, so it never needs a bank entry
    return set(re.findall(r'grantBadge\(\s*"([A-Za-z0-9_-]+)"\s*[,)]', js))


def check_badges(m, tome_path):
    """The badge bank must define every engine-granted id: grantBadge falls back to the
    RAW ID as the badge's name, so a missing entry toasts \"SIGIL PRESSED // combo-10\"
    at the student — working mechanics, dead flavor. The true-sight build shipped 1 of 6."""
    engine = engine_badge_ids()
    if not engine:
        return
    bpath = os.path.join(tome_path, "badges.toml")
    blabel = rel(bpath if os.path.isfile(bpath) else os.path.join(tome_path, "tome.toml"))
    bank = {b.get("id") for b in (m.get("badges") or []) if isinstance(b, dict)}
    missing = engine - bank
    if missing:
        err(blabel, f"badge bank is missing engine-granted id(s): {sorted(missing)} — app.js "
                    "grants these by id and an undefined one toasts as a raw id with no name "
                    "or story; define all of them, in this tome's voice")
    extra = bank - engine
    if extra:
        warn(blabel, f"badge id(s) {sorted(extra)} are never granted by the engine — dead sigils "
                     "(section badges belong in each section's [freestyle.badge], not the bank)")


def check_meta(m, label):
    meta = m.get("meta")
    if not isinstance(meta, dict):
        err(label, "[meta] table is missing")
        return None
    for key in META_REQUIRED:
        if not str(meta.get(key, "")).strip():
            err(label, f"[meta] {key} is required and must be non-empty")
    return meta


def check_runtime(m, tome_id, label):
    rt = m.get("runtime")
    if not isinstance(rt, dict):
        err(label, "[runtime] table is missing")
        return
    name = rt.get("name") or "custom"  # matches the engine's default (generic.py NAME) when name is omitted
    if not ID_RE.fullmatch(str(name)):
        err(label, f"[runtime] name {name!r} must match [A-Za-z0-9_-]+")
    merged = {**lang_config(name), **rt}
    has_cmd = bool(merged.get("command") or merged.get("runCommand"))
    if not runtime_resolves(name) and not has_cmd:
        err(label, f"[runtime] name {name!r} has no global-configs/runtimes/{name}.toml "
                   "and the tome sets neither command nor runCommand — nothing can run")
    if "workspaceDir" in rt:
        warn(label, "[runtime] workspaceDir is removed — a tome never hardwires the "
                    "project location. Use externalWorkspace = true to REQUIRE external "
                    "mode; the student always chooses the folder")
    xw = rt.get("externalWorkspace")
    if xw is not None and not isinstance(xw, bool):
        err(label, "[runtime] externalWorkspace must be a boolean (true to require external mode)")


def check_narrative(m, label):
    nar = m.get("narrative", {})
    if not isinstance(nar, dict) or not str(nar.get("objective", "")).strip():
        err(label, "[narrative] objective is required and must be non-empty — "
                   "the server refuses to load a tome without it")


def check_economy(m, label):
    econ = m.get("economy", {})
    if not isinstance(econ, dict):
        return
    ranks = econ.get("ranks")
    if ranks is None:
        return
    if not isinstance(ranks, list) or not ranks:
        warn(label, "[economy] ranks should be a non-empty array of [threshold, title] pairs")
        return
    ok = True
    for r in ranks:
        if (not isinstance(r, list) or len(r) != 2
                or not isinstance(r[0], (int, float)) or not isinstance(r[1], str)):
            ok = False
    if not ok:
        warn(label, "[economy] ranks entries should each be [threshold(number), title(string)]")
    elif ranks[0][0] != 0:
        warn(label, "[economy] ranks: the first title should start at threshold 0")


def check_shop(m, theme_ids, earned_granted, label):
    # every tome stocks the five engine power-ups, each reflavored and filled out — the
    # engine supplies generic defaults so mechanics never break, but a SHIPPED tome must
    # carry its own so nothing ever renders in another course's (or placeholder) voice.
    consumables = {i.get("id"): i for i in m.get("shop", [])
                   if isinstance(i, dict) and i.get("kind") == "consumable"}
    missing = REQUIRED_CONSUMABLES - set(consumables)
    if missing:
        err(label, f"[[shop]] is missing required power-up(s): {sorted(missing)} — every tome stocks "
                   "the five engine consumables (firewall/x2/skip/vpn/xray), each reflavored to its "
                   "world (oracle is an optional 6th)")
    for cid in sorted(REQUIRED_CONSUMABLES & set(consumables)):
        it = consumables[cid]
        for field in ("name", "desc"):
            if not str(it.get(field, "")).strip():
                err(label, f"[[shop]] power-up {cid!r}: {field} is required — reflavor it to this tome's world")
        cost = it.get("cost")
        if not isinstance(cost, (int, float)) or isinstance(cost, bool) or cost <= 0:
            err(label, f"[[shop]] power-up {cid!r}: cost must be a positive number (its price in credits)")
        if not str(it.get("ico", "")).strip():
            err(label, f"[[shop]] power-up {cid!r}: ico is required — pick an icon id for the shop tile")
        if cid == "x2" and "charges" in it:
            warn(label, "[[shop]] power-up 'x2': drop the charges key — the count is engine-fixed at 20")
        if cid in MULTI_CHARGE:
            ch = it.get("charges")
            if not isinstance(ch, int) or isinstance(ch, bool) or ch < 2:
                warn(label, f"[[shop]] power-up {cid!r}: set charges to 2+ — a one-charge ward barely "
                            "helps (reference tomes run firewall=5, vpn=3)")
    for item in m.get("shop", []):
        if not isinstance(item, dict):
            err(label, "[[shop]] entries must be tables")
            continue
        iid = item.get("id")
        kind = item.get("kind")
        if not iid:
            err(label, "[[shop]] item is missing id")
        if kind not in ("consumable", "theme"):
            warn(label, f"[[shop]] {iid!r}: kind should be \"consumable\" or \"theme\"")
        if kind == "consumable" and iid not in CONSUMABLE_IDS:
            warn(label, f"[[shop]] consumable {iid!r} is not one of the six engine "
                        "mechanics (firewall/x2/skip/vpn/xray/oracle) — it renders but does nothing")
        if kind == "theme":
            ref = item.get("theme")
            if not ref:
                err(label, f"[[shop]] theme item {iid!r} is missing its theme = <[[themes]] id>")
            elif ref not in theme_ids:
                err(label, f"[[shop]] theme item {iid!r} references theme {ref!r}, "
                           "which is not a [[themes]] id in this tome")
            elif earned_granted and ref == earned_granted:
                err(label, f"[[shop]] theme item {iid!r} sells the earned theme "
                           f"{earned_granted!r} — [progression.earnedTheme] is a trophy, "
                           "never merchandise")


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
                 "scaffold placeholder IS vellum; design this course's own palette (all 18 vars)")
        for other in themes[i + 1:]:
            d2 = _palette_dist(tv, other.get("vars", {}) or {})
            if d2 is not None and d2 < PALETTE_MIN_DIST:
                warn("content", f"[[themes]] {th.get('id')!r} and {other.get('id')!r} are "
                     f"near-identical (mean channel distance {d2:.1f} < {PALETTE_MIN_DIST}) — "
                     "palettes must differ in paper tint, accent ink, and candle")


def check_exercise(ex, label, seen_ex):
    if not isinstance(ex, dict):
        err(label, "[[lessons.exercises]] entries must be tables")
        return
    eid = ex.get("id")
    if not eid:
        err(label, "an exercise is missing its id")
    elif eid in seen_ex:
        err(label, f"exercise id {eid!r} is duplicated — ids key saved progress and must be unique per tome")
    else:
        seen_ex.add(eid)
    t = ex.get("type")
    if t not in EXERCISE_TYPES:
        err(label, f"exercise {eid!r}: type {t!r} is not one of mc/text/fill/type/write")
        return
    if t == "mc":
        choices = ex.get("choices")
        ans = ex.get("answer")
        if not isinstance(choices, list) or not choices:
            err(label, f"mc {eid!r}: choices must be a non-empty array")
        if not isinstance(ans, int):
            err(label, f"mc {eid!r}: answer must be a 0-based integer index")
        elif isinstance(choices, list) and not (0 <= ans < len(choices)):
            err(label, f"mc {eid!r}: answer index {ans} is out of range for {len(choices)} choices")
        if not str(ex.get("whyWrong", "")).strip():
            err(label, f"mc {eid!r}: whyWrong is required — every mc must name the misconception "
                       "its wrong answers betray (§3, the highest-value feedback channel)")
    elif t in ("text", "fill"):
        if not str(ex.get("answer", "")).strip():
            err(label, f"{t} {eid!r}: answer is required")
        if t == "fill" and "____" not in str(ex.get("code", "")):
            warn(label, f"fill {eid!r}: code should contain the ____ blank the answer fills")
    elif t == "type":
        if not str(ex.get("code", "")).strip():
            err(label, f"type drill {eid!r}: code (the text to retype) is required")
    elif t == "write":
        has_re = bool(str(ex.get("expectRe", "")).strip())
        if "expect" in ex:
            if not str(ex["expect"]).strip():
                err(label, f"write {eid!r}: expect is empty — unwinnable (empty stdout reads as \"(no output)\")")
        elif not has_re:
            err(label, f"write {eid!r}: needs a non-empty expect or an expectRe")
    if t != "type" and not str(ex.get("hint", "")).strip():
        warn(label, f"exercise {eid!r}: no hint (every exercise should have an exercise-specific one)")


def check_freestyle(fs, slabel):
    if not isinstance(fs, dict):
        err(slabel, "[freestyle] is required in every section and must be a table")
        return
    for key in ("title", "brief"):
        if not str(fs.get(key, "")).strip():
            err(slabel, f"[freestyle] {key} is required")
    if not str(fs.get("xray", "")).strip():
        warn(slabel, "[freestyle] xray is missing — the scrying-lens consumable would reveal nothing")
    badge = fs.get("badge")
    if isinstance(badge, dict) and not str(badge.get("id", "")).strip():
        err(slabel, "[freestyle.badge] present but missing id")
    rubric = fs.get("rubric")
    if not isinstance(rubric, list) or not rubric:
        err(slabel, "[[freestyle.rubric]] is required — at least one weighted criterion")
        return
    total = 0
    for row in rubric:
        if not isinstance(row, dict):
            err(slabel, "[[freestyle.rubric]] rows must be tables")
            continue
        if not str(row.get("criterion", "")).strip():
            err(slabel, "[[freestyle.rubric]] row is missing criterion")
        w = row.get("weight")
        if not isinstance(w, (int, float)):
            err(slabel, "[[freestyle.rubric]] row is missing a numeric weight")
        else:
            total += w
    if round(total, 6) != 100:
        err(slabel, f"[[freestyle.rubric]] weights must sum to exactly 100 (got {total})")


def check_section(sdata, sid, slabel, seen_ex, seen_les):
    if sdata.get("id") != sid:
        err(slabel, f"top-level id is {sdata.get('id')!r} but the section is listed as {sid!r}")
    for key in ("id", "codename", "title", "build", "brief"):
        if not str(sdata.get(key, "")).strip():
            err(slabel, f"section is missing required key {key!r}")
    check_freestyle(sdata.get("freestyle"), slabel)
    lessons = sdata.get("lessons", [])
    if not isinstance(lessons, list) or not lessons:
        warn(slabel, "section has no [[lessons]]")
    for les in lessons:
        if not isinstance(les, dict):
            err(slabel, "[[lessons]] entries must be tables")
            continue
        lid = les.get("id")
        if not lid:
            err(slabel, "a lesson is missing its id")
        elif lid in seen_les:
            err(slabel, f"lesson id {lid!r} is duplicated — lesson ids must be unique per tome")
        else:
            seen_les.add(lid)
        # title/body must sit directly on the [[lessons]] entry — a common breakage is
        # nesting them in a stray [lesson] sub-table or using `desc`, which parses fine
        # but renders a titleless, textless lesson the engine shows blank.
        if not str(les.get("title", "")).strip():
            err(slabel, f"lesson {lid!r}: missing title (must be a key on [[lessons]], not a "
                        "nested [lesson] table)")
        if not str(les.get("body", "")).strip():
            hint = " — found `desc`; the engine reads `body`" if str(les.get("desc", "")).strip() else ""
            err(slabel, f"lesson {lid!r}: missing body (the lesson's HTML teaching text){hint}")
        for ex in les.get("exercises", []):
            check_exercise(ex, slabel, seen_ex)
        for rd in les.get("readings", []) or []:
            if not isinstance(rd, dict):
                err(slabel, f"lesson {lid!r}: [[lessons.readings]] entries must be tables")
                continue
            u = str(rd.get("url", "")).strip()
            if not re.match(r"https?://", u):
                err(slabel, f"lesson {lid!r}: reading {str(rd.get('label', '?'))[:40]!r} needs an "
                            f"http(s) url (got {u!r}) — a reading the student cannot open is dead content")


def check_anti_template(sections_data):
    """Tome-wide WARNs for the two §3 anti-template rules structure checks miss:
    the machine-generated grid (every section the same shape) and mc answers
    stuck on one index. WARN, never ERROR — both are judgement calls, but they're
    the failures AI authors ship most, so name them mechanically."""
    from collections import Counter
    mc_answers = []
    shapes = []  # (lesson_count, tuple(exercise_counts)) per section
    lesson_types = []  # sorted type-tuple per lesson — catches "one of each type, every lesson"
    fields = {"hint": [], "prompt": [], "whyWrong": [], "explain": []}  # near-unique per §3
    for sdata in sections_data:
        lessons = sdata.get("lessons", []) or []
        ex_counts = []
        for les in lessons:
            if not isinstance(les, dict):
                continue
            exs = les.get("exercises", []) or []
            ex_counts.append(len(exs))
            lesson_types.append(tuple(sorted(e.get("type") for e in exs if isinstance(e, dict))))
            for ex in exs:
                if not isinstance(ex, dict):
                    continue
                if ex.get("type") == "mc" and isinstance(ex.get("answer"), int):
                    ch = ex.get("choices")
                    mc_answers.append((ex["answer"], len(ch) if isinstance(ch, list) else 0))
                for k, bucket in fields.items():
                    v = ex.get(k)
                    if isinstance(v, str) and v.strip():
                        bucket.append(v.strip())
        shapes.append((len(lessons), tuple(ex_counts)))
    # §3: hints/prompts/whyWrong/explain are exercise-specific — "180 exercises,
    # ~180 distinct hints". One canned string stamped across many exercises is the
    # content-level version of the uniform grid, and the shape checks miss it.
    for k, vals in fields.items():
        if len(vals) < 8:
            continue
        top, n = Counter(vals).most_common(1)[0]
        if n > 3:
            warn("anti-template", f"{k}: one string is reused {n}× of {len(vals)} "
                 f"({len(set(vals))} distinct) — {k} must be exercise-specific (§3), not a "
                 f"canned per-type sentence. Offender: {top[:60]!r}")
    # mc answer spread across 0–3. Catch three flavors, most-specific first: all one
    # index; a 4-choice bank that never lands on some index (the "only 1 & 2" case);
    # any bank clustered on <3 distinct indices.
    idxs = [a for a, _ in mc_answers]
    four = [a for a, n in mc_answers if n >= 4]
    if len(idxs) >= 4 and len(set(idxs)) == 1:
        warn("anti-template", f"all {len(idxs)} mc answers are index {idxs[0]} — spread "
             "correct answers across positions 0–3 (§3); a fixed index is guessable "
             "and reads as machine-authored")
    elif len(four) >= 8 and (set(range(4)) - set(four)):
        miss = sorted(set(range(4)) - set(four))
        warn("anti-template", f"mc answers never land on index {miss} across {len(four)} "
             f"four-choice questions (they cluster on {sorted(set(four))}) — spread correct "
             "answers evenly across 0–3 (§3), don't over-correct to the middle")
    elif len(idxs) >= 8 and len(set(idxs)) < 3:
        warn("anti-template", f"mc answers cluster on only {sorted(set(idxs))} — spread "
             "correct answers across positions 0–3 (§3)")
    # every index used, but not comparably: a bank where one position carries <10%
    # of the answers is still guessable-by-elimination and reads machine-authored
    # (§3 says 0-3 must each be used "a comparable number of times").
    elif len(four) >= 20:
        from collections import Counter as _C
        counts = _C(four)
        starved = [i for i in range(4) if counts[i] / len(four) < 0.10]
        if starved:
            share = {i: counts[i] for i in range(4)}
            warn("anti-template", f"mc answer index(es) {starved} carry under 10% of {len(four)} "
                 f"four-choice answers (spread: {share}) — rebalance so 0–3 are each used a "
                 "comparable number of times (§3)")
    if len(shapes) >= 3 and len(set(shapes)) == 1:
        lc, ec = shapes[0]
        warn("anti-template", f"every section has the same shape ({lc} lessons, exercise counts "
             f"{list(ec)}) — vary lesson counts (3–8) and exercise counts (4–6) by material (§3); "
             "a uniform grid reads as machine-generated")
    # even when section shapes differ, every lesson carrying the identical type mix
    # (e.g. exactly one of each of mc/text/fill/type/write) is a machine tell the
    # section-level shape check misses.
    if len(lesson_types) >= 4 and len(set(lesson_types)) == 1:
        warn("anti-template", f"all {len(lesson_types)} lessons have the identical exercise-type "
             f"mix {list(lesson_types[0])} — vary the mix and order per lesson (§3), not one of "
             "each type every time")


def _visible_words(html):
    """Word count of a lesson body as a reader sees it — HTML tags stripped. §3 wants
    300–600 words; the shipped reference (verisearch) runs 205–390. The floor below
    sits under that range so only genuinely thin prose trips it."""
    return len(re.sub(r"<[^>]+>", " ", str(html or "")).split())


def check_density(sections_data):
    """Anti-hollowness floors. A stub course — 1-exercise lessons, two-sentence bodies,
    one rubric cloned across every section — parses clean but teaches nothing; that is
    the failure a validator was assumed unable to catch, but thinness is mechanical.
    The floors sit far below a real tome (verisearch runs 4-6 lessons/section, 4+
    exercises and 205+ word bodies per lesson, every rubric distinct), so only a
    genuinely thin tome trips them. While the tome still carries TODO scaffolding these
    are WARNs (work in progress); once the TODOs are gone — the author calls it done —
    they become ERRORs. Simulated-but-dense labs and handed-over addresses are NOT
    caught here (that stays a judgement call for the Phase 8 student review)."""
    MIN_LESSONS, MIN_EXERCISES, MIN_BODY_WORDS = 3, 4, 180  # §3: 3-8 lessons, 4-6 exercises, 300-600 words
    wip = any("TODO" in str(les.get("body", ""))
              for sd in sections_data
              for les in (sd.get("lessons") or []) if isinstance(les, dict))
    report = warn if wip else err
    tag = "density (WIP → ERROR once TODOs cleared)" if wip else "density"
    rubric_sigs = []
    for sd in sections_data:
        sid = sd.get("id") or "?"
        lessons = [l for l in (sd.get("lessons") or []) if isinstance(l, dict)]
        if len(lessons) < MIN_LESSONS:
            report(tag, f"{sid}: only {len(lessons)} lesson(s) — need ≥{MIN_LESSONS} "
                   f"(§3: vary 3-8 by material); a thin section is the hollow-tome tell")
        for les in lessons:
            lid = les.get("id") or "?"
            nex = len([e for e in (les.get("exercises") or []) if isinstance(e, dict)])
            if nex < MIN_EXERCISES:
                report(tag, f"{sid}: lesson {lid!r} has {nex} exercise(s) — need ≥"
                       f"{MIN_EXERCISES} (§3: vary 4-6); too few is the hollow-tome tell")
            n = _visible_words(les.get("body"))
            if n < MIN_BODY_WORDS:
                report(tag, f"{sid}: lesson {lid!r} body is {n} visible words — under "
                       f"{MIN_BODY_WORDS} is a stub, not a taught lesson (§3 wants 300–600)")
        fs = sd.get("freestyle")
        if isinstance(fs, dict) and isinstance(fs.get("rubric"), list):
            rubric_sigs.append(tuple((r.get("criterion"), str(r.get("desc", "")).strip())
                                     for r in fs["rubric"] if isinstance(r, dict)))
    if len(rubric_sigs) >= 3 and len(set(rubric_sigs)) == 1:
        report(tag, f"all {len(rubric_sigs)} freestyle rubrics are identical — grade THAT "
               "section's build (§3), not one canned rubric cloned across the tome")


def check_content(m, sections_data, label, tooling=None):
    """Content-quality gates the structural checks miss. These are the floors a
    harness run erodes first, because until now nothing failed for them: prose
    depth, field-notes, narrative line counts, toolchain setup, naming drift.
    Language-neutral proxies only — no keyword matching, so non-English tomes
    aren't penalized. WARNs here are hard gates per TOME-WORKFLOW Phase 7."""
    nar = m.get("narrative", {}) or {}
    nboot = len(nar.get("bootLines", []) or [])
    ngrade = len(nar.get("gradingLines", []) or [])
    if not 8 <= nboot <= 12:
        warn("content", f"[narrative] bootLines has {nboot} line(s) — spec wants 8–12 "
             "(establish the fiction, the mentor, and the commission)")
    if not 6 <= ngrade <= 8:
        warn("content", f"[narrative] gradingLines has {ngrade} line(s) — spec wants 6–8 in-character lines")
    if not str(nar.get("completeText", "")).strip():
        warn("content", "[narrative] completeText is missing — the course-complete screen falls "
             "back to generic engine text instead of this tome's voice at its biggest moment")

    lessons = [les for sd in sections_data
               for les in (sd.get("lessons") or []) if isinstance(les, dict)]
    if lessons:
        # §3: field-notes appendix "strongly recommended on every lesson"; the
        # reference tome carries 52/52. Near-zero coverage is the hollow-content tell.
        fn = sum(1 for les in lessons if "field-notes" in str(les.get("body", "")))
        if fn / len(lessons) < 0.5:
            warn("content", f"only {fn} of {len(lessons)} lessons carry a FIELD NOTES appendix — "
                 "§3 strongly recommends one on every lesson (the deeper-cut channel)")
        words = sorted(_visible_words(les.get("body")) for les in lessons)
        median = words[len(words) // 2]
        if median < 300:
            warn("content", f"median lesson body is {median} words — §3 wants 300–600 per "
                 "lesson; the per-lesson floor only catches stubs, this catches systematic thinness")

    # §5 + the gate's Tooling choice (harness passes --tooling internal|external|both):
    #   internal → the course must stay in-browser: externalWorkspace = true is forbidden.
    #   external/both, or externalWorkspace = true → the tome MUST teach its external tools,
    #     named in the first section with resource links. Language-neutral proxy: the first
    #     section must carry at least one [[lessons.readings]] link.
    rt = m.get("runtime", {}) or {}
    xw = rt.get("externalWorkspace") is True
    if tooling == "internal" and xw:
        err(label, "tooling gate = internal (in-browser only) but [runtime] externalWorkspace "
                   "= true — an internal-only course keeps every workbench in the browser; drop it")
    if (xw or tooling in ("external", "both")) and sections_data:
        first = sections_data[0]
        has_reading = any(str(r.get("url", "")).strip()
                          for les in (first.get("lessons") or []) if isinstance(les, dict)
                          for r in (les.get("readings") or []) if isinstance(r, dict))
        if not has_reading:
            why = "[runtime] externalWorkspace = true" if xw else f"tooling gate = {tooling}"
            err(label, f"{why} but the first section has no [[lessons.readings]] links — the tome "
                       "REQUIRES external tools be taught: state which to install/use in the first "
                       "lesson, with resource links (marked mandatory/optional)")
    if rt.get("externalWorkspace") is True and not str(rt.get("projectFile", "")).strip():
        warn("content", "[runtime] externalWorkspace = true but no projectFile — the workbench's "
             "required-files panel falls back to the language default (e.g. a lone Main.java), "
             "misdescribing the real project; name its true build file (e.g. \"build.gradle\")")

    # §6 step 1, "one name, one spelling": the machine id is the kebab-case of the
    # project name — a word boundary (camelCase or a space) becomes a hyphen, so
    # ManaWeaver → mana-weaver. (meta.name is the tome-card title and may legitimately
    # differ — verisearch's card reads "The Liber Veritatis" — runtime.project anchors.)
    project = str(rt.get("project", "")).strip()
    tome_id = str((m.get("meta", {}) or {}).get("id", ""))
    if project:
        kebab = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", project)
        norm = re.sub(r"[^a-z0-9]+", "-", kebab.lower()).strip("-")
        if norm and norm != tome_id:
            warn("content", f"tome id {tome_id!r} is not the kebab-case of the project name "
                 f"{project!r} (→ {norm!r}) — §6: one name, one spelling, and never the "
                 "requester's phrasing; every derived form (id, caps branding, packages) "
                 "uses the same letters")


def check_attacks(path, m, label, attackstages):
    data, e = load_toml(path)
    if e:
        err(rel(path), e)
        return
    tiers = data.get("tiers")
    if not isinstance(tiers, list) or not tiers:
        err(rel(path), "attacks file has no [[tiers]]")
        return
    want = len(attackstages) if isinstance(attackstages, list) and attackstages else 3
    thin = []
    for ti, tier in enumerate(tiers):
        pool = tier.get("pool", []) if isinstance(tier, dict) else []
        if len(pool) < 3:
            thin.append(ti + 1)
        for pi, chal in enumerate(pool):
            where = f"tier {ti + 1} challenge {pi + 1}"
            starter = chal.get("starter") if isinstance(chal, dict) else None
            if isinstance(starter, str) and starter.count("{") != starter.count("}"):
                err(rel(path), f"{where}: starter has unbalanced braces ({starter.count('{')} open, "
                               f"{starter.count('}')} close) — it must run as given; a student "
                               "under the duel timer repairs logic, not scaffolding")
            stages = chal.get("stages", []) if isinstance(chal, dict) else []
            if len(stages) != want:
                err(rel(path), f"{where}: has {len(stages)} stages; expected exactly {want} "
                               "(one per [progression].attackStages entry)")
            prev = None
            for si, st in enumerate(stages):
                exp = st.get("expect") if isinstance(st, dict) else None
                if exp is None or not str(exp).strip():
                    err(rel(path), f"{where} stage {si + 1}: expect is empty")
                    prev = None
                    continue
                cur = norm_lines(exp)
                if prev is not None and cur[:len(prev)] != prev:
                    err(rel(path), f"{where} stage {si + 1}: breaks the append invariant "
                                   "(each stage's expect must begin with the previous stage's expect)")
                prev = cur
    if thin:
        warn(rel(path), f"{len(thin)} attack tier(s) have <3 challenges (tiers {thin}) — "
                        "spec wants 3+ per tier (one is picked at random)")
    # tier N unlocks after N sections passed (app.js caps depth at #tiers), so a bank
    # far shorter than the course stops scaling — the back half unlocks no new duels.
    sections = (m.get("content", {}) or {}).get("sections")
    nsec = len(sections) if isinstance(sections, list) else 0
    if nsec and len(tiers) < (nsec + 1) // 2:
        warn(rel(path), f"only {len(tiers)} attack tier(s) for a {nsec}-section course — tiers "
                        "should span the course (§4); the later sections unlock no new duels")


def check_attacks_sync(tome_path, apath):
    """attacks_src.toml is the authored source; generated/attacks.toml is machine-sliced
    from it by tools/gen_attacks.py. A phase that edits one and not the other ships a
    bank that silently disagrees with its source. Titles, starters, and briefs are
    copied verbatim by the generator, so they must match exactly.
    # ponytail: metadata sync only — re-deriving `expect` needs the live server and the
    # tome's toolchain; add a --run deep check if a desync ever slips past this."""
    spath = os.path.join(tome_path, "attacks_src.toml")
    if not os.path.isfile(spath):
        return
    src, e = load_toml(spath)
    if e:
        err(rel(spath), e)
        return
    gen, e = load_toml(apath)
    if e:
        return  # the unreadable generated file is already reported by check_attacks

    def sig(title, starter, briefs):
        return (str(title or "").strip(), str(starter or "").strip(),
                tuple(str(b or "").strip() for b in briefs))

    by_tier = {}
    for ch in src.get("challenge", []) or []:
        if isinstance(ch, dict):
            by_tier.setdefault(ch.get("tier", 0), []).append(
                sig(ch.get("title"), ch.get("starter"), ch.get("briefs") or []))
    ssig = [by_tier[t] for t in sorted(by_tier)]
    gsig = [[sig(c.get("t"), c.get("starter"),
                 [s.get("brief") for s in (c.get("stages") or []) if isinstance(s, dict)])
             for c in (t.get("pool") or []) if isinstance(c, dict)]
            for t in gen.get("tiers", []) if isinstance(t, dict)]
    if ssig == gsig:
        return
    where = f"{len(ssig)} source tier(s) vs {len(gsig)} generated"
    if len(ssig) == len(gsig):
        for ti, (st, gt) in enumerate(zip(ssig, gsig)):
            if st != gt:
                bad = next((ci for ci, pair in enumerate(zip(st, gt)) if pair[0] != pair[1]),
                           min(len(st), len(gt)))
                where = f"tier {ti + 1} challenge {bad + 1}"
                break
    err(rel(apath), "out of sync with attacks_src.toml — someone edited one file without the "
                    f"other (first difference: {where}); regenerate via tools/gen_attacks.py")


def load_intrusion_tiers(tome_path, m):
    """The HEX-DEFENSE bank as (tiers, label, error). Reads intrusions.toml's `tiers`
    key, else inline `[[progression.intrusionTiers]]`. Shared by check_intrusions and
    the economy recompute so bounties are summed from the same source the engine gates on."""
    ipath = os.path.join(tome_path, "intrusions.toml")
    if os.path.isfile(ipath):
        data, e = load_toml(ipath)
        if e:
            return None, rel(ipath), e
        if "tiers" not in data:
            others = [k for k, v in data.items() if isinstance(v, list)] or list(data)
            return None, rel(ipath), ("no [[tiers]] — the engine reads only the 'tiers' key, so "
                f"hex-defense loads as EMPTY and never fires. Found instead: {others}. Use "
                "[[tiers]] with a [[tiers.pool]] of stdout challenges (see §2).")
        return data["tiers"], rel(ipath), None
    tiers = (m.get("progression", {}) or {}).get("intrusionTiers")
    return tiers, rel(os.path.join(tome_path, "tome.toml")), None


def check_intrusions(tome_path, m, label):
    """HEX-DEFENSE bank. The engine gates each tier by `t.min <= sectionsPassed` and picks
    one challenge from `t.pool`, scoring it by exact stdout `expect`. The common AI failure
    is inventing a flat `[[intrusions]]` schema with exercise fields (type/code/answer) and
    a string `min` — which loads as ZERO tiers, silently killing the minigame. None of that
    is caught elsewhere, so it's an ERROR here. Intrusions are optional; when present they
    must be shaped right."""
    tiers, ilabel, e = load_intrusion_tiers(tome_path, m)
    if e:
        err(ilabel, e)
        return
    if tiers is None:
        return  # no intrusion bank at all — optional
    if not isinstance(tiers, list) or not tiers:
        err(ilabel, "intrusions define no tiers")
        return
    # #12: a tier gated at min >= section count can only fire AFTER the course is finished,
    # so its hexes never appear during play. min is 0-based sections-passed; with N sections
    # the last playable gate is N-1 (fires while studying the final section).
    nsec = len((m.get("content", {}) or {}).get("sections") or [])
    for ti, tier in enumerate(tiers):
        if isinstance(tier, dict) and isinstance(tier.get("min"), int) and not isinstance(tier.get("min"), bool):
            if nsec and tier["min"] >= nsec:
                warn(ilabel, f"intrusion tier {ti + 1}: min = {tier['min']} but the course has "
                     f"{nsec} section(s) — this tier only unlocks after the whole course is "
                     f"complete, so its hexes never fire during play (last playable gate is {nsec - 1})")
    for ti, tier in enumerate(tiers):
        where = f"intrusion tier {ti + 1}"
        if not isinstance(tier, dict):
            err(ilabel, f"{where}: must be a table")
            continue
        mn = tier.get("min")
        if not isinstance(mn, int) or isinstance(mn, bool):
            err(ilabel, f"{where}: min must be an integer (sections passed before it can "
                        f"fire), got {mn!r} — a string like \"s02\" breaks `t.min <= passed` gating")
        pool = tier.get("pool")
        if not isinstance(pool, list) or not pool:
            err(ilabel, f"{where}: needs a non-empty [[tiers.pool]] of challenges "
                        "(the flat exercise-style [[intrusions]] shape is not read)")
            continue
        if len(pool) < 3:
            warn(ilabel, f"{where}: only {len(pool)} challenge(s); spec wants 3+ per tier")
        for pi, ch in enumerate(pool):
            exp = ch.get("expect") if isinstance(ch, dict) else None
            if not (isinstance(exp, str) and exp.strip()):
                err(ilabel, f"{where} challenge {pi + 1}: needs a non-empty expect "
                            "(the exact required stdout)")


# --------------------------------------------------------------------------- content depth
# An "API-shaped" identifier segment: a camelCase hump (getMinecraft, setAccessible,
# SideOnly) or an underscore (field_110143_a, snake_case). This is the language-neutral
# tell that a token is *code the course teaches*, not an English prose word — plain and
# single-capitalized words (Item, Field, the) are deliberately excluded to keep noise down.
_API_SHAPE = re.compile(r"[a-z][A-Z]|_")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _unescape(s):
    return s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def _api_tokens(text):
    """API-shaped identifier segments in a blob of text (dotted names split on '.').
    Excludes all-underscore runs (the ____ fill-blank placeholder is not an identifier)."""
    return {t for t in _IDENT.findall(_unescape(str(text or "")))
            if _API_SHAPE.search(t) and set(t) != {"_"}}


def _all_idents(text):
    """Every identifier in a blob (lenient — used as the 'was this mentioned anywhere' set)."""
    return {t for t in _IDENT.findall(_unescape(str(text or ""))) if set(t) != {"_"}}


def _code_span_text(html):
    """Just the <code>/<pre> contents of a lesson body — where taught code vocabulary lives."""
    s = str(html or "")
    chunks = re.findall(r"<code>(.*?)</code>", s, re.S) + re.findall(r"<pre>(.*?)</pre>", s, re.S)
    return " ".join(re.sub(r"<[^>]+>", " ", c) for c in chunks)


def _exercise_api_tokens(ex):
    """API-shaped tokens a single exercise USES (its code/answer surface, not its prose)."""
    if not isinstance(ex, dict):
        return set()
    toks = set()
    toks |= _api_tokens(_code_span_text(ex.get("prompt")))         # API names cited in the prompt's <code>
    for ch in ex.get("choices", []) or []:                          # mc choices are short/code-heavy
        toks |= _api_tokens(ch)
    for k in ("code", "starter", "answer", "expect"):               # fill/type code, write starter, answers
        if ex.get(k):
            toks |= _api_tokens(ex[k])
    for alt in ex.get("accept", []) or []:
        toks |= _api_tokens(alt)
    return toks


# A dotted METHOD CALL: Receiver.member( … ). The trailing '(' is load-bearing — it keeps
# filenames (Program.cs), URLs (nist.gov), and enum/property access (SpecialFolder.Desktop)
# out, leaving actual API invocations. mc CHOICES are never scanned: a distractor is a
# wrong-by-design fake API, so flagging it as 'untaught' is exactly backwards.
_DOTTED_CALL = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def check_taught_before_used(sections_data):
    """#7 invented-API detector + #8 interleaving, off one cumulative-vocabulary pass.

    #7 targets the §3 coverage rule ('no exercise may depend on a concept no lesson taught')
    but only where it can be mechanically sure: a `Receiver.member(` call presented in a
    PROMPT's or freestyle brief's <code> — the given/correct surface, never a distractor
    choice — where both the receiver and the member are absent from every lesson body up to
    AND INCLUDING this section. That narrowness is hard-won: camelCase locals, filenames,
    URLs, enum access, and wrong-by-design mc distractors all masquerade as 'untaught APIs',
    so anything looser drowns a known-good tome in false positives. A never-mentioned method
    call in a question's own given code is the one shape that reliably means we quiz an API
    no lesson taught.

    #8 (interleaving): a section from the 3rd on whose exercises share NO API-shaped token
    with any earlier section is only testing its own lessons — the most common AI-author habit
    (§3 'don't only test the concept a lesson just taught')."""
    taught_idents = set()   # every identifier mentioned in any body up to the PREVIOUS section
    first_api = {}          # API-shaped token -> earliest section index mentioning it
    for i, sd in enumerate(sections_data):
        lessons = [l for l in (sd.get("lessons") or []) if isinstance(l, dict)]
        body_all = " ".join(re.sub(r"<[^>]+>", " ", str(les.get("body") or "")) for les in lessons)
        body_all += " " + re.sub(r"<[^>]+>", " ", str(sd.get("brief") or ""))
        for tok in _api_tokens(body_all):
            first_api.setdefault(tok, i)
        taught_incl = taught_idents | _all_idents(body_all)  # this section counts as taught too

        # #7: method calls in the given/correct surface (prompt code + freestyle brief code)
        given = []
        used_api = set()
        for les in lessons:
            for ex in les.get("exercises", []) or []:
                if not isinstance(ex, dict):
                    continue
                used_api |= _exercise_api_tokens(ex)
                given.append(_code_span_text(ex.get("prompt")))
        fs = sd.get("freestyle")
        if isinstance(fs, dict):
            given.append(_code_span_text(fs.get("brief")))
            used_api |= _api_tokens(_code_span_text(fs.get("brief")))
        invented = []
        for recv, member in _DOTTED_CALL.findall(_unescape(" ".join(given))):
            if recv not in taught_incl and member not in taught_incl and f"{recv}.{member}" not in invented:
                invented.append(f"{recv}.{member}")
        if invented:
            sid = sd.get("id") or f"section {i + 1}"
            shown = ", ".join(invented[:5]) + (f" (+{len(invented) - 5} more)" if len(invented) > 5 else "")
            warn("content", f"{sid}: prompt/brief code calls API(s) no lesson mentions: "
                 f"{shown} — §3: use only what a lesson taught. (Teach it, or fix the name.)")

        # #8: does this section's API vocabulary reach back to an earlier section?
        if i >= 2 and used_api:
            if not any(first_api.get(t, i) < i for t in used_api):
                sid = sd.get("id") or f"section {i + 1}"
                warn("anti-template", f"{sid}: no exercise reaches back to an earlier section's "
                     "material — it only tests its own lessons. §3 wants interleaving: fold an "
                     "earlier concept into a later section (a callback mc, a lab reusing prior data).")

        taught_idents = taught_incl


def check_verbatim_prose(sections_data):
    """#9: §3 forbids a sentence appearing verbatim in more than one lesson body. Catch it with
    14-word shingles over visible (tag-stripped) prose — long enough that a collision is a
    copied sentence, not a stock phrase. Skips shingles that are mostly UPPER-CASE, which are
    the shared appendix headers (FIELD NOTES // …, MARGINALIA // …) tomes repeat by design."""
    W = 14
    seen = {}   # shingle -> first lesson id that had it
    dupes = []  # (lid_a, lid_b, snippet)
    for sd in sections_data:
        for les in (sd.get("lessons") or []):
            if not isinstance(les, dict):
                continue
            lid = les.get("id") or "?"
            words = re.sub(r"<[^>]+>", " ", str(les.get("body") or "")).split()
            local = set()  # don't flag a shingle repeated within ONE lesson
            for j in range(len(words) - W + 1):
                win = words[j:j + W]
                caps = sum(1 for w in win if w.isupper())
                if caps >= W // 2:      # a header/label run, not teaching prose
                    continue
                sh = " ".join(win).lower()
                if sh in local:
                    continue
                local.add(sh)
                if sh in seen and seen[sh] != lid:
                    dupes.append((seen[sh], lid, " ".join(win)))
                else:
                    seen.setdefault(sh, lid)
    if dupes:
        a, b, snip = dupes[0]
        warn("anti-template", f"{len(dupes)} passage(s) of ≥{W} words repeat verbatim across "
             f"lessons — §3: write every lesson body fresh. First: {a} & {b} both contain "
             f"{snip[:70]!r}…")


def check_economy_totals(tome_path, m, sections_data):
    """#10: recompute earnable credit from disk and check the top rank tracks it. §2: 'make
    the top title ≈ total earnable coin'. Base earnable = Σ exercise points + Σ freestyle
    rewards + Σ intrusion bounties (duel coin is a late trickle, excluded per §2). Combos and
    the S multiplier push the real ceiling higher, so the top rank landing a bit UNDER base is
    fine; far under (unreachable ranks) or above (a title no one can earn) is the smell."""
    econ = m.get("economy", {}) or {}
    ranks = econ.get("ranks")
    if not isinstance(ranks, list) or not ranks:
        return
    ex_pts = sum(ex.get("points", 0) or 0
                 for sd in sections_data
                 for les in (sd.get("lessons") or []) if isinstance(les, dict)
                 for ex in (les.get("exercises") or []) if isinstance(ex, dict))
    fs_reward = sum((sd.get("freestyle") or {}).get("reward", 0) or 0
                    for sd in sections_data if isinstance(sd.get("freestyle"), dict))
    tiers, _, e = load_intrusion_tiers(tome_path, m)
    bounty = 0
    if not e and isinstance(tiers, list):
        bounty = sum(t.get("bounty", 0) or 0 for t in tiers if isinstance(t, dict))
    base = ex_pts + fs_reward + bounty
    if base <= 0:
        return
    try:
        top = max(r[0] for r in ranks if isinstance(r, list) and r and isinstance(r[0], (int, float)))
    except ValueError:
        return
    detail = f"(exercises {ex_pts} + freestyles {fs_reward} + bounties {bounty})"
    if top > base * 1.05:
        warn("content", f"[economy] top rank threshold {top} exceeds base earnable {base} "
             f"{detail} — that title is unreachable without heavy combo/S-rank luck; land the "
             "top rank at roughly total earnable (§2)")
    elif top < base * 0.6:
        warn("content", f"[economy] top rank threshold {top} is far below base earnable {base} "
             f"{detail} — the top title is reached with most of the course still ahead; spread "
             "ranks so the last title lands near total earnable (§2)")


def _resolve_run_command(m):
    """The argv that runs ONE file for this tome, plus (entryFile, timeout). Mirrors the
    engine merge: language-TOML defaults ∪ the tome's [runtime], the tome winning."""
    rt = m.get("runtime", {}) or {}
    merged = {**lang_config(rt.get("name") or "custom"), **rt}
    cmd = merged.get("command")
    if not isinstance(cmd, list) or not cmd:
        return None, None, None
    entry = merged.get("entryFile") or "Main.txt"
    timeout = merged.get("runTimeout") or 30
    return cmd, entry, timeout


def _run_one_file(cmd, entry, timeout, source, stdin=None):
    """Run `source` as a single file through the tome's runtime in a temp dir. Returns
    (ok, combined_output) — ok is False on a non-zero exit, timeout, or missing toolchain."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, entry)
        with open(path, "w", encoding="utf-8") as f:
            f.write(source)
        argv = [a.replace("{file}", path) for a in cmd]
        if "{file}" not in " ".join(cmd):
            argv = argv + [path]
        try:
            p = subprocess.run(argv, cwd=d, input=stdin, text=True,
                               capture_output=True, timeout=timeout)
        except FileNotFoundError:
            return False, "__NO_TOOLCHAIN__"
        except subprocess.TimeoutExpired:
            return False, f"timed out after {timeout}s"
        return p.returncode == 0, (p.stdout or "") + (p.stderr or "")


def check_starters_run(tome_path, m, sections_data):
    """#4/#5 (opt-in --run): actually execute every write-lab and intrusion starter through
    the tome's own runtime. Two failures neither structure nor static analysis can see:
      • the starter does not COMPILE/RUN as given — a student under the timer repairs logic,
        not a broken scaffold (Phase 8 used to hand-compile these);
      • the starter ALREADY prints the target `expect` — the exercise is pre-solved, so the
        student has nothing to do (this shipped twice in a past build).
    Language-neutral: it uses [runtime].command, so it works for any tome whose toolchain is
    installed. If the toolchain is absent it degrades to a single WARN, never a false ERROR."""
    cmd, entry, timeout = _resolve_run_command(m)
    if not cmd:
        warn("content", "--run: [runtime] resolves no `command` to run a single file — "
             "cannot execute starters (set command in the language TOML or [runtime])")
        return
    labs = []  # (label, id, starter, expect, stdin)
    for sd in sections_data:
        sid = sd.get("id") or "?"
        for les in (sd.get("lessons") or []):
            if not isinstance(les, dict):
                continue
            for ex in (les.get("exercises") or []):
                if isinstance(ex, dict) and ex.get("type") == "write" and str(ex.get("starter", "")).strip():
                    labs.append((f"{sid}", ex.get("id"), ex["starter"],
                                 ex.get("expect"), ex.get("stdin")))
    tiers, ilabel, e = load_intrusion_tiers(tome_path, m)
    if not e and isinstance(tiers, list):
        for ti, tier in enumerate(tiers):
            for pi, ch in enumerate(tier.get("pool", []) if isinstance(tier, dict) else []):
                if isinstance(ch, dict) and str(ch.get("starter", "")).strip():
                    labs.append((f"intrusion tier {ti + 1} challenge {pi + 1}", None,
                                 ch["starter"], ch.get("expect"), None))
    toolchain_ok = True
    for label, eid, starter, expect, stdin in labs:
        if not toolchain_ok:
            break
        ok, out = _run_one_file(cmd, entry, timeout, starter, stdin)
        name = f"{label}{' ' + repr(eid) if eid else ''}"
        if out == "__NO_TOOLCHAIN__":
            warn("content", f"--run: runtime binary {cmd[0]!r} not installed — skipped "
                 "executing starters (install the toolchain to run this check)")
            toolchain_ok = False
            break
        if not ok:
            err("run", f"{name}: starter does not compile/run as given — a scaffold the student "
                f"can't build on. Runtime said: {out.strip().splitlines()[-1] if out.strip() else '(no output)'}"[:300])
            continue
        # pre-solved: the untouched starter already yields the exact target output
        if expect is not None and str(expect).strip() and norm_lines(out) == norm_lines(expect):
            err("run", f"{name}: starter is PRE-SOLVED — it already prints the exact expect "
                "with no student edits; leave the required logic unwritten (a TODO where the "
                "student codes)")


def check_presolved_static(sections_data):
    """#4/#6 (always on, no execution): the static tell of a pre-solved / hardcodable write
    lab — the target `expect` string appears verbatim as a literal inside the starter, so the
    student can ship it untouched (or by copying). Catches the common case without needing the
    toolchain; --run catches the computed cases this misses."""
    for sd in sections_data:
        sid = sd.get("id") or "?"
        for les in (sd.get("lessons") or []):
            if not isinstance(les, dict):
                continue
            for ex in (les.get("exercises") or []):
                if not isinstance(ex, dict) or ex.get("type") != "write":
                    continue
                starter, expect = str(ex.get("starter", "")), ex.get("expect")
                if not starter.strip() or not (isinstance(expect, str) and expect.strip()):
                    continue
                exp_lines = norm_lines(expect)
                # Every expected line appears as a QUOTED STRING LITERAL in the starter — the
                # print-the-answer signature. Quoted-literal (not bare substring) matching is
                # what keeps input data out: expect "stone" won't match `"minecraft:stone"`.
                if exp_lines and all(any(f'{q}{el}{q}' in starter for q in ('"', "'", "`"))
                                     for el in exp_lines):
                    warn("anti-template", f"{sid}: write {ex.get('id')!r} looks pre-solved — every "
                         "target output line is a string literal already in the starter, so it can "
                         "ship untouched. Set up the data in the starter and leave the printing to "
                         "the student (§3).")


def validate(tome_path, run=False, tooling=None):
    tome_path = os.path.abspath(tome_path.rstrip(os.sep))
    tome_id = os.path.basename(tome_path)
    manifest = os.path.join(tome_path, "tome.toml")
    label = rel(manifest)

    if not os.path.isdir(tome_path):
        err(rel(tome_path), "not a directory")
        return
    m, e = load_toml(manifest)
    if e:
        err(label, e)
        return
    try:
        tome_layout.merge_banks(m, tome_path)  # fold in themes/shop/badges/intrusions siblings, if split out
    except Exception as ex:  # a malformed sibling bank file
        err(label, f"failed to read a split bank file: {ex}")

    meta = check_meta(m, label)
    if meta is not None and meta.get("id") != tome_id:
        err(label, f"[meta] id is {meta.get('id')!r} but the folder is named {tome_id!r} — they must match")
    if not ID_RE.fullmatch(tome_id):
        err(rel(tome_path), f"folder name {tome_id!r} must match [A-Za-z0-9_-]+")

    check_placeholders(check_layout(tome_path, m))
    check_badges(m, tome_path)
    check_runtime(m, tome_id, label)
    check_narrative(m, label)
    check_economy(m, label)
    theme_ids, earned_granted = check_themes(m, label)
    check_theme_distinctness(m, label)
    check_shop(m, theme_ids, earned_granted, label)

    content = m.get("content", {})
    sections = content.get("sections") if isinstance(content, dict) else None
    if not isinstance(sections, list) or not sections:
        err(label, "[content] sections must be a non-empty array of section ids")
        sections = []

    seen_ex, seen_les, seen_sid = set(), set(), set()
    sections_data = []
    for sid in sections:
        if sid in seen_sid:
            err(label, f"[content] section id {sid!r} is listed more than once")
        seen_sid.add(sid)
        folder = os.path.join(tome_path, "sections", str(sid))
        slabel = rel(folder if os.path.isdir(folder) else folder + ".toml")
        try:
            sdata = tome_layout.load_section(tome_path, sid)  # folder or flat
        except Exception as se:
            err(slabel, str(se))
            continue
        check_section(sdata, sid, slabel, seen_ex, seen_les)
        sections_data.append(sdata)
    check_anti_template(sections_data)
    check_density(sections_data)
    check_content(m, sections_data, label, tooling)
    check_taught_before_used(sections_data)
    check_verbatim_prose(sections_data)
    check_economy_totals(tome_path, m, sections_data)
    check_presolved_static(sections_data)
    check_intrusions(tome_path, m, label)
    if run:
        check_starters_run(tome_path, m, sections_data)

    # attacks is optional and machine-generated; default to generated/attacks.toml,
    # and only validate it when the file is actually present.
    attacks_name = (content.get("attacks") if isinstance(content, dict) else None) or "generated/attacks.toml"
    apath = os.path.join(tome_path, str(attacks_name))
    if os.path.isfile(apath):
        stages = (m.get("progression", {}) or {}).get("attackStages")
        check_attacks(apath, m, label, stages)
        check_attacks_sync(tome_path, apath)


def main():
    ap = argparse.ArgumentParser(
        description="Validate one ARCANUM tome folder against TOME-AUTHORING.md.",
        epilog="Fix every ERROR before shipping. WARNs are advisory; a tome that "
               "still emits an ERROR is not done.")
    ap.add_argument("tome", help="path to the tome folder, e.g. tomes/verisearch")
    ap.add_argument("--strict", action="store_true",
                    help="also exit 1 on hard-gate WARNs (anti-template/content) — the "
                         "TOME-WORKFLOW Phase 7 bar; the harness uses this from Phase 7 on")
    ap.add_argument("--run", action="store_true",
                    help="also EXECUTE every write-lab and intrusion starter through the tome's "
                         "runtime: flags starters that don't compile/run and ones already pre-solved. "
                         "Needs the toolchain installed; degrades to a WARN if it isn't.")
    ap.add_argument("--tooling", choices=("internal", "external", "both"), default=None,
                    help="enforce the build's gate Tooling choice: internal forbids "
                         "externalWorkspace; external/both require external tools taught in section 1")
    args = ap.parse_args()

    validate(args.tome, run=args.run, tooling=args.tooling)

    errors = sum(1 for f in _findings if f[0] == "ERROR")
    warns = len(_findings) - errors
    hard = sum(1 for lv, lbl, _ in _findings if lv == "WARN" and lbl in HARD_GATE_LABELS)
    for level, lbl, msg in _findings:
        print(f"{level} {lbl}: {msg}")
    strict_note = f", {hard} hard-gate warn(s) [--strict]" if args.strict and hard else ""
    print(f"-- {os.path.basename(os.path.abspath(args.tome.rstrip(os.sep)))}: "
          f"{errors} error(s), {warns} warning(s){strict_note}")
    sys.exit(1 if errors or (args.strict and hard) else 0)


if __name__ == "__main__":
    main()
