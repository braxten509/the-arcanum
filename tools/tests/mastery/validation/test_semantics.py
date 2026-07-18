#!/usr/bin/env python3
"""Variant-axis and cross-blueprint semantic-diversity fixtures."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from tools.validatelib.mastery_evidence.semantics import diversity_problems


shared = "Build the same challenge with one independently assigned variation axis."
same_blueprint = [
    {"variantId": "one", "blueprintId": "records", "brief": shared,
     "axes": {"domain": "harbor"}},
    {"variantId": "two", "blueprintId": "records", "brief": shared,
     "axes": {"domain": "clinic"}},
]
assert not diversity_problems(same_blueprint, ["domain"])

collapsed_blueprints = [
    {"variantId": "one", "blueprintId": "records", "brief": shared,
     "axes": {"domain": "harbor"}},
    {"variantId": "two", "blueprintId": "commands", "brief": shared,
     "axes": {"domain": "clinic"}},
]
problems = diversity_problems(collapsed_blueprints, ["domain"])
assert any("near-duplicates" in problem for problem in problems)

missing_axis = [dict(same_blueprint[0]), dict(same_blueprint[0], variantId="three")]
assert any("does not materially change" in problem
           for problem in diversity_problems(missing_axis, ["domain"]))

print("mastery semantic diversity tests: OK")
