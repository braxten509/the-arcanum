#!/usr/bin/env python3
import sys as _command_sys
from pathlib import Path as _CommandPath
_COMMAND_REPO = _CommandPath(__file__).resolve().parents[3]
_command_sys.path[:0] = [str(_COMMAND_REPO), str(_COMMAND_REPO / "tools")]

"""Run compact, real agent-editing trials for every model used by quality tiers 1–5."""
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
from tools.model_triallib.fixtures import TRIAL_MODELS, create_workspace  # noqa: E402
from tools.model_triallib.grading import baseline_hashes, grade_workspace  # noqa: E402


def _slug(value):
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _budget_command(spec, command):
    command = list(command)
    if spec.startswith("claude-cli:"):
        command += ["--safe-mode", "--disable-slash-commands", "--no-chrome",
                    "--prompt-suggestions", "false", "--strict-mcp-config",
                    "--mcp-config", '{"mcpServers":{}}',
                    "--max-budget-usd", "0.40", "--output-format", "json",
                    "--no-session-persistence"]
    elif spec.startswith("codex-cli:"):
        command.insert(len(command) - 1, "--json")
        command.insert(len(command) - 1, "--color")
        command.insert(len(command) - 1, "never")
    elif spec.startswith("opencode-cli:"):
        command += ["--format", "json", "--pure"]
    return command


def _numbers(value, found):
    if isinstance(value, dict):
        normalized = {re.sub(r"[^a-z]", "", str(key).lower()): item
                      for key, item in value.items()}
        aliases = {"inputtokens": "input", "inputtoken": "input",
                   "outputtokens": "output", "outputtoken": "output",
                   "cachereadinputtokens": "cacheRead", "cachereadtokens": "cacheRead"}
        for key, label in aliases.items():
            item = normalized.get(key)
            if isinstance(item, int) and not isinstance(item, bool):
                found[label] = max(found.get(label, 0), item)
        if isinstance(normalized.get("input"), int) and isinstance(normalized.get("output"), int):
            for key, label in (("input", "input"), ("output", "output"),
                               ("reasoning", "reasoning"), ("total", "total")):
                item = normalized.get(key)
                if isinstance(item, int) and not isinstance(item, bool):
                    found[label] = max(found.get(label, 0), item)
            cache = normalized.get("cache")
            if isinstance(cache, dict) and isinstance(cache.get("read"), int):
                found["cacheRead"] = max(found.get("cacheRead", 0), cache["read"])
        for item in value.values():
            _numbers(item, found)
    elif isinstance(value, list):
        for item in value:
            _numbers(item, found)


def _reported_usage(output):
    found = {}
    candidates = [output]
    candidates.extend(line for line in output.splitlines() if line.lstrip().startswith("{"))
    for text in candidates:
        try:
            _numbers(json.loads(text), found)
        except (TypeError, ValueError):
            continue
    return found


def _run_process(command, input_mode, prompt, cwd, timeout):
    full = command + ([prompt] if input_mode == "arg" else [])
    started = time.monotonic()
    proc = subprocess.Popen(
        full, cwd=cwd, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        stdin=(None if input_mode == "arg" else subprocess.PIPE),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        start_new_session=True)
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


def run_one(model, run_root, timeout):
    model_id, roles, spec = model["id"], tuple(model["roles"]), model["spec"]
    workspace = run_root / _slug(model_id)
    immutable = create_workspace(workspace, roles)
    baseline = baseline_hashes(immutable)
    display, command, input_mode = _spec_to_runner(spec, f"model role trial {model_id}")
    command = _budget_command(spec, command)
    command = scoped_runner_command(display, command, str(workspace), [str(workspace)], REPO)
    prompt = (workspace / "TASK.md").read_text(encoding="utf-8")
    print(f"START {model_id}: {', '.join(roles)}", flush=True)
    try:
        rc, timed_out, elapsed, output = _run_process(
            command, input_mode, prompt, str(workspace), timeout)
        budget_exceeded = "error_max_budget_usd" in output
        if re.search(r"not logged in|authentication required|please (?:log|sign) in", output, re.I):
            infrastructure_error = "provider authentication failed"
        else:
            infrastructure_error = None
    except (OSError, RuntimeError) as exc:
        rc, timed_out, elapsed, output = 125, False, 0, ""
        budget_exceeded = False
        infrastructure_error = f"{type(exc).__name__}: {exc}"
    (workspace / "agent-output.log").write_text(output, encoding="utf-8")
    grades = grade_workspace(workspace, roles, baseline)
    artifact_pass = all(item["passed"] for item in grades.values())
    # Claude can cross the cap while returning an end_turn after every required
    # artifact is already complete. Preserve that efficiency signal without
    # misreporting a deterministically green role result as infrastructure loss.
    if budget_exceeded and not artifact_pass:
        infrastructure_error = "test budget cap exhausted before passing the role gates"
    result = {
        "model": model_id, "spec": spec, "roles": list(roles),
        "experimental": bool(model.get("experimental")),
        "exitCode": rc, "timedOut": timed_out, "elapsedSeconds": elapsed,
        "promptCharacters": len(prompt), "fixtureBytes": sum(
            path.stat().st_size for path in workspace.rglob("*") if path.is_file()
            and path.name != "agent-output.log"),
        "agentOutputCharacters": len(output), "reportedUsage": _reported_usage(output),
        "budgetExceeded": budget_exceeded,
        "infrastructureError": infrastructure_error,
        "roleResults": grades,
        "passed": not infrastructure_error and artifact_pass,
        "workspace": os.path.relpath(workspace, REPO),
    }
    status_parts = []
    for role, item in grades.items():
        critical = item.get("criticalFailures")
        if critical is not None:
            label = "PASS" if item["passed"] else f"FAIL ({len(critical)} critical)"
            status_parts.append(f"{role}={label}")
        else:
            status_parts.append(f"{role}={item['score']}/{item['maximum']}")
    status = ", ".join(status_parts)
    cap = "; budget cap crossed after green artifacts" if budget_exceeded and artifact_pass else ""
    print(f"DONE  {model_id}: {status}; rc={rc}; {elapsed:.1f}s{cap}", flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", help="comma-separated trial ids (default: all)")
    parser.add_argument("--roles", help="optional comma-separated role subset")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    selected = list(TRIAL_MODELS)
    if args.models:
        wanted = {item.strip() for item in args.models.split(",") if item.strip()}
        selected = [item for item in selected if item["id"] in wanted]
        missing = wanted - {item["id"] for item in selected}
        if missing:
            parser.error("unknown model trial(s): " + ", ".join(sorted(missing)))
    if args.roles:
        wanted_roles = {item.strip() for item in args.roles.split(",") if item.strip()}
        known_roles = {role for model in TRIAL_MODELS for role in model["roles"]}
        if wanted_roles - known_roles:
            parser.error("unknown role(s): " + ", ".join(sorted(wanted_roles - known_roles)))
        selected = [{**item, "roles": tuple(role for role in item["roles"]
                                             if role in wanted_roles)} for item in selected]
        selected = [item for item in selected if item["roles"]]
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}"
    run_root = Path(REPO) / ".tome-build" / "model-role-trials" / stamp
    run_root.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = [pool.submit(run_one, model, run_root, max(30, args.timeout))
                   for model in selected]
        results = [future.result() for future in futures]
    payload = {"version": 1, "run": stamp, "results": results}
    report = run_root / "results.json"
    report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"REPORT {os.path.relpath(report, REPO)}", flush=True)
    return 0 if all(item["passed"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
