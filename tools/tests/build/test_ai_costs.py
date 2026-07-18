#!/usr/bin/env python3
"""Per-turn retention and lifetime phase/section cost accounting."""
import json
import os
import sys
import tempfile
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from tools.buildlib.ai_costs import (ensure_cost_totals, record_ai_turn,
                                     totals_path, turns_path)
from tools.buildlib.prerequisites import review as prerequisite_review
from tools.buildlib.runtime.events import usage_from_line


def rows(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


claude_usage = usage_from_line(json.dumps({"usage": {
    "input_tokens": 20, "cache_read_input_tokens": 80,
    "cache_creation_input_tokens": 10, "output_tokens": 5}}))
assert claude_usage["inputTokens"] == 110
assert claude_usage["freshInputTokens"] == 20
assert claude_usage["cachedInputTokens"] == 80
assert claude_usage["cacheWriteTokens"] == 10


with tempfile.TemporaryDirectory() as folder:
    build = "costed"
    with open(os.path.join(folder, f"{build}.course-map.json"), "w",
              encoding="utf-8") as handle:
        json.dump({"sections": [{"id": "s01"}, {"id": "s02"}]}, handle)

    ensure_cost_totals(folder, build)
    assert os.path.isfile(turns_path(folder, build))
    assert rows(turns_path(folder, build)) == []
    initial = rows(totals_path(folder, build))
    assert [row["phase"] for row in initial[:8]] == list(range(1, 9))
    assert [(row["phase"], row["section"]) for row in initial[8:]] == [
        (3, "s01"), (3, "s02")]
    assert all(row["turnCount"] == 0 for row in initial)

    record_ai_turn(
        folder, build, phase=3, section="s01", role="author", stage="author-turn",
        kind="codex-cli", model="gpt-5.6-terra", transport="cli",
        session_id="warm-s01", usage_mode="cumulative",
        usage={"inputTokens": 100, "cachedInputTokens": 80, "outputTokens": 10},
        ended_at=1000)
    second = record_ai_turn(
        folder, build, phase=3, section="s01", role="author", stage="author-turn",
        kind="codex-cli", model="gpt-5.6-terra", transport="cli",
        session_id="warm-s01", usage_mode="cumulative",
        usage={"inputTokens": 250, "cachedInputTokens": 200, "outputTokens": 25},
        ended_at=1001)
    assert second["usage"]["inputTokens"] == 150
    assert second["usage"]["cachedInputTokens"] == 120
    assert second["usage"]["freshInputTokens"] == 30

    record_ai_turn(
        folder, build, phase=3, section="s01", role="validator", stage="audit",
        kind="openai-api", model="gpt-5.6-luna", transport="responses-api",
        usage={"inputTokens": 100, "outputTokens": 10}, ended_at=1002)
    record_ai_turn(
        folder, build, phase=3, section="s02", role="author", stage="author-turn",
        kind="codex-cli", model="gpt-5.6-terra", transport="cli",
        usage={"inputTokens": 10, "outputTokens": 1}, ended_at=1003)

    summaries = rows(totals_path(folder, build))
    phase3 = next(row for row in summaries
                  if row["type"] == "phase-total" and row["phase"] == 3)
    s01 = next(row for row in summaries if row.get("section") == "s01")
    s02 = next(row for row in summaries if row.get("section") == "s02")
    assert phase3["turnCount"] == 4 and phase3["apiEquivalentUsd"] == 0.00075
    assert phase3["directApiUsd"] == 0.00016
    assert s01["turnCount"] == 3 and s01["apiEquivalentUsd"] == 0.00071
    assert s02["turnCount"] == 1 and s02["apiEquivalentUsd"] == 0.00004

with tempfile.TemporaryDirectory() as folder:
    build = "retention"
    for index in range(505):
        record_ai_turn(
            folder, build, phase=1, role="author", stage=f"turn-{index}",
            kind="codex-cli", model="gpt-5.6-luna", transport="cli",
            usage={"inputTokens": 1}, ended_at=2000 + index)
    turns = rows(turns_path(folder, build))
    assert len(turns) == 500
    assert turns[0]["stage"] == "turn-5" and turns[-1]["stage"] == "turn-504"
    phase1 = rows(totals_path(folder, build))[0]
    assert phase1["turnCount"] == 505
    assert phase1["usage"]["inputTokens"] == 505

with tempfile.TemporaryDirectory() as folder:
    record_ai_turn(
        folder, "unknown", phase=4, role="author", stage="author-turn",
        kind="claude-cli", model="future-model", transport="cli",
        usage={"inputTokens": 10}, ended_at=3000)
    phase4 = rows(totals_path(folder, "unknown"))[3]
    assert not phase4["pricingComplete"] and phase4["unpricedTurns"] == 1
    assert phase4["apiEquivalentUsd"] == 0


original_runner = prerequisite_review.author_runner
original_scope = prerequisite_review.scoped_runner_command
original_run = prerequisite_review.subprocess.run
try:
    prerequisite_review.author_runner = lambda spec, context: (
        spec, ["codex", "exec", "-"], "stdin")
    prerequisite_review.scoped_runner_command = lambda display, command, *args: command
    prerequisite_review.subprocess.run = lambda command, **kwargs: SimpleNamespace(
        returncode=0, stdout="\n".join((
            '{"type":"thread.started","thread_id":"validator-session"}',
            '{"type":"item.completed","item":{"type":"agent_message",'
            '"text":"{\\"outcome\\":\\"PASS\\"}"}}',
            '{"type":"turn.completed","usage":{"input_tokens":100,'
            '"cached_input_tokens":80,"output_tokens":12}}',
        )))
    raw, meta = prerequisite_review._cli_adapter(
        "bounded", {"kind": "codex-cli", "model": "gpt-5.6-luna", "effort": "high"})
    assert raw == '{"outcome":"PASS"}'
    assert meta["sessionId"] == "validator-session"
    assert meta["usage"]["freshInputTokens"] == 20
    assert meta["usage"]["cachedInputTokens"] == 80
finally:
    prerequisite_review.author_runner = original_runner
    prerequisite_review.scoped_runner_command = original_scope
    prerequisite_review.subprocess.run = original_run

print("AI turn costs and phase/section totals: OK")
