"""Per-section Validator AI policy: off, a single advisory pass, or a single enforced gate.

Replaces the old unbounded author<->validator loop. Three modes, chosen in the launch form:

- ``off``  — the section is gated by the mechanical checks alone; whole-tome depth is Phase 8's.
- ``pass`` — one advisory run. Its findings block the section once; the author gets a single
              repair turn, then the section is mechanical-only. The AI never re-audits.
- ``gate`` — one run sets findings the author MUST resolve. Each resubmission the AI verifies
              only those exact findings — it is forbidden from raising new ones (they are
              dropped) — for up to three verify rounds. If findings still aren't met after that,
              the section continues anyway as long as the mechanical validator passes.
"""
from __future__ import annotations

import json
import os

from .. import BUILD_DIR
from ..course.amend import amend_course_map
from ..course.state import record_section_failure
from ..course_map import CourseMapError, load_course_map
from ..mechanism_contract import candidate_with_findings
from ..prerequisites.ledger import load_ledger, open_fingerprints, restrict
from ..prerequisites.review import review_prerequisites

# review_prerequisites calls per mode: "off" never runs, "pass" runs once, "gate" runs the
# discovery pass plus up to three verify passes.
_RUN_LIMIT = {"off": 0, "pass": 1, "gate": 4}


def _mode(build_id):
    """Section review mode from launch.json `sectionAiReviewMode` (default "pass"), with
    back-compat for the old boolean `sectionAiReview` (True -> "pass", False -> "off")."""
    try:
        with open(os.path.join(BUILD_DIR, f"{build_id}.launch.json"), encoding="utf-8") as handle:
            launch = json.load(handle)
    except (OSError, ValueError):
        return "pass"
    mode = launch.get("sectionAiReviewMode")
    if mode in _RUN_LIMIT:
        return mode
    return "off" if launch.get("sectionAiReview") is False else "pass"


def should_run(build_id, sid):
    """Run the section Validator AI only while the mode's run budget is unspent. The durable
    ledger pass count survives resumes, so a restarted or already-audited section is never
    re-looped past its budget."""
    limit = _RUN_LIMIT[_mode(build_id)]
    return limit > 0 and load_ledger(BUILD_DIR, build_id, sid).get("pass", 0) < limit


def review_section(build_id, unit):
    """Run the due section audit; return (ok, report). ok=True means the section may proceed —
    it passed, review is off/spent, or (Single Gate) every previously required fix is now made.
    ok=False carries the findings report for one author repair turn."""
    sid = unit["section"]
    if not should_run(build_id, sid):
        return True, ""
    ledger = load_ledger(BUILD_DIR, build_id, sid)
    # Single Gate's second run is a verification pass: only the still-open first-pass findings
    # gate the section, and new issues are dropped rather than starting a fresh audit loop.
    verify_open = (open_fingerprints(ledger)
                   if _mode(build_id) == "gate" and ledger.get("pass", 0) >= 1 else None)
    if verify_open == set():
        return True, ""  # the discovery pass cited nothing to re-verify
    prerequisite = review_prerequisites(build_id, sid)
    if verify_open is not None:
        # ponytail: the model still audits fully; we gate only on the gated fingerprints and
        # discard anything new. Add a verify-only prompt to save tokens if cost matters.
        prerequisite = restrict(prerequisite, verify_open)
    if prerequisite.get("status") in ("PASS", "not-required"):
        return True, ""
    findings = prerequisite.get("missingMechanisms") or []
    quality_findings = prerequisite.get("qualityFindings") or []
    amended = ""
    if findings:
        try:
            candidate = candidate_with_findings(
                load_course_map(build_id), sid, findings)
            amend_course_map(
                build_id, candidate,
                f"Prerequisite audit found undeclared first-use mechanisms in {sid}")
            amended = (" The harness amended the sealed mechanism ledger; repair the "
                       "new lesson introductions and demand declarations, then retry.")
        except (CourseMapError, ValueError, TypeError) as exc:
            amended = f" Controlled amendment was rejected: {exc}"
    quality_repairs = "; ".join(
        f"{item.get('node', '?')} [{item.get('category', 'quality')}]: "
        f"{item.get('requiredRepair', 'repair the cited defect')}"
        for item in quality_findings if isinstance(item, dict))
    helpful_repairs = "; ".join(
        item.strip() for item in prerequisite.get("guidance") or []
        if isinstance(item, str) and item.strip())
    semantic_issues = max(1, len(findings) + len(quality_findings))
    review_report = (f"Issues found: {semantic_issues}\n"
                     "section teaching-quality and prerequisite audit: "
                     f"{prerequisite.get('status')} — "
                     + "; ".join(prerequisite.get("reasons") or ["no cited evidence"])
                     + (f" Repairs: {quality_repairs}." if quality_repairs else "")
                     + (f" Helpful findings: {helpful_repairs}."
                        if helpful_repairs else "")
                     + amended)
    try:
        record_section_failure(build_id, sid, review_report)
    except ValueError:
        pass
    return False, review_report
