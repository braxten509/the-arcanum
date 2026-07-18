"""Load shipped evidence descriptors and authored lab metadata."""
from __future__ import annotations

import glob
import json
import os
import tomllib

from arcanum_core.contracts.mastery import MasteryEvidenceContract, PerformanceObligation


def load_mastery_contract(tome_root: str) -> MasteryEvidenceContract:
    path = os.path.join(tome_root, "generated", "mastery-evidence.json")
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            "this evidence tome has no valid generated/mastery-evidence.json; "
            "finish the Phase 7 evidence export") from exc
    if isinstance(value, dict) and "masteryEvidence" in value:
        value = value["masteryEvidence"]
    return MasteryEvidenceContract.from_dict(value)


def performance_for(tome_root: str, node_id: str) -> tuple[
        MasteryEvidenceContract, PerformanceObligation]:
    contract = load_mastery_contract(tome_root)
    matches = [row for row in contract.performances if row.node_id == node_id]
    if len(matches) != 1:
        raise ValueError(f"node {node_id!r} is not one sealed mastery performance")
    return contract, matches[0]


def working_performance(tome_root: str, section_id: str,
                        capability_ids: tuple[str, ...]) -> tuple[
                            MasteryEvidenceContract, PerformanceObligation]:
    """Resolve a chapter Working without widening the sealed mastery claim.

    Every Working in an evidence-version tome is deterministically assessed for the
    chapter B gate.  Only the late Workings named by the sealed evidence contract are
    mastery performances, though.  Earlier Workings receive a stable formative receipt
    that can populate the capability ledger without becoming a required mastery seal.
    """
    contract = load_mastery_contract(tome_root)
    node_id = f"{section_id}.working"
    matches = [row for row in contract.performances if row.node_id == node_id]
    if len(matches) > 1:
        raise ValueError(f"node {node_id!r} names more than one sealed mastery performance")
    if matches:
        return contract, matches[0]
    known = tuple(dict.fromkeys(
        capability_id for capability_id in capability_ids
        if capability_id in contract.capability_ids))
    if not known:
        raise ValueError(
            f"chapter Working {node_id!r} must assess at least one declared capability")
    performance_id = f"chapter-working-{section_id}"
    if any(row.id == performance_id for row in contract.performances):
        raise ValueError(
            f"formative Working id {performance_id!r} collides with a sealed performance")
    return contract, PerformanceObligation(
        performance_id, node_id, "guided-modification", known, "project",
        "learning", False, "")


def authored_lab(tome_root: str, node_id: str) -> tuple[str, dict]:
    matches = []
    pattern = os.path.join(tome_root, "sections", "*", "mastery-labs", "*.toml")
    for path in sorted(glob.glob(pattern)):
        try:
            with open(path, "rb") as handle:
                value = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError):
            continue
        if (value.get("masteryLab") or {}).get("nodeId") == node_id:
            matches.append((path, value))
    if len(matches) != 1:
        raise ValueError(f"node {node_id!r} does not name one authored mastery lab")
    return matches[0]


def load_variant_assessment(variant_root: str):
    from arcanum_core.contracts.assessment import AssessmentContract

    path = os.path.join(variant_root, "hidden", "assessment.json")
    with open(path, encoding="utf-8") as handle:
        return AssessmentContract.from_dict(json.load(handle))
