#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath

_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[4]
_bootstrap_sys.path[:0] = [
    str(_BOOTSTRAP_REPO),
    str(_BOOTSTRAP_REPO / "tools"),
    str(_BOOTSTRAP_REPO / "tools" / "tests"),
]

"""Provider failures, infrastructure recovery, and warm prompt behavior."""
import os
import subprocess
import tempfile
from unittest.mock import patch

from tools.buildlib.single_author import gate  # noqa: E402
from tools.buildlib import brief_exception, measure, single_author  # noqa: E402
from author.sessions import (  # noqa: E402
    BlockedThenHandoffSession,
    ExplicitBlockedSession,
    UnlimitedRepairSession,
)


class AuthenticationRequiredSession(UnlimitedRepairSession):
    def run_turn(self, prompt, conversation_kind="system",
                 conversation_text=""):
        self.prompts.append(prompt)
        return (
            "authentication-required",
            "Run `claude setup-token` and set `CLAUDE_CODE_OAUTH_TOKEN`.",
        )


# Missing headless Claude auth pauses before a paid provider process starts.
with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    with patch.object(gate, "BUILD_DIR", build_dir), \
            patch.object(gate, "REPO", root), \
            patch.object(single_author, "BUILD_DIR", build_dir), \
            patch.object(single_author, "preflight_unit"), \
            patch.object(single_author, "notify"):
        gate._write_phase("warm", 8, "working")
        session = AuthenticationRequiredSession()
        session.kind = "claude-cli"
        session.controls.put({"type": "stop"})
        assert session.run() == 130
        assert len(session.prompts) == 1
        paused = [
            extra for state, extra in session.states if state == "paused"
        ]
        assert paused[-1]["gate"] == "author-authentication"
        assert "CLAUDE_CODE_OAUTH_TOKEN" in paused[-1]["error"]


# The explicit author-side circuit breaker is terminal until an operator resumes.
with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    with patch.object(gate, "BUILD_DIR", build_dir), \
            patch.object(gate, "REPO", root), \
            patch.object(single_author, "BUILD_DIR", build_dir), \
            patch.object(single_author, "preflight_unit"), \
            patch.object(single_author, "validate_author_self_check",
                         side_effect=measure.ValidatorInfrastructureError(
                             "python3 tools/validate_section.py",
                             "ModuleNotFoundError: validator")), \
            patch.object(single_author, "validate_unit") as validate, \
            patch.object(single_author.traceback, "print_exc"), \
            patch.object(single_author, "notify"):
        gate._write_phase("warm", 8, "working")
        session = ExplicitBlockedSession()
        session.controls.put({"type": "stop"})
        assert session.run() == 130
        assert len(session.prompts) == 1
        validate.assert_not_called()
        assert any(
            state_name == "paused"
            for state_name, _extra in session.states)


with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    with patch.object(gate, "BUILD_DIR", build_dir), \
            patch.object(gate, "REPO", root), \
            patch.object(single_author, "BUILD_DIR", build_dir), \
            patch.object(single_author, "preflight_unit"), \
            patch.object(single_author, "validate_author_self_check",
                         return_value=(
                             False,
                             "ERROR authored.toml: repair this field")), \
            patch.object(single_author, "validate_unit",
                         return_value=(True, "clean")), \
            patch.object(single_author, "notify"):
        gate._write_phase("warm", 8, "working")
        session = BlockedThenHandoffSession()
        assert session.run() == 0
        assert len(session.prompts) == 2
        assert "ERROR authored.toml: repair this field" in session.prompts[1]
        assert not any(
            state_name == "paused"
            for state_name, _extra in session.states)


# A clean reproduced self-check advances without another author turn.
with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    with patch.object(gate, "BUILD_DIR", build_dir), \
            patch.object(gate, "REPO", root), \
            patch.object(single_author, "BUILD_DIR", build_dir), \
            patch.object(single_author, "preflight_unit"), \
            patch.object(single_author, "validate_author_self_check",
                         return_value=(True, "clean")), \
            patch.object(single_author, "validate_unit",
                         return_value=(True, "clean")) as validate, \
            patch.object(single_author, "notify"):
        gate._write_phase("warm", 8, "working")
        session = ExplicitBlockedSession()
        assert session.run() == 0
        assert len(session.prompts) == 1
        validate.assert_called_once()
        assert not any(
            state_name == "paused"
            for state_name, _extra in session.states)


# An unstructured validator crash pauses instead of buying unlimited repairs.
with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    failure = measure.ValidatorInfrastructureError(
        "python3 tools/validate_section.py", "ModuleNotFoundError: arcanum")
    with patch.object(gate, "BUILD_DIR", build_dir), \
            patch.object(gate, "REPO", root), \
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
        paused = [
            extra for state_name, extra in session.states
            if state_name == "paused"
        ]
        assert len(paused) == 1
        assert paused[0]["gate"] == "validator-infrastructure"
        assert "No author retry was started" in paused[0]["error"]


# Bootstrap preflight happens before the first provider invocation.
with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    failure = measure.ValidatorInfrastructureError(
        "python3 tools/validate_section.py --help", "broken import")
    with patch.object(gate, "BUILD_DIR", build_dir), \
            patch.object(gate, "REPO", root), \
            patch.object(single_author, "BUILD_DIR", build_dir), \
            patch.object(single_author, "preflight_unit",
                         side_effect=failure), \
            patch.object(single_author.traceback, "print_exc"), \
            patch.object(single_author, "notify"):
        gate._write_phase("warm", 8, "working")
        session = UnlimitedRepairSession()
        session.controls.put({"type": "stop"})
        assert session.run() == 130
        assert session.prompts == []


# Timeout diagnostics must not re-print the large prompt argument.
prompt_argv = [
    "opencode", "run", "-m", "free/model",
    "EVIDENCE PACKET " + "x" * 6000,
]
message = []
session = UnlimitedRepairSession()
session.state = lambda *args, **kwargs: None
session.await_validation_controls = lambda: 130
with patch.object(
        single_author, "append_conversation",
        lambda build_id, kind, text: message.append(text)), \
        patch.object(single_author, "notify"):
    session.pause_for_validation_infrastructure(
        {"kind": "section", "section": "s01", "index": 1, "total": 8},
        subprocess.TimeoutExpired(prompt_argv, 900))
assert message and "timed out after 900s" in message[0], message
assert "EVIDENCE PACKET" not in message[0], len(message[0])

message.clear()
with patch.object(
        single_author, "append_conversation",
        lambda build_id, kind, text: message.append(text)), \
        patch.object(single_author, "notify"):
    session.pause_for_validation_infrastructure(
        {"kind": "section", "section": "s01", "index": 1, "total": 8},
        RuntimeError(
            "section Validator AI infrastructure failed: "
            + brief_exception(subprocess.TimeoutExpired(prompt_argv, 900))))
assert message and "timed out after 900s" in message[0], message
assert "EVIDENCE PACKET" not in message[0], len(message[0])


# Cost stops stay terse while the full report remains in conversation.
message.clear()
paused_state = []
session.state = lambda state_name, **extra: paused_state.append(
    (state_name, extra))
session.await_validation_controls = lambda: 130
with patch.object(
        single_author, "append_conversation",
        lambda build_id, kind, text: message.append(text)), \
        patch.object(single_author, "notify"):
    session.pause_for_section_repair_limit(
        {"kind": "section", "section": "s01", "index": 1, "total": 8},
        "long validator report", 1,
        {"displayUsd": 2.14, "apiEquivalentUsd": 2.14})
assert paused_state[-1][1]["error"] == (
    "Phase 3 section s01 (1/8) paused at $2.14 after 1 failed validation. "
    "Choose an AI to retry.")
assert (
    "Latest validator report" in message[-1]
    and "long validator report" in message[-1])


# Sections return to their warm second batch without regenerating context.
section = {"kind": "section", "section": "s01", "index": 1, "total": 8}
phase = {"kind": "phase", "phase": 4, "state": "working"}
resume_section = gate.continue_prompt("build", section)
assert "every sealed planned lesson is complete" in resume_section
assert "ALL remaining lessons together" in resume_section
assert "Working, assessment, and handoff together" in resume_section
assert "render_section_context.py" not in resume_section
assert "Read its phase guide" not in resume_section
assert (
    "python3 tools/workflow/report_section_progress.py "
    "build s01 1 8 validating" in resume_section)
assert "tools/validate_section.py" in resume_section
assert "--source-only" not in resume_section

operator_resume = gate.interrupted_prompt(
    "Why did these findings repeat?", section)
assert operator_resume.startswith("Why did these findings repeat?")
assert "continue the exact assignment that was interrupted" in operator_resume
assert "existing repair packet" in operator_resume
assert "do not rerun render_section_context.py" in operator_resume
assert "Read its phase guide" not in operator_resume
assert "TWO COHERENT AUTHORING BATCHES" not in operator_resume

resume_phase = gate.continue_prompt("build", phase)
assert "You stopped before handing off" in resume_phase
assert gate.unit_prompt("build", phase) in resume_phase

opening = gate.unit_prompt("build", section)
assert "EVERY sealed planned lesson" in opening
assert "TWO COHERENT AUTHORING BATCHES" in opening
assert "ONE LESSON PER TURN" not in opening
assert "TWO COHERENT AUTHORING BATCHES" not in gate.unit_prompt("build", phase)
assert "HARNESS_REPAIR_REQUIRED" not in opening
assert "HARNESS_BLOCKED" in opening
assert "COMMAND: <copy the exact failed command>" in opening
assert "never substitutes a different check" in opening
assert "ALWAYS run every listed command" in opening

print("single-author provider recovery and prompt behaviors: OK")
