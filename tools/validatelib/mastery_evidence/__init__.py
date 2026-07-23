"""Pure findings adapter for the complete future-tome evidence contract."""
from __future__ import annotations

import json
import os

from arcanum_core.findings import Finding, Severity

from buildlib.course_map import build_id_from_plan, map_path, proposal_path

from .exercises import exercise_findings
from .delivery import delivery_findings
from .labs import lab_findings
from .schema import manifest_findings
from .variants import variant_findings
from .workings import working_findings


def _read(path: str) -> str:
    try:
        return open(path, encoding="utf-8").read()
    except OSError:
        return ""


def _map(build_plan: str | None, phase2_proposal: str | None = None) -> dict | None:
    if phase2_proposal:
        paths = (phase2_proposal,)
    elif build_plan:
        build_id = build_id_from_plan(build_plan)
        paths = (map_path(build_id), proposal_path(build_id))
    else:
        return None
    for path in paths:
        try:
            return json.load(open(path, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return None


def _shipped_map(tome_root: str) -> dict | None:
    """Expose the shipped descriptor through the map-shaped validator boundary.

    A live Forge build owns an authoritative course-map sidecar, but an installed
    tome must remain fully validatable after those ignored authoring artifacts are
    gone.  The exported descriptor is the sealed runtime copy, so use it for
    capability and lab alignment when no build plan was supplied.  Phase-boundary
    drift checks still use the real course map whenever one is available.
    """
    path = os.path.join(tome_root, "generated", "mastery-evidence.json")
    try:
        with open(path, encoding="utf-8") as handle:
            evidence = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return {"masteryEvidence": evidence} if isinstance(evidence, dict) else None


def validate_mastery_evidence(tome_root: str, manifest: dict, sections: list[dict], *,
                              build_plan: str | None = None,
                              phase2_skeleton: bool = False,
                              phase2_proposal: str | None = None,
                              include_variants: bool = True) -> list[Finding]:
    mastery = manifest.get("mastery")
    if not isinstance(mastery, dict):
        return []
    plan_text = _read(build_plan) if build_plan else ""
    course_map = _map(build_plan, phase2_proposal)
    findings = manifest_findings(manifest, os.path.join(tome_root, "tome.toml"),
                                 plan_text=plan_text, course_map=course_map)
    if phase2_skeleton:
        return findings
    alignment_map = course_map or _shipped_map(tome_root)
    capabilities = set(
        (((alignment_map or {}).get("masteryEvidence") or {}).get("capabilityIds") or []))
    findings += exercise_findings(sections, capabilities)
    findings += working_findings(tome_root, manifest, sections)
    level = mastery.get("level") if isinstance(mastery.get("level"), int) else 0
    if 1 <= level <= 5:
        findings += lab_findings(tome_root, level, alignment_map)
        if include_variants:
            findings += delivery_findings(tome_root, manifest, alignment_map)
            findings += variant_findings(tome_root, os.path.join(tome_root, "save"), level)
    return findings
