"""Every word the Binder is sent. Kept apart from the runner that sends it.

The prose here is the Binder's whole specification -- what it may touch, which gate it is
measured by, what a finished turn looks like. It is edited far more often than the control
flow around it, and reading it as one block is the only way to see whether it still says
one consistent thing.
"""
import os

from ...config import ROOT

STANDARD_UPDATE = (
    "\n\nSTANDARD UPDATE: Compare this tome with the CURRENT repository standards: the "
    "validator implementation used by tools/validate_tome.py and all applicable Markdown "
    "authoring instructions at the repository root and under tome-authoring/. Bring forward "
    "any file versions, fields, structures, or instructions that have changed since this tome "
    "was authored. Use the current validator and current Markdown instructions as authoritative. "
    "Make only the compatibility changes actually needed; if the tome is already current in a "
    "given regard, leave it unchanged in that regard. Do not rewrite correct content merely for "
    "style. Never add or partially imitate an opt-in contract such as [mastery] evidenceVersion "
    "when the tome does not already declare it. Do not relax any progress-preservation boundary "
    "below.\n\n")


def continuation(prompt, why):
    return (prompt + "\n\n===== HARNESS CONTINUATION TURN =====\n"
            f"Your previous turn ended before you finished ({why}). Every edit you had "
            "already written is still on disk exactly as you left it, and this turn is a "
            "direct continuation of it, not a retry. Do NOT start over and do NOT undo "
            "your own work: read the tome's current state first, work out which parts of "
            "the request above you already completed, and finish what remains.")


def repair(prompt, report):
    return (prompt + "\n\n===== HARNESS REPAIR TURN =====\n"
            "The independent validator failed. Read every finding below, repair "
            "all in-scope failures without undoing the requested amendment, rerun "
            "the validator yourself until clean, then stop.\n\n" + report)


def _validation_command(jid, plan_rel, strict_flag):
    command = f"`python3 tools/validate_tome.py tomes/{jid}{strict_flag}`"
    if not plan_rel:
        return command
    # validate_tome does no sealed-map alignment and pools every section together, so a tome
    # can pass it and still be unshippable. Naming only that command taught the Binder to
    # certify its own work against a gate that cannot see half the contract it is held to.
    return command + (
        f" and then `python3 tools/validate_phase3.py tomes/{jid} --plan {plan_rel}"
        f"{strict_flag}` — that second one is the gate that decides whether the tome "
        "ships, and it is the one the harness repeats. The harness also re-runs each "
        f"section's own gate (`python3 tools/validate_section.py tomes/{jid} sNN --plan "
        f"{plan_rel} --source-only`); run that yourself for any section it names, because "
        "a defect confined to one section — answer-position clustering is the usual one — "
        "is averaged away by the whole-tome pass and never appears above")


def _handoff_note(handoffs, plan_rel):
    if not (handoffs and plan_rel):
        return ""
    return (
        f"\n\nCONTINUITY HANDOFFS: {os.path.relpath(handoffs, ROOT)}/sNN.json is one file per "
        "section recording what the learner's project looks like when that section ends. They "
        "are writable and they are part of the shipping gate: any whose `artifact_state` is "
        "blank or under 20 characters FAILS validate_phase3. If the gate reports one, write it "
        "from what that section actually builds — the files that exist by then and the state "
        "they are in. Never describe progress the tome does not teach.\n\n")


def _bounds(jid, reset_ok):
    """What the agent may and may not touch.

    reset_ok lifts ONLY the progress-preserving rules (rename/restructure); the engine,
    other-tome, and generated-output walls always hold.
    """
    if reset_ok:
        return (f"EDIT only under tomes/{jid}/ (READING anything in the repo is expected — the guides "
                "live at the root). The player has AUTHORIZED a progress-resetting rework for this "
                "run: you MAY add, remove, reorder, and renumber sections and lessons and rename ids or "
                "files as the change needs — this OVERRIDES the guides' rule against renaming ids/files. "
                "Keep the tome internally consistent (fix every cross-reference, the tome.toml section "
                "list, badges, and chapter numbers you move). You must STILL never touch engine code, "
                "skins/, or other tomes, and never edit save/ or hand-edit generated/. A trusted "
                "repository generator may update its own generated output when an in-scope source "
                "change requires it; inspect and validate that output.")
    return (f"EDIT only under tomes/{jid}/ (READING anything in the repo is expected — the guides "
            "live at the root). Progress is keyed by ids, so ADDING content with new "
            "tome-unique ids is always allowed and progress-safe — new exercises, new lessons "
            "(the next lNN.toml), even a new section APPENDED to the end of [content].sections "
            "with its full kit. But never rename, renumber, remove, or reorder EXISTING ids or "
            "files (that wipes player progress), never insert a section mid-list, never touch "
            "engine code, skins/, or other tomes, never edit save/ or hand-edit generated/. "
            "A trusted repository generator may update its own generated output when an in-scope "
            "source change requires it; inspect and validate that output.")


def _review(jid, req, report_rel, validation):
    focus = f"The player asks the review to focus especially on:\n\n{req}\n\n" if req else ""
    # A review that never runs the shipping gate reports a clean validator on a tome the
    # gate rejects, and the player commissions changes against a survey that missed the
    # blockers. Reading is all a review may do -- so it must read the gate's verdict too.
    measured = (
        f"MEASURE the tome, do not only read it: run {validation}. Report what each one "
        "actually says. A clean tools/validate_tome.py is NOT evidence the tome ships — it "
        "performs no sealed-course-map alignment and pools every section's question bank "
        "together, so map drift and one section's answer-position clustering are both "
        "invisible to it. Any blocker those gates report belongs in the recommendation "
        "order at the top, named as a blocker.\n\n")
    return (
        "You are THE BINDER — a maintenance agent for the Arcanum course platform, in "
        f"REVIEW mode on the course (tome) at tomes/{jid}/.\n\n"
        "FIRST read BOTH guides at the repo root: course-configuration-guide.md (the file/"
        "field map and hard rules) and course-improvement-guide.md (the rubric for what makes "
        f"a tome strong and where weaknesses hide). Then survey tomes/{jid}/ against them and "
        "write a well-organized markdown report of everything you find — flaws, weak spots, "
        f"inconsistencies, and the changes you would recommend, most important first.\n\n{measured}"
        f"{focus}"
        "After the title and brief review metadata, the FIRST substantive section MUST be "
        "`## Recommendation and implementation order`. Make that one section self-contained: "
        "state the tome's important strengths and validator status without letting a clean "
        "validator minimize substantive weaknesses; name EVERY material recommended workstream "
        "(all Critical and High findings, plus any Medium or Low work that belongs in the plan); "
        "and give one numbered, dependency-aware implementation order. Rank learner privacy, "
        "correctness, teaching integrity, and valid assessment evidence above compatibility or "
        "cosmetic conservatism. Recommend broad correction when the evidence warrants it. "
        "Progress-safety constraints should shape implementation, not suppress or downgrade a "
        "real finding. Do not split the overall recommendation into a later `Top findings`, "
        "`Recommended implementation order`, or closing-summary section. In the detailed "
        "findings below it, label finding-specific actions `Remediation`, never `Recommended "
        "change`, so they cannot be mistaken for the report's overall recommendation. "
        f"Write that report to {report_rel} (create the folder if needed) — that report is the "
        "ONLY file you may create or change. Do NOT edit anything else: no course files, no "
        "engine code, nothing under tomes/. Read files with whatever tools your harness provides "
        "(shell reads are fine where shell is your file interface); trusted repository Python "
        "tools may be executed when they help verify a finding.")


def _iterate(jid, req, standard, handoff, bounds, validation):
    focus = f"The player asks you to focus especially on:\n\n{req}\n\n" if req else ""
    return (
        "You are THE BINDER — a maintenance agent for the Arcanum course platform, in "
        f"ITERATE mode on the course (tome) at tomes/{jid}/.\n\n"
        "FIRST read course-improvement-guide.md and course-configuration-guide.md. Follow the "
        "improvement guide's conditional reference routing and consult the relevant tome-authoring/ "
        f"documents for the fields and contracts you touch. Then survey tomes/{jid}/ against the rubric, "
        "choose the HIGHEST-VALUE improvements you can make, and apply them, editing as many "
        f"files as it takes. {focus}{standard}{handoff}"
        f"{bounds} Read and edit files with whatever tools your harness provides — if shell "
        "commands are how you read or edit files, use them freely; you may also run trusted "
        "repository Python validators and inspection tools. "
        f"Before returning, run {validation}, read the complete "
        "report, and repair it until it exits cleanly with no new warnings. The harness repeats "
        "that check independently after you return. "
        "End with one short paragraph naming exactly the file(s) you changed and what you improved.")


def _change(jid, req, broad, review_path, standard, handoff, bounds, validation):
    ask = ("requests a broad change — a larger rework you can iterate on"
           if broad else "requests one small change")
    how = ("make the changes needed to fulfil the request, editing as many files as it takes"
           if broad else "make the SMALLEST edit that fulfils the request")
    ledger = (f"A review of this tome was just written to {review_path} — read it first; "
              "the request may refer to its findings.\n\n" if review_path else "")
    return (
        "You are THE BINDER — a maintenance agent for the Arcanum course platform. "
        f"The player of the course (tome) at tomes/{jid}/ {ask}:\n\n"
        f"REQUEST: {req}\n\n{ledger}"
        "If the request is actually a QUESTION — asking for information, an explanation, or "
        "advice, rather than instructing a change — answer it in your final message and make "
        "NO edits to the tome. Only proceed to change files if the request asks for a change.\n\n"
        "FIRST read course-configuration-guide.md at the repo root — it maps every file and "
        f"field you may touch and the rules that bind them. Then {how}. {standard}{handoff}"
        f"{bounds} Read and edit files with whatever tools your harness provides — if shell "
        "commands are how you read or edit files, use them freely; you may also run trusted "
        "repository Python validators and inspection tools. Before returning, run "
        f"{validation}, read the complete report, and repair it "
        "until it exits cleanly with no new warnings; the harness repeats the check independently. End with one "
        "short paragraph naming exactly the file(s) and field(s) you changed.")


def _access(jid, review, report_rel, handoffs):
    if review:
        return f"only {report_rel} is writable for this review."
    handoff_clause = (f" and so are its continuity handoffs at {os.path.relpath(handoffs, ROOT)}/"
                      if handoffs else "")
    return (f"the complete tome at tomes/{jid}/ is writable{handoff_clause}; other project "
            "paths are read-only. The sealed course map is mounted read-only on purpose — it "
            "is the contract you are measured against, so when the tome and the map disagree, "
            "the tome is what you change.")


def amend_prompt(jid, req, *, review, iterate, broad, reset_ok, update_standard,
                 review_path, report_rel, plan_rel, handoffs):
    """The complete instruction for one Binder run, in whichever mode it was asked for."""
    standard = STANDARD_UPDATE if update_standard else ""
    validation = _validation_command(jid, plan_rel, " --strict" if update_standard else "")
    handoff = _handoff_note(handoffs, plan_rel)
    bounds = _bounds(jid, reset_ok)
    if review:
        prompt = _review(jid, req, report_rel, validation)
    elif iterate:
        prompt = _iterate(jid, req, standard, handoff, bounds, validation)
    else:
        prompt = _change(jid, req, broad, review_path, standard, handoff, bounds, validation)
    return prompt + (
        f"\n\nAI ACCESS: The repository root is {ROOT}. You may read files and execute trusted "
        "Python anywhere in this repository, use web search/fetch for current sources, and "
        "use /tmp freely. Project writes are enforced by the harness: "
        + _access(jid, review, report_rel, handoffs))
