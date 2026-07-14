"""Headless worker execution with hang detection, plus the endpoint auth preflight.
Liveness reads Linux /proc: a hung LLM CLI burns ~0 CPU and holds no live socket;
a worker that's merely THINKING burns ~0 CPU but keeps its connection open — so "alive"
is (CPU advanced) OR (any established TCP connection), which keeps slow models off death row."""
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time

from . import DEAD_PINGS_DEFAULT, PING_INTERVAL_DEFAULT, REPO

_SS = shutil.which("ss")


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
              dead_pings=DEAD_PINGS_DEFAULT, hard_cap=None, cwd=None, env=None):
    """Invoke a headless agent, streaming its output to the terminal. Returns its exit code —
    or 124 if it goes UNRESPONSIVE: every `ping_interval`s we check the worker's process tree
    for liveness, and after `dead_pings` consecutive idle checks (no CPU AND no live network
    connection) we SIGKILL it, so the caller can switch runners instead of freezing the build.
    `hard_cap` (seconds) is an optional absolute backstop for a worker that spins but never
    progresses; None disables it (liveness handles the common hang)."""
    cmd = resolve_bin(cmd)
    # ponytail: stdout/stderr are inherited (stream straight to the server/terminal, as before);
    # only stdin is piped, fed from a thread so a multi-KB prompt can't block the monitor.
    proc = subprocess.Popen(cmd + ([prompt] if input_mode == "arg" else []), cwd=cwd or REPO,
                            env=env,
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


def preflight_runners(distinct, fatal=True):
    """Ping EVERY distinct endpoint that will drive a phase (not just the first) — the
    drafter/writer/reviewer may be different providers/models, and each must answer before a
    long build starts. Exits with a combined report if any endpoint can't be reached.
    `distinct` is a list of (label, cmd, input_mode)."""
    print(f"  · AI access Phase 0: checking {len(distinct)} selected endpoint(s)…")
    failures = []
    for label, cmd, input_mode in distinct:
        ok, detail = preflight_auth(cmd, input_mode, label)
        print(f"    {'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" — {detail}"))
        if not ok:
            failures.append((label, detail))
    if failures and fatal:
        lines = "\n".join(f"  · {lbl}: {d}" for lbl, d in failures)
        sys.exit(f"\nAI ACCESS PHASE 0 FAILED — {len(failures)} of {len(distinct)} selected endpoint(s) "
                 f"cannot answer (nothing was built):\n{lines}")
    if failures:
        return False
    print("  · AI access Phase 0: all selected endpoints answer\n")
    return True


def preflight_recovery_runner(name, original_cmd, scoped_cmd, input_mode, preflighted):
    """Probe a just-in-time fallback; an unavailable recovery hand is skipped, not fatal."""
    key = tuple(original_cmd)
    if key in preflighted:
        return True
    if not preflight_runners([(name, scoped_cmd, input_mode)], fatal=False):
        return False
    preflighted.add(key)
    return True
