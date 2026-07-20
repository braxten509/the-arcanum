#!/usr/bin/env python3
"""Only Phase 1 and Phase 2 planning gates invoke the planning Validator AI."""
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from tools.buildlib.single_author import gate


definition = SimpleNamespace(
    validate=lambda _build, _context: (True, "mechanical clean"),
    transition_command=True)
registry = SimpleNamespace(get=lambda phase: SimpleNamespace(
    phase=phase, validate=definition.validate,
    transition_command=definition.transition_command))
context = {"tid": "course", "plan": ".tome-build/build.plan.md", "tooling": "external"}
ai_failure = {
    "status": "FAIL", "reasons": ["The arc order is not yet coherent."],
    "report": "# FAIL\n\nThe arc order is not yet coherent. Repair the cited dependency only.",
    "checks": [], "findings": [{
        "criterion": "arc-sequencing", "path": ".tome-build/build.plan.md",
        "evidenceLines": [1, 1],
        "requiredRepair": "Repair the cited milestone order only.",
    }],
}

with patch.object(gate, "PHASE_REGISTRY", registry), \
        patch.object(gate, "context", return_value=context), \
        patch.object(gate, "review_planning_phase",
                     return_value=ai_failure) as planning, \
        patch.object(gate.subprocess, "run") as transition:
    ai_ok, ai_report = gate.validate_unit(
        "build", {"kind": "phase", "phase": 1, "state": "validating"})
assert not ai_ok and ai_failure["report"] in ai_report
planning.assert_called_once_with("build", 1, "course")
transition.assert_not_called()

with patch.object(gate, "PHASE_REGISTRY", registry), \
        patch.object(gate, "context", return_value=context), \
        patch.object(gate, "review_planning_phase", return_value={
            "status": "PASS", "reasons": ["Every planning criterion passed."],
            "report": "# PASS\n\nEvery planning criterion passed with bounded evidence.",
            "checks": [], "findings": []}) as planning, \
        patch.object(gate.subprocess, "run", return_value=SimpleNamespace(
            returncode=0, stdout="transition clean", stderr="")) as transition:
    ai_ok, ai_report = gate.validate_unit(
        "build", {"kind": "phase", "phase": 2, "state": "validating"})
assert ai_ok and "# PASS" in ai_report
planning.assert_called_once_with("build", 2, "course")
transition.assert_called_once()

definition.transition_command = False
with patch.object(gate, "PHASE_REGISTRY", registry), \
        patch.object(gate, "context", return_value=context), \
        patch.object(gate, "review_planning_phase") as planning:
    for later_phase in range(4, 9):
        later_ok, _later_report = gate.validate_unit(
            "build", {"kind": "phase", "phase": later_phase,
                      "state": "validating"})
        assert later_ok
planning.assert_not_called()

definition.validate = lambda _build, _context: (False, "mechanical failure")
with patch.object(gate, "PHASE_REGISTRY", registry), \
        patch.object(gate, "context", return_value=context), \
        patch.object(gate, "review_planning_phase") as planning:
    mechanical_ok, mechanical_report = gate.validate_unit(
        "build", {"kind": "phase", "phase": 1, "state": "validating"})
assert not mechanical_ok and mechanical_report == "mechanical failure"
planning.assert_not_called()

print("planning Validator AI gate routing: OK")
