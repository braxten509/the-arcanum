"""Which phase owns which titles, sidecars, and manifest blocks."""
from __future__ import annotations

import re

from .files import _atomic_text, _read_text


PHASE_TITLES = ("", "Concept & arc", "Skeleton & voice", "Sections", "Minigames",
                "Economy", "Cosmetics", "Validate", "Student review")

ECONOMY_SCAFFOLD = """[economy]
# TODO: rebalance once your exercise/freestyle points are set (see § [economy]).
ranks = [[0, "NOVICE"], [400, "ADEPT"], [1000, "MASTER"]]
hintCost = 50
oracleCost = 10
attemptMultipliers = [1, 0.6, 0.3]
comboStep = 0.05
comboCap = 0.5
sRankMultiplier = 1.5
attackStakePerDiff = 20
attackWinPerDiff = 15

"""

TERMINAL_SUFFIXES = (
    "active.json", "cancelled.json", "result.json", "session.json",
    "conversation.jsonl", "amend.json", "progress", "section-progress.json",
)
PHASE3_SIDECARS = ("handoffs", "sections-done", "section-findings")
COURSE_SEED_SIDECARS = ("course-map.seed.json", "course-map.proposal.json",
                        "course-map-author", "phase2-research.json")
COURSE_MAP_SIDECARS = ("course-map.json", "course-map.amendments.json")
COURSE_STATE_SIDECARS = ("course-state.json", "course-evidence", "course-failures",
                          "course-control.log.jsonl")
PHASE7_SIDECARS = ("proof-evidence.json", "shrink-ok", "learner-project")
PHASE8_SIDECARS = ("findings.json", "verdict")
AI_COST_SIDECARS = ("ai-costs.jsonl", "ai-cost-totals.jsonl", "ai-cost-state.json")
COST_SIDECARS = AI_COST_SIDECARS + ("status-log.jsonl",)


def _replace_economy(manifest):
    text = _read_text(manifest)
    updated, count = re.subn(r"(?ms)^\[economy\][^\n]*\n.*?(?=^\[|\Z)",
                             ECONOMY_SCAFFOLD, text, count=1)
    if count != 1:
        raise ValueError("tome.toml has no top-level [economy] block to reset")
    _atomic_text(manifest, updated)
