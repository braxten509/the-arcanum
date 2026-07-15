"""Phase-0 answers and the calibrated build plan given to the sole author."""
import json
import re
import sys

from .checkpoints import ARC_CONTRACT, ARC_HEADING


GATE_QS = [
    ("Prior knowledge", "What can the student already do?"),
    ("Starting level (1-10)", "How much does the student know about this subject?"),
    ("Breadth (1-10)", "How much of the topic's surface should enter the course?"),
    ("Lesson depth (1-10)", "How deeply should each included mechanism be taught?"),
    ("Mastery (1-5)", "Where must the student stand after the last chapter?"),
    ("Tooling", "internal, external, or both?"),
]

MASTERY_LEVELS = {
    1: ("ACQUAINTED", "Can explain core ideas and modify guided examples."),
    2: ("FUNCTIONAL", "Can build small everyday examples and repair simple faults unaided."),
    3: ("CAPABLE", "Can solve real problems independently and justify taught choices."),
    4: ("ADVANCED", "Can use important idioms, internals, and power tools fluently."),
    5: ("EXPERT", "Can reason about the machinery and architect a substantial solution."),
}

PRIOR_LEVELS = {
    1: ("FROM ZERO", "Assume only stated prior knowledge; teach setup, first run, and every required construct from first principles."),
    2: ("NEAR ZERO", "Cover level-1 fundamentals with less repetition, never fewer concepts."),
    3: ("BEGINNER", "Teach the subject from the ground up and introduce every construct before use."),
    4: ("TRANSFER LEARNER", "Compress only transferable concepts supported by prior knowledge."),
    5: ("GENERALIST", "Assume general practice, not subject expertise; teach focused foundations."),
    6: ("ADJACENT", "Bridge the stated neighboring experience to this subject explicitly."),
    7: ("PRACTITIONER", "Assume routine fundamentals; introduce course-specific APIs and constraints."),
    8: ("FLUENT", "Focus on integration, tradeoffs, and failure modes; teach uncommon material."),
    9: ("ADVANCED", "Focus on internals, architecture, edge cases, and difficult tradeoffs."),
    10: ("EXPERT", "Treat the learner as a peer and teach only relevant non-obvious material."),
}

TOOLING_POLICY = {
    "internal": ("INTERNAL (in-browser only)", "Use the browser workbench only; do not require downloads or externalWorkspace."),
    "external": ("EXTERNAL (teach the real tools)", "Teach the real toolchain from install through diagnostics and delivery."),
    "both": ("BOTH (internal + external available)", "Support the browser workbench and the complete real-tool path."),
}


def gate_errors(answers):
    values = {label: str(value or "").strip() for label, value in answers}
    errors = []
    if not values.get("Prior knowledge"):
        errors.append("Prior knowledge is required; use 'none' when appropriate")
    for label, maximum in (("Starting level (1-10)", 10), ("Breadth (1-10)", 10),
                           ("Lesson depth (1-10)", 10), ("Mastery (1-5)", 5)):
        raw = values.get(label, "")
        try:
            number = int(raw)
        except ValueError:
            number = 0
        if str(number) != raw or not 1 <= number <= maximum:
            errors.append(f"{label} must be a whole number from 1 to {maximum}")
    if values.get("Tooling", "").lower() not in TOOLING_POLICY:
        errors.append("Tooling must be exactly internal, external, or both")
    return errors


def read_tooling(plan_path):
    try:
        text = open(plan_path, encoding="utf-8").read()
    except OSError:
        return None
    match = re.search(r"(?im)^- \*\*Tooling:\*\*\s*(\w+)", text)
    value = match.group(1).lower() if match else None
    return value if value in TOOLING_POLICY else None


def write_plan(plan_path, tid, answers, concept=None):
    values = {key: str(value).strip() for key, value in answers}
    start = int(values["Starting level (1-10)"])
    mastery = int(values["Mastery (1-5)"])
    tooling = values["Tooling"].lower()
    with open(plan_path, "w", encoding="utf-8") as handle:
        handle.write(f"# BUILD PLAN — {tid}\n\n")
        if concept:
            handle.write("## Concept\n" + concept.strip() + "\n\n")
        handle.write("## Build contract\n- **Proof contract:** 1\n\n## Gate answers (Phase 0)\n")
        for key, value in answers:
            handle.write(f"- **{key}:** {value}\n")
        handle.write("\n## Calibration contract\n")
        handle.write(f"- **Start {start}/10 — {PRIOR_LEVELS[start][0]}:** {PRIOR_LEVELS[start][1]}\n")
        handle.write("- **Assumption boundary:** Prior knowledge is an exhaustive whitelist, not evidence that nearby skills are safe to assume.\n")
        if start <= 3:
            handle.write("- **First-use rule for Start 1–3:** Before required use, every unlisted keyword, syntax form, operator, API, tool action, or term needs a plain-language purpose, stepwise anatomy, a minimal worked example with observable output, one likely failure, and guided practice.\n")
        handle.write(f"- **Breadth {values['Breadth (1-10)']}/10:** controls which topic domains enter the arc, not chapter count.\n")
        handle.write(f"- **Depth {values['Lesson depth (1-10)']}/10:** controls how far each mechanism is explained, debugged, and qualified.\n")
        handle.write(f"- **Finish {mastery}/5 — {MASTERY_LEVELS[mastery][0]}:** {MASTERY_LEVELS[mastery][1]}\n")
        handle.write(f"- **Tooling — {TOOLING_POLICY[tooling][0]}:** {TOOLING_POLICY[tooling][1]}\n")
        handle.write("- These answers override casual scope adjectives. Phase 1 converts them into the difficulty spine, graduate boundary, lifecycle, acceptance proof, and section arc.\n")
        handle.write("\n" + ARC_HEADING + ARC_CONTRACT)


def do_gate(plan_path, tid, concept=None):
    while True:
        answers = [(label, input(f"{question}\n> ").strip()) for label, question in GATE_QS]
        errors = gate_errors(answers)
        if not errors:
            break
        print("\n".join(f"- {error}" for error in errors))
    write_plan(plan_path, tid, answers, concept)


def do_gate_json(plan_path, tid, gate_json, concept=None):
    try:
        values = json.loads(gate_json)
    except json.JSONDecodeError as exc:
        sys.exit(f"--gate-json is not valid JSON: {exc}")
    if not isinstance(values, dict):
        sys.exit("--gate-json must be an object")
    keys = ("prior_knowledge", "prior_level", "breadth", "depth", "mastery", "tooling")
    answers = [(label, str(values.get(key, "")).strip())
               for (label, _), key in zip(GATE_QS, keys)]
    errors = gate_errors(answers)
    if errors:
        sys.exit("--gate-json is invalid:\n- " + "\n- ".join(errors))
    write_plan(plan_path, tid, answers, concept)
    print(f"Phase 0 setup recorded in {plan_path}")
