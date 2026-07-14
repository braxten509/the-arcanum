"""The validator gate, the cross-phase no-silent-shrinkage contract, and
ground-truth content measuring (forecast + end-of-run plan reconciliation)."""
import hashlib
import os
import shlex
import subprocess
import tomllib

from . import REPO, VALIDATOR
from .validation_env import validation_subprocess_env

RUNTIME_CONFIG_DIR = os.path.join(REPO, "global-configs", "runtimes")
PHASE3_VALIDATOR = os.path.join(REPO, "tools", "validate_phase3.py")


def validator_argv(tid, phase=None, tooling=None, run=None, strict=None, plan_rel=None,
                   run_section=None):
    """Return the one canonical validator command used by workers and the harness.

    Keeping this as argv (rather than a hand-built flags string) makes command parity
    testable and keeps paths safely quoted when the same command is rendered into a
    worker prompt. ``phase`` selects only genuinely phase-specific gates; explicit
    ``run``/``strict`` overrides are retained for the split-Section fast checkpoint.
    """
    cmd = ["python3", os.path.relpath(VALIDATOR, REPO), f"tomes/{tid}"]
    if phase == 1:
        if not plan_rel:
            raise ValueError("Phase 1 validator command needs plan_rel")
        return cmd + ["--phase-1-plan", plan_rel]

    if phase == 2:
        cmd.append("--phase-2-skeleton")
    strict = (phase is not None and phase >= 7) if strict is None else strict
    run = (phase != 2) if run is None else run
    if strict:
        cmd.append("--strict")
    if not run:
        cmd.append("--no-run")
    if tooling:
        cmd += ["--tooling", tooling]  # enforce the gate's internal/external/both choice
    if run_section:
        cmd += ["--run-section", str(run_section)]
    return cmd


def validator_shell_command(tid, phase=None, tooling=None, run=None, strict=None,
                            plan_rel=None, run_section=None):
    """The canonical argv rendered exactly as the worker should run it."""
    return ('cd "$ARCANUM_REPO_ROOT" && '
            + shlex.join(validator_argv(
                tid, phase, tooling, run, strict, plan_rel, run_section)))


def phase3_validator_argv(tid, tooling, plan_rel, run=True, strict=False):
    if not plan_rel:
        raise ValueError("complete Phase-3 validator command needs plan_rel")
    cmd = ["python3", os.path.relpath(PHASE3_VALIDATOR, REPO), f"tomes/{tid}",
           "--plan", plan_rel]
    if tooling:
        cmd += ["--tooling", tooling]
    if strict:
        cmd.append("--strict")
    if not run:
        cmd.append("--no-run")
    return cmd


def phase3_validator_shell_command(tid, tooling, plan_rel, run=True, strict=False):
    """The exact complete Phase-3/shipping gate shared by worker and harness."""
    return ('cd "$ARCANUM_REPO_ROOT" && '
            + shlex.join(phase3_validator_argv(tid, tooling, plan_rel, run, strict)))


def section_validator_argv(tid, sid, tooling, plan_rel):
    """Return the complete fast Phase-3 gate for one section and its handoff."""
    if not plan_rel:
        raise ValueError("split-section validator command needs plan_rel")
    cmd = ["python3", "tools/validate_section.py", f"tomes/{tid}", sid,
           "--plan", plan_rel]
    if tooling:
        cmd += ["--tooling", tooling]
    return cmd


def section_validator_shell_command(tid, sid, tooling, plan_rel):
    """Render the exact complete section gate for a warm worker prompt."""
    return ('cd "$ARCANUM_REPO_ROOT" && '
            + shlex.join(section_validator_argv(tid, sid, tooling, plan_rel)))


def section_window_validator_argv(tid, through, plan_rel):
    """Return the continuity + anti-template checkpoint for an authored prefix."""
    if not plan_rel:
        raise ValueError("section-window validator command needs plan_rel")
    return ["python3", "tools/validate_section_window.py", f"tomes/{tid}",
            "--through", through, "--plan", plan_rel]


def section_window_validator_shell_command(tid, through, plan_rel):
    """Render the periodic same-worker quality checkpoint."""
    return ('cd "$ARCANUM_REPO_ROOT" && '
            + shlex.join(section_window_validator_argv(tid, through, plan_rel)))


def validate(tid, phase=None, strict=None, tooling=None, run=None, plan_rel=None,
             run_section=None):
    cmd = validator_argv(tid, phase, tooling, run, strict, plan_rel, run_section)
    p = subprocess.run(cmd, cwd=REPO, env=validation_subprocess_env(tid),
                       capture_output=True, text=True)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def validate_section(tid, sid, tooling, plan_rel):
    """Repeat the worker's exact combined content + continuity command independently."""
    cmd = section_validator_argv(tid, sid, tooling, plan_rel)
    p = subprocess.run(cmd, cwd=REPO, env=validation_subprocess_env(tid),
                       capture_output=True, text=True)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def validate_section_window(tid, through, plan_rel):
    """Run a cross-section quality window independently of the author worker."""
    cmd = section_window_validator_argv(tid, through, plan_rel)
    p = subprocess.run(cmd, cwd=REPO, env=validation_subprocess_env(tid),
                       capture_output=True, text=True)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def validate_phase3(tid, tooling, plan_rel, _sections):
    """Repeat the worker's complete executable/authorship/continuity command."""
    cmd = phase3_validator_argv(tid, tooling, plan_rel)
    process = subprocess.run(cmd, cwd=REPO, env=validation_subprocess_env(tid),
                             capture_output=True, text=True)
    return process.returncode == 0, (process.stdout + process.stderr).strip()


def validate_shipping(tid, tooling, plan_rel):
    """Strict tome validation plus Phase-3 completion and continuity invariants."""
    cmd = phase3_validator_argv(tid, tooling, plan_rel, strict=True)
    process = subprocess.run(cmd, cwd=REPO, env=validation_subprocess_env(tid),
                             capture_output=True, text=True)
    return process.returncode == 0, (process.stdout + process.stderr).strip()


def blocking_report(report, strict=False):
    """Trim validator output to findings that can actually fail the current gate.

    A non-strict phase exits nonzero only for ``ERROR``. Strict phases additionally
    fail on non-advisory ``WARN`` findings. If the process crashed or returned some
    unexpected format, preserve the full report so diagnostics are never hidden.
    """
    lines = str(report or "").splitlines()
    blockers = []
    for line in lines:
        if line.startswith("ERROR "):
            blockers.append(line)
        elif (strict and line.startswith("WARN ")
              and not line.startswith("WARN advisory:")):
            blockers.append(line)
    summaries = [line for line in lines if line.startswith("-- ")]
    return "\n".join(blockers + summaries) if blockers else str(report or "").strip()


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
    """Ground-truth counts: content/bank sizes, fixed rewards, and repeatable hex range.
    Feeds the pre-build forecast (#23) and the post-build plan reconciliation (#11) — the plan
    is prose and 'claims are not evidence', so the harness writes the real numbers itself."""
    root = os.path.join(REPO, "tomes", tid)
    out = {"sections": 0, "lessons": 0, "exercises": 0, "ex_points": 0,
           "fs_reward": 0, "bounty": 0, "bounty_min": 0, "bounty_max": 0,
           "badges": 0, "themes": 0, "shop": 0}
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
    bounties = [t.get("bounty") for t in tiers if isinstance(t, dict)
                and isinstance(t.get("bounty"), (int, float))
                and not isinstance(t.get("bounty"), bool)]
    out["bounty"] = sum(bounties)
    out["bounty_min"] = min(bounties, default=0)
    out["bounty_max"] = max(bounties, default=0)
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
    # Hex defenses repeat every 10–15 minutes and may be won zero or many times.
    # Their tier schedule is useful balance context, but it is not a finite base total.
    out["base_earnable"] = out["ex_points"] + out["fs_reward"]
    return out


def forecast_line(mv):
    """One rough line: content size + a crude token estimate (lessons/exercises are the bulk).
    Deliberately a heuristic, not a promise — it's a 'how big is this getting' gut-check."""
    est_k = round((mv["lessons"] * 1.2 + mv["exercises"] * 0.4) )  # ~KB of TOML, order-of-magnitude
    hex_part = (f" · repeatable hex bounty {mv['bounty_min']}–{mv['bounty_max']}/win"
                if mv.get("bounty_max") else "")
    return (f"{mv['sections']} sections · {mv['lessons']} lessons · {mv['exercises']} exercises "
            f"· fixed face-value {mv['base_earnable']}{hex_part} · ~{est_k}KB content (rough)")
