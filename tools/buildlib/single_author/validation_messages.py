"""Interpret deterministic validator output for author recovery."""
import re

_ISSUE_COUNT_RE = re.compile(
    r"(?im)^\s*issues?\s+found\s*[:=]\s*(\d+)\b")
_SUMMARY_COUNT_RE = re.compile(
    r"(?i)(\d+)\s+error\(s\)(?:\s*,\s*(\d+)\s+warning\(s\))?")


def validation_issue_count(report):
    """Return the number of findings represented by a failed report."""
    text = str(report or "")
    explicit = [
        int(match.group(1)) for match in _ISSUE_COUNT_RE.finditer(text)
    ]
    if explicit:
        return max(1, explicit[-1])
    structured = sum(
        1 for line in text.splitlines()
        if re.match(r"^\s*(?:ERROR|WARN)\b", line))
    if structured:
        return structured
    summarized = sum(
        int(match.group(1)) + int(match.group(2) or 0)
        for match in _SUMMARY_COUNT_RE.finditer(text))
    return max(1, summarized)


def validation_failure_message(unit_label, report):
    return (
        f"Validation failed for {unit_label}. The report was returned to the "
        "same author session. Any repeated finding was not cleared by the "
        f"preceding changes. ({validation_issue_count(report)} issues found)")
