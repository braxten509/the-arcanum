"""Harness-owned, content-bound Phase-8 evidence for proof-v1 tomes."""
import json
import os
import sys
import tomllib

from . import REPO

sys.path.insert(0, REPO)
import tome_layout  # noqa: E402
from tome_proof import (active_proofs, learner_project_path, proof_enabled,
                        proof_evidence_path, proof_fingerprint, review_coverage)  # noqa: E402


def _read(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def _load_tome(tid):
    root = os.path.join(REPO, "tomes", tid)
    with open(os.path.join(root, "tome.toml"), "rb") as handle:
        manifest = tomllib.load(handle)
    sections = [tome_layout.load_section(root, sid)
                for sid in (manifest.get("content") or {}).get("sections") or []]
    return manifest, sections


def _required_rows(manifest, sections):
    required = []
    for index, section in enumerate(sections):
        checkpoint = str(section.get("id"))
        for item in active_proofs(sections[:index + 1]):
            required.append(f"checkpoint:{checkpoint}/proof:{item['section']}")
    acceptance = manifest.get("acceptance") or {}
    scenarios = acceptance.get("scenarios") or []
    if acceptance.get("mode") == "run":
        required += ["project:final-build", "launch:ordinary", "acceptance:anti-constant"]
    required.append("acceptance:source")
    if acceptance.get("mode") == "run":
        required += [f"acceptance:negative:{scenario}" for scenario in scenarios]
    if acceptance.get("artifact") == "package":
        required += ["package:build", "acceptance:package"]
        required += [f"acceptance:package-negative:{scenario}" for scenario in scenarios]
    return required


def _evidence(tid, manifest, sections):
    report = _read(proof_evidence_path(REPO, tid))
    fingerprint = proof_fingerprint(manifest, sections)
    project = os.path.relpath(learner_project_path(REPO, tid), REPO).replace(os.sep, "/")
    if not isinstance(report, dict) or report.get("version") != 2:
        return False, fingerprint, [], "proof evidence sidecar is missing, stale-versioned, or malformed", project
    if report.get("tome") != tid or report.get("fingerprint") != fingerprint:
        return False, fingerprint, [], "proof evidence is stale for the current tome content", project
    if (report.get("learnerProject") != project
            or not os.path.isdir(os.path.join(REPO, *project.split("/")))):
        return False, fingerprint, [], "the persisted reconstructed learner project is missing or mismatched", project
    rows = report.get("rows")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        return False, fingerprint, [], "proof evidence rows are malformed", project
    ids = [row.get("id") for row in rows]
    if (any(not isinstance(row_id, str) or not row_id for row_id in ids)
            or len(set(ids)) != len(ids)):
        return False, fingerprint, [], "proof evidence row ids are missing or duplicated", project
    if any(row.get("status") != "pass" for row in rows):
        return False, fingerprint, ids, "one or more proof evidence rows are not green", project
    required = _required_rows(manifest, sections)
    if ids != required:
        return False, fingerprint, ids, "proof evidence does not contain the exact cumulative matrix", project
    by_id = {row["id"]: row for row in rows}
    command_rows = ["launch:ordinary", "acceptance:source"]
    command_rows += [row_id for row_id in ids if row_id.startswith("acceptance:negative:")]
    if (manifest.get("acceptance") or {}).get("artifact") == "package":
        command_rows += ["acceptance:package"]
        command_rows += [row_id for row_id in ids
                         if row_id.startswith("acceptance:package-negative:")]
    for row_id in command_rows:
        row = by_id.get(row_id) or {}
        if (not isinstance(row.get("command"), list) or not row.get("command")
                or not isinstance(row.get("output"), str)):
            return False, fingerprint, ids, f"evidence row {row_id!r} lacks actual command/output", project
    final_build = by_id.get("project:final-build")
    if final_build is not None and (not isinstance(final_build.get("commands"), list)
                                    or not isinstance(final_build.get("output"), str)):
        return False, fingerprint, ids, "final build evidence lacks command/output", project
    return True, fingerprint, ids, "", project


def _contract(tid):
    try:
        manifest, sections = _load_tome(tid)
        if not proof_enabled(manifest):
            return None
        reviewed_sections, capabilities = review_coverage(sections)
        valid, fingerprint, rows, problem, project = _evidence(tid, manifest, sections)
        return {"sections": reviewed_sections, "capabilities": capabilities,
                "fingerprint": fingerprint, "rows": rows,
                "learnerProject": project,
                "evidenceValid": valid, "evidenceProblem": problem}
    except (OSError, tomllib.TOMLDecodeError, ValueError):
        return None


def enabled(tid):
    return _contract(tid) is not None


def protocol(tid, findings_rel, review_scope):
    contract = _contract(tid)
    if contract is None:
        return None
    evidence_rel = os.path.relpath(proof_evidence_path(REPO, tid), REPO)
    readiness = ("valid as a deterministic prerequisite" if contract["evidenceValid"] else
                 "NOT VALID: " + contract["evidenceProblem"])
    return f"""

===== PHASE 8 HARNESS PROTOCOL — CONTENT-BOUND EVIDENCE =====
You are already the fresh reviewer. Work directly; do not spawn reviewers or run a private
multi-pass loop. This invocation performs one review/fix pass, writes its evidence, and stops.

Review scope for this invocation:
{review_scope}

The harness-owned executable matrix is {evidence_rel}. Its state is: {readiness}.
The exact reconstructed learner project is {contract['learnerProject']}. Open and inspect that
project directly; do not mentally compose the lesson edits. Read the matrix's actual commands and
outputs, especially `project:final-build`, `launch:ordinary`, every negative acceptance challenge,
and package rows. A green row is only a deterministic prerequisite. It is NOT evidence that the
adapter honestly exercises the promised domain behavior, that the teaching is correct, or that a
beginner can follow it. Check those claims adversarially against the reconstructed source.

Do not manufacture or edit either harness artifact. The matrix is SHA-256-bound to the exact
tome/runtime/acceptance content. If it is invalid, repair the authored cause and report that fresh
harness verification is required.

Do not write PASS, GAPS REMAIN, or any verdict. Your only sidecar is {findings_rel}. After
actually reading every listed section, tracing every listed capability, cold-reading the persisted
project, and checking the evidence matrix against the implementation, write one JSON object with
these exact keys (derive every value by reading the artifacts; do not copy a supplied report):

  {{"version": 3, "evidenceFingerprint": "<matrix fingerprint>",
   "evidenceRowsReviewed": ["<every row id in exact order>"],
   "learnerProjectReviewed": "<exact persisted project path>",
   "sectionsReviewed": ["<every section id in exact order>"],
   "capabilitiesReviewed": ["<every capability in exact sorted order>"],
   "findings": [{{"file": "tomes/{tid}/... or {contract['learnerProject']}/...",
                  "line": 12, "evidenceRow": "<closest row id>",
                  "issue": "specific blocking semantic gap", "severity": "blocking"}}]}}

Use an empty `findings` array only when the deterministic evidence is valid, this invocation made no authored
tome/runtime change, and no blocking semantic gap exists. Findings require a real repo-relative
file and line when localizable plus the closest evidence row. If you repair anything, include a
blocking finding saying fresh verification is required; the harness will regenerate evidence and
start another pass. A malformed, partial, stale, or sampled report cannot complete the build.
"""


def _valid_citation(tid, finding, row_ids):
    path = finding.get("file")
    line = finding.get("line")
    evidence_row = finding.get("evidenceRow")
    if path is None:
        if line is not None:
            return False
    elif not isinstance(path, str):
        return False
    else:
        normalized = path.replace("\\", "/")
        allowed = normalized.startswith(f"tomes/{tid}/") or normalized.startswith(
            "global-configs/runtimes/") or normalized.startswith(
                f".tome-build/{tid}.learner-project/")
        full = os.path.realpath(os.path.join(REPO, normalized))
        if not allowed or not full.startswith(os.path.realpath(REPO) + os.sep) or not os.path.isfile(full):
            return False
        if not isinstance(line, int) or isinstance(line, bool) or line < 1:
            return False
        try:
            with open(full, encoding="utf-8", errors="replace") as handle:
                if line > sum(1 for _ in handle):
                    return False
        except OSError:
            return False
    return isinstance(evidence_row, str) and evidence_row in row_ids


def valid_report(tid, path):
    contract, report = _contract(tid), _read(path)
    if contract is None or not contract["evidenceValid"] or not isinstance(report, dict):
        return False, report
    required = {"version", "evidenceFingerprint", "evidenceRowsReviewed",
                "learnerProjectReviewed",
                "sectionsReviewed", "capabilitiesReviewed", "findings"}
    if set(report) != required:
        return False, report
    if (report.get("version") != 3
            or report.get("evidenceFingerprint") != contract["fingerprint"]
            or report.get("evidenceRowsReviewed") != contract["rows"]
            or report.get("learnerProjectReviewed") != contract["learnerProject"]
            or report.get("sectionsReviewed") != contract["sections"]
            or report.get("capabilitiesReviewed") != contract["capabilities"]
            or not isinstance(report.get("findings"), list)):
        return False, report
    finding_keys = {"file", "line", "evidenceRow", "issue", "severity"}
    for finding in report["findings"]:
        if not isinstance(finding, dict) or set(finding) != finding_keys:
            return False, report
        if not isinstance(finding.get("issue"), str) or len(finding["issue"].strip()) < 8:
            return False, report
        if finding.get("severity") != "blocking":
            return False, report
        if not _valid_citation(tid, finding, set(contract["rows"])):
            return False, report
    return True, report


def derived_verdict(tid, verdict_path, findings_path):
    """Return a verdict only from current harness evidence plus fresh reviewer findings."""
    try:
        raw_verdict = open(verdict_path, encoding="utf-8").read().strip()
        open(verdict_path, "w", encoding="utf-8").close()
    except OSError:
        raw_verdict = ""
    if raw_verdict:
        return None
    valid, report = valid_report(tid, findings_path)
    if not valid:
        return None
    return "GAPS REMAIN" if report["findings"] else "PASS"


def findings_clear(tid, path):
    valid, report = valid_report(tid, path)
    return bool(valid and not report["findings"])
