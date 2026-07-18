#!/usr/bin/env python3
import sys as _command_sys
from pathlib import Path as _CommandPath
_COMMAND_REPO = _CommandPath(__file__).resolve().parents[3]
_command_sys.path[:0] = [str(_COMMAND_REPO), str(_COMMAND_REPO / "tools")]

"""Run brief blind reviews over the frozen real HollowCrawl Phase 8 failure."""
import argparse
import concurrent.futures
import datetime as dt
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO = str(_COMMAND_REPO)
sys.path.insert(0, REPO)

from arcanum.platform.agent_commands import scoped_runner_command  # noqa: E402
from tools.buildlib.runtime.runners import _spec_to_runner  # noqa: E402
from tools.model_triallib.hollowcrawl_audit import (  # noqa: E402
    AUDIT_MODELS, baseline_hashes, create_workspace, grade_workspace, immutable_paths)
from tools.model_triallib.commands.run_model_role_trials import (  # noqa: E402
    _budget_command, _reported_usage, _slug)


def _validation_bin():
    roots = sorted((Path(REPO) / ".tome-build" / "validation-envs").glob("*/bin"),
                   key=lambda path: path.stat().st_mtime, reverse=True)
    for root in roots:
        try:
            proc = subprocess.run([str(root / "python"), "-c", "import pygame"],
                                  capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode == 0:
            return root
    raise RuntimeError("no cached HollowCrawl validation environment with pygame is available")


def _run_process(command, input_mode, prompt, cwd, timeout, runtime_bin):
    full = command + ([prompt] if input_mode == "arg" else [])
    env = dict(os.environ)
    env.update(PYTHONDONTWRITEBYTECODE="1", SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    env["PATH"] = str(runtime_bin) + os.pathsep + env.get("PATH", "")
    started = time.monotonic()
    proc = subprocess.Popen(
        full, cwd=cwd, env=env, stdin=(None if input_mode == "arg" else subprocess.PIPE),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        output, _ = proc.communicate(None if input_mode == "arg" else prompt, timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        output, _ = proc.communicate()
    return proc.returncode, timed_out, round(time.monotonic() - started, 2), output


def run_one(model, run_root, timeout, runtime_bin):
    model_id, spec = model["id"], model["spec"]
    workspace = run_root / _slug(model_id)
    immutable = create_workspace(workspace)
    baseline = baseline_hashes(immutable)
    display, command, input_mode = _spec_to_runner(spec, f"HollowCrawl review {model_id}")
    command = _budget_command(spec, command)
    command = scoped_runner_command(display, command, str(workspace),
                                    [str(workspace / "review.json")], REPO)
    prompt = (workspace / "TASK.md").read_text(encoding="utf-8")
    print(f"START {model_id}", flush=True)
    infrastructure_error = None
    try:
        rc, timed_out, elapsed, output = _run_process(
            command, input_mode, prompt, str(workspace), timeout, runtime_bin)
        if re.search(r"not logged in|authentication required|please (?:log|sign) in", output, re.I):
            infrastructure_error = "provider authentication failed"
    except (OSError, RuntimeError) as exc:
        rc, timed_out, elapsed, output = 125, False, 0, ""
        infrastructure_error = f"{type(exc).__name__}: {exc}"
    (workspace / "agent-output.log").write_text(output, encoding="utf-8")
    grade = grade_workspace(workspace, baseline)
    result = {
        "model": model_id, "spec": spec, "comparison": bool(model.get("comparison")),
        "exitCode": rc, "timedOut": timed_out, "elapsedSeconds": elapsed,
        "reportedUsage": _reported_usage(output), "infrastructureError": infrastructure_error,
        "grade": grade, "passed": not infrastructure_error and grade["passed"],
        "workspace": os.path.relpath(workspace, REPO),
    }
    label = "PASS" if result["passed"] else f"FAIL ({len(grade['criticalFailures'])} critical)"
    print(f"DONE  {model_id}: {label}; {grade['score']}/{grade['maximum']}; {elapsed:.1f}s",
          flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", help="comma-separated audit ids (default: all)")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--regrade", help="regrade an existing results.json without model calls")
    args = parser.parse_args()
    if args.regrade:
        report = Path(args.regrade).resolve()
        payload = json.loads(report.read_text(encoding="utf-8"))
        for result in payload.get("results", []):
            workspace = Path(REPO) / result["workspace"]
            grade = grade_workspace(workspace, baseline_hashes(immutable_paths(workspace)))
            result["grade"] = grade
            result["passed"] = not result.get("infrastructureError") and grade["passed"]
            label = "PASS" if result["passed"] else f"FAIL ({len(grade['criticalFailures'])} critical)"
            print(f"REGRADE {result['model']}: {label}; {grade['score']}/{grade['maximum']}")
        payload["regradedAt"] = dt.datetime.now().isoformat(timespec="seconds")
        report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0 if all(item.get("passed") for item in payload.get("results", [])) else 1
    selected = list(AUDIT_MODELS)
    if args.models:
        wanted = {item.strip() for item in args.models.split(",") if item.strip()}
        selected = [item for item in selected if item["id"] in wanted]
        missing = wanted - {item["id"] for item in selected}
        if missing:
            parser.error("unknown model trial(s): " + ", ".join(sorted(missing)))
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}"
    run_root = Path(REPO) / ".tome-build" / "hollowcrawl-review-trials" / stamp
    run_root.mkdir(parents=True, exist_ok=True)
    runtime_bin = _validation_bin()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = [pool.submit(run_one, model, run_root, max(30, args.timeout), runtime_bin)
                   for model in selected]
        results = [future.result() for future in futures]
    payload = {"version": 1, "case": "hollowcrawl-phase8-false-pass",
               "run": stamp, "results": results}
    report = run_root / "results.json"
    report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"REPORT {os.path.relpath(report, REPO)}", flush=True)
    return 0 if all(item["passed"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
