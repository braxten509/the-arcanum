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

from tools.buildlib.ai_costs import (api_equivalent_completion_cost,
                                     completed_cost_line, ensure_cost_totals,
                                     gpt_completion_cost, record_ai_turn,
                                     rewind_ai_costs, totals_path, turns_path)
from arcanum.authoring.read_models.durable_status import load_gpt_running_cost
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
    record_ai_turn(
        folder, "claude-priced", phase=3, section="s01", role="author",
        stage="author-turn", kind="claude-cli", model="claude-sonnet-5",
        transport="cli", usage={"freshInputTokens": 100_000,
                                "cachedInputTokens": 100_000,
                                "cacheWriteTokens": 100_000,
                                "outputTokens": 100_000}, ended_at=900)
    claude_cost = api_equivalent_completion_cost(
        folder, "claude-priced", phase=3, section="s01")
    assert claude_cost["apiEquivalentUsd"] == 1.47
    assert claude_cost["apiTurnCount"] == 1 and claude_cost["gptTurnCount"] == 0
    assert completed_cost_line(
        folder, "claude-priced", phase=3, section="s01", at=901) == (
            "AI API-EQUIVALENT COST COMPLETE [901.000] › "
            "PHASE 3 SECTION s01 › $1.47")
    running = load_gpt_running_cost(folder, "claude-priced")
    assert running["aiTurnCount"] == 1 and running["claudeTurnCount"] == 1
    assert running["displayUsd"] == 1.47
    assert running["turns"] == [{
        "at": 900.0, "phase": 3, "section": "s01",
        "model": "claude-sonnet-5", "apiEquivalentUsd": 1.47,
        "pricingStatus": "priced",
    }]


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
    assert phase3["gptTurnCount"] == 4 and phase3["gptPricingComplete"]
    assert s01["turnCount"] == 3 and s01["apiEquivalentUsd"] == 0.00071
    assert s02["turnCount"] == 1 and s02["apiEquivalentUsd"] == 0.00004
    s01_roles = [row["role"] for row in rows(turns_path(folder, build))
                 if row.get("section") == "s01"]
    assert s01_roles == ["author", "author", "validator"]

with tempfile.TemporaryDirectory() as folder:
    build = "displayed"
    with open(os.path.join(folder, f"{build}.course-map.json"), "w",
              encoding="utf-8") as handle:
        json.dump({"sections": [{"id": "s01"}, {"id": "s02"}]}, handle)
    record_ai_turn(
        folder, build, phase=3, section="s01", role="author", stage="author-turn",
        kind="codex-cli", model="gpt-5.6-luna", transport="cli",
        usage={"inputTokens": 1_000_000}, ended_at=1100)
    record_ai_turn(
        folder, build, phase=3, section="s02", role="validator", stage="audit",
        kind="openai-api", model="gpt-5.6-luna", transport="responses-api",
        usage={"outputTokens": 100_000}, ended_at=1101)
    # Non-GPT work remains in the token ledger but never contributes a dollar estimate.
    record_ai_turn(
        folder, build, phase=3, section="s02", role="author", stage="author-turn",
        kind="claude-cli", model="claude-future", transport="cli",
        usage={"inputTokens": 9_000_000, "outputTokens": 1_000_000}, ended_at=1102)
    s01 = gpt_completion_cost(folder, build, phase=3, section="s01")
    s02 = gpt_completion_cost(folder, build, phase=3, section="s02")
    phase3 = gpt_completion_cost(folder, build, phase=3)
    assert (s01["displayUsd"], s02["displayUsd"], phase3["displayUsd"]) == (1.0, 0.6, 1.6)
    assert phase3["displayUsd"] == s01["displayUsd"] + s02["displayUsd"]
    assert phase3["gptTurnCount"] == 2
    assert completed_cost_line(
        folder, build, phase=3, section="s01", at=1200) == (
            "AI API-EQUIVALENT COST COMPLETE [1200.000] › "
            "PHASE 3 SECTION s01 › $1.00")
    assert completed_cost_line(folder, build, phase=3, at=1201) == (
        "AI API-EQUIVALENT COST COMPLETE [1201.000] › "
        "PHASE 3 TOTAL · SUM OF 2 SECTIONS › $1.60")
    record_ai_turn(
        folder, build, phase=1, role="author", stage="planning",
        kind="codex-cli", model="gpt-5.6-luna", transport="cli",
        usage={"outputTokens": 100_000}, ended_at=1202)
    running = load_gpt_running_cost(folder, build)
    assert running["displayUsd"] == 2.2
    assert running["apiEquivalentUsd"] == 2.2
    assert running["gptTurnCount"] == 3 and running["gptPricedTurns"] == 3
    assert [(turn["phase"], turn["model"], turn["apiEquivalentUsd"])
            for turn in running["turns"]] == [
                (3, "gpt-5.6-luna", 1.0),
                (3, "gpt-5.6-luna", 0.6),
                (3, "claude-future", None),
                (1, "gpt-5.6-luna", 0.6),
            ]

with tempfile.TemporaryDirectory() as folder:
    build = "resume-model-switch"
    first = record_ai_turn(
        folder, build, phase=2, role="author", stage="author-turn",
        kind="codex-cli", model="gpt-5.6-terra", transport="cli",
        session_id="resumed", usage_mode="cumulative",
        usage={"inputTokens": 100, "cachedInputTokens": 80, "outputTokens": 10},
        ended_at=1300)
    switched = record_ai_turn(
        folder, build, phase=2, role="author", stage="author-turn",
        kind="codex-cli", model="gpt-5.6-sol", transport="cli",
        session_id="resumed", usage_mode="cumulative",
        usage={"inputTokens": 150, "cachedInputTokens": 100, "outputTokens": 20},
        ended_at=1301)
    assert first["usage"]["inputTokens"] == 100
    assert switched["usage"]["inputTokens"] == 50
    assert switched["usage"]["cachedInputTokens"] == 20
    assert switched["usage"]["freshInputTokens"] == 30
    # A fresh-session model change owns a fresh counter and is added independently.
    fresh = record_ai_turn(
        folder, build, phase=2, role="author", stage="author-turn",
        kind="codex-cli", model="gpt-5.6-luna", transport="cli",
        session_id="fresh", usage_mode="cumulative",
        usage={"inputTokens": 40, "outputTokens": 5}, ended_at=1302)
    assert fresh["usage"]["inputTokens"] == 40
    phase2 = next(row for row in rows(totals_path(folder, build))
                  if row["phase"] == 2)
    assert phase2["gptTurnCount"] == 3 and phase2["turnCount"] == 3
    assert phase2["apiEquivalentUsd"] == 0.00075
    assert completed_cost_line(folder, build, phase=2, at=1303).startswith(
        "AI API-EQUIVALENT COST COMPLETE [1303.000] › PHASE 2 TOTAL › $")
    assert load_gpt_running_cost(folder, build)["gptTurnCount"] == 3

with tempfile.TemporaryDirectory() as folder:
    # A resumed thread can have a large lifetime counter before this build ever
    # sees it. Only the explicit trace delta belongs to the current phase.
    resumed = record_ai_turn(
        folder, "old-resume", phase=1, role="author", stage="repair",
        kind="codex-cli", model="gpt-5.6-sol", transport="cli",
        session_id="old-thread", usage_mode="cumulative",
        usage={"inputTokens": 79_227_041, "cachedInputTokens": 77_064_704,
               "outputTokens": 327_841},
        usage_baseline={"inputTokens": 78_900_224, "cachedInputTokens": 76_792_832,
                        "outputTokens": 326_352}, ended_at=1350)
    assert resumed["usage"] == {
        "inputTokens": 326_817, "freshInputTokens": 54_945,
        "cachedInputTokens": 271_872, "cacheWriteTokens": 0,
        "outputTokens": 1_489, "reasoningTokens": 0, "totalTokens": 328_306,
    }
    assert resumed["apiEquivalentUsd"] == 0.455331

with tempfile.TemporaryDirectory() as folder:
    build = "restart-boundary"
    record_ai_turn(
        folder, build, phase=1, role="author", stage="author-turn",
        kind="codex-cli", model="gpt-5.6-terra", transport="cli",
        session_id="same-provider-session", usage_mode="cumulative",
        usage={"inputTokens": 100, "cachedInputTokens": 80, "outputTokens": 10},
        ended_at=1400)
    record_ai_turn(
        folder, build, phase=2, role="author", stage="discarded-attempt",
        kind="codex-cli", model="gpt-5.6-sol", transport="cli",
        session_id="same-provider-session", usage_mode="cumulative",
        usage={"inputTokens": 200, "cachedInputTokens": 150, "outputTokens": 20},
        ended_at=1401)
    assert rewind_ai_costs(folder, build, 2) == 1
    assert [row["phase"] for row in rows(turns_path(folder, build))] == [1]
    assert load_gpt_running_cost(folder, build)["gptTurnCount"] == 1
    rebuilt = record_ai_turn(
        folder, build, phase=2, role="author", stage="rebuilt-after-switch",
        kind="codex-cli", model="gpt-5.6-luna", transport="cli",
        session_id="same-provider-session", usage_mode="cumulative",
        usage={"inputTokens": 240, "cachedInputTokens": 180, "outputTokens": 25},
        ended_at=1402)
    # The discarded Phase 2 cost stays gone, while its cumulative counter remains
    # a hidden baseline. Only post-restart usage is priced at the new model's rate.
    assert rebuilt["usage"]["inputTokens"] == 40
    assert rebuilt["usage"]["cachedInputTokens"] == 30
    assert rebuilt["usage"]["outputTokens"] == 5
    assert rewind_ai_costs(folder, build, 1) == 2
    assert rows(turns_path(folder, build)) == []
    assert all(row["turnCount"] == 0 for row in rows(totals_path(folder, build))[:8])
    assert load_gpt_running_cost(folder, build) is None
    fresh_phase1 = record_ai_turn(
        folder, build, phase=1, role="author", stage="fresh-phase-1",
        kind="codex-cli", model="gpt-5.6-sol", transport="cli",
        session_id="same-provider-session", usage_mode="cumulative",
        usage={"inputTokens": 260, "cachedInputTokens": 190, "outputTokens": 30},
        ended_at=1403)
    assert fresh_phase1["usage"]["inputTokens"] == 20
    assert fresh_phase1["usage"]["cachedInputTokens"] == 10
    assert fresh_phase1["usage"]["outputTokens"] == 5
    assert rows(totals_path(folder, build))[0]["turnCount"] == 1
    assert load_gpt_running_cost(folder, build)["gptTurnCount"] == 1

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
    assert rewind_ai_costs(folder, build, 2) == 0
    # Rewinding a later phase must preserve the non-trimmable lifetime bucket,
    # not rebuild it from the capped 500-row detail journal.
    phase1 = rows(totals_path(folder, build))[0]
    assert phase1["turnCount"] == 505 and phase1["usage"]["inputTokens"] == 505

with tempfile.TemporaryDirectory() as folder:
    record_ai_turn(
        folder, "unknown", phase=4, role="author", stage="author-turn",
        kind="claude-cli", model="future-model", transport="cli",
        usage={"inputTokens": 10}, ended_at=3000)
    phase4 = rows(totals_path(folder, "unknown"))[3]
    assert not phase4["pricingComplete"] and phase4["unpricedTurns"] == 1
    assert phase4["apiEquivalentUsd"] == 0
    assert phase4["gptTurnCount"] == 0
    assert completed_cost_line(folder, "unknown", phase=4, at=3001) == ""
    assert load_gpt_running_cost(folder, "unknown") is None

with tempfile.TemporaryDirectory() as folder:
    record_ai_turn(
        folder, "missing-usage", phase=1, role="author", stage="author-turn",
        kind="codex-cli", model="gpt-5.6-luna", transport="cli",
        usage=None, ended_at=3100)
    assert completed_cost_line(folder, "missing-usage", phase=1, at=3101).endswith(
        "› UNAVAILABLE · PARTIAL: 1 AI TURN LACKED TOKEN USAGE")
    running = load_gpt_running_cost(folder, "missing-usage")
    assert running["gptPricedTurns"] == 0
    assert running["gptUnpricedTurns"] == 1


original_runner = prerequisite_review.author_runner
original_scope = prerequisite_review.scoped_runner_command
original_run = prerequisite_review.run_watched
original_retry_delays = prerequisite_review.TRANSIENT_VALIDATOR_RETRY_DELAYS
try:
    prerequisite_review.author_runner = lambda spec, context: (
        spec, ["codex", "exec", "-"], "stdin")
    prerequisite_review.scoped_runner_command = (
        lambda display, command, *args, **kwargs: command)
    # (returncode, stdout, stalled) — the validator is watched for stalls now, so this
    # stands in for a CLI that answered and exited cleanly.
    prerequisite_review.run_watched = lambda command, **kwargs: (0, "\n".join((
        '{"type":"thread.started","thread_id":"validator-session"}',
        '{"type":"item.completed","item":{"type":"agent_message",'
        '"text":"{\\"outcome\\":\\"PASS\\"}"}}',
        '{"type":"turn.completed","usage":{"input_tokens":100,'
        '"cached_input_tokens":80,"output_tokens":12}}',
    )), False)
    raw, meta = prerequisite_review._cli_adapter(
        "bounded", {"kind": "codex-cli", "model": "gpt-5.6-luna", "effort": "high"})
    assert raw == '{"outcome":"PASS"}'
    assert meta["sessionId"] == "validator-session"
    assert meta["usage"]["freshInputTokens"] == 20
    assert meta["usage"]["cachedInputTokens"] == 80

    prerequisite_review.run_watched = lambda command, **kwargs: (1, "\n".join((
        '{"type":"thread.started","thread_id":"validator-session"}',
        '{"type":"error","message":"You have hit your usage limit; retry next week."}',
        '{"type":"turn.failed","error":{"message":'
        '"You have hit your usage limit; retry next week."}}',
    )), False)
    try:
        prerequisite_review._cli_adapter(
            "bounded", {"kind": "codex-cli", "model": "gpt-5.6-luna",
                        "effort": "high"})
        raise AssertionError("a failed validator CLI must raise")
    except RuntimeError as exc:
        assert str(exc) == (
            "validator process exited 1: "
            "You have hit your usage limit; retry next week.")

    transient_calls = []
    transient_results = iter((
        (1, '{"type":"error","message":"rate_limit"}', False),
        (0, '\n'.join((
            '{"type":"thread.started","thread_id":"retried-validator"}',
            '{"type":"item.completed","item":{"type":"agent_message",'
            '"text":"{\\"outcome\\":\\"PASS\\"}"}}',
        )), False),
    ))
    prerequisite_review.TRANSIENT_VALIDATOR_RETRY_DELAYS = (0,)
    def transient_run(command, **kwargs):
        transient_calls.append(command)
        return next(transient_results)
    prerequisite_review.run_watched = transient_run
    raw, meta = prerequisite_review._cli_adapter(
        "bounded", {"kind": "codex-cli", "model": "gpt-5.6-luna",
                    "effort": "high"})
    assert raw == '{"outcome":"PASS"}'
    assert meta["sessionId"] == "retried-validator"
    assert len(transient_calls) == 2

    captured = {}
    prerequisite_review.author_runner = lambda spec, context: (
        spec, ["claude", "-p", "--model", "audit"], "arg")
    def claude_run(command, **kwargs):
        captured["command"] = command
        captured["stdin"] = kwargs.get("stdin_text")
        return (0, '{"type":"assistant","message":{"content":['
                '{"type":"text","text":"PASS"}]}}', False)
    prerequisite_review.run_watched = claude_run
    raw, meta = prerequisite_review._cli_adapter(
        "large bounded packet", {"kind": "claude-cli", "model": "audit",
                                 "effort": "medium"})
    assert raw == "PASS"
    assert captured["stdin"] == "large bounded packet"
    assert "large bounded packet" not in captured["command"]
    assert captured["command"][-4:] == [
        "--safe-mode", "--output-format", "stream-json", "--verbose"]
    assert meta["kind"] == "claude-cli"
finally:
    prerequisite_review.author_runner = original_runner
    prerequisite_review.scoped_runner_command = original_scope
    prerequisite_review.run_watched = original_run
    prerequisite_review.TRANSIENT_VALIDATOR_RETRY_DELAYS = original_retry_delays

print("AI turn costs and phase/section totals: OK")
