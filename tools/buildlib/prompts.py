"""Phase prompt assembly, the Phase-0 gate → plan writer, and verdict/findings IO."""
import json
import os
import re
import sys

from .checkpoints import ARC_CONTRACT, ARC_HEADING

PREAMBLE = """You are the headless worker for ONE phase of an Arcanum tome build.
Complete only Phase {num}, then stop. The harness owns phase order, retries, and folder
renames; never run `new_tome.py`, copy/move the tome, or leave scratch files in it.

Start by reading {plan} and the existing files relevant to this phase. The files, not
earlier prose claims, are ground truth. `tome-authoring/` is reference material: open only
the sections named by this phase, and use them to resolve schema or authoring questions.
Preserve correct earlier work unless this phase explicitly replaces it.

Before returning, run this phase-appropriate warm-context check:

  {validator_command}

Read the complete report. Fix every in-scope failure and rerun until it exits cleanly.
Report an out-of-scope finding without crossing the write boundary. The harness repeats
the gate independently and rejects unexplained file deletion or array shrinkage.

===== PHASE {num}: {title} =====

{body}
"""

STUDENT_HOOK = """

===== PHASE 8 HARNESS PROTOCOL =====
You are already the fresh reviewer. Work directly; do not spawn reviewers or run a private
multi-pass loop. This invocation performs one review/fix pass, writes its result, and stops.
The harness starts another fresh pass when needed.

Review scope for this invocation:
{review_scope}

Write exactly `PASS` or `GAPS REMAIN` as the sole line of {verdict}. PASS means a learner
matching the stated prerequisites can use the real tools to produce and verify the exact
artifact promised by `meta.description`, using only the tome, and this invocation made no
authored tome/runtime change. If you repair anything, write GAPS REMAIN; the harness will
start a fresh reviewer to verify the repair before accepting PASS.

On `GAPS REMAIN`, write {findings} as a JSON array of blocking findings, most severe first:
  [{{"file": "tomes/<id>/sections/s05/lessons/l04.toml", "issue": "the capstone uses an untaught API", "severity": "blocking"}}]
Use `null` for a whole-tome file. On PASS, write `[]` or remove the findings file.
"""

FULL_REVIEW_SCOPE = """Read the selected global runtime, then every section, lesson,
exercise, freestyle, and content bank in order. Do not sample. Apply the complete Phase 8
rubric."""

FOCUSED_REVIEW_SCOPE = """Start with the prior blocking findings below. Recheck each changed
file, its prerequisite owners, and downstream consumers. Expand only when a finding is
systemic; a focused retry need not reread unrelated chapters.

{focus}"""


def repair_verification_focus(changes):
    """Focus for the mandatory fresh pass after a reviewer changed authored content."""
    shown = list(changes[:40])
    lines = "\n".join(f"  - {change}" for change in shown)
    if len(changes) > len(shown):
        lines += (f"\n  - ... {len(changes) - len(shown)} additional authored files changed; "
                  "treat this as systemic and repeat the full-tome review")
    return ("- [blocking] Fresh verification is required because the previous reviewer "
            "changed authored tome/runtime content. Recheck each change against its earlier "
            "owners and downstream consumers. If every repair is sound, make no authored "
            "change and write PASS. If anything remains wrong, repair it and write GAPS "
            "REMAIN; the harness will schedule another fresh pass.\n" + lines)


def review_pass_eligible(verdict, changes, gates_clean=True, worker_rc=0):
    """Only a successful, no-edit reviewer may close the editorial gate."""
    return (verdict == "PASS" and not changes and gates_clean and worker_rc == 0)


def review_findings_clear(path):
    """PASS may accompany only a missing/blank findings sidecar or the exact JSON ``[]``."""
    if not os.path.exists(path):
        return True
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read().strip()
        return not raw or json.loads(raw) == []
    except (OSError, json.JSONDecodeError):
        return False


def build_prompt(tid, num, title, body, plan_rel, verdict_rel, findings_rel=None, focus=None,
                 validation_flags=None):
    if num == 1:
        validator_command = (f'cd "$ARCANUM_REPO_ROOT" && python3 tools/validate_tome.py '
                             f"tomes/{tid} --phase-1-plan {plan_rel}")
    else:
        flags = validation_flags if validation_flags is not None else ("--strict" if num >= 7 else "")
        validator_command = (f'cd "$ARCANUM_REPO_ROOT" && '
                             f"python3 tools/validate_tome.py tomes/{tid} {flags}").rstrip()
    p = PREAMBLE.format(tid=tid, num=num, title=title, body=body, plan=plan_rel,
                        validator_command=validator_command)
    if num == 8:
        review_scope = (FOCUSED_REVIEW_SCOPE.format(focus=focus)
                        if focus else FULL_REVIEW_SCOPE)
        p += STUDENT_HOOK.format(tid=tid, verdict=verdict_rel, findings=findings_rel,
                                 review_scope=review_scope)
    return p


def read_findings(path):
    """The reviewer's structured GAPS-REMAIN findings, as a short focus block (or None)."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            items = json.load(f)
    except (OSError, json.JSONDecodeError):
        try:
            open(path, "w", encoding="utf-8").close()
        except OSError:
            pass
        return None
    open(path, "w", encoding="utf-8").close()  # consume without removing the mounted sidecar
    if not isinstance(items, list):
        return None
    lines = []
    for item in items[:40]:
        if not isinstance(item, dict):
            continue
        clean = lambda value, limit: re.sub(r"\s+", " ", str(value or "")).strip()[:limit]
        issue = clean(item.get("issue"), 600)
        if not issue:
            continue
        severity = clean(item.get("severity") or "blocking", 40)
        file = clean(item.get("file"), 300) or "(whole tome)"
        lines.append(f"- [{severity}] {file}: {issue}")
    return "\n".join(lines) if lines else None


def read_verdict(path):
    if not os.path.exists(path):
        return None
    v = open(path, encoding="utf-8").read().strip().upper()
    open(path, "w", encoding="utf-8").close()  # keep the exact mounted file, clear stale verdict
    # Exact protocol, not keyword spotting: "NOT PASS", prose containing PASS, or a
    # malformed multi-line response must never end the editorial gate successfully.
    return v if v in ("PASS", "GAPS REMAIN") else None


GATE_QS = [
    ("Prior knowledge", "What can the student already do? (languages / tools they know)"),
    ("Starting level (1-10)", "How much does the student already know about THIS subject? "
     "1 = absolute zero (teach the language/tool from scratch as its own chapters), 10 = expert (advanced material only)"),
    ("Breadth (1-10)", "How much of the topic's surface? 1 = one tight path to the objective, 10 = the whole territory"),
    ("Lesson depth (1-10)", "How deep does each lesson dig? 1 = just use it, 10 = internals and edge cases"),
    ("Mastery (1-5)", "Where must the student stand after the last chapter? 1 = acquainted, 5 = expert"),
    ("Tooling", "internal (in-browser only), external (teach real tools), or both?"),
]

MASTERY_LEVELS = {
    1: ("ACQUAINTED", "Can explain the core ideas and modify guided examples, but not work alone."),
    2: ("FUNCTIONAL", "Can build small everyday examples and repair simple faults unaided."),
    3: ("CAPABLE", "Can solve real problems independently and justify choices among taught approaches."),
    4: ("ADVANCED", "Can use the topic's important idioms, internals, and power tools fluently."),
    5: ("EXPERT", "Can reason about the machinery and architect a substantial solution defensibly."),
}
PRIOR_LEVELS = {
    1: ("FROM ZERO", "Teach installation, first run, syntax, and fundamentals before domain work."),
    2: ("NEAR ZERO", "Teach the language/tool from its basics, moving only slightly faster."),
    3: ("BEGINNER", "Teach this language/tool from the ground up; general coding ideas may be familiar."),
    4: ("OTHER-STACK CODER", "Give this language and toolchain a focused on-ramp before domain work."),
    5: ("GENERALIST", "Give a brisk primer on this stack's differences, then enter the domain."),
    6: ("ADJACENT", "Recap only the specific tooling and APIs this course relies on."),
    7: ("PRACTITIONER", "Skip fundamentals and begin with the domain, introducing APIs in context."),
    8: ("FLUENT", "Assume language idioms and standard tooling; begin at the real work."),
    9: ("ADVANCED", "Assume the domain except for the advanced material this course targets."),
    10: ("EXPERT", "Teach only non-obvious frontier material."),
}
TOOLING_POLICY = {
    "internal": ("INTERNAL (in-browser only)",
        "Use the browser workbench only; do not require downloads or set `externalWorkspace`."),
    "external": ("EXTERNAL (teach the real tools)",
        "Teach the real toolchain from install through diagnostics and final delivery; use "
        "`externalWorkspace` when the real work cannot run in-browser."),
    "both": ("BOTH (internal + external available)",
        "Support the browser workbench and teach the complete real-tool path through final delivery."),
}


def gate_errors(answers):
    """Validate Phase-0 answers before any model spends tokens interpreting them.

    The plan is the source of truth for every later phase and for --tooling validation;
    a blank/invalid answer here otherwise silently disables the corresponding guardrail.
    """
    values = {label: str(value or "").strip() for label, value in answers}
    errors = []
    if not values.get("Prior knowledge"):
        errors.append("Prior knowledge must say what the student already knows (use 'none' if appropriate)")
    for label, hi in (("Starting level (1-10)", 10), ("Breadth (1-10)", 10),
                      ("Lesson depth (1-10)", 10), ("Mastery (1-5)", 5)):
        raw = values.get(label, "")
        try:
            number = int(raw)
        except ValueError:
            number = 0
        if str(number) != raw or not 1 <= number <= hi:
            errors.append(f"{label} must be a whole number from 1 to {hi}")
    tooling = values.get("Tooling", "").lower()
    if tooling not in TOOLING_POLICY:
        errors.append("Tooling must be exactly internal, external, or both")
    return errors


def read_tooling(plan_path):
    """The Tooling gate answer (internal|external|both) from the plan, or None — the
    single source of truth the harness passes to the validator on every phase, resume
    included (the plan always exists once Phase 0 has run)."""
    try:
        txt = open(plan_path, encoding="utf-8").read()
    except OSError:
        return None
    m = re.search(r"(?im)^- \*\*Tooling:\*\*\s*(\w+)", txt)
    v = m.group(1).lower() if m else None
    return v if v in ("internal", "external", "both") else None


def write_plan(plan_path, tid, answers, concept=None):
    """Write a compact Phase-0 brief; Phase 1 adds only course-specific decisions."""
    with open(plan_path, "w", encoding="utf-8") as f:
        f.write(f"# BUILD PLAN — {tid}\n\n")
        if concept:
            f.write("## Concept\n" + concept.strip() + "\n\n")
        f.write("## Gate answers (Phase 0)\n")
        for k, v in answers:
            if v:   # an unanswered dial is omitted, not written as an empty line
                f.write(f"- **{k}:** {v}\n")
        values = {k: str(v).strip() for k, v in answers}
        m = next((v for k, v in answers if k.startswith("Mastery")), "")
        try:
            lvl = MASTERY_LEVELS.get(int(str(m).strip()))
        except (ValueError, TypeError):
            lvl = None
        p = next((v for k, v in answers if k.startswith("Starting level")), "")
        try:
            plvl = PRIOR_LEVELS.get(int(str(p).strip()))
        except (ValueError, TypeError):
            plvl = None
        pol = TOOLING_POLICY.get(next((v.lower() for k, v in answers if k == "Tooling"), ""))
        f.write("\n## Calibration contract\n")
        if plvl:
            f.write(f"- **Start {str(p).strip()}/10 — {plvl[0]}:** {plvl[1]}\n")
        f.write(f"- **Breadth {values.get('Breadth (1-10)', '?')}/10:** controls which "
                "topic domains enter the section arc; it does not set a chapter count.\n")
        f.write(f"- **Depth {values.get('Lesson depth (1-10)', '?')}/10:** controls how "
                "far each included mechanism is explained, debugged, and qualified.\n")
        if lvl:
            f.write(f"- **Finish {str(m).strip()}/5 — {lvl[0]}:** {lvl[1]}\n")
        if pol:
            f.write(f"- **Tooling — {pol[0]}:** {pol[1]}\n")
        f.write("- These calibrated answers override casual scope adjectives in the concept. "
                "Phase 1 must translate them into the actual difficulty spine, graduate ledger, "
                "daily-driver scope, lifecycle, acceptance proof, and section arc below.\n")
        f.write("\n" + ARC_HEADING + ARC_CONTRACT)


def do_gate(plan_path, tid, concept=None):
    """Phase 0 is interactive by design — the harness asks the user, no agent involved."""
    print("\n=== Phase 0 — GATE: six course-shaping questions (the harness asks YOU) ===")
    while True:
        ans = [(k, input(f"  {q}\n  > ").strip()) for k, q in GATE_QS]
        errors = gate_errors(ans)
        if not errors:
            break
        print("\n  Gate answers are incomplete or invalid:")
        for error in errors:
            print(f"  - {error}")
        print("  Please answer the gate again; no build has started.\n")
    write_plan(plan_path, tid, ans, concept)
    print(f"  -> wrote {plan_path}\n")


def do_gate_json(plan_path, tid, gate_json, concept=None):
    """Phase 0 without a terminal (web-launched): the gate answers arrive as JSON."""
    try:
        g = json.loads(gate_json)
    except json.JSONDecodeError as e:
        sys.exit(f"--gate-json is not valid JSON: {e}")
    if not isinstance(g, dict):
        sys.exit("--gate-json must be a JSON object containing all six Phase-0 answers")
    ans = [(label, str(g.get(key, "")).strip()) for (label, _), key in
           zip(GATE_QS, ("prior_knowledge", "prior_level", "breadth", "depth", "mastery", "tooling"))]
    errors = gate_errors(ans)
    if errors:
        sys.exit("--gate-json has incomplete or invalid Phase-0 answers:\n- " + "\n- ".join(errors))
    write_plan(plan_path, tid, ans, concept)
    print(f"=== Phase 0 — GATE: answers taken from --gate-json ===\n  -> wrote {plan_path}\n")
