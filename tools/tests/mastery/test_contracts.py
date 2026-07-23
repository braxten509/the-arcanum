#!/usr/bin/env python3
"""Versioned mastery, assessment, and grading contract tests."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from arcanum_core.contracts.assessment import AssessmentContract
from arcanum_core.contracts.mastery import MasteryDeclaration, MasteryEvidenceContract
from arcanum_core.policies.grading import compose_grade


assert MasteryDeclaration.from_dict(None) is None
assert MasteryDeclaration.from_dict({"evidenceVersion": 1, "level": 3}).level == 3
assert MasteryDeclaration.from_dict({"evidenceVersion": 1, "sourceEvidenceVersion": 1,
                                    "level": 3}).source_evidence_version == 1

contract = MasteryEvidenceContract.from_dict({
    "version": 1, "level": 3,
    "capabilityIds": ["language-data", "language-verification"],
    "foundationCapabilities": {"data": "language-data", "verification": "language-verification"},
    "cognitiveTasks": ["debug", "test-design"],
    "requiredPerformanceCount": 1, "standaloneLabCount": 1, "rationaleCount": 1,
    "performances": [{
        "id": "performance-s03-lab", "nodeId": "s03.lab01", "kind": "novel-transfer",
        "capabilityIds": ["language-data"], "contextRelation": "unrelated",
        "aidPolicy": "cold", "rationaleRequired": True,
        "variantFamilyId": "s03-transfer-family",
    }],
    "retentionCapabilityIds": ["language-data"],
})
assert contract.level == 3 and contract.performances[0].aid_policy == "cold"

assessment = AssessmentContract.from_dict({
    "version": 1,
    "requirements": [{"id": "valid-output", "text": "Produces valid output.",
                      "essential": True, "capabilityIds": ["language-data"]}],
    "scenarios": [{"id": "valid-output-case", "kind": "run",
                   "requirementIds": ["valid-output"], "capabilityIds": ["language-data"],
                   "commandRef": "project-run", "args": [], "stdin": "sample\n",
                   "expect": {"regex": "sample"}, "timeout": 20, "public": False}],
    "rubric": [
        {"id": "behavior", "criterion": "Behavior", "weight": 70,
         "kind": "deterministic", "assessmentIds": ["valid-output-case"]},
        {"id": "design", "criterion": "Design", "weight": 30,
         "kind": "qualitative", "assessmentIds": []},
    ],
})
assert len(assessment.requirements) == 1
green = compose_grade(
    [vars(item) for item in assessment.rubric],
    [{"id": "behavior", "score": 10, "comment": "green"},
     {"id": "design", "score": 6, "comment": "clear"}], True)
assert green.total == 88 and green.grade == "B"
red = compose_grade(
    [vars(item) for item in assessment.rubric],
    [{"id": "behavior", "score": 10}, {"id": "design", "score": 10}], False)
assert red.total == 100 and red.grade == "INCOMPLETE"
print("mastery evidence contract/grading tests: OK")
