"""Shared low-level helpers for language runtimes: safe writes, output clipping,
process-group kill, run locks, the single in-flight run registry used by
/api/runcancel, and the cancellable project runner every runtime shares."""
import os
import signal
import subprocess
import threading

# one heavy compile/run at a time — matches the original single-user semantics
project_lock = threading.Lock()   # guards a tome's workspace project
snippet_lock = threading.Lock()   # guards a runtime's scratch project

# the in-flight `run project` process, so /api/runcancel can kill it
CURRENT = {"proc": None}

# snippet EXECUTION cap (trials, hexes, duels — no cancel button there, so an
# accidental infinite loop must die fast). Compile/build time is budgeted separately.
SNIPPET_TIMEOUT = 10


def atomic_write(path, data):
    """Power-outage-safe write: tmp file + fsync + rename."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def clip(s, n=100_000):
    """Cap runaway program output — a tight print loop can emit hundreds of MB."""
    s = s or ""
    return ("(…output truncated — your program printed a LOT…)\n" + s[-n:]) if len(s) > n else s


def kill_run(p):
    """Kill the whole process group: a run spawns the student's program as a child
    that would otherwise survive and keep the output pipes (and a CPU core) hostage."""
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass


def cancel_current():
    """Kill the in-flight project run, if any. Returns True if something was killed."""
    p = CURRENT.get("proc")
    if p and p.poll() is None:
        kill_run(p)
        return True
    return False


def safe_join(base, rel):
    """Resolve a project-relative path, refusing escapes outside `base`."""
    rel = rel.replace("\\", "/").lstrip("/")
    full = os.path.realpath(os.path.join(base, rel))
    root = os.path.realpath(base)
    if not full.startswith(root + os.sep) and full != root:
        raise ValueError("path escapes project")
    return full


def join_output(stdout, stderr):
    """Program output as the UI shows it: stdout, then stderr if any, both clipped."""
    return (clip(stdout) + ("\n" + clip(stderr) if (stderr or "").strip() else "")).strip()


def run_cancellable(argv, stdin_text, timeout, cwd=None):
    """Run a student project: cancellable via /api/runcancel, process-group killed on
    timeout, output clipped. The one runner every runtime's run_project delegates to."""
    try:
        with project_lock:
            p = subprocess.Popen(argv, cwd=cwd,
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, start_new_session=True)
            CURRENT["proc"] = p
            try:
                out_s, err_s = p.communicate(input=stdin_text or "", timeout=timeout)
            except subprocess.TimeoutExpired:
                kill_run(p)
                out_s, _ = p.communicate()
                return {"ok": False, "output": clip(out_s) +
                        f"\n(KILLED: exceeded {timeout}s — waiting for input? Provide stdin in the STDIN box.)"}
            finally:
                CURRENT["proc"] = None
        out = join_output(out_s, err_s)
        if p.returncode and p.returncode < 0:
            return {"ok": False, "output": (out + "\n(CANCELLED by operator)").strip(), "exit": p.returncode}
        return {"ok": p.returncode == 0, "output": out or "(no output)", "exit": p.returncode}
    except OSError as e:
        return {"ok": False, "output": f"(run failed to start: {e})"}
