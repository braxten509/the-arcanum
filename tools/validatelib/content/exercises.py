"""Per-exercise structural and learner-feedback checks."""
import re

from .. import EXERCISE_TYPES, err, warn


def check_exercise(ex, label, seen_ex):
    if not isinstance(ex, dict):
        err(label, "[[lessons.exercises]] entries must be tables")
        return
    exercise_id = ex.get("id")
    if not exercise_id:
        err(label, "an exercise is missing its id")
    elif exercise_id in seen_ex:
        err(
            label,
            f"exercise id {exercise_id!r} is duplicated — ids key saved "
            "progress and must be unique per tome")
    else:
        seen_ex.add(exercise_id)
    exercise_type = ex.get("type")
    if exercise_type not in EXERCISE_TYPES:
        err(
            label,
            f"exercise {exercise_id!r}: type {exercise_type!r} is not one "
            "of mc/text/fill/type/write")
        return
    if not str(ex.get("prompt", "")).strip():
        err(
            label,
            f"exercise {exercise_id!r}: prompt is required — the client "
            "renders it as the student's entire instruction for this trial")
    points = ex.get("points")
    if (not isinstance(points, (int, float)) or isinstance(points, bool)
            or points <= 0):
        err(
            label,
            f"exercise {exercise_id!r}: points must be a positive number — "
            "the engine pays e.points raw, so a missing one credits NaN and "
            "corrupts the purse")
    if exercise_type == "mc":
        choices = ex.get("choices")
        answer = ex.get("answer")
        if not isinstance(choices, list) or len(choices) < 2:
            err(
                label,
                f"mc {exercise_id!r}: choices must be an array with at least "
                "two options")
        elif any(
                not isinstance(choice, str) or not choice.strip()
                for choice in choices):
            err(
                label,
                f"mc {exercise_id!r}: every choice must be a non-empty string")
        elif len({
                choice.strip().casefold() for choice in choices
        }) != len(choices):
            err(
                label,
                f"mc {exercise_id!r}: choices must be distinct — duplicate "
                "options make the question ambiguous or reveal the answer")
        if not isinstance(answer, int) or isinstance(answer, bool):
            err(
                label,
                f"mc {exercise_id!r}: answer must be a 0-based integer index")
        elif isinstance(choices, list) and not 0 <= answer < len(choices):
            err(
                label,
                f"mc {exercise_id!r}: answer index {answer} is out of range "
                f"for {len(choices)} choices")
        if not str(ex.get("whyWrong", "")).strip():
            err(
                label,
                f"mc {exercise_id!r}: whyWrong is required — every mc must "
                "name the misconception its wrong answers betray (§3, the "
                "highest-value feedback channel)")
    elif exercise_type in ("text", "fill"):
        if not str(ex.get("answer", "")).strip():
            err(label, f"{exercise_type} {exercise_id!r}: answer is required")
        if exercise_type == "fill" and "____" not in str(ex.get("code", "")):
            err(
                label,
                f"fill {exercise_id!r}: code must contain the ____ blank the "
                "answer fills — without it the client renders a fill exercise "
                "with nothing to complete")
    elif exercise_type == "type":
        if not str(ex.get("code", "")).strip():
            err(
                label,
                f"type drill {exercise_id!r}: code (the text to retype) is "
                "required")
        repetitions = ex.get("reps")
        if (repetitions is not None
                and (not isinstance(repetitions, int)
                     or isinstance(repetitions, bool) or repetitions < 1)):
            err(
                label,
                f"type drill {exercise_id!r}: reps must be a positive integer "
                "when present")
    elif exercise_type == "write":
        has_regex = bool(str(ex.get("expectRe", "")).strip())
        if has_regex:
            try:
                re.compile(re.sub(
                    r"\(\?<(?=[A-Za-z])", "(?P<", str(ex["expectRe"])))
            except re.error as regex_error:
                err(
                    label,
                    f"write {exercise_id!r}: expectRe does not compile "
                    f"({regex_error}) — the engine builds new RegExp(expectRe, "
                    '"m") at grade time, so this lab is unwinnable')
        if "expect" in ex:
            if not str(ex["expect"]).strip():
                err(
                    label,
                    f"write {exercise_id!r}: expect is empty — unwinnable "
                    '(empty stdout reads as "(no output)")')
        elif not has_regex:
            err(
                label,
                f"write {exercise_id!r}: needs a non-empty expect or an "
                "expectRe")
    if exercise_type != "type" and not str(ex.get("hint", "")).strip():
        warn(
            label,
            f"exercise {exercise_id!r}: no hint (every exercise should have "
            "an exercise-specific one)",
            phase=3)
