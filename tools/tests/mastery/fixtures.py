"""Synthetic future-course contracts for all five mastery levels."""
from __future__ import annotations

from tools.buildlib.mastery_evidence import load_policy


def future_map(level: int) -> tuple[dict, list[dict]]:
    row = load_policy().for_level(level)
    capabilities = [f"capability-{index:02d}" for index in range(1, row.capability_floor + 1)]
    foundations = {role: capabilities[index] for index, role in enumerate(row.foundation_roles)}
    sections = []
    for ordinal in range(1, 10):
        sid = f"s{ordinal:02d}"
        sections.append({
            "id": sid, "ordinal": ordinal,
            "nodes": [{"id": f"{sid}.working", "kind": "working",
                       "masteryPerformances": []}],
        })
    nodes = []
    if level == 1:
        nodes = [("s09.working", "guided-modification", "project", "limited")]
    elif level == 2:
        nodes = [("s08.lab01", "familiar-independent-task", "different", "cold"),
                 ("s09.working", "familiar-independent-task", "project", "cold")]
    elif level == 3:
        nodes = [("s08.lab01", "novel-transfer", "unrelated", "cold"),
                 ("s09.working", "novel-transfer", "project", "cold")]
    elif level == 4:
        nodes = [("s07.lab01", "unfamiliar-tradeoff", "unrelated", "documentation-only"),
                 ("s08.lab01", "unfamiliar-tradeoff", "unfamiliar", "cold"),
                 ("s09.working", "unfamiliar-tradeoff", "project", "cold")]
    else:
        nodes = [("s07.lab01", "architecture-defense", "unrelated", "documentation-only"),
                 ("s08.lab01", "architecture-defense", "unfamiliar", "cold"),
                 ("s09.working", "architecture-defense", "project", "cold")]
    chunks = [capabilities[index::len(nodes)] for index in range(len(nodes))]
    performances = []
    rationale_from = max(0, len(nodes) - row.rationales)
    for index, ((node_id, kind, relation, aid), cited) in enumerate(zip(nodes, chunks), 1):
        performance_id = f"evidence-performance-{level}-{index}"
        family = f"mastery-{level}-family-{index}" if ".lab" in node_id else ""
        rationale = index - 1 >= rationale_from
        performances.append({
            "id": performance_id, "nodeId": node_id, "kind": kind,
            "capabilityIds": cited, "contextRelation": relation, "aidPolicy": aid,
            "rationaleRequired": rationale, "variantFamilyId": family,
        })
        sid = node_id.split(".", 1)[0]
        section = next(item for item in sections if item["id"] == sid)
        if ".lab" in node_id:
            section["nodes"].insert(0, {
                "id": node_id, "kind": "mastery-lab", "title": "Synthetic transfer",
                "performanceKind": kind, "capabilityIds": cited,
                "cognitiveTasks": list(row.cognitive_tasks), "contextRelation": relation,
                "aidPolicy": aid, "variantFamilyId": family,
                "rationaleRequired": rationale, "validationDependencies": [],
                "doneWhen": {"checks": ["learner-evidence", "variant-proof"]},
            })
        else:
            section["nodes"][-1]["masteryPerformances"].append(performance_id)
    contract = {
        "version": 1, "level": level, "capabilityIds": capabilities,
        "foundationCapabilities": foundations,
        "cognitiveTasks": list(row.cognitive_tasks),
        "requiredPerformanceCount": row.late_performances,
        "standaloneLabCount": row.standalone_labs,
        "rationaleCount": row.rationales,
        "performances": performances,
        "retentionCapabilityIds": capabilities if level >= 3 else list(foundations.values()),
    }
    return contract, sections
