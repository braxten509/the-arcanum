"""Phase 8's fresh-review loop and its independent repair-verification gate."""
import os
import time

from . import MAX_STUDENT_LOOPS, REPO
from .agent_runtime import scoped_runner_command
from .liveness import run_agent
from .measure import (blocking_report, inventory, review_changes, review_inventory,
                      runtime_config_scope_violations, selected_runtime_config,
                      shrink_marks, shrinkage, validate)
from .prompts import (build_prompt, read_findings, read_tooling, read_verdict,
                      repair_verification_focus, review_findings_clear,
                      review_pass_eligible)
from .runners import request_runner
from .workflow import phase_sidecars, phase_writable_paths


def run_student_review(tid, title, body, runner, prompt_refs, sidecar_paths,
                       phase_start_inventory, runtime_start_inventory, shrink_mark_count,
                       latest_edits, initial_rc, continuity_context, access,
                       ping_interval, dead_pings, hard_cap, timings,
                       build_id=None, ask_on_death=False, interactive=False):
    """Run focused repair passes until an independent no-change reviewer writes PASS.

    The first Phase 8 invocation has already run in the main phase loop.  Its verdict,
    return code, and content diff enter here so it cannot certify a repair it just made.
    Returns ``None`` on a clean PASS or a concise unresolved finding at the loop cap.
    """
    name, cmd, input_mode = runner
    build_id = build_id or tid
    plan_rel, verdict_rel, findings_rel = prompt_refs
    plan_path, verdict_path, findings_path, shrink_path = sidecar_paths
    tooling = read_tooling(plan_path)
    loop = 1
    verdict = read_verdict(verdict_path)
    validation_focus = repair_verification_focus(latest_edits) if latest_edits else None
    if latest_edits:
        print("  ~ Phase 8 changed authored content -> a fresh verification pass is required")
    if verdict == "PASS" and not review_findings_clear(findings_path):
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
                          or "reviewer did not write the exact one-line verdict PASS")
            if not (ask_on_death or interactive):
                return unresolved
            nxt, extra = request_runner(
                build_id, 8, name, f"{loop} review rounds used", interactive,
                report=unresolved)
            if nxt is None and extra <= 0:
                return unresolved
            if nxt is not None:
                name, cmd, input_mode = nxt
                print(f"  ⇒ operator switched Phase 8 review to {name}")
            loop_budget = loop + max(extra, 1)
            print(f"  ↻ operator granted more Phase 8 review rounds — budget now {loop_budget}")
        loop += 1
        focus = read_findings(findings_path)
        if validation_focus:
            focus = ((focus + "\n") if focus else "") + validation_focus
        where = "flagged files only" if focus else "full re-read (no findings file)"
        print(f"  ~ student verdict not PASS -> review/fill loop {loop} ({where})")
        started = time.monotonic()
        tome_scope = os.path.join(REPO, "tomes", tid)
        sidecars = phase_sidecars(
            8, plan_path, verdict_path, findings_path, shrink_path)
        writable = phase_writable_paths(8, tome_scope, sidecars)
        scoped = scoped_runner_command(name, cmd, tome_scope, writable, REPO)
        before = review_inventory(tid)
        env = os.environ.copy()
        env.update(ARCANUM_REPO_ROOT=REPO, ARCANUM_TOME_ROOT=tome_scope,
                   PYTHONDONTWRITEBYTECODE="1")
        rc = run_agent(
            scoped, input_mode,
            build_prompt(tid, 8, title, body, plan_rel, verdict_rel, findings_rel, focus,
                         tooling=tooling)
            + continuity_context + access,
            ping_interval, dead_pings, hard_cap, cwd=tome_scope, env=env)
        timings.append((f"8.{loop}", name, round(time.monotonic() - started), 1))
        latest_edits = review_changes(before, review_inventory(tid))
        verdict = read_verdict(verdict_path)

        clean, report = validate(tid, phase=8, tooling=tooling)
        gate_focus = []
        if verdict == "PASS" and not review_findings_clear(findings_path):
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
            if ask_on_death or interactive:
                reason = "hung/timeout" if rc == 124 else f"exit {rc}"
                nxt, _ = request_runner(build_id, 8, name, reason, interactive)
                if nxt is None:
                    return f"Phase 8 review worker {name} failed ({reason})"
                name, cmd, input_mode = nxt
                loop -= 1  # infrastructure failure does not spend an editorial review round
                print(f"  ⇒ Phase 8 reviewer died — continuing on {name}")
                continue
        if verdict == "PASS" and not review_pass_eligible(
                verdict, latest_edits, not validation_focus, rc):
            verdict = None

    if verdict == "PASS":
        return None
    return None
