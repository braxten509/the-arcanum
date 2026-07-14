"""Phase-3 authored-completion checks that distinguish active work from future scaffolds.

The ordinary non-strict validator deliberately tolerates Phase-2 TODOs while a tome is being
authored.  These checks provide the missing scope: one warm section gate rejects scaffolding in
its owning section, while the final Phase-3 gate applies the same contract to the complete Arc.
"""
import os
import re

from . import PLACEHOLDER_RE

import tome_layout


MIN_LESSONS = 3
MIN_EXERCISES = 4
MIN_BODY_WORDS = 180
PHASE3_PLACEHOLDER = "phase3-placeholder"


def _walk_strings(value, at=""):
    if isinstance(value, str):
        yield at or "(top level)", value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_strings(child, f"{at}.{key}" if at else str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_strings(child, f"{at}[{index}]")


def section_completion_problems(section, sid):
    """Return blockers proving that ``sid`` still contains Phase-2/thin scaffolding."""
    if not isinstance(section, dict):
        return [f"{sid}: section data is not a table"]
    problems = []
    placeholders = [at for at, value in _walk_strings(section)
                    if PLACEHOLDER_RE.search(value)]
    if placeholders:
        shown = ", ".join(placeholders[:5])
        more = f" (+{len(placeholders) - 5} more)" if len(placeholders) > 5 else ""
        problems.append(f"{sid}: authored fields still contain TODO/FIXME/placeholder text at "
                        f"{shown}{more}")

    lessons = [lesson for lesson in (section.get("lessons") or [])
               if isinstance(lesson, dict)]
    if len(lessons) < MIN_LESSONS:
        problems.append(f"{sid}: only {len(lessons)} lesson(s); Phase 3 requires at least "
                        f"{MIN_LESSONS}")
    for lesson in lessons:
        lid = lesson.get("id") or "?"
        exercises = [exercise for exercise in (lesson.get("exercises") or [])
                     if isinstance(exercise, dict)]
        if len(exercises) < MIN_EXERCISES:
            problems.append(f"{sid}: lesson {lid!r} has {len(exercises)} exercise(s); Phase 3 "
                            f"requires at least {MIN_EXERCISES}")
        words = len(re.sub(r"<[^>]+>", " ", str(lesson.get("body") or "")).split())
        if words < MIN_BODY_WORDS:
            problems.append(f"{sid}: lesson {lid!r} body has {words} visible words; Phase 3 "
                            f"requires at least {MIN_BODY_WORDS}")
        teaches = lesson.get("teaches") if isinstance(lesson.get("teaches"), list) else []
        if any(PHASE3_PLACEHOLDER in str(capability) for capability in teaches):
            problems.append(f"{sid}: lesson {lid!r} still teaches a Phase-2 placeholder capability")

    freestyle = section.get("freestyle")
    requires = freestyle.get("requires") if isinstance(freestyle, dict) else []
    if isinstance(requires, list) and any(
            PHASE3_PLACEHOLDER in str(capability) for capability in requires):
        problems.append(f"{sid}: freestyle still requires a Phase-2 placeholder capability")
    return problems


def load_section_completion(tome_path, sid):
    try:
        section = tome_layout.load_section(os.path.abspath(tome_path), sid)
    except Exception as exc:
        return [f"{sid}: cannot load section: {exc}"]
    return section_completion_problems(section, sid)


def tome_section_ids(tome_path):
    try:
        import tomllib
        with open(os.path.join(tome_path, "tome.toml"), "rb") as handle:
            manifest = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return []
    return [str(value) for value in ((manifest.get("content") or {}).get("sections") or [])]


def tome_completion_problems(tome_path, ids=None):
    ids = list(ids if ids is not None else tome_section_ids(tome_path))
    if not ids:
        return ["tome has no Phase-3 section ids"]
    return [problem for sid in ids for problem in load_section_completion(tome_path, sid)]
