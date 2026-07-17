#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""The sole author stops at every harness-owned phase and section gate."""
import json
import os
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.buildlib.single_author import gate  # noqa: E402
from tools.buildlib import measure  # noqa: E402
from tools.buildlib.workflow import section_progress  # noqa: E402
from tools.buildlib.runtime.agent_runtime import scoped_runner_command, scoped_shell_command  # noqa: E402
from tools.buildlib import single_author  # noqa: E402
from tools.buildlib.single_author import runtime as single_author_runtime  # noqa: E402


# Provider streams may contain JSON primitives or malformed nested rows. They are
# ignorable transport noise, not a reason for the harness process itself to crash.
for primitive in ('"Output:"', "null", "[]", "42", "true"):
    assert single_author_runtime.assistant_text(primitive) == ""
    assert single_author_runtime.opencode_output_session_id(primitive) == ""
assert single_author_runtime.assistant_text(
    '{"type":"item.completed","item":"not-an-object"}') == ""
assert single_author_runtime.assistant_text(
    '{"type":"item.completed","item":{"type":"agent_message","text":"ready"}}') == "ready"
assert single_author_runtime.usage_from_line(
    '{"type":"turn.completed","usage":{"input_tokens":100,"cached_input_tokens":80,'
    '"output_tokens":12}}') == {
        "inputTokens": 100, "cachedInputTokens": 80, "outputTokens": 12,
        "freshInputTokens": 20}


with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    tome_dir = os.path.join(root, "tomes", "course")
    os.makedirs(build_dir)
    os.makedirs(tome_dir)
    with open(os.path.join(build_dir, "build.plan.md"), "w", encoding="utf-8") as handle:
        handle.write("- **Tooling:** external\n")
    map_file = os.path.join(build_dir, "build.course-map.json")
    with open(map_file, "w", encoding="utf-8") as handle:
        handle.write("{}\n")
    course = {"sections": [{"id": "s01"}, {"id": "s02"}]}
    state = {"sections": [{"id": "s01", "status": "planned"},
                          {"id": "s02", "status": "planned"}]}

    with patch.object(gate, "BUILD_DIR", build_dir), patch.object(gate, "REPO", root), \
            patch.object(section_progress, "BUILD_DIR", build_dir), \
            patch.object(gate, "resolve_working_tid", return_value="course"), \
            patch.object(gate, "tome_section_ids", return_value=["s01", "s02"]), \
            patch.object(gate, "map_path", return_value=map_file), \
            patch.object(gate, "load_course_map", return_value=course), \
            patch.object(gate, "derive_course_state", return_value=state), \
            patch.object(gate, "prepare_handoff"), \
            patch.object(gate, "review_prerequisites", return_value={"status": "PASS"}), \
            patch.object(gate, "record_section_verification", return_value={
                "activeObligations": [], "sections": [{"id": "s01", "status": "verified"},
                                                       {"id": "s02", "status": "verified"}]}), \
            patch.object(gate, "append_course_control", side_effect=lambda prompt, *_args: prompt + "\nHARNESS COURSE CONTROL"):
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
        state["sections"][0]["status"] = "verified"
        with patch.object(gate, "validate_section", return_value=(True, "section clean")) as section, \
                patch.object(gate, "validate_phase3", return_value=(True, "window clean")) as window:
            ok, report = gate.validate_unit("build", last)
        assert ok and "section clean" in report and "window clean" in report
        section.assert_called_once()
        window.assert_called_once()

        with patch.object(gate, "validate_section", return_value=(False, "mechanical failure")), \
                patch.object(gate, "review_prerequisites") as validator_call:
            failed, failed_report = gate.validate_unit("build", last)
        assert not failed and "mechanical failure" in failed_report
        validator_call.assert_not_called()

        phase4 = gate.advance_unit("build", last)
        assert phase4 == {"kind": "phase", "phase": 4, "state": "working"}, phase4
        with open(os.path.join(build_dir, "build.progress"), encoding="utf-8") as handle:
            assert json.load(handle)["phase"] == 4

        resume = gate.next_prompt("build", last, phase4, "clean")
        assert "PASSED" in resume and "Phase 4" in resume
        assert "python3 tools/workflow/report_tome_progress.py build 4 validating" in resume
        assert "BUILD_ID" not in resume
        assert "--build-phase 4 --phase-only --no-run" in resume, resume
        repair = gate.repair_prompt("build", last, "bad")
        assert "wherever they occur in the cumulative tome" in repair
        assert "--source-only" in repair, repair
        section_prompt = gate.unit_prompt("build", ready)
        assert "tools/validate_section.py tomes/course s01" in section_prompt
        assert ("python3 tools/workflow/report_section_progress.py build s01 1 2 validating"
                in section_prompt)
        assert "--source-only" in section_prompt
        assert "do not substitute ad-hoc" in section_prompt.lower()
        assert "HARNESS_BLOCKED:" in section_prompt
        assert section_prompt.endswith("HARNESS COURSE CONTROL")
        phase2_checks = gate.self_validation_commands(
            "build", {"kind": "phase", "phase": 2, "state": "working"})
        assert len(phase2_checks) == 1
        assert "--phase-2-skeleton" in phase2_checks[0]
        assert "--no-run" in phase2_checks[0]
        shipping_checks = gate.self_validation_commands(
            "build", {"kind": "phase", "phase": 7, "state": "working"})
        assert len(shipping_checks) == 2
        assert "tools/validate_phase3.py" in shipping_checks[0]
        assert "--strict" in shipping_checks[0]
        assert shipping_checks[1] == "python3 tools/smoke_tome.py course"

wrapped = scoped_shell_command("true", "/")
assert "--unshare-pid" in wrapped and "--proc" in wrapped

with tempfile.TemporaryDirectory() as root:
    fake = os.path.join(root, "opencode")
    with open(fake, "w", encoding="utf-8") as handle:
        handle.write("#!/bin/sh\nexit 0\n")
    os.chmod(fake, 0o755)
    command = scoped_runner_command("OpenCode startup", [fake, "run"], root, [], root)
    setting = command.index("--setenv")
    assert command[setting:setting + 3] == [
        "--setenv", "OPENCODE_DISABLE_PRUNE", "true"]

assert single_author._opencode_output_session_id(json.dumps({
    "type": "step_start", "sessionID": "session-exact"})) == "session-exact"

repo = str(_BOOTSTRAP_REPO)
for helper in ("workflow/report_tome_progress.py", "workflow/report_section_progress.py",
               "validate_section.py"):
    result = subprocess.run(
        [sys.executable, os.path.join(repo, "tools", helper), "--help"], cwd=repo,
        capture_output=True, text=True, check=False)
    assert result.returncode == 0, (helper, result.stdout, result.stderr)
assert single_author._runner_stdin("arg") == subprocess.DEVNULL
assert single_author._runner_stdin("stdin") == subprocess.PIPE
initial_codex = single_author_runtime.initial_runner("codex-cli", "gpt-5.6-terra", "medium")[1]
assert "model_auto_compact_token_limit=80000" in initial_codex
resumed_codex = single_author_runtime.resume_command(
    "codex-cli", "gpt-5.6-terra", "medium", "session", "continue")[1]
assert "model_auto_compact_token_limit=80000" in resumed_codex

with tempfile.TemporaryDirectory() as root:
    writable = os.path.join(root, "build")
    os.makedirs(writable)
    sealed = os.path.join(writable, "sealed-map.json")
    current = os.path.join(writable, "current-handoff.json")
    with open(sealed, "w", encoding="utf-8") as handle:
        handle.write("sealed\n")
    with open(current, "w", encoding="utf-8") as handle:
        handle.write("empty\n")
    fake = os.path.join(root, "codex")
    with open(fake, "w", encoding="utf-8") as handle:
        handle.write("#!/bin/sh\nprintf tampered > \"$SEALED\" 2>/dev/null || true\n"
                     "printf authored > \"$CURRENT\"\n")
    os.chmod(fake, 0o755)
    command = scoped_runner_command("boundary test", [fake, "exec"], root, [writable], root,
                                    readonly_paths=[sealed])
    environment = {**os.environ, "SEALED": sealed, "CURRENT": current}
    process = subprocess.run(command, env=environment, capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    assert open(sealed, encoding="utf-8").read() == "sealed\n"
    assert open(current, encoding="utf-8").read() == "authored"


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
            patch.object(single_author, "preflight_unit"), \
            patch.object(single_author, "validate_unit", return_value=(True, "clean")):
        gate._write_phase("warm", 7, "working")
        session = FakeWarmSession()
        assert session.run() == 0
        assert session.session_id == ""
        assert len(session.prompts) == 2
        assert "Phase 7" in session.prompts[0]
        assert "HARNESS VALIDATION PASSED for Phase 7" in session.prompts[1]
        assert "Continue with Phase 8" in session.prompts[1]
        assert "active unit author" in session.prompts[1]
        assert session.states[-1][0] == "complete"


class RoutedWarmSession(FakeWarmSession):
    def __init__(self):
        single_author.AuthorSession.__init__(
            self, "routed", "codex-cli", "sections", "high", "", "external", 7,
            "sections-warm", phase_authors={
                "phase12": ("claude-cli", "arc", "high"),
                "phase37": ("codex-cli", "sections", "high"),
                "phase8": ("opencode-cli", "student-review", "max"),
            })
        self.prompts = []
        self.states = []

    def run_turn(self, prompt, conversation_kind="system", conversation_text=""):
        self.prompts.append(prompt)
        active = gate.current_unit("routed", 7)
        gate._write_phase("routed", active["phase"], "validating")
        return "complete", ""


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
            patch.object(single_author, "preflight_unit"), \
            patch.object(single_author, "validate_unit", side_effect=eventually_clean):
        gate._write_phase("warm", 8, "working")
        session = UnlimitedRepairSession()
        assert session.run() == 0
        assert attempts[0] == 13
        assert len(session.prompts) == 13
        assert not any(state == "paused" for state, _extra in session.states)


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


class ExplicitBlockedSession(UnlimitedRepairSession):
    def run_turn(self, prompt, conversation_kind="system", conversation_text=""):
        self.prompts.append(prompt)
        return "harness-blocked", "HARNESS_BLOCKED: validator import failed"


# The explicit author-side circuit breaker is terminal until an operator resumes it.
with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    with patch.object(gate, "BUILD_DIR", build_dir), patch.object(gate, "REPO", root), \
            patch.object(single_author, "BUILD_DIR", build_dir), \
            patch.object(single_author, "preflight_unit"), \
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

print("single-author mechanical gates: OK")
