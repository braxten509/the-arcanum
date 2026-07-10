#!/usr/bin/env python3
"""build_tome.py — build a tome ONE PHASE AT A TIME, each in a fresh agent.

Why this exists: a single agent handed the whole workflow skips phases (especially the
final student-review pass) and half-reads buried rules. This harness runs each phase
file in tome-workflow/ as a SEPARATE headless agent, so no phase can be
skipped and each gets clean, focused context. Between content phases it runs
validate_tome.py as a hard gate and re-runs the phase (feeding back the errors) until
it passes. Phase 8 (student review + gap-fill) loops until the student agent writes PASS.

    python3 tools/build_tome.py <tome-id> [--from-phase N]

Which AI drives each phase is set in global-configs/harness.toml.

Cross-phase state is the FILESYSTEM: the tome under tomes/<id>/ that each phase mutates,
plus one plan file at .tome-build/<id>.plan.md carrying the gate answers + arc.
The machinery lives in tools/buildlib/ (see its __init__ for the module map);
this file is the CLI + the phase loop."""
import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import time

try:
    import tomllib
except ModuleNotFoundError:
    sys.exit("build_tome.py needs Python 3.11+ (tomllib).")

from buildlib import (BUILD_DIR, CONFIG, DEAD_PINGS_DEFAULT, MAX_STUDENT_LOOPS,
                      PING_INTERVAL_DEFAULT, REPO, WORKFLOW_DIR, retries_for)
from buildlib.checkpoints import arc_checkpoint, arc_written, maybe_rename, reset_arc
from buildlib.liveness import run_agent, preflight_runners
from buildlib.measure import forecast_line, inventory, measure, plan_shrink_marks, shrinkage, validate
from buildlib.prompts import (GATE_QS, build_prompt, do_gate, do_gate_json, gate_errors,
                              read_findings, read_tooling, read_verdict)
from buildlib.runners import (_implicit_fallback, parse_fallbacks, parse_runner_flags,
                              request_runner, runner_for)
from buildlib.sections import author_sections_split, section_ids, wipe_sections


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


PHASE_H1 = re.compile(r"#\s*Phase (\d+)\s*—\s*(.*)")


def parse_phases():
    """Read tome-workflow/phase-N-*.md, one file per phase, ordered by N.

    Returns [(num, title, body), ...]: the title comes from each file's `# Phase N — Title`
    H1, the body is everything after it — the phase's own instructions, verbatim.
    """
    phases = []
    for path in glob.glob(os.path.join(WORKFLOW_DIR, "phase-*.md")):
        head, _, body = open(path, encoding="utf-8").read().partition("\n")
        m = PHASE_H1.fullmatch(head.strip())
        if not m:
            sys.exit(f"{path}: first line must be '# Phase N — Title', got {head.strip()!r}")
        phases.append((int(m.group(1)), m.group(2).strip(), body.strip()))
    if not phases:
        sys.exit(f"parsed 0 phases from {WORKFLOW_DIR}/ — where did the phase-N-*.md files go?")
    return sorted(phases)


def _selftest():
    """Runnable check for the fallback/chain logic — `python3 tools/build_tome.py --selftest`."""
    from buildlib.liveness import _cpu_ticks, _descendants, _has_live_conn
    from buildlib.runners import _spec_to_runner, default_runner
    from buildlib.sections import _load_sections_done, _mark_section_done, _sections_done_path
    # spec → runner tuple
    d, cmd, im = _spec_to_runner("opencode-cli:opencode-go/deepseek-v4-flash", "--fallback")
    assert cmd[:2] == ["opencode", "run"] and "opencode-go/deepseek-v4-flash" in cmd, cmd
    assert im == "arg" and d == "opencode-cli opencode-go/deepseek-v4-flash", (im, d)
    # effort injection keeps codex's trailing stdin marker last
    _, ccmd, _ = _spec_to_runner("codex-cli:gpt-5.5@high", "--fallback")
    assert ccmd[-1] == "-" and "model_reasoning_effort=high" in ccmd, ccmd
    # agy: the appended prompt must land as --print's VALUE — a bare --print swallows the
    # next flag as the prompt (the Phase-1 "greeting" failures), so --print stays LAST
    _, gcmd, gim = _spec_to_runner("antigravity-cli:gemini-3-pro", "--runner")
    assert gcmd[-1] == "--print" and gim == "arg", gcmd
    # ordered fallback chain
    fb = parse_fallbacks(["opencode-cli:a", "codex-cli:b"])
    assert [x[0] for x in fb] == ["opencode-cli a", "codex-cli b"], fb
    # implicit fallback = default runner, but empty when the phase already IS default
    cfg = {"default": "d", "runners": {"d": {"cmd": ["opencode", "run", "-m", "m"], "input": "arg"}}}
    same = ("opencode-cli m", ["opencode", "run", "-m", "m"], "arg")
    diff = ("codex-cli x", ["codex", "exec", "-"], "stdin")
    assert _implicit_fallback(cfg, {}, same) == [], "no fallback when phase == default"
    assert _implicit_fallback(cfg, {}, diff) == [default_runner(cfg, {})], "fallback to default"
    # switch decision: only when a worker died AND another runner remains
    switch = lambda died, ri, n: died and ri + 1 < n
    assert switch(True, 0, 2) and not switch(False, 0, 2) and not switch(True, 1, 2)
    # liveness helpers read this very process tree
    me = os.getpid()
    assert me in _descendants(me), "descendant walk misses self"
    assert _cpu_ticks([me]) > 0, "our own process shows 0 CPU?"
    assert isinstance(_has_live_conn([me]), bool)
    # section list reads gracefully; missing tome → [] (split then falls back to one worker)
    assert section_ids("no-such-tome-xyz") == []
    # resume manifest: fresh id is empty, marks round-trip through disk, skip set is what resume reads
    os.makedirs(BUILD_DIR, exist_ok=True)
    _t = "selftest-resume-xyz"
    try:
        os.remove(_sections_done_path(_t))
    except OSError:
        pass
    assert _load_sections_done(_t) == set()
    _mark_section_done(_t, "s01")
    _mark_section_done(_t, "s03")
    assert _load_sections_done(_t) == {"s01", "s03"}, _load_sections_done(_t)
    os.remove(_sections_done_path(_t))
    # wipe_sections: drops stale section dirs AND the split-mode resume manifest
    _sec = os.path.join(REPO, "tomes", _t, "sections")
    os.makedirs(os.path.join(_sec, "s01"))
    _mark_section_done(_t, "s01")
    assert wipe_sections(_t) == 1 and not os.path.exists(_sec)
    assert _load_sections_done(_t) == set()
    os.rmdir(os.path.join(REPO, "tomes", _t))
    assert wipe_sections("no-such-tome-xyz") == 0  # fresh build: nothing to wipe, no error
    # Phase-0 input is a machine-enforced contract, not prose a weak model can guess around.
    good_gate = [(label, value) for (label, _), value in zip(
        GATE_QS, ("none", "1", "7", "6", "3", "external"))]
    assert gate_errors(good_gate) == [], gate_errors(good_gate)
    bad_gate = [(label, "") for label, _ in GATE_QS]
    assert len(gate_errors(bad_gate)) == 6, gate_errors(bad_gate)
    # Phase 1 gate: an empty/greeting run leaves the Arc blank → fail; every required
    # labeled part + the length floor → pass; a missing label or a thin arc → fail.
    from buildlib.checkpoints import ARC_CONTRACT, ARC_HEADING, ARC_PARTS, DAILY_DRIVERS
    plan_test = os.path.join(BUILD_DIR, f"{_t}.plan.md")
    header = "## Gate answers\n- stuff\n\n" + ARC_HEADING + ARC_CONTRACT
    dd = "; ".join(f"{d} = CAN" for d in DAILY_DRIVERS)
    full = "".join(f"**{p}:** {dd if p == 'Daily drivers' else 'hammered out in ample forge-detail'}\n"
                   for p in ARC_PARTS)
    for extra, expected in (("", False), ("\n\n", False),
                            (full, True),
                            (full.replace("**Graduate ledger:**", "ledger"), False),  # missing part
                            (full.replace("key-value = CAN", "key-value"), False),    # driver unassigned
                            ("".join(f"**{p}:** x\n" for p in ARC_PARTS), False)):    # under the floor
        with open(plan_test, "w", encoding="utf-8") as f:
            f.write(header + extra)
        ok, _ = arc_written(plan_test, plan_test)
        assert ok is expected, (extra, expected)
    reset_arc(plan_test)  # a --from-phase 1 restart blanks the old arc → gate must fail again
    assert arc_written(plan_test, plan_test)[0] is False
    os.remove(plan_test)
    assert arc_written("/no/such/plan.md", "x")[0] is False
    # The editorial protocol accepts exactly PASS, never "NOT PASS" or explanatory prose.
    verdict_test = os.path.join(BUILD_DIR, f"{_t}.verdict")
    for raw, expected in (("PASS\n", "PASS"), ("GAPS REMAIN\n", "GAPS REMAIN"),
                          ("NOT PASS\n", None), ("PASS - looks good\n", None)):
        with open(verdict_test, "w", encoding="utf-8") as f:
            f.write(raw)
        assert read_verdict(verdict_test) == expected, raw
    print("build_tome self-test: OK")


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

    # Preflight every DISTINCT endpoint that will drive a phase (the drafter/writer/reviewer
    # may be different providers), deduped by command — so a bad model/login for ANY selected
    # runner is caught up front, not on the phase that first uses it.
    distinct, seen = [], set()
    for pnum, _, _ in phases:
        if pnum == 0 or pnum < args.from_phase:
            continue
        nm, cmd, im = runner_for(cfg, pnum, overrides)
        if tuple(cmd) not in seen:
            seen.add(tuple(cmd))
            distinct.append((nm, cmd, im))
    if distinct:
        preflight_runners(distinct)

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

        primary = runner_for(cfg, num, overrides)
        # Runner chain: the primary, then any explicit --fallback runners, tried in order when
        # a worker DIES (each resumes from the tome on disk). With no --fallback left, a death
        # instead PAUSES for a human to pick the next runner — see the death handling below.
        chain = [primary] + list(fallbacks)

        # #17: never spend the editorial reviewer's tokens on a structurally-broken tome.
        # In order this is already true (Phase 7 gated strict); it matters on --from-phase 8.
        if num == 8:
            ok, report = validate(tid, strict=True, tooling=read_tooling(plan_path))
            if not ok:
                sys.exit("Phase 8 gate: the structural validator (--strict) must pass before the "
                         "editorial review runs — fix these first (or re-run from Phase 7):\n" + report)

        fb_note = f"  (+{len(chain) - 1} fallback)" if len(chain) > 1 else ""
        print(f"\n{'=' * 64}\n> Phase {num} — {title}   [runner: {primary[0]}]{fb_note}\n{'=' * 64}")
        prompt = build_prompt(tid, num, title, body, plan_rel, verdict_rel, findings_rel)

        t0 = time.monotonic()
        pre = inventory(tid)                    # phase-start snapshot: the shrinkage contract
        marks = plan_shrink_marks(plan_path)    # SHRINK OK lines already in the plan
        attempt = 0
        ri = 0                                  # index into the runner chain
        retry_budget = retries_for(chain[0][0])  # local runners get more; the failure pause extends it

        # Split Phase 3: author each section in its own worker (small context → any model is
        # affordable), then let the loop below run the workflow's whole-tome reconcile/validate.
        if num == 3 and split_sections and len(section_ids(tid)) >= 2:
            ri = author_sections_split(tid, num, title, body, chain,
                                       (plan_rel, verdict_rel, findings_rel), cfg, overrides,
                                       ping_interval, dead_pings, hard_cap, ask_on_death,
                                       interactive, args.tome_id,
                                       # starts below 3 wiped the sections (see wipe_sections),
                                       # so ONLY a start AT phase 3 is a genuine resume
                                       resume=(args.from_phase == 3))
            prompt = build_prompt(tid, num, title, body, plan_rel, verdict_rel, findings_rel) + (
                "\n\n===== every section is ALREADY authored, one worker per section, on disk — "
                "do NOT re-author them =====\nDo the end-of-Phase-3 reconciliation across the whole "
                "tome: tally the anti-template rules (lesson/exercise shape, mc `answer`-index spread, "
                "and per-exercise hint/prompt/whyWrong/explain) ACROSS all sections and fix the "
                "outliers; verify concepts stay strictly cumulative across section boundaries; remove "
                "any cross-section duplication; and confirm one consistent mentor voice throughout. "
                "Then make validate_tome pass. Author no new sections.")

        while True:
            name, cmd, input_mode = chain[ri]
            rc = run_agent(cmd, input_mode, prompt, ping_interval, dead_pings, hard_cap)
            died = rc != 0
            if died:
                print(f"  ! runner {name} exited {rc}" + (" (hung/timeout)" if rc == 124 else ""))
            if num >= 2:  # rename only once Phase 2 has set [runtime] project — before
                tid = maybe_rename(tid, plan_path)  # Phase 3 reads paths. Earlier, the
                # scaffold's placeholder project would rename untitled-N to a junk id.
            if num == 1:  # Phase 1 writes the plan's Arc, not tome content — gate on that
                probs = []
                ok, report = arc_written(plan_path, plan_rel)
            elif not os.path.isdir(os.path.join(REPO, "tomes", tid)):
                break  # the raw scaffold isn't gradeable until Phase 2 fills it in
            else:
                probs = shrinkage(pre, inventory(tid))
                if probs and plan_shrink_marks(plan_path) > marks:
                    print(f"  · shrinkage justified in the plan (SHRINK OK): {len(probs)} change(s) accepted")
                    probs = []
                ok, report = validate(tid, strict=(num >= 7), tooling=read_tooling(plan_path))  # Phase 7+: hard-gate WARNs fail too
            if ok and not probs:
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
                    prompt = build_prompt(tid, num, title, body, plan_rel, verdict_rel, findings_rel)
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
                                            ("shrinkage", bool(probs))) if on)
            print(f"  x gates failed ({what}) -> re-running phase {num} (attempt {attempt + 1})")
            feedback = ""
            if not ok:
                feedback += (("\n\n===== the previous attempt did NOT deliver this phase =====\n"
                              if num == 1 else
                              "\n\n===== validate_tome.py still reports failures — fix exactly these =====\n")
                             + report)
            if probs:
                feedback += ("\n\n===== cross-phase contract violations — this phase deleted or shrank "
                             "content an earlier phase built =====\n" + "\n".join(probs) +
                             "\nRestore it. If a removal is genuinely deliberate, append a line starting "
                             "`SHRINK OK:` to the plan file saying what and why; it will then be accepted.")
            prompt = build_prompt(tid, num, title, body, plan_rel, verdict_rel, findings_rel) + feedback

        timings.append((num, name, round(time.monotonic() - t0), attempt + 1))

        if num == 1:                 # #21: human approves the arc before authoring commits to it
            arc_checkpoint(plan_path, interactive, args.yes)
        if num == 3:                 # #23: forecast the now-real content size
            print(f"  · forecast: {forecast_line(measure(tid))}")

        if num == 8:  # loop the student review/fill until PASS (#18 capped, #19 scoped)
            loop = 1
            verdict = read_verdict(verdict_path)
            validation_focus = None
            while verdict != "PASS" and loop < MAX_STUDENT_LOOPS:
                loop += 1
                focus = read_findings(findings_path)  # #19: re-review only the flagged files
                if validation_focus:
                    focus = ((focus + "\n") if focus else "") + validation_focus
                where = "flagged files only" if focus else "full re-read (no findings file)"
                print(f"  ~ student verdict not PASS -> review/fill loop {loop} ({where})")
                t1 = time.monotonic()
                rc = run_agent(cmd, input_mode,
                               build_prompt(tid, num, title, body, plan_rel, verdict_rel, findings_rel, focus),
                               ping_interval, dead_pings, hard_cap)
                timings.append((f"8.{loop}", name, round(time.monotonic() - t1), 1))
                verdict = read_verdict(verdict_path)
                ok, report = validate(tid, strict=True, tooling=read_tooling(plan_path))
                if not ok:
                    print("  x Phase 8 revisions broke strict validation; the next review must fix it")
                    validation_focus = ("- [blocking] strict validator failures introduced during "
                                        "review:\n" + report)
                    verdict = None  # PASS cannot override a structurally broken tome
                else:
                    validation_focus = None
                if rc != 0:
                    print(f"  ! Phase 8 review worker exited {rc}; no verdict is trusted")
                    verdict = None
            if verdict != "PASS":     # #18: cap reached — surface, don't pretend success
                review_unresolved = (validation_focus or read_findings(findings_path)
                                     or "reviewer did not write the exact one-line verdict PASS")

    # #11: the plan is prose ("claims are not evidence") — append the harness's own
    # ground-truth counts + phase timings so the numbers are on disk, not asserted.
    if os.path.isdir(os.path.join(REPO, "tomes", tid)):
        mv = measure(tid)
        with open(plan_path, "a", encoding="utf-8") as f:
            f.write("\n## Harness ground truth (measured from disk)\n")
            f.write(f"- {forecast_line(mv)}\n")
            f.write(f"- exercise points {mv['ex_points']} · freestyle rewards {mv['fs_reward']} "
                    f"· intrusion bounties {mv['bounty']} → base earnable {mv['base_earnable']}\n")
            f.write(f"- banks: {mv['themes']} themes · {mv['shop']} shop items · {mv['badges']} badges\n")
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
