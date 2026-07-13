"""Focused regression checks for the build harness wiring."""
import json
import os
import shutil
import subprocess
import sys
from unittest.mock import patch

from . import BUILD_DIR, REPO
from . import review as review_module
from .agent_runtime import scoped_runner_command
from .checkpoints import (ARC_CONTRACT, ARC_HEADING, ARC_PARTS, DAILY_DRIVERS,
                          arc_written, finalize_arc, reset_arc)
from .continuity import (continuity_prompt, handoff_dir, prepare_handoff,
                         reconciliation_prompt, validate_all_handoffs,
                         validate_handoff)
from .liveness import _cpu_ticks, _descendants, _has_live_conn
from .measure import (blocking_report, review_changes, review_inventory,
                      runtime_config_inventory, runtime_config_scope_violations,
                      selected_runtime_config, validate, validator_argv,
                      validator_shell_command)
from .prompts import (GATE_QS, PREAMBLE, REPAIR_ONLY, STUDENT_HOOK, build_prompt, gate_errors,
                      read_findings, read_verdict, repair_verification_focus,
                      review_findings_clear, review_pass_eligible, write_plan)
from .runners import _implicit_fallback, _spec_to_runner, default_runner, parse_fallbacks
from .section_security_selftest import run as section_security_selftest
from .sections import (_load_sections_done, _mark_section_done, _sections_done_path,
                       section_ids, wipe_sections)
from .skeleton import parse_section_list, scaffold_sections
from .workflow import (RUNTIME_CONFIG_DIR, access_boundary, parse_phases,
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

    # Fresh section workers communicate through exact, schema-checked handoffs. A
    # distant obligation remains visible and must be closed by its named target.
    ctid = "selftest-continuity-xyz"
    cids = ["s01", "s02", "s03"]
    croot = os.path.join(REPO, "tomes", ctid)
    cplan = os.path.join(BUILD_DIR, f"{ctid}.plan.md")
    try:
        with open(cplan, "w", encoding="utf-8") as f:
            f.write("**Continuity map:**\n- s01 -> s03: Reuse the health route in the final "
                    "encounter.\n**Artifact lifecycle:** tested\n")
        for sid in cids:
            section = os.path.join(croot, "sections", sid)
            os.makedirs(section, exist_ok=True)
            with open(os.path.join(section, "lesson.toml"), "w", encoding="utf-8") as f:
                f.write("# evidence\n")

        def write_handoff(sid, future=(), temporary=(), fulfills=()):
            path = prepare_handoff(ctid, sid, reset=True)
            payload = {
                "version": 1,
                "section": sid,
                "artifact_state": f"The cumulative artifact after {sid} has a stable tested route.",
                "public_contracts": [{"name": f"{sid}.contract", "location": "lesson.toml",
                                      "promise": "Later sections preserve this exact behavior."}],
                "future_obligations": list(future),
                "temporary_artifacts": list(temporary),
                "fulfills": list(fulfills),
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f)

        write_handoff("s01")
        assert not validate_handoff(ctid, "s01", cids, cplan)[0]
        write_handoff("s01", future=[{
            "id": "s01-plan-s03-01", "target": "s03", "location": "lesson.toml",
            "requirement": "Reuse the health route in the final encounter.",
            "reason": "The learner already owns this state transition.",
        }], temporary=[{
            "id": "s01-debug-caption", "target": "s02", "location": "lesson.toml",
            "artifact": "Temporary caption used as visible diagnostics.",
            "retirement": "Replace the caption with the taught HUD.",
        }])
        assert validate_handoff(ctid, "s01", cids, cplan)[0]
        write_handoff("s02", fulfills=[{
            "id": "s01-debug-caption", "location": "lesson.toml",
            "evidence": "The HUD replacement and caption removal are both explicit.",
        }])
        assert validate_handoff(ctid, "s02", cids, cplan)[0]
        write_handoff("s03")
        assert not validate_handoff(ctid, "s03", cids, cplan)[0]
        briefing = continuity_prompt(ctid, "s03", cids, cplan)
        assert "s01-plan-s03-01" in briefing and "DUE NOW" in briefing
        write_handoff("s03", fulfills=[{
            "id": "s01-plan-s03-01", "location": "lesson.toml",
            "evidence": "The final encounter calls the stable health transition.",
        }])
        assert validate_all_handoffs(ctid, cids, cplan)[0]
        assert "Deterministic handoff gate: CLOSED" in reconciliation_prompt(
            ctid, cids, cplan)
    finally:
        shutil.rmtree(croot, ignore_errors=True)
        shutil.rmtree(handoff_dir(ctid), ignore_errors=True)
        try:
            os.remove(cplan)
        except OSError:
            pass

    plan = os.path.join(BUILD_DIR, f"{tid}.plan.md")
    header = "## Gate answers\n- stuff\n\n" + ARC_HEADING + ARC_CONTRACT
    drivers = "; ".join(f"{driver} = CAN" for driver in DAILY_DRIVERS)
    values = {
        "Daily drivers": drivers,
        "Continuity map": "s01 -> s02: preserve the exact forge contract",
        "Section list": ("\n1. **s01 — First Forge:** establish the project shell\n"
                         "2. **s02 — Second Forge:** deliver the finished artifact"),
    }
    full = "".join(f"**{part}:** {values.get(part, 'hammered out in ample forge-detail')}\n"
                   for part in ARC_PARTS)
    parsed = parse_section_list(full)
    assert [spec.sid for spec in parsed] == ["s01", "s02"]
    cases = (("", False), ("\n\n", False), (full, True),
             (full.replace("**Graduate ledger:**", "ledger"), False),
             (full.replace("key-value = CAN", "key-value"), False),
             (full.replace("s01 -> s02:", "s02 -> s01:"), False),
             (full.replace("s01 -> s02: preserve", "s01 -> s02:\npreserve"), False),
             (full.replace("2. **s02 —", "3. **s03 —"), False),
             ("".join(f"**{part}:** x\n" for part in ARC_PARTS), False))
    for extra, expected in cases:
        with open(plan, "w", encoding="utf-8") as f:
            f.write(header + extra)
        assert arc_written(plan, plan)[0] is expected
    with open(plan, "w", encoding="utf-8") as f:
        f.write(header + full)
    assert finalize_arc(plan) and ARC_CONTRACT not in open(plan, encoding="utf-8").read()
    assert arc_written(plan, plan)[0]
    cli = subprocess.run([sys.executable, os.path.join(REPO, "tools", "validate_tome.py"),
                          "tomes/not-authored-yet", "--phase-1-plan", plan],
                         cwd=REPO, capture_output=True, text=True)
    assert cli.returncode == 0, (cli.stdout, cli.stderr)

    # The approved Section list becomes a deterministic, validator-green Phase-2 tree:
    # one placeholder lesson per section. Adding a second lesson crosses the phase
    # boundary and must fail the narrow gate even though it is legal finished content.
    skeleton_tid = "selftest-phase2-skeleton-xyz"
    skeleton_root = os.path.join(REPO, "tomes", skeleton_tid)
    skeleton_plan = os.path.join(BUILD_DIR, f"{skeleton_tid}.plan.md")
    shutil.rmtree(skeleton_root, ignore_errors=True)
    try:
        made = subprocess.run(
            [sys.executable, os.path.join(REPO, "tools", "new_tome.py"), skeleton_tid],
            cwd=REPO, capture_output=True, text=True)
        assert made.returncode == 0, (made.stdout, made.stderr)
        with open(skeleton_plan, "w", encoding="utf-8") as handle:
            handle.write("## Arc\n" + full)
        specs = scaffold_sections(skeleton_tid, skeleton_plan)
        assert [spec.sid for spec in specs] == ["s01", "s02"]
        assert section_ids(skeleton_tid) == ["s01", "s02"]
        for spec in specs:
            lesson_dir = os.path.join(skeleton_root, "sections", spec.sid, "lessons")
            assert os.listdir(lesson_dir) == ["l01.toml"]
        skeleton_check = subprocess.run(
            validator_argv(skeleton_tid, phase=2, tooling="internal"),
            cwd=REPO, capture_output=True, text=True)
        assert skeleton_check.returncode == 0, (skeleton_check.stdout, skeleton_check.stderr)
        assert "density" not in skeleton_check.stdout and "TODO/FIXME" not in skeleton_check.stdout
        first_lessons = os.path.join(skeleton_root, "sections", "s01", "lessons")
        shutil.copyfile(os.path.join(first_lessons, "l01.toml"),
                        os.path.join(first_lessons, "l02.toml"))
        overbuilt = subprocess.run(
            validator_argv(skeleton_tid, phase=2, tooling="internal"),
            cwd=REPO, capture_output=True, text=True)
        assert overbuilt.returncode != 0 and "expected exactly 1 placeholder lesson" in overbuilt.stdout
    finally:
        shutil.rmtree(skeleton_root, ignore_errors=True)
        try:
            os.remove(skeleton_plan)
        except OSError:
            pass

    reset_arc(plan)
    assert arc_written(plan, plan)[0] is False
    os.remove(plan)
    assert arc_written("/no/such/plan.md", "x")[0] is False

    verdict = os.path.join(BUILD_DIR, f"{tid}.verdict")
    for raw, expected in (("PASS\n", "PASS"), ("GAPS REMAIN\n", "GAPS REMAIN"),
                          ("NOT PASS\n", None), ("PASS - looks good\n", None)):
        with open(verdict, "w", encoding="utf-8") as f:
            f.write(raw)
        assert read_verdict(verdict) == expected
        assert os.path.exists(verdict) and os.path.getsize(verdict) == 0
    findings_path = os.path.join(BUILD_DIR, f"{tid}.findings.json")
    with open(findings_path, "w", encoding="utf-8") as f:
        json.dump([{"file": f"f{i}", "issue": "line one\nline two", "severity": "blocking"}
                   for i in range(50)], f)
    assert not review_findings_clear(findings_path)
    findings = read_findings(findings_path)
    assert len(findings.splitlines()) == 40 and "line one line two" in findings
    assert os.path.exists(findings_path) and os.path.getsize(findings_path) == 0
    assert review_findings_clear(findings_path)
    with open(findings_path, "w", encoding="utf-8") as f:
        f.write("[]\n")
    assert review_findings_clear(findings_path)
    with open(findings_path, "w", encoding="utf-8") as f:
        f.write("not json\n")
    assert not review_findings_clear(findings_path)

    # Exercise the loop seam itself: a clean PASS returns without another worker, while
    # the identical PASS attached to an authored repair schedules one fresh invocation.
    def clean_review_worker(*_args, **_kwargs):
        with open(verdict, "w", encoding="utf-8") as f:
            f.write("PASS\n")
        with open(findings_path, "w", encoding="utf-8") as f:
            f.write("[]\n")
        return 0

    def invoke_review(latest_edits):
        with open(verdict, "w", encoding="utf-8") as f:
            f.write("PASS\n")
        with open(findings_path, "w", encoding="utf-8") as f:
            f.write("[]\n")
        return review_module.run_student_review(
            "no-such-review-tome", "Test", "Body", ("fake", ["fake"], "stdin"),
            ("plan", "verdict", "findings"),
            (os.path.join(BUILD_DIR, "missing.plan"), verdict, findings_path,
             os.path.join(BUILD_DIR, "missing.shrink")),
            {"files": set(), "arrays": {}}, runtime_config_inventory(), 0,
            latest_edits, 0, "", "", 1, 1, 1, [])

    with (patch.object(review_module, "scoped_runner_command", return_value=["fake"]),
          patch.object(review_module, "validate", return_value=(True, "")),
          patch.object(review_module, "run_agent", side_effect=clean_review_worker) as agent):
        assert invoke_review([]) is None and agent.call_count == 0
        assert invoke_review(["MODIFIED: tomes/x/tome.toml"]) is None
        assert agent.call_count == 1
    os.remove(verdict)
    os.remove(findings_path)
    print("build_tome self-test: OK")
