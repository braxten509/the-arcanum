"""Phase-8 semantic congruence review receipt and mechanical coverage gate."""
from __future__ import annotations

import json
import os
import tomllib

from arcanum_core.contracts.mastery import MasteryEvidenceContract


def review_path(build_dir: str, build_id: str) -> str:
    return os.path.join(build_dir, f"{build_id}.mastery-semantic-review.json")


def _contract(tome_root: str) -> MasteryEvidenceContract | None:
    with open(os.path.join(tome_root, "tome.toml"), "rb") as handle:
        manifest = tomllib.load(handle)
    if not isinstance(manifest.get("mastery"), dict):
        return None
    with open(os.path.join(tome_root, "generated", "mastery-evidence.json"),
              encoding="utf-8") as handle:
        return MasteryEvidenceContract.from_dict(json.load(handle))


def validate_semantic_review(build_dir: str, build_id: str,
                             tome_root: str) -> tuple[bool, str]:
    try:
        contract = _contract(tome_root)
    except (OSError, json.JSONDecodeError, tomllib.TOMLDecodeError, ValueError) as exc:
        return False, f"cannot load the shipped mastery contract for semantic review: {exc}"
    if contract is None:
        return True, "legacy tome has no mastery semantic-review obligation"
    try:
        with open(review_path(build_dir, build_id), encoding="utf-8") as handle:
            report = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return False, "Phase 8 mastery semantic-review evidence is missing or malformed"
    expected = {"version", "reviewMode", "capabilities", "performances", "findings",
                "unresolvedFindings", "independenceJudgment", "summary"}
    if not isinstance(report, dict) or set(report) != expected:
        return False, "semantic-review evidence must contain exactly the required keys"
    if report.get("version") != 1 or report.get("reviewMode") != "semantic-congruence":
        return False, "semantic review must use version 1 and semantic-congruence mode"
    capability_ids = [row.get("id") for row in report.get("capabilities") or []
                      if isinstance(row, dict)]
    if capability_ids != list(contract.capability_ids):
        return False, "semantic review must cover every capability in sealed order"
    for row in report.get("capabilities") or []:
        if (set(row) != {"id", "evidence", "judgment"}
                or not isinstance(row.get("evidence"), list) or not row["evidence"]
                or row.get("judgment") != "congruent"):
            return False, f"capability {row.get('id')!r} lacks concrete congruent evidence"
    expected_performances = [(item.id, item.node_id) for item in contract.performances]
    actual_performances = [(row.get("id"), row.get("nodeId"))
                           for row in report.get("performances") or []
                           if isinstance(row, dict)]
    if actual_performances != expected_performances:
        return False, "semantic review must cover every sealed performance in order"
    for row in report.get("performances") or []:
        if (set(row) != {"id", "nodeId", "evidence", "judgment"}
                or not isinstance(row.get("evidence"), list) or not row["evidence"]
                or row.get("judgment") != "congruent"):
            return False, f"performance {row.get('id')!r} lacks concrete congruent evidence"
    if not isinstance(report.get("findings"), list):
        return False, "semantic review findings must be an array"
    for finding in report["findings"]:
        if (not isinstance(finding, dict)
                or set(finding) != {"location", "issue", "resolution"}
                or any(len(str(finding.get(key) or "").strip()) < 4
                       for key in ("location", "issue", "resolution"))):
            return False, "each semantic finding needs a location, issue, and repair"
    if report.get("unresolvedFindings") != []:
        return False, "unresolved semantic evidence findings block Phase 8"
    judgment = str(report.get("independenceJudgment") or "").strip()
    if len(judgment) < 40:
        return False, "independenceJudgment must answer whether a learner can build independently"
    if len(str(report.get("summary") or "").strip()) < 8:
        return False, "semantic review summary is missing"
    return True, "semantic review covers every capability and performance with no unresolved findings"
