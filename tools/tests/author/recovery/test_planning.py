#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[4]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""The sole author's recovery, repair-cycle, and cost-stop behaviors across warm sessions."""
import json
import os
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(_BOOTSTRAP_REPO / "tools" / "tests"))

from tools.buildlib.single_author import gate  # noqa: E402
from tools.buildlib import brief_exception, measure  # noqa: E402
from tools.buildlib.workflow import section_progress  # noqa: E402
from tools.buildlib import single_author  # noqa: E402
from author.sessions import (BlockedThenHandoffSession,  # noqa: E402
                             ExplicitBlockedSession,
                             FakeWarmSession,
                             OscillatingNoHandoffSession,
                             RoutedWarmSession,
                             UnlimitedRepairSession)


class PlanningSelfCheckRepairSession(single_author.AuthorSession):
    def __init__(self):
        super().__init__(
            "planning", "codex-cli", "gpt-5.6-terra", "high", "concept", "external",
            1, "terra-session")
        self.prompts = []
        self.states = []

    def read_controls(self):
        return

    def state(self, state, **extra):
        self.states.append((state, extra))

    def run_turn(self, prompt, conversation_kind="system", conversation_text=""):
        self.prompts.append(prompt)
        return (("repair-required", "HARNESS_REPAIR_REQUIRED: exact language missing")
                if len(self.prompts) == 1 else ("stopped", ""))


class StalledPlanningRepairSession(PlanningSelfCheckRepairSession):
    def run_turn(self, prompt, conversation_kind="system", conversation_text=""):
        self.prompts.append(prompt)
        return "repair-required", "HARNESS_REPAIR_REQUIRED: exact language missing"


class OscillatingPlanningValidationSession(PlanningSelfCheckRepairSession):
    def __init__(self, authored_path):
        single_author.AuthorSession.__init__(
            self, "planning-cycle", "codex-cli", "gpt-5.6-terra", "high",
            "concept", "external", 2, "terra-session")
        self.authored_path = authored_path
        self.prompts = []
        self.states = []

    def run_turn(self, prompt, conversation_kind="system", conversation_text=""):
        self.prompts.append(prompt)
        value = "A\n" if len(self.prompts) % 2 else "B\n"
        with open(self.authored_path, "w", encoding="utf-8") as handle:
            handle.write(value)
        gate._write_phase("planning-cycle", 2, "validating")
        return "complete", ""


class PlanningContractConflictSession(single_author.AuthorSession):
    def __init__(self):
        super().__init__(
            "planning-conflict", "codex-cli", "gpt-5.6-terra", "high",
            "concept", "external", 2, "terra-session")
        self.prompts = []
        self.states = []

    def read_controls(self):
        return

    def state(self, state, **extra):
        self.states.append((state, extra))

    def run_turn(self, prompt, conversation_kind="system", conversation_text=""):
        self.prompts.append(prompt)
        raise AssertionError("a sealed planning conflict was routed to the author")


class AuthenticationRequiredSession(UnlimitedRepairSession):
    def run_turn(self, prompt, conversation_kind="system", conversation_text=""):
        self.prompts.append(prompt)
        return (
            "authentication-required",
            "Run `claude setup-token` and set `CLAUDE_CODE_OAUTH_TOKEN`.",
        )


with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    with patch.object(gate, "BUILD_DIR", build_dir), patch.object(gate, "REPO", root), \
            patch.object(single_author, "BUILD_DIR", build_dir), \
            patch.object(single_author, "preflight_unit"), \
            patch.object(single_author, "validate_unit", return_value=(True, "clean")), \
            patch.object(single_author, "report_completed_unit_cost") as report_cost:
        gate._write_phase("warm", 7, "working")
        session = FakeWarmSession()
        assert session.run() == 0
        assert session.session_id == ""
        assert len(session.prompts) == 2
        assert "Phase 7" in session.prompts[0]
        assert "HARNESS VALIDATION PASSED for Phase 7" in session.prompts[1]
        assert "Continue with Phase 8" in session.prompts[1]
        assert "active unit author" in session.prompts[1]
        assert [call.args[1]["phase"] for call in report_cost.call_args_list] == [7, 8]
        assert session.states[-1][0] == "complete"


with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    with patch.object(gate, "BUILD_DIR", build_dir), patch.object(gate, "REPO", root), \
            patch.object(single_author, "BUILD_DIR", build_dir), \
            patch.object(single_author, "preflight_unit"), \
            patch.object(single_author, "validate_unit", return_value=(True, "clean")):
        gate._write_phase("routed", 7, "working")
        session = RoutedWarmSession()
        assert session.run() == 0
        assert (session.kind, session.model, session.effort) == (
            "opencode-cli", "student-review", "max")
        assert session.session_id == ""
        assert len(session.prompts) == 2
        assert "active unit author" in session.prompts[1]
        assert "Continue with Phase 8" in session.prompts[1]


with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    attempts = [0]

    def eventually_clean(_build_id, _unit):
        attempts[0] += 1
        return ((True, "clean") if attempts[0] == 13
                else (False, f"repair {attempts[0]}"))

    with patch.object(gate, "BUILD_DIR", build_dir), patch.object(gate, "REPO", root), \
            patch.object(single_author, "BUILD_DIR", build_dir), \
            patch.object(single_author, "preflight_unit"), \
            patch.object(single_author, "validate_unit", side_effect=eventually_clean):
        gate._write_phase("warm", 8, "working")
        session = UnlimitedRepairSession()
        assert session.run() == 0
        assert attempts[0] == 13
        assert len(session.prompts) == 13
        assert not any(state == "paused" for state, _extra in session.states)


# A repeated A -> B -> A authored state is a proven repair cycle, not progress.
# Pause before paying for a fourth provider turn; unique repair states remain unlimited.
with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    authored_path = os.path.join(root, "proposal.json")
    with open(authored_path, "w", encoding="utf-8") as handle:
        handle.write("initial\n")
    with patch.object(gate, "BUILD_DIR", build_dir), patch.object(gate, "REPO", root), \
            patch.object(single_author, "BUILD_DIR", build_dir), \
            patch.object(single_author, "preflight_unit"), \
            patch.object(single_author, "author_paths", return_value=([authored_path], [])), \
            patch.object(single_author, "notify"):
        gate._write_phase("cycle", 2, "working")
        session = OscillatingNoHandoffSession(authored_path)
        session.controls.put({"type": "stop"})
        assert session.run() == 130
        assert len(session.prompts) == 3
        paused = [extra for state_name, extra in session.states if state_name == "paused"]
        assert len(paused) == 1
        assert paused[0]["gate"] == "author-no-progress-cycle"
        assert "No further author turn was started" in paused[0]["error"]


# A durable validating marker is recovered mechanically after a harness restart;
# the already-authored unit is never sent through another paid provider turn.
with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    with patch.object(gate, "BUILD_DIR", build_dir), patch.object(gate, "REPO", root), \
            patch.object(single_author, "BUILD_DIR", build_dir), \
            patch.object(single_author, "preflight_unit") as preflight, \
            patch.object(single_author, "validate_unit", return_value=(True, "clean")):
        gate._write_phase("warm", 8, "validating")
        session = UnlimitedRepairSession()
        assert session.run() == 0
        assert session.prompts == []


# A Validator-AI finding that can only be repaired in the sealed Phase-1 plan
# pauses at the harness. Resuming retries validation, never the Phase-2 author.
with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    conflict = (
        "-- planning-conflict: mechanical gate clean\n"
        "# CONTRACT CONFLICT\n\nThe sealed arc and lesson count cannot both be satisfied.")
    with patch.object(gate, "BUILD_DIR", build_dir), patch.object(gate, "REPO", root), \
            patch.object(single_author, "BUILD_DIR", build_dir), \
            patch.object(single_author, "validate_unit", return_value=(False, conflict)), \
            patch.object(single_author, "append_conversation"), \
            patch.object(single_author, "notify"):
        gate._write_phase("planning-conflict", 2, "validating")
        session = PlanningContractConflictSession()
        session.controls.put({"type": "stop"})
        assert session.run() == 130
        assert session.prompts == []
        paused = [extra for state, extra in session.states if state == "paused"]
        assert paused[-1]["gate"] == "planning-contract-conflict"
        assert "No author or alternate-AI retry was started" in paused[-1]["error"]
        assert "without an author turn" in paused[-1]["error"]


# A durable planning-review fingerprint cycle carries a harness marker across
# worker restarts and pauses before either AI receives another turn.
with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    cycle_report = (
        "HARNESS_PLANNING_CONTRACT_CYCLE\n\n"
        "# FAIL\n\nThis exact Phase-2 evidence already received this finding.")
    with patch.object(gate, "BUILD_DIR", build_dir), patch.object(gate, "REPO", root), \
            patch.object(single_author, "BUILD_DIR", build_dir), \
            patch.object(single_author, "validate_unit", return_value=(False, cycle_report)), \
            patch.object(single_author, "append_conversation"), \
            patch.object(single_author, "notify"):
        gate._write_phase("planning-conflict", 2, "validating")
        session = PlanningContractConflictSession()
        session.controls.put({"type": "stop"})
        assert session.run() == 130
        assert session.prompts == []
        paused = [extra for state, extra in session.states if state == "paused"]
        assert paused[-1]["gate"] == "planning-contract-stall"
        assert "No author or alternate-AI retry was started" in paused[-1]["error"]


# An ordinary Phase 1 repair stays on the selected model and warm session, with no
# planning budget stop or automatic escalation.
with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    with patch.object(gate, "BUILD_DIR", build_dir), patch.object(gate, "REPO", root), \
            patch.object(single_author, "BUILD_DIR", build_dir), \
            patch.object(single_author, "preflight_unit"), \
            patch.object(single_author, "validate_author_self_check", return_value=(
                False, "ERROR plan: exact declared language is missing")), \
            patch.object(single_author, "notify"):
        gate._write_phase("planning", 1, "working")
        session = PlanningSelfCheckRepairSession()
        assert session.run() == 130
        assert len(session.prompts) == 2
        assert (session.kind, session.model, session.effort) == (
            "codex-cli", "gpt-5.6-terra", "high")
        assert session.session_id == "terra-session"
        assert "ERROR plan: exact declared language is missing" in session.prompts[1]
        assert "Repair only this unit" in session.prompts[1]


# A truly motionless Phase 1 loop pauses before paying for a third author turn.
with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    with patch.object(gate, "BUILD_DIR", build_dir), patch.object(gate, "REPO", root), \
            patch.object(single_author, "BUILD_DIR", build_dir), \
            patch.object(single_author, "preflight_unit"), \
            patch.object(single_author, "validate_author_self_check", return_value=(
                False, "ERROR plan: exact declared language is missing")), \
            patch.object(single_author, "append_conversation"), \
            patch.object(single_author, "notify"):
        gate._write_phase("planning", 1, "working")
        session = StalledPlanningRepairSession()
        session.controls.put({"type": "stop"})
        assert session.run() == 130
        assert len(session.prompts) == 2
        assert (session.kind, session.model, session.session_id) == (
            "codex-cli", "gpt-5.6-terra", "terra-session")
        paused = [extra for state, extra in session.states if state == "paused"]
        assert paused[-1]["gate"] == "planning-contract-stall"
        assert "No author or alternate-AI retry was started" in paused[-1]["error"]
        assert "without an author turn" in paused[-1]["error"]


# A -> B -> A across completed Phase-2 handoffs is a validator-contract oscillation.
# Stop on the repeated authored state instead of paying for another repair turn.
with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    authored_path = os.path.join(root, "audit.json")
    os.makedirs(build_dir)
    with open(authored_path, "w", encoding="utf-8") as handle:
        handle.write("initial\n")
    reports = iter(("split the family", "merge the family", "split the family"))
    with patch.object(gate, "BUILD_DIR", build_dir), patch.object(gate, "REPO", root), \
            patch.object(single_author, "BUILD_DIR", build_dir), \
            patch.object(single_author, "preflight_unit"), \
            patch.object(single_author, "author_paths", return_value=([authored_path], [])), \
            patch.object(single_author, "validate_unit",
                         side_effect=lambda *_args: (False, next(reports))), \
            patch.object(single_author, "append_conversation"), \
            patch.object(single_author, "notify"):
        gate._write_phase("planning-cycle", 2, "working")
        session = OscillatingPlanningValidationSession(authored_path)
        session.controls.put({"type": "stop"})
        assert session.run() == 130
        assert len(session.prompts) == 3
        paused = [extra for state, extra in session.states if state == "paused"]
        assert paused[-1]["gate"] == "planning-contract-stall"
        assert "alternate-AI retry was started" in paused[-1]["error"]


print("single-author planning recovery behaviors: OK")
