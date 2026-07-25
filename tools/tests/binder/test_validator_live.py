"""The in-flight Validator AI row: token parsing, live publish, pane projection."""
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath

_bootstrap_sys.path.insert(0, str(_BootstrapPath(__file__).resolve().parents[3]))

import json  # noqa: E402
import os  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
from unittest.mock import patch  # noqa: E402

from arcanum.ai.events import step_tokens_from_line  # noqa: E402
from arcanum.authoring.adapters import validator_live  # noqa: E402
from arcanum.authoring.read_models import durable_status  # noqa: E402
from arcanum.jobs.stall import run_watched  # noqa: E402
from tools.buildlib.prerequisites import review  # noqa: E402

validator_live.demo()

# Verbatim shape of an opencode `--format json` step_finish, from a real probe.
STEP = json.dumps({
    "type": "step_finish", "sessionID": "ses_1",
    "part": {"type": "step-finish", "reason": "stop",
             "tokens": {"total": 8030, "input": 8005, "output": 0, "reasoning": 26,
                        "cache": {"write": 0, "read": 0}}, "cost": 0}})

assert step_tokens_from_line(STEP) == {
    "input": 8005, "output": 0, "reasoning": 26, "total": 8030}
# Cached input counts as input the call still had to carry.
cached = json.dumps({"part": {"tokens": {"total": 90, "input": 10, "output": 5,
                                         "cache": {"read": 60, "write": 15}}}})
assert step_tokens_from_line(cached)["input"] == 85, step_tokens_from_line(cached)
for ignored in ("", "not json", "{}", json.dumps({"part": {"type": "text"}}),
                json.dumps({"part": {"tokens": {}}}), json.dumps([1, 2])):
    assert step_tokens_from_line(ignored) is None, ignored


# A live call publishes a growing row; multi-step token events accumulate.
with tempfile.TemporaryDirectory() as build_dir:
    with patch.object(review, "BUILD_DIR", build_dir), \
            patch.object(review, "LIVE_PUBLISH_SECONDS", 0):
        tick = review._live_tick("b1", "section quality s01", time.time() - 5)
        tick(64.0, STEP + "\n" + STEP + "\n")
    row = validator_live.row(build_dir, "b1")
    assert row and row["kind"] == "harness", row
    assert "16,060 tokens" in row["text"], row["text"]      # both steps counted
    assert "CPU 64%" in row["text"], row["text"]
    assert "section quality s01" in row["text"], row["text"]

    # A half-written trailing line is never parsed, and never re-counted once whole.
    with patch.object(review, "BUILD_DIR", build_dir), \
            patch.object(review, "LIVE_PUBLISH_SECONDS", 0):
        tick = review._live_tick("b1", "s01", time.time())
        tick(1.0, STEP.partition('"reasoning"')[0])
        assert "tokens pending" in validator_live.row(build_dir, "b1")["text"]
        tick(1.0, STEP + "\n")
        assert "8,030 tokens" in validator_live.row(build_dir, "b1")["text"]

    # Publishing is throttled so a long gate does not rebuild the pane every second,
    # but CPU still averages every sample taken inside the window.
    with patch.object(review, "BUILD_DIR", build_dir):
        tick = review._live_tick("b3", "s01", time.time())
        tick(10.0, "")
        first = validator_live.row(build_dir, "b3")["text"]
        assert "CPU 10%" in first, first
        for sample in (90.0, 90.0, 90.0):
            tick(sample, "")
        assert validator_live.row(build_dir, "b3")["text"] == first, "throttled"
        with patch.object(review, "LIVE_PUBLISH_SECONDS", 0):
            tick(90.0, "")
        assert "CPU 90%" in validator_live.row(build_dir, "b3")["text"]
        validator_live.clear(build_dir, "b3")

    # The pane projects exactly one live row, and it retires with the call.
    conversation = os.path.join(build_dir, "b1.conversation.jsonl")
    with open(conversation, "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": 1.0, "kind": "harness", "text": "earlier"}) + "\n")
    rows = durable_status.load_conversation(build_dir, "b1")
    assert len(rows) == 2 and rows[0]["text"] == "earlier", rows
    assert rows[-1]["eventKey"] == validator_live.EVENT_KEY, rows[-1]
    validator_live.clear(build_dir, "b1")
    assert [row["text"] for row in durable_status.load_conversation(build_dir, "b1")] \
        == ["earlier"]


# The row is published from inside a real watched run and cleared on every exit path.
with tempfile.TemporaryDirectory() as build_dir:
    seen = []
    with patch.object(review, "BUILD_DIR", build_dir):
        tick = review._live_tick("b2", "phase 1 arc quality", time.time())
        run_watched(["sh", "-c", f"printf '%s\\n' '{STEP}'; sleep 2"],
                    seconds=30.0,
                    on_tick=lambda cpu, text: (tick(cpu, text),
                                               seen.append(validator_live.row(
                                                   build_dir, "b2"))))
    assert any(row and "8,030 tokens" in row["text"] for row in seen), seen
    validator_live.clear(build_dir, "b2")
    assert validator_live.row(build_dir, "b2") is None

print("validator live row: OK")
