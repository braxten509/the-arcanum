#!/usr/bin/env python3
"""build_tome.py — build a tome ONE PHASE AT A TIME, each in a fresh agent.

Why this exists: a single agent handed the whole TOME-WORKFLOW.md skips phases
(especially the final student-review pass) and half-reads buried rules. This harness
runs each phase of TOME-WORKFLOW.md as a SEPARATE headless agent, so no phase can be
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
import os
import re
import subprocess
import sys
import time

try:
    import tomllib
except ModuleNotFoundError:
    sys.exit("build_tome.py needs Python 3.11+ (tomllib).")

from buildlib import (BUILD_DIR, CONFIG, DEAD_PINGS_DEFAULT, MAX_STUDENT_LOOPS,
                      PING_INTERVAL_DEFAULT, REPO, WORKFLOW, retries_for)
from buildlib.liveness import run_agent, preflight_runners
from buildlib.measure import forecast_line, inventory, measure, plan_shrink_marks, shrinkage, validate
from buildlib.prompts import build_prompt, do_gate, do_gate_json, read_findings, read_tooling, read_verdict
from buildlib.runners import (_implicit_fallback, parse_fallbacks, parse_runner_flags,
                              request_runner, runner_for)
from buildlib.sections import author_sections_split, section_ids


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


def parse_phases():
    """Slice TOME-WORKFLOW.md on its '## Phase N — Title' headers.

    Returns [(num, title, body), ...]. The body is the phase's own instructions,
    verbatim, minus any trailing '---' separator.
    """
    text = open(WORKFLOW, encoding="utf-8").read()
    parts = re.split(r"^## Phase (\d+)\s*—\s*(.*)$", text, flags=re.M)
    phases = []
    for i in range(1, len(parts), 3):  # [pre, num, title, body, num, title, body, ...]
        num = int(parts[i])
        title = parts[i + 1].strip()
        body = re.sub(r"\n+---\s*$", "", parts[i + 2]).strip()
        phases.append((num, title, body))
    if not phases:
        sys.exit("parsed 0 phases from TOME-WORKFLOW.md — did the '## Phase N —' headers change?")
    return phases


def arc_checkpoint(plan_path, interactive, skip):
    """#21: after Phase 1, let a human approve the arc before ~30k tokens of authoring commit
    to it. Zero model cost. Skipped automatically when non-interactive (web/--gate-json) or --yes."""
    if skip or not interactive:
        print("  · arc checkpoint skipped (non-interactive or --yes) — review the plan's Arc if unsure")
        return
    try:
        arc = open(plan_path, encoding="utf-8").read().split("## Arc", 1)[-1]
    except OSError:
        return
    print("\n" + "-" * 64 + "\n  PHASE 1 ARC — approve before authoring commits to it:\n" + "-" * 64)
    print(arc.strip()[:2000] or "(no arc recorded?)")
    ans = input("\n  Proceed with this arc? [y = go / anything else = stop and edit the plan] > ").strip().lower()
    if ans != "y":
        sys.exit("Stopped at the arc checkpoint. Edit the plan's Arc, then resume with "
                 "--from-phase 2.")


KEBAB_SPLIT = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")  # camel boundary -> hyphen (§6 one-name rule)


def maybe_rename(tid, plan_path):
    """Filesystem surgery is the harness's job, not an agent's: when [runtime] project
    implies a different kebab-case id (§6: ManaWeaver -> mana-weaver, never the
    requester's phrasing), rename the folder and patch meta.id deterministically. The
    agent-driven version of this move nested an entire tome inside itself once; never again.
    Returns the (possibly new) tome id."""
    manifest = os.path.join(REPO, "tomes", tid, "tome.toml")
    if not os.path.isfile(manifest):
        return tid
    try:
        with open(manifest, "rb") as f:
            m = tomllib.load(f)
    except Exception:
        return tid  # unparseable manifest — the validator will say so
    project = str((m.get("runtime") or {}).get("project") or "").strip()
    new = re.sub(r"[^a-z0-9]+", "-", KEBAB_SPLIT.sub("-", project).lower()).strip("-")
    if not new or new == tid:
        return tid
    target = os.path.join(REPO, "tomes", new)
    if os.path.exists(target):
        print(f"  ! naming: id should be {new!r} but tomes/{new} already exists — keeping {tid!r}")
        return tid
    os.rename(os.path.join(REPO, "tomes", tid), target)
    tpath = os.path.join(target, "tome.toml")
    txt = open(tpath, encoding="utf-8").read()
    with open(tpath, "w", encoding="utf-8") as f:  # [meta] id is the first id = "…" line
        f.write(re.sub(r'(?m)^(id\s*=\s*)"[^"]*"', rf'\g<1>"{new}"', txt, count=1))
    with open(plan_path, "a", encoding="utf-8") as f:
        f.write(f"\n- **Tome id renamed by the harness:** `{tid}` → `{new}` "
                f"(kebab-case of project {project!r}); all later phases use tomes/{new}/\n")
    print(f"  · renamed tomes/{tid} -> tomes/{new} (kebab-case of project {project!r}); meta.id patched")
    return new


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
    print("build_tome self-test: OK")


def main():
    if "--selftest" in sys.argv[1:]:
        _selftest()
        return
    ap = argparse.ArgumentParser(description="Build a tome phase-by-phase via harness.toml runners.")
    ap.add_argument("tome_id")
    ap.add_argument("--from-phase", type=int, default=0, help="resume at this phase number")
    ap.add_argument("--gate-json", default=None, metavar="JSON",
                    help='answer Phase 0 non-interactively: {"prior_knowledge","depth","tooling"}'
                         ' (tooling = internal|external|both)')
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

    if os.path.isdir(os.path.join(REPO, "tomes", tid)):  # resume: forecast current size (#23)
        print(f"  · forecast: {forecast_line(measure(tid))}")

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
                                       interactive, args.tome_id, resume=(args.from_phase > 0))
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
            if num < 2 or not os.path.isdir(os.path.join(REPO, "tomes", tid)):
                break  # Phase 0/1 write the plan+arc, not tome content — the raw scaffold
                       # the harness laid down isn't gradeable until Phase 2 fills it in
            probs = shrinkage(pre, inventory(tid))
            if probs and plan_shrink_marks(plan_path) > marks:
                print(f"  · shrinkage justified in the plan (SHRINK OK): {len(probs)} change(s) accepted")
                probs = []
            ok, report = validate(tid, strict=(num >= 7), tooling=read_tooling(plan_path))  # Phase 7+: hard-gate WARNs fail too
            if ok and not probs:
                print(f"  ok validate_tome: clean")
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
            what = "+".join(w for w, on in (("validator", not ok), ("shrinkage", bool(probs))) if on)
            print(f"  x gates failed ({what}) -> re-running phase {num} (attempt {attempt + 1})")
            feedback = ""
            if not ok:
                feedback += ("\n\n===== validate_tome.py still reports failures — fix exactly these =====\n"
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
            while verdict != "PASS" and loop < MAX_STUDENT_LOOPS:
                loop += 1
                focus = read_findings(findings_path)  # #19: re-review only the flagged files
                where = "flagged files only" if focus else "full re-read (no findings file)"
                print(f"  ~ student verdict not PASS -> review/fill loop {loop} ({where})")
                t1 = time.monotonic()
                run_agent(cmd, input_mode,
                          build_prompt(tid, num, title, body, plan_rel, verdict_rel, findings_rel, focus),
                          ping_interval, dead_pings, hard_cap)
                timings.append((f"8.{loop}", name, round(time.monotonic() - t1), 1))
                verdict = read_verdict(verdict_path)
            if verdict != "PASS":     # #18: cap reached — surface, don't pretend success
                review_unresolved = read_findings(findings_path)

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
              f"! Surfaced for a human — do not treat this build as done.\n{'!' * 64}")

    print(f"\n== all phases complete for '{tid}'. Smoke-test: http://localhost:8777/?tome={tid}")


if __name__ == "__main__":
    main()
