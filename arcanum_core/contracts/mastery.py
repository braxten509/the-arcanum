"""Language-neutral mastery declarations and authored-map evidence contracts."""
from __future__ import annotations

from dataclasses import dataclass

from ..ids import is_capability_id, is_node_id, is_stable_id

EVIDENCE_VERSION = 1
COGNITIVE_TASKS = frozenset({
    "recall", "recognize", "predict", "trace", "explain", "complete", "modify",
    "debug", "test-design", "build", "integrate", "refactor", "profile",
    "evaluate-tradeoff", "design-defense",
})
SCAFFOLDS = frozenset({"worked", "completion", "guided", "independent", "cold"})
AID_POLICIES = frozenset({"learning", "limited", "documentation-only", "cold"})
PERFORMANCE_KINDS = {
    "guided-modification": 1,
    "familiar-independent-task": 2,
    "novel-transfer": 3,
    "unfamiliar-tradeoff": 4,
    "architecture-defense": 5,
}
EVIDENCE_SOURCES = frozenset({
    "lesson-retrieval", "ordinary-code-exercise", "cumulative-project-working",
    "standalone-mastery-lab", "cold-project-change", "debugging-diagnosis",
    "test-design", "rationale-design-defense", "delayed-varied-retrieval",
})


def _integer(value: object, label: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be a whole number from {minimum} through {maximum}")
    return value


def _strings(value: object, label: str, *, allowed=None, minimum: int = 0) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) < minimum:
        raise ValueError(f"{label} must be an array with at least {minimum} item(s)")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{label} entries must be non-empty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{label} must not contain duplicates")
    if allowed is not None and any(item not in allowed for item in value):
        raise ValueError(f"{label} contains an unsupported value")
    return tuple(value)


@dataclass(frozen=True)
class MasteryDeclaration:
    evidence_version: int
    level: int
    source_evidence_version: int | None = None

    @classmethod
    def from_dict(cls, value: object) -> "MasteryDeclaration | None":
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("mastery must be an object")
        extra = set(value) - {"evidenceVersion", "sourceEvidenceVersion", "level"}
        if extra:
            raise ValueError("mastery has unknown keys: " + ", ".join(sorted(extra)))
        version = _integer(value.get("evidenceVersion"), "mastery.evidenceVersion", 1, 1)
        level = _integer(value.get("level"), "mastery.level", 1, 5)
        source = value.get("sourceEvidenceVersion")
        if source is not None:
            source = _integer(source, "mastery.sourceEvidenceVersion", 1, 1)
        return cls(version, level, source)


@dataclass(frozen=True)
class PerformanceObligation:
    id: str
    node_id: str
    kind: str
    capability_ids: tuple[str, ...]
    context_relation: str
    aid_policy: str
    rationale_required: bool
    variant_family_id: str

    @classmethod
    def from_dict(cls, value: object, label: str) -> "PerformanceObligation":
        if not isinstance(value, dict):
            raise ValueError(f"{label} must be an object")
        expected = {"id", "nodeId", "kind", "capabilityIds", "contextRelation",
                    "aidPolicy", "rationaleRequired", "variantFamilyId"}
        if set(value) != expected:
            raise ValueError(f"{label} keys must be exactly {sorted(expected)}")
        if not is_stable_id(value.get("id")):
            raise ValueError(f"{label}.id must be stable")
        if not is_node_id(value.get("nodeId")):
            raise ValueError(f"{label}.nodeId must name a lesson, Working, or mastery lab")
        if value.get("kind") not in PERFORMANCE_KINDS:
            raise ValueError(f"{label}.kind is unsupported")
        capabilities = _strings(value.get("capabilityIds"), f"{label}.capabilityIds", minimum=1)
        if any(not is_capability_id(item) for item in capabilities):
            raise ValueError(f"{label}.capabilityIds must be stable capability ids")
        if value.get("aidPolicy") not in AID_POLICIES:
            raise ValueError(f"{label}.aidPolicy is unsupported")
        if not isinstance(value.get("rationaleRequired"), bool):
            raise ValueError(f"{label}.rationaleRequired must be boolean")
        relation = value.get("contextRelation")
        if relation not in {"project", "different", "unrelated", "unfamiliar"}:
            raise ValueError(f"{label}.contextRelation is unsupported")
        family = value.get("variantFamilyId")
        if family and not is_stable_id(family):
            raise ValueError(f"{label}.variantFamilyId must be empty or stable")
        if ".lab" in value["nodeId"] and not family:
            raise ValueError(f"{label}.variantFamilyId is required for mastery labs")
        if not isinstance(family, str):
            raise ValueError(f"{label}.variantFamilyId must be a string")
        return cls(value["id"], value["nodeId"], value["kind"], capabilities,
                   relation, value["aidPolicy"], value["rationaleRequired"], family)


@dataclass(frozen=True)
class MasteryEvidenceContract:
    version: int
    level: int
    capability_ids: tuple[str, ...]
    foundation_capabilities: tuple[tuple[str, str], ...]
    cognitive_tasks: tuple[str, ...]
    required_performance_count: int
    standalone_lab_count: int
    rationale_count: int
    performances: tuple[PerformanceObligation, ...]
    retention_capability_ids: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: object) -> "MasteryEvidenceContract":
        if not isinstance(value, dict):
            raise ValueError("masteryEvidence must be an object")
        expected = {"version", "level", "capabilityIds", "foundationCapabilities",
                    "cognitiveTasks", "requiredPerformanceCount", "standaloneLabCount",
                    "rationaleCount", "performances", "retentionCapabilityIds"}
        if set(value) != expected:
            raise ValueError(f"masteryEvidence keys must be exactly {sorted(expected)}")
        version = _integer(value.get("version"), "masteryEvidence.version", 1, 1)
        level = _integer(value.get("level"), "masteryEvidence.level", 1, 5)
        capabilities = _strings(value.get("capabilityIds"), "masteryEvidence.capabilityIds", minimum=1)
        if any(not is_capability_id(item) for item in capabilities):
            raise ValueError("masteryEvidence.capabilityIds must be stable capability ids")
        raw_foundations = value.get("foundationCapabilities")
        if not isinstance(raw_foundations, dict) or not raw_foundations:
            raise ValueError("masteryEvidence.foundationCapabilities must be a non-empty object")
        if any(not is_stable_id(role) or capability not in capabilities
               for role, capability in raw_foundations.items()):
            raise ValueError("foundationCapabilities must map stable roles into the capability spine")
        foundations = tuple(sorted(raw_foundations.items()))
        tasks = _strings(value.get("cognitiveTasks"), "masteryEvidence.cognitiveTasks",
                         allowed=COGNITIVE_TASKS, minimum=1)
        counts = []
        for key in ("requiredPerformanceCount", "standaloneLabCount", "rationaleCount"):
            raw = value.get(key)
            if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
                raise ValueError(f"masteryEvidence.{key} must be a non-negative integer")
            counts.append(raw)
        raw_performances = value.get("performances")
        if not isinstance(raw_performances, list):
            raise ValueError("masteryEvidence.performances must be an array")
        performances = tuple(PerformanceObligation.from_dict(item, f"performances[{index}]")
                             for index, item in enumerate(raw_performances))
        retention = _strings(value.get("retentionCapabilityIds"),
                             "masteryEvidence.retentionCapabilityIds", minimum=0)
        if set(retention) - set(capabilities):
            raise ValueError("retentionCapabilityIds must be inside the capability spine")
        return cls(version, level, capabilities, foundations, tasks,
                   counts[0], counts[1], counts[2], performances, retention)
