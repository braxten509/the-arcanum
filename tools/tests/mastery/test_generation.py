#!/usr/bin/env python3
"""Hybrid variant expansion, proof, persistence, and tamper fixtures."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from arcanum.assessment.variants import VariantRepository
from runtimes import for_config
from tools.buildlib.mastery_evidence.variants import VariantGenerator


class SemanticPass:
    def review(self, candidate: dict) -> dict:
        return {"passed": True, "problems": [],
                "evidenceHash": "semantic-" + candidate["variantId"]}


class PythonProofSandbox:
    """Deterministic process-port fake; SandboxRunner itself has separate boundary tests."""

    def run(self, command, *, cwd, stdin="", timeout=30, policy=None, env=None):
        source = (Path(cwd) / "main.py").read_text()
        if "compileall" in command:
            output, passed = "", True
        elif "READY" in source:
            output, passed = source.split('print("', 1)[1].split('")', 1)[0], True
        else:
            output, passed = "WRONG", True
        return {"passed": passed, "argv": list(command), "exitCode": 0,
                "output": output, "timedOut": False, "outputClipped": False}


def blueprint() -> dict:
    requirement = {"id": "emit-result", "text": "Emit the declared result.",
                   "essential": True, "capabilityIds": ["language-data"]}
    scenarios = [
        {"id": "builds", "kind": "build", "requirementIds": ["emit-result"],
         "capabilityIds": ["language-data"], "commandRef": "build", "args": [],
         "stdin": "", "expect": {"exitCode": 0}, "timeout": 20, "public": True},
        {"id": "varied-result", "kind": "run", "requirementIds": ["emit-result"],
         "capabilityIds": ["language-data"], "commandRef": "run", "args": [],
         "stdin": "", "expect": {"exact": "READY {{domain}} {{shape}}", "exitCode": 0},
         "timeout": 20, "public": False},
    ]
    return {
        "version": 1, "id": "record-transform", "title": "{{domain}} {{shape}} transform",
        "brief": "Reconcile {{domain}} records delivered as {{shape}} input and emit the result.",
        "difficulty": "introductory transfer", "starterBuildable": True,
        "axes": {"domain": ["harbor", "clinic", "archive"],
                 "shape": ["rows", "events"]},
        "publicFiles": {"main.py": 'print("WRONG")\n'},
        "publicExamples": ["A valid run emits the declared domain and input shape."],
        "hiddenFiles": {},
        "referenceFiles": {"main.py": 'print("READY {{domain}} {{shape}}")\n'},
        "mutations": {"omits-domain": {"main.py": 'print("READY {{shape}}")\n'},
                      "omits-shape": {"main.py": 'print("READY {{domain}}")\n'}},
        "dependencies": [],
        "assessment": {"version": 1, "requirements": [requirement],
                       "scenarios": scenarios,
                       "rubric": [{"id": "behavior", "criterion": "Observable behavior",
                                   "weight": 100, "kind": "deterministic",
                                   "assessmentIds": ["builds", "varied-result"]}]},
    }


with tempfile.TemporaryDirectory() as temp:
    tome = Path(temp)
    (tome / "tome.toml").write_text(
        '[mastery]\nevidenceVersion = 1\nlevel = 1\n\n[runtime]\nname = "python"\n')
    family = tome / "sections" / "s01" / "mastery-labs" / "transfer"
    (family / "public").mkdir(parents=True)
    (family / "hidden").mkdir()
    (family / "blueprints").mkdir()
    lab_file = family.with_suffix(".toml")
    lab_file.write_text('''[masteryLab]
version = 1
id = "transfer"
nodeId = "s01.lab01"
performanceId = "performance-s01-lab01"
title = "Transfer"
performanceKind = "guided-modification"
capabilityIds = ["language-data"]
cognitiveTasks = ["build", "explain"]
contextFamily = "records"
contextRelation = "project"
aidPolicy = "cold"
estimatedMinutes = 20
rationaleRequired = true
variantFamilyId = "transfer"

[generator]
mode = "hybrid-ai-verified"
minimumBlueprints = 1
minimumVerifiedVariants = 6
variationAxes = ["domain", "shape"]
newVariantOnRetry = true
''')
    (family / "blueprints" / "records.json").write_text(json.dumps(blueprint()))
    runtime = for_config({"name": "python"})
    generator = VariantGenerator(runtime, SemanticPass(), sandbox=PythonProofSandbox())
    first = generator.generate(str(tome), str(lab_file))
    assert first.generated == 6 and first.reused == 0
    second = generator.generate(str(tome), str(lab_file))
    assert second.generated == 0 and second.reused == 6

    repository = VariantRepository(str(tome), str(tome / "save"))
    assert len(repository.verified_variants("transfer")) == 6
    package = repository.public_package("transfer", first.variant_ids[0])
    assert set(package) == {"version", "familyId", "variantId", "variantHash", "title",
                            "brief", "requirements", "publicExamples", "difficulty",
                            "estimatedMinutes", "rationalePrompt", "aidPolicy", "axes", "files"}
    assert not any("hidden" in str(value) or "reference" in str(value)
                   for value in package.values())

    hidden = (tome / "generated" / "mastery-labs" / "transfer" /
              first.variant_ids[0] / "hidden" / "assessment.json")
    hidden.write_text(hidden.read_text() + "\n")
    assert len(repository.verified_variants("transfer")) == 5

print("mastery variant generation tests: OK")
