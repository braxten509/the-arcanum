"""Harness-owned checkpoint validation for the persistent tome author."""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import time

from .. import BUILD_DIR, REPO
from ..ai_costs import completed_cost_line
from ..authoring import standard_phase_registry
from ..measure import (preflight_validator_runtime, run_harness_command,
                       phase3_validator_argv, section_validator_argv, validate_phase3,
                       validate_section)
from ..workflow.prompts import LEARNER_CONSTRUCTION_INSTRUCTION, read_tooling
from ..workflow.phase_reset import capture_phase_snapshot
from ..workflow.section_progress import write_section_progress
from ..continuity import continuity_prompt, prepare_handoff
from ..course.control import append_course_control
from ..course_map import load_course_map, map_path, seed_path
from ..course_map.author_spec import initialize_author_spec, spec_root
from ..phase2_audit import audit_path, initialize_audit
from ..phase2.research import initialize_ledger, ledger_path
from ..section_quality_contract import (section_quality_authority,
                                        section_quality_settings)
from ..course.state import (derive_course_state, record_section_failure,
                           record_section_verification)
from .section_review import review_section
from .prompts.continuation import (LESSON_BATCH_INSTRUCTION,
                                   continue_prompt as render_continue_prompt)
from .validation_messages import (
    validation_failure_message as render_validation_failure_message)
from ..planning_review import (planning_authority, planning_dynamic_authority,
                               review_planning_phase,
                               review_report as planning_review_report)
from ..status_log import emit_status_line
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
        if int(unit["index"]) == int(unit["total"]):
            full_ok, full = validate_phase3(ctx["tid"], ctx["tooling"], ctx["plan"], ())
            report = "\n".join(part for part in (report, full) if part)
            if not full_ok:
                record_section_failure(build_id, unit["section"], full)
                return False, report
        # Single optional advisory pass, then deterministic-only (see section_review).
        ok, review_report = review_section(build_id, unit)
        if not ok:
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
        return True, report
    phase = int(unit["phase"])
    definition = PHASE_REGISTRY.get(phase)
    ok, report = definition.validate(build_id, ctx)
    if ok and phase in (1, 2):
        planning = review_planning_phase(build_id, phase, ctx["tid"])
        ai_report = planning_review_report(phase, planning)
        if planning.get("status") != "PASS" and not re.search(
                r"(?im)^\s*issues?\s+found\s*[:=]\s*\d+\b", ai_report):
            explicit = planning.get("issueCount")
            finding_count = len(planning.get("findings") or [])
            issue_count = (int(explicit) if str(explicit or "").isdigit()
                           else finding_count or 1)
            ai_report = f"Issues found: {max(1, issue_count)}\n\n{ai_report}"
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
    """Exact mechanical checks shared by the author and independent harness gate."""
    ctx = context(build_id)
    if unit["kind"] == "section":
        commands = [section_validator_argv(
            ctx["tid"], unit["section"], ctx["tooling"], ctx["plan"])]
        if int(unit.get("index") or 0) == int(unit.get("total") or -1):
            commands.append(phase3_validator_argv(
                ctx["tid"], ctx["tooling"], ctx["plan"], run=True))
    else:
        commands = PHASE_REGISTRY.get(unit["phase"]).self_checks(build_id, ctx)
    return [list(command) for command in commands]


def self_validation_commands(build_id, unit):
    return [shlex.join(command) for command in self_validation_argvs(build_id, unit)]


def validate_author_self_check(build_id, unit):
    """Independently reproduce an author-reported mechanical check outcome."""
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
    """Trusted marker used after independently reproducing a clean author self-check."""
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
            elif not os.path.isfile(audit_path(build_id, BUILD_DIR)):
                initialize_audit(
                    build_id, _read(seed_path(build_id), {}) or {}, build_dir=BUILD_DIR)
            if not os.path.isfile(ledger_path(build_id)):
                initialize_ledger(build_id, ctx["tooling"])
    preflight_validator_runtime(ctx["tid"], entrypoints)


def validation_failure_message(unit, report):
    return render_validation_failure_message(label(unit), report)


def mechanical_validation_prompt(build_id, unit):
    commands = self_validation_commands(build_id, unit)
    rendered = "\n".join(f"- `{command}`" for command in commands)
    return (
        "Run the exact mechanical check(s) below whenever useful while authoring and after every "
        "repair; there is no one-run limit. Before handoff, ALWAYS run every listed command in "
        "order and repair authored findings until every command exits 0. These transparent "
        "mechanical checks are required author feedback and are not the Validator AI. Do not run "
        "or imitate the Validator AI, run deterministic transition commands, or substitute ad-hoc "
        "checks. If an exact command cannot start or crashes before returning structured "
        "ERROR/WARN findings, answer once in this exact form and stop:\n"
        "`HARNESS_BLOCKED:`\n"
        "`COMMAND: <copy the exact failed command>`\n"
        "`DIAGNOSTIC:`\n"
        "`<raw diagnostic>`\n"
        "Do not edit repository tooling. The harness reruns the named command; it never "
        "substitutes a different check.\nExact mechanical checks:\n"
        f"{rendered}\nOnly after all exact checks exit 0, set the unit's progress marker to "
        "`validating` and stop. The harness independently reruns the same complete mechanical gate, "
        "then starts the Validator AI when that unit has one."
    )


def next_prompt(build_id, passed, next_unit, report):
    summary = str(report or "clean").strip()[-1600:]
    return (f"HARNESS VALIDATION PASSED for {label(passed)}.\n{summary}\n\n"
            + unit_prompt(build_id, next_unit))


def unit_semantic_authority(build_id, unit):
    """Return the exact semantic policy shared with this unit's Validator AI."""
    if unit.get("kind") == "section":
        return section_quality_authority(
            **section_quality_settings(BUILD_DIR, build_id))
    phase = int(unit.get("phase") or 0)
    if phase in (1, 2):
        return (planning_authority(phase) + "\n\n"
                + planning_dynamic_authority(
                    build_id, phase, build_dir=BUILD_DIR))
    return ""


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
    authority = unit_semantic_authority(build_id, unit)
    return (f"HARNESS VALIDATION FAILED for {label(unit)}. {scope} in the same "
            "session. Preserve clean work. Treat the report below as the complete repair packet: "
            "do not rerender the section context, repeat initial discovery, or broaden the edit. "
            "Read only cited files/ranges needed for the findings and batch all related fixes into one "
            "coherent repair pass, using as many small valid edit operations as needed. Do not run "
            "or imitate the Validator AI and do not serialize one "
            "finding per turn. Use the exact mechanical checks below while repairing.\n\n"
            + (authority + "\n\n" if authority else "")
            + f"{str(report or 'validator failed')[-12000:]}\n\n"
            + f"{mechanical_validation_prompt(build_id, unit)} Then run exactly `{marker}` and stop "
            + "so the harness can validate the repair.")


def continue_prompt(build_id, unit):
    return render_continue_prompt(
        build_id, unit,
        label=label,
        unit_prompt=unit_prompt,
        mechanical_validation_prompt=mechanical_validation_prompt,
    )




def unit_prompt(build_id, unit):
    marker = ((f"python3 tools/workflow/report_section_progress.py {build_id} {unit['section']} "
               f"{unit['index']} {unit['total']} validating")
              if unit["kind"] == "section" else
              f"python3 tools/workflow/report_tome_progress.py {build_id} {unit['phase']} validating")
    construction = (f" {LEARNER_CONSTRUCTION_INSTRUCTION}" if unit["kind"] == "section" else "")
    rhythm = (f" {LESSON_BATCH_INSTRUCTION}" if unit["kind"] == "section" else "")
    prompt = (f"Continue with {label(unit)}. Read its phase guide, then complete exactly this unit."
              f"{construction}{rhythm} "
              f"{mechanical_validation_prompt(build_id, unit)} Then run exactly `{marker}` and stop so the harness "
              "can validate it.")
    authority = unit_semantic_authority(build_id, unit)
    if authority:
        prompt += "\n\n" + authority
    if unit["kind"] != "section":
        phase = int(unit.get("phase") or 0)
        if phase == 2:
            prompt += (
                f" Begin with exactly `python3 tools/workflow/context/render_phase2_context.py {build_id}`. "
                "That bounded packet replaces broad repository discovery. Edit only the compact "
                "Phase-2 sources and other repairable paths it names. Its authority block controls "
                "family meaning, same-lesson prerequisite order, artifact-production modes, source "
                "budget, and repair ownership. Complete audit.json v2 with one exact family, "
                "teaching-prerequisite list, and production-prerequisite list per mechanism; one "
                "component-mechanism row per taught capability; one preserved-mechanism row per "
                "planned continuity obligation; every failure-path role; and one "
                "production row per sealed artifact. External installation and verification must "
                "precede project source editing. This "
                "is mechanically checked author work, not an optional prose checklist. The harness "
                "deterministically materializes the full "
                "proposal after handoff. Complete every section plan in one coherent batch. If external "
                "tooling is selected, use web search only for facts that affect installation, current "
                "commands, APIs, compatibility, or delivery; cite no more than six official or primary "
                "sources in the research ledger. Later authors reuse that ledger. Target no more than "
                "$2 API-equivalent for initial Phase 2 planning; avoid rereading generated proposal JSON."
            )
        return prompt
    prompt += (
        f" Begin with exactly `python3 tools/workflow/context/render_section_context.py {build_id} "
        f"{unit['section']}`; that bounded packet replaces scattered initial discovery reads. "
        "Its `sectionQualityContract` is the exact binding policy used by the Validator AI; apply "
        "it before drafting lessons or the Working. "
        "After it, batch independent file reads and searches into one tool call and group related "
        "file edits into one coherent edit pass using small valid patch operations. Do not inspect one "
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
