"""Harness-owned checkpoint validation for the persistent tome author."""
from __future__ import annotations

import json
import os
import subprocess
import time

from . import BUILD_DIR, REPO
from .measure import (validate, validate_live_smoke, validate_phase3, validate_section,
                      validate_shipping)
from .prompts import read_tooling
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
    return current_unit(build_id, phase + 1)


def next_prompt(passed, next_unit, report):
    summary = str(report or "clean").strip()[-1600:]
    return (f"HARNESS VALIDATION PASSED for {label(passed)}.\n{summary}\n\n"
            + unit_prompt(next_unit))


def repair_prompt(unit, report):
    cumulative = ((unit["kind"] == "section"
                   and int(unit.get("index") or 0) == int(unit.get("total") or -1))
                  or (unit["kind"] == "phase" and int(unit["phase"]) >= 7))
    scope = ("Repair the exact reported findings wherever they occur in the cumulative tome"
             if cumulative else "Repair only this unit")
    return (f"HARNESS VALIDATION FAILED for {label(unit)}. {scope} in the same "
            "session. Preserve clean work and do not run the validator yourself.\n\n"
            f"{str(report or 'validator failed')[-12000:]}\n\n{unit_prompt(unit)}")


def unit_prompt(unit):
    marker = ("tools/report_section_progress.py BUILD_ID SECTION INDEX TOTAL validating"
              if unit["kind"] == "section" else
              f"tools/report_tome_progress.py BUILD_ID {unit['phase']} validating")
    return (f"Continue with {label(unit)}. Read its phase guide, then complete exactly this unit. "
            f"Do not run its validator. End by running `{marker}` with the real values, then stop "
            "so the harness can validate it.")
