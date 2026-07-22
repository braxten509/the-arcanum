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
from tools.buildlib.workflow import section_progress  # noqa: E402
from arcanum.platform.agent_commands import scoped_runner_command, scoped_shell_command  # noqa: E402
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
            patch.object(gate, "resolve_working_id", return_value="course"), \
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
        assert "complete repair packet" in repair
        assert "render_section_context.py" not in repair
        section_prompt = gate.unit_prompt("build", ready)
        assert "tools/validate_section.py tomes/course s01" in section_prompt
        assert ("python3 tools/workflow/report_section_progress.py build s01 1 2 validating"
                in section_prompt)
        assert "--source-only" in section_prompt
        assert "do not substitute ad-hoc" in section_prompt.lower()
        assert "HARNESS_BLOCKED:" in section_prompt
        assert "$1–2 API-equivalent per section" in section_prompt
        assert section_prompt.endswith("HARNESS COURSE CONTROL")
        phase2_checks = gate.self_validation_commands(
            "build", {"kind": "phase", "phase": 2, "state": "working"})
        assert len(phase2_checks) == 2
        assert phase2_checks[0] == "python3 tools/workflow/materialize_phase2_map.py build"
        assert "--phase-2-skeleton" in phase2_checks[1]
        assert "--no-run" in phase2_checks[1]
        shipping_checks = gate.self_validation_commands(
            "build", {"kind": "phase", "phase": 7, "state": "working"})
        assert len(shipping_checks) == 3
        assert shipping_checks[0] == (
            "python3 tools/gen_mastery_labs.py course --build-id build")
        assert "tools/validate_phase3.py" in shipping_checks[1]
        assert "--strict" in shipping_checks[1]
        assert shipping_checks[2] == "python3 tools/smoke_tome.py course"

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
assert single_author._authoritative_session_id(
    "stale-resume", '{"type":"thread.started","thread_id":"actual-thread"}'
) == "actual-thread"

repo = str(_BOOTSTRAP_REPO)
for helper in ("workflow/report_tome_progress.py", "workflow/report_section_progress.py",
               "workflow/context/render_phase2_context.py",
               "workflow/render_phase2_context.py",
               "workflow/materialize_phase2_map.py", "validate_section.py"):
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
assert resumed_codex[resumed_codex.index("-m") + 1] == "gpt-5.6-terra"
assert "PLANNING ESCALATION" not in _BootstrapPath(
    single_author.__file__).read_text(encoding="utf-8")

with tempfile.TemporaryDirectory() as root:
    writable = os.path.join(root, "build")
    os.makedirs(writable)
    git_secret = os.path.join(root, ".git", "old-phase.txt")
    os.makedirs(os.path.dirname(git_secret))
    with open(git_secret, "w", encoding="utf-8") as handle:
        handle.write("abandoned phase")
    hidden_dir = os.path.join(writable, "phase-snapshots")
    os.makedirs(hidden_dir)
    with open(os.path.join(hidden_dir, "old.txt"), "w", encoding="utf-8") as handle:
        handle.write("abandoned phase")
    hidden_file = os.path.join(writable, "review-calls.jsonl")
    with open(hidden_file, "w", encoding="utf-8") as handle:
        handle.write("abandoned phase\n")
    sealed = os.path.join(writable, "sealed-map.json")
    current = os.path.join(writable, "current-handoff.json")
    with open(sealed, "w", encoding="utf-8") as handle:
        handle.write("sealed\n")
    with open(current, "w", encoding="utf-8") as handle:
        handle.write("empty\n")
    fake = os.path.join(root, "codex")
    with open(fake, "w", encoding="utf-8") as handle:
        handle.write("#!/bin/sh\ntest ! -e \"$GIT_SECRET\" || exit 21\n"
                     "test ! -e \"$HIDDEN_DIR/old.txt\" || exit 22\n"
                     "test ! -s \"$HIDDEN_FILE\" || exit 23\n"
                     "printf tampered > \"$SEALED\" 2>/dev/null || true\n"
                     "printf authored > \"$CURRENT\"\n")
    os.chmod(fake, 0o755)
    command = scoped_runner_command("boundary test", [fake, "exec"], root, [writable], root,
                                    readonly_paths=[sealed],
                                    hidden_paths=[hidden_dir, hidden_file])
    environment = {**os.environ, "SEALED": sealed, "CURRENT": current,
                   "GIT_SECRET": git_secret, "HIDDEN_DIR": hidden_dir,
                   "HIDDEN_FILE": hidden_file}
    process = subprocess.run(command, env=environment, capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    assert open(sealed, encoding="utf-8").read() == "sealed\n"
    assert open(current, encoding="utf-8").read() == "authored"


print("single-author mechanical gates: OK")
