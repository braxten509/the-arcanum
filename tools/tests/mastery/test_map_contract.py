#!/usr/bin/env python3
"""All-level positive and downgrade-negative map contract tests."""
from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from tools.buildlib.mastery_evidence.map_contract import validate_map_contract
from tools.tests.mastery.fixtures import future_map


for level in range(1, 6):
    contract, sections = future_map(level)
    assert validate_map_contract(contract, sections) == [], (level, validate_map_contract(contract, sections))

contract, sections = future_map(3)
downgraded = copy.deepcopy(contract)
downgraded["requiredPerformanceCount"] = 1
assert any("central floor" in item for item in validate_map_contract(downgraded, sections))

early = copy.deepcopy(contract)
early["performances"][0]["nodeId"] = "s01.lab01"
early["performances"][0]["variantFamilyId"] = "early-family"
assert any("missing node" in item or "late course" in item
           for item in validate_map_contract(early, sections))

supported = copy.deepcopy(contract)
supported["performances"][0]["aidPolicy"] = "learning"
assert any("documentation-only or cold" in item
           for item in validate_map_contract(supported, sections))

missing_capability = copy.deepcopy(contract)
missing_capability["performances"][0]["capabilityIds"] = []
assert any("at least 1" in item or "misses capabilities" in item
           for item in validate_map_contract(missing_capability, sections))

print("mastery evidence all-level map contract tests: OK")
