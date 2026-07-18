#!/usr/bin/env python3
"""Central policy and pure progression boundary tests."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from arcanum_core.policies.progression import ProgressionPolicy, ProgressionSnapshot
from tools.buildlib.mastery_evidence import load_policy


policy = load_policy()
assert policy.version == 1
assert policy.required_lesson_completion == 1.0
assert policy.minimum_working_score == 80
assert policy.minimum_grade == "B"
assert policy.essential_failure_status == "INCOMPLETE"
expected = {
    1: (5, 1, 0, 1, 6),
    2: (7, 2, 1, 1, 8),
    3: (12, 2, 1, 1, 12),
    4: (15, 3, 2, 2, 12),
    5: (18, 3, 2, 3, 16),
}
for level, values in expected.items():
    row = policy.for_level(level)
    assert (row.capability_floor, row.late_performances, row.standalone_labs,
            row.rationales, row.minimum_verified_variants) == values

rules = ProgressionPolicy()
assert not ProgressionSnapshot(100, 99, 4, 2, 2, 0, 100, True).working_unlocked(rules)
assert ProgressionSnapshot(100, 100, 4, 2, 2, 0, 80, True).working_unlocked(rules)
assert not ProgressionSnapshot(100, 100, 4, 2, 2, 1, 80, True).working_unlocked(rules)
assert not ProgressionSnapshot(2, 2, 0, 1, 1, 0, 79, True).chapter_passed(rules)
assert not ProgressionSnapshot(2, 2, 0, 1, 1, 0, 99, False).chapter_passed(rules)
assert ProgressionSnapshot(2, 2, 0, 1, 1, 0, 80, True).chapter_passed(rules)
print("mastery evidence policy/progression tests: OK")
