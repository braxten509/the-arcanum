"""Harness-owned checkpoint validation for the persistent tome author."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import time

from .. import BUILD_DIR, REPO
from ..ai_costs import completed_cost_line
from ..authoring import standard_phase_registry
from ..measure import (preflight_validator_runtime, run_harness_command,
                       section_source_validator_argv, validate_phase3,
                       validate_section)
from ..workflow.prompts import LEARNER_CONSTRUCTION_INSTRUCTION, read_tooling
from ..workflow.phase_reset import capture_phase_snapshot
from ..workflow.section_progress import write_section_progress
from ..continuity import continuity_prompt, prepare_handoff
from ..course.control import append_course_control
from ..course_map import CourseMapError, load_course_map, map_path
from ..course_map.author_spec import initialize_author_spec, spec_root
from ..phase2_research import initialize_ledger, ledger_path
from ..course.state import (derive_course_state, record_section_failure,
                           record_section_verification)
from ..prerequisites.review import review_prerequisites
from ..planning_review import (review_planning_phase,
                               review_report as planning_review_report)
from ..status_log import emit_status_line
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
            quality_findings = prerequisite.get("qualityFindings") or []
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
            quality_repairs = "; ".join(
                f"{item.get('node', '?')} [{item.get('category', 'quality')}]: "
                f"{item.get('requiredRepair', 'repair the cited defect')}"
                for item in quality_findings if isinstance(item, dict))
            helpful_repairs = "; ".join(
                item.strip() for item in prerequisite.get("guidance") or []
                if isinstance(item, str) and item.strip())
            review_report = ("section teaching-quality and prerequisite audit: "
                             f"{prerequisite.get('status')} — "
                             + "; ".join(prerequisite.get("reasons") or ["no cited evidence"])
                             + (f" Repairs: {quality_repairs}." if quality_repairs else "")
                             + (f" Helpful findings: {helpful_repairs}."
                                if helpful_repairs else "")
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
    phase = int(unit["phase"])
    definition = PHASE_REGISTRY.get(phase)
    ok, report = definition.validate(build_id, ctx)
    if ok and phase in (1, 2):
        planning = review_planning_phase(build_id, phase, ctx["tid"])
        ai_report = planning_review_report(phase, planning)
        report = "\n".join(part for part in (report, ai_report) if part)
        if planning.get("status") != "PASS":
            return False, report
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


def report_completed_unit_cost(build_id, unit):
    """Publish Claude/GPT API-equivalent cost at one harness-sealed boundary."""
    scopes = [(int(unit["phase"]), unit.get("section"))]
    if (unit.get("kind") == "section"
            and int(unit.get("index") or 0) == int(unit.get("total") or -1)):
        scopes.append((3, None))
    lines = []
    for phase, section in scopes:
        line = completed_cost_line(
            BUILD_DIR, build_id, phase=phase, section=section)
        if line:
            emit_status_line(line, build_id, build_dir=BUILD_DIR)
            lines.append(line)
    return lines


def self_validation_argvs(build_id, unit):
    """Exact bounded checks the warm author runs before the harness repeats the gate."""
    ctx = context(build_id)
    if unit["kind"] == "section":
        commands = [section_source_validator_argv(
            ctx["tid"], unit["section"], ctx["tooling"], ctx["plan"])]
    else:
        commands = PHASE_REGISTRY.get(unit["phase"]).self_checks(build_id, ctx)
    return [list(command) for command in commands]


def self_validation_commands(build_id, unit):
    return [shlex.join(command) for command in self_validation_argvs(build_id, unit)]


def validate_author_self_check(build_id, unit):
    """Independently reproduce a claimed blocked self-check without an AI turn."""
    ctx = context(build_id)
    reports = []
    for command in self_validation_argvs(build_id, unit):
        process = run_harness_command(command, ctx["tid"])
        report = ((process.stdout or "") + (process.stderr or "")).strip()
        if report:
            reports.append(report)
        if process.returncode != 0:
            return False, "\n".join(reports)
    return True, "\n".join(reports)


def mark_unit_validating(build_id, unit):
    """Trusted marker used only after a clean independently reproduced self-check."""
    if unit["kind"] == "section":
        write_section_progress(
            build_id, unit["section"], int(unit["index"]), int(unit["total"]),
            "validating")
    else:
        _write_phase(build_id, int(unit["phase"]), "validating")
    return current_unit(build_id, int(unit["phase"]), require_gate=True)


def preflight_unit(build_id, unit):
    """Prove the unit's deterministic CLI bootstrap before invoking its author."""
    ctx = context(build_id)
    if unit["kind"] == "section":
        entrypoints = ("tools/validate_section.py",)
    else:
        entrypoints = PHASE_REGISTRY.get(unit["phase"]).preflight_entrypoints
        if int(unit["phase"]) == 2:
            if not os.path.isdir(spec_root(build_id)):
                initialize_author_spec(build_id)
            if not os.path.isfile(ledger_path(build_id)):
                initialize_ledger(build_id, ctx["tooling"])
    preflight_validator_runtime(ctx["tid"], entrypoints)


def self_validation_prompt(build_id, unit):
    commands = self_validation_commands(build_id, unit)
    rendered = "\n".join(f"`{command}`" for command in commands)
    section_note = (" The harness will repeat the complete section gate without "
                    "`--source-only`." if unit["kind"] == "section" else "")
    return (
        "Before handing off, run only the exact self-check command(s) below. Read the complete "
        "report. Run each command at most once in this turn. If a command exits nonzero with "
        "structured ERROR/WARN findings, do not repair or rerun it in this turn; answer once with "
        "HARNESS_REPAIR_REQUIRED: plus a one-line summary, then stop. The harness will reproduce "
        "the check and return one complete bounded repair packet. Do not inspect validator implementation to "
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
    marker = ((f"python3 tools/workflow/report_section_progress.py {build_id} {unit['section']} "
               f"{unit['index']} {unit['total']} validating")
              if unit["kind"] == "section" else
              f"python3 tools/workflow/report_tome_progress.py {build_id} {unit['phase']} validating")
    return (f"HARNESS VALIDATION FAILED for {label(unit)}. {scope} in the same "
            "session. Preserve clean work. Treat the report below as the complete repair packet: "
            "do not rerender the section context, repeat initial discovery, or broaden the edit. "
            "Read only cited files/ranges needed for the findings and batch all related fixes into one "
            "coherent patch. After the repair, run the assigned exact self-check once; do not replace "
            "it with manual validator imitation or serialize one finding per turn.\n\n"
            f"{str(report or 'validator failed')[-12000:]}\n\n"
            f"{self_validation_prompt(build_id, unit)} Then run exactly `{marker}` and stop so "
            "the harness can independently validate the repair.")


# A full section plus hidden replay is too large for one upstream generation, while one
# lesson per turn repeatedly charges the same warm context. The stable boundary is all
# lessons in one batch, followed by one Working/assessment/handoff turn.
LESSON_BATCH_INSTRUCTION = (
    "Use TWO COHERENT AUTHORING BATCHES for this section. In the first turn, research the "
    "section's external facts, then author EVERY sealed planned lesson completely in one batch. "
    "Stop after all lesson files without authoring the Working, assessment, handoff, self-check, "
    "or progress marker. The harness returns you to this same session once, retaining the bounded "
    "context. In the second turn, author the Working, assessment, and handoff together, then use "
    "the self-check and marker instructions below.")


def continue_prompt(build_id, unit):
    """Return the author to the same unit after it stopped without a handoff.

    For a section this is the expected two-batch boundary rather than a stall, so it must
    not re-send unit_prompt, whose section branch
    re-runs render_section_context and the continuity packet the author already has. A
    genuine stall is caught by the no-progress fingerprint in single_author.run(), which
    compares author-writable state across turns, so this prompt never has to police it.
    """
    if unit["kind"] != "section":
        return (f"You stopped before handing off {label(unit)}. Finish only that unit, "
                "run its assigned exact self-check, set its progress marker to "
                "validating, and stop.\n\n" + unit_prompt(build_id, unit))
    marker = (f"python3 tools/workflow/report_section_progress.py {build_id} {unit['section']} "
              f"{unit['index']} {unit['total']} validating")
    return (f"Continuing {label(unit)} in the same bounded session. Do not rerender the "
            "section context, reread the phase guide, or repeat discovery. Verify that every "
            "sealed planned lesson is complete. If an interrupted first batch left any lesson "
            "incomplete, finish ALL remaining lessons together and stop again before the Working. "
            "Otherwise author the Working, assessment, and handoff together, then "
            f"{self_validation_prompt(build_id, unit)} Then run exactly `{marker}` and stop "
            "so the harness can independently validate the complete section.")


def unit_prompt(build_id, unit):
    marker = ((f"python3 tools/workflow/report_section_progress.py {build_id} {unit['section']} "
               f"{unit['index']} {unit['total']} validating")
              if unit["kind"] == "section" else
              f"python3 tools/workflow/report_tome_progress.py {build_id} {unit['phase']} validating")
    construction = (f" {LEARNER_CONSTRUCTION_INSTRUCTION}" if unit["kind"] == "section" else "")
    rhythm = (f" {LESSON_BATCH_INSTRUCTION}" if unit["kind"] == "section" else "")
    prompt = (f"Continue with {label(unit)}. Read its phase guide, then complete exactly this unit."
              f"{construction}{rhythm} "
              f"{self_validation_prompt(build_id, unit)} Then run exactly `{marker}` "
              "and stop so the harness can independently validate it.")
    if unit["kind"] != "section":
        if int(unit.get("phase") or 0) == 2:
            prompt += (
                f" Begin with exactly `python3 tools/workflow/context/render_phase2_context.py {build_id}`. "
                "That bounded packet replaces broad repository discovery. Edit only the compact "
                "Phase-2 author files it names; the exact self-check deterministically materializes "
                "the full proposal. Complete every section plan in one coherent batch. If external "
                "tooling is selected, use web search only for facts that affect installation, current "
                "commands, APIs, compatibility, or delivery; cite no more than six official or primary "
                "sources in the research ledger. Later authors reuse that ledger. Target no more than "
                "$2 API-equivalent for initial Phase 2 planning; avoid rereading generated proposal JSON."
            )
        return prompt
    prompt += (
        f" Begin with exactly `python3 tools/workflow/context/render_section_context.py {build_id} "
        f"{unit['section']}`; that bounded packet replaces scattered initial discovery reads. "
        "After it, batch independent file reads and searches into one tool call and group related "
        "file edits into one coherent patch whenever the artifacts permit it. Do not inspect one "
        "known file per tool round trip. The operating target for the Phase 3 author plus its "
        "mandatory Validator AI is $1–2 API-equivalent per section for Codex authors; Claude "
        "authors may use up to $4. Meet the complete quality "
        "contract within that target by using this bounded packet once and avoiding redundant "
        "discovery or speculative rewrites."
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
