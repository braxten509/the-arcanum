"""Learner evidence and immutable receipt DTOs."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class ExerciseEvidence:
    attempts: int = 0
    resolved: bool = False
    support_used: bool = False
    support_kinds: tuple[str, ...] = ()
    independent: bool | None = False
    retained: bool = False
    capability_ids: tuple[str, ...] = ()
    last_variant_id: str = ""

    def to_dict(self) -> dict:
        value = asdict(self)
        value["supportKinds"] = list(value.pop("support_kinds"))
        value["supportUsed"] = value.pop("support_used")
        value["capabilityIds"] = list(value.pop("capability_ids"))
        value["lastVariantId"] = value.pop("last_variant_id")
        return value


@dataclass(frozen=True)
class EvidenceReceipt:
    version: int
    tome_id: str
    mastery_level: int
    node_id: str
    performance_id: str
    workspace_hash: str
    contract_hash: str
    variant_id: str
    variant_hash: str
    aid_policy: str
    support_used: bool
    deterministic: tuple[dict, ...]
    qualitative_scores: tuple[dict, ...]
    weighted_total: int
    grade: str
    essential_passed: bool
    independent: bool
    capability_ids: tuple[str, ...]
    created_at: str
    receipt_hash: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "version": self.version, "tomeId": self.tome_id,
            "masteryLevel": self.mastery_level, "nodeId": self.node_id,
            "performanceId": self.performance_id, "workspaceHash": self.workspace_hash,
            "contractHash": self.contract_hash, "variantId": self.variant_id,
            "variantHash": self.variant_hash, "aidPolicy": self.aid_policy,
            "supportUsed": self.support_used, "scenarios": list(self.deterministic),
            "qualitativeScores": list(self.qualitative_scores),
            "weightedTotal": self.weighted_total, "grade": self.grade,
            "essentialPassed": self.essential_passed, "independent": self.independent,
            "capabilityIds": list(self.capability_ids), "createdAt": self.created_at,
            "receiptHash": self.receipt_hash, "metadata": dict(self.metadata),
        }
