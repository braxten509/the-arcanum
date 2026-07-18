#!/usr/bin/env python3
"""Every assessment scenario adapter obeys the same explicit registry contract."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from arcanum.assessment.scenarios import ScenarioAdapter, ScenarioRegistry, default_registry
from arcanum_core.contracts.assessment import SCENARIO_KINDS


registry = default_registry()
entries = registry.entries()
assert {entry.kind for entry in entries} == SCENARIO_KINDS
assert all(entry.version == 1 for entry in entries)
assert all(entry.capabilities and callable(entry.handler) for entry in entries)
registry.validate_references(tuple(sorted(SCENARIO_KINDS)))

try:
    registry.register(entries[0])
except ValueError as error:
    assert "duplicate" in str(error)
else:
    raise AssertionError("duplicate scenario registration was accepted")

for adapter, expected in (
        (ScenarioAdapter("zero", lambda *_: {}, 0, ("process",)), "positive version"),
        (ScenarioAdapter("empty", lambda *_: {}, 1, ()), "capabilities")):
    try:
        ScenarioRegistry().register(adapter)
    except ValueError as error:
        assert expected in str(error)
    else:
        raise AssertionError(f"invalid scenario adapter {adapter.kind!r} was accepted")

try:
    registry.get("not-installed")
except ValueError as error:
    assert "available:" in str(error) and "build" in str(error)
else:
    raise AssertionError("unknown scenario lookup silently fell back")

try:
    registry.validate_references(("missing-b", "build", "missing-a"))
except ValueError as error:
    assert str(error).endswith("missing-a, missing-b")
else:
    raise AssertionError("missing scenario references were not reported together")

print("assessment scenario registry contracts: OK")
