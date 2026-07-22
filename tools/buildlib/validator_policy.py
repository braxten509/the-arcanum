"""Shared semantic policy for Validator AI output in any readable format."""
from __future__ import annotations

from dataclasses import dataclass
import json
import re


_VERDICT_KEYS = ("outcome", "status", "verdict", "judgment", "result", "decision",
                 "assessment", "conclusion")
_JSON_PUNCTUATION = frozenset(',:[]{}"')


def _normalized_verdict(value):
    if not isinstance(value, str):
        return ""
    match = re.match(r"(?i)^\s*(PASS|FAIL)\b", value)
    return match.group(1).upper() if match else ""


def _looks_like_verdict(value):
    if not isinstance(value, dict):
        return False
    has_outcome = any(_normalized_verdict(value.get(key)) for key in _VERDICT_KEYS)
    has_envelope = any(key in value for key in (
        "reasons", "reason", "summary", "explanation", "analysis", "details", "message",
        "report", "checks", "findings", "missingMechanisms", "nodeReviews",
        "qualityFindings"))
    return has_outcome and has_envelope


def _repair_json_verdict(text, *, max_edits=2):
    """Repair a tiny punctuation slip without asking another model to reformat it.

    CLI models occasionally emit an otherwise complete object with one stray quote/comma at
    an object boundary. Search only a small window around the JSON parser's error, delete at
    most two punctuation characters, and accept only a top-level object with an explicit
    validator verdict. Domain-specific evidence checks still decide whether a PASS is usable.
    """
    starts = [match.start() for match in re.finditer(r"\{", text)]
    last = text.rfind("}")
    segments = []
    for start in starts[:8]:
        if last > start:
            candidate = text[start:last + 1]
            if re.search(r'(?i)["\']?(?:outcome|status|verdict|judgment|result|decision|'
                         r'assessment|conclusion)["\']?\s*:', candidate[:2000]):
                segments.append(candidate)
    for segment in segments:
        frontier, seen = [segment], {segment}
        for _edit_count in range(max_edits + 1):
            successes, following = [], []
            for candidate in frontier:
                try:
                    value = json.loads(candidate)
                except json.JSONDecodeError as exc:
                    left, right = max(0, exc.pos - 16), min(len(candidate), exc.pos + 5)
                    positions = [index for index in range(left, right)
                                 if candidate[index] in _JSON_PUNCTUATION]
                    positions.sort(key=lambda index: (abs(index - exc.pos), index))
                    for index in positions:
                        repaired = candidate[:index] + candidate[index + 1:]
                        if repaired not in seen:
                            seen.add(repaired)
                            following.append(repaired)
                else:
                    if _looks_like_verdict(value):
                        successes.append(value)
            if successes:
                return max(successes, key=lambda value: sum(
                    key in value for key in (
                        "reasons", "reason", "summary", "checks", "findings",
                        "nodeReviews", "qualityFindings", "citations")))
            # Bound malformed-input work while retaining all nearby one/two-character fixes.
            frontier = following[:512]
    return None


@dataclass(frozen=True)
class ValidatorOutput:
    """Separate audit-format defects from whether a verdict is operationally usable."""

    result: dict
    malformed: bool
    unusable: bool
    recovered_verdict: bool


def extract_json(raw):
    """Extract the largest JSON object from a provider response with optional prose."""
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        candidates = []
        for index, char in enumerate(text):
            if char != "{":
                continue
            try:
                value, consumed = decoder.raw_decode(text[index:])
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                candidates.append((consumed, value))
        verdicts = [item for item in candidates if _looks_like_verdict(item[1])]
        if verdicts:
            return max(verdicts, key=lambda item: item[0])[1]
        repaired = _repair_json_verdict(text)
        if repaired is not None:
            return repaired
        if candidates:
            return max(candidates, key=lambda item: item[0])[1]
    return None


def readable_outcome(value):
    if not isinstance(value, dict):
        return ""
    for key in _VERDICT_KEYS:
        normalized = _normalized_verdict(value.get(key))
        if normalized:
            return normalized
    return ""


def readable_reasons(value):
    if not isinstance(value, dict):
        return []
    for key in ("reasons", "reason", "summary", "explanation", "analysis", "details",
                "message", "report"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return [candidate.strip()]
        if isinstance(candidate, list):
            reasons = [item.strip() for item in candidate
                       if isinstance(item, str) and item.strip()]
            if reasons:
                return reasons
    return []


def readable_line_ranges(value):
    """Normalize common provider spellings of one or more inclusive line ranges."""
    if (isinstance(value, list) and len(value) == 2
            and all(type(number) is int for number in value)):
        return [value]
    if not isinstance(value, str):
        return []
    ranges = [[int(start), int(end)] for start, end in re.findall(
        r"(?<!\d)(\d+)\s*(?:-|–|—|:|\.\.)\s*(\d+)(?!\d)", value)]
    if ranges:
        return ranges
    stripped = value.strip()
    if stripped.isdigit():
        return [[int(stripped), int(stripped)]]
    single = re.fullmatch(r"(?i)\s*lines?\s+(\d+)\s*", value)
    return [[int(single.group(1)), int(single.group(1))]] if single else []


def _first_text(value, keys):
    if not isinstance(value, dict):
        return ""
    for key in keys:
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def readable_guidance(raw):
    """Extract helpful repair guidance without requiring a particular response schema."""
    value = extract_json(raw)
    if not isinstance(value, dict):
        return []
    checks = [item for item in value.get("checks") or [] if isinstance(item, dict)]
    by_criterion = {str(item.get("criterion") or ""): item for item in checks}
    candidates = []
    for key in ("findings", "qualityFindings", "missingMechanisms", "repairs"):
        rows = value.get(key)
        if isinstance(rows, str) and rows.strip():
            rows = [{"repair": rows}]
        if isinstance(rows, dict):
            rows = [rows]
        if isinstance(rows, list):
            candidates.extend(
                item if isinstance(item, dict) else {"repair": item}
                for item in rows if isinstance(item, dict)
                or isinstance(item, str) and item.strip())
    top_level_repair = _first_text(value, (
        "requiredRepair", "repair", "correction", "recommendation", "action", "fix"))
    if top_level_repair:
        candidates.append({"repair": top_level_repair})
    for check in checks:
        rows = check.get("findings", check.get("finding"))
        if isinstance(rows, str) and rows.strip():
            candidates.append({"criterion": check.get("criterion"), "repair": rows})
        elif isinstance(rows, dict):
            candidates.append({"criterion": check.get("criterion"), **rows})
        elif isinstance(rows, list):
            candidates.extend(
                {"criterion": check.get("criterion"), **item}
                for item in rows if isinstance(item, dict))
        if readable_outcome(check) == "FAIL" and not rows:
            evidence = _first_text(check, (
                "evidence", "issue", "problem", "reason", "explanation", "description"))
            evidence = evidence or next(iter(readable_reasons(check)), "")
            citations = [item for item in check.get("citations") or []
                         if isinstance(item, dict)]
            citation = citations[0] if citations else {}
            evidence = evidence or _first_text(citation, (
                "evidence", "issue", "problem", "reason", "description"))
            if evidence:
                candidates.append({
                    "criterion": check.get("criterion"),
                    "path": _first_text(citation, ("path", "file", "source")),
                    "lines": citation.get("evidenceLines", citation.get("lines")),
                    "evidence": evidence,
                })
    guidance = []
    for item in candidates:
        criterion = _first_text(item, ("criterion", "category", "id", "kind"))
        check = by_criterion.get(criterion, {})
        citations = item.get("citations")
        if not isinstance(citations, list):
            citations = check.get("citations") if isinstance(check, dict) else []
        citations = [row for row in citations or [] if isinstance(row, dict)]
        path = _first_text(item, ("path", "file", "source"))
        citation = next((row for row in citations if not path or row.get("path") == path),
                        citations[0] if citations else {})
        path = path or _first_text(citation, ("path", "file", "source"))
        ranges = readable_line_ranges(item.get(
            "evidenceLines", item.get("lines", item.get("location"))))
        if not ranges:
            ranges = readable_line_ranges(citation.get(
                "evidenceLines", citation.get("lines", citation.get("location"))))
        repair = _first_text(item, (
            "requiredRepair", "repair", "correction", "recommendation", "action", "fix"))
        evidence = _first_text(item, (
            "evidence", "issue", "problem", "reason", "semanticDelta", "description"))
        evidence = evidence or _first_text(citation, ("evidence", "issue", "problem"))
        if not repair and not evidence:
            continue
        location = path or "cited evidence"
        if ranges:
            location += ":" + ",".join(
                str(start) if start == end else f"{start}-{end}" for start, end in ranges)
        label = criterion or "validator finding"
        detail = repair or evidence
        if repair and evidence and evidence.casefold() not in repair.casefold():
            detail += f" Evidence: {evidence}"
        guidance.append(f"{label} at {location}: {detail}")
    # Preserve order while preventing repeated aliases from duplicating the same guidance.
    return list(dict.fromkeys(guidance))[:12]
