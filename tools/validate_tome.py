#!/usr/bin/env python3
"""validate_tome.py — hold a tome up to the candlelight before you ship it.

Machine-checks one tome folder against the rules in TOME-AUTHORING.md: does the
TOML parse, do the ids line up, does every palette carry all 18 inks, do the
rubric weights sum true. One finding per line; a tome with any ERROR is not done.

    python3 tools/validate_tome.py tomes/<id>

Exit 0 = clean (WARNs allowed). Exit 1 = at least one ERROR. Stdlib only.
"""
import argparse
import os
import re
import sys

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
# The six engine consumable mechanics (§ [[shop]]). Any other consumable id
# renders in the shop but does nothing — a WARN, never an ERROR.
CONSUMABLE_IDS = {"firewall", "x2", "skip", "vpn", "xray", "oracle"}
META_REQUIRED = ["id", "name", "description", "author", "version", "favicon"]
ID_RE = re.compile(r"[A-Za-z0-9_-]+")

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
    ws = rt.get("workspaceDir")
    if ws is not None:
        if not isinstance(ws, str) or not os.path.isabs(os.path.expanduser(ws)):
            err(label, "[runtime] workspaceDir must be an absolute path")


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


def check_shop(m, theme_ids, label):
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


def check_themes(m, label):
    themes = m.get("themes", [])
    if not isinstance(themes, list) or not themes:
        err(label, "[[themes]] — at least one signature palette is required")
        return set()
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
        present = set(th.get("vars", {}) or {})
        missing = THEME_VARS - present
        if missing:
            err(label, f"[[themes]] {tid!r}: missing theme var(s): "
                       + ", ".join(sorted(missing)))
        extra = present - THEME_VARS
        if extra:
            warn(label, f"[[themes]] {tid!r}: unknown theme var(s): " + ", ".join(sorted(extra)))

    defaults = m.get("defaults", {})
    dtheme = defaults.get("theme") if isinstance(defaults, dict) else None
    if dtheme is not None and dtheme not in theme_ids and dtheme not in global_skin_ids():
        err(label, f"[defaults] theme {dtheme!r} is neither a [[themes]] id in this "
                   "tome nor a global skin id under skins/")

    earned_ref = (m.get("progression", {}) or {}).get("earnedTheme", {})
    if isinstance(earned_ref, dict) and earned_ref.get("id"):
        eid = earned_ref["id"]
        if eid not in theme_ids:
            err(label, f"[progression.earnedTheme] id {eid!r} has no matching [[themes]] entry")
        elif eid not in earned_ids:
            err(label, f"[progression.earnedTheme] id {eid!r} must mark that theme earned = true")
    return theme_ids


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
        for ex in les.get("exercises", []):
            check_exercise(ex, slabel, seen_ex)


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
    for ti, tier in enumerate(tiers):
        for pi, chal in enumerate(tier.get("pool", []) if isinstance(tier, dict) else []):
            where = f"tier {ti + 1} challenge {pi + 1}"
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


def validate(tome_path):
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

    check_runtime(m, tome_id, label)
    check_narrative(m, label)
    check_economy(m, label)
    theme_ids = check_themes(m, label)
    check_shop(m, theme_ids, label)

    content = m.get("content", {})
    sections = content.get("sections") if isinstance(content, dict) else None
    if not isinstance(sections, list) or not sections:
        err(label, "[content] sections must be a non-empty array of section ids")
        sections = []

    seen_ex, seen_les, seen_sid = set(), set(), set()
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

    # attacks is optional and machine-generated; default to generated/attacks.toml,
    # and only validate it when the file is actually present.
    attacks_name = (content.get("attacks") if isinstance(content, dict) else None) or "generated/attacks.toml"
    apath = os.path.join(tome_path, str(attacks_name))
    if os.path.isfile(apath):
        stages = (m.get("progression", {}) or {}).get("attackStages")
        check_attacks(apath, m, label, stages)


def main():
    ap = argparse.ArgumentParser(
        description="Validate one ARCANUM tome folder against TOME-AUTHORING.md.",
        epilog="Fix every ERROR before shipping. WARNs are advisory; a tome that "
               "still emits an ERROR is not done.")
    ap.add_argument("tome", help="path to the tome folder, e.g. tomes/verisearch")
    args = ap.parse_args()

    validate(args.tome)

    errors = sum(1 for f in _findings if f[0] == "ERROR")
    warns = len(_findings) - errors
    for level, lbl, msg in _findings:
        print(f"{level} {lbl}: {msg}")
    print(f"-- {os.path.basename(os.path.abspath(args.tome.rstrip(os.sep)))}: "
          f"{errors} error(s), {warns} warning(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
