"""Sealed Phase-1 minimum language practice for every project Working."""
from __future__ import annotations

import re

from .shared import LANGUAGE_CAPABILITY, _field


CONTRACT_MARKER = "Language practice contract"
CONTRACT_VERSION = 1
ALLOCATION_LABEL = "Language practice allocation"


def required_by_plan(text):
    return bool(re.search(
        rf"(?im)^- \*\*{re.escape(CONTRACT_MARKER)}:\*\*\s*{CONTRACT_VERSION}\s*$",
        str(text or "")))


def practice_allocations(text, section_ids, capability_ids):
    """Parse and validate `sNN = language-*` minimums from the Phase-1 Arc."""
    if not required_by_plan(text):
        return {}, []
    raw = _field(text, ALLOCATION_LABEL)
    if not raw:
        return {}, [f"**{ALLOCATION_LABEL}:** is missing"]
    expected, spine = list(section_ids), set(capability_ids)
    allocations, problems = {}, []
    for raw_clause in raw.split(";"):
        clause = raw_clause.strip()
        match = re.fullmatch(r"(s\d{2})\s*=\s*(\S.*)", clause, re.I)
        if not match:
            problems.append(
                f"invalid language practice allocation {clause!r}; expected "
                "`sNN = language-capability[, language-capability]`")
            continue
        sid, raw_capabilities = match.groups()
        sid = sid.lower()
        if sid in allocations:
            problems.append(f"**{ALLOCATION_LABEL}:** repeats {sid}")
            continue
        capabilities = [item.strip() for item in raw_capabilities.split(",") if item.strip()]
        if not capabilities:
            problems.append(f"{sid} language practice allocation must not be empty")
        invalid = [item for item in capabilities if not LANGUAGE_CAPABILITY.fullmatch(item)]
        if invalid:
            problems.append(f"{sid} language practice has invalid capability ids: "
                            + ", ".join(invalid))
        if len(capabilities) != len(set(capabilities)):
            problems.append(f"{sid} language practice allocation contains duplicates")
        outside = sorted(set(capabilities) - spine)
        if outside:
            problems.append(f"{sid} language practice is outside the declared spine: "
                            + ", ".join(outside))
        allocations[sid] = capabilities
    missing = [sid for sid in expected if sid not in allocations]
    extra = sorted(set(allocations) - set(expected))
    if missing:
        problems.append(f"**{ALLOCATION_LABEL}:** is missing sections: " + ", ".join(missing))
    if extra:
        problems.append(f"**{ALLOCATION_LABEL}:** names unknown sections: " + ", ".join(extra))
    return allocations, problems


def seeded_practice_problems(seed_sections, proposed_sections):
    """Require Phase 2 to retain every Phase-1 minimum while permitting later retrieval."""
    seed_by_id = {
        section.get("id"): section for section in seed_sections or []
        if isinstance(section, dict)
    }
    proposed_by_id = {
        section.get("id"): section for section in proposed_sections or []
        if isinstance(section, dict)
    }
    problems = []
    for sid, seeded in seed_by_id.items():
        required = set(seeded.get("languagePractice") or [])
        proposed = set((proposed_by_id.get(sid) or {}).get("languagePractice") or [])
        missing = sorted(required - proposed)
        if missing:
            problems.append(
                f"{sid}.languagePractice removed sealed Phase-1 minimums: "
                + ", ".join(missing))
    return problems
