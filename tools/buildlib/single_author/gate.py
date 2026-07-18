"""Harness-owned checkpoint validation for the persistent tome author."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import time

from .. import BUILD_DIR, REPO
from ..authoring import standard_phase_registry
from ..measure import (preflight_validator_runtime, section_source_validator_argv,
                       validate_phase3, validate_section)
from ..workflow.prompts import LEARNER_CONSTRUCTION_INSTRUCTION, read_tooling
from ..workflow.phase_reset import capture_phase_snapshot
from ..workflow.section_progress import write_section_progress
from ..continuity import continuity_prompt, prepare_handoff
from ..course.control import append_course_control
from ..course_map import CourseMapError, load_course_map, map_path
from ..course.state import (derive_course_state, record_section_failure,
                           record_section_verification)
from ..prerequisites.review import review_prerequisites
from ..mechanism_contract import candidate_with_findings
from ..course.amend import amend_course_map
from arcanum.catalog.build_ids import resolve_working_id
from tools.validatelib.phase3 import tome_section_ids

PHASE_REGISTRY = standard_phase_registry()
PHASES = tuple(definition.title for definition in PHASE_REGISTRY.definitions())


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
    tid = resolve_working_id(build_id, text, os.path.join(REPO, "tomes"))
    return {"build": build_id, "tid": tid, "plan": plan_rel,
            "tooling": read_tooling(plan)}


def current_unit(build_id, fallback_phase=1, require_gate=False):
    progress = _read(os.path.join(BUILD_DIR, f"{build_id}.progress"), {}) or {}
    phase = int(progress.get("phase") or fallback_phase)
    state = str(progress.get("state") or "working")
    if PHASE_REGISTRY.get(phase).unit_kind == "section":
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
    if PHASE_REGISTRY.get(phase).unit_kind == "section":
        section_path = os.path.join(BUILD_DIR, f"{build_id}.section-progress.json")
        section = _read(section_path, {}) or {}
        ctx = context(build_id)
        if not os.path.isfile(map_path(build_id)):
            raise ValueError("Phase 3 cannot start without a sealed complete course map")
        state = derive_course_state(build_id)
        sections = [row["id"] for row in state["sections"]]
        unfinished = next((row for row in state["sections"]
                           if row["status"] != "verified"), None)
        if unfinished and (not section.get("section")
                           or section.get("section") != unfinished["id"]
                           or section.get("state") == "complete"):
            sid = unfinished["id"]
            write_section_progress(build_id, sid, sections.index(sid) + 1,
                                   len(sections), "authoring")
        active = current_unit(build_id, phase)
        if active and active.get("section"):
            prepare_handoff(ctx["tid"], active["section"], ids=sections,
                            plan_path=os.path.join(REPO, ctx["plan"]))
    return current_unit(build_id, phase)


def label(unit):
    return (f"Phase 3 section {unit['section']} ({unit['index']}/{unit['total']})"
            if unit["kind"] == "section" else
            f"Phase {unit['phase']} — {PHASE_REGISTRY.get(unit['phase']).title}")


def validate_unit(build_id, unit):
    ctx = context(build_id)
    if unit["kind"] == "section":
        state_before = derive_course_state(build_id)
        expected = next((row["id"] for row in state_before["sections"]
                         if row["status"] != "verified"), None)
        ids = [row["id"] for row in state_before["sections"]]
        expected_index = ids.index(expected) + 1 if expected in ids else 0
        if (unit.get("section") != expected or int(unit.get("index") or 0) != expected_index
                or int(unit.get("total") or 0) != len(ids)):
            report = ("harness section marker does not match the earliest unfinished sealed-map "
                      f"unit: expected {expected or 'none'} {expected_index}/{len(ids)}")
            if expected:
                record_section_failure(build_id, expected, report)
            return False, report
        ok, report = validate_section(ctx["tid"], unit["section"], ctx["tooling"], ctx["plan"])
        if not ok:
            try:
                record_section_failure(build_id, unit["section"], report)
            except ValueError:
                pass
            return False, report
        prerequisite = review_prerequisites(build_id, unit["section"])
        if prerequisite.get("status") not in ("PASS", "not-required"):
            findings = prerequisite.get("missingMechanisms") or []
            amended = ""
            if findings:
                try:
                    candidate = candidate_with_findings(
                        load_course_map(build_id), unit["section"], findings)
                    amend_course_map(
                        build_id, candidate,
                        f"Prerequisite audit found undeclared first-use mechanisms in {unit['section']}")
                    amended = (" The harness amended the sealed mechanism ledger; repair the "
                               "new lesson introductions and demand declarations, then retry.")
                except (CourseMapError, ValueError, TypeError) as exc:
                    amended = f" Controlled amendment was rejected: {exc}"
            review_report = ("prerequisite completeness audit: "
                             f"{prerequisite.get('status')} — "
                             + "; ".join(prerequisite.get("reasons") or ["no cited evidence"])
                             + amended)
            try:
                record_section_failure(build_id, unit["section"], review_report)
            except ValueError:
                pass
            return False, "\n".join(part for part in (report, review_report) if part)
        try:
            state = record_section_verification(build_id, unit["section"], report)
        except ValueError as exc:
            record_section_failure(build_id, unit["section"], str(exc))
            return False, "\n".join(part for part in (report, str(exc)) if part)
        verified = next(row for row in state["sections"] if row["id"] == unit["section"])
        if verified["status"] != "verified":
            failure = "section evidence did not produce a harness-owned verified state"
            record_section_failure(build_id, unit["section"], failure)
            return False, "\n".join(part for part in (report, failure) if part)
        if int(unit["index"]) == int(unit["total"]) and state["activeObligations"]:
            active = ", ".join(item["id"] for item in state["activeObligations"])
            failure = "final Phase 3 gate left active obligations: " + active
            record_section_failure(build_id, unit["section"], failure)
            return False, "\n".join(part for part in (report, failure) if part)
        if int(unit["index"]) == int(unit["total"]):
            full_ok, full = validate_phase3(ctx["tid"], ctx["tooling"], ctx["plan"], ())
            report = "\n".join(part for part in (report, full) if part)
            if not full_ok:
                record_section_failure(build_id, unit["section"], full)
                return False, report
        return True, report
    definition = PHASE_REGISTRY.get(int(unit["phase"]))
    ok, report = definition.validate(build_id, ctx)
    if ok and definition.transition_command:
        transition = subprocess.run(
            ["python3", "tools/workflow/author_phase_transition.py", build_id,
             str(definition.phase)],
            cwd=REPO, capture_output=True, text=True)
        transition_report = (transition.stdout + transition.stderr).strip()
        return transition.returncode == 0, "\n".join(
            part for part in (report, transition_report) if part)
    return ok, report


def _write_phase(build_id, phase, state):
    path = os.path.join(BUILD_DIR, f"{build_id}.progress")
    prior = _read(path, {}) or {}
    started = prior.get("phaseStartedAt") if prior.get("phase") == phase else time.time()
    _write(path, {"phase": phase, "phaseTitle": PHASE_REGISTRY.get(phase).title,
                  "state": state,
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
    definition = PHASE_REGISTRY.get(int(unit["phase"]))
    _write_phase(build_id, definition.phase, "complete")
    if definition.on_exit:
        definition.on_exit(build_id, context(build_id))
    successor = PHASE_REGISTRY.next(definition.phase)
    if successor is None:
        return None
    _write_phase(build_id, successor.phase, "working")
    if successor.unit_kind == "section":
        sections = tome_section_ids(os.path.join(REPO, "tomes", context(build_id)["tid"]))
        first = sections[0] if sections else "s01"
        write_section_progress(build_id, first, 1, max(1, len(sections)), "authoring")
    _capture_phase_start(build_id, successor.phase)
    return current_unit(build_id, successor.phase)


def self_validation_commands(build_id, unit):
    """Exact bounded checks the warm author runs before the harness repeats the gate."""
    ctx = context(build_id)
    if unit["kind"] == "section":
        commands = [section_source_validator_argv(
            ctx["tid"], unit["section"], ctx["tooling"], ctx["plan"])]
    else:
        commands = PHASE_REGISTRY.get(unit["phase"]).self_checks(build_id, ctx)
    return [shlex.join(command) for command in commands]


def preflight_unit(build_id, unit):
    """Prove the unit's deterministic CLI bootstrap before invoking its author."""
    ctx = context(build_id)
    if unit["kind"] == "section":
        entrypoints = ("tools/validate_section.py",)
    else:
        entrypoints = PHASE_REGISTRY.get(unit["phase"]).preflight_entrypoints
    preflight_validator_runtime(ctx["tid"], entrypoints)


def self_validation_prompt(build_id, unit):
    commands = self_validation_commands(build_id, unit)
    rendered = "\n".join(f"`{command}`" for command in commands)
    section_note = (" The harness will repeat the complete section gate without "
                    "`--source-only`." if unit["kind"] == "section" else "")
    return (
        "Before handing off, run only the exact self-check command(s) below. Read the complete "
        "report; if a command exits nonzero, repair only this assigned unit from those findings "
        "and rerun until every command exits zero. Do not inspect validator implementation to "
        "guess at hidden checks, and do not substitute ad-hoc schema/replay/quality scripts. "
        "If it crashes before structured ERROR/WARN findings, answer once with HARNESS_BLOCKED: "
        "and the diagnostic, then stop; never spend another turn retrying repository tooling.\n"
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
    marker = ((f"python3 tools/workflow/report_section_progress.py {build_id} {unit['section']} "
               f"{unit['index']} {unit['total']} validating")
              if unit["kind"] == "section" else
              f"python3 tools/workflow/report_tome_progress.py {build_id} {unit['phase']} validating")
    construction = (f" {LEARNER_CONSTRUCTION_INSTRUCTION}" if unit["kind"] == "section" else "")
    prompt = (f"Continue with {label(unit)}. Read its phase guide, then complete exactly this unit."
              f"{construction} "
              f"{self_validation_prompt(build_id, unit)} Then run exactly `{marker}` "
              "and stop so the harness can independently validate it.")
    if unit["kind"] != "section":
        return prompt
    prompt += (
        f" Begin with exactly `python3 tools/workflow/render_section_context.py {build_id} "
        f"{unit['section']}`; that bounded packet replaces scattered initial discovery reads. "
        "After it, batch independent file reads and searches into one tool call and group related "
        "file edits into one coherent patch whenever the artifacts permit it. Do not inspect one "
        "known file per tool round trip."
    )
    if not os.path.isfile(map_path(build_id)):
        return prompt  # direct legacy/test helper; ensure_unit blocks real Phase 3 entry
    ctx = context(build_id)
    course = load_course_map(build_id)
    ids = [section["id"] for section in course["sections"]]
    prepare_handoff(ctx["tid"], unit["section"], ids=ids,
                    plan_path=os.path.join(REPO, ctx["plan"]))
    prompt += continuity_prompt(ctx["tid"], unit["section"], ids,
                                os.path.join(REPO, ctx["plan"]))
    return append_course_control(prompt, build_id, unit["section"])
