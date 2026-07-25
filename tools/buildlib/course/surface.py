"""Catch a sealed mechanism's literal spelling used before the lesson that owns it.

`mechanism_contract.authored_problems` already checks the ids an author *declared*
at each demand site. It cannot see a construct the author simply used and never
mentioned, which is why almost every recorded Validator AI failure reads like
"s02.l01 uses print in its first runnable example, but the sealed owner
python-print-call is s02.l03". Reading code blocks for that is mechanical work,
so the harness does it here for free and the paid audit keeps the judgement calls
it is actually needed for -- whether a mechanism deserves an owner at all.

Only use *before* the owner is reported. A spelling appearing at or after its
owner without a declaration is genuinely ambiguous (already-taught code recurs
everywhere), and that ambiguity is the audit's job, not a regex's.
"""
from __future__ import annotations

import re

# Fields that hold code a learner reads or types. Prose fields are scanned only
# through their `<code>`/backtick spans, below: a lesson body says "print" in
# English constantly, and matching that would fail every well-written section.
CODE_FIELDS = ("code", "starter", "solution", "answer", "expect", "content")
PROSE_FIELDS = ("body", "prompt", "explain", "hint", "desc", "brief", "xray", "instruction")
_TICK_OR_CODE = re.compile(r"`([^`]+)`|<code>(.*?)</code>", re.S)


def _pattern(literal):
    """Match a spelling verbatim, but never inside a longer identifier.

    Without the guard, `print` hits `blueprint` and `sprint`; with it, symbol
    spellings like `#`, `=>`, and `print(` still match exactly as written.
    """
    left = r"\b" if literal[:1].isalnum() or literal[:1] == "_" else ""
    right = r"\b" if literal[-1:].isalnum() or literal[-1:] == "_" else ""
    return re.compile(left + re.escape(literal) + right)


def _text(value):
    """Every code string reachable from one authored table, prose spans included."""
    if not isinstance(value, dict):
        return ""
    parts = [str(value.get(key) or "") for key in CODE_FIELDS]
    for key in PROSE_FIELDS:
        blob = str(value.get(key) or "")
        parts += [span or fenced for span, fenced in _TICK_OR_CODE.findall(blob)]
    for key in ("lines", "choices", "steps"):
        parts += [str(item) for item in value.get(key) or [] if isinstance(item, str)]
    return "\n".join(parts)


def _sites(planned, actual):
    """Yield (where, node_id, text) for every authored code site in one section."""
    planned_lessons = [node for node in planned.get("nodes") or []
                       if isinstance(node, dict) and node.get("kind") == "lesson"]
    actual_lessons = [lesson for lesson in actual.get("lessons") or []
                      if isinstance(lesson, dict)]
    for node, lesson in zip(planned_lessons, actual_lessons):
        nid = node.get("id")
        for group in ("exercises", "artifactSteps", "concepts"):
            for index, row in enumerate(lesson.get(group) or []):
                yield f"{nid}.{group}[{index}]", nid, _text(row)
        yield f"{nid}.body", nid, _text({"body": lesson.get("body")})

    working = next((node for node in planned.get("nodes") or []
                    if isinstance(node, dict) and node.get("kind") == "working"), None)
    if working is None:
        return
    wid = working.get("id")
    freestyle = actual.get("freestyle") or {}
    if isinstance(freestyle, dict):
        yield f"{wid}.brief", wid, _text(freestyle)
        for group in ("rubric", "referenceSteps", "checklist"):
            for index, row in enumerate(freestyle.get(group) or []):
                yield f"{wid}.{group}[{index}]", wid, _text(row)
    yield f"{wid}.proof", wid, _text(actual.get("proof") or {})


def surface_problems(course, actual, sid):
    """Report each sealed spelling that appears earlier than the lesson owning it."""
    if int(course.get("version") or 0) < 4:
        return []
    contract = course.get("mechanismContract") or {}
    section_ids = [section.get("id") for section in course.get("sections") or []
                   if isinstance(section, dict)]
    coverage = contract.get("coverageStart")
    if sid not in section_ids or coverage not in section_ids:
        return []
    if section_ids.index(sid) < section_ids.index(coverage):
        return []

    positions = {}
    for sindex, section in enumerate(course.get("sections") or []):
        for nindex, node in enumerate(section.get("nodes") or []):
            if isinstance(node, dict):
                positions[node.get("id")] = (sindex, nindex)
    watched = []
    for record in contract.get("mechanisms") or []:
        if not isinstance(record, dict):
            continue
        owner_at = positions.get(record.get("owner"))
        for literal in record.get("detect") or []:
            if isinstance(literal, str) and literal.strip() and owner_at is not None:
                watched.append((_pattern(literal), literal, record, owner_at))
    if not watched:
        return []

    planned = next(section for section in course["sections"] if section.get("id") == sid)
    problems = []
    for where, nid, text in _sites(planned, actual):
        site_at = positions.get(nid)
        if not text or site_at is None:
            continue
        for pattern, literal, record, owner_at in watched:
            if owner_at <= site_at or not pattern.search(text):
                continue
            problems.append(
                f"{where} uses {literal!r} but mechanism {record['id']!r} "
                f"({record.get('label')}) is not introduced until "
                f"{record.get('owner')} -- teach it before this use or rewrite "
                "the example without it")
    return sorted(set(problems))
