#!/usr/bin/env python3
"""Future-tome exercise, Working, manifest, and payload validator fixtures."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from tools.validatelib.mastery_evidence import validate_mastery_evidence
from tools.validatelib.mastery_evidence.payload import (evidence_payload_privacy_enabled,
                                                        payload_findings)
from tools.tests.mastery.authoring.fixture import write_labs
from tools.tests.mastery.fixtures import future_map


MANIFEST = {
    "mastery": {"evidenceVersion": 1, "level": 1},
    "runtime": {"name": "python"}, "acceptance": {"artifact": "runtime"},
}
SECTION = {
    "id": "s01",
    "lessons": [{"id": "s01-l01", "exercises": [{
        "id": "s01-l01-e1", "type": "write", "points": 10, "prompt": "Build it.",
        "required": True, "capabilities": ["language-data"], "cognitiveTask": "build",
        "scaffold": "guided", "contextFamily": "small-records", "aidPolicy": "learning",
    }]}],
    "freestyle": {
        "requirements": [{"id": "observable-result", "text": "Print READY.",
                          "essential": True, "capabilities": ["language-data"]}],
        "rubric": [{"id": "observable-evidence", "criterion": "Observable result",
                    "weight": 100, "kind": "deterministic",
                    "assessmentIds": ["builds", "runs", "cold-launch"]}],
    },
}
ASSESSMENT = '''version = 1
[[scenarios]]
id = "builds"
kind = "build"
requirementIds = ["observable-result"]
capabilityIds = ["language-data"]
commandRef = "build"
args = []
stdin = ""
exitCode = 0
timeout = 20
public = true

[[scenarios]]
id = "runs"
kind = "run"
requirementIds = ["observable-result"]
capabilityIds = ["language-data"]
commandRef = "run"
args = []
stdin = ""
expectRegex = "READY"
exitCode = 0
timeout = 20
public = false

[[scenarios]]
id = "cold-launch"
kind = "cold-launch"
requirementIds = ["observable-result"]
capabilityIds = ["language-data"]
commandRef = "run"
args = []
stdin = ""
expectRegex = "READY"
exitCode = 0
timeout = 20
public = false
'''


with tempfile.TemporaryDirectory() as temp:
    tome = Path(temp)
    (tome / "sections" / "s01").mkdir(parents=True)
    (tome / "sections" / "s01" / "assessment.toml").write_text(ASSESSMENT)
    clean = validate_mastery_evidence(str(tome), copy.deepcopy(MANIFEST),
                                      [copy.deepcopy(SECTION)], include_variants=False)
    assert not clean, "\n".join(item.message for item in clean)

    bad_exercise = copy.deepcopy(SECTION)
    del bad_exercise["lessons"][0]["exercises"][0]["cognitiveTask"]
    findings = validate_mastery_evidence(str(tome), MANIFEST, [bad_exercise],
                                         include_variants=False)
    assert any(item.code == "mastery.exercise.metadata" for item in findings)

    copying = copy.deepcopy(SECTION)
    exercise = copying["lessons"][0]["exercises"][0]
    exercise.update(type="type", cognitiveTask="recall", scaffold="cold")
    findings = validate_mastery_evidence(str(tome), MANIFEST, [copying], include_variants=False)
    assert any(item.code == "mastery.exercise.copying-evidence" for item in findings)

    unstructured = copy.deepcopy(SECTION)
    unstructured["freestyle"].pop("requirements")
    findings = validate_mastery_evidence(str(tome), MANIFEST, [unstructured],
                                         include_variants=False)
    assert any(item.code == "mastery.working.requirements" for item in findings)

    drift = copy.deepcopy(MANIFEST)
    drift["mastery"]["evidenceVersion"] = 99
    findings = validate_mastery_evidence(str(tome), drift, [SECTION], include_variants=False)
    assert any(item.code == "mastery.manifest.version" for item in findings)

    assert payload_findings({"sections": [{"assessment": {"scenarios": []}}]})
    assert not payload_findings({"sections": [{"freestyle": {"requirements": []}}]})
    assert evidence_payload_privacy_enabled(MANIFEST)
    assert not evidence_payload_privacy_enabled({"mastery": {"level": 3}})

with tempfile.TemporaryDirectory() as temp:
    tome = Path(temp)
    contract, _sections = future_map(3)
    (tome / "generated").mkdir(parents=True)
    (tome / "generated" / "mastery-evidence.json").write_text(
        json.dumps(contract), encoding="utf-8")
    write_labs(tome, contract)
    manifest = copy.deepcopy(MANIFEST)
    manifest["mastery"]["level"] = 3
    findings = validate_mastery_evidence(
        str(tome), manifest, [], include_variants=False)
    assert not any(item.code in {"mastery.lab.node", "mastery.lab.missing"}
                   for item in findings), [item.to_dict() for item in findings]

    (tome / "generated" / "mastery-evidence.json").unlink()
    findings = validate_mastery_evidence(
        str(tome), manifest, [], include_variants=False)
    assert any(item.code == "mastery.lab.node" for item in findings)

print("mastery authored-contract validator tests: OK")
