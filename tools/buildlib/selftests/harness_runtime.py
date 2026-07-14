"""Regression checks for runner, prompt, access, and runtime harness contracts."""
import json
import os
import shutil
import subprocess
from unittest.mock import patch

from .. import BUILD_DIR, REPO
from .. import sections as sections_module
from ..agent_runtime import scoped_runner_command
from ..checkpoints import ARC_PARTS
from ..liveness import _cpu_ticks, _descendants, _has_live_conn
from ..measure import (blocking_report, review_changes, review_inventory,
                       runtime_config_inventory, runtime_config_scope_violations,
                       phase3_validator_argv, phase3_validator_shell_command,
                       section_validator_argv, section_validator_shell_command,
                       section_window_validator_argv,
                       section_window_validator_shell_command,
                       selected_runtime_config, validate, validate_phase3, validate_shipping,
                       validate_section, validate_section_window,
                       validator_argv, validator_shell_command)
from ..prompts import (GATE_QS, PREAMBLE, PRIOR_LEVELS, REPAIR_ONLY, STUDENT_HOOK,
                       build_prompt, current_start_calibration, gate_errors,
                       read_prior_level, repair_verification_focus,
                       review_pass_eligible, write_plan)
from ..runners import _implicit_fallback, _spec_to_runner, default_runner, parse_fallbacks
from ..section_security_selftest import run as section_security_selftest
from ..sections import (_load_sections_done, _mark_section_done, _sections_done_path,
                        prepare_whole_tome_warm_worker, section_ids, section_progress_path,
                        section_progress_shell_command, wipe_sections)
from ..workflow import (RUNTIME_CONFIG_DIR, access_boundary, parse_phases,
                        phase_sidecars, phase_writable_paths, support_prompt)


def run():
    section_security_selftest(_spec_to_runner)
    d, cmd, im = _spec_to_runner("opencode-cli:opencode-go/deepseek-v4-flash", "--fallback")
    assert cmd[:2] == ["opencode", "run"] and "opencode-go/deepseek-v4-flash" in cmd, cmd
    assert im == "arg" and d == "opencode-cli opencode-go/deepseek-v4-flash", (im, d)
    _, ccmd, _ = _spec_to_runner("codex-cli:gpt-5.5@high", "--fallback")
    assert ccmd[-1] == "-" and "model_reasoning_effort=high" in ccmd, ccmd
    _, gcmd, gim = _spec_to_runner("antigravity-cli:gemini-3-pro", "--runner")
    assert gcmd[-1] == "--print" and gim == "arg", gcmd
    fb = parse_fallbacks(["opencode-cli:a", "codex-cli:b"])
    assert [x[0] for x in fb] == ["opencode-cli a", "codex-cli b"], fb
    cfg = {"default": "d", "runners": {"d": {"cmd": ["opencode", "run", "-m", "m"],
                                                "input": "arg"}}}
    same = ("opencode-cli m", ["opencode", "run", "-m", "m"], "arg")
    diff = ("codex-cli x", ["codex", "exec", "-"], "stdin")
    assert _implicit_fallback(cfg, {}, same) == []
    assert _implicit_fallback(cfg, {}, diff) == [default_runner(cfg, {})]
    switch = lambda died, ri, n: died and ri + 1 < n
    assert switch(True, 0, 2) and not switch(False, 0, 2) and not switch(True, 1, 2)

    me = os.getpid()
    assert me in _descendants(me)
    assert _cpu_ticks([me]) > 0
    assert isinstance(_has_live_conn([me]), bool)
    assert section_ids("no-such-tome-xyz") == []

    os.makedirs(BUILD_DIR, exist_ok=True)
    tid = "selftest-resume-xyz"
    try:
        os.remove(_sections_done_path(tid))
    except OSError:
        pass
    assert _load_sections_done(tid) == set()
    _mark_section_done(tid, "s01")
    _mark_section_done(tid, "s03")
    assert _load_sections_done(tid) == {"s01", "s03"}
    os.remove(_sections_done_path(tid))
    sec = os.path.join(REPO, "tomes", tid, "sections")
    os.makedirs(os.path.join(sec, "s01"))
    _mark_section_done(tid, "s01")
    assert wipe_sections(tid) == 1 and not os.path.exists(sec)
    assert _load_sections_done(tid) == set()
    os.rmdir(os.path.join(REPO, "tomes", tid))
    assert wipe_sections("no-such-tome-xyz") == 0

    # Split Phase 3 keeps one provider process warm across a bounded batch, then
    # checkpoints each section independently. This command shape is runner-neutral:
    # the provider adapter still receives one ordinary headless prompt.
    batch_tid = "selftest-warm-batches-xyz"
    batch_root = os.path.join(REPO, "tomes", batch_tid)
    batch_plan = os.path.join(BUILD_DIR, f"{batch_tid}.plan.md")
    batch_done = _sections_done_path(batch_tid)
    batch_progress = section_progress_path(batch_tid)
    os.makedirs(batch_root, exist_ok=True)
    with open(batch_plan, "w", encoding="utf-8") as handle:
        handle.write("**Artifact lifecycle:** none\n")
    handoff_paths = {sid: os.path.join(BUILD_DIR, f"{batch_tid}-{sid}.json")
                     for sid in ("s01", "s02", "s03", "s04", "s05")}
    for path in handoff_paths.values():
        open(path, "a", encoding="utf-8").close()
    try:
        with (patch.object(sections_module, "section_ids",
                           return_value=["s01", "s02", "s03", "s04", "s05"]),
              patch.object(sections_module, "read_tooling", return_value="internal"),
              patch.object(sections_module, "support_prompt", return_value="author contract"),
              patch.object(sections_module, "prepare_handoff",
                           side_effect=lambda _tid, sid, **_kwargs: handoff_paths[sid]),
              patch.object(sections_module, "validate_handoff", return_value=(False, "stub")),
              patch.object(sections_module, "continuity_prompt",
                           side_effect=lambda _tid, sid, *_args: f"\nCONTINUITY {sid}\n"),
              patch.object(sections_module, "section_validator_shell_command",
                           side_effect=lambda _tid, sid, *_args: f"validate-{sid}"),
              patch.object(sections_module, "build_prompt",
                           side_effect=lambda *_args, validation_command=None, **_kwargs:
                           f"PROMPT {validation_command}\n"),
              patch.object(sections_module, "validate_section", return_value=(True, "clean")),
              patch.object(sections_module, "_author_batch", return_value=(0, True)) as worker):
            sections_module.author_sections_split(
                batch_tid, 3, "Sections", [("fake", ["fake"], "stdin")],
                (os.path.relpath(batch_plan, REPO), "verdict", "findings"), {}, {},
                1, 1, None, False, False, batch_tid, batch_size=3)
        assert worker.call_count == 2
        assert worker.call_args_list[0].args[3] == ["s01", "s02", "s03"]
        assert worker.call_args_list[1].args[3] == ["s04", "s05"]
        first_prompt = worker.call_args_list[0].args[2]
        assert "(validate-s01) && (validate-s02) && (validate-s03)" in first_prompt
        assert "until it exits 0 BEFORE moving to the next section" in first_prompt
        assert "report_section_progress.py" in first_prompt
        assert batch_progress in worker.call_args_list[0].args[14]
        assert _load_sections_done(batch_tid) == {"s01", "s02", "s03", "s04", "s05"}
        with open(batch_progress, encoding="utf-8") as handle:
            progress = json.load(handle)
        assert (progress["section"], progress["index"], progress["state"]) == (
            "s05", 5, "complete")
        command = section_progress_shell_command(batch_tid, "s03", 3, 5, "validating", 1, 2)
        assert "s03 3 5 validating --batch 1 --batches 2" in command
    finally:
        shutil.rmtree(batch_root, ignore_errors=True)
        for path in (batch_plan, batch_done, batch_progress, *handoff_paths.values()):
            try:
                os.remove(path)
            except OSError:
                pass

    # Unsplit Phase 3 keeps one provider process for the complete Arc while putting the
    # same section gates and periodic anti-template windows inside that warm context.
    whole_tid = "selftest-whole-warm-xyz"
    whole_progress = section_progress_path(whole_tid)
    whole_handoffs = {sid: os.path.join(BUILD_DIR, f"{whole_tid}-{sid}.json")
                      for sid in ("s01", "s02", "s03", "s04", "s05")}
    for path in whole_handoffs.values():
        open(path, "a", encoding="utf-8").close()
    try:
        with (patch.object(sections_module, "section_ids",
                           return_value=["s01", "s02", "s03", "s04", "s05"]),
              patch.object(sections_module, "prepare_handoff",
                           side_effect=lambda _tid, sid, **_kwargs: whole_handoffs[sid]),
              patch.object(sections_module, "section_validator_shell_command",
                           side_effect=lambda _tid, sid, *_args: f"validate-{sid}"),
              patch.object(sections_module, "section_window_validator_shell_command",
                           side_effect=lambda _tid, sid, *_args: f"window-{sid}")):
            warm_prompt, warm_sidecars = prepare_whole_tome_warm_worker(
                whole_tid, ".tome-build/whole.plan.md", "external", checkpoint_size=3)
        assert "same provider session for every section" in warm_prompt
        assert "validate-s01" in warm_prompt and "validate-s05" in warm_prompt
        assert "window-s03" in warm_prompt and "window-s05" in warm_prompt
        assert "Never run pip/npm/cargo/system package installs" in warm_prompt
        assert "Do not pipe validator output through grep/head" in warm_prompt
        assert warm_sidecars == [*whole_handoffs.values(), whole_progress]
    finally:
        for path in (whole_progress, *whole_handoffs.values()):
            try:
                os.remove(path)
            except OSError:
                pass

    good_gate = [(label, value) for (label, _), value in zip(
        GATE_QS, ("very basic", "2", "7", "6", "3", "external"))]
    assert gate_errors(good_gate) == []
    bad_gate = [(label, "") for label, _ in GATE_QS]
    assert len(gate_errors(bad_gate)) == 6
    assert set(PRIOR_LEVELS) == set(range(1, 11))
    assert [PRIOR_LEVELS[level][0] for level in range(4, 11)] == [
        "TRANSFER LEARNER", "GENERALIST", "ADJACENT", "PRACTITIONER", "FLUENT",
        "ADVANCED", "EXPERT"]
    upper_tiers = " ".join(PRIOR_LEVELS[level][1] for level in range(4, 11)).lower()
    assert "other-stack" not in upper_tiers and "coder" not in upper_tiers
    assert "transferable concepts explicitly supported" in PRIOR_LEVELS[4][1]
    assert "not subject expertise" in PRIOR_LEVELS[5][1]
    assert "stated neighboring experience" in PRIOR_LEVELS[6][1]
    assert "course-specific API" in PRIOR_LEVELS[7][1]
    assert "uncommon or specialized material" in PRIOR_LEVELS[8][1]
    assert "difficult tradeoffs" in PRIOR_LEVELS[9][1]
    assert "frontier topics only when relevant" in PRIOR_LEVELS[10][1]
    assert "4 = transfer learner" in GATE_QS[1][1]
    compact_plan = os.path.join(BUILD_DIR, "selftest-compact-plan.md")
    write_plan(compact_plan, "selftest", good_gate, "Teach one real artifact")
    compact_text = open(compact_plan, encoding="utf-8").read()
    assert len(compact_text.split()) <= 650, len(compact_text.split())
    assert "## Calibration contract" in compact_text
    assert "Start 2/10 — NEAR ZERO" in compact_text
    assert "same required fundamentals as level 1" in compact_text
    assert "Assumption boundary" in compact_text
    assert "First-use rule for Start 1–3" in compact_text
    assert "keyword, syntax form, operator, API, tool action" in compact_text
    assert "Start 2 shortens repetition" in compact_text
    assert "Calibration contrasts" not in compact_text and "Sample end-state" not in compact_text
    os.remove(compact_plan)

    # Every AI phase uses the exact validator argv the harness will repeat. Phase 1
    # validates its Arc, Phase 2 uses the narrow skeleton gate, shipping phases use
    # strict, and split workers avoid running the growing tome O(n²).
    for phase in range(1, 9):
        prompt = build_prompt("selftest", phase, "Test", "Body", "plan", "verdict", "findings",
                              tooling="internal")
        expected = (phase3_validator_shell_command(
            "selftest", "internal", "plan", strict=phase >= 7)
                    if phase == 3 or phase >= 7 else validator_shell_command(
                        "selftest", phase=phase, tooling="internal", plan_rel="plan"))
        assert f"  {expected}\n" in prompt and "warm-context check" in prompt, phase
    assert validator_argv("selftest", phase=2, tooling="internal") == [
        "python3", "tools/validate_tome.py", "tomes/selftest",
        "--phase-2-skeleton", "--no-run", "--tooling", "internal"]
    assert validator_argv(
        "selftest", phase=3, tooling="external", run_section="s03") == [
            "python3", "tools/validate_tome.py", "tomes/selftest",
            "--tooling", "external", "--run-section", "s03"]
    with patch("buildlib.measure.subprocess.run") as run_validator, \
         patch("buildlib.measure.validation_subprocess_env", return_value=os.environ.copy()):
        run_validator.return_value.returncode = 0
        run_validator.return_value.stdout = "-- selftest: clean"
        run_validator.return_value.stderr = ""
        assert validate("selftest", phase=2, tooling="internal")[0]
        assert run_validator.call_args.args[0] == validator_argv(
            "selftest", phase=2, tooling="internal")
    section_prompt = build_prompt("selftest", 3, "Test", "Body", "plan", "verdict", "findings",
                                  tooling="external", validation_run=False)
    assert "validate_phase3.py tomes/selftest --plan plan --tooling external --no-run" in section_prompt
    section_command = section_validator_shell_command(
        "selftest", "s03", "external", ".tome-build/selftest.plan.md")
    complete_section_prompt = build_prompt(
        "selftest", 3, "Test", "Body", ".tome-build/selftest.plan.md", "verdict",
        "findings", tooling="external", validation_run=False,
        validation_command=section_command)
    assert f"  {section_command}\n" in complete_section_prompt
    assert section_validator_argv(
        "selftest", "s03", "external", ".tome-build/selftest.plan.md") == [
            "python3", "tools/validate_section.py", "tomes/selftest", "s03",
            "--plan", ".tome-build/selftest.plan.md", "--tooling", "external"]
    window_command = section_window_validator_shell_command(
        "selftest", "s06", ".tome-build/selftest.plan.md")
    assert "validate_section_window.py tomes/selftest --through s06" in window_command
    assert section_window_validator_argv(
        "selftest", "s06", ".tome-build/selftest.plan.md") == [
            "python3", "tools/validate_section_window.py", "tomes/selftest",
            "--through", "s06", "--plan", ".tome-build/selftest.plan.md"]
    with patch("buildlib.measure.subprocess.run") as run_section_validator, \
         patch("buildlib.measure.validation_subprocess_env", return_value=os.environ.copy()):
        run_section_validator.return_value.returncode = 0
        run_section_validator.return_value.stdout = "-- section s03 handoff: clean"
        run_section_validator.return_value.stderr = ""
        assert validate_section(
            "selftest", "s03", "external", ".tome-build/selftest.plan.md")[0]
        assert run_section_validator.call_args.args[0] == section_validator_argv(
            "selftest", "s03", "external", ".tome-build/selftest.plan.md")
        run_section_validator.reset_mock()
        assert validate_section_window(
            "selftest", "s06", ".tome-build/selftest.plan.md")[0]
        assert run_section_validator.call_args.args[0] == section_window_validator_argv(
            "selftest", "s06", ".tome-build/selftest.plan.md")
    with patch("buildlib.measure.subprocess.run") as run_complete, \
         patch("buildlib.measure.validation_subprocess_env", return_value=os.environ.copy()):
        run_complete.return_value.returncode = 1
        run_complete.return_value.stdout = "ERROR quality-window: copied template"
        run_complete.return_value.stderr = ""
        clean, phase3_report = validate_phase3(
            "selftest", "external", ".tome-build/selftest.plan.md", ["s01", "s02"])
        assert not clean and "copied template" in phase3_report
        assert run_complete.call_args.args[0] == phase3_validator_argv(
            "selftest", "external", ".tome-build/selftest.plan.md")
        run_complete.return_value.returncode = 0
        assert validate_shipping(
            "selftest", "external", ".tome-build/selftest.plan.md")[0]
        assert run_complete.call_args.args[0] == phase3_validator_argv(
            "selftest", "external", ".tome-build/selftest.plan.md", strict=True)
    review_prompt = build_prompt("selftest", 8, "Test", "Body", "plan", "verdict", "findings")
    focused = build_prompt("selftest", 8, "Test", "Body", "plan", "verdict", "findings",
                           focus="- [blocking] lesson.toml: missing proof")
    assert "then every section" in review_prompt
    assert "focused retry need not reread unrelated chapters" in focused
    assert "missing proof" in focused and "then every section" not in focused
    repair_prompt = build_prompt("selftest", 3, "Test", "Body", "plan", "verdict", "findings",
                                 repair_only=True)
    assert "REPAIR-ONLY RETRY" in repair_prompt and "Do not restart the phase" in repair_prompt
    sample_report = ("WARN content: leave this for later\nERROR tome.toml: real blocker\n"
                     "WARN advisory: host limitation\n-- selftest: 1 error(s), 2 warning(s)")
    assert "leave this" not in blocking_report(sample_report)
    assert "real blocker" in blocking_report(sample_report)
    assert "leave this" in blocking_report(sample_report, strict=True)
    assert "host limitation" not in blocking_report(sample_report, strict=True)
    combined_report = ("WARN content: unrelated future scaffold\n"
                       "-- selftest: 0 error(s), 1 warning(s)\n"
                       "ERROR handoff: artifact_state is over 1200 characters\n"
                       "-- section s03 handoff: error(s)")
    combined_blockers = blocking_report(combined_report)
    assert "artifact_state" in combined_blockers
    assert "unrelated future scaffold" not in combined_blockers
    assert "-- selftest:" in combined_blockers and "-- section s03" in combined_blockers
    assert "this invocation made no" in review_prompt
    assert "starting-level number could not be read" in review_prompt
    stale_plan = os.path.join(BUILD_DIR, "selftest-stale-calibration-plan.md")
    with open(stale_plan, "w", encoding="utf-8") as handle:
        handle.write("## Gate answers (Phase 0)\n"
                     "- **Prior knowledge:** routine basics\n"
                     "- **Starting level (1-10):** 7\n\n"
                     "## Calibration contract\n"
                     "- **Start 7/10 — OLD:** Skip every fundamental and API.\n")
    try:
        stale_rel = os.path.relpath(stale_plan, REPO)
        assert read_prior_level(stale_plan) == 7
        refreshed = current_start_calibration(stale_rel)
        assert "7/10 — PRACTITIONER" in refreshed
        assert "course-specific API" in refreshed, refreshed
        assert "older paraphrase" in refreshed
        stale_review = build_prompt(
            "selftest", 8, "Test", "Body", stale_rel, "verdict", "findings")
        assert refreshed in stale_review
    finally:
        os.remove(stale_plan)
    change_focus = repair_verification_focus([
        "MODIFIED: tomes/selftest/sections/s01/lessons/l01.toml"])
    assert "Fresh verification" in change_focus and "l01.toml" in change_focus
    assert review_pass_eligible("PASS", [])
    assert not review_pass_eligible("PASS", ["MODIFIED: tome.toml"])
    assert not review_pass_eligible("PASS", [], worker_rc=1)
    assert not review_pass_eligible("GAPS REMAIN", [])
    assert "three duties" not in review_prompt.lower()
    assert len(PREAMBLE.split()) <= 200 and len(STUDENT_HOOK.split()) <= 180
    assert len(REPAIR_ONLY.split()) <= 80
    phase_bodies = {num: body for num, _, body in parse_phases()}
    assert "prior-knowledge answer as an exhaustive whitelist" in phase_bodies[1]
    assert "Start 2 changes pace and repetition" in phase_bodies[1]
    assert "complete assumption boundary" in support_prompt("section-author")
    assert "Start 2 permits less repetition" in phase_bodies[8]
    assert max(len(body.split()) for body in phase_bodies.values()) <= 450
    assert len(phase_bodies[3].split()) <= 250, len(phase_bodies[3].split())
    assert len(phase_bodies[8].split()) <= 700, len(phase_bodies[8].split())
    assert len(support_prompt("section-author").split()) <= 650
    assert len(support_prompt("phase-3-reconcile").split()) <= 300
    assert "Artifact lifecycle" in ARC_PARTS and "Acceptance proof" in ARC_PARTS

    # Phase 2 establishes a reusable runtime and Phase 8 may reconcile it with the
    # completed tome. Other phases cannot write shared runtime definitions.
    tome_scope = os.path.join(BUILD_DIR, "phase-write-scope-selftest")
    sidecar = os.path.join(BUILD_DIR, "phase-write-scope-selftest.plan")
    handoff_sidecar = os.path.join(BUILD_DIR, "phase-write-scope-selftest.handoffs")
    runtime_write_probe = os.path.join(RUNTIME_CONFIG_DIR, ".phase8-write-selftest")
    os.makedirs(tome_scope, exist_ok=True)
    os.makedirs(handoff_sidecar, exist_ok=True)
    open(sidecar, "a", encoding="utf-8").close()
    try:
        plan_sidecar = sidecar + ".plan"
        verdict_sidecar = sidecar + ".verdict"
        findings_sidecar = sidecar + ".findings"
        shrink_sidecar = sidecar + ".shrink"
        for path in (plan_sidecar, verdict_sidecar, findings_sidecar, shrink_sidecar):
            open(path, "a", encoding="utf-8").close()
        assert phase_sidecars(1, plan_sidecar, verdict_sidecar, findings_sidecar,
                              shrink_sidecar) == [plan_sidecar]
        assert phase_sidecars(3, plan_sidecar, verdict_sidecar, findings_sidecar,
                              shrink_sidecar) == [shrink_sidecar]
        assert phase_sidecars(7, plan_sidecar, verdict_sidecar, findings_sidecar,
                              shrink_sidecar, tid="phase-write-scope-selftest") == [
                                  shrink_sidecar, handoff_sidecar]
        assert phase_sidecars(8, plan_sidecar, verdict_sidecar, findings_sidecar,
                              shrink_sidecar, tid="phase-write-scope-selftest") == [
                                  shrink_sidecar, verdict_sidecar, findings_sidecar,
                                  handoff_sidecar]
        phase_four_paths = phase_writable_paths(4, tome_scope, (shrink_sidecar,))
        assert tome_scope not in phase_four_paths
        assert os.path.join(tome_scope, "intrusions.toml") in phase_four_paths
        assert os.path.join(tome_scope, "attacks_src.toml") in phase_four_paths
        phase_two_paths = phase_writable_paths(2, tome_scope, (shrink_sidecar,))
        assert RUNTIME_CONFIG_DIR in phase_two_paths
        phase_eight_paths = phase_writable_paths(
            8, tome_scope, (shrink_sidecar, verdict_sidecar, findings_sidecar))
        assert RUNTIME_CONFIG_DIR in phase_eight_paths
        phase_seven_paths = phase_writable_paths(
            7, tome_scope, (shrink_sidecar, handoff_sidecar))
        assert RUNTIME_CONFIG_DIR not in phase_seven_paths
        phase_one_paths = phase_writable_paths(1, tome_scope, (plan_sidecar,))
        assert RUNTIME_CONFIG_DIR not in phase_one_paths and tome_scope not in phase_one_paths
        wrapped = scoped_runner_command(same[0], same[1], tome_scope, phase_two_paths, REPO)
        assert ["--bind", RUNTIME_CONFIG_DIR, RUNTIME_CONFIG_DIR] == wrapped[
            wrapped.index(RUNTIME_CONFIG_DIR) - 1:wrapped.index(RUNTIME_CONFIG_DIR) + 2]
        assert "global-configs/runtimes/" in access_boundary("selftest", 2)
        assert "global-configs/runtimes/" in access_boundary("selftest", 8)
        assert "global-configs/runtimes/" not in access_boundary("selftest", 3)
        assert "assigned Phase-3 section directories" in access_boundary("selftest", 3)
        assert "scaffolded tome is read-only" in access_boundary("selftest", 1)
        assert "tomes/selftest/intrusions.toml" in access_boundary("selftest", 4)
        assert "rest of the tome is read-only" in access_boundary("selftest", 4)

        # Exercise the actual mount namespace, not just its argv: Phase 8 can write the
        # runtime directory and Phase 7 sees the same repository path read-only.
        phase_eight_wrapped = scoped_runner_command(
            same[0], same[1], tome_scope, phase_eight_paths, REPO)
        cut = phase_eight_wrapped.index("--chdir") + 2
        probe_cmd = ["/bin/sh", "-c", 'printf mounted > "$1"', "phase8-probe",
                     runtime_write_probe]
        wrote = subprocess.run(phase_eight_wrapped[:cut] + probe_cmd,
                               capture_output=True, text=True)
        assert wrote.returncode == 0 and os.path.isfile(runtime_write_probe), (
            wrote.returncode, wrote.stdout, wrote.stderr)
        os.remove(runtime_write_probe)
        phase_seven_wrapped = scoped_runner_command(
            same[0], same[1], tome_scope, phase_seven_paths, REPO)
        cut = phase_seven_wrapped.index("--chdir") + 2
        blocked = subprocess.run(phase_seven_wrapped[:cut] + probe_cmd,
                                 capture_output=True, text=True)
        assert blocked.returncode != 0 and not os.path.exists(runtime_write_probe), (
            blocked.returncode, blocked.stdout, blocked.stderr)
        handoff_probe = os.path.join(handoff_sidecar, "phase7-write.json")
        handoff_cmd = ["/bin/sh", "-c", 'printf mounted > "$1"', "handoff-probe",
                       handoff_probe]
        wrote_handoff = subprocess.run(phase_seven_wrapped[:cut] + handoff_cmd,
                                       capture_output=True, text=True)
        assert wrote_handoff.returncode == 0 and os.path.isfile(handoff_probe), (
            wrote_handoff.returncode, wrote_handoff.stdout, wrote_handoff.stderr)
    finally:
        shutil.rmtree(tome_scope, ignore_errors=True)
        shutil.rmtree(handoff_sidecar, ignore_errors=True)
        for path in (sidecar, plan_sidecar, verdict_sidecar, findings_sidecar,
                     shrink_sidecar):
            try:
                os.remove(path)
            except OSError:
                pass
        try:
            os.remove(runtime_write_probe)
        except OSError:
            pass

    runtime_probe = os.path.join(BUILD_DIR, "runtime-scope-selftest")
    runtime_tome = os.path.join(REPO, "tomes", "selftest-runtime-scope")
    shutil.rmtree(runtime_probe, ignore_errors=True)
    shutil.rmtree(runtime_tome, ignore_errors=True)
    os.makedirs(runtime_probe)
    os.makedirs(runtime_tome)
    try:
        with open(os.path.join(runtime_probe, "chosen.toml"), "w", encoding="utf-8") as f:
            f.write("command = ['old']\n")
        with open(os.path.join(runtime_probe, "other.toml"), "w", encoding="utf-8") as f:
            f.write("command = ['keep']\n")
        before_runtime = runtime_config_inventory(runtime_probe)
        with open(os.path.join(runtime_probe, "chosen.toml"), "w", encoding="utf-8") as f:
            f.write("command = ['new']\n")
        assert not runtime_config_scope_violations(
            before_runtime, "chosen.toml", runtime_probe)
        with open(os.path.join(runtime_probe, "scratch.txt"), "w", encoding="utf-8") as f:
            f.write("stray")
        violations = runtime_config_scope_violations(
            before_runtime, "chosen.toml", runtime_probe)
        assert violations and "scratch.txt" in violations[0]
        with open(os.path.join(runtime_tome, "tome.toml"), "w", encoding="utf-8") as f:
            f.write('[runtime]\nname = "chosen"\n')
        assert selected_runtime_config("selftest-runtime-scope") == "chosen.toml"
        save_dir = os.path.join(runtime_tome, "save")
        os.makedirs(save_dir)
        with open(os.path.join(save_dir, "state.json"), "w", encoding="utf-8") as f:
            f.write("before")
        before_review = review_inventory("selftest-runtime-scope", runtime_probe)
        with open(os.path.join(runtime_tome, "tome.toml"), "a", encoding="utf-8") as f:
            f.write('project = "Changed"\n')
        with open(os.path.join(runtime_probe, "chosen.toml"), "a", encoding="utf-8") as f:
            f.write("# repaired\n")
        with open(os.path.join(save_dir, "state.json"), "w", encoding="utf-8") as f:
            f.write("after")
        changed = review_changes(
            before_review, review_inventory("selftest-runtime-scope", runtime_probe))
        assert changed == [
            "MODIFIED: global-configs/runtimes/chosen.toml",
            "MODIFIED: tomes/selftest-runtime-scope/tome.toml",
        ], changed
    finally:
        shutil.rmtree(runtime_probe, ignore_errors=True)
        shutil.rmtree(runtime_tome, ignore_errors=True)
