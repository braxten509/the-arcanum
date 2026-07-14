#!/usr/bin/env python3
"""build_tome.py — build a tome ONE PHASE AT A TIME, each in a fresh agent.

Why this exists: a single agent handed the whole workflow skips phases (especially the
final student-review pass) and half-reads buried rules. This harness runs each phase
file in tome-workflow/ as a SEPARATE headless agent, so no phase can be
skipped and each gets clean, focused context. Between content phases it runs
validate_tome.py as a hard gate and re-runs the phase (feeding back the errors) until
it passes. Phase 8 loops through review/repair workers until a fresh no-change reviewer
writes PASS; a worker cannot certify content it changed in the same invocation.

    python3 tools/build_tome.py <tome-id> [--from-phase N]

Which AI drives each phase is set in global-configs/harness.toml.

Cross-phase state is the FILESYSTEM: the tome under tomes/<id>/ that each phase mutates,
plus one plan file at .tome-build/<id>.plan.md carrying the gate answers + arc.
The machinery lives in tools/buildlib/ (see its __init__ for the module map);
this file is the CLI + the phase loop."""
import argparse
import os
import shutil
import subprocess
import sys
import time

from buildlib import (BUILD_DIR, DEAD_PINGS_DEFAULT, MAX_STUDENT_LOOPS,
                      PING_INTERVAL_DEFAULT, REPO, retries_for)
from buildlib.checkpoints import finalize_arc, maybe_rename, reset_arc
from buildlib.config import load_config
from buildlib.continuity import handoffs_exist, reconciliation_prompt, validate_all_handoffs
from buildlib.agent_runtime import scoped_runner_command
from buildlib.liveness import (preflight_recovery_runner, preflight_runners, run_agent)
from buildlib.measure import (forecast_line, inventory, measure, runtime_config_inventory,
                              review_changes, review_inventory,
                              shrink_marks, validate, validate_phase3, validate_shipping,
                              blocking_report)
from buildlib.phase3_runtime import (prepare_warm_phase3_recovery,
                                     prepare_warm_phase3_start, uses_whole_warm_worker)
from buildlib.gates import evaluate_content_gate
from buildlib.prompts import build_prompt, do_gate, do_gate_json, read_tooling
from buildlib.review import run_student_review
from buildlib.reporting import append_ground_truth
from buildlib.runners import (_implicit_fallback, automatic_fallbacks, parse_fallbacks,
                              parse_runner_flags, runner_for, unique_chain)
from buildlib.sections import (author_sections_split, clear_section_progress,
                               section_ids, wipe_sections)
from buildlib.skeleton import scaffold_sections
from buildlib.workflow import (access_boundary, parse_phases, phase_sidecars,
                               prepare_phase_writable_paths, support_prompt)
from buildlib.validation_env import (ValidationEnvironmentError, ensure_validation_environment,
                                     headless_validation_env, validation_subprocess_env)

def main():
    if "--selftest" in sys.argv[1:]:
        from buildlib.build_selftest import run
        run()
        return
    ap = argparse.ArgumentParser(description="Build a tome phase-by-phase via harness.toml runners.")
    ap.add_argument("tome_id")
    ap.add_argument("--from-phase", type=int, default=0, help="resume at this phase number")
    ap.add_argument("--gate-json", default=None, metavar="JSON",
                    help='answer Phase 0 non-interactively with prior_knowledge, prior_level, '
                         'breadth, depth, mastery, and tooling (internal|external|both)')
    ap.add_argument("--concept", default=None,
                    help="free-form course concept, recorded in the plan for Phase 1 to read")
    ap.add_argument("--runner", action="append", metavar="KEY=KIND:MODEL[@EFFORT]",
                    help="override the AI for one phase (KEY=phase number) or all phases "
                         "(KEY=default), e.g. --runner default=claude-cli:claude-opus-4-8@high "
                         "--runner 8=codex-cli:gpt-5.5. @EFFORT sets reasoning effort where "
                         "the CLI takes one (claude/codex). Beats harness.toml.")
    ap.add_argument("--preset", default=None, metavar="NAME",
                    help="flip the whole model/effort matrix to a [presets.<name>] block in "
                         "harness.toml (e.g. budget, quality). Beats the file's `preset`/`default`.")
    ap.add_argument("--yes", action="store_true",
                    help="deprecated compatibility flag; construction is always unattended")
    ap.add_argument("--fallback", action="append", metavar="KIND:MODEL[@EFFORT]",
                    help="runner to switch to when a phase's worker DIES (crash, exhausted "
                         "quota, or hang) — repeat for an ordered chain. Each resumes from the "
                         "tome on disk. Defaults to the 'default' runner when omitted.")
    ap.add_argument("--ping-interval", type=int, default=None, metavar="SEC",
                    help=f"seconds between worker liveness checks (overrides harness.toml "
                         f"[liveness]; default {PING_INTERVAL_DEFAULT}).")
    ap.add_argument("--dead-pings", type=int, default=None, metavar="N",
                    help=f"consecutive idle checks (no CPU, no live connection) before a worker "
                         f"is declared hung and killed (overrides harness.toml [liveness]; "
                         f"default {DEAD_PINGS_DEFAULT}).")
    ap.add_argument("--phase-timeout", type=int, default=0, metavar="SEC",
                    help="optional absolute backstop: kill a worker after SEC seconds even if it "
                         "looks busy (default 0 = off; liveness pings handle the common hang).")
    ap.add_argument("--ask-on-death", action="store_true",
                    help="deprecated compatibility flag; autonomous builds never pause")
    ap.add_argument("--split-sections", action="store_true",
                    help="author Phase 3 in bounded warm section batches instead of one whole-tome "
                         "session — preserves nearby context while keeping every provider below a "
                         "portable batch boundary. Falls back to one worker for <2 sections.")
    ap.add_argument("--section-batch-size", type=int, default=3, metavar="N",
                    help="maximum Arc-ordered sections per warm Phase-3 worker (default 3). The "
                         "harness checkpoints every section and retries only failures.")
    ap.add_argument("--selftest", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    tid = args.tome_id

    cfg = load_config(args.preset)
    overrides = parse_runner_flags(args.runner)
    fallbacks = parse_fallbacks(args.fallback)
    hard_cap = args.phase_timeout or None
    # liveness: CLI flag > harness.toml [liveness] > built-in default
    lv = cfg.get("liveness") or {}
    ping_interval = max(1, args.ping_interval if args.ping_interval is not None
                        else int(lv.get("ping_interval", PING_INTERVAL_DEFAULT)))
    dead_pings = max(1, args.dead_pings if args.dead_pings is not None
                     else int(lv.get("dead_pings", DEAD_PINGS_DEFAULT)))
    split_sections = True  # future tomes always use bounded warm section batches
    section_batch_size = max(1, args.section_batch_size)
    phases = parse_phases()
    os.makedirs(BUILD_DIR, exist_ok=True)
    plan_path = os.path.join(BUILD_DIR, f"{tid}.plan.md")
    verdict_path = os.path.join(BUILD_DIR, f"{tid}.verdict")
    findings_path = os.path.join(BUILD_DIR, f"{tid}.findings.json")
    shrink_path = os.path.join(BUILD_DIR, f"{tid}.shrink-ok")
    # Candidate sidecars are pre-created so bubblewrap can expose the phase-specific
    # subset as exact files without making the containing directory writable.
    for sidecar in (plan_path, verdict_path, findings_path, shrink_path):
        if not os.path.exists(sidecar):
            open(sidecar, "a", encoding="utf-8").close()
    plan_rel = os.path.relpath(plan_path, REPO)
    verdict_rel = os.path.relpath(verdict_path, REPO)
    findings_rel = os.path.relpath(findings_path, REPO)
    tome_dir = os.path.join(REPO, "tomes", tid)
    proof_build = args.from_phase <= 2
    if not proof_build:
        try:
            manifest_text = open(os.path.join(tome_dir, "tome.toml"), encoding="utf-8").read()
        except OSError:
            manifest_text = ""
        try:
            plan_text = open(plan_path, encoding="utf-8").read()
        except OSError:
            plan_text = ""
        proof_build = ("proofVersion = 1" in manifest_text
                       or "**Proof contract:** 1" in plan_text)
    if proof_build:
        os.environ["ARCANUM_REQUIRE_PROOF_V1"] = "1"
    else:
        os.environ.pop("ARCANUM_REQUIRE_PROOF_V1", None)
    timings = []              # (phase, runner, seconds, attempts) for the end-of-run log
    review_unresolved = None  # set if Phase 8 exhausts its loops without PASS

    if os.path.isdir(tome_dir):
        if args.from_phase <= 2:
            # Restarting at/below Phase 2 re-derives the whole skeleton — everything in the
            # tome is the OLD run's output, and building on a dead-end file is how a bad arc
            # survives a restart. Reset to a fresh scaffold, exactly the state Phase 2 expects.
            shutil.rmtree(tome_dir)
            wipe_sections(tid)  # dirs went with the tree; this clears the split-resume manifest
            if args.from_phase > 0:  # Phase 0 scaffolds itself; a start at 1/2 needs it now
                rc = subprocess.call([sys.executable, os.path.join(REPO, "tools", "new_tome.py"), tid])
                if rc != 0 or not os.path.isdir(tome_dir):
                    sys.exit(f"could not re-scaffold tomes/{tid}/ (new_tome.py exit {rc})")
            print(f"  · reset tomes/{tid}/ to a fresh scaffold (restart at phase {args.from_phase})")
        else:
            print(f"  · forecast: {forecast_line(measure(tid))}")  # resume: current size (#23)
    if args.from_phase == 1:  # Phase 1 re-run: a stale arc from the old run must not pass the gate
        reset_arc(plan_path)

    preflight_done = False
    preflighted = set()  # raw runner commands whose provider/model has answered Phase 0

    for num, title, body in phases:
        if num < args.from_phase:
            continue

        if num == 0:
            if args.gate_json is not None:
                do_gate_json(plan_path, tid, args.gate_json, args.concept)
            else:
                do_gate(plan_path, tid, args.concept)
            # The harness owns the folder: scaffold tomes/<tid>/ NOW so Phase 1+ (and the
            # author-AI) write into an existing tome. Phase 2 fills it, then maybe_rename
            # (below) renames it from [runtime] project. Skip if present (resume/retry).
            if not os.path.isdir(os.path.join(REPO, "tomes", tid)):
                rc = subprocess.call([sys.executable, os.path.join(REPO, "tools", "new_tome.py"), tid])
                if rc != 0 or not os.path.isdir(os.path.join(REPO, "tomes", tid)):
                    sys.exit(f"Phase 0: could not scaffold tomes/{tid}/ (new_tome.py exit {rc})")
            continue

        if not os.path.exists(plan_path):
            sys.exit(f"no plan file at {plan_path} — run Phase 0 first (drop --from-phase, or >0 needs an existing plan).")

        if num == 2:
            try:
                specs = scaffold_sections(tid, plan_path)
            except ValueError as exc:
                sys.exit(f"Phase 2 deterministic scaffold failed before starting a worker: {exc}")
            print(f"  · Phase 2 scaffolded from the approved Arc: {len(specs)} sections, "
                  "one placeholder lesson each")

        # Phase 0 for AI access: prove every selected provider/model answers through the
        # same read/web/bubblewrap mechanism used by real phases. Local self-tests prove
        # the narrower per-phase write mounts independently.
        if not preflight_done:
            distinct, seen = [], set()
            current_tome = os.path.join(REPO, "tomes", tid)
            writable = [current_tome, plan_path, verdict_path, findings_path, shrink_path]
            for pnum, _, _ in phases:
                if pnum == 0 or pnum < args.from_phase:
                    continue
                nm, pcmd, pim = runner_for(cfg, pnum, overrides)
                if tuple(pcmd) not in seen:
                    seen.add(tuple(pcmd))
                    distinct.append((nm, scoped_runner_command(
                        nm, pcmd, current_tome, writable, REPO), pim))
            # Explicit fallbacks are just as important as primary phase runners: prove them
            # now, rather than discovering an expired login only after the primary dies.
            for nm, pcmd, pim in fallbacks:
                if tuple(pcmd) not in seen:
                    seen.add(tuple(pcmd))
                    distinct.append((nm, scoped_runner_command(
                        nm, pcmd, current_tome, writable, REPO), pim))
            if distinct:
                # A bad selected endpoint is recoverable: record the whole set only when
                # clean; otherwise each phase probes its primary then advances automatically.
                if preflight_runners(distinct, fatal=False):
                    preflighted.update(seen)
            preflight_done = True

        primary = runner_for(cfg, num, overrides)
        chain = unique_chain([primary], fallbacks, automatic_fallbacks(cfg, num))
        tooling = read_tooling(plan_path)

        # Phase 2 authors the dependency contract. Every later worker and every
        # independent gate receive one cached isolated environment for that exact
        # runtime+dependency set. Project package managers install into validator
        # scratch projects instead, through the same declaration.
        if num >= 3:
            try:
                ensure_validation_environment(tid)
            except ValidationEnvironmentError as exc:
                sys.exit(f"validation dependency provisioning failed: {exc}")

        # #17: never spend the editorial reviewer's tokens on a structurally-broken tome.
        # In order this is already true (Phase 7 gated strict); it matters on --from-phase 8.
        if num == 8:
            ok, report = validate_shipping(tid, tooling, plan_rel)
            if not ok:
                sys.exit("Phase 8 gate: the structural validator (--strict) must pass before the "
                         "editorial review runs — fix these first (or re-run from Phase 7):\n" + report)

        fb_note = f"  (+{len(chain) - 1} fallback)" if len(chain) > 1 else ""
        print(f"\n{'=' * 64}\n> Phase {num} — {title}   [runner: {primary[0]}]{fb_note}\n{'=' * 64}")
        access = access_boundary(tid, num)
        continuity_context = (reconciliation_prompt(tid, section_ids(tid), plan_path)
                              if num >= 7 and handoffs_exist(tid) and section_ids(tid) else "")
        phase_sections = section_ids(tid)
        warm_whole_phase3 = uses_whole_warm_worker(num, split_sections, phase_sections)
        whole_phase3_sidecars, warm_write_sections, resume_gate = [], [], None
        active_body = body
        if warm_whole_phase3:
            warm = prepare_warm_phase3_start(
                tid, title, body, (plan_rel, verdict_rel, findings_rel), tooling, access,
                resume=(args.from_phase == 3))
            prompt, continuity_context = warm.prompt, warm.context
            whole_phase3_sidecars, warm_write_sections, active_body, resume_gate = (
                warm.sidecars, warm.pending, warm.body, warm.gate)
            if warm.notice:
                print("  · " + warm.notice)
        else:
            prompt = (build_prompt(tid, num, title, active_body, plan_rel, verdict_rel,
                                   findings_rel, tooling=tooling)
                      + continuity_context + access)

        t0 = time.monotonic()
        pre = inventory(tid)                    # phase-start snapshot: the shrinkage contract
        runtime_pre = runtime_config_inventory() if num in (2, 8) else None
        review_edits = []                         # changes made by the latest Phase-8 pass
        marks = shrink_marks(shrink_path)
        attempt = 0
        ri = 0                                  # index into the runner chain
        retry_budget = retries_for(chain[0][0])  # local runners get more; the failure pause extends it
        skip_worker_once = bool(resume_gate and resume_gate[0])
        prevalidated = resume_gate if skip_worker_once else None

        # Split Phase 3: one warm provider process owns a bounded Arc-ordered batch. Every
        # section is checkpointed separately; a whole-tome reconciliation worker is launched
        # only when the complete executable gate proves one is actually needed.
        if num == 3 and split_sections and len(section_ids(tid)) >= 2:
            ri = author_sections_split(tid, num, title, chain,
                                       (plan_rel, verdict_rel, findings_rel), cfg, overrides,
                                       ping_interval, dead_pings, hard_cap,
                                       # starts below 3 wiped the sections (see wipe_sections),
                                       # so ONLY a start AT phase 3 is a genuine resume
                                       resume=(args.from_phase == 3), preflighted=preflighted,
                                       batch_size=section_batch_size)
            clear_section_progress(tid)  # section authoring is over; any next worker reconciles globally
            warm_write_sections = section_ids(tid)
            whole_phase3_sidecars = [os.path.join(BUILD_DIR, f"{tid}.handoffs")]
            handoffs_ok, handoffs_report = validate_all_handoffs(
                tid, section_ids(tid), plan_path)
            if not handoffs_ok:
                sys.exit("split-section continuity gate failed; resume Phase 3 so the owning "
                         "section workers can repair their exact handoffs:\n" + handoffs_report)
            prevalidated = validate_phase3(
                tid, tooling, plan_rel, section_ids(tid))
            if prevalidated[0]:
                print("  · Phase 3 full gate is clean — reconciliation worker not needed")
                # Enter the normal gate/accounting path without paying for a no-op AI turn.
                skip_worker_once = True
            else:
                reconcile_body = support_prompt("phase-3-reconcile")
                active_body = reconcile_body
                continuity_context = reconciliation_prompt(tid, section_ids(tid), plan_path)
                prompt = (build_prompt(tid, num, title, active_body, plan_rel, verdict_rel,
                                       findings_rel, tooling=tooling, repair_only=True)
                          + continuity_context + access
                          + "\n\n===== FULL PHASE-3 GATE REQUIRES RECONCILIATION =====\n"
                          + blocking_report(prevalidated[1]))
                prevalidated = None

        while True:
            name, cmd, input_mode = chain[ri]
            tome_scope = os.path.join(REPO, "tomes", tid)
            review_pre = review_inventory(tid) if num == 8 else None
            if num == 8:
                # A verdict belongs to this exact fresh invocation. Never let a PASS or
                # findings file from an earlier build satisfy the editorial gate.
                for review_sidecar in (verdict_path, findings_path):
                    open(review_sidecar, "w", encoding="utf-8").close()
            sidecars = phase_sidecars(
                num, plan_path, verdict_path, findings_path, shrink_path, tid=tid)
            if whole_phase3_sidecars:
                sidecars += whole_phase3_sidecars
            writable = prepare_phase_writable_paths(
                num, tome_scope, sidecars, warm_write_sections)
            if skip_worker_once:
                rc = 0
                skip_worker_once = False
            else:
                scoped = scoped_runner_command(name, cmd, tome_scope, writable, REPO)
                # Human-selected and implicit recovery runners do not exist during the initial
                # census. Give each one the same bounded Phase 0 check before it can do real work.
                if not preflight_recovery_runner(
                        name, cmd, scoped, input_mode, preflighted):
                    rc = 125  # advance to the next autonomous hand through normal death handling
                else:
                    try:
                        ensure_validation_environment(tid)
                        env = validation_subprocess_env(tid)
                    except ValidationEnvironmentError:
                        env = headless_validation_env()
                    env.update(ARCANUM_REPO_ROOT=REPO, ARCANUM_TOME_ROOT=tome_scope,
                               PYTHONDONTWRITEBYTECODE="1")
                    rc = run_agent(scoped, input_mode, prompt, ping_interval, dead_pings,
                                   hard_cap, cwd=tome_scope, env=env)
            died = rc != 0
            if died:
                print(f"  ! runner {name} exited {rc}" + (" (hung/timeout)" if rc == 124 else ""))
            if num >= 2:  # rename only once Phase 2 has set [runtime] project — before
                tid = maybe_rename(tid, plan_path)  # Phase 3 reads paths. Earlier, the
                # scaffold's placeholder project would rename untitled-N to a junk id.
                access = access_boundary(tid, num)
            if num == 8:
                review_edits = review_changes(review_pre, review_inventory(tid))
            if num == 1:  # Phase 1 writes the plan's Arc, not tome content — gate on that
                probs = []
                ok, report = validate(tid, phase=1, plan_rel=plan_rel)
            else:
                ok, report, probs, prevalidated = evaluate_content_gate(
                    tid, num, tooling, plan_rel, pre, marks, shrink_path,
                    runtime_pre, prevalidated, attempt)
            if num == 1 and not ok and "TOOLING_CONFLICT:" in report:
                sys.exit(report)
            if ok and not probs and not (num == 8 and died):
                print("  ok plan Arc written" if num == 1 else "  ok validate_tome: clean")
                break
            # A dead/quota-limited worker cannot spend a repair retry. Continue on the next
            # autonomous hand, preserving the exact tome state already on disk.
            if died:
                nxt = chain[ri + 1] if ri + 1 < len(chain) else None
                if nxt is None:
                    imp = _implicit_fallback(cfg, overrides, chain[ri])
                    if imp and imp[0][1] not in [c[1] for c in chain]:
                        chain.append(imp[0])
                        nxt = imp[0]
                if nxt is not None:
                    ri += 1
                    print(f"  ⇒ {name} died — continuing on {chain[ri][0]} "
                          f"(resumes from tomes/{tid}/ on disk)")
                    if warm_whole_phase3:
                        death_feedback = (("\n\n===== CURRENT GATE BLOCKERS =====\n"
                                           + blocking_report(report)) if not ok else "")
                        warm = prepare_warm_phase3_recovery(
                            tid, title, body, (plan_rel, verdict_rel, findings_rel), tooling,
                            access, death_feedback)
                        prompt, continuity_context = warm.prompt, warm.context
                        whole_phase3_sidecars, warm_write_sections, active_body = (
                            warm.sidecars, warm.pending, warm.body)
                    else:
                        prompt = (build_prompt(tid, num, title, active_body, plan_rel, verdict_rel,
                                               findings_rel, tooling=tooling)
                                  + continuity_context + access)
                    continue
            if attempt >= retry_budget:
                report_txt = "\n".join(probs + [report])
                if ri + 1 < len(chain):
                    ri += 1
                    retry_budget = attempt + retries_for(chain[ri][0])
                    print(f"  ⇒ repair budget spent — escalating phase {num} to {chain[ri][0]} "
                          f"(budget now {retry_budget}; resumes from disk)")
                else:
                    sys.exit(f"Phase {num} exhausted every autonomous repair hand:\n" + report_txt)
            attempt += 1
            what = "+".join(w for w, on in (("arc missing" if num == 1 else "validator", not ok),
                                            ("write contract", bool(probs)),
                                            ("worker exit", num == 8 and died)) if on)
            print(f"  x gates failed ({what}) -> re-running phase {num} (attempt {attempt + 1})")
            feedback = ""
            if not ok:
                retry_report = (report if num == 1 else
                                blocking_report(report, strict=(num >= 7)))
                feedback += (("\n\n===== the previous attempt did NOT deliver this phase =====\n"
                              if num == 1 else
                              "\n\n===== BLOCKING validator findings — fix only these =====\n")
                             + retry_report)
            if probs:
                feedback += ("\n\n===== phase write-contract violations =====\n" + "\n".join(probs) +
                             "\nRestore every out-of-scope change. If a reported tome removal or shrink "
                             "is genuinely deliberate, append one line starting "
                             f"`SHRINK OK:` to {os.path.relpath(shrink_path, REPO)} saying what and why; "
                             "that exception never authorizes another runtime file.")
            if warm_whole_phase3:
                warm = prepare_warm_phase3_recovery(
                    tid, title, body, (plan_rel, verdict_rel, findings_rel), tooling,
                    access, feedback)
                prompt, continuity_context = warm.prompt, warm.context
                whole_phase3_sidecars, warm_write_sections, active_body = (
                    warm.sidecars, warm.pending, warm.body)
            else:
                prompt = (build_prompt(tid, num, title, active_body, plan_rel, verdict_rel,
                                       findings_rel, tooling=tooling, repair_only=True)
                          + continuity_context + access + feedback)

        timings.append((num, name, round(time.monotonic() - t0), attempt + 1))

        if num == 1:                 # Later phases need the arc, not its Phase-1 schema.
            finalize_arc(plan_path)
        if num == 3:                 # #23: forecast the now-real content size
            clear_section_progress(tid)
            print(f"  · forecast: {forecast_line(measure(tid))}")

        if num == 8:
            review_unresolved = run_student_review(
                tid, title, body, (name, cmd, input_mode),
                (plan_rel, verdict_rel, findings_rel),
                (plan_path, verdict_path, findings_path, shrink_path),
                pre, runtime_pre, marks, review_edits, rc, continuity_context, access,
                ping_interval, dead_pings, hard_cap, timings,
                runner_chain=chain[ri:])

    if os.path.isdir(os.path.join(REPO, "tomes", tid)):
        append_ground_truth(tid, plan_path, timings)

    if review_unresolved is not None:
        print(f"\n{'!' * 64}\n! Phase 8 review hit its {MAX_STUDENT_LOOPS}-round cap WITHOUT a PASS.\n"
              f"! The tome VALIDATES but the editorial reviewer still flags blocking gaps:\n"
              f"{review_unresolved or '  (no structured findings written)'}\n"
              f"! Every autonomous review hand is exhausted; the harness exits nonzero and "
              f"does not mark this build done.\n{'!' * 64}")
        sys.exit(1)

    print(f"\n== all phases complete for '{tid}'. Smoke-test: http://localhost:8777/?tome={tid}")


if __name__ == "__main__":
    main()
