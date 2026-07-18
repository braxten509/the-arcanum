"""Composition of the eight standard authoring phase definitions."""
from __future__ import annotations

import os
import subprocess

from .. import REPO
from ..course.state import refresh_course_verifications
from ..course_map import load_course_map
from ..mastery_evidence import export_mastery_contract, validate_semantic_review
from ..measure import (phase3_validator_argv, validate, validate_live_smoke,
                       validate_phase3, validate_shipping, validator_argv)
from .models import PhaseDefinition
from .registry import PhaseRegistry


def _phase1(build_id: str, context: dict) -> tuple[bool, str]:
    return validate(build_id, phase=1, plan_rel=context["plan"])


def _phase2(_build_id: str, context: dict) -> tuple[bool, str]:
    return validate(context["tid"], phase=2, tooling=context["tooling"], run=False,
                    plan_rel=context["plan"])


def _phase3(_build_id: str, context: dict) -> tuple[bool, str]:
    return validate_phase3(context["tid"], context["tooling"], context["plan"], ())


def _authored_bank(phase: int):
    def run(_build_id: str, context: dict) -> tuple[bool, str]:
        return validate(context["tid"], phase=phase, tooling=context["tooling"],
                        run=False, plan_rel=context["plan"], phase_only=True)
    return run


def _shipping(build_id: str, context: dict, prelude: str = "") -> tuple[bool, str]:
    ok, report = validate_shipping(context["tid"], context["tooling"], context["plan"])
    report = "\n".join(part for part in (prelude, report) if part)
    if not ok:
        return False, report
    try:
        refresh_course_verifications(build_id, report)
    except ValueError as exc:
        return False, "\n".join(part for part in (report, str(exc)) if part)
    smoke_ok, smoke = validate_live_smoke(context["tid"])
    return smoke_ok, "\n".join(part for part in (report, smoke) if part)


def _phase7(build_id: str, context: dict) -> tuple[bool, str]:
    generated = subprocess.run(
        ["python3", "tools/gen_mastery_labs.py", context["tid"],
         "--build-id", build_id], cwd=REPO, capture_output=True, text=True)
    generation_report = (generated.stdout + generated.stderr).strip()
    if generated.returncode:
        return False, "MASTERY VARIANT GENERATION:\n" + generation_report
    return _shipping(build_id, context, generation_report)


def _phase8(build_id: str, context: dict) -> tuple[bool, str]:
    review_ok, review_report = validate_semantic_review(
        os.path.join(REPO, ".tome-build"), build_id,
        os.path.join(REPO, "tomes", context["tid"]))
    if not review_ok:
        return False, "MASTERY SEMANTIC REVIEW:\n" + review_report
    return _shipping(build_id, context, review_report)


def _validator(phase: int, *, phase_only: bool = False):
    def commands(_build_id: str, context: dict) -> list[list[str]]:
        return [validator_argv(
            context["tid"], phase=phase, tooling=context["tooling"], run=False,
            plan_rel=context["plan"], phase_only=phase_only)]
    return commands


def _phase1_commands(_build_id: str, context: dict) -> list[list[str]]:
    return [validator_argv(context["tid"], phase=1, plan_rel=context["plan"])]


def _phase3_commands(_build_id: str, context: dict) -> list[list[str]]:
    return [phase3_validator_argv(
        context["tid"], context["tooling"], context["plan"], run=True)]


def _phase7_commands(build_id: str, context: dict) -> list[list[str]]:
    return [["python3", "tools/gen_mastery_labs.py", context["tid"],
             "--build-id", build_id],
            phase3_validator_argv(context["tid"], context["tooling"],
                                  context["plan"], run=True, strict=True),
            ["python3", "tools/smoke_tome.py", context["tid"]]]


def _phase8_commands(build_id: str, context: dict) -> list[list[str]]:
    return [["python3", "tools/validate_mastery_review.py", build_id, context["tid"]],
            phase3_validator_argv(context["tid"], context["tooling"],
                                  context["plan"], run=True, strict=True),
            ["python3", "tools/smoke_tome.py", context["tid"]]]


def _export_mastery(build_id: str, context: dict) -> None:
    export_mastery_contract(load_course_map(build_id),
                            os.path.join(REPO, "tomes", context["tid"]))


def standard_phase_registry() -> PhaseRegistry:
    registry = PhaseRegistry()
    entries = (
        PhaseDefinition(1, "concept-arc", "Concept & arc", _phase1,
                        _phase1_commands,
                        ("tools/validate_tome.py", "tools/workflow/author_phase_transition.py"),
                        transition_command=True),
        PhaseDefinition(2, "skeleton-voice", "Skeleton & voice", _phase2,
                        _validator(2),
                        ("tools/validate_tome.py", "tools/workflow/author_phase_transition.py"),
                        transition_command=True, on_exit=_export_mastery),
        PhaseDefinition(3, "sections", "Sections", _phase3, _phase3_commands,
                        ("tools/validate_phase3.py",), unit_kind="section"),
        PhaseDefinition(4, "minigames", "Minigames", _authored_bank(4),
                        _validator(4, phase_only=True), ("tools/validate_tome.py",)),
        PhaseDefinition(5, "economy", "Economy", _authored_bank(5),
                        _validator(5, phase_only=True), ("tools/validate_tome.py",)),
        PhaseDefinition(6, "cosmetics", "Cosmetics", _authored_bank(6),
                        _validator(6, phase_only=True), ("tools/validate_tome.py",)),
        PhaseDefinition(7, "validate", "Validate", _phase7, _phase7_commands,
                        ("tools/validate_phase3.py", "tools/smoke_tome.py",
                         "tools/gen_mastery_labs.py")),
        PhaseDefinition(8, "student-review", "Student review", _phase8,
                        _phase8_commands,
                        ("tools/validate_phase3.py", "tools/smoke_tome.py",
                         "tools/validate_mastery_review.py"), final=True),
    )
    for entry in entries:
        registry.register(entry)
    return registry.seal()
