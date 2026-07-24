#!/usr/bin/env python3
"""Binder live output exposes calls and conversation, never tool results."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from arcanum.authoring.amender import (  # noqa: E402
    _activity_rows, _review_verdict, _run_agent_turn)
from arcanum.authoring.services.binder import BinderService  # noqa: E402
from arcanum.ai.models import AiRequest  # noqa: E402
from arcanum.ai.providers.cli import (  # noqa: E402
    ClaudeCliProvider, CodexCliProvider, OpenCodeCliProvider)
from arcanum.jobs import JobManager, ProcessStore  # noqa: E402


command = json.dumps({
    "type": "item.completed",
    "item": {
        "id": "call-1",
        "type": "command_execution",
        "command": "python3 tools/validate_tome.py tomes/demo",
        "aggregated_output": "SECRET RAW TOOL OUTPUT",
        "exit_code": 0,
    },
})
rows = _activity_rows("codex-cli", command)
assert len(rows) == 1 and rows[0]["kind"] == "tool", rows
assert "validate_tome.py" in rows[0]["text"], rows
assert "--:--:--" not in rows[0]["text"] and rows[0]["at"] > 0, rows
assert "SECRET RAW TOOL OUTPUT" not in json.dumps(rows), rows

message = json.dumps({
    "type": "item.completed",
    "item": {"type": "agent_message", "text": "The tome now passes."},
})
message_rows = _activity_rows("codex-cli", message)
assert len(message_rows) == 1 and message_rows[0]["kind"] == "assistant", message_rows
assert message_rows[0]["text"] == "The tome now passes." and message_rows[0]["at"] > 0

claude = json.dumps({
    "type": "assistant",
    "message": {"content": [
        {"type": "text", "text": "I am checking the lesson."},
        {"type": "tool_use", "name": "Read",
         "input": {"file_path": "tomes/demo/tome.toml"}},
    ]},
})
rows = _activity_rows("claude-cli", claude)
assert [row["kind"] for row in rows] == ["assistant", "tool"], rows
assert "tomes/demo/tome.toml" in rows[1]["text"], rows

assert _activity_rows("codex-cli", "unstructured tool output") == []

report = """# Review

## Recommendation and implementation order

Broad correction is required.

1. Repair the trust boundary.

## Findings

This is a repairable consistency issue rather than a wholesale sourcing problem.
"""
verdict = _review_verdict(report)
assert verdict.startswith("## Recommendation and implementation order"), verdict
assert "Broad correction is required" in verdict, verdict
assert "repairable consistency issue" not in verdict, verdict

jobs = JobManager()
job_id = jobs.create(
    "binder-amend", log=["SECRET RAW TOOL OUTPUT"],
    activity=[{"kind": "tool", "text": "12:00:00  read › tome.toml"}])["id"]
status = BinderService(jobs, ProcessStore(), None).status(job_id)
assert "log" not in status and "logtail" not in status, status
assert status["activity"][0]["kind"] == "tool", status

# A completed Codex turn carries its reported usage into the shared API-equivalent
# estimator; the raw event remains server-side.
priced_job = jobs.create("binder-amend", log=[], activity=[])["id"]
usage_event = json.dumps({
    "type": "turn.completed",
    "usage": {
        "input_tokens": 1000, "cached_input_tokens": 800,
        "output_tokens": 100,
    },
})
rc, timed_out, _ = _run_agent_turn(
    priced_job,
    [sys.executable, "-c", f"print({usage_event!r})"],
    "", "none", {}, str(ROOT), "codex-cli", "gpt-5.6-sol",
    jobs, ProcessStore())
priced = jobs.status(priced_job)
assert rc == 0 and not timed_out, priced
assert priced["apiCostEstimate"]["actualCharge"] is False, priced
assert priced["apiCostEstimate"]["provider"] == "codex-cli", priced
assert priced["apiCostEstimate"]["usage"]["freshInputTokens"] == 200, priced
assert priced["apiCostEstimate"]["usage"]["cachedInputTokens"] == 800, priced
assert priced["apiCostEstimate"]["usage"]["outputTokens"] == 100, priced
assert priced["apiCostEstimate"]["usd"] > 0, priced

request = AiRequest(
    role="binder-amend", model="model", input="work", timeout=10,
    workspace=str(ROOT), stream_events=True)
codex, _ = CodexCliProvider().command(request)
claude, _ = ClaudeCliProvider().command(request)
opencode, _ = OpenCodeCliProvider().command(request)
assert "--json" in codex, codex
assert {"--output-format", "stream-json", "--verbose"} <= set(claude), claude
format_at = opencode.index("--format")
assert opencode[format_at:format_at + 2] == ["--format", "json"], opencode

print("Binder activity projection: OK")
