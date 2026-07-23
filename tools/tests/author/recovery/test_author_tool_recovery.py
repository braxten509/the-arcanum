#!/usr/bin/env python3
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(REPO), str(REPO / "tools")]

from tools.buildlib import single_author  # noqa: E402
from tools.buildlib.single_author import gate  # noqa: E402
from tools.buildlib.single_author.session.recovery import (  # noqa: E402
    MAX_CODEX_PATCH_RECOVERIES,
    recoverable_codex_patch_failure,
    with_codex_patch_safety,
)


PATCH_CRASH = (
    "exit code 1\n"
    "ERROR codex_core::tools::router: error=apply_patch verification failed: "
    "invalid hunk at line 19, Expected update hunk to start with a @@ context marker"
)


class RecoveringSession(single_author.AuthorSession):
    def __init__(self, failures=1):
        super().__init__(
            "patch-recovery", "codex-cli", "gpt-5.6-terra", "high",
            "concept", "external", 8, "saved-codex-session")
        self.failures = failures
        self.prompts = []
        self.states = []

    def read_controls(self):
        return

    def state(self, state, **extra):
        self.states.append((state, extra))

    def run_turn(self, prompt, conversation_kind="system", conversation_text=""):
        self.prompts.append((prompt, conversation_kind, conversation_text))
        if len(self.prompts) <= self.failures:
            return "failed", PATCH_CRASH
        gate._write_phase("patch-recovery", 8, "validating")
        return "complete", ""


assert recoverable_codex_patch_failure(
    "codex-cli", "author", "saved-session", PATCH_CRASH)
assert not recoverable_codex_patch_failure(
    "codex-cli", "author", "", PATCH_CRASH)
assert not recoverable_codex_patch_failure(
    "claude-cli", "author", "saved-session", PATCH_CRASH)
assert "every update hunk" in with_codex_patch_safety(
    "codex-cli", "author", "write the unit")
assert with_codex_patch_safety(
    "claude-cli", "author", "write the unit") == "write the unit"


with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    conversations = []
    with patch.object(gate, "BUILD_DIR", build_dir), \
            patch.object(gate, "REPO", root), \
            patch.object(single_author, "BUILD_DIR", build_dir), \
            patch.object(single_author, "preflight_unit"), \
            patch.object(single_author, "validate_unit", return_value=(True, "clean")), \
            patch.object(single_author, "report_completed_unit_cost"), \
            patch.object(single_author, "append_conversation",
                         side_effect=lambda *args, **kwargs: conversations.append(args)):
        gate._write_phase("patch-recovery", 8, "working")
        session = RecoveringSession()
        assert session.run() == 0
    assert len(session.prompts) == 2
    assert "previous Codex turn ended" in session.prompts[1][0]
    assert session.prompts[1][1] == "harness"
    assert "tool recovery 1/2" in session.prompts[1][2]
    assert session.session_id == "saved-codex-session"
    assert not any(state == "paused" for state, _extra in session.states)


with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    with patch.object(gate, "BUILD_DIR", build_dir), \
            patch.object(gate, "REPO", root), \
            patch.object(single_author, "BUILD_DIR", build_dir), \
            patch.object(single_author, "preflight_unit"), \
            patch.object(single_author, "append_conversation"), \
            patch.object(single_author, "notify"):
        gate._write_phase("patch-recovery", 8, "working")
        session = RecoveringSession(failures=MAX_CODEX_PATCH_RECOVERIES + 1)
        session.controls.put({"type": "stop"})
        assert session.run() == 130
    assert len(session.prompts) == MAX_CODEX_PATCH_RECOVERIES + 1
    paused = [extra for state, extra in session.states if state == "paused"]
    assert len(paused) == 1
    assert "exhausted automatic same-session recovery" in paused[0]["error"]


print("author Codex patch recovery: OK")
