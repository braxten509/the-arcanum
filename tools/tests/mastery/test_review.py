#!/usr/bin/env python3
"""Required Phase-8 semantic congruence receipt fixtures."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from tools.buildlib.mastery_evidence.review import review_path, validate_semantic_review


with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    build, tome = root / "build", root / "tome"
    build.mkdir(); (tome / "generated").mkdir(parents=True)
    (tome / "tome.toml").write_text('[mastery]\nevidenceVersion = 1\nlevel = 1\n')
    evidence = {
        "version": 1, "level": 1, "capabilityIds": ["language-data"],
        "foundationCapabilities": {"data": "language-data"},
        "cognitiveTasks": ["build"], "requiredPerformanceCount": 1,
        "standaloneLabCount": 0, "rationaleCount": 1,
        "performances": [{"id": "final-proof", "nodeId": "s01.working",
                          "kind": "guided-modification", "capabilityIds": ["language-data"],
                          "contextRelation": "project", "aidPolicy": "limited",
                          "rationaleRequired": True, "variantFamilyId": ""}],
        "retentionCapabilityIds": ["language-data"],
    }
    (tome / "generated" / "mastery-evidence.json").write_text(json.dumps(evidence))
    assert not validate_semantic_review(str(build), "demo", str(tome))[0]
    report = {
        "version": 1, "reviewMode": "semantic-congruence",
        "capabilities": [{"id": "language-data",
                          "evidence": ["sections/s01/lessons/l01.toml concept+exercise"],
                          "judgment": "congruent"}],
        "performances": [{"id": "final-proof", "nodeId": "s01.working",
                          "evidence": ["sections/s01/freestyle.toml requirement+assessment"],
                          "judgment": "congruent"}],
        "findings": [], "unresolvedFindings": [],
        "independenceJudgment": (
            "A learner following the visible path can build and verify the declared change "
            "independently without receiving the canonical implementation."),
        "summary": "All declared evidence is semantically load-bearing.",
    }
    Path(review_path(str(build), "demo")).write_text(json.dumps(report))
    clean, message = validate_semantic_review(str(build), "demo", str(tome))
    assert clean, message
    report["capabilities"][0]["judgment"] = "label-only"
    Path(review_path(str(build), "demo")).write_text(json.dumps(report))
    assert not validate_semantic_review(str(build), "demo", str(tome))[0]

print("mastery Phase-8 semantic review tests: OK")
