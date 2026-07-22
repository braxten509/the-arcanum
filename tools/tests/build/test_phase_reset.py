#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""Regression coverage for Binder phase rewinds and phase-start snapshots."""
import copy
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = str(_BOOTSTRAP_REPO)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from arcanum import forge
from arcanum.catalog import ManifestRepository, TomeCatalogService, TomePaths
from arcanum.forge import build_state
from arcanum.settings import Settings
from runtimes import RuntimeRegistry
from tools.buildlib import continuity, course_map
from tools.buildlib.ai_costs import record_ai_turn, turns_path
from tools.buildlib.course import control as course_control
from tools.buildlib.course import state as course_state
from tools.buildlib.prerequisites import review as prerequisite_review
from tools.buildlib.status_log import append_status_line, load_status_lines
from tools.buildlib.workflow import phase_reset
from tools.buildlib.workflow.checkpoints import ARC_CONTRACT, ARC_HEADING


PLAN_HEAD = """# Build plan: build

## Concept
Teach a thing

## Gate answers
- **Tooling:** internal

"""
ARC = """## Arc (Phase 1 fills this in, later phases read it)
**Finished tool:** Finished
**Graduate ledger:** The learner can build and verify the complete two-stage tool.
**Mastery proof:** The final Working integrates both capabilities without implementation help.
**Acceptance scenarios:** starts-clean -> finishes-clean
**Continuity map:**
s01 -> s02: preserve the first capability through final delivery
**Artifact lifecycle:** s01's temporary fixture is replaced in s02
**Section list:**
1. **s01 — First:** first promise
2. **s02 — Final:** final integration promise
"""
RENAME = ("- **Tome id renamed by the harness:** `build` → `demo` "
          "(kebab-case of project 'Demo'); all later phases use tomes/demo/\n")


def write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def configure_modules(root, build_dir):
    for module in (course_map, course_state, continuity, prerequisite_review, course_control):
        module.BUILD_DIR, module.REPO = str(build_dir), str(root)


def detailed_map(seed):
    value = copy.deepcopy(seed)
    value["graduateCapabilities"] = ["first-capability", "final-capability"]
    cumulative = []
    for number, section in enumerate(value["sections"], 1):
        sid = section["id"]
        capability = value["graduateCapabilities"][number - 1]
        capabilities = [capability, f"{capability}-practice", f"{capability}-proof"]
        cumulative.extend(capabilities)
        section["capabilities"] = capabilities
        section["dependsOn"] = [] if number == 1 else ["s01"]
        lessons = [{"id": f"{sid}.l{index:02d}", "kind": "lesson",
                    "title": f"Lesson {number}.{index}", "teaches": [owned],
                    "introduces": [],
                    "dependsOn": [] if index == 1 else [f"{sid}.l{index - 1:02d}"],
                    "validationDependencies": [],
                    "doneWhen": {"checks": ["lesson-source", "learner-construction"]}}
                   for index, owned in enumerate(capabilities, 1)]
        working = {"id": f"{sid}.working", "kind": "working", "title": f"Working {number}",
                   "requires": list(cumulative), "dependsOn": [lessons[-1]["id"]],
                   "mechanisms": [],
                   "validationDependencies": [],
                   "projectMilestone": section["projectMilestone"],
                   "learnerOwnedArtifacts": [f"src/{sid}.txt"],
                   "doneWhen": {"checks": ["working-replay", "learner-construction"]}}
        section["nodes"] = [*lessons, working]
    for obligation in value["plannedObligations"]:
        obligation.update({"owner": "first capability", "location": "lessons/l01.toml",
                           "reason": "The final integration must preserve this contract.",
                           "doneWhen": {"evidenceLocations": ["lessons/l01.toml"],
                                        "capabilityIds": ["final-capability"],
                                        "proofIds": ["s02"],
                                        "acceptanceIds": ["finishes-clean"],
                                        "observedResult": "The final evidence preserves it."}})
    return value


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


def seed_cost_history(build_dir):
    for phase in range(1, 9):
        record_ai_turn(
            str(build_dir), "build", phase=phase,
            **({"section": "s01"} if phase == 3 else {}),
            role="author", stage=f"phase-{phase}", kind="codex-cli",
            model="gpt-5.6-luna", transport="cli",
            session_id=f"phase-{phase}", usage_mode="cumulative",
            usage={"inputTokens": phase * 100, "outputTokens": phase * 10},
            ended_at=1000 + phase)
        append_status_line(
            "build", f"AI API-EQUIVALENT COST COMPLETE [{1000 + phase}.000] › "
            f"PHASE {phase} TOTAL › ${phase}.00", build_dir=str(build_dir),
            at=1000 + phase)
        append_status_line(
            "build", f"AI VALIDATOR CALL COMPLETE [{1000 + phase}.500] (PASS) › "
            f"section quality s0{phase} › codex-cli luna", build_dir=str(build_dir),
            at=1000.5 + phase)


def assert_cost_boundary(build_dir, phase):
    with open(turns_path(str(build_dir), "build"), encoding="utf-8") as handle:
        retained = [json.loads(line) for line in handle if line.strip()]
    assert [row["phase"] for row in retained] == list(range(1, phase))
    lines = load_status_lines("build", build_dir=str(build_dir))
    cost_lines = [line for line in lines if line.startswith("AI API-EQUIVALENT COST")]
    assert [int(line.split("PHASE ", 1)[1].split()[0]) for line in cost_lines] \
        == list(range(1, phase))
    assert not [line for line in lines
                if line.startswith(("VALIDATOR COMMAND", "AI VALIDATOR CALL"))]


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
    for review_phase in (1, 2):
        write(build_dir / "build.phase-ai-reviews" / f"phase-{review_phase}.json",
              json.dumps({"phase": review_phase}))
    write(build_dir / "build.prerequisite-reviews" / "s01.json", '{"status":"FAIL"}')
    write(build_dir / "build.prerequisite-review.calls.jsonl", "".join(
        json.dumps({"phase": call_phase,
                    "section": "s01" if call_phase == 3 else None}) + "\n"
        for call_phase in (1, 2, 3)))
    archive = Path(root, "validator-failures", "build")
    for unit in ("phase-1", "phase-2", "s01"):
        write(archive / f"time__{unit}__failure.json", "{}")
    write(build_dir / "build.author-usage.jsonl", "{}\n")
    write(build_dir / "build.conversation.jsonl.bak", "{}\n")
    write(build_dir / "build.reset-stash" / "old" / "s01" / "section.toml", "old")
    for number in range(1, 9):
        snapshot(build_dir, number)

    phase_reset.BUILD_DIR = str(build_dir)
    phase_reset.TOMES_DIR = str(tomes_dir)
    configure_modules(root, build_dir)
    seed_cost_history(build_dir)
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
    assert_cost_boundary(build_dir, phase)
    assert not (build_dir / "build.author-usage.jsonl").exists()
    assert not (build_dir / "build.conversation.jsonl.bak").exists()
    assert not (build_dir / "build.reset-stash").exists()
    retained_reviews = sorted(path.stem for path in
                              (build_dir / "build.phase-ai-reviews").glob("*.json"))
    assert retained_reviews == [f"phase-{number}" for number in (1, 2)
                                if number < phase]
    calls = []
    try:
        calls = [json.loads(line)["phase"] for line in
                 (build_dir / "build.prerequisite-review.calls.jsonl").read_text().splitlines()]
    except FileNotFoundError:
        pass
    assert calls == [number for number in (1, 2, 3) if number < phase]
    retained_archives = sorted(path.name for path in archive.glob("*"))
    expected_archives = [f"time__phase-{number}__failure.json"
                         for number in (1, 2) if number < phase]
    if phase > 3:
        expected_archives.append("time__s01__failure.json")
    assert retained_archives == sorted(expected_archives)


def exercise_legacy_fallback(root, phase):
    build_dir, tomes_dir = Path(root, ".tome-build"), Path(root, "tomes")
    build_dir.mkdir(parents=True)
    tomes_dir.mkdir(parents=True)
    phase_reset.BUILD_DIR = str(build_dir)
    phase_reset.TOMES_DIR = str(tomes_dir)
    configure_modules(root, build_dir)
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
    seed_cost_history(build_dir)

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
    assert_cost_boundary(build_dir, phase)
    assert (build_dir / "build.phase-snapshots" / f"phase-{phase}").is_dir()
    if phase == 3:
        with (patch.object(forge, "BUILD_DIR", str(build_dir)),
              patch.object(build_state, "BUILD_DIR", str(build_dir)),
              patch.object(forge, "_live_build_processes", return_value=[])):
            from arcanum.jobs import JobManager
            settings = Settings(str(root), str(Path(root, "web")), str(tomes_dir),
                                str(Path(root, "cache")), str(build_dir),
                                str(Path(root, "skins")),
                                str(Path(root, "settings.toml")), 8777)
            paths = TomePaths(settings)
            catalog = TomeCatalogService(paths, ManifestRepository(paths),
                                         RuntimeRegistry.from_root(root))
            workings = forge.list_workings(JobManager(), catalog)
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
    configure_modules(root, build_dir)
    seed_cost_history(build_dir)
    original_costs = {suffix: (build_dir / f"build.{suffix}").read_bytes()
                      for suffix in phase_reset.COST_SIDECARS}

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
    assert {suffix: (build_dir / f"build.{suffix}").read_bytes()
            for suffix in phase_reset.COST_SIDECARS} == original_costs


def exercise_course_sidecar_snapshot(root):
    build_dir, tomes_dir = Path(root, ".tome-build"), Path(root, "tomes")
    build_dir.mkdir(parents=True)
    phase_reset.BUILD_DIR, phase_reset.TOMES_DIR = str(build_dir), str(tomes_dir)
    configure_modules(root, build_dir)
    phase_reset._fresh_tome("demo")
    plan = build_dir / "demo.plan.md"
    write(plan, PLAN_HEAD + ARC)
    seed = course_map.seed_course_map("demo", str(plan))
    write(course_map.proposal_path("demo"), json.dumps(detailed_map(seed)))
    sealed = course_map.seal_course_map("demo")
    write(build_dir / "demo.launch.json", json.dumps({
        "gate": {"prior_level": "5"},
        "validator": {"kind": "codex-cli", "model": "validator"},
    }))
    write(build_dir / "demo.handoffs" / "s01.json", '{"snapshot":"kept"}')
    original_state = course_state.derive_course_state("demo")
    assert phase_reset.capture_phase_snapshot("demo", 4)
    sidecars = build_dir / "demo.phase-snapshots" / "phase-4" / "sidecars"
    for name in ("demo.course-map.seed.json", "demo.course-map.proposal.json",
                 "demo.course-map.json", "demo.course-state.json", "demo.handoffs"):
        assert (sidecars / name).exists(), name
    write(course_map.map_path("demo"), '{"tampered":true}')
    write(course_state.state_path("demo"), '{"complete":true}')
    write(build_dir / "demo.handoffs" / "s01.json", '{"snapshot":"tampered"}')
    result = phase_reset.reset_tome_to_phase("demo", 4)
    assert result["usedSnapshot"] and result["phase"] == 4
    assert course_map.load_course_map("demo")["digest"] == sealed["digest"]
    rebuilt = json.loads(Path(course_state.state_path("demo")).read_text())
    assert rebuilt["sourceDigest"] == original_state["sourceDigest"]
    assert json.loads((build_dir / "demo.handoffs" / "s01.json").read_text()) == {
        "snapshot": "kept"}


def exercise_section_rewind(root):
    build_dir, tomes_dir = Path(root, ".tome-build"), Path(root, "tomes")
    build_dir.mkdir(parents=True)
    phase_reset.BUILD_DIR, phase_reset.TOMES_DIR = str(build_dir), str(tomes_dir)
    configure_modules(root, build_dir)
    phase_reset._fresh_tome("demo")
    plan = build_dir / "demo.plan.md"
    write(plan, PLAN_HEAD + ARC)
    seed = course_map.seed_course_map("demo", str(plan))
    write(course_map.proposal_path("demo"), json.dumps(detailed_map(seed)))
    course_map.seal_course_map("demo")
    write(build_dir / "demo.launch.json", json.dumps({
        "gate": {"prior_level": "5"},
        "validator": {"kind": "codex-cli", "model": "validator"},
    }))
    for sid in ("s01", "s02"):
        write(build_dir / "demo.handoffs" / f"{sid}.json", '{"version":3}')
        write(course_state.receipt_path("demo", sid), '{"version":1}')
        write(course_state.failure_path("demo", sid), '{"report":"stale"}')
    write(build_dir / "demo.conversation.jsonl", '{"role":"harness"}\n')
    write(build_dir / "demo.section-progress.json", '{"section":"s02"}')
    write(build_dir / "demo.result.json", '{"status":"done"}')
    write(build_dir / "demo.author-usage.jsonl", "{}\n")
    write(build_dir / "demo.conversation.jsonl.bak", "{}\n")
    write(build_dir / "demo.reset-stash" / "old" / "s02" / "section.toml", "OLD")
    write(build_dir / "demo.prerequisite-review.calls.jsonl", "".join((
        json.dumps({"phase": 3, "unit": "s01", "section": "s01"}) + "\n",
        json.dumps({"phase": 3, "unit": "s02", "section": "s02"}) + "\n",
    )))
    archive = Path(root, "validator-failures", "demo")
    write(archive / "time__s01__failure.json", "{}")
    write(archive / "time__s02__failure.json", "{}")
    for section, ended in (("s01", 800), ("s02", 810)):
        record_ai_turn(
            str(build_dir), "demo", phase=3, section=section,
            role="author", stage="section", kind="codex-cli", model="gpt-5.6-luna",
            transport="cli", session_id=section, usage_mode="turn",
            usage={"inputTokens": 100, "outputTokens": 10}, ended_at=ended)
    append_status_line("demo", "AI VALIDATOR CALL COMPLETE [900.000] (FAIL) › "
                       "section quality s02 › claude-cli haiku",
                       build_dir=str(build_dir), at=900)
    append_status_line("demo", "AI API-EQUIVALENT COST COMPLETE [901.000] › "
                       "PHASE 2 TOTAL › $7.80", build_dir=str(build_dir), at=901)

    sections_dir = Path(phase_reset.TOMES_DIR) / "demo" / "sections"
    authored = sections_dir / "s02" / "section.toml"
    write(authored, 'id = "s02"\ncodename = "AUTHORED"\ntitle = "authored prose"\n')

    result = phase_reset.reset_tome_to_section("demo", "s02")

    # The authored tree comes back as its own Phase-2 scaffold, while the abandoned
    # attempt is deleted after the rollback-safe reset transaction succeeds.
    assert "AUTHORED" not in authored.read_text()
    assert phase_reset.is_scaffold(str(sections_dir / "s02")), "s02 was not rebuilt"
    assert not (build_dir / "demo.reset-stash").exists()

    # Restarting a section that is already an untouched scaffold has nothing to rewind, so
    # it must not stash or rewrite anything a second time.
    scaffold_before = authored.read_text()
    phase_reset.reset_tome_to_section("demo", "s02")
    assert authored.read_text() == scaffold_before, "a scaffold must survive untouched"
    assert not (build_dir / "demo.reset-stash").exists()

    assert result == {"id": "demo", "tome": "demo", "phase": 3, "section": "s02",
                      "phaseTitle": phase_reset.PHASE_TITLES[3], "usedSnapshot": False}
    for name in (build_dir / "demo.handoffs" / "s01.json",
                 Path(course_state.receipt_path("demo", "s01")),
                 Path(course_state.failure_path("demo", "s01"))):
        assert name.exists(), name
    for name in (build_dir / "demo.handoffs" / "s02.json",
                 Path(course_state.receipt_path("demo", "s02")),
                 Path(course_state.failure_path("demo", "s02")),
                 build_dir / "demo.conversation.jsonl",
                 build_dir / "demo.section-progress.json",
                 build_dir / "demo.result.json"):
        assert not name.exists(), name
    progress = json.loads((build_dir / "demo.progress").read_text())
    assert progress["phase"] == 3 and progress["state"] == "working"
    assert json.loads(Path(course_state.state_path("demo")).read_text())["sections"][1][
        "status"] != "verified"
    # The tool history the operator sees is rebuilt from here; the cost ledger is not.
    assert load_status_lines("demo", build_dir=str(build_dir)) == [
        "AI API-EQUIVALENT COST COMPLETE [901.000] › PHASE 2 TOTAL › $7.80"]
    assert not (build_dir / "demo.author-usage.jsonl").exists()
    assert not (build_dir / "demo.conversation.jsonl.bak").exists()
    assert [json.loads(line)["section"] for line in
            (build_dir / "demo.prerequisite-review.calls.jsonl").read_text().splitlines()] \
        == ["s01"]
    assert sorted(path.name for path in archive.glob("*")) == ["time__s01__failure.json"]
    with open(turns_path(str(build_dir), "demo"), encoding="utf-8") as handle:
        assert [json.loads(line)["section"] for line in handle if line.strip()] == ["s01"]
    for bad in ("s03", "nope", ""):
        try:
            phase_reset.reset_tome_to_section("demo", bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted invalid section {bad!r}")


def exercise_phase1_refreshes_machine_contract():
    gate = """## Gate answers (Phase 0)
- **Prior knowledge:** Very basic Python syntax
- **Starting level (1-10):** 2
- **Breadth (1-10):** 7
- **Lesson depth (1-10):** 8
- **Mastery (1-5):** 3
- **Tooling:** external

## Calibration contract
- **Language foundation contract:** 1
- **Language-foundation rule:** stale five-role snapshot

"""
    reset = phase_reset.reset_plan_text(PLAN_HEAD + gate + ARC, 1)
    assert "**Language foundation contract:** 2" in reset
    assert "**Project scope 4/5" in reset
    assert "**Lesson pacing 2/3 — MODERATE DENSITY:**" in reset
    assert "**Pacing/depth separation:**" in reset
    assert "**Prerequisite topology rule:**" in reset
    assert "**Transitive prerequisite closure rule:**" in reset
    assert "**Observable-interaction closure rule:**" in reset
    assert "**Capability honesty rule:**" in reset
    assert "**Foundation cadence rule:**" in reset
    assert "**Verification cadence rule:**" in reset
    assert "**Milestone coherence rule:**" in reset
    assert "**Curriculum capacity rule:**" in reset
    assert "**Transfer distribution rule:**" in reset
    assert "no leading, trailing, or doubled slash" in reset
    assert "Python requires classes" not in reset
    assert "stale five-role snapshot" not in reset


def main():
    modules = (course_map, course_state, continuity, prerequisite_review, course_control)
    old = (phase_reset.BUILD_DIR, phase_reset.TOMES_DIR,
           [(module, module.BUILD_DIR, module.REPO) for module in modules])
    try:
        for phase in range(1, 9):
            with tempfile.TemporaryDirectory() as root:
                exercise_phase(root, phase)
            with tempfile.TemporaryDirectory() as root:
                exercise_legacy_fallback(root, phase)
        with tempfile.TemporaryDirectory() as root:
            exercise_failed_reset_rolls_back(root)
        with tempfile.TemporaryDirectory() as root:
            exercise_course_sidecar_snapshot(root)
        with tempfile.TemporaryDirectory() as root:
            exercise_section_rewind(root)
        exercise_phase1_refreshes_machine_contract()
    finally:
        phase_reset.BUILD_DIR, phase_reset.TOMES_DIR = old[:2]
        for module, build_dir, repo in old[2]:
            module.BUILD_DIR, module.REPO = build_dir, repo
    print("phase reset tests: OK")


if __name__ == "__main__":
    main()
