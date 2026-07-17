"""The narrow Phase-2 skeleton boundary and Phase-0 tooling contract."""
import json
import re

from . import PLACEHOLDER_RE, err


_CAPABILITY_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def check_phase2_artifact_alignment(build_id, manifest, sections, plan_path):
    """Gate strict inventory against runtime, lifecycle, and proof-owned paths."""
    from buildlib.course_map import proposal_path
    from buildlib.course.dependencies import (
        external_workspace_capability_alignment_problems,
        validation_dependency_alignment_problems,
    )
    from buildlib.skeleton.integrity import phase2_alignment_problems
    try:
        with open(proposal_path(build_id), encoding="utf-8") as handle:
            proposal = json.load(handle)
        with open(plan_path, encoding="utf-8") as handle:
            plan_text = handle.read()
    except (OSError, json.JSONDecodeError) as exc:
        err("phase-2-artifacts", f"cannot read strict artifact inputs: {exc}")
        return
    for problem in phase2_alignment_problems(
            proposal.get("artifactContract"), plan_text, manifest, sections):
        err("phase-2-artifacts", problem)
    for problem in validation_dependency_alignment_problems(proposal, manifest):
        err("phase-2-dependencies", problem)
    for problem in external_workspace_capability_alignment_problems(proposal, manifest):
        err("phase-2-course-map", problem)


def check_phase2_skeleton(sections_data):
    """Require a useful stub, while mechanically preventing early course authoring."""
    taught = set()
    for index, section in enumerate(sections_data, 1):
        sid = str(section.get("id") or f"section-{index}")
        lessons = [lesson for lesson in (section.get("lessons") or [])
                   if isinstance(lesson, dict)]
        if len(lessons) != 1:
            err("phase-2-skeleton", f"{sid}: expected exactly 1 placeholder lesson, found "
                f"{len(lessons)} — Phase 3 authors the real 3–8 lesson section")
            continue
        lesson = lessons[0]
        body = str(lesson.get("body") or "")
        if not PLACEHOLDER_RE.search(body):
            err("phase-2-skeleton", f"{sid}: placeholder lesson body has no TODO/FIXME marker — "
                "do not author lesson prose during Phase 2")
        body_words = len(re.sub(r"<[^>]+>", " ", body).split())
        if body_words > 120:
            err("phase-2-skeleton", f"{sid}: placeholder lesson body is {body_words} words — "
                "Phase 2 stubs stay under 120; Phase 3 owns full teaching prose")
        exercises = [exercise for exercise in (lesson.get("exercises") or [])
                     if isinstance(exercise, dict)]
        if len(exercises) > 5:
            err("phase-2-skeleton", f"{sid}: placeholder lesson has {len(exercises)} exercises — "
                "preserve the scaffold's maximum of 5; Phase 3 authors the real exercise set")
        caps = lesson.get("teaches")
        if (not isinstance(caps, list) or not caps
                or any(not isinstance(cap, str) or not _CAPABILITY_ID.fullmatch(cap)
                       for cap in caps)):
            err("phase-2-skeleton", f"{sid}: placeholder lesson `teaches` must be a non-empty "
                "array of lowercase kebab-case capability ids")
            valid_caps = set()
        else:
            valid_caps = set(caps)
            if len(valid_caps) != len(caps):
                err("phase-2-skeleton", f"{sid}: placeholder lesson repeats a capability id")
        taught |= valid_caps

        freestyle = section.get("freestyle")
        if isinstance(freestyle, dict):
            freestyle_brief = str(freestyle.get("brief") or "")
            if not PLACEHOLDER_RE.search(freestyle_brief):
                err("phase-2-skeleton", f"{sid}: freestyle brief has no TODO/FIXME marker — "
                    "Phase 3 authors the cumulative capstone")
            brief_words = len(re.sub(r"<[^>]+>", " ", freestyle_brief).split())
            if brief_words > 120:
                err("phase-2-skeleton", f"{sid}: freestyle brief is {brief_words} words — "
                    "Phase 2 stubs stay under 120; Phase 3 owns the capstone brief")
            requires = freestyle.get("requires")
            if (not isinstance(requires, list) or not requires
                    or any(not isinstance(cap, str) or not _CAPABILITY_ID.fullmatch(cap)
                           for cap in requires)):
                err("phase-2-skeleton", f"{sid}: freestyle.requires must be a non-empty array "
                    "of lowercase kebab-case capability ids")
            else:
                missing = sorted(set(requires) - taught)
                if missing:
                    err("phase-2-skeleton", f"{sid}: freestyle requires capability ids not yet "
                        f"taught by its placeholder or an earlier one: {', '.join(missing)}")


def check_tooling_contract(m, sections_data, label, tooling=None):
    """Enforce the Phase-0 tooling choice independently of content-quality checks."""
    rt = m.get("runtime", {}) or {}
    xw = rt.get("externalWorkspace") is True
    if tooling == "internal" and xw:
        err(label, "tooling gate = internal (in-browser only) but [runtime] externalWorkspace "
                   "= true — an internal-only course keeps every workbench in the browser; drop it")
    if (xw or tooling in ("external", "both")) and sections_data:
        first = sections_data[0]
        has_reading = any(str(reading.get("url", "")).strip()
                          for lesson in (first.get("lessons") or []) if isinstance(lesson, dict)
                          for reading in (lesson.get("readings") or [])
                          if isinstance(reading, dict))
        if not has_reading:
            why = "[runtime] externalWorkspace = true" if xw else f"tooling gate = {tooling}"
            err(label, f"{why} but the first section has no [[lessons.readings]] links — the tome "
                       "REQUIRES external tools be taught: state which to install/use in the first "
                       "lesson, with resource links (marked mandatory/optional)")
