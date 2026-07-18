"""Course-map helpers that do not know authoring storage or repository paths."""
from __future__ import annotations

from .mastery import MasteryEvidenceContract


def mastery_contract(value: object) -> MasteryEvidenceContract | None:
    if not isinstance(value, dict):
        raise ValueError("course map must be an object")
    raw = value.get("masteryEvidence")
    return None if raw is None else MasteryEvidenceContract.from_dict(raw)
