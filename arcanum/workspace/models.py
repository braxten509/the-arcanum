"""Pure learner-workspace state predicates."""
from __future__ import annotations


def has_progress(state: object) -> bool:
    if not isinstance(state, dict):
        return False
    if state.get("earned") or state.get("credits"):
        return True
    return any(state.get(key) for key in (
        "ex", "read", "badges", "fs", "exerciseEvidence", "capabilityEvidence",
        "masteryLabs", "assessmentReceipts",
    ))
