"""Pure findings adapter for the complete future-tome evidence contract."""
from __future__ import annotations

import json
import os

from arcanum_core.findings import Finding, Severity

from buildlib.course_map import build_id_from_plan, map_path, proposal_path

from .exercises import exercise_findings
from .labs import lab_findings
from .schema import manifest_findings
from .variants import variant_findings
from .workings import working_findings


def _read(path: str) -> str:
    try:
        return open(path, encoding="utf-8").read()
    except OSError:
        return ""


def _map(build_plan: str | None) -> dict | None:
    if not build_plan:
        return None
    build_id = build_id_from_plan(build_plan)
    for path in (map_path(build_id), proposal_path(build_id)):
        try:
            return json.load(open(path, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return None


def validate_mastery_evidence(tome_root: str, manifest: dict, sections: list[dict], *,
                              build_plan: str | None = None,
                              phase2_skeleton: bool = False,
                              include_variants: bool = True) -> list[Finding]:
    mastery = manifest.get("mastery")
    if not isinstance(mastery, dict):
        return []
    plan_text, course_map = _read(build_plan) if build_plan else "", _map(build_plan)
    findings = manifest_findings(manifest, os.path.join(tome_root, "tome.toml"),
                                 plan_text=plan_text, course_map=course_map)
    if phase2_skeleton:
        return findings
    capabilities = set((((course_map or {}).get("masteryEvidence") or {}).get("capabilityIds") or []))
    findings += exercise_findings(sections, capabilities)
    findings += working_findings(tome_root, manifest, sections)
    level = mastery.get("level") if isinstance(mastery.get("level"), int) else 0
    if 1 <= level <= 5:
        findings += lab_findings(tome_root, level, course_map)
        if include_variants:
            findings += variant_findings(tome_root, os.path.join(tome_root, "save"), level)
    return findings
