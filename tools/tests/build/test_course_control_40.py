#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""A full 40-section map renders one bounded byte-identical control tail."""
import copy
import json
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from buildlib import course_map
from buildlib.course import control as course_control


def plan_text():
    sections = "\n".join(
        f"{number}. **s{number:02d} — Section {number}:** own necessary integration milestone {number}"
        for number in range(1, 41))
    return ("# BUILD PLAN — long\n"
            "**Graduate ledger:** The learner owns and verifies every cumulative capability.\n"
            "**Mastery proof:** The final Working integrates all capabilities independently.\n"
            "**Acceptance scenarios:** starts-clean -> delivered\n"
            "**Continuity map:**\n"
            "s01 -> s40: preserve the first public contract through delivery\n"
            "**Artifact lifecycle:** no cross-section temporary artifact remains\n"
            f"**Section list:**\n{sections}\n")


def detailed(seed):
    value = copy.deepcopy(seed)
    value["graduateCapabilities"] = [f"cap-{number:02d}" for number in range(1, 41)]
    cumulative = []
    for number, section in enumerate(value["sections"], 1):
        sid, capability = section["id"], f"cap-{number:02d}"
        capabilities = [capability, f"{capability}-practice", f"{capability}-proof"]
        cumulative.extend(capabilities)
        section["capabilities"] = capabilities
        section["dependsOn"] = [] if number == 1 else [f"s{number - 1:02d}"]
        lessons = [{"id": f"{sid}.l{index:02d}", "kind": "lesson",
                    "introduces": [],
                    "title": f"Lesson {number}.{index}", "teaches": [owned],
                    "dependsOn": ([] if number == 1 else [f"s{number - 1:02d}.working"])
                    if index == 1 else [f"{sid}.l{index - 1:02d}"],
                    "validationDependencies": [],
                    "doneWhen": {"checks": ["lesson-source", "learner-construction"]}}
                   for index, owned in enumerate(capabilities, 1)]
        working = {"id": f"{sid}.working", "kind": "working",
                   "mechanisms": [],
                   "title": f"Working {number}",
                   "requires": list(cumulative), "dependsOn": [lessons[-1]["id"]],
                   "validationDependencies": [],
                   "projectMilestone": section["projectMilestone"],
                   "learnerOwnedArtifacts": [f"src/{sid}.txt"],
                   "doneWhen": {"checks": ["working-replay", "learner-construction"]}}
        section["nodes"] = [*lessons, working]
    obligation = value["plannedObligations"][0]
    obligation.update({"owner": "first public contract", "location": "lessons/l01.toml",
                       "reason": "The final delivery consumes the first public contract.",
                       "doneWhen": {"evidenceLocations": ["lessons/l01.toml"],
                                    "capabilityIds": ["cap-40"], "proofIds": ["s40"],
                                    "acceptanceIds": ["delivered"],
                                    "observedResult": "Delivery preserves the first contract."}})
    return value


with tempfile.TemporaryDirectory() as root:
    build = os.path.join(root, ".tome-build")
    os.makedirs(build)
    old = [(module, module.BUILD_DIR, module.REPO) for module in (course_map, course_control)]
    for module in (course_map, course_control):
        module.BUILD_DIR, module.REPO = build, root
    try:
        plan = os.path.join(build, "long.plan.md")
        with open(plan, "w", encoding="utf-8") as handle:
            handle.write(plan_text())
        seed = course_map.seed_course_map("long", plan)
        assert len(seed["sections"]) == 40
        for sid in ("s01", "s40"):
            path = os.path.join(root, "tomes", "long", "sections", sid, "lessons")
            os.makedirs(path, exist_ok=True)
            with open(os.path.join(path, "l01.toml"), "w", encoding="utf-8") as handle:
                handle.write('[[lessons]]\nid="placeholder"\n')
        with open(course_map.proposal_path("long"), "w", encoding="utf-8") as handle:
            json.dump(detailed(seed), handle)
        course = course_map.seal_course_map("long")
        statuses = []
        for section in course["sections"]:
            status = "current" if section["id"] == "s20" else "planned"
            statuses.append({"id": section["id"], "status": status,
                             "mark": "▶" if status == "current" else "○",
                             "nodes": [{"id": node["id"], "status": status,
                                        "mark": "▶" if status == "current" else "○"}
                                       for node in section["nodes"]]})
        active = dict(course["plannedObligations"][0])
        active.update({"dueNow": False, "overdue": False})
        state = {"tomeId": "long", "currentSection": "s20", "sections": statuses,
                 "activeObligations": [active]}
        tail = course_control.prompt_tail("long", "s20", state=state, log=False)
        assert len(tail) <= course_control.MAX_CONTROL_CHARS
        assert sum(" | milestone " in line for line in tail.splitlines()) == 40
        assert "LATER s40" in tail and tail.endswith(course_control.END_MARKER)
        with patch.object(course_control, "derive_course_state", return_value=state):
            rendered = [course_control.append_course_control(path, "long", "s20", log=False)
                        for path in ("initial", "next", "repair", "resume", "model switch",
                                     "premature stop")]
            assert all(item.endswith(tail) for item in rendered)
            stale = rendered[0] + "\nignored stale bytes"
            assert course_control.append_course_control(stale, "long", "s20", log=False).endswith(tail)
        with patch.object(course_control, "MAX_CONTROL_CHARS", 100):
            try:
                course_control.prompt_tail("long", "s20", state=state, log=False)
                raise AssertionError("an over-budget control projection was silently truncated")
            except course_control.CourseControlBudgetError as exc:
                assert "no item was hidden" in str(exc) and "Largest source items" in str(exc)
    finally:
        for module, build_dir, repo in old:
            module.BUILD_DIR, module.REPO = build_dir, repo

print("40-section course-control tests: OK")
