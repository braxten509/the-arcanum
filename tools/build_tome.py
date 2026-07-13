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

try:
    import tomllib
except ModuleNotFoundError:
    sys.exit("build_tome.py needs Python 3.11+ (tomllib).")

from buildlib import (BUILD_DIR, CONFIG, DEAD_PINGS_DEFAULT, MAX_STUDENT_LOOPS,
                      PING_INTERVAL_DEFAULT, REPO, retries_for)
from buildlib.checkpoints import arc_checkpoint, finalize_arc, maybe_rename, reset_arc
from buildlib.continuity import (handoffs_exist, planned_edges, reconciliation_prompt,
                                 validate_all_handoffs)
from buildlib.agent_runtime import scoped_runner_command
from buildlib.liveness import run_agent, preflight_runners
from buildlib.measure import (forecast_line, inventory, measure, runtime_config_inventory,
                              review_changes, review_inventory,
                              runtime_config_scope_violations, selected_runtime_config,
                              shrink_marks, shrinkage, validate, blocking_report)
from buildlib.prompts import build_prompt, do_gate, do_gate_json, read_tooling
from buildlib.review import run_student_review
from buildlib.runners import (_implicit_fallback, parse_fallbacks, parse_runner_flags,
                              request_runner, runner_for)
from buildlib.sections import author_sections_split, section_ids, wipe_sections
from buildlib.skeleton import scaffold_sections
from buildlib.workflow import (access_boundary, parse_phases, phase_sidecars,
                               phase_writable_paths, support_prompt)


def load_config(preset=None):
    if not os.path.exists(CONFIG):
        sys.exit(f"missing {CONFIG} — see the sample in the repo.")
    with open(CONFIG, "rb") as f:
        cfg = tomllib.load(f)
    preset = preset or cfg.get("preset")
    if preset:
        p = (cfg.get("presets") or {}).get(preset)
        if not p:
            sys.exit(f"harness.toml: preset {preset!r} requested but no [presets.{preset}] table")
        cfg["default"] = p.get("default", cfg.get("default"))
        cfg["phases"] = dict(p.get("phases") or {})  # a preset is a full matrix, not a merge
        print(f"  · preset {preset!r}: default={cfg['default']}, phase overrides={cfg['phases'] or '(none)'}")
    return cfg


def _selftest():
    """Runnable check for the fallback/chain logic — `python3 tools/build_tome.py --selftest`."""
    from buildlib.build_selftest import run
    run()


def main():
    if "--selftest" in sys.argv[1:]:
        _selftest()
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
                    help="skip the interactive arc checkpoint after Phase 1 (for unattended runs)")
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
                    help="when a worker dies with no --fallback left, PAUSE and request a new "
                         "runner from the UI (via .tome-build handshake) instead of failing. The "
                         "web bindery passes this; the build waits until a runner is chosen.")
    ap.add_argument("--split-sections", action="store_true",
                    help="author Phase 3 one SECTION per fresh worker instead of the whole tome in "
                         "one session — keeps each worker's context (and cache-read cost) small, so "
                         "any model is affordable there. Falls back to a single worker if the tome "
                         "has <2 sections.")
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
    ask_on_death = args.ask_on_death
    split_sections = args.split_sections
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
    interactive = sys.stdin.isatty() and args.gate_json is None
    timings = []              # (phase, runner, seconds, attempts) for the end-of-run log
    review_unresolved = None  # set if Phase 8 exhausts its loops without PASS

    tome_dir = os.path.join(REPO, "tomes", tid)
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
                preflight_runners(distinct)
                preflighted.update(seen)
            preflight_done = True

        primary = runner_for(cfg, num, overrides)
        # Runner chain: the primary, then any explicit --fallback runners, tried in order when
        # a worker DIES (each resumes from the tome on disk). With no --fallback left, a death
        # instead PAUSES for a human to pick the next runner — see the death handling below.
        chain = [primary] + list(fallbacks)
        tooling = read_tooling(plan_path)

        # #17: never spend the editorial reviewer's tokens on a structurally-broken tome.
        # In order this is already true (Phase 7 gated strict); it matters on --from-phase 8.
        if num == 8:
            ok, report = validate(tid, phase=8, tooling=tooling)
            if not ok:
                sys.exit("Phase 8 gate: the structural validator (--strict) must pass before the "
                         "editorial review runs — fix these first (or re-run from Phase 7):\n" + report)

        fb_note = f"  (+{len(chain) - 1} fallback)" if len(chain) > 1 else ""
        print(f"\n{'=' * 64}\n> Phase {num} — {title}   [runner: {primary[0]}]{fb_note}\n{'=' * 64}")
        access = access_boundary(tid, num)
        continuity_context = ""
        if num >= 7 and handoffs_exist(tid) and section_ids(tid):
            continuity_context = reconciliation_prompt(tid, section_ids(tid), plan_path)
        active_body = body
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

        # Split Phase 3: author each section in its own worker (small context → any model is
        # affordable), then let the loop below run the workflow's whole-tome reconcile/validate.
        if num == 3 and split_sections and len(section_ids(tid)) >= 2:
            ri = author_sections_split(tid, num, title, chain,
                                       (plan_rel, verdict_rel, findings_rel), cfg, overrides,
                                       ping_interval, dead_pings, hard_cap, ask_on_death,
                                       interactive, args.tome_id,
                                       # starts below 3 wiped the sections (see wipe_sections),
                                       # so ONLY a start AT phase 3 is a genuine resume
                                       resume=(args.from_phase == 3), preflighted=preflighted)
            handoffs_ok, handoffs_report = validate_all_handoffs(
                tid, section_ids(tid), plan_path)
            if not handoffs_ok:
                sys.exit("split-section continuity gate failed; resume Phase 3 so the owning "
                         "section workers can repair their exact handoffs:\n" + handoffs_report)
            reconcile_body = support_prompt("phase-3-reconcile")
            active_body = reconcile_body
            continuity_context = reconciliation_prompt(tid, section_ids(tid), plan_path)
            prompt = (build_prompt(tid, num, title, active_body, plan_rel, verdict_rel,
                                   findings_rel, tooling=tooling)
                      + continuity_context + access)

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
                num, plan_path, verdict_path, findings_path, shrink_path)
            writable = phase_writable_paths(num, tome_scope, sidecars)
            scoped = scoped_runner_command(name, cmd, tome_scope, writable, REPO)
            # Human-selected and implicit recovery runners do not exist during the initial
            # census. Give each one the same bounded Phase 0 check before it can do real work.
            if tuple(cmd) not in preflighted:
                preflight_runners([(name, scoped, input_mode)])
                preflighted.add(tuple(cmd))
            env = os.environ.copy()
            env.update(ARCANUM_REPO_ROOT=REPO, ARCANUM_TOME_ROOT=tome_scope,
                       PYTHONDONTWRITEBYTECODE="1")
            rc = run_agent(scoped, input_mode, prompt, ping_interval, dead_pings, hard_cap,
                           cwd=tome_scope, env=env)
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
                shrink_probs = shrinkage(pre, inventory(tid))
                if shrink_probs and shrink_marks(shrink_path) > marks:
                    print(f"  · shrinkage justified in {os.path.relpath(shrink_path, REPO)}: "
                          f"{len(shrink_probs)} change(s) accepted")
                    shrink_probs = []
                probs = list(shrink_probs)
                if num in (2, 8):
                    probs += runtime_config_scope_violations(
                        runtime_pre, selected_runtime_config(tid))
                if not os.path.isdir(os.path.join(REPO, "tomes", tid)):
                    ok, report = False, f"tomes/{tid}/ is missing — restore the scaffolded tome"
                else:
                    ok, report = validate(
                        tid, phase=num, tooling=tooling)
            if num == 1 and not ok and "TOOLING_CONFLICT:" in report:
                sys.exit(report)
            if ok and not probs and not (num == 8 and died):
                print("  ok plan Arc written" if num == 1 else "  ok validate_tome: clean")
                break
            # A DIED worker (crash/quota/hang) that left work undone: don't waste a validator
            # retry re-invoking a dead/exhausted worker — continue on ANOTHER runner, which
            # resumes from the tome on disk. Explicit --fallback runners go first; with none
            # left, PAUSE for a human to choose (the Bindery box, or a TTY prompt).
            if died:
                nxt = chain[ri + 1] if ri + 1 < len(chain) else None
                reason = "hung/timeout" if rc == 124 else f"exit {rc}"
                if nxt is None and (ask_on_death or interactive):
                    nxt, _ = request_runner(args.tome_id, num, name, reason, interactive)
                    if nxt is not None:
                        chain.append(nxt)
                elif nxt is None:  # unattended, nobody to ask → default runner as a safety net
                    imp = _implicit_fallback(cfg, overrides, chain[ri])
                    if imp and imp[0][1] not in [c[1] for c in chain]:
                        chain.append(imp[0])
                        nxt = imp[0]
                if nxt is not None:
                    ri += 1
                    print(f"  ⇒ {name} died — continuing on {chain[ri][0]} "
                          f"(resumes from tomes/{tid}/ on disk)")
                    prompt = (build_prompt(tid, num, title, active_body, plan_rel, verdict_rel,
                                           findings_rel, tooling=tooling)
                              + continuity_context + access)
                    continue
            if attempt >= retry_budget:
                # Automatic budget spent. Unattended with nobody to ask → fail as before. Otherwise
                # PAUSE and let the operator grant more retries and/or switch THIS phase's model
                # (Bindery box / TTY prompt); either way it resumes the phase from the tome on disk.
                report_txt = "\n".join(probs + [report])
                if not (ask_on_death or interactive):
                    sys.exit(f"Phase {num} still fails its gates after {attempt} retries:\n" + report_txt)
                nxt, extra = request_runner(args.tome_id, num, name,
                                            f"{attempt} retries used", interactive, report=report_txt)
                if nxt is None and extra <= 0:
                    sys.exit(f"Phase {num} still fails its gates after {attempt} retries "
                             f"(operator declined to continue):\n" + report_txt)
                if nxt is not None and nxt[1] not in [c[1] for c in chain]:
                    chain.append(nxt)
                    ri = len(chain) - 1
                    print(f"  ⇒ operator switched phase {num} to {chain[ri][0]}")
                retry_budget = attempt + max(extra, 1)  # a model switch with no count = one more go
                print(f"  ↻ operator granted more retries — budget now {retry_budget} "
                      f"(resumes from tomes/{tid}/ on disk)")
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
            prompt = (build_prompt(tid, num, title, active_body, plan_rel, verdict_rel,
                                   findings_rel, tooling=tooling, repair_only=True)
                      + continuity_context + access + feedback)

        timings.append((num, name, round(time.monotonic() - t0), attempt + 1))

        if num == 1:                 # Later phases need the arc, not its Phase-1 schema.
            finalize_arc(plan_path)
            # #21: human approves the arc before authoring commits to it
            arc_checkpoint(plan_path, interactive, args.yes)
        if num == 3:                 # #23: forecast the now-real content size
            print(f"  · forecast: {forecast_line(measure(tid))}")

        if num == 8:
            review_unresolved = run_student_review(
                tid, title, body, (name, cmd, input_mode),
                (plan_rel, verdict_rel, findings_rel),
                (plan_path, verdict_path, findings_path, shrink_path),
                pre, runtime_pre, marks, review_edits, rc, continuity_context, access,
                ping_interval, dead_pings, hard_cap, timings,
                build_id=args.tome_id, ask_on_death=ask_on_death,
                interactive=interactive)

    # #11: append measured ground truth; model-authored decisions are not measurement.
    if os.path.isdir(os.path.join(REPO, "tomes", tid)):
        mv = measure(tid)
        with open(plan_path, "a", encoding="utf-8") as f:
            f.write("\n## Harness ground truth (measured from disk)\n")
            f.write(f"- {forecast_line(mv)}\n")
            f.write(f"- exercise points {mv['ex_points']} · freestyle rewards {mv['fs_reward']} "
                    f"→ fixed face-value {mv['base_earnable']}\n")
            if mv["bounty_max"]:
                f.write(f"- repeatable hex-defense bonus {mv['bounty_min']}–{mv['bounty_max']} "
                        f"per win (tier schedule sum {mv['bounty']}; excluded from fixed total)\n")
            f.write(f"- banks: {mv['themes']} themes · {mv['shop']} shop items · {mv['badges']} badges\n")
            if handoffs_exist(tid) and section_ids(tid):
                continuity_ok, _ = validate_all_handoffs(tid, section_ids(tid), plan_path)
                f.write(f"- continuity: {len(section_ids(tid))} section handoffs · "
                        f"{len(planned_edges(plan_path, section_ids(tid)))} planned edges · "
                        f"gate {'CLOSED' if continuity_ok else 'BROKEN'}\n")
            if timings:
                f.write("\n### Phase timings\n")
                for ph, rn, secs, tries in timings:
                    f.write(f"- phase {ph}: {secs}s via {rn}"
                            + (f" ({tries} attempts)" if tries > 1 else "") + "\n")

    if review_unresolved is not None:
        print(f"\n{'!' * 64}\n! Phase 8 review hit its {MAX_STUDENT_LOOPS}-round cap WITHOUT a PASS.\n"
              f"! The tome VALIDATES but the editorial reviewer still flags blocking gaps:\n"
              f"{review_unresolved or '  (no structured findings written)'}\n"
              f"! Surfaced for a human — the harness exits nonzero and does not mark this build done.\n{'!' * 64}")
        sys.exit(1)

    print(f"\n== all phases complete for '{tid}'. Smoke-test: http://localhost:8777/?tome={tid}")


if __name__ == "__main__":
    main()
