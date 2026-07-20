"""Shared ownership for Working-level mastery performance identifiers.

Language mastery and the central mastery-evidence policy may both assign a
performance to the same Working.  The Working owns one ordered, duplicate-free
union so independent validators cannot give the field contradictory meanings.
"""
from __future__ import annotations


def expected_working_performances(course_map: object) -> dict[str, list[str]]:
    """Return language IDs followed by central evidence IDs for each Working."""
    if not isinstance(course_map, dict):
        return {}
    expected: dict[str, list[str]] = {}

    def add(records: object, node_key: str) -> None:
        if not isinstance(records, list):
            return
        for record in records:
            if not isinstance(record, dict):
                continue
            node_id, performance_id = record.get(node_key), record.get("id")
            if not (isinstance(node_id, str) and node_id.endswith(".working")
                    and isinstance(performance_id, str) and performance_id):
                continue
            values = expected.setdefault(node_id, [])
            if performance_id not in values:
                values.append(performance_id)

    language = course_map.get("languageMastery")
    if isinstance(language, dict):
        add(language.get("performances"), "workingId")
    evidence = course_map.get("masteryEvidence")
    if isinstance(evidence, dict):
        add(evidence.get("performances"), "nodeId")
    return expected
