"""Phase 8's fresh-review loop and its independent repair-verification gate."""
import os
import time

from . import MAX_STUDENT_LOOPS, REPO
from .agent_runtime import scoped_runner_command
from .liveness import preflight_recovery_runner, run_agent
from .measure import (blocking_report, inventory, review_changes, review_inventory,
                      runtime_config_scope_violations, selected_runtime_config,
                      shrink_marks, shrinkage, validate_shipping)
from .prompts import (build_prompt, read_findings, read_tooling, read_verdict,
                      repair_verification_focus, review_findings_clear,
                      review_pass_eligible)
from .workflow import phase_sidecars, prepare_phase_writable_paths
from .validation_env import (ValidationEnvironmentError, ensure_validation_environment,
                             headless_validation_env, validation_subprocess_env)


def run_student_review(tid, title, body, runner, prompt_refs, sidecar_paths,
                       phase_start_inventory, runtime_start_inventory, shrink_mark_count,
                       latest_edits, initial_rc, continuity_context, access,
                       ping_interval, dead_pings, hard_cap, timings,
                       runner_chain=None):
    """Run focused repair passes until independent no-change evidence derives PASS.

    The first Phase 8 invocation has already run in the main phase loop.  Its verdict,
    return code, and content diff enter here so it cannot certify a repair it just made.
    Returns ``None`` on a clean PASS or a concise unresolved finding at the loop cap.
    """
    chain = list(runner_chain or [runner])
    ri = next((index for index, item in enumerate(chain) if item[1] == runner[1]), 0)
    name, cmd, input_mode = chain[ri]
    preflighted = {tuple(cmd)}
    plan_rel, verdict_rel, findings_rel = prompt_refs
    plan_path, verdict_path, findings_path, shrink_path = sidecar_paths
    tooling = read_tooling(plan_path)
    loop = 1
    verdict = read_verdict(verdict_path, tid, findings_path)
    validation_focus = repair_verification_focus(latest_edits) if latest_edits else None
    if latest_edits:
        print("  ~ Phase 8 changed authored content -> a fresh verification pass is required")
    if verdict == "PASS" and not review_findings_clear(findings_path, tid):
        conflict = ("- [blocking] PASS contradicted a non-empty or malformed findings "
                    "sidecar; resolve those findings, then use [] with PASS")
        validation_focus = ((validation_focus + "\n") if validation_focus else "") + conflict
    if verdict == "PASS" and not review_pass_eligible(
            verdict, latest_edits, not validation_focus, initial_rc):
        verdict = None

    loop_budget = MAX_STUDENT_LOOPS
    while verdict != "PASS":
        if loop >= loop_budget:
            unresolved = (validation_focus or read_findings(findings_path)
                          or "reviewer did not return complete clean review evidence")
            if ri + 1 < len(chain):
                ri += 1
                name, cmd, input_mode = chain[ri]
                loop_budget = loop + MAX_STUDENT_LOOPS
                validation_focus = unresolved
                print(f"  ⇒ review budget spent — escalating Phase 8 to {name}")
                continue
            return unresolved
        loop += 1
        focus = read_findings(findings_path)
        if validation_focus:
            focus = ((focus + "\n") if focus else "") + validation_focus
        where = "flagged files only" if focus else "full re-read (no findings file)"
        print(f"  ~ student verdict not PASS -> review/fill loop {loop} ({where})")
        started = time.monotonic()
        tome_scope = os.path.join(REPO, "tomes", tid)
        sidecars = phase_sidecars(
            8, plan_path, verdict_path, findings_path, shrink_path, tid=tid)
        writable = prepare_phase_writable_paths(8, tome_scope, sidecars)
        scoped = scoped_runner_command(name, cmd, tome_scope, writable, REPO)
        before = review_inventory(tid)
        try:
            ensure_validation_environment(tid)
            env = validation_subprocess_env(tid)
        except ValidationEnvironmentError:
            # The previous review may have broken the declaration. Preserve a path
            # for the next reviewer to repair it instead of crashing the harness.
            env = headless_validation_env()
        env.update(ARCANUM_REPO_ROOT=REPO, ARCANUM_TOME_ROOT=tome_scope,
                   PYTHONDONTWRITEBYTECODE="1")
        if not preflight_recovery_runner(name, cmd, scoped, input_mode, preflighted):
            rc = 125
        else:
            rc = run_agent(
                scoped, input_mode,
                build_prompt(tid, 8, title, body, plan_rel, verdict_rel, findings_rel, focus,
                             tooling=tooling)
                + continuity_context + access,
                ping_interval, dead_pings, hard_cap, cwd=tome_scope, env=env)
        timings.append((f"8.{loop}", name, round(time.monotonic() - started), 1))
        latest_edits = review_changes(before, review_inventory(tid))
        verdict = read_verdict(verdict_path, tid, findings_path)

        try:
            ensure_validation_environment(tid)
            clean, report = validate_shipping(tid, tooling, plan_rel)
        except ValidationEnvironmentError as exc:
            clean, report = False, f"ERROR validation dependencies: {exc}"
        gate_focus = []
        if verdict == "PASS" and not review_findings_clear(findings_path, tid):
            gate_focus.append("- [blocking] PASS contradicted a non-empty or malformed "
                              "findings sidecar; resolve those findings, then use [] with PASS")
        if not clean:
            print("  x Phase 8 revisions broke strict validation; the next review must fix it")
            gate_focus.append("- [blocking] strict validator failures introduced during "
                              "review:\n" + blocking_report(report, strict=True))
        shrink_problems = shrinkage(phase_start_inventory, inventory(tid))
        if shrink_problems and shrink_marks(shrink_path) > shrink_mark_count:
            shrink_problems = []
        contract_problems = list(shrink_problems)
        contract_problems += runtime_config_scope_violations(
            runtime_start_inventory, selected_runtime_config(tid))
        if contract_problems:
            print("  x Phase 8 revisions violated the write/shrink contract")
            gate_focus.append("- [blocking] restore these phase-contract violations:\n" +
                              "\n".join(contract_problems))
        if latest_edits:
            gate_focus.insert(0, repair_verification_focus(latest_edits))
            if verdict == "PASS":
                print("  ~ same-pass PASS rejected because the reviewer changed authored content")
        validation_focus = "\n".join(gate_focus) or None
        if rc != 0:
            print(f"  ! Phase 8 review worker exited {rc}; no verdict is trusted")
            verdict = None
            if ri + 1 < len(chain):
                ri += 1
                name, cmd, input_mode = chain[ri]
                loop -= 1
                print(f"  ⇒ Phase 8 reviewer died — continuing on {name}")
                continue
            reason = "hung/timeout" if rc == 124 else f"exit {rc}"
            return f"Phase 8 review worker {name} failed ({reason})"
        if verdict == "PASS" and not review_pass_eligible(
                verdict, latest_edits, not validation_focus, rc):
            verdict = None

    if verdict == "PASS":
        return None
    return None
