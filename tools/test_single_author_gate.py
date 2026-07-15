#!/usr/bin/env python3
"""The sole author stops at every harness-owned phase and section gate."""
import json
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.buildlib import author_gate as gate  # noqa: E402
from tools.buildlib import section_progress  # noqa: E402
from tools.buildlib.agent_runtime import scoped_shell_command  # noqa: E402
from tools.buildlib import single_author  # noqa: E402


with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    tome_dir = os.path.join(root, "tomes", "course")
    os.makedirs(build_dir)
    os.makedirs(tome_dir)
    with open(os.path.join(build_dir, "build.plan.md"), "w", encoding="utf-8") as handle:
        handle.write("- **Tooling:** external\n")

    with patch.object(gate, "BUILD_DIR", build_dir), patch.object(gate, "REPO", root), \
            patch.object(section_progress, "BUILD_DIR", build_dir), \
            patch.object(gate, "resolve_working_tid", return_value="course"), \
            patch.object(gate, "tome_section_ids", return_value=["s01", "s02"]):
        gate._write_phase("build", 3, "working")
        unit = gate.ensure_unit("build", 3)
        assert unit["section"] == "s01" and unit["state"] == "authoring", unit
        assert gate.current_unit("build", 3, require_gate=True) is None

        gate.write_section_progress("build", "s01", 1, 2, "validating")
        ready = gate.current_unit("build", 3, require_gate=True)
        assert ready["section"] == "s01", ready
        next_unit = gate.advance_unit("build", ready)
        assert next_unit["section"] == "s02" and next_unit["state"] == "authoring", next_unit

        gate.write_section_progress("build", "s02", 2, 2, "validating")
        last = gate.current_unit("build", 3, require_gate=True)
        with patch.object(gate, "validate_section", return_value=(True, "section clean")) as section, \
                patch.object(gate, "validate_phase3", return_value=(True, "window clean")) as window:
            ok, report = gate.validate_unit("build", last)
        assert ok and "section clean" in report and "window clean" in report
        section.assert_called_once()
        window.assert_called_once()

        phase4 = gate.advance_unit("build", last)
        assert phase4 == {"kind": "phase", "phase": 4, "state": "working"}, phase4
        with open(os.path.join(build_dir, "build.progress"), encoding="utf-8") as handle:
            assert json.load(handle)["phase"] == 4

        resume = gate.next_prompt(last, phase4, "clean")
        assert "PASSED" in resume and "Phase 4" in resume
        assert "report_tome_progress.py BUILD_ID 4 validating" in resume
        assert "wherever they occur in the cumulative tome" in gate.repair_prompt(last, "bad")

wrapped = scoped_shell_command("true", "/")
assert "--unshare-pid" in wrapped and "--proc" in wrapped


class FakeWarmSession(single_author.AuthorSession):
    def __init__(self):
        super().__init__("warm", "codex-cli", "test", "", "", "external", 7, "warm-session")
        self.prompts = []
        self.states = []

    def read_controls(self):
        return

    def state(self, state, **extra):
        self.states.append((state, extra))

    def run_turn(self, prompt, conversation_kind="system", conversation_text=""):
        self.prompts.append(prompt)
        active = gate.current_unit("warm", 7)
        gate._write_phase("warm", active["phase"], "validating")
        return "complete", ""


with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    with patch.object(gate, "BUILD_DIR", build_dir), patch.object(gate, "REPO", root), \
            patch.object(single_author, "BUILD_DIR", build_dir), \
            patch.object(single_author, "validate_unit", return_value=(True, "clean")):
        gate._write_phase("warm", 7, "working")
        session = FakeWarmSession()
        assert session.run() == 0
        assert session.session_id == "warm-session"
        assert len(session.prompts) == 2
        assert "Phase 7" in session.prompts[0]
        assert "HARNESS VALIDATION PASSED for Phase 7" in session.prompts[1]
        assert "Continue with Phase 8" in session.prompts[1]
        assert session.states[-1][0] == "complete"


class UnlimitedRepairSession(FakeWarmSession):
    def __init__(self):
        super().__init__()
        self.from_phase = 8


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
            patch.object(single_author, "validate_unit", side_effect=eventually_clean):
        gate._write_phase("warm", 8, "working")
        session = UnlimitedRepairSession()
        assert session.run() == 0
        assert attempts[0] == 13
        assert len(session.prompts) == 13
        assert not any(state == "paused" for state, _extra in session.states)

print("single-author mechanical gates: OK")
