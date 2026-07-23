"""Manifest, sealed-map, and Phase-0 mastery alignment."""
from __future__ import annotations

import re

from arcanum_core.findings import Finding, Severity

from buildlib.mastery_evidence import load_policy
from buildlib.mastery_evidence.map_contract import validate_map_contract


def error(code: str, location: str, message: str, phase: int = 7) -> Finding:
    return Finding(Severity.ERROR, code, location, message, phase)


def manifest_findings(manifest: dict, location: str, *, plan_text: str = "",
                      course_map: dict | None = None) -> list[Finding]:
    mastery = manifest.get("mastery")
    if mastery is None:
        return []
    findings = []
    allowed = {"evidenceVersion", "sourceEvidenceVersion", "level"}
    if (not isinstance(mastery, dict)
            or not {"evidenceVersion", "level"}.issubset(mastery)
            or set(mastery) - allowed):
        return [error("mastery.manifest.shape", location,
                      "[mastery] keys must include evidenceVersion and level; optional "
                      "sourceEvidenceVersion is 1", 2)]
    policy = load_policy()
    if mastery.get("evidenceVersion") != policy.version:
        findings.append(error("mastery.manifest.version", location,
                              f"[mastery] evidenceVersion must be {policy.version}", 2))
    if ("sourceEvidenceVersion" in mastery
            and mastery.get("sourceEvidenceVersion") != 1):
        findings.append(error("mastery.manifest.source-version", location,
                              "[mastery] sourceEvidenceVersion must be 1", 2))
    level = mastery.get("level")
    try:
        policy.for_level(level)
    except (TypeError, ValueError):
        findings.append(error("mastery.manifest.level", location,
                              "[mastery] level must be an integer from 1 through 5", 2))
    gate = re.search(r"(?im)^- \*\*Mastery \(1-5\):\*\*\s*([1-5])\s*$", plan_text)
    if gate and level != int(gate.group(1)):
        findings.append(error("mastery.manifest.drift", location,
                              "[mastery] level drifted from the sealed Phase-0 answer", 2))
    if course_map is not None:
        evidence = course_map.get("masteryEvidence") if isinstance(course_map, dict) else None
        if not isinstance(evidence, dict):
            findings.append(error("mastery.map.missing", location,
                                  "evidence-version tomes require the sealed masteryEvidence map", 2))
        else:
            if evidence.get("version") != mastery.get("evidenceVersion"):
                findings.append(error("mastery.map.version-drift", location,
                                      "manifest and map evidence versions differ", 2))
            if evidence.get("level") != level:
                findings.append(error("mastery.map.level-drift", location,
                                      "manifest and map mastery levels differ", 2))
            for problem in validate_map_contract(evidence, course_map.get("sections") or [],
                                                 detailed=True):
                findings.append(error("mastery.map.contract", location, problem, 2))
    return findings
