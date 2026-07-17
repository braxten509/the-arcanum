"""Shared parsing and performance rules for the language-mastery contract."""
from __future__ import annotations

import math
import re

CONTRACT_VERSION = 1
CONTRACT_MARKER = "Language mastery contract"
LANGUAGE_CAPABILITY = re.compile(r"language-[a-z0-9]+(?:-[a-z0-9]+)*\Z")
PERFORMANCE_ID = re.compile(r"language-performance-s\d{2}-\d{2}\Z")
WORKING_ID = re.compile(r"s\d{2}\.working\Z")
KINDS = {
    "guided-modification": 1,
    "familiar-independent-task": 2,
    "novel-transfer": 3,
    "unfamiliar-tradeoff": 4,
    "architecture-defense": 5,
}
RULES = {
    1: {"count": 1, "rationales": 1},
    2: {"count": 1, "rationales": 0},
    3: {"count": 2, "rationales": 1},
    4: {"count": 3, "rationales": 2},
    5: {"count": 2, "rationales": 2},
}
CONTRACT_KEYS = {"version", "language", "level", "capabilityIds", "performances"}
OPTIONAL_CONTRACT_KEYS = {
    "foundationCapabilities", "foundationVersion", "coverageProfileVersion", "coverageAreaIds",
}
PERFORMANCE_KEYS = {
    "id", "workingId", "kind", "capabilityIds", "description", "rationaleRequired",
}


def _field(text, label):
    match = re.search(rf"(?im)^\*\*{re.escape(label)}:\*\*\s*(\S.*)$", str(text or ""))
    return match.group(1).strip() if match else ""


def _gate_int(text, label):
    match = re.search(rf"(?im)^- \*\*{re.escape(label)}:\*\*\s*([0-9]+)\s*$", text)
    return int(match.group(1)) if match else 0


def required_by_plan(text):
    return bool(re.search(
        rf"(?im)^- \*\*{re.escape(CONTRACT_MARKER)}:\*\*\s*{CONTRACT_VERSION}\s*$",
        str(text or "")))


def capability_spine(text):
    raw = _field(text, "Language capability spine")
    return [item.strip() for item in raw.split(" -> ") if item.strip()]


def performance_specs(text):
    """Parse the compact Phase-1 performance line into deterministic stable records."""
    raw = _field(text, "Language performances")
    if not raw:
        return [], ["**Language performances:** is missing"]
    pattern = re.compile(
        r"^(s\d{2}\.working)\s*=\s*"
        r"(guided-modification|familiar-independent-task|novel-transfer|"
        r"unfamiliar-tradeoff|architecture-defense)"
        r"(\s*\+\s*rationale)?\s*:\s*(\S.{19,})$", re.I)
    counts, records, problems = {}, [], []
    for raw_clause in raw.split(";"):
        clause = raw_clause.strip()
        match = pattern.fullmatch(clause)
        if not match:
            problems.append(
                "invalid language performance clause " + repr(clause) + "; expected "
                "`sNN.working = <kind> [+ rationale]: description of at least 20 characters`")
            continue
        working, kind, rationale, description = match.groups()
        working, kind = working.lower(), kind.lower()
        sid = working.split(".", 1)[0]
        counts[working] = counts.get(working, 0) + 1
        records.append({
            "id": f"language-performance-{sid}-{counts[working]:02d}",
            "workingId": working,
            "kind": kind,
            "capabilityIds": [],
            "description": " ".join(description.split()),
            "rationaleRequired": bool(rationale),
        })
    return records, problems


def _performance_rule_problems(records, level, section_ids):
    problems = []
    rule = RULES.get(level)
    if not rule:
        return ["language mastery level must be a whole number from 1 through 5"]
    if len(records) < rule["count"]:
        problems.append(
            f"Finish {level}/5 needs at least {rule['count']} structured late language "
            f"performance(s); found {len(records)}")
    rationale_count = sum(item.get("rationaleRequired") is True for item in records)
    if rationale_count < rule["rationales"]:
        problems.append(
            f"Finish {level}/5 needs at least {rule['rationales']} language performance(s) "
            f"with `+ rationale`; found {rationale_count}")
    order = {sid: index for index, sid in enumerate(section_ids, 1)}
    late_start = math.floor(2 * len(section_ids) / 3) + 1 if section_ids else 1
    for item in records:
        sid = str(item.get("workingId") or "").split(".", 1)[0]
        if sid not in order:
            problems.append(f"language performance {item.get('id')!r} names unknown {sid}.working")
        elif order[sid] < late_start:
            problems.append(
                f"language performance {item.get('id')!r} is in {sid}; Finish {level}/5 "
                f"performances must be late (section ordinal {late_start} or later)")
        kind = item.get("kind")
        if KINDS.get(kind, 0) < level:
            problems.append(
                f"language performance {item.get('id')!r} kind {kind!r} is below Finish {level}/5")
    if section_ids and not any(
            item.get("workingId") == f"{section_ids[-1]}.working" for item in records):
        problems.append("the final Working must contain a structured language performance")
    return problems
