"""Builders for a complete synthetic evidence tome without language-specific engine branches."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from buildlib.mastery_evidence import load_policy


class SemanticPass:
    def review(self, candidate: dict) -> dict:
        encoded = json.dumps(candidate, sort_keys=True, separators=(",", ":"))
        return {"passed": True, "problems": [],
                "evidenceHash": hashlib.sha256(encoded.encode()).hexdigest()}


class PythonProofSandbox:
    """Process-port fake; the real sandbox boundary has its own executable tests."""

    def run(self, command, *, cwd, stdin="", timeout=30, policy=None, env=None):
        source = (Path(cwd) / "main.py").read_text(encoding="utf-8")
        if "compileall" in command:
            output = ""
        else:
            marker = 'print("'
            output = source.split(marker, 1)[1].split('")', 1)[0] if marker in source else ""
        return {"passed": True, "argv": list(command), "exitCode": 0,
                "output": output, "timedOut": False, "outputClipped": False}


def authored_sections(contract: dict) -> list[dict]:
    sections = []
    for ordinal in range(1, 10):
        sid = f"s{ordinal:02d}"
        capability = contract["capabilityIds"][(ordinal - 1) % len(contract["capabilityIds"])]
        scenario_ids = ["builds", "runs"] + (["cold-launch"] if ordinal == 9 else [])
        performances = [row["id"] for row in contract["performances"]
                        if row["nodeId"] == f"{sid}.working"]
        sections.append({
            "id": sid,
            "lessons": [{"id": f"{sid}-l01", "exercises": [{
                "id": f"{sid}-l01-e01", "type": "write", "points": 10,
                "prompt": "Produce and verify a fresh solution.", "required": True,
                "capabilities": [capability],
                "cognitiveTask": contract["cognitiveTasks"][0],
                "scaffold": "guided" if contract["level"] == 1 else "cold",
                "contextFamily": f"context-{sid}",
                "aidPolicy": "learning" if contract["level"] == 1 else "cold",
                "reviewVariants": [
                    {"prompt": f"Retrieve {capability} in context alpha.", "answer": "alpha"},
                    {"prompt": f"Retrieve {capability} in context beta.", "answer": "beta"},
                ],
            }]}],
            "freestyle": {
                "masteryPerformances": performances,
                "requirements": [{"id": "observable-result", "text": "Print READY.",
                                  "essential": True, "capabilities": [capability]}],
                "rubric": [{"id": "observable-evidence", "criterion": "Observable result",
                            "weight": 100, "kind": "deterministic",
                            "assessmentIds": scenario_ids}],
            },
        })
    return sections


def write_working_assessments(tome_root: Path) -> None:
    for ordinal in range(1, 10):
        sid = f"s{ordinal:02d}"
        rows = [
            ("builds", "build", "build", "", True),
            ("runs", "run", "run", "READY", False),
        ]
        if ordinal == 9:
            rows.append(("cold-launch", "cold-launch", "run", "READY", False))
        parts = ["version = 1\n"]
        for scenario_id, kind, command, expected, public in rows:
            parts.append(f'''[[scenarios]]
id = "{scenario_id}"
kind = "{kind}"
requirementIds = ["observable-result"]
capabilityIds = []
commandRef = "{command}"
args = []
stdin = ""
{f'expectRegex = "{expected}"' if expected else 'exitCode = 0'}
{'' if expected else ''}timeout = 20
public = {str(public).lower()}
''')
            if expected:
                parts[-1] = parts[-1].replace("timeout = 20", "exitCode = 0\ntimeout = 20")
        target = tome_root / "sections" / sid / "assessment.toml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(parts), encoding="utf-8")


def _axis_names(count: int) -> list[str]:
    return [f"axis-{number}" for number in range(1, count + 1)]


def blueprint(blueprint_number: int, axes: list[str], capabilities: list[str]) -> dict:
    slots = " ".join("{{" + axis + "}}" for axis in axes)
    expected = "READY " + slots
    axis_values = {axis: [f"b{blueprint_number}a{index}left",
                               f"b{blueprint_number}a{index}right"]
                   for index, axis in enumerate(axes, 1)}
    assessment = {
        "version": 1,
        "requirements": [{"id": "emit-result", "text": "Emit the assigned result.",
                          "essential": True, "capabilityIds": capabilities}],
        "scenarios": [
            {"id": "builds", "kind": "build", "requirementIds": ["emit-result"],
             "capabilityIds": capabilities, "commandRef": "build", "args": [],
             "stdin": "", "expect": {"exitCode": 0}, "timeout": 20, "public": True},
            {"id": "assigned-result", "kind": "run", "requirementIds": ["emit-result"],
             "capabilityIds": capabilities, "commandRef": "run", "args": [],
             "stdin": "", "expect": {"exact": expected, "exitCode": 0},
             "timeout": 20, "public": False},
        ],
        "rubric": [{"id": "behavior", "criterion": "Observable behavior", "weight": 100,
                    "kind": "deterministic", "assessmentIds": ["builds", "assigned-result"]}],
    }
    return {
        "version": 1, "id": f"blueprint-{blueprint_number}",
        "title": slots + " transfer", "brief": slots,
        "difficulty": "independent transfer", "starterBuildable": True,
        "axes": axis_values, "publicFiles": {"main.py": 'print("WRONG")\n'},
        "publicExamples": ["The output follows the public assignment."], "hiddenFiles": {},
        "referenceFiles": {"main.py": f'print("{expected}")\n'},
        "mutations": {
            "wrong-result": {"main.py": 'print("WRONG")\n'},
            "empty-result": {"main.py": 'print("")\n'},
        },
        "dependencies": [], "assessment": assessment,
    }


def write_labs(tome_root: Path, contract: dict) -> list[Path]:
    policy = load_policy().for_level(contract["level"])
    paths = []
    for performance in contract["performances"]:
        if ".lab" not in performance["nodeId"]:
            continue
        sid = performance["nodeId"].split(".", 1)[0]
        family = performance["variantFamilyId"]
        lab_root = tome_root / "sections" / sid / "mastery-labs"
        family_root = lab_root / family
        for name in ("public", "hidden", "blueprints"):
            (family_root / name).mkdir(parents=True, exist_ok=True)
        axes = _axis_names(policy.minimum_variation_axes)
        task_values = ", ".join(json.dumps(item) for item in contract["cognitiveTasks"])
        capability_values = ", ".join(json.dumps(item) for item in performance["capabilityIds"])
        axis_values = ", ".join(json.dumps(item) for item in axes)
        lab_path = lab_root / f"{family}.toml"
        lab_path.write_text(f'''[masteryLab]
version = 1
id = "{family}"
nodeId = "{performance['nodeId']}"
performanceId = "{performance['id']}"
title = "Synthetic transfer"
performanceKind = "{performance['kind']}"
capabilityIds = [{capability_values}]
cognitiveTasks = [{task_values}]
contextFamily = "{family}-context"
contextRelation = "{performance['contextRelation']}"
aidPolicy = "{performance['aidPolicy']}"
estimatedMinutes = 25
rationaleRequired = {str(performance['rationaleRequired']).lower()}
variantFamilyId = "{family}"
rationalePrompt = "Defend the design and verification strategy."

[generator]
mode = "hybrid-ai-verified"
minimumBlueprints = {policy.minimum_blueprints}
minimumVerifiedVariants = {policy.minimum_verified_variants}
variationAxes = [{axis_values}]
newVariantOnRetry = true
''', encoding="utf-8")
        for number in range(1, policy.minimum_blueprints + 1):
            value = blueprint(number, axes, performance["capabilityIds"])
            (family_root / "blueprints" / f"blueprint-{number}.json").write_text(
                json.dumps(value), encoding="utf-8")
        paths.append(lab_path)
    return paths


def semantic_report(contract: dict) -> dict:
    return {
        "version": 1, "reviewMode": "semantic-congruence",
        "capabilities": [{"id": capability,
                          "evidence": [f"lesson and required activity for {capability}"],
                          "judgment": "congruent"}
                         for capability in contract["capabilityIds"]],
        "performances": [{"id": row["id"], "nodeId": row["nodeId"],
                          "evidence": [f"public requirements and executable proof at {row['nodeId']}"],
                          "judgment": "congruent"}
                         for row in contract["performances"]],
        "findings": [], "unresolvedFindings": [],
        "independenceJudgment": (
            "The visible path teaches each declared capability, then withholds the canonical "
            "implementation while the learner builds and verifies every late performance."),
        "summary": "Every sealed capability and performance is load-bearing.",
    }
