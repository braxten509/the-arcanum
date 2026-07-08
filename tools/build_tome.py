#!/usr/bin/env python3
"""build_tome.py — build a tome ONE PHASE AT A TIME, each in a fresh agent.

Why this exists: a single agent handed the whole TOME-WORKFLOW.md skips phases
(especially the final student-review pass) and half-reads buried rules. This harness
runs each phase of TOME-WORKFLOW.md as a SEPARATE headless agent, so no phase can be
skipped and each gets clean, focused context. Between content phases it runs
validate_tome.py as a hard gate and re-runs the phase (feeding back the errors) until
it passes. Phase 8 (student review + gap-fill) loops until the student agent writes PASS.

    python3 tools/build_tome.py <tome-id> [--from-phase N]

Which AI drives each phase is set in harness.toml at the repo root.

Cross-phase state is the FILESYSTEM: the tome under tomes/<id>/ that each phase mutates,
plus one plan file at .tome-build/<id>.plan.md carrying the gate answers + arc. Stdlib only.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import signal
import sys
import threading
import time

try:
    import tomllib
except ModuleNotFoundError:
    sys.exit("build_tome.py needs Python 3.11+ (tomllib).")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(REPO, "TOME-WORKFLOW.md")
CONFIG = os.path.join(REPO, "harness.toml")
VALIDATOR = os.path.join(REPO, "tools", "validate_tome.py")
BUILD_DIR = os.path.join(REPO, ".tome-build")

MAX_RETRIES = 2        # per content phase on validator ERROR — paid cloud runners (retries cost money)
MAX_RETRIES_LOCAL = 4  # a free local ollama runner gets more automatic tries before it pauses to ask
MAX_STUDENT_LOOPS = 3  # phase 8 review -> fill loops before giving up
PING_INTERVAL_DEFAULT = 30  # seconds between worker liveness checks
DEAD_PINGS_DEFAULT = 2      # consecutive idle checks before a worker is declared hung


def retries_for(runner_display):
    """Default gate-retry budget for a phase's runner: a free local/ollama worker gets more tries
    than a paid cloud one. The operator can extend either on the failure pause (see request_runner)."""
    return MAX_RETRIES_LOCAL if "ollama/" in (runner_display or "") else MAX_RETRIES


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


# Ready-made runner templates the web bindery's pickers map onto (--runner overrides).
# A build runner must wield tools and edit files, so only the agentic login CLIs
# qualify — ollama prints text; it cannot hold the quill.
CLI_RUNNERS = {
    "claude-cli": {"cmd": ["claude", "-p", "--permission-mode", "acceptEdits", "--model", "{model}"], "input": "arg",
                   "efforts": ("low", "medium", "high", "xhigh", "max"),
                   "effortArgs": ["--effort", "{effort}"]},
    # agy has no effort switch — its Gemini model names carry it (Low/Medium/High variants)
    "antigravity-cli": {"cmd": ["agy", "--print", "--dangerously-skip-permissions", "--model", "{model}"], "input": "stdin"},
    "codex-cli": {"cmd": ["codex", "exec", "--skip-git-repo-check", "-s", "workspace-write", "-m", "{model}", "-"], "input": "stdin",
                  "efforts": ("minimal", "low", "medium", "high", "xhigh"),
                  "effortArgs": ["-c", "model_reasoning_effort={effort}"]},
    # opencode drives OpenCode Go / free models (opencode-go/*, opencode/*) AND local models
    # (ollama/* run THROUGH the opencode agent, which wields the tools the raw model can't).
    # --dangerously-skip-permissions auto-approves edits/bash so it can build headlessly (same
    # posture as agy/claude above). --variant is opencode's reasoning-effort knob — only some
    # models honour a given variant, so the picker offers it for OpenCode CLI (not Local) and
    # leaving it DEFAULT sends none.
    "opencode-cli": {"cmd": ["opencode", "run", "--dangerously-skip-permissions", "-m", "{model}"], "input": "arg",
                     "efforts": ("none", "minimal", "low", "medium", "high", "max"),
                     "effortArgs": ["--variant", "{effort}"]},
}


def _spec_to_runner(spec, ctx):
    """'KIND:MODEL[@EFFORT]' → (display, cmd, input). `ctx` names the flag for errors.
    An optional @effort suffix sets reasoning effort on the CLIs that take one."""
    kind, _, model = spec.partition(":")
    model, _, effort = model.partition("@")
    t = CLI_RUNNERS.get(kind)
    if not (t and model):
        sys.exit(f"{ctx} wants <{'|'.join(CLI_RUNNERS)}>:<model>[@effort], got {spec!r}")
    cmd = [a.replace("{model}", model) for a in t["cmd"]]
    if effort:
        allowed = t.get("efforts", ())
        if effort not in allowed:
            sys.exit(f"{ctx}: {kind} takes no effort {effort!r}"
                     + (f" (allowed: {', '.join(allowed)})" if allowed
                        else " — its effort is chosen by the model name"))
        extra = [a.replace("{effort}", effort) for a in t["effortArgs"]]
        pos = len(cmd) - 1 if cmd[-1] == "-" else len(cmd)  # codex: before the stdin marker
        cmd[pos:pos] = extra
    return (f"{kind} {model}" + (f" @{effort}" if effort else ""), cmd, t["input"])


def parse_runner_flags(flags):
    """--runner default=claude-cli:claude-opus-4-8@high / --runner 8=codex-cli:gpt-5.5 →
    {key: (display, cmd, input)}. These beat harness.toml; a phase key beats default."""
    out = {}
    for f in flags or []:
        key, _, spec = f.partition("=")
        if "=" not in f or not key:
            sys.exit(f"--runner wants <default|phase-number>=<{'|'.join(CLI_RUNNERS)}>:<model>[@effort], got {f!r}")
        out[key] = _spec_to_runner(spec, "--runner")
    return out


def parse_fallbacks(flags):
    """--fallback opencode-cli:opencode-go/deepseek-v4-flash (repeatable) → ordered
    [(display, cmd, input), ...]. Tried in order when a phase's primary worker DIES —
    crash, exhausted quota, or hang — each resuming from the tome already on disk."""
    return [_spec_to_runner(s, "--fallback") for s in (flags or [])]


def request_runner(build_id, phase_num, dead_name, reason, interactive, report=None):
    """Ask a HUMAN what to do next on a stuck phase and BLOCK until they answer. Two callers:
    a worker DIED with no --fallback left, or a phase EXHAUSTED its gate retries (pass the failing
    validator `report`, which flips this to the gate-failure pause — the Bindery box then also
    offers 'N more retries'). A TTY run prompts on the terminal; a server-launched run hands off
    via .tome-build/<id>.runner-{request,reply}.json, which the Bindery UI bridges (it polls the
    request via /api/buildtome/status and writes the reply via /api/buildtome/runner). Whatever
    they pick resumes the SAME phase from the tome already on disk. Returns
    (runner_or_None, extra_retries): a runner to switch to (None = keep the current model, or give
    up), and how many MORE gate retries to grant (0 for a death)."""
    gate = report is not None
    if interactive:
        if gate:
            print(f"\n  ⚠ phase {phase_num} still fails its gates ({reason}).")
            spec = input("  switch runner KIND:MODEL[@EFFORT] (blank = keep current model): ").strip()
            more = input("  how many MORE retries? (blank/0 = give up): ").strip()
            runner = _spec_to_runner(spec, "runner picker") if spec else None
            return runner, (int(more) if more.isdigit() else 0)
        print(f"\n  ⚠ runner {dead_name} died on phase {phase_num} ({reason}).")
        spec = input("  new runner KIND:MODEL[@EFFORT] (blank = give up): ").strip()
        return (_spec_to_runner(spec, "runner picker") if spec else None), 0
    req = os.path.join(BUILD_DIR, f"{build_id}.runner-request.json")
    reply = os.path.join(BUILD_DIR, f"{build_id}.runner-reply.json")
    with open(req, "w", encoding="utf-8") as f:
        json.dump({"phase": phase_num, "dead": dead_name, "reason": reason,
                   "gate": gate, "report": report or ""}, f)
    print(f"  ⏸ phase {phase_num} " + (f"failed its gates ({reason})" if gate
          else f"lost runner {dead_name} ({reason})") + " — waiting for the Bindery…")
    try:
        while not os.path.exists(reply):
            time.sleep(2)
        with open(reply, encoding="utf-8") as f:
            choice = json.load(f)
    finally:
        for p in (req, reply):
            try:
                os.remove(p)
            except OSError:
                pass
    kind, model, effort = (str(choice.get(k) or "") for k in ("kind", "model", "effort"))
    try:
        extra = max(0, int(choice.get("retries") or 0))
    except (TypeError, ValueError):
        extra = 0
    runner = (_spec_to_runner(f"{kind}:{model}" + (f"@{effort}" if effort else ""), "runner picker")
              if kind and model else None)  # empty runner: keep current model (or, for a death, give up)
    return runner, extra


def runner_for(cfg, phase_num, overrides=None):
    ov = (overrides or {}).get(str(phase_num)) or (overrides or {}).get("default")
    if ov:
        return ov
    name = cfg.get("phases", {}).get(str(phase_num)) or cfg.get("default")
    if not name:  # no browser pick, no --runner, and harness.toml carries no default
        sys.exit(f"no runner for phase {phase_num}: pick a model in the browser, pass "
                 f"--runner {phase_num}=<kind>:<model>, or set a `default` in harness.toml.")
    try:
        r = cfg["runners"][name]
    except KeyError:
        sys.exit(f"harness.toml: no [runners.{name}] defined (phase {phase_num}).")
    return name, list(r["cmd"]), r.get("input", "stdin")


def default_runner(cfg, overrides):
    """The 'default' runner (what a phase with no phase-specific override uses) — reused as
    the implicit fallback when --fallback isn't given. None when harness.toml sets no default
    (the browser-pick workflow), so there's simply nothing to fall back to unattended."""
    ov = (overrides or {}).get("default")
    if ov:
        return ov
    name = cfg.get("default")
    if not name or name not in (cfg.get("runners") or {}):
        return None
    r = cfg["runners"][name]
    return name, list(r["cmd"]), r.get("input", "stdin")


def _implicit_fallback(cfg, overrides, primary):
    """No explicit --fallback: fall back to the 'default' runner, unless there is none (the
    browser-pick workflow) or this phase already IS the default (switching changes nothing)."""
    d = default_runner(cfg, overrides)
    return [] if (d is None or d[1] == primary[1]) else [d]


def section_ids(tid):
    """Ordered section ids from tome.toml [content].sections — the validator's source of truth,
    and (once Phase 2 scaffolds it) the list a split Phase 3 authors one worker at a time."""
    try:
        with open(os.path.join(REPO, "tomes", tid, "tome.toml"), "rb") as f:
            d = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return []
    return [str(s) for s in ((d.get("content") or {}).get("sections") or [])]


def _author_section(chain, ri, prompt, sid, num, cfg, overrides,
                    ping, dead, cap, ask_on_death, interactive, tome_id):
    """Run ONE section's worker with liveness + death recovery (fallback → human ask → implicit
    default), switching runners as needed. Returns (ri, ok) — ri may have grown as the chain did,
    ok is True only if a runner finished cleanly. Mirrors the main loop's death handling but scoped
    to a single section, so split Phase 3 stays isolated from the normal phase loop."""
    while True:
        name, cmd, im = chain[ri]
        rc = run_agent(cmd, im, prompt, ping, dead, cap)
        if rc == 0:
            return ri, True
        reason = "hung/timeout" if rc == 124 else f"exit {rc}"
        print(f"  ! section {sid}: runner {name} exited {rc}" + (" (hung/timeout)" if rc == 124 else ""))
        nxt = chain[ri + 1] if ri + 1 < len(chain) else None
        if nxt is None and (ask_on_death or interactive):
            nxt, _ = request_runner(tome_id, num, name, reason, interactive)
            if nxt is not None:
                chain.append(nxt)
        elif nxt is None:
            imp = _implicit_fallback(cfg, overrides, chain[ri])
            if imp and imp[0][1] not in [c[1] for c in chain]:
                chain.append(imp[0])
                nxt = imp[0]
        if nxt is None:
            return ri, False  # out of options — the post-split whole-tome validation catches the gap
        ri += 1
        print(f"  ⇒ continuing section {sid} on {chain[ri][0]}")


# Which sections Phase 3 has finished, persisted so a resume skips them without re-running a
# worker. Recorded per section on a clean exit; the id is the FINAL tome id, since Phase 3 runs
# after the Phase-2 rename. This is the reliable completion signal — file content can't be trusted
# (authored exercises legitimately contain `# TODO:` fill-in markers, so a placeholder sweep gives
# false "stub" hits). Lesson-level continuation inside the one interrupted section is delegated to
# the worker: it reads what's on disk, keeps the finished lessons, and authors the rest.
def _sections_done_path(tid):
    return os.path.join(BUILD_DIR, f"{tid}.sections-done")


def _load_sections_done(tid):
    try:
        with open(_sections_done_path(tid), encoding="utf-8") as f:
            return set(json.load(f))
    except (OSError, ValueError):
        return set()


def _mark_section_done(tid, sid):
    done = _load_sections_done(tid)
    done.add(sid)
    try:
        with open(_sections_done_path(tid), "w", encoding="utf-8") as f:
            json.dump(sorted(done), f)
    except OSError:
        pass


def author_sections_split(tid, num, title, body, chain, refs, cfg, overrides,
                          ping, dead, cap, ask_on_death, interactive, tome_id, resume=False):
    """Phase 3, split mode: author each section in its OWN fresh worker, so the context (and the
    cache-read tokens that dominated GLM's bill) never accumulate across the whole tome — which
    makes ANY model affordable here. On resume, sections recorded done are skipped and the one that
    was interrupted is finished IN PLACE — its worker keeps the lessons already correct on disk and
    authors only the rest. The workflow's end-of-phase cross-tome reconcile then runs in the caller's
    normal loop. Returns ri after the last section."""
    plan_rel, verdict_rel, findings_rel = refs
    ids = section_ids(tid)
    done = _load_sections_done(tid) if resume else set()
    print(f"  · split-sections: {len(ids)} sections, one worker each — {', '.join(ids)}"
          + (f"  (resume: {len(done)} already done)" if resume and done else ""))
    ri = 0
    for i, sid in enumerate(ids):
        if sid in done:
            print(f"    · section {sid} [{i + 1}/{len(ids)}] already authored — skipping (resume)")
            continue
        prev = (f"Section {ids[i - 1]} is finished on disk — read it so concepts stay strictly "
                f"cumulative and callbacks reach back into it." if i else
                "This is the FIRST section — it opens the course.")
        if resume:  # interrupted (or never-started) section: finish it, keeping what's already correct
            focus = (f"\n\n===== SPLIT RUN — RESUME section {sid} ({i + 1} of {len(ids)}) =====\n"
                     f"A previous run was interrupted mid-build. Open tomes/{tid}/sections/{sid}/ and "
                     f"FINISH section {sid}: KEEP every lesson already fully and correctly authored (do "
                     f"not rewrite, reword, or reorder them — a scaffold-placeholder file counts as NOT "
                     f"authored), and author only what is missing or still a stub — the remaining lessons "
                     f"and their exercises, the section brief, and the freestyle — so the section is "
                     f"complete and coherent. If nothing here has been authored yet, author the whole "
                     f"section. Do NOT create, author, edit, or delete any OTHER section this run. {prev} "
                     f"The [narrative] voice and the Phase 1 arc for this op live in the plan — follow "
                     f"them exactly so {sid} reads as one book with the rest.")
            print(f"    · resuming {sid} [{i + 1}/{len(ids)}] — keep finished lessons, author the rest — on {chain[ri][0]}")
        else:
            focus = (f"\n\n===== SPLIT RUN — author ONLY section {sid} ({i + 1} of {len(ids)}) =====\n"
                     f"Author the COMPLETE section {sid} — its brief, its lessons and their exercises, and "
                     f"its freestyle — into tomes/{tid}/sections/{sid}/. Do NOT create, author, edit, or "
                     f"delete any OTHER section this run. {prev} The [narrative] voice and the Phase 1 arc "
                     f"line for this op live in the plan — follow them exactly so {sid} reads as one book "
                     f"with the rest.")
            print(f"    · authoring {sid} [{i + 1}/{len(ids)}] on {chain[ri][0]}")
        p = build_prompt(tid, num, title, body, plan_rel, verdict_rel, findings_rel) + focus
        ri, ok = _author_section(chain, ri, p, sid, num, cfg, overrides,
                                 ping, dead, cap, ask_on_death, interactive, tome_id)
        if ok:
            _mark_section_done(tid, sid)  # so a future resume skips this finished section
    return ri


def resolve_bin(cmd):
    """Absolute-path cmd[0] so we don't depend on the PARENT's PATH — the web server
    launches us with a bare /usr/local/bin PATH, but agy/claude live in ~/.local/bin.
    Search PATH plus the usual user bindirs; error clearly if the tool isn't installed."""
    exe = cmd[0]
    if os.path.isabs(exe):
        return cmd
    extra = os.pathsep.join([os.path.expanduser("~/.local/bin"), "/usr/local/bin", "/usr/bin"])
    found = shutil.which(exe, path=os.environ.get("PATH", "") + os.pathsep + extra)
    if not found:
        sys.exit(f"runner binary {exe!r} not found on PATH or in ~/.local/bin — is it installed?")
    return [found] + cmd[1:]


# --- worker liveness (Linux /proc). A hung LLM CLI burns ~0 CPU and holds no live socket;
# a worker that's merely THINKING burns ~0 CPU but keeps its connection open — so "alive"
# is (CPU advanced) OR (any established TCP connection), which keeps slow models off death row.
_SS = shutil.which("ss")


def _descendants(root_pid):
    """root_pid and every descendant, walked through /proc ppid links (rebuilt each ping so
    it follows children the worker spawns)."""
    kids = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            with open(f"/proc/{d}/stat") as f:
                fields = f.read().rpartition(")")[2].split()  # everything after the comm ')'
            kids.setdefault(int(fields[1]), []).append(int(d))  # fields[1] = ppid
        except (OSError, ValueError, IndexError):
            continue
    out, stack = [], [root_pid]
    while stack:
        p = stack.pop()
        out.append(p)
        stack.extend(kids.get(p, []))
    return out


def _cpu_ticks(pids):
    """Summed utime+stime (jiffies) across pids — advances while any of them run on-CPU."""
    total = 0
    for pid in pids:
        try:
            with open(f"/proc/{pid}/stat") as f:
                fields = f.read().rpartition(")")[2].split()
            total += int(fields[11]) + int(fields[12])  # utime, stime
        except (OSError, ValueError, IndexError):
            pass
    return total


def _has_live_conn(pids):
    """True if any pid holds an ESTABLISHED TCP connection (the worker is mid-request)."""
    if not _SS:
        return False  # no `ss` → fall back to CPU-only liveness
    try:
        out = subprocess.run([_SS, "-tnpH", "state", "established"],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return bool(set(re.findall(r"pid=(\d+)", out)) & {str(p) for p in pids})


def _kill_subtree(proc):
    """SIGKILL the worker and its descendants (leaves first), then reap the direct child."""
    for pid in reversed(_descendants(proc.pid)):
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def _feed_stdin(proc, prompt):
    try:
        proc.stdin.write(prompt)
        proc.stdin.close()
    except (BrokenPipeError, OSError):
        pass


def run_agent(cmd, input_mode, prompt, ping_interval=PING_INTERVAL_DEFAULT,
              dead_pings=DEAD_PINGS_DEFAULT, hard_cap=None):
    """Invoke a headless agent, streaming its output to the terminal. Returns its exit code —
    or 124 if it goes UNRESPONSIVE: every `ping_interval`s we check the worker's process tree
    for liveness, and after `dead_pings` consecutive idle checks (no CPU AND no live network
    connection) we SIGKILL it, so the caller can switch runners instead of freezing the build.
    `hard_cap` (seconds) is an optional absolute backstop for a worker that spins but never
    progresses; None disables it (liveness handles the common hang)."""
    cmd = resolve_bin(cmd)
    # ponytail: stdout/stderr are inherited (stream straight to the server/terminal, as before);
    # only stdin is piped, fed from a thread so a multi-KB prompt can't block the monitor.
    proc = subprocess.Popen(cmd + ([prompt] if input_mode == "arg" else []), cwd=REPO,
                            stdin=(None if input_mode == "arg" else subprocess.PIPE),
                            text=(input_mode != "arg"))
    if input_mode != "arg":
        threading.Thread(target=_feed_stdin, args=(proc, prompt), daemon=True).start()
    prev = _cpu_ticks(_descendants(proc.pid))
    dead, start = 0, time.monotonic()
    while True:
        try:
            return proc.wait(timeout=ping_interval)   # finished on its own
        except subprocess.TimeoutExpired:
            pass
        if hard_cap and time.monotonic() - start > hard_cap:
            print(f"  ! worker exceeded hard cap {hard_cap}s — killing")
            _kill_subtree(proc)
            return 124
        pids = _descendants(proc.pid)
        now = _cpu_ticks(pids)
        alive = now > prev or _has_live_conn(pids)
        prev = now
        if alive:
            dead = 0
            continue
        dead += 1
        print(f"  · liveness ping {dead}/{dead_pings}: worker idle (no CPU, no live connection)")
        if dead >= dead_pings:
            print(f"  ! worker unresponsive across {dead_pings} pings "
                  f"(~{dead_pings * ping_interval}s) — killing")
            _kill_subtree(proc)
            return 124


def validate(tid, strict=False, tooling=None):
    cmd = [sys.executable, VALIDATOR, f"tomes/{tid}"] + (["--strict"] if strict else [])
    if tooling:
        cmd += ["--tooling", tooling]  # enforce the gate's internal/external/both choice
    p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def inventory(tid):
    """Tome-root-relative file list + top-level array length per TOML — the cross-phase
    no-silent-shrinkage contract. The failure this catches: Phase 6 registers six badges,
    Phase 7 rewrites badges.toml down to one while 'clearing TODOs', and no later gate
    can know what used to exist. Paths are root-relative so a folder rename is invisible.
    # ponytail: top-level arrays only (badges/themes/shop/tiers/lessons/challenge) —
    # count nested ones (lessons.exercises) if erosion ever moves a level down."""
    root = os.path.join(REPO, "tomes", tid)
    files, arrays = set(), {}
    if not os.path.isdir(root):
        return {"files": files, "arrays": arrays}
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d != "save"]  # runtime state, not content
        for n in names:
            p = os.path.join(dirpath, n)
            r = os.path.relpath(p, root).replace(os.sep, "/")
            files.add(r)
            if n.endswith(".toml"):
                try:
                    with open(p, "rb") as f:
                        arrays[r] = {k: len(v) for k, v in tomllib.load(f).items()
                                     if isinstance(v, list)}
                except Exception:
                    pass  # unparseable mid-phase files are the validator's problem
    return {"files": files, "arrays": arrays}


def shrinkage(before, after):
    """What the phase deleted or shrank, as human-readable lines (empty = clean)."""
    probs = [f"file DELETED: {f}" for f in sorted(before["files"] - after["files"])]
    for f, keys in sorted(before["arrays"].items()):
        cur = after["arrays"].get(f)
        if cur is None:
            continue  # deletion already reported above
        for k, n in keys.items():
            if cur.get(k, 0) < n:
                probs.append(f"{f}: [[{k}]] shrank {n} -> {cur.get(k, 0)} entries")
    return probs


def plan_shrink_marks(plan_path):
    """How many `SHRINK OK` justification lines the plan carries — the escape hatch for
    deliberate removals (a new mark during a phase accepts that phase's shrinkage)."""
    try:
        with open(plan_path, encoding="utf-8") as f:
            return f.read().count("SHRINK OK")
    except OSError:
        return 0


def measure(tid):
    """Ground-truth counts from disk: sections/lessons/exercises + bank sizes + economy total.
    Feeds the pre-build forecast (#23) and the post-build plan reconciliation (#11) — the plan
    is prose and 'claims are not evidence', so the harness writes the real numbers itself."""
    root = os.path.join(REPO, "tomes", tid)
    out = {"sections": 0, "lessons": 0, "exercises": 0, "ex_points": 0,
           "fs_reward": 0, "bounty": 0, "badges": 0, "themes": 0, "shop": 0}
    if not os.path.isdir(root):
        return out

    def load(*parts):
        p = os.path.join(root, *parts)
        try:
            with open(p, "rb") as f:
                return tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError):
            return {}

    manifest = load("tome.toml")
    for bank, key in (("themes", "themes"), ("shop", "shop"), ("badges", "badges")):
        data = load(f"{bank}.toml") or manifest
        out[key] = len(data.get(key, []) or [])
    tiers = (load("intrusions.toml").get("tiers")
             or (manifest.get("progression", {}) or {}).get("intrusionTiers") or [])
    out["bounty"] = sum(t.get("bounty", 0) or 0 for t in tiers if isinstance(t, dict))
    sids = (manifest.get("content", {}) or {}).get("sections") or []
    for sid in sids:
        sd = None
        for cand in ((f"sections/{sid}", "section.toml"), (f"sections/{sid}.toml",)):
            d = load(*cand)
            if d:
                sd = d if len(cand) == 1 else d
                break
        # in split layout the section keys + freestyle + lessons live in sibling files;
        # count lessons/exercises/freestyle across whichever files exist
        out["sections"] += 1
        fdir = os.path.join(root, "sections", str(sid))
        fs = load(f"sections/{sid}", "freestyle.toml").get("freestyle") or (sd or {}).get("freestyle") or {}
        out["fs_reward"] += fs.get("reward", 0) or 0
        les_list = []
        ldir = os.path.join(fdir, "lessons")
        if os.path.isdir(ldir):
            for ln in sorted(os.listdir(ldir)):
                les_list += load(f"sections/{sid}", "lessons", ln).get("lessons", []) or []
        else:
            les_list = (sd or {}).get("lessons", []) or []
        out["lessons"] += len(les_list)
        for les in les_list:
            exs = les.get("exercises", []) or []
            out["exercises"] += len(exs)
            out["ex_points"] += sum(e.get("points", 0) or 0 for e in exs if isinstance(e, dict))
    out["base_earnable"] = out["ex_points"] + out["fs_reward"] + out["bounty"]
    return out


def forecast_line(mv):
    """One rough line: content size + a crude token estimate (lessons/exercises are the bulk).
    Deliberately a heuristic, not a promise — it's a 'how big is this getting' gut-check."""
    est_k = round((mv["lessons"] * 1.2 + mv["exercises"] * 0.4) )  # ~KB of TOML, order-of-magnitude
    return (f"{mv['sections']} sections · {mv['lessons']} lessons · {mv['exercises']} exercises "
            f"· base earnable {mv['base_earnable']} · ~{est_k}KB content (rough)")


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


# a runner that can't reach its model prints one of these instead of doing the work.
# agy, when its login has lapsed, prints an auth URL and blocks on a browser OAuth flow;
# catching the marker lets us fail in seconds instead of stalling every phase.
AUTH_MARKERS = ("not logged in", "you are not logged into", "authentication required",
                "please visit", "please log in", "please sign in", "not authenticated",
                "authentication interrupted", "oauth")


def preflight_auth(cmd, input_mode, label=None):
    """One fast ping: prove THIS runner can reach its model/endpoint. Returns (ok, detail)
    instead of exiting, so the caller can check every distinct runner and report them together."""
    cmd = resolve_bin(cmd)
    ping = "Reply with the single word READY and nothing else."
    full = cmd + [ping] if input_mode == "arg" else cmd
    binname = cmd[0].split("/")[-1]
    try:
        proc = subprocess.Popen(
            full, cwd=REPO, text=True,
            stdin=(subprocess.DEVNULL if input_mode == "arg" else subprocess.PIPE),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except OSError as e:
        return False, f"could not launch {cmd[0]!r}: {e}"
    if input_mode != "arg":
        try:
            proc.stdin.write(ping)
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass
    watchdog = threading.Timer(45, proc.kill)  # backstop if it hangs with no output
    watchdog.start()
    out = []
    try:
        for line in proc.stdout:
            out.append(line)
            if any(m in line.lower() for m in AUTH_MARKERS):
                proc.kill()
                break
    finally:
        watchdog.cancel()
    rc = proc.wait()
    text = "".join(out)
    if rc != 0 or any(m in text.lower() for m in AUTH_MARKERS):
        tail = " | ".join(text.strip().splitlines()[-4:]) or "(no output)"
        fix = (f"run `{binname}` in a real terminal and sign in"
               if "agy" in binname else f"authenticate/configure `{binname}`")
        return False, f"{fix} — last output: {tail}"
    return True, "ok"


def preflight_runners(distinct):
    """Ping EVERY distinct endpoint that will drive a phase (not just the first) — the
    drafter/writer/reviewer may be different providers/models, and each must answer before a
    long build starts. Exits with a combined report if any endpoint can't be reached.
    `distinct` is a list of (label, cmd, input_mode)."""
    print(f"  · pre-flight: checking {len(distinct)} selected endpoint(s)…")
    failures = []
    for label, cmd, input_mode in distinct:
        ok, detail = preflight_auth(cmd, input_mode, label)
        print(f"    {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" — {detail}"))
        if not ok:
            failures.append((label, detail))
    if failures:
        lines = "\n".join(f"  · {lbl}: {d}" for lbl, d in failures)
        sys.exit(f"\nPRE-FLIGHT FAILED — {len(failures)} of {len(distinct)} selected endpoint(s) "
                 f"cannot answer (nothing was built):\n{lines}")
    print("  · pre-flight: all selected endpoints answer\n")


PREAMBLE = """You are ONE stage of an automated build harness for an Arcanum coding-tome.
You are running headless. Do this ONE phase completely and correctly, then STOP — do
NOT start other phases; the harness runs those separately.

Context you share with the other phases (all of it lives on disk):
- Tome id: {tid}. Its folder ALREADY EXISTS — the harness scaffolded tomes/{tid}/ after
  Phase 0. Put ALL content THERE; never run new_tome.py or create another tome folder.
- Full authoring reference: TOME-AUTHORING.md — READ the sections THIS phase names below.
- Build plan (the user's gate answers + the arc): {plan}
  READ IT FIRST. Append any durable decision you make (arc, section list, the VOICE) so
  the later phases inherit it — you are not the same agent that runs the next phase.
- The tome files already on disk are the source of truth; earlier phases wrote them.
- The plan is a LOG, not evidence: before you build on a prior phase's claim, verify it
  against the files — phases have claimed work the disk never showed.
- Never duplicate the tome directory, and leave no backups, scratch files, or old-name
  folders under tomes/ — every file outside the layout contract fails validation.
  Folder renames are the HARNESS's job (it derives the id from [runtime] project);
  never mv/cp the tome folder yourself.

After you finish, the harness runs tools/validate_tome.py (from Phase 7 on, in --strict
mode where anti-template/content WARNs fail too); if it reports failures you will be
re-invoked with them, so leave the tome parseable. The harness also compares the file
tree and content counts before/after your phase: deleting files or shrinking arrays an
earlier phase built gets you re-invoked unless the plan gains a `SHRINK OK:` line
explaining why.

===== YOUR PHASE =====
## Phase {num} — {title}

{body}
"""

STUDENT_HOOK = """

===== HARNESS HOOK (phase 8) =====
This phase is the whole point of the harness: do NOT skip the student read-through, and
read EVERY chapter s01..last cover to cover, then fill the gaps you find.

You are ALREADY the clean-context reviewer: the harness runs you as a fresh worker with
no authoring context, so where the workflow says to spawn a clean-context subagent, that
means YOU — do NOT spawn a subagent/child agent to do the reading (it re-reads the whole
tome a second time and doubles this phase's cost for zero information). Read the chapters
yourself, in order. And run `python3 tools/validate_tome.py tomes/{tid} --strict` directly
in your own shell, as often as you like — it is a free local script; its failures are
never counted against you, so there is nothing to gain by testing it in a child.

ONE pass per invocation. The harness owns the review loop (it re-runs this phase and
scopes the next round to your findings) — do NOT run your own second/third/final review
rounds, and do NOT spawn reviewers to re-check your fixes. Read once, fix what you found,
re-run the validator, write the honest verdict, STOP. If gaps remain after your fixes,
that is what GAPS REMAIN + the findings file is for — the harness will send the next
round. A private review loop re-reads the tome four or five times over and burns the
whole usage budget in one phase.

You are also the AUDITOR — the last eyes before shipping, with three duties the
student lens does not cover (a smarter reviewer only does the job it was given, so
here is the whole job):
- INVENTORY: list every file under the tome folder (`find tomes/<id> -type f`) and
  justify each against the layout contract in TOME-AUTHORING.md. A nested folder, a
  backup copy, or a scratch file is a FAIL, not a shrug.
- CLAIMS vs DISK: reread the build plan and verify every claim in it against the
  files. A phase that wrote "registered the 6 badges" must have six [[badges]] on
  disk right now. Claims are not evidence.
- ENGINE CONTRACTS: the badge bank defines every engine-granted id; shop theme items
  point at real [[themes]]; attack starters run as given. The META files — badges,
  themes, shop, intrusions, attacks — are content too: read them in the tome's voice,
  not just the chapters.

When done, write your verdict to the file {verdict} — exactly one line:
  PASS          if a first-time student, having read every chapter, could now sit down
                with the REAL tools and a REAL target and do what meta.description
                promises, unaided.
  GAPS REMAIN   otherwise.
The harness re-runs this phase until you write PASS (up to a few times), so only write
PASS when it is genuinely true.

If (and only if) the verdict is GAPS REMAIN, ALSO write {findings} as a JSON array of the
blocking findings, most-severe first — so the next review pass can go straight to them
instead of re-reading all 46 files:
  [{{"file": "tomes/<id>/sections/s05/lessons/l04.toml", "issue": "recursion never taught before the lab", "severity": "blocking"}}, …]
Use "file": null for a whole-tome finding. Keep it to the real blockers you just fixed or
still need fixed. On PASS, do not write this file (or write []).
"""


def build_prompt(tid, num, title, body, plan_rel, verdict_rel, findings_rel=None, focus=None):
    p = PREAMBLE.format(tid=tid, num=num, title=title, body=body, plan=plan_rel)
    if num == 8:
        p += STUDENT_HOOK.format(tid=tid, verdict=verdict_rel, findings=findings_rel)
        if focus:
            p += ("\n\n===== FOCUS THIS PASS (from the previous review's findings) =====\n"
                  "A prior pass already read the whole tome and flagged the items below. Fix "
                  "THESE first and re-verify the chapters they touch — you need not re-read every "
                  "chapter from scratch this round:\n" + focus)
    return p


def read_findings(path):
    """The reviewer's structured GAPS-REMAIN findings, as a short focus block (or None)."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            items = json.load(f)
        os.remove(path)  # consume it; the next round writes fresh
    except (OSError, json.JSONDecodeError):
        return None
    lines = [f"- [{it.get('severity', '?')}] {it.get('file') or '(whole tome)'}: {it.get('issue', '')}"
             for it in items if isinstance(it, dict)]
    return "\n".join(lines) if lines else None


GATE_QS = [
    ("Prior knowledge", "What can the student already do? (languages / tools they know)"),
    ("Breadth (1-10)", "How much of the topic's surface? 1 = one tight path to the objective, 10 = the whole territory"),
    ("Lesson depth (1-10)", "How deep does each lesson dig? 1 = just use it, 10 = internals and edge cases"),
    ("Mastery (1-5)", "Where must the student stand after the last chapter? 1 = acquainted, 5 = expert"),
    ("Tooling", "internal (in-browser only), external (teach real tools), or both?"),
]

# How the three dials steer the arc — written into the plan so every phase reads the same
# semantics instead of re-interpreting three bare numbers.
DIALS_NOTE = """\
- **Breadth** shapes the SECTION LIST: how much of the topic's surface appears. 1 = the
  single tight path to the objective; 10 = the whole territory, side-paths included.
- **Lesson depth** shapes EACH LESSON: how far under the surface it digs. 1 = use the
  thing; 10 = internals, edge cases, why it works.
- **Mastery** (see Mastery target below) fixes the ENDPOINT — where the student stands
  after the final chapter. Breadth and depth spend the pages; mastery decides where the
  pages must ARRIVE. Material the student already has (see Prior knowledge) gets AT MOST
  one brief recap section, no matter how high breadth is.
- The concept is casual prose; these dials are the user's CALIBRATED intent. Where the
  two disagree (e.g. the concept says "from beginner" but prior knowledge + mastery say
  otherwise), THE DIALS WIN. Take the concept for topic and flavor, the dials for shape.
"""

# The mastery tick expanded into concrete sample end-state objectives — a cheap model
# can't misread an example the way it can misread an adjective. Written into the plan.
MASTERY_LEVELS = {
    1: ("ACQUAINTED", "The student ends able to READ and follow the topic, not yet work "
        "alone: explain the core ideas, run and modify provided examples, finish guided "
        "exercises. Sample end-state objectives: edit a provided script to change its "
        "behavior; explain what a given loop or lookup does; spot the obvious bug in five lines."),
    2: ("FUNCTIONAL", "Ends able to do the everyday basics unaided: build small things "
        "from scratch with the core constructs, read error messages, fix simple faults. "
        "Samples: write a small program that reads input and prints a computed result; "
        "use the basic collection types correctly; trace why a branch did or didn't run."),
    3: ("CAPABLE", "Ends able to solve real problems alone and CHOOSE between approaches. "
        "Samples: implement recursion where iteration hurts; pick a map over an array (or "
        "the reverse) and justify the tradeoff; decompose a fuzzy problem into functions; "
        "treat error handling as a design decision, not an afterthought."),
    4: ("ADVANCED", "Ends fluent in the topic's idioms and the internals that matter. "
        "Samples: wield the topic's power tools (e.g. generators/iterators, decorators/"
        "closures in a programming course); reason about complexity and performance; "
        "structure a multi-part project; read unfamiliar source to answer what the docs don't."),
    5: ("EXPERT", "Ends at the deep end: the machinery under the surface and the judgment "
        "to wield it. Samples: metaprogramming or the topic's equivalent under-the-hood "
        "layer; performance/memory models; concurrency where applicable; architect a "
        "substantial tool end to end and defend its design."),
}
MASTERY_CODA = """
These samples CALIBRATE the endpoint — they are not a syllabus. Translate them into THIS
course's topic, and spend the chapter budget so the FINAL chapters sit AT this level.

Adapt the samples to this topic's OWN difficulty landscape, not to generic computer
science. Before writing the section list:
1. Name, in the plan, the 3-6 concepts practitioners of THIS language/tool actually
   find hard and idiomatic at the target level — its REAL difficulty spine.
2. Build the advanced chapters toward THAT list. Where a sample above names a concept
   that is rare or unidiomatic here, swap it for this topic's equal-difficulty
   counterpart instead of teaching it anyway.
Calibration contrasts: nearly every language HAS recursion, but a Python course at
level 3 leans on iterators, comprehensions and dict-shaped design (recursion earns a
lesson, not a chapter), while a Lisp or Haskell course inverts that ratio; JavaScript's
hard spine is async/the event loop/closures; Rust's is ownership and borrowing; C's is
pointers and memory; SQL's is joins, aggregation and window functions. Weight the
course toward what is hard AND used HERE."""

# The gate's Tooling choice expanded into the rules the author-AI must honor — written
# into the plan (which every phase reads) so it steers all phases. The validator enforces
# the mechanical half (see validate_tome.py --tooling); this is the rest, via the prompt.
TOOLING_POLICY = {
    "internal": ("INTERNAL (in-browser only)",
        "Every workbench is the built-in browser editor — do NOT set `externalWorkspace`. The "
        "course must need NO external download or install: never tell the student to fetch, "
        "install, or run an external program, IDE, or toolchain, and never assume one is present. "
        "(They may still opt into their own editor via USE MY OWN EDITOR, but write the course as "
        "if in-browser.) Every lab runs in the engine's own runtime."),
    "external": ("EXTERNAL (teach the real tools)",
        "The course MUST teach how to install and use the real external tools the topic needs — "
        "name them in section 1 with `[[lessons.readings]]` links (mark mandatory/optional). Where "
        "the real toolchain cannot run in the browser, set `externalWorkspace = true` (§5) and make "
        "the workbenches external; an in-browser workbench is fine only where genuinely applicable. "
        "Never simulate away the real skill."),
    "both": ("BOTH (internal + external available)",
        "Both in-browser and real external tools must be available to the student. Teach the real "
        "external tools — name them in section 1 with `[[lessons.readings]]` links. Workbenches may "
        "be internal or external per topic: set `externalWorkspace = true` only where the real "
        "toolchain needs it; otherwise keep the in-browser workbench while STILL teaching the "
        "external tools."),
}


def read_tooling(plan_path):
    """The Tooling gate answer (internal|external|both) from the plan, or None — the
    single source of truth the harness passes to the validator on every phase, resume
    included (the plan always exists once Phase 0 has run)."""
    try:
        txt = open(plan_path, encoding="utf-8").read()
    except OSError:
        return None
    m = re.search(r"(?im)^- \*\*Tooling:\*\*\s*(\w+)", txt)
    v = m.group(1).lower() if m else None
    return v if v in ("internal", "external", "both") else None


def write_plan(plan_path, tid, answers, concept=None):
    """Write the Phase-0 plan file — the one format both gate paths share."""
    with open(plan_path, "w", encoding="utf-8") as f:
        f.write(f"# BUILD PLAN — {tid}\n\n")
        if concept:
            f.write("## Concept\n" + concept.strip() + "\n\n")
        f.write("## Gate answers (Phase 0)\n")
        for k, v in answers:
            if v:   # an unanswered dial is omitted, not written as an empty line
                f.write(f"- **{k}:** {v}\n")
        if any(v for k, v in answers if k.startswith(("Breadth", "Lesson depth", "Mastery"))):
            f.write("\n## Course dials — how to read them\n" + DIALS_NOTE)
        m = next((v for k, v in answers if k.startswith("Mastery")), "")
        try:
            lvl = MASTERY_LEVELS.get(int(str(m).strip()))
        except (ValueError, TypeError):
            lvl = None
        if lvl:
            f.write(f"\n## Mastery target — {str(m).strip()}/5: {lvl[0]}\n{lvl[1]}{MASTERY_CODA}\n")
        pol = TOOLING_POLICY.get(next((v.lower() for k, v in answers if k == "Tooling"), ""))
        if pol:
            f.write(f"\n## Tooling policy — {pol[0]}\n{pol[1]}\n")
        f.write("\n## Arc (Phase 1 fills this in, later phases read it)\n")


def do_gate(plan_path, tid, concept=None):
    """Phase 0 is interactive by design — the harness asks the user, no agent involved."""
    print("\n=== Phase 0 — GATE: three questions (the harness asks YOU) ===")
    ans = [(k, input(f"  {q}\n  > ").strip()) for k, q in GATE_QS]
    write_plan(plan_path, tid, ans, concept)
    print(f"  -> wrote {plan_path}\n")


def do_gate_json(plan_path, tid, gate_json, concept=None):
    """Phase 0 without a terminal (web-launched): the gate answers arrive as JSON."""
    try:
        g = json.loads(gate_json)
    except json.JSONDecodeError as e:
        sys.exit(f"--gate-json is not valid JSON: {e}")
    ans = [(label, str(g.get(key, "")).strip()) for (label, _), key in
           zip(GATE_QS, ("prior_knowledge", "breadth", "depth", "mastery", "tooling"))]
    write_plan(plan_path, tid, ans, concept)
    print(f"=== Phase 0 — GATE: answers taken from --gate-json ===\n  -> wrote {plan_path}\n")


def read_verdict(path):
    if not os.path.exists(path):
        return None
    v = open(path, encoding="utf-8").read().strip().upper()
    os.remove(path)  # consume it so the next loop reads a fresh write
    return "PASS" if "PASS" in v.split() else "GAPS REMAIN"


def _selftest():
    """Runnable check for the fallback/chain logic — `python3 tools/build_tome.py --selftest`."""
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
