"""Prompt and durable conversation helpers for a tome author session."""
import json
import os
import time

from ...workflow.prompts import LEARNER_CONSTRUCTION_INSTRUCTION


def json_path(build_dir, build_id, suffix):
    return os.path.join(build_dir, f"{build_id}.{suffix}.json")


def write_json(path, value):
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
    os.replace(temp, path)


def append_conversation(build_dir, build_id, kind, text, **extra):
    text = str(text or "").strip()
    if not text:
        return
    row = {"at": time.time(), "kind": kind, "text": text, **extra}
    path = json_path(build_dir, build_id, "conversation") + "l"
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def load_conversation(build_dir, build_id, limit=120):
    path = json_path(build_dir, build_id, "conversation") + "l"
    try:
        with open(path, encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
    except (OSError, ValueError):
        return []
    return rows[-max(1, int(limit)):]


def author_prompt(build_id, concept, tooling, from_phase=1):
    plan = f".tome-build/{build_id}.plan.md"
    return f"""You are the active unit author of one complete Arcanum tome. This is an
interactive, resumable author session. Retain context while authoring and repairing the currently
assigned unit. Phase 1 and Phase 2 may share their planning session; after that, the harness starts
a fresh session after every validated phase or Phase-3 section. The operator may pause you and
later send guidance while your current unit session is active.

BUILD ID: {build_id}
CURRENT TOME ID: {build_id} (Phase 2's transition command may rename it; follow its output.)
CONCEPT: {concept}
TOOLING: {tooling}
PLAN: {plan}
START OR RESUME AT PHASE: {from_phase}

Read `tome-workflow/single-author.md` now. At the start of each phase, read only that phase's
guide under `tome-workflow/` plus the references it explicitly names. Files on disk are truth.

NON-NEGOTIABLE LEARNER CONSTRUCTION: {LEARNER_CONSTRUCTION_INSTRUCTION}

Work on exactly the phase or Phase-3 section named in the final instruction. When it is authored,
run only the exact self-check command given in that assignment once. If it reports findings, stop
with `HARNESS_REPAIR_REQUIRED:` so the harness can aggregate and return one bounded repair packet.
When the check exits cleanly, set that unit's progress marker to `validating` and end your turn. Do not invent
ad-hoc substitutes, run a deterministic phase transition, or begin the next unit. The harness
independently runs the unit's mechanical gate while you are stopped, then its mandatory Validator
AI gate for Phase 1, Phase 2, or a Phase-3 section. It checkpoints only a fully clean unit, returns
failures to this unit's warm repair session, and assigns clean successors to a fresh session.
Preserve correct
work already on disk and honor earlier phase contracts as immutable inputs.

If the assigned self-check crashes before it can report structured `ERROR` or `WARN` findings,
do not rerun it and do not edit repository tooling. Answer once with `HARNESS_BLOCKED:` plus the
raw bootstrap diagnostic, then stop. The harness will independently reproduce that exact check:
structured findings return as an ordinary repair packet, while a reproduced infrastructure crash
pauses and retries mechanically after resume without starting another author turn.

Continue this checkpoint cycle until the harness ends this unit session or reaches Phase 8.
Do not spawn another author or reviewer yourself.
If the operator selected an independent reviewer, the harness will start it only after your final
Phase 8 gate passes. Do not perform or impersonate that optional independent review. Do not
merely describe work: edit the tome, report `validating`, and stop at the assigned boundary.
"""


def continuation_prompt(_build_id):
    """A resumed CLI already owns the full author conversation and workflow contract."""
    return "Continue."


def harness_blocked_message(text):
    return str(text or "").lstrip().startswith("HARNESS_BLOCKED:")


def repair_required_message(text):
    return str(text or "").lstrip().startswith("HARNESS_REPAIR_REQUIRED:")
