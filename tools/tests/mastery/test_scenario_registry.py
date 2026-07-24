#!/usr/bin/env python3
"""Every assessment scenario adapter obeys the same explicit registry contract."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from arcanum.assessment.scenarios import ScenarioAdapter, ScenarioRegistry, default_registry
from arcanum_core.contracts.assessment import SCENARIO_KINDS, Scenario


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


class ExpectedFailureRuntime:
    def assessment_command(self, _command_ref, _work, _args):
        return ["fixture"]


class ExpectedFailureSandbox:
    def run(self, *_args, **_kwargs):
        return {"passed": False, "exitCode": 1, "output": "FAIL",
                "rawOutput": "FAIL\n", "timedOut": False}


expected_failure = Scenario.from_dict({
    "id": "controlled-failure", "kind": "run",
    "requirementIds": ["reports-failure"],
    "capabilityIds": ["language-output"], "commandRef": "run",
    "args": ["--fail"], "stdin": "",
    "expect": {"exitCode": 1, "raw": "FAIL\n"},
    "timeout": 20, "public": False,
}, "scenario")
outcome = registry.execute(expected_failure, {
    "runtime": ExpectedFailureRuntime(), "sandbox": ExpectedFailureSandbox(),
    "work": "/tmp",
})
assert outcome["passed"], outcome

wrong_bytes = Scenario.from_dict({
    **{
        "id": expected_failure.id, "kind": expected_failure.kind,
        "requirementIds": list(expected_failure.requirement_ids),
        "capabilityIds": list(expected_failure.capability_ids),
        "commandRef": expected_failure.command_ref,
        "args": list(expected_failure.args), "stdin": expected_failure.stdin,
        "timeout": expected_failure.timeout, "public": expected_failure.public,
    },
    "expect": {"exitCode": 1, "raw": "FAIL"},
}, "scenario")
outcome = registry.execute(wrong_bytes, {
    "runtime": ExpectedFailureRuntime(), "sandbox": ExpectedFailureSandbox(),
    "work": "/tmp",
})
assert not outcome["passed"] and "raw result" in outcome["problems"][0], outcome

print("assessment scenario registry contracts: OK")
