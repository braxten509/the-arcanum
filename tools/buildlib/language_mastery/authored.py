"""Authored-tome evidence checks for mapped language performances."""
from __future__ import annotations

def authored_mastery_problems(course, tome_path, through=None):
    """Require each mapped language performance to be visible in its Working rubric."""
    contract = course.get("languageMastery")
    if not isinstance(contract, dict):
        return []
    try:
        import tome_layout
    except ModuleNotFoundError:
        from tools import tome_layout
    selected = course.get("sections") or []
    ids = [section.get("id") for section in selected]
    if through in ids:
        selected = selected[:ids.index(through) + 1]
    by_working = {}
    for item in contract.get("performances") or []:
        if isinstance(item, dict):
            by_working.setdefault(item.get("workingId"), []).append(item)
    language_ids = {
        item.get("id") for records in by_working.values() for item in records
        if isinstance(item.get("id"), str)
    }
    problems = []
    for section in selected:
        sid = section.get("id")
        working = next((node for node in section.get("nodes") or []
                        if isinstance(node, dict) and node.get("kind") == "working"), {})
        expected = by_working.get(working.get("id"), [])
        try:
            actual = tome_layout.load_section(tome_path, sid)
        except Exception as exc:
            problems.append(f"{sid} cannot load for language-mastery evidence: {exc}")
            continue
        freestyle = actual.get("freestyle") or {}
        actual_ids = ([item for item in (freestyle.get("masteryPerformances") or [])
                       if item in language_ids]
                      if isinstance(freestyle, dict) else [])
        expected_ids = [item["id"] for item in expected]
        if actual_ids != expected_ids:
            problems.append(
                f"{working.get('id')}.masteryPerformances {actual_ids} do not match {expected_ids}")
        if not expected:
            continue
        rubrics = freestyle.get("rubric") if isinstance(freestyle, dict) else []
        rubrics = rubrics if isinstance(rubrics, list) else []
        for performance in expected:
            tagged = [row for row in rubrics if isinstance(row, dict)
                      and row.get("masteryPerformance") == performance["id"]]
            if not tagged:
                problems.append(
                    f"{working.get('id')} needs a rubric row tagged masteryPerformance = "
                    f"{performance['id']!r}")
                continue
            covered = {capability for row in tagged
                       for capability in (row.get("languageCapabilities") or [])
                       if isinstance(capability, str)}
            missing = sorted(set(performance.get("capabilityIds") or []) - covered)
            if missing:
                problems.append(
                    f"rubric evidence for {performance['id']} omits language capabilities: "
                    + ", ".join(missing))
            if performance.get("rationaleRequired") and not any(
                    row.get("rationaleRequired") is True for row in tagged):
                problems.append(
                    f"rubric evidence for {performance['id']} must set rationaleRequired = true")
    return problems
