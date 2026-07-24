"""Warm-session continuation and operator-interruption prompts."""

LESSON_BATCH_INSTRUCTION = (
    "Use TWO COHERENT AUTHORING BATCHES for this section. In the first turn, "
    "research the section's external facts, then author EVERY sealed planned "
    "lesson completely in one batch. Stop after all lesson files without "
    "authoring the Working, assessment, handoff, or progress marker. The "
    "harness returns you to this same session once, retaining the bounded "
    "context. In the second turn, author the Working, assessment, and handoff "
    "together, then use the exact mechanical-check and marker instructions "
    "below.")


def continue_prompt(build_id, unit, *, label, unit_prompt,
                    mechanical_validation_prompt):
    """Return an author to the same unit without rerendering section context."""
    if unit["kind"] != "section":
        return (
            f"You stopped before handing off {label(unit)}. Finish only that "
            "unit, set its progress marker to validating, and stop.\n\n"
            + unit_prompt(build_id, unit))
    marker = (
        "python3 tools/workflow/report_section_progress.py "
        f"{build_id} {unit['section']} {unit['index']} {unit['total']} "
        "validating")
    return (
        f"Continuing {label(unit)} in the same bounded session. Do not "
        "rerender the section context, reread the phase guide, or repeat "
        "discovery. Verify that every sealed planned lesson is complete. If "
        "an interrupted first batch left any lesson incomplete, finish ALL "
        "remaining lessons together and stop again before the Working. "
        "Otherwise author the Working, assessment, and handoff together, then "
        f"{mechanical_validation_prompt(build_id, unit)} Then run exactly "
        f"`{marker}` and stop so the harness can validate the complete section.")


def interrupted_prompt(message, unit):
    """Deliver operator guidance without replacing the active assignment."""
    resume = (
        "Respond to the operator, then continue the exact assignment that was "
        "interrupted in this same session. Preserve partial edits and the "
        "existing repair packet. Do not restart the unit or regenerate its "
        "initial context. Only this active turn was interrupted to deliver the "
        "operator message; do not attribute an earlier validation result to an "
        "interruption unless the transcript explicitly records one.")
    if unit["kind"] == "section":
        resume += (
            " In particular, do not rerun render_section_context.py or repeat "
            "initial discovery; continue from the cited repair files and "
            "current on-disk state.")
    return f"{str(message or '').strip()}\n\n{resume}"
