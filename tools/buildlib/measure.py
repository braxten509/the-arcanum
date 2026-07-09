"""The validator gate, the cross-phase no-silent-shrinkage contract, and
ground-truth content measuring (forecast + end-of-run plan reconciliation)."""
import os
import subprocess
import sys
import tomllib

from . import REPO, VALIDATOR


def validate(tid, strict=False, tooling=None):
    cmd = [sys.executable, VALIDATOR, f"tomes/{tid}"] + (["--strict"] if strict else [])
    if tooling:
        cmd += ["--tooling", tooling]  # enforce the gate's internal/external/both choice
    p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def inventory(tid):
    """Tome-root-relative file list + top-level array length per TOML — the cross-phase
    no-silent-shrinkage contract. The failure this catches: Phase 6 registers six badges,
    Phase 7 rewrites badges.toml down to one while 'clearing TODOs', and no later gate
    can know what used to exist. Paths are root-relative so a folder rename is invisible.
    # ponytail: top-level arrays only (badges/themes/shop/tiers/lessons/challenge) —
    # count nested ones (lessons.exercises) if erosion ever moves a level down."""
    root = os.path.join(REPO, "tomes", tid)
    files, arrays = set(), {}
    if not os.path.isdir(root):
        return {"files": files, "arrays": arrays}
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d != "save"]  # runtime state, not content
        for n in names:
            p = os.path.join(dirpath, n)
            r = os.path.relpath(p, root).replace(os.sep, "/")
            files.add(r)
            if n.endswith(".toml"):
                try:
                    with open(p, "rb") as f:
                        arrays[r] = {k: len(v) for k, v in tomllib.load(f).items()
                                     if isinstance(v, list)}
                except Exception:
                    pass  # unparseable mid-phase files are the validator's problem
    return {"files": files, "arrays": arrays}


def shrinkage(before, after):
    """What the phase deleted or shrank, as human-readable lines (empty = clean)."""
    probs = [f"file DELETED: {f}" for f in sorted(before["files"] - after["files"])]
    for f, keys in sorted(before["arrays"].items()):
        cur = after["arrays"].get(f)
        if cur is None:
            continue  # deletion already reported above
        for k, n in keys.items():
            if cur.get(k, 0) < n:
                probs.append(f"{f}: [[{k}]] shrank {n} -> {cur.get(k, 0)} entries")
    return probs


def plan_shrink_marks(plan_path):
    """How many `SHRINK OK` justification lines the plan carries — the escape hatch for
    deliberate removals (a new mark during a phase accepts that phase's shrinkage)."""
    try:
        with open(plan_path, encoding="utf-8") as f:
            return f.read().count("SHRINK OK")
    except OSError:
        return 0


def measure(tid):
    """Ground-truth counts from disk: sections/lessons/exercises + bank sizes + economy total.
    Feeds the pre-build forecast (#23) and the post-build plan reconciliation (#11) — the plan
    is prose and 'claims are not evidence', so the harness writes the real numbers itself."""
    root = os.path.join(REPO, "tomes", tid)
    out = {"sections": 0, "lessons": 0, "exercises": 0, "ex_points": 0,
           "fs_reward": 0, "bounty": 0, "badges": 0, "themes": 0, "shop": 0}
    if not os.path.isdir(root):
        return out

    def load(*parts):
        p = os.path.join(root, *parts)
        try:
            with open(p, "rb") as f:
                return tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError):
            return {}

    manifest = load("tome.toml")
    for bank, key in (("themes", "themes"), ("shop", "shop"), ("badges", "badges")):
        data = load(f"{bank}.toml") or manifest
        out[key] = len(data.get(key, []) or [])
    tiers = (load("intrusions.toml").get("tiers")
             or (manifest.get("progression", {}) or {}).get("intrusionTiers") or [])
    out["bounty"] = sum(t.get("bounty", 0) or 0 for t in tiers if isinstance(t, dict))
    sids = (manifest.get("content", {}) or {}).get("sections") or []
    for sid in sids:
        sd = None
        for cand in ((f"sections/{sid}", "section.toml"), (f"sections/{sid}.toml",)):
            d = load(*cand)
            if d:
                sd = d if len(cand) == 1 else d
                break
        # in split layout the section keys + freestyle + lessons live in sibling files;
        # count lessons/exercises/freestyle across whichever files exist
        out["sections"] += 1
        fdir = os.path.join(root, "sections", str(sid))
        fs = load(f"sections/{sid}", "freestyle.toml").get("freestyle") or (sd or {}).get("freestyle") or {}
        out["fs_reward"] += fs.get("reward", 0) or 0
        les_list = []
        ldir = os.path.join(fdir, "lessons")
        if os.path.isdir(ldir):
            for ln in sorted(os.listdir(ldir)):
                les_list += load(f"sections/{sid}", "lessons", ln).get("lessons", []) or []
        else:
            les_list = (sd or {}).get("lessons", []) or []
        out["lessons"] += len(les_list)
        for les in les_list:
            exs = les.get("exercises", []) or []
            out["exercises"] += len(exs)
            out["ex_points"] += sum(e.get("points", 0) or 0 for e in exs if isinstance(e, dict))
    out["base_earnable"] = out["ex_points"] + out["fs_reward"] + out["bounty"]
    return out


def forecast_line(mv):
    """One rough line: content size + a crude token estimate (lessons/exercises are the bulk).
    Deliberately a heuristic, not a promise — it's a 'how big is this getting' gut-check."""
    est_k = round((mv["lessons"] * 1.2 + mv["exercises"] * 0.4) )  # ~KB of TOML, order-of-magnitude
    return (f"{mv['sections']} sections · {mv['lessons']} lessons · {mv['exercises']} exercises "
            f"· base earnable {mv['base_earnable']} · ~{est_k}KB content (rough)")
