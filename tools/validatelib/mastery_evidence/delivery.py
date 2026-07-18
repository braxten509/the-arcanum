"""Runtime evidence-descriptor availability and sealed-map identity."""
from __future__ import annotations

import json
import os

from arcanum_core.contracts.mastery import MasteryEvidenceContract
from arcanum_core.findings import Finding, Severity

from .schema import error


def delivery_findings(tome_root: str, manifest: dict,
                      course_map: dict | None) -> list[Finding]:
    path = os.path.join(tome_root, "generated", "mastery-evidence.json")
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
        contract = MasteryEvidenceContract.from_dict(value)
    except FileNotFoundError:
        return [Finding(Severity.WARNING, "mastery.delivery.missing", path,
                        "Phase 7 must ship the sealed runtime mastery-evidence descriptor", 7)]
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return [error("mastery.delivery.invalid", path,
                      f"runtime mastery-evidence descriptor is invalid: {exc}", 7)]
    mastery = manifest.get("mastery") or {}
    findings = []
    if (contract.version != mastery.get("evidenceVersion")
            or contract.level != mastery.get("level")):
        findings.append(error("mastery.delivery.manifest-drift", path,
                              "runtime evidence version/level differs from tome.toml", 7))
    sealed = (course_map or {}).get("masteryEvidence") if course_map else None
    if sealed is not None and value != sealed:
        findings.append(error("mastery.delivery.map-drift", path,
                              "runtime evidence descriptor differs from the sealed course map", 7))
    return findings
