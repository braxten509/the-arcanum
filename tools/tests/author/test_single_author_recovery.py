#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""The sole author's recovery, repair-cycle, and cost-stop behaviors across warm sessions."""
import os
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
        assert paused[-1]["gate"] == "planning-stall"
        assert "same repair is repeating" in paused[-1]["error"]


# The explicit author-side circuit breaker is terminal until an operator resumes it.
with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    with patch.object(gate, "BUILD_DIR", build_dir), patch.object(gate, "REPO", root), \
            patch.object(single_author, "BUILD_DIR", build_dir), \
            patch.object(single_author, "preflight_unit"), \
            patch.object(single_author, "validate_author_self_check", side_effect=(
                measure.ValidatorInfrastructureError(
                    "python3 tools/validate_section.py", "ModuleNotFoundError: validator"))), \
            patch.object(single_author, "validate_unit") as validate, \
            patch.object(single_author.traceback, "print_exc"), \
            patch.object(single_author, "notify"):
        gate._write_phase("warm", 8, "working")
        session = ExplicitBlockedSession()
        session.controls.put({"type": "stop"})
        assert session.run() == 130
        assert len(session.prompts) == 1
        validate.assert_not_called()
        assert any(state_name == "paused" for state_name, _extra in session.states)
        preflight.assert_not_called()


with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    with patch.object(gate, "BUILD_DIR", build_dir), patch.object(gate, "REPO", root), \
            patch.object(single_author, "BUILD_DIR", build_dir), \
            patch.object(single_author, "preflight_unit"), \
            patch.object(single_author, "validate_author_self_check", return_value=(
                False, "ERROR authored.toml: repair this field")), \
            patch.object(single_author, "validate_unit", return_value=(True, "clean")), \
            patch.object(single_author, "notify"):
        gate._write_phase("warm", 8, "working")
        session = BlockedThenHandoffSession()
        assert session.run() == 0
        assert len(session.prompts) == 2
        assert "ERROR authored.toml: repair this field" in session.prompts[1]
        assert not any(state_name == "paused" for state_name, _extra in session.states)


# If the reproduced self-check is already clean, the harness writes the trusted
# validating marker and runs the authoritative gate without another author turn.
with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    with patch.object(gate, "BUILD_DIR", build_dir), patch.object(gate, "REPO", root), \
            patch.object(single_author, "BUILD_DIR", build_dir), \
            patch.object(single_author, "preflight_unit"), \
            patch.object(single_author, "validate_author_self_check", return_value=(
                True, "clean")), \
            patch.object(single_author, "validate_unit", return_value=(True, "clean")) as validate, \
            patch.object(single_author, "notify"):
        gate._write_phase("warm", 8, "working")
        session = ExplicitBlockedSession()
        assert session.run() == 0
        assert len(session.prompts) == 1
        validate.assert_called_once()
        assert not any(state_name == "paused" for state_name, _extra in session.states)


# An unstructured validator crash pauses after one author handoff instead of
# becoming an unlimited sequence of paid repair turns.
with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    failure = measure.ValidatorInfrastructureError(
        "python3 tools/validate_section.py", "ModuleNotFoundError: arcanum")
    with patch.object(gate, "BUILD_DIR", build_dir), patch.object(gate, "REPO", root), \
            patch.object(single_author, "BUILD_DIR", build_dir), \
            patch.object(single_author, "preflight_unit"), \
            patch.object(single_author, "validate_unit", side_effect=failure), \
            patch.object(single_author.traceback, "print_exc"), \
            patch.object(single_author, "notify"):
        gate._write_phase("warm", 8, "working")
        session = UnlimitedRepairSession()
        session.controls.put({"type": "stop"})
        assert session.run() == 130
        assert len(session.prompts) == 1
        paused = [extra for state_name, extra in session.states if state_name == "paused"]
        assert len(paused) == 1
        assert paused[0]["gate"] == "validator-infrastructure"
        assert "No author retry was started" in paused[0]["error"]


# Bootstrap preflight happens before even the first provider invocation.
with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    failure = measure.ValidatorInfrastructureError(
        "python3 tools/validate_section.py --help", "broken import")
    with patch.object(gate, "BUILD_DIR", build_dir), patch.object(gate, "REPO", root), \
            patch.object(single_author, "BUILD_DIR", build_dir), \
            patch.object(single_author, "preflight_unit", side_effect=failure), \
            patch.object(single_author.traceback, "print_exc"), \
            patch.object(single_author, "notify"):
        gate._write_phase("warm", 8, "working")
        session = UnlimitedRepairSession()
        session.controls.put({"type": "stop"})
        assert session.run() == 130
        assert session.prompts == []

# A timed-out validator must report the timeout, not re-print the prompt it was sent.
# TimeoutExpired stringifies its whole argv, and the prompt is one of those arguments.
prompt_argv = ["opencode", "run", "-m", "free/model", "EVIDENCE PACKET " + "x" * 6000]
message = []
session = UnlimitedRepairSession()
session.state = lambda *args, **kwargs: None
session.await_validation_controls = lambda: 130
with patch.object(single_author, "append_conversation",
                  lambda build_id, kind, text: message.append(text)), \
        patch.object(single_author, "notify"):
    session.pause_for_validation_infrastructure(
        {"kind": "section", "section": "s01", "index": 1, "total": 8},
        subprocess.TimeoutExpired(prompt_argv, 900))
assert message and "timed out after 900s" in message[0], message
assert "EVIDENCE PACKET" not in message[0], len(message[0])

# The real path wraps the timeout in a RuntimeError first, so the raise site must
# compress the cause too; a wrapper built with str(exc) smuggles the packet back in.
message.clear()
with patch.object(single_author, "append_conversation",
                  lambda build_id, kind, text: message.append(text)), \
        patch.object(single_author, "notify"):
    session.pause_for_validation_infrastructure(
        {"kind": "section", "section": "s01", "index": 1, "total": 8},
        RuntimeError("section Validator AI infrastructure failed: " + brief_exception(
            subprocess.TimeoutExpired(prompt_argv, 900))))
assert message and "timed out after 900s" in message[0], message
assert "EVIDENCE PACKET" not in message[0], len(message[0])

# A section cost stop keeps the recovery bar terse while preserving the full report in chat.
message.clear()
paused_state = []
session.state = lambda state_name, **extra: paused_state.append((state_name, extra))
session.await_validation_controls = lambda: 130
with patch.object(single_author, "append_conversation",
                  lambda build_id, kind, text: message.append(text)), \
        patch.object(single_author, "notify"):
    session.pause_for_section_repair_limit(
        {"kind": "section", "section": "s01", "index": 1, "total": 8},
        "long validator report", 1,
        {"displayUsd": 2.14, "apiEquivalentUsd": 2.14})
assert paused_state[-1][1]["error"] == (
    "Phase 3 section s01 (1/8) paused at $2.14 after 1 failed validation. "
    "Choose an AI to retry.")
assert "Latest validator report" in message[-1] and "long validator report" in message[-1]

# Sections author all lessons in one batch, then Working/assessment/handoff in another.
# The return prompt must NOT re-send unit_prompt: that would rerun the bounded context
# render and recharge discovery the warm section session still holds.
section = {"kind": "section", "section": "s01", "index": 1, "total": 8}
phase = {"kind": "phase", "phase": 4, "state": "working"}
resume_section = gate.continue_prompt("build", section)
assert "every sealed planned lesson is complete" in resume_section, resume_section
assert "ALL remaining lessons together" in resume_section, resume_section
assert "Working, assessment, and handoff together" in resume_section, resume_section
assert "render_section_context.py" not in resume_section, resume_section
assert "Read its phase guide" not in resume_section, resume_section
# the last turn still carries the gate, so the section can actually be handed off
assert ("python3 tools/workflow/report_section_progress.py build s01 1 8 validating"
        in resume_section), resume_section
assert "tools/validate_section.py tomes/build s01" in resume_section, resume_section

# Phases are one unit, not a series of lessons, so their return prompt is unchanged.
resume_phase = gate.continue_prompt("build", phase)
assert "You stopped before handing off" in resume_phase, resume_phase
assert gate.unit_prompt("build", phase) in resume_phase, resume_phase

# The two-batch boundary has to be stated on the way in.
opening = gate.unit_prompt("build", section)
assert "EVERY sealed planned lesson" in opening, opening
assert "TWO COHERENT AUTHORING BATCHES" in opening, opening
assert "ONE LESSON PER TURN" not in opening, opening
assert "TWO COHERENT AUTHORING BATCHES" not in gate.unit_prompt("build", phase)
assert "HARNESS_REPAIR_REQUIRED:" in opening

# Cost and repeated-failure governors are independent: an unpriced model still pauses
# after repeated failures, while a priced GPT section pauses as soon as it crosses $2.
assert not single_author.section_repair_limit_reached(1, None)
assert single_author.section_repair_limit_reached(2, None)
assert not single_author.section_repair_limit_reached(
    1, {"apiEquivalentUsd": 1.999})
assert single_author.section_repair_limit_reached(
    1, {"apiEquivalentUsd": 2.0})
print("single-author recovery behaviors: OK")
