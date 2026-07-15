"""Durable phase-start snapshots and destructive tome build rewinds.

The authoring harness records the tome exactly as each phase begins.  The Binder can
later restore that checkpoint, clear terminal build state, erase the learner save, and
turn the tome back into an unfinished working.  Older builds without snapshots use the
same phase-ownership contract to reconstruct the closest deterministic phase boundary.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import tempfile
import time

from . import BUILD_DIR, REPO
from .checkpoints import ARC_CONTRACT, ARC_HEADING
from .skeleton import scaffold_sections
from arcanum.tomes import resolve_working_tid


TOMES_DIR = os.path.join(REPO, "tomes")
PHASE_TITLES = ("", "Concept & arc", "Skeleton & voice", "Sections", "Minigames",
                "Economy", "Cosmetics", "Validate", "Student review")
ID_RE = re.compile(r"[A-Za-z0-9_-]+")
GROUND_TRUTH_RE = re.compile(r"(?m)^## Harness ground truth\b")
RENAME_RE = re.compile(
    r"(?m)^\s*-\s*\*\*Tome id renamed by the harness:\*\*[^\n]*(?:\n|$)")

ECONOMY_SCAFFOLD = """[economy]
# TODO: rebalance once your exercise/freestyle points are set (see § [economy]).
ranks = [[0, "NOVICE"], [400, "ADEPT"], [1000, "MASTER"]]
hintCost = 50
oracleCost = 10
attemptMultipliers = [1, 0.6, 0.3]
comboStep = 0.05
comboCap = 0.5
sRankMultiplier = 1.5
attackStakePerDiff = 20
attackWinPerDiff = 15

"""

TERMINAL_SUFFIXES = (
    "active.json", "cancelled.json", "result.json", "session.json",
    "conversation.jsonl", "amend.json", "progress", "section-progress.json",
)
PHASE3_SIDECARS = ("handoffs", "sections-done")
PHASE7_SIDECARS = ("proof-evidence.json", "shrink-ok", "learner-project")
PHASE8_SIDECARS = ("findings.json", "verdict")


def _valid_id(value):
    value = str(value or "")
    if not ID_RE.fullmatch(value):
        raise ValueError(f"invalid tome/build id {value!r}")
    return value


def _atomic_text(path, text):
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(temp, path)


def _atomic_json(path, value):
    _atomic_text(path, json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def _read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _remove(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    else:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def find_plan_for_tome(tid):
    """Return the newest ``(build_id, path, text)`` whose plan resolves to ``tid``."""
    tid = _valid_id(tid)
    matches = []
    for path in glob.glob(os.path.join(BUILD_DIR, "*.plan.md")):
        build_id = os.path.basename(path)[:-len(".plan.md")]
        if not ID_RE.fullmatch(build_id):
            continue
        try:
            text = _read_text(path)
        except OSError:
            continue
        if build_id == tid or resolve_working_tid(build_id, text) == tid:
            matches.append((os.path.getmtime(path), build_id, path, text))
    if not matches:
        raise ValueError("this tome has no Bindery build plan, so it cannot be reset by phase")
    _mtime, build_id, path, text = max(matches)
    return build_id, path, text


def reset_plan_text(text, phase):
    """Remove completion evidence and return the plan shape valid at ``phase`` start."""
    phase = int(phase)
    if phase not in range(1, 9):
        raise ValueError("phase must be between 1 and 8")
    match = GROUND_TRUTH_RE.search(text)
    if match:
        text = text[:match.start()].rstrip() + "\n"
    if phase == 1:
        head, marker, _old_arc = text.partition("## Arc")
        if not marker:
            raise ValueError("the build plan has no Arc boundary to reset")
        return head + ARC_HEADING + ARC_CONTRACT
    if phase == 2:
        text = RENAME_RE.sub("", text)
    return text.rstrip() + "\n"


def snapshot_root(build_id):
    return os.path.join(BUILD_DIR, f"{_valid_id(build_id)}.phase-snapshots")


def snapshot_path(build_id, phase):
    return os.path.join(snapshot_root(build_id), f"phase-{int(phase)}")


def _copy_item(source, target):
    if os.path.isdir(source) and not os.path.islink(source):
        shutil.copytree(source, target)
    else:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target)


def _baseline_sidecars(build_id, tid, phase):
    suffixes = list(PHASE3_SIDECARS if phase >= 4 else ())
    if phase >= 8:
        suffixes.extend(PHASE7_SIDECARS)
    for key in {build_id, tid}:
        for suffix in suffixes:
            path = os.path.join(BUILD_DIR, f"{key}.{suffix}")
            if os.path.exists(path):
                yield path


def capture_phase_snapshot(build_id, phase, replace=False):
    """Record an immutable phase-start tome/plan checkpoint. Returns ``True`` if written."""
    build_id, phase = _valid_id(build_id), int(phase)
    if phase not in range(1, 9):
        raise ValueError("phase must be between 1 and 8")
    plan = os.path.join(BUILD_DIR, f"{build_id}.plan.md")
    text = _read_text(plan)
    tid = resolve_working_tid(build_id, text)
    tome = os.path.join(TOMES_DIR, _valid_id(tid))
    if not os.path.isfile(os.path.join(tome, "tome.toml")):
        raise ValueError(f"cannot snapshot missing tomes/{tid}/tome.toml")
    root, target = snapshot_root(build_id), snapshot_path(build_id, phase)
    if os.path.isdir(target) and not replace:
        return False
    os.makedirs(root, exist_ok=True)
    temp = tempfile.mkdtemp(prefix=f".phase-{phase}-", dir=root)
    try:
        shutil.copytree(tome, os.path.join(temp, "tome"),
                        ignore=shutil.ignore_patterns("save"))
        shutil.copy2(plan, os.path.join(temp, "plan.md"))
        sidecars = os.path.join(temp, "sidecars")
        for source in _baseline_sidecars(build_id, tid, phase):
            os.makedirs(sidecars, exist_ok=True)
            _copy_item(source, os.path.join(sidecars, os.path.basename(source)))
        _atomic_json(os.path.join(temp, "meta.json"), {
            "buildId": build_id, "tomeId": tid, "phase": phase,
            "phaseTitle": PHASE_TITLES[phase], "capturedAt": time.time(),
        })
        if replace:
            _remove(target)
        os.replace(temp, target)
        return True
    finally:
        if os.path.exists(temp):
            shutil.rmtree(temp, ignore_errors=True)


def _load_snapshot(build_id, phase):
    root = snapshot_path(build_id, phase)
    try:
        with open(os.path.join(root, "meta.json"), encoding="utf-8") as handle:
            meta = json.load(handle)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    tome = os.path.join(root, "tome")
    plan = os.path.join(root, "plan.md")
    try:
        tid = _valid_id(meta.get("tomeId"))
    except ValueError:
        return None
    if int(meta.get("phase") or 0) != int(phase) or not os.path.isdir(tome) or not os.path.isfile(plan):
        return None
    return {"root": root, "tome": tome, "plan": plan,
            "sidecars": os.path.join(root, "sidecars"), "tomeId": tid}


def _fresh_tome(tid):
    """Create the ordinary one-section split scaffold under the active TOMES_DIR."""
    try:
        from tools.new_tome import SECTION_TEMPLATE, TOME_TEMPLATE, render, roman
        from tools import split_tome
    except ModuleNotFoundError:  # build_tome.py imports buildlib with tools/ on sys.path
        from new_tome import SECTION_TEMPLATE, TOME_TEMPLATE, render, roman
        import split_tome
    tome = os.path.join(TOMES_DIR, tid)
    if os.path.exists(tome):
        raise ValueError(f"refused to overwrite existing tomes/{tid}")
    name = tid.replace("-", " ").replace("_", " ").title()
    project = "".join(word.capitalize() for word in re.split(r"[-_ ]+", tid)) or "Project"
    os.makedirs(os.path.join(tome, "sections"))
    manifest = render(TOME_TEMPLATE, {
        "ID": tid, "NAME": name, "RUNTIME": "python", "LANGUAGE": "Python",
        "PROJECT": project, "SECTIONS_ARRAY": '"s01"',
    })
    _atomic_text(os.path.join(tome, "tome.toml"), manifest.lstrip("\n"))
    section = render(SECTION_TEMPLATE, {"SID": "s01", "ROMAN": roman(1)})
    _atomic_text(os.path.join(tome, "sections", "s01.toml"), section.lstrip("\n"))
    previous_quiet = split_tome.QUIET
    split_tome.QUIET = True
    try:
        split_tome.migrate_manifest(tome)
        split_tome.migrate_section(tome, "s01")
    finally:
        split_tome.QUIET = previous_quiet


def _replace_economy(manifest):
    text = _read_text(manifest)
    updated, count = re.subn(r"(?ms)^\[economy\][^\n]*\n.*?(?=^\[|\Z)",
                             ECONOMY_SCAFFOLD, text, count=1)
    if count != 1:
        raise ValueError("tome.toml has no top-level [economy] block to reset")
    _atomic_text(manifest, updated)


def _fallback_phase_boundary(tome, tid, plan, phase):
    """Reconstruct a phase boundary for builds created before snapshots existed."""
    if phase <= 3:
        scaffold_sections(tid, plan, force=True, repo=os.path.dirname(TOMES_DIR))
    if phase <= 4:
        for relative in ("intrusions.toml", "attacks_src.toml", "generated"):
            _remove(os.path.join(tome, relative))
    if phase <= 5:
        _replace_economy(os.path.join(tome, "tome.toml"))
    if phase <= 6:
        for relative in ("themes.toml", "shop.toml", "badges.toml"):
            _remove(os.path.join(tome, relative))


def _clear_sidecars(keys, phase, everything=False):
    for key in {_valid_id(value) for value in keys if value}:
        for suffix in TERMINAL_SUFFIXES + PHASE8_SIDECARS:
            _remove(os.path.join(BUILD_DIR, f"{key}.{suffix}"))
        if everything or phase <= 3:
            for suffix in PHASE3_SIDECARS:
                _remove(os.path.join(BUILD_DIR, f"{key}.{suffix}"))
        if everything or phase <= 7:
            for suffix in PHASE7_SIDECARS:
                _remove(os.path.join(BUILD_DIR, f"{key}.{suffix}"))


def _restore_snapshot_sidecars(snapshot):
    source = snapshot.get("sidecars")
    if not source or not os.path.isdir(source):
        return
    for name in os.listdir(source):
        if os.path.basename(name) != name:
            raise ValueError("unsafe snapshot sidecar name")
        _copy_item(os.path.join(source, name), os.path.join(BUILD_DIR, name))


def _stage_sidecars(keys, transaction):
    target = os.path.join(transaction, "build-state")
    os.makedirs(target, exist_ok=True)
    suffixes = TERMINAL_SUFFIXES + PHASE3_SIDECARS + PHASE7_SIDECARS + PHASE8_SIDECARS
    for key in {_valid_id(value) for value in keys if value}:
        for suffix in suffixes:
            source = os.path.join(BUILD_DIR, f"{key}.{suffix}")
            if os.path.exists(source):
                os.replace(source, os.path.join(target, os.path.basename(source)))
    return target


def _copy_staged_sidecars(source, suffixes):
    if not suffixes or not os.path.isdir(source):
        return
    endings = tuple(f".{suffix}" for suffix in suffixes)
    for name in os.listdir(source):
        if name.endswith(endings):
            _copy_item(os.path.join(source, name), os.path.join(BUILD_DIR, name))


def _stage_later_snapshots(build_id, phase, transaction):
    target = os.path.join(transaction, "later-snapshots")
    os.makedirs(target, exist_ok=True)
    for later in range(int(phase) + 1, 9):
        source = snapshot_path(build_id, later)
        if os.path.exists(source):
            os.replace(source, os.path.join(target, os.path.basename(source)))
    return target


def _restore_later_snapshots(build_id, source):
    if not os.path.isdir(source):
        return
    os.makedirs(snapshot_root(build_id), exist_ok=True)
    for name in os.listdir(source):
        os.replace(os.path.join(source, name), os.path.join(snapshot_root(build_id), name))


def reset_tome_to_phase(tid, phase):
    """Restore ``tid`` to a phase start, erase its save, and mark it unfinished."""
    tid, phase = _valid_id(tid), int(phase)
    if phase not in range(1, 9):
        raise ValueError("phase must be between 1 and 8")
    build_id, plan, original_plan = find_plan_for_tome(tid)
    current_tome = os.path.realpath(os.path.join(TOMES_DIR, tid))
    if (os.path.dirname(current_tome) != os.path.realpath(TOMES_DIR)
            or not os.path.isdir(current_tome)):
        raise ValueError(f"tomes/{tid} is missing or unsafe")
    snapshot = _load_snapshot(build_id, phase)
    target_tid = snapshot["tomeId"] if snapshot else (build_id if phase <= 2 else tid)
    target_tid = _valid_id(target_tid)
    target_tome = os.path.realpath(os.path.join(TOMES_DIR, target_tid))
    if os.path.dirname(target_tome) != os.path.realpath(TOMES_DIR):
        raise ValueError("refused unsafe reset target")
    if target_tome != current_tome and os.path.exists(target_tome):
        raise ValueError(f"refused to overwrite existing tomes/{target_tid}")

    transaction = tempfile.mkdtemp(prefix=".phase-reset-", dir=TOMES_DIR)
    backup = os.path.join(transaction, "original-tome")
    state_backup = os.path.join(transaction, "build-state")
    snapshot_backup = os.path.join(transaction, "later-snapshots")
    moved_tome = False
    try:
        _stage_sidecars((build_id, tid, target_tid), transaction)
        _stage_later_snapshots(build_id, phase, transaction)
        os.replace(current_tome, backup)
        moved_tome = True
        plan_text = reset_plan_text(
            _read_text(snapshot["plan"]) if snapshot else original_plan, phase)
        _atomic_text(plan, plan_text)
        if snapshot:
            shutil.copytree(snapshot["tome"], target_tome)
            _clear_sidecars((build_id, tid, target_tid), phase, everything=True)
            _restore_snapshot_sidecars(snapshot)
        elif phase <= 2:
            _fresh_tome(target_tid)
            if phase == 2:
                scaffold_sections(target_tid, plan, force=True,
                                  repo=os.path.dirname(TOMES_DIR))
            _clear_sidecars((build_id, tid, target_tid), phase)
        else:
            shutil.copytree(backup, target_tome, ignore=shutil.ignore_patterns("save"))
            _fallback_phase_boundary(target_tome, target_tid, plan, phase)
            _clear_sidecars((build_id, tid, target_tid), phase)

        if not snapshot:
            preserved = (() if phase <= 3 else PHASE3_SIDECARS) + (
                () if phase <= 7 else PHASE7_SIDECARS)
            _copy_staged_sidecars(state_backup, preserved)

        os.makedirs(os.path.join(target_tome, "save"), exist_ok=True)
        now = time.time()
        _atomic_json(os.path.join(BUILD_DIR, f"{build_id}.progress"), {
            "phase": phase, "phaseTitle": PHASE_TITLES[phase], "state": "working",
            "phaseStartedAt": now, "updatedAt": now,
        })
        if not snapshot:
            capture_phase_snapshot(build_id, phase, replace=True)
        shutil.rmtree(transaction, ignore_errors=True)
        return {"id": build_id, "tome": target_tid, "phase": phase,
                "phaseTitle": PHASE_TITLES[phase], "usedSnapshot": bool(snapshot)}
    except Exception:
        if moved_tome:
            _remove(target_tome)
        _atomic_text(plan, original_plan)
        if moved_tome:
            _clear_sidecars((build_id, tid, target_tid), phase, everything=True)
        _copy_staged_sidecars(state_backup,
                              TERMINAL_SUFFIXES + PHASE3_SIDECARS
                              + PHASE7_SIDECARS + PHASE8_SIDECARS)
        _restore_later_snapshots(build_id, snapshot_backup)
        if os.path.exists(backup):
            os.replace(backup, current_tome)
        shutil.rmtree(transaction, ignore_errors=True)
        raise
