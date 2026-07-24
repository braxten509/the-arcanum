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
from arcanum.catalog.assembly import _strip_evidence_bank_answers
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

PARTIAL_ASSESSMENT = ASSESSMENT.split(
    '[[scenarios]]\nid = "cold-launch"', 1)[0]


with tempfile.TemporaryDirectory() as temp:
    tome = Path(temp)
    (tome / "sections" / "s01").mkdir(parents=True)
    (tome / "sections" / "s01" / "assessment.toml").write_text(ASSESSMENT)
    clean = validate_mastery_evidence(str(tome), copy.deepcopy(MANIFEST),
                                      [copy.deepcopy(SECTION)], include_variants=False)
    assert not clean, "\n".join(item.message for item in clean)

    # A section-scoped Phase-3 packet is not the course boundary. Final delivery
    # requirements come from the manifest's complete section order, even when the
    # validator receives only the current authored section.
    scoped_manifest = copy.deepcopy(MANIFEST)
    scoped_manifest["content"] = {"sections": ["s01", "s08"]}
    scoped_manifest["acceptance"]["artifact"] = "package"
    scoped_section = copy.deepcopy(SECTION)
    scoped_section["freestyle"]["rubric"][0]["assessmentIds"] = ["builds", "runs"]
    (tome / "sections" / "s01" / "assessment.toml").write_text(
        PARTIAL_ASSESSMENT, encoding="utf-8")
    scoped_findings = validate_mastery_evidence(
        str(tome), scoped_manifest, [scoped_section], include_variants=False)
    assert not any(item.code in {"mastery.assessment.cold-launch",
                                 "mastery.assessment.package"}
                   for item in scoped_findings), [item.to_dict() for item in scoped_findings]

    final_section = copy.deepcopy(scoped_section)
    final_section["id"] = "s08"
    (tome / "sections" / "s08").mkdir(parents=True)
    (tome / "sections" / "s08" / "assessment.toml").write_text(
        PARTIAL_ASSESSMENT, encoding="utf-8")
    final_findings = validate_mastery_evidence(
        str(tome), scoped_manifest, [final_section], include_variants=False)
    assert {item.code for item in final_findings} >= {
        "mastery.assessment.cold-launch", "mastery.assessment.package"}, [
            item.to_dict() for item in final_findings]

    # Restore the complete fixture for the remaining independent cases.
    (tome / "sections" / "s01" / "assessment.toml").write_text(
        ASSESSMENT, encoding="utf-8")

    bad_exercise = copy.deepcopy(SECTION)
    del bad_exercise["lessons"][0]["exercises"][0]["cognitiveTask"]
    findings = validate_mastery_evidence(str(tome), MANIFEST, [bad_exercise],
                                         include_variants=False)
    assert any(item.code == "mastery.exercise.metadata" for item in findings)

    malformed_lesson = copy.deepcopy(SECTION)
    malformed_lesson["lessons"] = ["readings", "concepts", "exercises"]
    findings = validate_mastery_evidence(str(tome), MANIFEST, [malformed_lesson],
                                         include_variants=False)
    assert sum(item.code == "mastery.lesson.shape" for item in findings) == 3

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
    assert not payload_findings({"acceptance": {"scenarios": ["ordinary-launch"]}})
    assert evidence_payload_privacy_enabled(MANIFEST)
    assert not evidence_payload_privacy_enabled({"mastery": {"level": 3}})

    # New tomes opt into receipts and adversarial Working evidence. A receipt must be
    # attributable to the lesson and an essential behavior cannot live on one happy path.
    hardened_manifest = copy.deepcopy(MANIFEST)
    hardened_manifest["mastery"]["sourceEvidenceVersion"] = 1
    hardened_section = copy.deepcopy(SECTION)
    hardened_section["lessons"][0]["researchSources"] = ["python-print"]
    hardened_section["lessons"][0]["readings"] = [{
        "label": "Python print documentation",
        "url": "https://docs.python.org/3/library/functions.html#print",
    }]
    (tome / "sections" / "s01" / "research.toml").write_text('''version = 1
[[sources]]
id = "python-print"
url = "https://docs.python.org/3/library/functions.html#print"
authority = "Official Python standard-library documentation."
claims = ["print writes the requested observable result to standard output."]
''', encoding="utf-8")
    findings = validate_mastery_evidence(str(tome), hardened_manifest, [hardened_section],
                                         include_variants=False)
    assert not any(item.code.startswith("mastery.sources")
                   or item.code.startswith("mastery.assessment.varied")
                   for item in findings), [item.to_dict() for item in findings]

    duplicate_input = ASSESSMENT + '''
[[scenarios]]
id = "runs-again"
kind = "run"
requirementIds = ["observable-result"]
capabilityIds = ["language-data"]
commandRef = "run"
args = []
stdin = ""
expectRegex = "DIFFERENT"
exitCode = 0
timeout = 20
public = false
'''
    duplicate_section = copy.deepcopy(hardened_section)
    duplicate_section["freestyle"]["rubric"][0]["assessmentIds"].append("runs-again")
    (tome / "sections" / "s01" / "assessment.toml").write_text(
        duplicate_input, encoding="utf-8")
    duplicate_findings = validate_mastery_evidence(
        str(tome), hardened_manifest, [duplicate_section], include_variants=False)
    assert any(item.code == "mastery.assessment.redundant-evidence"
               for item in duplicate_findings), [
                   item.to_dict() for item in duplicate_findings]
    (tome / "sections" / "s01" / "assessment.toml").write_text(
        ASSESSMENT, encoding="utf-8")

    hardened_section["lessons"][0]["researchSources"] = ["invented-source"]
    findings = validate_mastery_evidence(str(tome), hardened_manifest, [hardened_section],
                                         include_variants=False)
    assert any(item.code == "mastery.sources.lesson" for item in findings)
    hardened_section["lessons"][0]["researchSources"] = ["python-print"]
    hardened_section["freestyle"]["rubric"][0]["assessmentIds"] = ["builds", "runs"]
    one_path = ASSESSMENT.split('[[scenarios]]\nid = "cold-launch"', 1)[0]
    (tome / "sections" / "s01" / "assessment.toml").write_text(one_path, encoding="utf-8")
    findings = validate_mastery_evidence(str(tome), hardened_manifest, [hardened_section],
                                         include_variants=False)
    assert any(item.code == "mastery.assessment.varied-evidence" for item in findings), [
        item.to_dict() for item in findings]
    (tome / "sections" / "s01" / "assessment.toml").write_text(ASSESSMENT, encoding="utf-8")

    evidence_payload = {
        "mastery": {"evidenceVersion": 1, "level": 3},
        "progression": {"intrusionTiers": [{"pool": [
            {"id": "hex-one", "starter": "incomplete", "solution": "private"}]}]},
    }
    _strip_evidence_bank_answers(evidence_payload)
    challenge = evidence_payload["progression"]["intrusionTiers"][0]["pool"][0]
    assert challenge == {"id": "hex-one", "starter": "incomplete"}

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

with tempfile.TemporaryDirectory() as temp:
    tome = Path(temp)
    contract, sections = future_map(1)
    preview = tome / "materialized-preview.json"
    stale_proposal = tome / "course-map.proposal.json"
    preview.write_text(json.dumps({"masteryEvidence": contract, "sections": sections}),
                       encoding="utf-8")
    stale_sections = copy.deepcopy(sections)
    for section in stale_sections:
        section["nodes"] = []
    stale_proposal.write_text(
        json.dumps({"masteryEvidence": contract, "sections": stale_sections}),
        encoding="utf-8")

    stale_findings = validate_mastery_evidence(
        str(tome), MANIFEST, [], phase2_skeleton=True,
        phase2_proposal=str(stale_proposal))
    assert any("names missing node" in item.message for item in stale_findings), [
        item.to_dict() for item in stale_findings]

    preview_findings = validate_mastery_evidence(
        str(tome), MANIFEST, [], phase2_skeleton=True,
        phase2_proposal=str(preview))
    assert not [item for item in preview_findings if item.code == "mastery.map.contract"], [
        item.to_dict() for item in preview_findings]

print("mastery authored-contract validator tests: OK")
