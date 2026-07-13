"""The validator gate, the cross-phase no-silent-shrinkage contract, and
ground-truth content measuring (forecast + end-of-run plan reconciliation)."""
import hashlib
import os
import subprocess
import sys
import tomllib

from . import REPO, VALIDATOR

RUNTIME_CONFIG_DIR = os.path.join(REPO, "global-configs", "runtimes")


def validate(tid, strict=False, tooling=None, run=True):
    cmd = [sys.executable, VALIDATOR, f"tomes/{tid}"] + (["--strict"] if strict else [])
    if not run:
        cmd.append("--no-run")
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


def shrink_marks(path):
    """How many `SHRINK OK` lines the dedicated justification sidecar carries."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().count("SHRINK OK")
    except OSError:
        return 0


def runtime_config_inventory(root=RUNTIME_CONFIG_DIR):
    """Content hashes for the shared runtime-directory write audit."""
    out = {}
    try:
        names = os.listdir(root)
    except OSError:
        return out
    for name in names:
        path = os.path.join(root, name)
        if os.path.isfile(path):
            try:
                with open(path, "rb") as f:
                    out[name] = hashlib.sha256(f.read()).hexdigest()
            except OSError:
                pass
    return out


def review_inventory(tid, runtime_root=RUNTIME_CONFIG_DIR):
    """Hashes of every authored tome file plus every runtime config.

    Phase 8 uses this snapshot around one reviewer invocation.  Sidecars are excluded,
    so writing the required verdict is not mistaken for an editorial repair; ``save/``
    is excluded because it is learner state rather than authored course content.  The
    runtime directory is included in full because the post-write scope audit separately
    rejects changes to anything except the runtime selected by this tome.
    """
    root = os.path.join(REPO, "tomes", tid)
    out = {}
    if os.path.isdir(root):
        for dirpath, dirs, names in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d != "save")
            for name in sorted(names):
                path = os.path.join(dirpath, name)
                if not os.path.isfile(path):
                    continue
                key = os.path.relpath(path, REPO).replace(os.sep, "/")
                try:
                    with open(path, "rb") as f:
                        out[key] = hashlib.sha256(f.read()).hexdigest()
                except OSError:
                    pass
    for name, digest in runtime_config_inventory(runtime_root).items():
        out[f"global-configs/runtimes/{name}"] = digest
    return out


def review_changes(before, after):
    """Human-readable authored-file changes between two Phase-8 snapshots."""
    changes = []
    for path in sorted(before.keys() | after.keys()):
        if path not in before:
            kind = "ADDED"
        elif path not in after:
            kind = "DELETED"
        elif before[path] != after[path]:
            kind = "MODIFIED"
        else:
            continue
        changes.append(f"{kind}: {path}")
    return changes


def selected_runtime_config(tid):
    try:
        with open(os.path.join(REPO, "tomes", tid, "tome.toml"), "rb") as f:
            runtime = tomllib.load(f).get("runtime")
    except (OSError, tomllib.TOMLDecodeError):
        return None
    if not isinstance(runtime, dict):
        return None
    name = runtime.get("name")
    return str(name) + ".toml" if name else None


def runtime_config_scope_violations(before, allowed, root=RUNTIME_CONFIG_DIR):
    """A runtime-writing phase may alter only the runtime selected by its tome."""
    after = runtime_config_inventory(root)
    changed = sorted(name for name in before.keys() | after.keys()
                     if before.get(name) != after.get(name))
    wrong = [name for name in changed if name != allowed]
    return (["runtime config OUT OF SCOPE: " + ", ".join(wrong)
             + f" (this tome selects {allowed or 'no valid runtime'}; restore every other file)"]
            if wrong else [])


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
