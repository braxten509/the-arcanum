"""Regression checks for runner, prompt, access, and runtime harness contracts."""
import os
import shutil
import subprocess
from unittest.mock import patch

from .. import BUILD_DIR, REPO
from ..agent_runtime import scoped_runner_command
from ..checkpoints import ARC_PARTS
from ..liveness import _cpu_ticks, _descendants, _has_live_conn
from ..measure import (blocking_report, review_changes, review_inventory,
                       runtime_config_inventory, runtime_config_scope_violations,
                       selected_runtime_config, validate, validator_argv,
                       validator_shell_command)
from ..prompts import (GATE_QS, PREAMBLE, PRIOR_LEVELS, REPAIR_ONLY, STUDENT_HOOK,
                       build_prompt, current_start_calibration, gate_errors,
                       read_prior_level, repair_verification_focus,
                       review_pass_eligible, write_plan)
from ..runners import _implicit_fallback, _spec_to_runner, default_runner, parse_fallbacks
from ..section_security_selftest import run as section_security_selftest
from ..sections import (_load_sections_done, _mark_section_done, _sections_done_path,
                        section_ids, wipe_sections)
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
        expected = validator_shell_command(
            "selftest", phase=phase, tooling="internal", plan_rel="plan")
        assert f"  {expected}\n" in prompt and "warm-context check" in prompt, phase
    assert validator_argv("selftest", phase=2, tooling="internal") == [
        "python3", "tools/validate_tome.py", "tomes/selftest",
        "--phase-2-skeleton", "--no-run", "--tooling", "internal"]
    with patch("buildlib.measure.subprocess.run") as run_validator:
        run_validator.return_value.returncode = 0
        run_validator.return_value.stdout = "-- selftest: clean"
        run_validator.return_value.stderr = ""
        assert validate("selftest", phase=2, tooling="internal")[0]
        assert run_validator.call_args.args[0] == validator_argv(
            "selftest", phase=2, tooling="internal")
    section_prompt = build_prompt("selftest", 3, "Test", "Body", "plan", "verdict", "findings",
                                  tooling="external", validation_run=False)
    assert "tomes/selftest --no-run --tooling external" in section_prompt
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
    runtime_write_probe = os.path.join(RUNTIME_CONFIG_DIR, ".phase8-write-selftest")
    os.makedirs(tome_scope, exist_ok=True)
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
        assert phase_sidecars(8, plan_sidecar, verdict_sidecar, findings_sidecar,
                              shrink_sidecar) == [shrink_sidecar, verdict_sidecar, findings_sidecar]
        phase_two_paths = phase_writable_paths(2, tome_scope, (shrink_sidecar,))
        assert RUNTIME_CONFIG_DIR in phase_two_paths
        phase_eight_paths = phase_writable_paths(
            8, tome_scope, (shrink_sidecar, verdict_sidecar, findings_sidecar))
        assert RUNTIME_CONFIG_DIR in phase_eight_paths
        phase_seven_paths = phase_writable_paths(7, tome_scope, (shrink_sidecar,))
        assert RUNTIME_CONFIG_DIR not in phase_seven_paths
        phase_one_paths = phase_writable_paths(1, tome_scope, (plan_sidecar,))
        assert RUNTIME_CONFIG_DIR not in phase_one_paths and tome_scope not in phase_one_paths
        wrapped = scoped_runner_command(same[0], same[1], tome_scope, phase_two_paths, REPO)
        assert ["--bind", RUNTIME_CONFIG_DIR, RUNTIME_CONFIG_DIR] == wrapped[
            wrapped.index(RUNTIME_CONFIG_DIR) - 1:wrapped.index(RUNTIME_CONFIG_DIR) + 2]
        assert "global-configs/runtimes/" in access_boundary("selftest", 2)
        assert "global-configs/runtimes/" in access_boundary("selftest", 8)
        assert "global-configs/runtimes/" not in access_boundary("selftest", 3)
        assert "scaffolded tome is read-only" in access_boundary("selftest", 1)

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
    finally:
        shutil.rmtree(tome_scope, ignore_errors=True)
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
