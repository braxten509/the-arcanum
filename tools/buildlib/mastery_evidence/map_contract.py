"""Phase-1/2 mastery evidence obligations and map-node alignment."""
from __future__ import annotations

import math

from arcanum_core.contracts.mastery import (AID_POLICIES, COGNITIVE_TASKS,
                                             MasteryEvidenceContract,
                                             PERFORMANCE_KINDS)

from .policy import EvidencePolicy, load_policy

LAB_CHECKS = {"learner-evidence", "variant-proof"}


def _node_index(sections: list[dict]) -> tuple[dict[str, dict], dict[str, int]]:
    nodes, ordinals = {}, {}
    for ordinal, section in enumerate(sections, 1):
        if not isinstance(section, dict):
            continue
        section_ordinal = section.get("ordinal") if isinstance(section.get("ordinal"), int) else ordinal
        for node in section.get("nodes") or ():
            if isinstance(node, dict) and isinstance(node.get("id"), str):
                nodes[node["id"]] = node
                ordinals[node["id"]] = section_ordinal
    return nodes, ordinals


def _lab_problems(node: dict, performance, label: str) -> list[str]:
    problems = []
    expected = {
        "performanceKind": performance.kind,
        "capabilityIds": list(performance.capability_ids),
        "contextRelation": performance.context_relation,
        "aidPolicy": performance.aid_policy,
        "variantFamilyId": performance.variant_family_id,
        "rationaleRequired": performance.rationale_required,
    }
    for key, value in expected.items():
        if node.get(key) != value:
            problems.append(f"{label}.{key} must match performance {performance.id!r}")
    tasks = node.get("cognitiveTasks")
    if not isinstance(tasks, list) or not tasks:
        problems.append(f"{label}.cognitiveTasks must be a non-empty array")
    elif any(item not in COGNITIVE_TASKS for item in tasks):
        problems.append(f"{label}.cognitiveTasks contains an unsupported task")
    checks = set((node.get("doneWhen") or {}).get("checks") or ())
    if checks != LAB_CHECKS:
        problems.append(f"{label}.doneWhen.checks must be exactly {sorted(LAB_CHECKS)}")
    dependencies = node.get("validationDependencies")
    if not isinstance(dependencies, list) or any(not isinstance(item, str) for item in dependencies):
        problems.append(f"{label}.validationDependencies must be an array of strings")
    return problems


def validate_map_contract(value: object, sections: list[dict], *, detailed: bool = True,
                          seed: object = None, policy: EvidencePolicy | None = None) -> list[str]:
    """Validate central floors, late evidence, and mastery-lab node alignment."""
    if value is None:
        return []
    try:
        contract = MasteryEvidenceContract.from_dict(value)
    except ValueError as exc:
        return [str(exc)]
    policy = policy or load_policy()
    row = policy.for_level(contract.level)
    problems = []
    if len(contract.capability_ids) < row.capability_floor:
        problems.append(
            f"Mastery {contract.level} needs at least {row.capability_floor} capabilities; "
            f"found {len(contract.capability_ids)}")
    foundations = dict(contract.foundation_capabilities)
    missing_roles = sorted(set(row.foundation_roles) - set(foundations))
    if missing_roles:
        problems.append("masteryEvidence foundation mapping is missing: " + ", ".join(missing_roles))
    missing_tasks = sorted(set(row.cognitive_tasks) - set(contract.cognitive_tasks))
    if missing_tasks:
        problems.append("masteryEvidence cognitive tasks are missing: " + ", ".join(missing_tasks))
    declared_floors = (
        ("requiredPerformanceCount", contract.required_performance_count, row.late_performances),
        ("standaloneLabCount", contract.standalone_lab_count, row.standalone_labs),
        ("rationaleCount", contract.rationale_count, row.rationales),
    )
    for label, actual, floor in declared_floors:
        if actual < floor:
            problems.append(f"masteryEvidence.{label} cannot be below central floor {floor}")
    performances = contract.performances
    if len(performances) < contract.required_performance_count:
        problems.append("masteryEvidence has fewer performances than requiredPerformanceCount")
    lab_performances = [item for item in performances if ".lab" in item.node_id]
    rationale_count = sum(item.rationale_required for item in performances)
    if len(lab_performances) < contract.standalone_lab_count:
        problems.append("masteryEvidence has fewer mastery labs than standaloneLabCount")
    if rationale_count < contract.rationale_count:
        problems.append("masteryEvidence has fewer rationales than rationaleCount")
    if len({item.id for item in performances}) != len(performances):
        problems.append("masteryEvidence performance IDs contain duplicates")
    if len({item.node_id for item in performances}) != len(performances):
        problems.append("each mastery evidence performance must use a distinct node")
    minimum_rank = PERFORMANCE_KINDS[row.minimum_kind]
    for item in performances:
        if PERFORMANCE_KINDS[item.kind] < minimum_rank:
            problems.append(
                f"performance {item.id!r} kind {item.kind!r} is below Mastery {contract.level}")
        if contract.level >= 2 and item.aid_policy not in {"documentation-only", "cold"}:
            problems.append(f"performance {item.id!r} must be documentation-only or cold")
        if item.aid_policy not in AID_POLICIES:
            problems.append(f"performance {item.id!r} has an unsupported aid policy")
    relation_set = {item.context_relation for item in performances}
    missing_relations = sorted(set(row.context_relations) - relation_set)
    if missing_relations:
        problems.append("masteryEvidence context relations are missing: " + ", ".join(missing_relations))
    required_coverage = (set(contract.capability_ids) if contract.level >= 3
                         else set(foundations.values()))
    assessed = {capability for item in performances for capability in item.capability_ids}
    if required_coverage - assessed:
        problems.append("late evidence union misses capabilities: "
                        + ", ".join(sorted(required_coverage - assessed)))
    if required_coverage - set(contract.retention_capability_ids):
        problems.append("retention obligations miss capabilities: "
                        + ", ".join(sorted(required_coverage - set(contract.retention_capability_ids))))
    nodes, ordinals = _node_index(sections)
    section_count = len([section for section in sections if isinstance(section, dict)])
    section_ordinals = {
        str(section.get("id")): int(section.get("ordinal") or index)
        for index, section in enumerate(sections, 1) if isinstance(section, dict)
    }
    late_start = math.floor(2 * section_count / 3) + 1 if section_count else 1
    final_section = next((section for section in reversed(sections) if isinstance(section, dict)), {})
    final_working = f"{final_section.get('id')}.working" if final_section.get("id") else ""
    if not any(item.node_id == final_working for item in performances):
        problems.append("the final Working must contain a mastery evidence performance")
    for item in performances:
        node = nodes.get(item.node_id)
        sid = item.node_id.split(".", 1)[0]
        if sid not in section_ordinals:
            problems.append(f"performance {item.id!r} names unknown section {sid!r}")
        if detailed and node is None:
            problems.append(f"performance {item.id!r} names missing node {item.node_id!r}")
            continue
        if ordinals.get(item.node_id, section_ordinals.get(sid, late_start)) < late_start:
            problems.append(f"performance {item.id!r} must be in the late course window")
        if not detailed or node is None:
            continue
        if ".lab" in item.node_id:
            if node.get("kind") != "mastery-lab":
                problems.append(f"{item.node_id} must be a mastery-lab node")
            else:
                problems += _lab_problems(node, item, item.node_id)
        else:
            if node.get("kind") != "working":
                problems.append(f"{item.node_id} must be a Working node")
            if item.id not in (node.get("masteryPerformances") or []):
                problems.append(f"{item.node_id}.masteryPerformances must include {item.id!r}")
    if seed is not None:
        try:
            seeded = MasteryEvidenceContract.from_dict(seed)
        except ValueError:
            problems.append("seed masteryEvidence contract is missing or invalid")
        else:
            if contract != seeded:
                problems.append("Phase 2 may not alter the seeded masteryEvidence contract")
    return problems
