"""Optional exhaustive post-Phase-8 reviewer contract and evidence gate."""
from __future__ import annotations

import json
import os

from arcanum.ai import NO_TOME_MEMORY_POLICY

from .. import BUILD_DIR, REPO
from ..measure import selected_runtime_config
from ..workflow.prompts import LEARNER_CONSTRUCTION_INSTRUCTION


def inventory(tid):
    """Return every authored tome file plus the selected shared runtime config."""
    root = os.path.join(REPO, "tomes", tid)
    paths = []
    if os.path.isdir(root):
        for dirpath, dirs, names in os.walk(root):
            dirs[:] = sorted(name for name in dirs if name != "save")
            for name in sorted(names):
                path = os.path.join(dirpath, name)
                if os.path.isfile(path):
                    paths.append(os.path.relpath(path, REPO).replace(os.sep, "/"))
    runtime = selected_runtime_config(tid)
    if runtime:
        path = os.path.join(REPO, "global-configs", "runtimes", runtime)
        if os.path.isfile(path):
            paths.append(os.path.relpath(path, REPO).replace(os.sep, "/"))
    return sorted(paths)


def evidence_path(build_id):
    return os.path.join(BUILD_DIR, f"{build_id}.full-review.json")


def prompt(build_id, tid, repair_report=""):
    paths = inventory(tid)
    evidence_rel = os.path.relpath(evidence_path(build_id), REPO).replace(os.sep, "/")
    listed = "\n".join(f"- `{path}`" for path in paths) or "- (inventory is empty; report this as blocking)"
    repair = (f"\n\nTHE HARNESS REJECTED THE PREVIOUS PASS:\n{repair_report[-18000:]}\n"
              if repair_report else "")
    return f"""You are the optional independent reviewer for a completed Arcanum tome.

{NO_TOME_MEMORY_POLICY}

THOROUGH FULL-TOME REVIEW — READ EVERYTHING — NO SAMPLING.

This is not a spot check, representative sample, summary review, or validator-only pass. Read
EVERY authored text file in the exact inventory below from beginning to end. Inspect EVERY
non-text asset in the inventory for correctness and suitability. Do not skip files because they
look generated, repetitive, familiar, or already validated. Do not rely on the author session's
claims. Review the entire tome as both a first-time learner and an adversarial technical editor.

Check teaching completeness, correctness, continuity, cumulative code, exercises, hints,
rubrics, runtime agreement, acceptance behavior, accessibility, delivery, and learner-facing
clarity. Open the reconstructed learner project and proof evidence when the tome references
them. Fix anything you see fit directly in the authored tome or its selected runtime config.
Preserve correct work. Do not edit unrelated tomes, runtime configs, engine code, validators, or
harness evidence. Do not spawn another reviewer. The harness will independently run strict
shipping validation and live smoke checks after you stop.

NON-NEGOTIABLE LEARNER CONSTRUCTION: {LEARNER_CONSTRUCTION_INSTRUCTION} Compare every visible
starter, code block, exercise solution, and any exceptional artifactStep against the hidden reference project;
production-ready overlap or a rename-equivalent solution is a blocking finding in every section,
not only in the final language-mastery performances. Treat the project as the cumulative
practice/proof vehicle; do not accept working project behavior as a substitute for fluency in
the declared implementation language.

EXACT REVIEW INVENTORY ({len(paths)} files):
{listed}

After all repairs, re-read every file you changed. Then write `{evidence_rel}` as strict JSON
with exactly these keys:

{{"version":1,"reviewMode":"thorough-full-tome","sampling":false,
 "filesReviewed":["every inventory path above, in the exact order shown"],
 "findings":[{{"file":"an inventory path","issue":"specific issue",
               "resolution":"specific repair made"}}],
 "unresolvedFindings":[],"summary":"concise review result"}}

`filesReviewed` must equal the complete inventory exactly; a sampled, shortened, malformed, or
stale report fails mechanically. Every finding must be repaired and recorded. Leave
`unresolvedFindings` empty only when no known issue remains. Do not claim the tome is complete
without writing this evidence. Stop after writing it so the harness can double-check your work.
{repair}"""


def validate_report(build_id, tid):
    path = evidence_path(build_id)
    try:
        with open(path, encoding="utf-8") as handle:
            report = json.load(handle)
    except (OSError, ValueError):
        return False, "the exhaustive review evidence is missing or malformed"
    required = {"version", "reviewMode", "sampling", "filesReviewed", "findings",
                "unresolvedFindings", "summary"}
    if not isinstance(report, dict) or set(report) != required:
        return False, "the exhaustive review evidence must contain exactly the required keys"
    expected = inventory(tid)
    if (report.get("version") != 1
            or report.get("reviewMode") != "thorough-full-tome"
            or report.get("sampling") is not False):
        return False, "reviewMode must be thorough-full-tome and sampling must be false"
    if report.get("filesReviewed") != expected:
        missing = [path for path in expected if path not in (report.get("filesReviewed") or [])]
        extra = [path for path in (report.get("filesReviewed") or []) if path not in expected]
        detail = []
        if missing:
            detail.append("missing: " + ", ".join(missing))
        if extra:
            detail.append("unexpected: " + ", ".join(extra))
        return False, "the reviewer did not attest to the exact full inventory" + (
            " (" + "; ".join(detail) + ")" if detail else "")
    findings = report.get("findings")
    if not isinstance(findings, list):
        return False, "findings must be a JSON array"
    finding_keys = {"file", "issue", "resolution"}
    for finding in findings:
        if (not isinstance(finding, dict) or set(finding) != finding_keys
                or finding.get("file") not in expected
                or any(not isinstance(finding.get(key), str) or len(finding[key].strip()) < 4
                       for key in ("issue", "resolution"))):
            return False, "every finding needs an inventory file plus a specific issue and repair"
    if report.get("unresolvedFindings") != []:
        return False, "all known review findings must be repaired before completion"
    if not isinstance(report.get("summary"), str) or len(report["summary"].strip()) < 8:
        return False, "the exhaustive review summary is missing"
    return True, "exhaustive review evidence covers every authored file"
