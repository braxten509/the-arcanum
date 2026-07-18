"""Publish the sealed Phase-2 evidence contract for the learner runtime."""
from __future__ import annotations

import json
import os

from arcanum_core.contracts.mastery import MasteryEvidenceContract
from runtimes.common import atomic_write


def export_mastery_contract(course_map: dict, tome_root: str) -> str:
    evidence = course_map.get("masteryEvidence") if isinstance(course_map, dict) else None
    MasteryEvidenceContract.from_dict(evidence)
    target = os.path.join(tome_root, "generated", "mastery-evidence.json")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    atomic_write(target, json.dumps(evidence, ensure_ascii=False,
                                    indent=2, sort_keys=True) + "\n")
    return target
