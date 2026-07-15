"""Harness-owned checkpoint validation for the persistent tome author."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import time

from . import BUILD_DIR, REPO
from .measure import (phase3_validator_argv, section_source_validator_argv, validate,
                      validate_live_smoke, validate_phase3, validate_section,
                      validate_shipping, validator_argv)
from .prompts import read_tooling
from .phase_reset import capture_phase_snapshot
from .section_progress import write_section_progress
from arcanum.tomes import resolve_working_tid
from tools.validatelib.phase3 import tome_section_ids

PHASES = ("Concept & arc", "Skeleton & voice", "Sections", "Minigames",
          "Economy", "Cosmetics", "Validate", "Student review")


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


def _write(path, value):
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(value, handle, separators=(",", ":"))
        handle.write("\n")
    os.replace(temp, path)


def context(build_id):
    plan_rel = f".tome-build/{build_id}.plan.md"
    plan = os.path.join(REPO, plan_rel)
    try:
        with open(plan, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        text = ""
    tid = resolve_working_tid(build_id, text)
    return {"build": build_id, "tid": tid, "plan": plan_rel,
            "tooling": read_tooling(plan)}


def current_unit(build_id, fallback_phase=1, require_gate=False):
    progress = _read(os.path.join(BUILD_DIR, f"{build_id}.progress"), {}) or {}
    phase = int(progress.get("phase") or fallback_phase)
    state = str(progress.get("state") or "working")
    if phase == 3:
        section = _read(os.path.join(BUILD_DIR, f"{build_id}.section-progress.json"), {}) or {}
        if section.get("section") and (not require_gate or section.get("state") in
                                       ("validating", "complete")):
            return {"kind": "section", "phase": 3, **section}
        if require_gate:
            return None
    if not require_gate or state in ("validating", "complete"):
        return {"kind": "phase", "phase": phase, "state": state}
    return None


def ensure_unit(build_id, fallback_phase=1):
    """Return a concrete unit and create missing harness-owned progress markers."""
    progress_path = os.path.join(BUILD_DIR, f"{build_id}.progress")
    progress = _read(progress_path, {}) or {}
    phase = int(progress.get("phase") or fallback_phase)
    if not progress:
        _write_phase(build_id, phase, "working")
    if phase == 3:
        section_path = os.path.join(BUILD_DIR, f"{build_id}.section-progress.json")
        section = _read(section_path, {}) or {}
        if not section.get("section"):
            ctx = context(build_id)
            sections = tome_section_ids(os.path.join(REPO, "tomes", ctx["tid"]))
            first = sections[0] if sections else "s01"
            write_section_progress(build_id, first, 1, max(1, len(sections)), "authoring")
    return current_unit(build_id, phase)


def label(unit):
    return (f"Phase 3 section {unit['section']} ({unit['index']}/{unit['total']})"
            if unit["kind"] == "section" else
            f"Phase {unit['phase']} — {PHASES[unit['phase'] - 1]}")


def validate_unit(build_id, unit):
    ctx = context(build_id)
    if unit["kind"] == "section":
        ok, report = validate_section(ctx["tid"], unit["section"], ctx["tooling"], ctx["plan"])
        if ok and int(unit["index"]) == int(unit["total"]):
            full_ok, full = validate_phase3(ctx["tid"], ctx["tooling"], ctx["plan"], ())
            return full_ok, "\n".join(part for part in (report, full) if part)
        return ok, report
    phase = int(unit["phase"])
    if phase == 1:
        ok, report = validate(build_id, phase=1, plan_rel=ctx["plan"])
    elif phase == 2:
        ok, report = validate(ctx["tid"], phase=2, tooling=ctx["tooling"], run=False,
                              plan_rel=ctx["plan"])
    elif phase == 3:
        ok, report = validate_phase3(ctx["tid"], ctx["tooling"], ctx["plan"], ())
    elif phase in (4, 5, 6):
        ok, report = validate(ctx["tid"], phase=phase, tooling=ctx["tooling"], run=False,
                              plan_rel=ctx["plan"], phase_only=True)
    else:
        ok, report = validate_shipping(ctx["tid"], ctx["tooling"], ctx["plan"])
        if ok:
            smoke_ok, smoke = validate_live_smoke(ctx["tid"])
            return smoke_ok, "\n".join(part for part in (report, smoke) if part)
    if ok and phase in (1, 2):
        transition = subprocess.run(
            ["python3", "tools/author_phase_transition.py", build_id, str(phase)],
            cwd=REPO, capture_output=True, text=True)
        transition_report = (transition.stdout + transition.stderr).strip()
        return transition.returncode == 0, "\n".join(
            part for part in (report, transition_report) if part)
    return ok, report


def _write_phase(build_id, phase, state):
    path = os.path.join(BUILD_DIR, f"{build_id}.progress")
    prior = _read(path, {}) or {}
    started = prior.get("phaseStartedAt") if prior.get("phase") == phase else time.time()
    _write(path, {"phase": phase, "phaseTitle": PHASES[phase - 1], "state": state,
                  "phaseStartedAt": started, "updatedAt": time.time()})


def _capture_phase_start(build_id, phase):
    """A missing rewind checkpoint must not block an otherwise healthy build."""
    ctx = context(build_id)
    if not os.path.isfile(os.path.join(REPO, "tomes", ctx["tid"], "tome.toml")):
        return
    try:
        capture_phase_snapshot(build_id, phase)
    except Exception as exc:
        print(f"phase snapshot warning: {exc}", flush=True)


def advance_unit(build_id, unit):
    """Checkpoint a clean unit and return the next unit, or None after Phase 8."""
    if unit["kind"] == "section":
        index, total = int(unit["index"]), int(unit["total"])
        write_section_progress(build_id, unit["section"], index, total, "complete")
        if index < total:
            sections = tome_section_ids(os.path.join(REPO, "tomes", context(build_id)["tid"]))
            next_sid = sections[index] if index < len(sections) else f"s{index + 1:02d}"
            write_section_progress(build_id, next_sid, index + 1, total, "authoring")
            return current_unit(build_id, 3)
        _write_phase(build_id, 3, "complete")
        _write_phase(build_id, 4, "working")
        _capture_phase_start(build_id, 4)
        return current_unit(build_id, 4)
    phase = int(unit["phase"])
    _write_phase(build_id, phase, "complete")
    if phase == 8:
        return None
    _write_phase(build_id, phase + 1, "working")
    if phase + 1 == 3:
        sections = tome_section_ids(os.path.join(REPO, "tomes", context(build_id)["tid"]))
        first = sections[0] if sections else "s01"
        write_section_progress(build_id, first, 1, max(1, len(sections)), "authoring")
    _capture_phase_start(build_id, phase + 1)
    return current_unit(build_id, phase + 1)


def self_validation_commands(build_id, unit):
    """Exact bounded checks the warm author runs before the harness repeats the gate."""
    ctx = context(build_id)
    if unit["kind"] == "section":
        commands = [section_source_validator_argv(
            ctx["tid"], unit["section"], ctx["tooling"], ctx["plan"])]
    else:
        phase = int(unit["phase"])
        if phase == 1:
            commands = [validator_argv(ctx["tid"], phase=1, plan_rel=ctx["plan"])]
        elif phase == 2:
            commands = [validator_argv(
                ctx["tid"], phase=2, tooling=ctx["tooling"], run=False,
                plan_rel=ctx["plan"])]
        elif phase == 3:
            commands = [phase3_validator_argv(
                ctx["tid"], ctx["tooling"], ctx["plan"], run=True)]
        elif phase in (4, 5, 6):
            commands = [validator_argv(
                ctx["tid"], phase=phase, tooling=ctx["tooling"], run=False,
                plan_rel=ctx["plan"], phase_only=True)]
        else:
            commands = [
                phase3_validator_argv(
                    ctx["tid"], ctx["tooling"], ctx["plan"], run=True, strict=True),
                ["python3", "tools/smoke_tome.py", ctx["tid"]],
            ]
    return [shlex.join(command) for command in commands]


def self_validation_prompt(build_id, unit):
    commands = self_validation_commands(build_id, unit)
    rendered = "\n".join(f"`{command}`" for command in commands)
    section_note = (" The harness will repeat the complete section gate without "
                    "`--source-only`." if unit["kind"] == "section" else "")
    return (
        "Before handing off, run only the exact self-check command(s) below. Read the complete "
        "report; if a command exits nonzero, repair only this assigned unit from those findings "
        "and rerun until every command exits zero. Do not inspect validator implementation to "
        "guess at hidden checks, and do not substitute ad-hoc schema/replay/quality scripts.\n"
        f"{rendered}\nThe harness independently reruns the authoritative gate after you stop."
        f"{section_note}"
    )


def next_prompt(build_id, passed, next_unit, report):
    summary = str(report or "clean").strip()[-1600:]
    return (f"HARNESS VALIDATION PASSED for {label(passed)}.\n{summary}\n\n"
            + unit_prompt(build_id, next_unit))


def repair_prompt(build_id, unit, report):
    cumulative = ((unit["kind"] == "section"
                   and int(unit.get("index") or 0) == int(unit.get("total") or -1))
                  or (unit["kind"] == "phase" and int(unit["phase"]) >= 7))
    scope = ("Repair the exact reported findings wherever they occur in the cumulative tome"
             if cumulative else "Repair only this unit")
    return (f"HARNESS VALIDATION FAILED for {label(unit)}. {scope} in the same "
            "session. Preserve clean work. After the repair, rerun the assigned exact "
            "self-check until it exits zero; do not replace it with manual validator imitation.\n\n"
            f"{str(report or 'validator failed')[-12000:]}\n\n{unit_prompt(build_id, unit)}")


def unit_prompt(build_id, unit):
    marker = ("tools/report_section_progress.py BUILD_ID SECTION INDEX TOTAL validating"
              if unit["kind"] == "section" else
              f"tools/report_tome_progress.py BUILD_ID {unit['phase']} validating")
    return (f"Continue with {label(unit)}. Read its phase guide, then complete exactly this unit. "
            f"{self_validation_prompt(build_id, unit)} Then run `{marker}` with the real values "
            "and stop so the harness can independently validate it.")
