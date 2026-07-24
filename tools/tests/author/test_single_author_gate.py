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
from tools.buildlib.single_author import section_review  # noqa: E402
from tools.buildlib.single_author import full_review  # noqa: E402
from tools.buildlib.workflow import section_progress  # noqa: E402
from arcanum.platform.agent_commands import scoped_runner_command, scoped_shell_command  # noqa: E402
from arcanum.platform.agent_commands import _claude_command, _codex_command  # noqa: E402
from arcanum.ai import NO_TOME_MEMORY_POLICY  # noqa: E402
from tools.buildlib import single_author  # noqa: E402
from tools.buildlib.single_author import runtime as single_author_runtime  # noqa: E402
from tools.buildlib.single_author import scope as single_author_scope  # noqa: E402
from tools.buildlib.authoring import phases as authoring_phases  # noqa: E402
from tools.buildlib.planning_review import (planning_authority,
                                            planning_dynamic_authority,
                                            planning_prompt)  # noqa: E402
from tools.buildlib.prerequisites.prompt import prerequisite_prompt  # noqa: E402
from tools.buildlib.section_quality_contract import (  # noqa: E402
    section_quality_authority,
    section_quality_contract_packet,
)
from tools.workflow.context import render_section_context  # noqa: E402
from tools.buildlib.single_author.session.support import author_prompt  # noqa: E402


# Every persistent CLI role receives the same absolute no-tome-memory instruction. Root provider
# instruction files cover fresh manual sessions in this checkout as well as harness-created turns.
with patch.object(full_review, "inventory", return_value=[]):
    role_prompts = (
        author_prompt("build", "concept", "internal"),
        planning_prompt(1, "", []),
        planning_prompt(2, "", []),
        prerequisite_prompt("", "s01", [], "", 1),
        full_review.prompt("build", "course"),
    )
assert all(prompt.count(NO_TOME_MEMORY_POLICY) == 1 for prompt in role_prompts)
for provider_file in ("AGENTS.md", "CLAUDE.md"):
    provider_policy = (_BOOTSTRAP_REPO / provider_file).read_text(encoding="utf-8")
    assert "Never save anything about Arcanum tomes" in provider_policy
assert "memories = false" in (_BOOTSTRAP_REPO / ".codex" / "config.toml").read_text(
    encoding="utf-8")
assert json.loads((_BOOTSTRAP_REPO / ".claude" / "settings.json").read_text(
    encoding="utf-8"))["autoMemoryEnabled"] is False
codex_without_memory = _codex_command(["codex", "exec", "-"])
codex_memory_setting = codex_without_memory.index("features.memories=false")
assert codex_without_memory[codex_memory_setting - 1] == "-c"
assert codex_memory_setting < codex_without_memory.index("exec")
claude_without_memory = _claude_command(["claude", "-p"], str(_BOOTSTRAP_REPO))
assert "--safe-mode" in claude_without_memory
claude_settings = json.loads(claude_without_memory[claude_without_memory.index("--settings") + 1])
assert claude_settings["autoMemoryEnabled"] is False


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


# The bounded author packet embeds the exact contract used by Validator AI, not a
# separately maintained summary that can drift later.
with tempfile.TemporaryDirectory() as packet_root, \
        patch.object(render_section_context, "REPO", packet_root), \
        patch.object(render_section_context, "context", return_value={
            "tid": "course", "tooling": "external", "plan": "build.plan.md"}), \
        patch.object(render_section_context, "load_course_map", return_value={
            "sections": [{"id": "s01", "nodes": []}],
            "plannedObligations": [], "acceptanceScenarios": []}), \
        patch.object(render_section_context, "ledger_path",
                     return_value=os.path.join(packet_root, "ledger.json")), \
        patch.object(render_section_context, "handoff_path",
                     return_value=os.path.join(packet_root, "handoff.json")):
    bounded_packet = json.loads(render_section_context.render("build", "s01"))
assert bounded_packet["sectionQualityContract"] == section_quality_contract_packet()


with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    tome_dir = os.path.join(root, "tomes", "course")
    os.makedirs(build_dir)
    os.makedirs(tome_dir)
    with open(os.path.join(build_dir, "build.plan.md"), "w", encoding="utf-8") as handle:
        handle.write("- **Tooling:** external\n")
    with open(os.path.join(build_dir, "build.launch.json"), "w", encoding="utf-8") as handle:
        json.dump({"gate": {"prior_level": 2, "prior_knowledge": "names and literals",
                            "depth": 7, "mastery": 3}}, handle)
    map_file = os.path.join(build_dir, "build.course-map.json")
    with open(map_file, "w", encoding="utf-8") as handle:
        handle.write("{}\n")
    course = {"sections": [{"id": "s01"}, {"id": "s02"}]}
    state = {"sections": [{"id": "s01", "status": "planned"},
                          {"id": "s02", "status": "planned"}]}

    with patch.object(gate, "BUILD_DIR", build_dir), patch.object(gate, "REPO", root), \
            patch.object(section_review, "BUILD_DIR", build_dir), \
            patch.object(section_progress, "BUILD_DIR", build_dir), \
            patch.object(gate, "resolve_working_id", return_value="course"), \
            patch.object(gate, "tome_section_ids", return_value=["s01", "s02"]), \
            patch.object(gate, "map_path", return_value=map_file), \
            patch.object(gate, "load_course_map", return_value=course), \
            patch.object(gate, "derive_course_state", return_value=state), \
            patch.object(gate, "prepare_handoff"), \
            patch.object(section_review, "review_prerequisites", return_value={"status": "PASS"}), \
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
                patch.object(section_review, "review_prerequisites") as validator_call:
            failed, failed_report = gate.validate_unit("build", last)
        assert not failed and "mechanical failure" in failed_report
        validator_call.assert_not_called()

        with patch.object(gate, "validate_section", return_value=(True, "section clean")), \
                patch.object(gate, "validate_phase3", return_value=(False, "full failure")), \
                patch.object(gate, "record_section_failure"), \
                patch.object(section_review, "review_prerequisites") as validator_call:
            failed, failed_report = gate.validate_unit("build", last)
        assert not failed and "full failure" in failed_report
        validator_call.assert_not_called()

        phase4 = gate.advance_unit("build", last)
        assert phase4 == {"kind": "phase", "phase": 4, "state": "working"}, phase4
        with open(os.path.join(build_dir, "build.progress"), encoding="utf-8") as handle:
            assert json.load(handle)["phase"] == 4

        resume = gate.next_prompt("build", last, phase4, "clean")
        assert "PASSED" in resume and "Phase 4" in resume
        assert "python3 tools/workflow/report_tome_progress.py build 4 validating" in resume
        assert "BUILD_ID" not in resume
        assert "--build-phase 4 --phase-only" in resume, resume
        repair = gate.repair_prompt("build", last, "bad")
        assert "wherever they occur in the cumulative tome" in repair
        assert "--source-only" not in repair, repair
        assert "Do not run or imitate the Validator AI" in repair
        assert "tools/validate_section.py" in repair
        assert "tools/validate_phase3.py" in repair
        assert "complete repair packet" in repair
        assert "render_section_context.py" not in repair
        assert repair.count(
            section_quality_authority(2, "names and literals", 7, 3)) == 1
        assert "whole-section coverage sweep" in repair
        section_prompt = gate.unit_prompt("build", ready)
        assert "tools/validate_section.py" in section_prompt
        assert ("python3 tools/workflow/report_section_progress.py build s01 1 2 validating"
                in section_prompt)
        assert "--source-only" not in section_prompt
        assert "ALWAYS run every listed command" in section_prompt
        assert "HARNESS_BLOCKED" in section_prompt
        assert "HARNESS_REPAIR_REQUIRED" not in section_prompt
        assert "$1–2 API-equivalent per section" in section_prompt
        assert "sectionQualityContract" in section_prompt
        assert "exact binding policy used by the Validator AI" in section_prompt
        assert section_prompt.count(
            section_quality_authority(2, "names and literals", 7, 3)) == 1
        assert "HARDENED SOURCE AND ADVERSARIAL EVIDENCE" in section_prompt
        assert ("at least two distinct non-build deterministic scenarios"
                in " ".join(section_prompt.split()))
        assert "whole-section coverage sweep" in section_prompt
        assert "all five facts" in section_prompt
        assert section_prompt.endswith("HARNESS COURSE CONTROL")
        phase1_prompt = gate.unit_prompt(
            "build", {"kind": "phase", "phase": 1, "state": "working"})
        assert phase1_prompt.count(planning_authority(1)) == 1
        assert phase1_prompt.count(planning_dynamic_authority(
            "build", 1, build_dir=build_dir)) == 1
        assert "runtime repair must never put a Makefile" in phase1_prompt
        phase1_repair = gate.repair_prompt(
            "build", {"kind": "phase", "phase": 1, "state": "validating"}, "bad")
        assert phase1_repair.count(planning_authority(1)) == 1
        assert phase1_repair.count(planning_dynamic_authority(
            "build", 1, build_dir=build_dir)) == 1
        phase2_prompt = gate.unit_prompt(
            "build", {"kind": "phase", "phase": 2, "state": "working"})
        assert phase2_prompt.count(planning_authority(2)) == 1
        assert phase2_prompt.count(planning_dynamic_authority(
            "build", 2, build_dir=build_dir)) == 1
        assert "authority block controls family meaning" in phase2_prompt
        assert "other repairable paths it names" in phase2_prompt
        assert "materialize_phase2_map.py build --preview" in phase2_prompt
        assert "--phase-2-proposal" in phase2_prompt
        phase2_repair = gate.repair_prompt(
            "build", {"kind": "phase", "phase": 2, "state": "validating"}, "bad")
        assert phase2_repair.count(planning_authority(2)) == 1
        assert phase2_repair.count(planning_dynamic_authority(
            "build", 2, build_dir=build_dir)) == 1
        # Every phase exposes the same exact mechanical commands the harness repeats.
        phase2_checks = gate.self_validation_commands(
            "build", {"kind": "phase", "phase": 2, "state": "working"})
        assert len(phase2_checks) == 2
        assert phase2_checks[0] == (
            "python3 tools/workflow/materialize_phase2_map.py build --preview")
        assert "--phase-2-skeleton" in phase2_checks[1]
        assert "--no-run" in phase2_checks[1]
        assert "--phase-2-proposal" in phase2_checks[1]
        shipping_checks = gate.self_validation_commands(
            "build", {"kind": "phase", "phase": 7, "state": "working"})
        assert len(shipping_checks) == 3
        assert shipping_checks[0] == (
            "python3 tools/gen_mastery_labs.py course --build-id build")
        assert "tools/validate_phase3.py" in shipping_checks[1]
        assert "--strict" in shipping_checks[1]
        assert shipping_checks[2] == "python3 tools/smoke_tome.py course"
        final_section_checks = gate.self_validation_commands("build", last)
        assert len(final_section_checks) == 2
        assert "tools/validate_section.py" in final_section_checks[0]
        assert "tools/validate_phase3.py" in final_section_checks[1]
        for phase in (1, 2, 4, 5, 6, 7, 8):
            phase_unit = {"kind": "phase", "phase": phase, "state": "working"}
            phase_prompt = gate.unit_prompt("build", phase_unit)
            checks = gate.self_validation_commands("build", phase_unit)
            assert checks and all(f"`{command}`" in phase_prompt for command in checks), (
                phase, checks, phase_prompt)

assert gate.validation_issue_count(
    "ERROR plan: first\nWARN plan: second\n-- plan: 1 error(s), 1 warning(s)") == 2
assert gate.validation_issue_count("-- tome: 3 error(s), 2 warning(s)") == 5
assert gate.validation_issue_count("# FAIL\n\nIssues found: 4\n\nRepairs") == 4
failure_text = gate.validation_failure_message(
    {"kind": "phase", "phase": 1}, "ERROR plan: one")
assert failure_text.endswith("(1 issues found)"), failure_text
assert "repeated finding was not cleared" in failure_text

blocked = (
    "HARNESS_BLOCKED:\n"
    "COMMAND: `python3 tools/workflow/context/render_section_context.py build s01`\n"
    "DIAGNOSTIC:\npacket too large")
assert gate.author_blocked_command(blocked) == [
    "python3", "tools/workflow/context/render_section_context.py", "build", "s01"]
with patch.object(gate, "self_validation_argvs", return_value=[]), \
        patch.object(gate, "context", return_value={"tid": "course"}), \
        patch.object(
            gate, "run_harness_command",
            return_value=subprocess.CompletedProcess(
                ["python3", "tools/workflow/context/render_section_context.py",
                 "build", "s01"],
                0, stdout='{"version":1}\n', stderr="")) as reproduce:
    blocked_kind, blocked_ok, blocked_report = gate.validate_author_blocked_check(
        "build", {"kind": "section", "section": "s01"}, blocked)
assert (blocked_kind, blocked_ok) == ("bootstrap", True)
assert '"version":1' in blocked_report
reproduce.assert_called_once_with(
    ["python3", "tools/workflow/context/render_section_context.py", "build", "s01"],
    "course")
try:
    gate.author_blocked_command("HARNESS_BLOCKED:\nDIAGNOSTIC:\nbroken")
except Exception as exc:
    assert "missing required" in str(exc)
else:
    raise AssertionError("a commandless HARNESS_BLOCKED report was accepted")

phase2_context = {
    "tid": "course", "tooling": "external", "plan": ".tome-build/build.plan.md"}
expected_phase2 = authoring_phases._phase2_commands("build", phase2_context)
with patch.object(
        authoring_phases, "run_harness_command",
        side_effect=lambda command, _tid: subprocess.CompletedProcess(
            command, 0, stdout="mechanical clean\n", stderr="")) as phase2_run, \
        patch.object(authoring_phases, "materialize_author_spec") as publish_proposal:
    phase2_ok, phase2_report = authoring_phases._phase2("build", phase2_context)
assert phase2_ok and "mechanical clean" in phase2_report
assert [call.args[0] for call in phase2_run.call_args_list] == expected_phase2
publish_proposal.assert_called_once_with("build")

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
resumed_opencode = single_author_runtime.resume_command(
    "opencode-cli", "opencode-go/deepseek-v4-pro", "max",
    "same-model-conversation", "continue")[1]
assert resumed_opencode[resumed_opencode.index("--session") + 1] == "same-model-conversation"
assert resumed_opencode[resumed_opencode.index("-m") + 1] == "opencode-go/deepseek-v4-pro"
assert resumed_opencode[resumed_opencode.index("--variant") + 1] == "max"
with patch.object(single_author, "current_unit", return_value={
        "kind": "section", "phase": 3, "section": "s01"}), \
        patch("arcanum.platform.agent_scratch.provider_session_exists",
              return_value=False) as session_available:
    migrated_opencode = single_author.AuthorSession(
        "build", "opencode-cli", "openrouter/deepseek/deepseek-v4-pro", "",
        "course", "external", from_phase=3, resume_id="orphan")
assert migrated_opencode.session_id == ""
session_available.assert_called_once_with(
    "opencode", "build", "author", 3, "s01", "orphan")
assert "PLANNING ESCALATION" not in _BootstrapPath(
    single_author.__file__).read_text(encoding="utf-8")

with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    author_root = os.path.join(build_dir, "build.course-map-author")
    proposal = os.path.join(build_dir, "build.course-map.proposal.json")
    ledger = os.path.join(build_dir, "build.phase2-research.json")
    tome = os.path.join(root, "tomes", "course")
    runtimes = os.path.join(root, "global-configs", "runtimes")
    for directory in (author_root, tome, runtimes):
        os.makedirs(directory, exist_ok=True)
    for path in (proposal, ledger):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{}\n")
    missing = lambda name: os.path.join(build_dir, "missing-" + name)
    with patch.object(single_author_scope, "BUILD_DIR", build_dir), \
            patch.object(single_author_scope, "REPO", root), \
            patch.object(single_author_scope, "VALIDATOR_FAILURE_DIR",
                         os.path.join(root, "validator-failures")), \
            patch.object(single_author_scope, "proposal_path", return_value=proposal), \
            patch.object(single_author_scope, "spec_root", return_value=author_root), \
            patch.object(single_author_scope, "ledger_path", return_value=ledger), \
            patch.object(single_author_scope, "seed_path",
                         return_value=missing("seed")), \
            patch.object(single_author_scope, "map_path",
                         return_value=missing("map")), \
            patch.object(single_author_scope, "amendment_path",
                         return_value=missing("amendment")), \
            patch.object(single_author_scope, "state_path",
                         return_value=missing("state")), \
            patch.object(single_author_scope, "evidence_dir",
                         return_value=missing("evidence")), \
            patch.object(single_author_scope, "failure_dir",
                         return_value=missing("failure")), \
            patch.object(single_author_scope, "prerequisite_calls_path",
                         return_value=missing("calls")):
        writable, protected = single_author_scope.author_paths(
            "build", 2, "course", {"kind": "phase", "phase": 2})
    assert author_root in writable and ledger in writable
    assert tome in writable and runtimes in writable
    assert proposal not in writable
    assert proposal in protected

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


# Claude and Codex keep auth/session state writable, but their persistent-memory subtrees are
# empty process-local overlays: old content is invisible and attempted writes vanish on exit.
with tempfile.TemporaryDirectory() as root:
    fake_home = os.path.join(root, "home")
    memory_dirs = {
        "codex": os.path.join(fake_home, ".codex", "memories"),
        "claude": os.path.join(fake_home, ".claude", "projects", "repo", "memory"),
    }
    os.makedirs(os.path.join(fake_home, ".claude", "agent-memory"))
    for memory in memory_dirs.values():
        os.makedirs(memory, exist_ok=True)
        with open(os.path.join(memory, "old.txt"), "w", encoding="utf-8") as handle:
            handle.write("stored tome memory\n")
    for provider, memory in memory_dirs.items():
        fake = os.path.join(root, provider)
        with open(fake, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\n"
                         "test ! -e \"$MEMORY_DIR/old.txt\" || exit 31\n"
                         "printf transient > \"$MEMORY_DIR/new.txt\" || exit 32\n"
                         "test -e \"$MEMORY_DIR/new.txt\" || exit 33\n")
        os.chmod(fake, 0o755)
        with patch.dict(os.environ, {"HOME": fake_home}):
            command = scoped_runner_command(
                f"{provider} memory boundary", [fake, "exec"], root, [], root)
            process = subprocess.run(
                command, env={**os.environ, "MEMORY_DIR": memory},
                capture_output=True, text=True)
        assert process.returncode == 0, (provider, process.stdout, process.stderr)
        assert command.count("--tmpfs") >= 1
        if provider == "codex":
            assert "features.memories=false" in command
        else:
            setting = command.index("--setenv")
            assert command[setting:setting + 3] == [
                "--setenv", "CLAUDE_CODE_DISABLE_AUTO_MEMORY", "1"]
        assert os.path.exists(os.path.join(memory, "old.txt"))
        assert not os.path.exists(os.path.join(memory, "new.txt"))


print("single-author mechanical gates: OK")
