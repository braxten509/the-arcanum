"""Phase prompt assembly, the Phase-0 gate → plan writer, and verdict/findings IO."""
import json
import os
import re
import sys

PREAMBLE = """You are ONE stage of an automated build harness for an Arcanum coding-tome.
You are running headless. Do this ONE phase completely and correctly, then STOP — do
NOT start other phases; the harness runs those separately.

Context you share with the other phases (all of it lives on disk):
- Tome id: {tid}. Its folder ALREADY EXISTS — the harness scaffolded tomes/{tid}/ after
  Phase 0. Put ALL content THERE; never run new_tome.py or create another tome folder.
- Full authoring reference: the tome-authoring/ folder, one file per section — `§N` means
  the file starting with `N-` (so "§3" = tome-authoring/3-chapters.md; its README indexes
  them all). READ the sections THIS phase names below, and only those.
- Build plan (the user's gate answers + the arc): {plan}
  READ IT FIRST. Append any durable decision you make (arc, section list, the VOICE) so
  the later phases inherit it — you are not the same agent that runs the next phase.
- The tome files already on disk are the source of truth; earlier phases wrote them.
- The plan is a LOG, not evidence: before you build on a prior phase's claim, verify it
  against the files — phases have claimed work the disk never showed.
- Never duplicate the tome directory, and leave no backups, scratch files, or old-name
  folders under tomes/ — every file outside the layout contract fails validation.
  Folder renames are the HARNESS's job (it derives the id from [runtime] project);
  never mv/cp the tome folder yourself.

After you finish, the harness runs tools/validate_tome.py (from Phase 7 on, in --strict
mode where anti-template/content WARNs fail too); if it reports failures you will be
re-invoked with them, so leave the tome parseable. The harness also compares the file
tree and content counts before/after your phase: deleting files or shrinking arrays an
earlier phase built gets you re-invoked unless the plan gains a `SHRINK OK:` line
explaining why.

===== YOUR PHASE =====
## Phase {num} — {title}

{body}
"""

STUDENT_HOOK = """

===== HARNESS HOOK (phase 8) =====
This phase is the whole point of the harness: do NOT skip the student read-through, and
read EVERY chapter s01..last cover to cover, then fill the gaps you find.

You are ALREADY the clean-context reviewer: the harness runs you as a fresh worker with
no authoring context, so where the workflow says to spawn a clean-context subagent, that
means YOU — do NOT spawn a subagent/child agent to do the reading (it re-reads the whole
tome a second time and doubles this phase's cost for zero information). Read the chapters
yourself, in order. And run `python3 tools/validate_tome.py tomes/{tid} --strict` directly
in your own shell, as often as you like — it is a free local script; its failures are
never counted against you, so there is nothing to gain by testing it in a child.

ONE pass per invocation. The harness owns the review loop (it re-runs this phase and
scopes the next round to your findings) — do NOT run your own second/third/final review
rounds, and do NOT spawn reviewers to re-check your fixes. Read once, fix what you found,
re-run the validator, write the honest verdict, STOP. If gaps remain after your fixes,
that is what GAPS REMAIN + the findings file is for — the harness will send the next
round. A private review loop re-reads the tome four or five times over and burns the
whole usage budget in one phase.

You are also the AUDITOR — the last eyes before shipping, with three duties the
student lens does not cover (a smarter reviewer only does the job it was given, so
here is the whole job):
- INVENTORY: list every file under the tome folder (`find tomes/<id> -type f`) and
  justify each against the layout contract in tome-authoring/7-validate.md. A nested folder, a
  backup copy, or a scratch file is a FAIL, not a shrug.
- CLAIMS vs DISK: reread the build plan and verify every claim in it against the
  files. A phase that wrote "registered the 6 badges" must have six [[badges]] on
  disk right now. Claims are not evidence.
- ENGINE CONTRACTS: the badge bank defines every engine-granted id; shop theme items
  point at real [[themes]]; attack starters run as given. The META files — badges,
  themes, shop, intrusions, attacks — are content too: read them in the tome's voice,
  not just the chapters.

When done, write your verdict to the file {verdict} — exactly one line:
  PASS          if a first-time student, having read every chapter, could now sit down
                with the REAL tools and a REAL target and do what meta.description
                promises, unaided.
  GAPS REMAIN   otherwise.
The harness re-runs this phase until you write PASS (up to a few times), so only write
PASS when it is genuinely true.

If (and only if) the verdict is GAPS REMAIN, ALSO write {findings} as a JSON array of the
blocking findings, most-severe first — so the next review pass can go straight to them
instead of re-reading all 46 files:
  [{{"file": "tomes/<id>/sections/s05/lessons/l04.toml", "issue": "recursion never taught before the lab", "severity": "blocking"}}, …]
Use "file": null for a whole-tome finding. Keep it to the real blockers you just fixed or
still need fixed. On PASS, do not write this file (or write []).
"""


def build_prompt(tid, num, title, body, plan_rel, verdict_rel, findings_rel=None, focus=None):
    p = PREAMBLE.format(tid=tid, num=num, title=title, body=body, plan=plan_rel)
    if num == 8:
        p += STUDENT_HOOK.format(tid=tid, verdict=verdict_rel, findings=findings_rel)
        if focus:
            p += ("\n\n===== FOCUS THIS PASS (from the previous review's findings) =====\n"
                  "A prior pass already read the whole tome and flagged the items below. Fix "
                  "THESE first and re-verify the chapters they touch — you need not re-read every "
                  "chapter from scratch this round:\n" + focus)
    return p


def read_findings(path):
    """The reviewer's structured GAPS-REMAIN findings, as a short focus block (or None)."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            items = json.load(f)
        os.remove(path)  # consume it; the next round writes fresh
    except (OSError, json.JSONDecodeError):
        return None
    lines = [f"- [{it.get('severity', '?')}] {it.get('file') or '(whole tome)'}: {it.get('issue', '')}"
             for it in items if isinstance(it, dict)]
    return "\n".join(lines) if lines else None


def read_verdict(path):
    if not os.path.exists(path):
        return None
    v = open(path, encoding="utf-8").read().strip().upper()
    os.remove(path)  # consume it so the next loop reads a fresh write
    return "PASS" if "PASS" in v.split() else "GAPS REMAIN"


GATE_QS = [
    ("Prior knowledge", "What can the student already do? (languages / tools they know)"),
    ("Starting level (1-10)", "How much does the student already know about THIS subject? "
     "1 = absolute zero (teach the language/tool from scratch as its own chapters), 10 = expert (advanced material only)"),
    ("Breadth (1-10)", "How much of the topic's surface? 1 = one tight path to the objective, 10 = the whole territory"),
    ("Lesson depth (1-10)", "How deep does each lesson dig? 1 = just use it, 10 = internals and edge cases"),
    ("Mastery (1-5)", "Where must the student stand after the last chapter? 1 = acquainted, 5 = expert"),
    ("Tooling", "internal (in-browser only), external (teach real tools), or both?"),
]

# How the three dials steer the arc — written into the plan so every phase reads the same
# semantics instead of re-interpreting three bare numbers.
DIALS_NOTE = """\
- **Starting level** (see Starting level below) fixes where teaching BEGINS — how much the
  student already knows about THIS subject. Low = teach the course's own language/tool from
  zero as its own early chapters; high = skip fundamentals. It pairs with Prior knowledge,
  which names WHAT they already know. A low starting level ADDS chapters — there is no cap.
- **Breadth** shapes the SECTION LIST: how much of the topic's surface appears. 1 = the
  single tight path to the objective; 10 = the whole territory, side-paths included.
- **Lesson depth** shapes EACH LESSON: how far under the surface it digs. 1 = use the
  thing; 10 = internals, edge cases, why it works.
- **Mastery** (see Mastery target below) fixes the ENDPOINT — where the student stands
  after the final chapter. Breadth and depth spend the pages; mastery decides where the
  pages must ARRIVE. Material the student already has (see Prior knowledge) gets AT MOST
  one brief recap section, no matter how high breadth is.
- The concept is casual prose; these dials are the user's CALIBRATED intent. Where the
  two disagree (e.g. the concept says "from beginner" but prior knowledge + mastery say
  otherwise), THE DIALS WIN. Take the concept for topic and flavor, the dials for shape.
"""

# The mastery tick expanded into concrete sample end-state objectives — a cheap model
# can't misread an example the way it can misread an adjective. Written into the plan.
MASTERY_LEVELS = {
    1: ("ACQUAINTED", "The student ends able to READ and follow the topic, not yet work "
        "alone: explain the core ideas, run and modify provided examples, finish guided "
        "exercises. Sample end-state objectives: edit a provided script to change its "
        "behavior; explain what a given loop or lookup does; spot the obvious bug in five lines."),
    2: ("FUNCTIONAL", "Ends able to do the everyday basics unaided: build small things "
        "from scratch with the core constructs, read error messages, fix simple faults. "
        "Samples: write a small program that reads input and prints a computed result; "
        "use the basic collection types correctly; trace why a branch did or didn't run."),
    3: ("CAPABLE", "Ends able to solve real problems alone and CHOOSE between approaches. "
        "Samples: implement recursion where iteration hurts; pick a map over an array (or "
        "the reverse) and justify the tradeoff; decompose a fuzzy problem into functions; "
        "treat error handling as a design decision, not an afterthought."),
    4: ("ADVANCED", "Ends fluent in the topic's idioms and the internals that matter. "
        "Samples: wield the topic's power tools (e.g. generators/iterators, decorators/"
        "closures in a programming course); reason about complexity and performance; "
        "structure a multi-part project; read unfamiliar source to answer what the docs don't."),
    5: ("EXPERT", "Ends at the deep end: the machinery under the surface and the judgment "
        "to wield it. Samples: metaprogramming or the topic's equivalent under-the-hood "
        "layer; performance/memory models; concurrency where applicable; architect a "
        "substantial tool end to end and defend its design."),
}
MASTERY_CODA = """
These samples CALIBRATE the endpoint — they are not a syllabus. Translate them into THIS
course's topic, and spend the chapter budget so the FINAL chapters sit AT this level.

Adapt the samples to this topic's OWN difficulty landscape, not to generic computer
science. Before writing the section list:
1. Name, in the plan, the 3-6 concepts practitioners of THIS language/tool actually
   find hard and idiomatic at the target level — its REAL difficulty spine.
2. Build the advanced chapters toward THAT list. Where a sample above names a concept
   that is rare or unidiomatic here, swap it for this topic's equal-difficulty
   counterpart instead of teaching it anyway.
Calibration contrasts: nearly every language HAS recursion, but a Python course at
level 3 leans on iterators, comprehensions and dict-shaped design (recursion earns a
lesson, not a chapter), while a Lisp or Haskell course inverts that ratio; JavaScript's
hard spine is async/the event loop/closures; Rust's is ownership and borrowing; C's is
pointers and memory; SQL's is joins, aggregation and window functions. Weight the
course toward what is hard AND used HERE."""

# The starting-level tick expanded into concrete instructions — mirror of MASTERY_LEVELS but
# for where teaching BEGINS. Low ticks force the course's own language/tool to be taught from
# zero as its own chapters, so a "teach me X in Python" course for a non-programmer actually
# teaches Python instead of assuming it. Written into the plan.
PRIOR_LEVELS = {
    1: ("FROM ZERO", "The student has never programmed. The course's OWN language/tool is taught "
        "from the absolute basics — install it, run the first program, variables, control flow — "
        "as its OWN early chapters BEFORE any domain work. Assume NOTHING, not even that they know "
        "what the language is."),
    2: ("NEAR ZERO", "Has glimpsed code but cannot write it. Still teach the language from basics "
        "as its own chapters; move only slightly faster than level 1."),
    3: ("RANK BEGINNER", "Can copy and tweak examples in some language. Teach THIS course's language "
        "from the ground up as its own chapters, but the idea of a variable or loop need not be "
        "introduced as brand-new."),
    4: ("OTHER-LANGUAGE CODER", "Comfortable in at least ONE other language, but NOT this course's. "
        "Give this language its own fast on-ramp chapter(s) — syntax, toolchain, how to run it — then "
        "proceed. Do NOT assume they know this language's syntax or standard library."),
    5: ("GENERALIST", "Solid general coding experience across languages, but not necessarily this "
        "exact stack. A brisk language/tooling primer (one focused chapter on what differs from what "
        "they likely know), then straight into the domain."),
    6: ("ADJACENT", "Knows this language's neighborhood or an adjacent stack. A short recap of the "
        "specific tools this course uses, then domain work — no from-zero language teaching."),
    7: ("PRACTITIONER", "Already uses this language/stack. Skip fundamentals; open at the domain. "
        "Recap only the exact APIs the course leans on, in context."),
    8: ("FLUENT", "Fluent in the language and its ecosystem. No primers — begin at the real work; "
        "assume idioms and the standard library are known."),
    9: ("ADVANCED", "Deep in this exact domain already. Go straight to advanced material; assume "
        "everything short of the course's frontier."),
    10: ("EXPERT", "Near-mastery of the subject. Teach ONLY the sharp edge — advanced, non-obvious, "
        "and frontier material; assume all else."),
}
PRIOR_CODA = """
This fixes where teaching BEGINS (Mastery fixes where it ends). Read it against the concept: if
the concept names a language or tool the student does NOT already know (per this level and the
Prior-knowledge note), that language's fundamentals and toolchain are THEIR OWN early chapters —
never assumed away or folded into one artifact's build. There is NO maximum chapter count; a
from-zero course simply needs more chapters than an expert's. Size the arc to the gap.
"""

# The gate's Tooling choice expanded into the rules the author-AI must honor — written
# into the plan (which every phase reads) so it steers all phases. The validator enforces
# the mechanical half (see validate_tome.py --tooling); this is the rest, via the prompt.
TOOLING_POLICY = {
    "internal": ("INTERNAL (in-browser only)",
        "Every workbench is the built-in browser editor — do NOT set `externalWorkspace`. The "
        "course must need NO external download or install: never tell the student to fetch, "
        "install, or run an external program, IDE, or toolchain, and never assume one is present. "
        "(They may still opt into their own editor via USE MY OWN EDITOR, but write the course as "
        "if in-browser.) Every lab runs in the engine's own runtime."),
    "external": ("EXTERNAL (teach the real tools)",
        "The course MUST teach how to install and use the real external tools the topic needs — "
        "name them in section 1 with `[[lessons.readings]]` links (mark mandatory/optional). Where "
        "the real toolchain cannot run in the browser, set `externalWorkspace = true` (§5) and make "
        "the workbenches external; an in-browser workbench is fine only where genuinely applicable. "
        "Never simulate away the real skill."),
    "both": ("BOTH (internal + external available)",
        "Both in-browser and real external tools must be available to the student. Teach the real "
        "external tools — name them in section 1 with `[[lessons.readings]]` links. Workbenches may "
        "be internal or external per topic: set `externalWorkspace = true` only where the real "
        "toolchain needs it; otherwise keep the in-browser workbench while STILL teaching the "
        "external tools."),
}


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
    """Write the Phase-0 plan file — the one format both gate paths share."""
    with open(plan_path, "w", encoding="utf-8") as f:
        f.write(f"# BUILD PLAN — {tid}\n\n")
        if concept:
            f.write("## Concept\n" + concept.strip() + "\n\n")
        f.write("## Gate answers (Phase 0)\n")
        for k, v in answers:
            if v:   # an unanswered dial is omitted, not written as an empty line
                f.write(f"- **{k}:** {v}\n")
        if any(v for k, v in answers if k.startswith(("Breadth", "Lesson depth", "Mastery"))):
            f.write("\n## Course dials — how to read them\n" + DIALS_NOTE)
        m = next((v for k, v in answers if k.startswith("Mastery")), "")
        try:
            lvl = MASTERY_LEVELS.get(int(str(m).strip()))
        except (ValueError, TypeError):
            lvl = None
        if lvl:
            f.write(f"\n## Mastery target — {str(m).strip()}/5: {lvl[0]}\n{lvl[1]}{MASTERY_CODA}\n")
        p = next((v for k, v in answers if k.startswith("Starting level")), "")
        try:
            plvl = PRIOR_LEVELS.get(int(str(p).strip()))
        except (ValueError, TypeError):
            plvl = None
        if plvl:
            f.write(f"\n## Starting level — {str(p).strip()}/10: {plvl[0]}\n{plvl[1]}{PRIOR_CODA}\n")
        pol = TOOLING_POLICY.get(next((v.lower() for k, v in answers if k == "Tooling"), ""))
        if pol:
            f.write(f"\n## Tooling policy — {pol[0]}\n{pol[1]}\n")
        f.write("\n## Arc (Phase 1 fills this in, later phases read it)\n")


def do_gate(plan_path, tid, concept=None):
    """Phase 0 is interactive by design — the harness asks the user, no agent involved."""
    print("\n=== Phase 0 — GATE: three questions (the harness asks YOU) ===")
    ans = [(k, input(f"  {q}\n  > ").strip()) for k, q in GATE_QS]
    write_plan(plan_path, tid, ans, concept)
    print(f"  -> wrote {plan_path}\n")


def do_gate_json(plan_path, tid, gate_json, concept=None):
    """Phase 0 without a terminal (web-launched): the gate answers arrive as JSON."""
    try:
        g = json.loads(gate_json)
    except json.JSONDecodeError as e:
        sys.exit(f"--gate-json is not valid JSON: {e}")
    ans = [(label, str(g.get(key, "")).strip()) for (label, _), key in
           zip(GATE_QS, ("prior_knowledge", "prior_level", "breadth", "depth", "mastery", "tooling"))]
    write_plan(plan_path, tid, ans, concept)
    print(f"=== Phase 0 — GATE: answers taken from --gate-json ===\n  -> wrote {plan_path}\n")
