#!/usr/bin/env python3
"""Regression coverage for Binder phase rewinds and phase-start snapshots."""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from arcanum import build_state, forge, tomes
from tools.buildlib import phase_reset
from tools.buildlib.checkpoints import ARC_CONTRACT, ARC_HEADING


PLAN_HEAD = """# Build plan: build

## Concept
Teach a thing

## Gate answers
- **Tooling:** internal

"""
ARC = """## Arc (Phase 1 fills this in, later phases read it)
**Finished tool:** Finished
**Section list:**
1. **s01 — First:** first promise
"""
RENAME = ("- **Tome id renamed by the harness:** `build` → `demo` "
          "(kebab-case of project 'Demo'); all later phases use tomes/demo/\n")


def write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def snapshot(build_dir, phase):
    root = Path(build_dir, "build.phase-snapshots", f"phase-{phase}")
    tid = "build" if phase <= 2 else "demo"
    plan = PLAN_HEAD + (ARC_HEADING + ARC_CONTRACT if phase == 1 else ARC)
    if phase >= 3:
        plan += "\n" + RENAME
    write(root / "plan.md", plan)
    write(root / "tome" / "tome.toml", f'[meta]\nid = "{tid}"\n')
    write(root / "tome" / "phase-marker.txt", str(phase))
    write(root / "meta.json", json.dumps({"buildId": "build", "tomeId": tid,
                                           "phase": phase}))
    if phase >= 4:
        write(root / "sidecars" / "demo.handoffs" / "s01.json", '{"ok":true}')
    if phase >= 8:
        write(root / "sidecars" / "demo.proof-evidence.json", '{"valid":true}')
        write(root / "sidecars" / "demo.learner-project" / "main.py", "print('ok')\n")


def exercise_phase(root, phase):
    build_dir, tomes_dir = Path(root, ".tome-build"), Path(root, "tomes")
    build_dir.mkdir(parents=True)
    current = tomes_dir / "demo"
    write(current / "tome.toml", '[meta]\nid = "demo"\n')
    write(current / "finished-content.txt", "must disappear")
    write(current / "save" / "state.json", '{"earned":900}')
    plan = PLAN_HEAD + ARC + "\n" + RENAME + "\n## Harness ground truth (measured from disk)\nDONE\n"
    write(build_dir / "build.plan.md", plan)
    write(build_dir / "build.result.json", '{"status":"done"}')
    write(build_dir / "demo.findings.json", '{"findings":[]}')
    write(build_dir / "demo.proof-evidence.json", '{"stale":true}')
    write(build_dir / "demo.learner-project" / "stale.py", "stale\n")
    for number in range(1, 9):
        snapshot(build_dir, number)

    phase_reset.BUILD_DIR = str(build_dir)
    phase_reset.TOMES_DIR = str(tomes_dir)
    tomes.TOMES_DIR = str(tomes_dir)
    result = phase_reset.reset_tome_to_phase("demo", phase)

    expected_tid = "build" if phase <= 2 else "demo"
    restored = tomes_dir / expected_tid
    assert result == {"id": "build", "tome": expected_tid, "phase": phase,
                      "phaseTitle": phase_reset.PHASE_TITLES[phase], "usedSnapshot": True}
    assert (restored / "phase-marker.txt").read_text() == str(phase)
    assert not (restored / "finished-content.txt").exists()
    assert (restored / "save").is_dir() and not any((restored / "save").iterdir())
    assert not (build_dir / "build.result.json").exists()
    assert not (build_dir / "demo.findings.json").exists()
    progress = json.loads((build_dir / "build.progress").read_text())
    assert progress["phase"] == phase and progress["state"] == "working"
    assert "Harness ground truth" not in (build_dir / "build.plan.md").read_text()
    assert not (build_dir / "build.phase-snapshots" / f"phase-{min(8, phase + 1)}").exists() \
        if phase < 8 else True
    if phase >= 3:
        assert "Tome id renamed by the harness" in (build_dir / "build.plan.md").read_text()
    else:
        assert "Tome id renamed by the harness" not in (build_dir / "build.plan.md").read_text()
    assert (build_dir / "demo.handoffs").exists() == (phase >= 4)
    assert (build_dir / "demo.proof-evidence.json").exists() == (phase >= 8)
    assert (build_dir / "demo.learner-project").exists() == (phase >= 8)


def exercise_legacy_fallback(root, phase):
    build_dir, tomes_dir = Path(root, ".tome-build"), Path(root, "tomes")
    build_dir.mkdir(parents=True)
    tomes_dir.mkdir(parents=True)
    phase_reset.BUILD_DIR = str(build_dir)
    phase_reset.TOMES_DIR = str(tomes_dir)
    tomes.TOMES_DIR = str(tomes_dir)
    phase_reset._fresh_tome("demo")
    current = tomes_dir / "demo"
    write(current / "sections" / "s01" / "authored-marker.txt", "section survives phase 4+")
    write(current / "intrusions.toml", "phase4 = true\n")
    write(current / "attacks_src.toml", "phase4 = true\n")
    write(current / "generated" / "attacks.toml", "phase4 = true\n")
    write(current / "themes.toml", "phase6 = true\n")
    write(current / "shop.toml", "phase6 = true\n")
    write(current / "badges.toml", "phase6 = true\n")
    write(current / "save" / "state.json", '{"earned":900}')
    manifest = (current / "tome.toml").read_text()
    manifest = manifest.replace('ranks = [[0, "NOVICE"], [400, "ADEPT"], [1000, "MASTER"]]',
                                'ranks = [[0, "CHANGED"], [9999, "FINAL"]]')
    write(current / "tome.toml", manifest)
    write(build_dir / "build.plan.md", PLAN_HEAD + ARC + "\n" + RENAME
          + "\n## Harness ground truth (measured from disk)\nDONE\n")
    write(build_dir / "build.result.json", '{"status":"done"}')
    write(build_dir / "demo.handoffs" / "s01.json", '{"ok":true}')
    write(build_dir / "demo.proof-evidence.json", '{"valid":true}')
    write(build_dir / "demo.learner-project" / "main.py", "print('ok')\n")
    write(build_dir / "demo.findings.json", '{"findings":[]}')

    result = phase_reset.reset_tome_to_phase("demo", phase)
    target_tid = "build" if phase <= 2 else "demo"
    restored = tomes_dir / target_tid
    assert not result["usedSnapshot"] and result["phase"] == phase
    assert (restored / "save").is_dir() and not any((restored / "save").iterdir())
    assert not (build_dir / "build.result.json").exists()
    assert "Harness ground truth" not in (build_dir / "build.plan.md").read_text()
    if phase == 1:
        assert ARC_CONTRACT in (build_dir / "build.plan.md").read_text()
    if phase <= 3:
        assert not (restored / "sections" / "s01" / "authored-marker.txt").exists()
    else:
        assert (restored / "sections" / "s01" / "authored-marker.txt").exists()
    assert (restored / "intrusions.toml").exists() == (phase >= 5)
    changed_economy = '9999, "FINAL"' in (restored / "tome.toml").read_text()
    assert changed_economy == (phase >= 6)
    assert (restored / "themes.toml").exists() == (phase <= 2 or phase >= 7)
    assert (build_dir / "demo.handoffs").exists() == (phase >= 4)
    assert (build_dir / "demo.proof-evidence.json").exists() == (phase >= 8)
    assert not (build_dir / "demo.findings.json").exists()
    assert (build_dir / "build.phase-snapshots" / f"phase-{phase}").is_dir()
    if phase == 3:
        with (patch.object(forge, "BUILD_DIR", str(build_dir)),
              patch.object(forge, "TOMES_DIR", str(tomes_dir)),
              patch.object(build_state, "BUILD_DIR", str(build_dir)),
              patch.object(forge, "jobs", {}),
              patch.object(forge, "_live_build_processes", return_value=[])):
            workings = forge.list_workings()
        assert [(row["id"], row["tome"], row["phase"]) for row in workings] == [
            ("build", "demo", 3)
        ]


def exercise_failed_reset_rolls_back(root):
    build_dir, tomes_dir = Path(root, ".tome-build"), Path(root, "tomes")
    build_dir.mkdir(parents=True)
    current = tomes_dir / "demo"
    write(current / "tome.toml", '[meta]\nid = "demo"\n')
    write(current / "original.txt", "keep me")
    write(current / "save" / "state.json", '{"earned":900}')
    original_plan = PLAN_HEAD + ARC + "\n" + RENAME \
        + "\n## Harness ground truth (measured from disk)\nDONE\n"
    write(build_dir / "build.plan.md", original_plan)
    write(build_dir / "build.result.json", '{"status":"done"}')
    write(build_dir / "build.progress", '{"phase":8}')
    write(build_dir / "demo.handoffs" / "s01.json", '{"ok":true}')
    write(build_dir / "build.phase-snapshots" / "phase-5" / "keep.txt", "later")
    phase_reset.BUILD_DIR = str(build_dir)
    phase_reset.TOMES_DIR = str(tomes_dir)
    tomes.TOMES_DIR = str(tomes_dir)

    with patch.object(phase_reset, "_fallback_phase_boundary",
                      side_effect=RuntimeError("injected reset failure")):
        try:
            phase_reset.reset_tome_to_phase("demo", 4)
            raise AssertionError("the injected reset failure was swallowed")
        except RuntimeError as exc:
            assert str(exc) == "injected reset failure"
    assert (current / "original.txt").read_text() == "keep me"
    assert json.loads((current / "save" / "state.json").read_text())["earned"] == 900
    assert (build_dir / "build.plan.md").read_text() == original_plan
    assert (build_dir / "build.result.json").is_file()
    assert (build_dir / "build.progress").is_file()
    assert (build_dir / "demo.handoffs" / "s01.json").is_file()
    assert (build_dir / "build.phase-snapshots" / "phase-5" / "keep.txt").is_file()


def main():
    old = phase_reset.BUILD_DIR, phase_reset.TOMES_DIR, tomes.TOMES_DIR
    try:
        for phase in range(1, 9):
            with tempfile.TemporaryDirectory() as root:
                exercise_phase(root, phase)
            with tempfile.TemporaryDirectory() as root:
                exercise_legacy_fallback(root, phase)
        with tempfile.TemporaryDirectory() as root:
            exercise_failed_reset_rolls_back(root)
    finally:
        phase_reset.BUILD_DIR, phase_reset.TOMES_DIR, tomes.TOMES_DIR = old
    print("phase reset tests: OK")


if __name__ == "__main__":
    main()
