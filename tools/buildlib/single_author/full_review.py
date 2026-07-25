"""Optional exhaustive post-Phase-8 reviewer contract and evidence gate."""
from __future__ import annotations

import json
import os

from arcanum.ai import NO_TOME_MEMORY_POLICY

from .. import BUILD_DIR, REPO
from ..measure import selected_runtime_config
from ..workflow.prompts import LEARNER_CONSTRUCTION_INSTRUCTION


def inventory(tid):
    """Return every authored file the reviewer must read and may repair.

    Continuity handoffs belong here even though they sit outside the tome folder.
    They are author-owned prose about how each section leaves the project, they are
    graded by the same strict gate the reviewer is graded by, and a repair the
    reviewer cannot cite as a finding is a repair it will not make.
    """
    from ..continuity import handoff_dir
    root = os.path.join(REPO, "tomes", tid)
    paths = []
    for base, skip_save in ((root, True), (handoff_dir(tid), False)):
        if not os.path.isdir(base):
            continue
        for dirpath, dirs, names in os.walk(base):
            dirs[:] = sorted(name for name in dirs if not (skip_save and name == "save"))
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
them. Fix anything you see fit directly in the authored tome, its continuity handoffs, or its
selected runtime config. Preserve correct work. Do not edit unrelated tomes, runtime configs,
engine code, validators, or harness evidence beyond those files. Do not spawn another reviewer.
After you stop, the harness independently runs strict shipping validation, EVERY SECTION'S OWN
validator gate, and live smoke checks. The per-section gate catches what a tome-wide pass averages
away — most often an answer-position spread that clusters inside one section while the pooled bank
looks even — so check each section's question bank on its own terms, not the tome's.
A handoff carries only what its schema already defines — fill blank fields, invent no keys.

YOU ARE THE PRIMARY DEPTH GATE. Each section received at most a single advisory Validator-AI
pass before this review — there was no per-section repair loop — so unresolved teaching defects
reach you here and nowhere else. Do not defer, soft-flag, or merely note a defect: repair it in
place. Be especially adversarial about the failure classes a per-section pass most often leaves
behind, and fix each where you find it:
- CONTINUITY: a lesson that contradicts, silently depends on, or forward-references another
  lesson, the Working, or the runtime config. Reconcile both sides so the learner route is
  consistent end to end.
- PREREQUISITE / FIRST-USE TEACHING: any command, syntax, flag, or mechanism the Working or a
  later lesson requires but no earlier lesson introduces with purpose, syntax, an observable
  demonstration, and guided practice. Add the missing instruction before first required use.
- LEARNER INDEPENDENCE: a required exercise, Working, or check the learner cannot complete from
  what was actually taught. Add the missing construction practice or correct the requirement.
- TECHNICAL CORRECTNESS: any claim, command, or expected output that is wrong or unachievable in
  the taught workspace. Correct it and make the observable result match reality.
- EMPTY CONTINUITY HANDOFF: an inventory handoff whose `artifact_state` is blank. The harness
  creates that file but cannot know what it should say. Read the section, then write what the
  learner's project actually looks like once that section ends — which artifacts now exist, what
  runs, what the next section inherits. Change nothing else in the file.
- STRAY LAYOUT: a file or section folder the validator reports as outside the layout contract,
  including a section folder absent from `[content].sections`. Delete the debris, or list the
  section in the manifest if it is genuinely meant to ship.
If a stated requirement is genuinely unsatisfiable (for example it demands an external citation
or artifact that cannot exist), repair it by relaxing the requirement to a taught, verifiable
route rather than leaving a defect the tome can never resolve.

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
    reviewed = report.get("filesReviewed")
    if not isinstance(reviewed, list) or any(not isinstance(item, str) for item in reviewed):
        return False, "filesReviewed must be an array of inventory paths"
    # The inventory is recomputed here, after the review, so deleting stray layout
    # debris -- which the reviewer is told to do -- moves a path off it. Attesting a
    # path that no longer exists is that deletion, and is allowed. Attesting one that
    # still exists but was never in the inventory is a fabrication, and is not.
    missing = [path for path in expected if path not in reviewed]
    extra = [path for path in reviewed
             if path not in expected and os.path.exists(os.path.join(REPO, path))]
    if missing or extra:
        detail = ([("missing: " + ", ".join(missing))] if missing else []) + (
            [("unexpected: " + ", ".join(extra))] if extra else [])
        return False, ("the reviewer did not attest to the exact full inventory ("
                       + "; ".join(detail) + ")")
    expected = set(expected) | set(reviewed)
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
