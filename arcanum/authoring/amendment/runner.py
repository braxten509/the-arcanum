"""One streamed, bounded Binder provider turn."""
from __future__ import annotations

import signal
import subprocess
import threading
import time

from ...ai.economics import estimate_api_equivalent_cost
from ...ai.events import error_text, usage_from_line
from ...forge import ANSI_RE
from ...jobs.stall import StallWatch
from ..amendment.activity import activity_rows


def _append_activity(job_manager, job_id, row, seen):
    key = (row.get("kind"), row.get("text"))
    if not key[1] or key == seen.get("last"):
        return
    seen["last"] = key
    job_manager.append(job_id, "activity", row, limit=200)


def activity_summary(job_manager, job_id, fallback=""):
    messages = [
        str(row.get("text") or "").strip()
        for row in job_manager.status(job_id).get("activity", [])
        if isinstance(row, dict) and row.get("kind") == "assistant"
    ]
    return (messages[-1] if messages else fallback).strip()


def failure_summary(logtail):
    errors = [error_text(line).strip() for line in logtail]
    return next(
        (message for message in reversed(errors) if message),
        "the AI exited without a structured error message")


def _merge_usage(job_manager, job_id, provider_kind, provider_model,
                 turn_usage):
    if provider_kind not in {"codex-cli", "claude-cli"} or not turn_usage:
        return
    status = job_manager.status(job_id)
    combined = dict(status.get("usage") or {})
    for key, value in turn_usage.items():
        if isinstance(value, (int, float)):
            combined[key] = int(combined.get(key) or 0) + int(value)
    estimate = estimate_api_equivalent_cost(provider_model, combined)
    fields = {"usage": combined}
    if estimate:
        fields["apiCostEstimate"] = {
            **estimate,
            "provider": provider_kind,
            "actualCharge": False,
        }
    job_manager.update(job_id, **fields)


def run_agent_turn(job_id, cmd, prompt, input_mode, env, cwd, provider_kind,
                   provider_model, job_manager, processes, *, timeout, stall):
    """Run one scoped turn, retaining diagnostics and a quiet transcript.

    ``stall`` is the real bound and ``timeout`` only a far-off backstop. A wall clock
    cannot tell a long job from a wedged one, so it kills both, and a whole-tome
    remediation is exactly the job it kills -- mid-edit, with the work discarded.
    StallWatch instead kills a tree that is provably doing nothing: no CPU consumed,
    no connection to the provider, no output. A Binder still working never looks idle,
    so it is never killed for taking the time the work actually needs.
    """
    stdin_data = prompt if input_mode == "stdin" else None
    full_cmd = cmd + ([prompt] if input_mode == "arg" else [])
    process = subprocess.Popen(
        full_cmd,
        stdin=(subprocess.DEVNULL if stdin_data is None else subprocess.PIPE),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
        cwd=cwd,
        start_new_session=True)
    processes.put(job_id, process)
    if stdin_data is not None:
        try:
            process.stdin.write(stdin_data)
            process.stdin.close()
        except BrokenPipeError:
            pass

    timed_out = {"value": False}
    watch = StallWatch(process.pid, stall)
    finished = threading.Event()

    def kill_timeout():
        timed_out["value"] = True
        processes.terminate(job_id, signal.SIGKILL)

    def watchdog():
        deadline = time.monotonic() + float(timeout)
        while not finished.wait(2.0):
            if watch.wedged() or time.monotonic() >= deadline:
                kill_timeout()
                return

    monitor = threading.Thread(target=watchdog, daemon=True)
    monitor.start()
    seen_activity = {}
    turn_usage = {}

    def pump_output():
        nonlocal turn_usage
        for line in process.stdout:
            line = ANSI_RE.sub("", line.rstrip("\n"))
            watch.poke()  # output is proof of life even when CPU and sockets are quiet
            try:
                job_manager.append(job_id, "log", line, limit=400)
                for row in activity_rows(provider_kind, line):
                    _append_activity(
                        job_manager, job_id, row, seen_activity)
                reported = usage_from_line(line)
                if reported:
                    turn_usage = reported
            except KeyError:
                break

    pump = threading.Thread(target=pump_output, daemon=True)
    pump.start()
    try:
        return_code = process.wait()
        pump.join(15)
        if pump.is_alive():
            processes.terminate_process(process, signal.SIGKILL)
            pump.join(5)
    finally:
        finished.set()
        processes.pop(job_id)
    _merge_usage(
        job_manager, job_id, provider_kind, provider_model, turn_usage)
    logtail = list(job_manager.status(job_id).get("log", []))
    return return_code, timed_out["value"], logtail
