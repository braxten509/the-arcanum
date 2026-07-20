"""Orthogonal exercise renderer/cognitive/evidence metadata checks."""
from __future__ import annotations

import re

from arcanum_core.contracts.mastery import AID_POLICIES, COGNITIVE_TASKS, SCAFFOLDS
from arcanum_core.findings import Finding
from arcanum_core.ids import is_capability_id, is_stable_id

from .schema import error

REQUIRED_KEYS = {"required", "capabilities", "cognitiveTask", "scaffold",
                 "contextFamily", "aidPolicy"}
IMPOSSIBLE = {
    "mc": {"build", "integrate", "refactor", "profile", "design-defense"},
    "fill": {"build", "integrate", "refactor", "profile", "design-defense"},
    "type": set(COGNITIVE_TASKS) - {"recall", "recognize", "complete"},
}


def _exercise_findings(exercise: dict, location: str, known_capabilities: set[str]) -> list[Finding]:
    findings = []
    missing = sorted(REQUIRED_KEYS - set(exercise))
    if missing:
        findings.append(error("mastery.exercise.metadata", location,
                              "exercise is missing evidence metadata: " + ", ".join(missing), 3))
        return findings
    if not isinstance(exercise.get("required"), bool):
        findings.append(error("mastery.exercise.required", location, "required must be boolean", 3))
    capabilities = exercise.get("capabilities")
    if (not isinstance(capabilities, list) or not capabilities
            or len(capabilities) != len(set(capabilities))
            or any(not is_capability_id(item) for item in capabilities)):
        findings.append(error("mastery.exercise.capabilities", location,
                              "capabilities must be a unique non-empty capability-id array", 3))
    elif known_capabilities and set(capabilities) - known_capabilities:
        findings.append(error("mastery.exercise.unknown-capability", location,
                              "exercise names capability IDs outside the sealed spine: "
                              + ", ".join(sorted(set(capabilities) - known_capabilities)), 3))
    task = exercise.get("cognitiveTask")
    if task not in COGNITIVE_TASKS:
        findings.append(error("mastery.exercise.cognitive-task", location,
                              "cognitiveTask is unsupported", 3))
    renderer = exercise.get("type")
    if task in IMPOSSIBLE.get(renderer, set()):
        findings.append(error("mastery.exercise.renderer-mismatch", location,
                              f"renderer {renderer!r} cannot demonstrate cognitive task {task!r}", 3))
    scaffold = exercise.get("scaffold")
    if scaffold not in SCAFFOLDS:
        findings.append(error("mastery.exercise.scaffold", location, "scaffold is unsupported", 3))
    if renderer == "type" and scaffold in {"independent", "cold"}:
        findings.append(error("mastery.exercise.copying-evidence", location,
                              "a copying drill cannot be credited as independent mastery", 3))
    aid = exercise.get("aidPolicy")
    if aid not in AID_POLICIES:
        findings.append(error("mastery.exercise.aid-policy", location, "aidPolicy is unsupported", 3))
    if aid in {"documentation-only", "cold"} and exercise.get("hint"):
        findings.append(error("mastery.exercise.aid-leak", location,
                              f"{aid} activities may not ship an answer-producing hint", 3))
    if not is_stable_id(exercise.get("contextFamily")):
        findings.append(error("mastery.exercise.context", location,
                              "contextFamily must be a stable kebab-case id", 3))
    variants = exercise.get("reviewVariants")
    if variants is not None:
        if not isinstance(variants, list) or len(variants) < 2:
            findings.append(error("mastery.exercise.review-variants", location,
                                  "reviewVariants must contain at least two varied records", 3))
        elif any(not isinstance(row, dict) or not str(row.get("prompt") or "").strip()
                 for row in variants):
            findings.append(error("mastery.exercise.review-variant-shape", location,
                                  "every review variant needs a concrete prompt and answer fields", 3))
        elif len({str(row.get("prompt")) for row in variants}) != len(variants):
            findings.append(error("mastery.exercise.review-duplicate", location,
                                  "review variant prompts must materially differ", 3))
    return findings


def exercise_findings(sections: list[dict], known_capabilities: set[str]) -> list[Finding]:
    findings = []
    for section in sections:
        sid = str(section.get("id") or "?")
        for index, lesson in enumerate(section.get("lessons") or []):
            if not isinstance(lesson, dict):
                findings.append(error(
                    "mastery.lesson.shape",
                    f"sections/{sid}:lesson[{index}]",
                    "lesson entries must be [[lessons]] tables",
                    3,
                ))
                continue
            lid = str(lesson.get("id") or "?")
            exercises = [row for row in lesson.get("exercises") or [] if isinstance(row, dict)]
            for index, exercise in enumerate(exercises):
                location = f"sections/{sid}/lessons/{lid}:exercise[{index}]"
                findings += _exercise_findings(exercise, location, known_capabilities)
            if exercises and not any(row.get("required") is True for row in exercises):
                findings.append(error("mastery.lesson.no-required-work", f"sections/{sid}/{lid}",
                                      "every lesson needs at least one required activity", 3))
    return findings
