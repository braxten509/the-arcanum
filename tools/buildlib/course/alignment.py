"""One-to-one alignment between sealed course-map nodes and authored tome files."""
import os
import tomllib

from ..course_map import load_course_map
from ..language_mastery import authored_mastery_problems
from ..mechanism_contract import authored_problems as authored_mechanism_problems


def actual_lesson_id(node_id):
    return str(node_id).replace(".", "-", 1)


def validate_tome_alignment(build_id, tome_path, through=None):
    course = load_course_map(build_id)
    try:
        with open(os.path.join(tome_path, "tome.toml"), "rb") as handle:
            manifest = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return False, f"course-map alignment cannot read tome.toml: {exc}"
    declared = [str(value) for value in ((manifest.get("content") or {}).get("sections") or [])]
    expected = [section["id"] for section in course["sections"]]
    problems = []
    if declared != expected:
        problems.append(f"manifest section ids {declared} do not match sealed map ids {expected}")
    selected = course["sections"]
    if through in expected:
        selected = selected[:expected.index(through) + 1]
    try:
        import tome_layout
    except ModuleNotFoundError:
        from tools import tome_layout
    for section in selected:
        sid = section["id"]
        try:
            actual = tome_layout.load_section(tome_path, sid)
        except Exception as exc:
            problems.append(f"{sid} cannot load for map alignment: {exc}")
            continue
        planned_lessons = [node for node in section["nodes"] if node["kind"] == "lesson"]
        actual_lessons = actual.get("lessons") or []
        actual_ids = [str(lesson.get("id") or "") for lesson in actual_lessons
                      if isinstance(lesson, dict)]
        planned_ids = [actual_lesson_id(node["id"]) for node in planned_lessons]
        if actual_ids != planned_ids:
            problems.append(f"{sid} lesson ids {actual_ids} do not map one-to-one to {planned_ids}")
        for node, lesson in zip(planned_lessons, actual_lessons):
            if isinstance(lesson, dict) and list(lesson.get("teaches") or []) != list(node["teaches"]):
                problems.append(f"{node['id']} teaches drifted from the sealed map")
        working = next(node for node in section["nodes"] if node["kind"] == "working")
        freestyle = actual.get("freestyle") or {}
        if not isinstance(freestyle, dict):
            problems.append(f"{sid}.working has no [freestyle] owner")
        elif list(freestyle.get("requires") or []) != list(working["requires"]):
            problems.append(f"{sid}.working requires drifted from the sealed map")
        elif list(freestyle.get("masteryPerformances") or []) != list(
                working.get("masteryPerformances") or []):
            problems.append(f"{sid}.working mastery performances drifted from the sealed map")
        problems += authored_mechanism_problems(course, actual, sid)
    problems += authored_mastery_problems(course, tome_path, through)
    return (not problems, "" if not problems else "course-map alignment:\n- " + "\n- ".join(problems))
