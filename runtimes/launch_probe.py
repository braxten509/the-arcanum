"""Harness-owned cold-start observation for a reconstructed learner project."""
import re
import subprocess

from . import common


ORDINARY_LAUNCH_SMOKE_TIMEOUT = 4
_FATAL_OUTPUT = re.compile(
    r"Traceback \(most recent call last\):|Unhandled exception|Exception in thread|"
    r"thread ['\"][^'\"]+['\"] panicked at|\bpanic:|Segmentation fault|\bfatal error\b", re.I)


def smoke_project(runtime, project_dir, stdin_text=None, env=None, timeout=None):
    """Cold-start the real entrypoint without proof/acceptance arguments.

    A normal zero exit is clean. An interactive, graphical, or server program that
    remains alive for the bounded observation window is also clean and is killed by the
    harness afterward. A nonzero early exit is a real learner-facing launch failure.
    Leaving stdin open when no fixture is declared lets ordinary interactive programs
    wait for a learner instead of crashing on artificial EOF.
    """
    timeout = ORDINARY_LAUNCH_SMOKE_TIMEOUT if timeout is None else max(1, int(timeout))
    if not runtime.available():
        return {"ok": False, "output": f"ERROR: {runtime._exe() or runtime.NAME} not found.",
                "command": [], "outcome": "not-started"}
    try:
        command = runtime.project_command(project_dir)
    except ValueError as exc:
        return {"ok": False, "output": str(exc), "command": [], "outcome": "not-started"}
    try:
        with common.project_lock:
            process = subprocess.Popen(
                command, cwd=project_dir, env=env, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                start_new_session=True)
            common.CURRENT["proc"] = process
            if stdin_text is not None:
                try:
                    process.stdin.write(stdin_text)
                    process.stdin.close()
                    process.stdin = None
                except (BrokenPipeError, OSError):
                    pass
            try:
                process.wait(timeout=timeout)
                outcome = "exited"
            except subprocess.TimeoutExpired:
                outcome = "survived"
                common.kill_run(process)
            try:
                stdout, stderr = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                common.kill_run(process)
                stdout, stderr = process.communicate()
            finally:
                common.CURRENT["proc"] = None
        output = common.join_output(stdout, stderr) or "(no output)"
        if outcome == "survived":
            if _FATAL_OUTPUT.search(output):
                return {"ok": False, "output": output, "exit": None,
                        "command": command, "outcome": "fatal-output",
                        "observedSeconds": timeout}
            return {"ok": True, "output": output, "exit": None,
                    "command": command, "outcome": outcome, "observedSeconds": timeout}
        return {"ok": process.returncode == 0, "output": output,
                "exit": process.returncode, "command": command,
                "outcome": outcome, "observedSeconds": 0}
    except OSError as exc:
        common.CURRENT["proc"] = None
        return {"ok": False, "output": f"(ordinary launch failed to start: {exc})",
                "command": command, "outcome": "not-started"}
