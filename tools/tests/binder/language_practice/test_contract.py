#!/usr/bin/env python3
"""Phase 1 seals honest per-section language practice for Phase 2."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from tools.buildlib.language_mastery.practice import (
    practice_allocations,
    seeded_practice_problems,
)
from tools.buildlib.planning_review import planning_prompt


MARKER = "- **Language practice contract:** 1\n"
SPINE = ["language-values", "language-control", "language-functions"]
SECTIONS = ["s01", "s02"]


valid = (
    MARKER
    + "**Language practice allocation:** "
    + "s01 = language-values; s02 = language-control, language-functions\n"
)
allocations, problems = practice_allocations(valid, SECTIONS, SPINE)
assert not problems, problems
assert allocations == {
    "s01": ["language-values"],
    "s02": ["language-control", "language-functions"],
}

_allocations, problems = practice_allocations(
    MARKER + "**Language practice allocation:** s01 = language-values\n",
    SECTIONS,
    SPINE,
)
assert any("missing sections: s02" in problem for problem in problems), problems

_allocations, problems = practice_allocations(
    MARKER
    + "**Language practice allocation:** "
    + "s01 = language-values, language-values; s02 = language-tooling\n",
    SECTIONS,
    SPINE,
)
assert any("duplicates" in problem for problem in problems), problems
assert any("outside the declared spine" in problem for problem in problems), problems

seed = [
    {"id": "s01", "languagePractice": ["language-values"]},
    {"id": "s02", "languagePractice": ["language-control"]},
]
expanded = [
    {"id": "s01", "languagePractice": ["language-values", "language-functions"]},
    {"id": "s02", "languagePractice": ["language-control"]},
]
assert seeded_practice_problems(seed, expanded) == []
removed = [
    {"id": "s01", "languagePractice": ["language-functions"]},
    {"id": "s02", "languagePractice": ["language-control"]},
]
floor_problems = seeded_practice_problems(seed, removed)
assert floor_problems == [
    "s01.languagePractice removed sealed Phase-1 minimums: language-values"
]

phase1 = planning_prompt(1, "packet", [{"path": "plan.md", "repairable": True}])
assert "Audit every sealed Language practice allocation" in phase1
assert "version checks" in phase1 and "not language practice" in phase1
phase2 = planning_prompt(2, "packet", [{"path": "plan.md", "repairable": False}])
assert "seeded Phase-1 languagePractice minimum" in phase2
assert "CONTRACT CONFLICT" in phase2

print("language-practice contract tests: OK")
