"""Language-neutral teach-before-use contracts for sealed course maps and authored TOML.

A capability describes what the learner can do.  A mechanism is the concrete
syntax, API, tool, operator, keyword, or technical term they must use to do it.
Keeping those ledgers separate prevents an author from satisfying a broad
capability while silently requiring an unintroduced language construct.
"""
from __future__ import annotations

import copy
import re


CONTRACT_KEYS = {"version", "coverageStart", "mechanisms"}
MECHANISM_KEYS = {"id", "label", "kind", "owner"}
ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def seed_contract(section_ids):
    return {"version": 1,
            "coverageStart": section_ids[0] if section_ids else "s01",
            "mechanisms": []}


def upgrade_map(value, prior_version):
    """Mechanically make an older map v4-shaped during an audited amendment."""
    if int(prior_version or 0) >= 4:
        return
    sections = value.get("sections") or []
    ids = [section.get("id") for section in sections if isinstance(section, dict)]
    value["mechanismContract"] = seed_contract(ids)
    for section in sections:
        for node in section.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            node["introduces" if node.get("kind") == "lesson" else "mechanisms"] = []


def validate_map_contract(value, sections, positions, *, detailed, map_version):
    if map_version < 4:
        return []
    problems = []
    contract = value.get("mechanismContract")
    if not isinstance(contract, dict):
        return ["mechanismContract must be an object in course-map v4"]
    missing = CONTRACT_KEYS - set(contract)
    extra = set(contract) - CONTRACT_KEYS
    if missing:
        problems.append("mechanismContract is missing keys: " + ", ".join(sorted(missing)))
    if extra:
        problems.append("mechanismContract has unknown keys: " + ", ".join(sorted(extra)))
    if contract.get("version") != 1:
        problems.append("mechanismContract.version must be 1")
    section_ids = [section.get("id") for section in sections if isinstance(section, dict)]
    coverage = contract.get("coverageStart")
    if coverage not in section_ids:
        problems.append("mechanismContract.coverageStart must name a sealed section")
    records = contract.get("mechanisms")
    if not isinstance(records, list):
        return problems + ["mechanismContract.mechanisms must be an array"]
    owners, records_by_id = {}, {}
    for index, record in enumerate(records):
        label = f"mechanismContract.mechanisms[{index}]"
        if not isinstance(record, dict):
            problems.append(f"{label} must be an object")
            continue
        if set(record) != MECHANISM_KEYS:
            problems.append(f"{label} keys must be exactly {sorted(MECHANISM_KEYS)}")
        mid = record.get("id")
        if not ID_RE.fullmatch(str(mid or "")):
            problems.append(f"{label}.id must be a stable kebab id")
        elif mid in records_by_id:
            problems.append(f"mechanism {mid!r} has multiple records")
        records_by_id[mid] = record
        for key in ("label", "kind"):
            text = record.get(key)
            if not isinstance(text, str) or not text.strip():
                problems.append(f"{label}.{key} must be a non-empty string")
        if not ID_RE.fullmatch(str(record.get("kind") or "")):
            problems.append(f"{label}.kind must be a language-neutral kebab category")
        owner = record.get("owner")
        if owner not in positions or ".l" not in str(owner):
            problems.append(f"{label}.owner must name a sealed lesson node")
        owners[mid] = owner

    introduced = {}
    coverage_index = section_ids.index(coverage) if coverage in section_ids else 0
    for section_index, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        enforced = detailed and section_index >= coverage_index
        for node in section.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            nid = node.get("id")
            field = "introduces" if node.get("kind") == "lesson" else "mechanisms"
            values = node.get(field)
            if not isinstance(values, list):
                if enforced:
                    problems.append(f"{nid}.{field} must be an array")
                continue
            if len(values) != len(set(item for item in values if isinstance(item, str))):
                problems.append(f"{nid}.{field} contains duplicates")
            for mid in values:
                if mid not in records_by_id:
                    problems.append(f"{nid}.{field} names unknown mechanism {mid!r}")
                    continue
                if node.get("kind") == "lesson":
                    if mid in introduced:
                        problems.append(f"mechanism {mid!r} has multiple introduction owners")
                    introduced[mid] = nid
                else:
                    owner = owners.get(mid)
                    if owner in positions and nid in positions and positions[owner] > positions[nid]:
                        problems.append(f"{nid} requires mechanism {mid!r} before {owner} introduces it")
    for mid, owner in owners.items():
        if introduced.get(mid) != owner:
            problems.append(
                f"mechanism {mid!r} owner {owner!r} must exactly match one lesson introduces entry")
    return problems


def _ids(value, where, problems, *, required=True):
    values = value.get("mechanisms") if isinstance(value, dict) else None
    if not isinstance(values, list):
        if required:
            problems.append(f"{where}.mechanisms must be an array, even when empty")
        return []
    if any(not isinstance(item, str) or not item for item in values):
        problems.append(f"{where}.mechanisms must contain only non-empty ids")
    if len(values) != len(set(item for item in values if isinstance(item, str))):
        problems.append(f"{where}.mechanisms contains duplicates")
    return [item for item in values if isinstance(item, str)]


def authored_problems(course, actual, sid):
    """Validate demand declarations and ordering for one loaded authored section."""
    if int(course.get("version") or 0) < 4:
        return []
    contract = course.get("mechanismContract") or {}
    section_ids = [section.get("id") for section in course.get("sections") or []]
    coverage = contract.get("coverageStart")
    if sid not in section_ids or coverage not in section_ids:
        return [f"{sid}: cannot resolve mechanism-contract coverage"]
    if section_ids.index(sid) < section_ids.index(coverage):
        return []
    records = {item.get("id"): item for item in contract.get("mechanisms") or []
               if isinstance(item, dict)}
    positions = {}
    for sindex, section in enumerate(course.get("sections") or []):
        for nindex, node in enumerate(section.get("nodes") or []):
            if isinstance(node, dict):
                positions[node.get("id")] = (sindex, nindex)
    planned = next(section for section in course["sections"] if section.get("id") == sid)
    planned_lessons = [node for node in planned.get("nodes") or []
                       if node.get("kind") == "lesson"]
    actual_lessons = [lesson for lesson in actual.get("lessons") or []
                      if isinstance(lesson, dict)]
    problems = []
    for node, lesson in zip(planned_lessons, actual_lessons):
        introduced = lesson.get("introduces")
        if list(introduced or []) != list(node.get("introduces") or []):
            problems.append(f"{node['id']} introduces drifted from the sealed mechanism contract")
        allowed_at_lesson = {mid for mid, record in records.items()
                             if positions.get(record.get("owner"), (999, 999))
                             <= positions.get(node.get("id"), (-1, -1))}
        for index, exercise in enumerate(lesson.get("exercises") or []):
            used = _ids(exercise, f"{node['id']}.exercises[{index}]", problems)
            unknown = set(used) - allowed_at_lesson
            if unknown:
                problems.append(f"{node['id']}.exercises[{index}] uses unintroduced mechanisms {sorted(unknown)}")
        for index, step in enumerate(lesson.get("artifactSteps") or []):
            used = _ids(step, f"{node['id']}.artifactSteps[{index}]", problems)
            unknown = set(used) - allowed_at_lesson
            if unknown:
                problems.append(f"{node['id']}.artifactSteps[{index}] uses unintroduced mechanisms {sorted(unknown)}")

    working = next(node for node in planned.get("nodes") or [] if node.get("kind") == "working")
    freestyle = actual.get("freestyle") or {}
    declared = _ids(freestyle, f"{sid}.working", problems)
    if declared != list(working.get("mechanisms") or []):
        problems.append(f"{sid}.working mechanisms drifted from the sealed mechanism contract")
    allowed_working = {mid for mid, record in records.items()
                       if positions.get(record.get("owner"), (999, 999))
                       <= positions.get(working.get("id"), (-1, -1))}
    declared_set, demand_union = set(declared), set()
    for index, rubric in enumerate(freestyle.get("rubric") or []):
        used = _ids(rubric, f"{sid}.working.rubric[{index}]", problems)
        demand_union.update(used)
        if set(used) - allowed_working:
            problems.append(f"{sid}.working.rubric[{index}] uses unintroduced mechanisms")
        if set(used) - declared_set:
            problems.append(f"{sid}.working.rubric[{index}] uses mechanisms absent from its Working")
    for index, step in enumerate(freestyle.get("referenceSteps") or []):
        used = _ids(step, f"{sid}.working.referenceSteps[{index}]", problems)
        demand_union.update(used)
        if set(used) - allowed_working:
            problems.append(f"{sid}.working.referenceSteps[{index}] uses unintroduced mechanisms")
        if set(used) - declared_set:
            problems.append(
                f"{sid}.working.referenceSteps[{index}] uses mechanisms absent from its Working")
    proof_used = _ids(actual.get("proof") or {}, f"{sid}.proof", problems)
    demand_union.update(proof_used)
    if set(proof_used) - allowed_working:
        problems.append(f"{sid}.proof uses unintroduced mechanisms")
    if set(proof_used) - declared_set:
        problems.append(f"{sid}.proof uses mechanisms absent from its Working")
    if demand_union != declared_set:
        problems.append(
            f"{sid}.working mechanisms must exactly equal the union declared by its rubrics, "
            f"proof, and hidden replay; missing={sorted(declared_set - demand_union)}, "
            f"extra={sorted(demand_union - declared_set)}")
    return problems


def candidate_with_findings(course, sid, findings):
    """Return a complete candidate for the existing audited amendment path.

    Findings are intentionally narrow: each new mechanism must be introduced by
    a lesson in the currently failing section.  Nothing is written here.
    """
    candidate = copy.deepcopy(course)
    records = candidate["mechanismContract"]["mechanisms"]
    known = {item["id"] for item in records}
    section = next(item for item in candidate["sections"] if item["id"] == sid)
    nodes = {node["id"]: node for node in section["nodes"]}
    for finding in findings:
        expected = MECHANISM_KEYS | {"demands"}
        if not isinstance(finding, dict) or set(finding) != expected:
            raise ValueError("each mechanism finding must contain id, label, kind, owner, demands")
        mid, owner = finding["id"], finding["owner"]
        if mid in known or not ID_RE.fullmatch(str(mid or "")):
            raise ValueError(f"new mechanism id {mid!r} is invalid or already sealed")
        if owner not in nodes or nodes[owner].get("kind") != "lesson":
            raise ValueError("a finding owner must be a lesson in the failing section")
        records.append({key: finding[key] for key in MECHANISM_KEYS})
        nodes[owner]["introduces"].append(mid)
        for demand in finding["demands"]:
            target = nodes.get(demand)
            if target is None:
                raise ValueError("a finding demand must be a node in the failing section")
            field = "introduces" if target.get("kind") == "lesson" else "mechanisms"
            if mid not in target[field]:
                target[field].append(mid)
        known.add(mid)
    return candidate
