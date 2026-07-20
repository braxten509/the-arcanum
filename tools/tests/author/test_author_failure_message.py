#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""A crashing author CLI must report why, not just that it stopped."""
import json
import os
import tempfile

from tools.buildlib.single_author import AuthorSession  # noqa: E402
from tools.buildlib.single_author.session import turn  # noqa: E402


folder = tempfile.mkdtemp(prefix="author-failure-")
turn.BUILD_DIR = folder
turn.initial_runner = lambda kind, model, effort: (
    "fake", ["sh", "-c", "echo '{\"type\":\"noise\"}'; "
             "echo 'Provider rate limit exceeded' >&2; exit 3"], "none")
turn.scoped_runner_command = lambda display, cmd, *args, **kwargs: cmd
turn.ensure_cost_totals = lambda *args, **kwargs: None
turn.record_ai_turn = lambda *args, **kwargs: None
turn.runner_session = lambda *args, **kwargs: None
turn.current_unit = lambda *args, **kwargs: None

session = AuthorSession("failure-proof", "fake-cli", "test", "", "", "external")
session.state = lambda *args, **kwargs: None
session._writable = lambda: []
session._readonly = lambda: []

outcome, message = session.run_turn("write the section")
assert outcome == "failed", outcome
# The exit code alone says nothing; the CLI's own last words are the diagnosis.
assert "exit code 3" in message, message
assert "Provider rate limit exceeded" in message, message
# Structured events are the turn's transcript, not its crash report.
assert "noise" not in message, message

rows = [json.loads(line) for line
        in open(os.path.join(folder, "failure-proof.conversation.jsonl"))]
assert rows and rows[0]["text"] == "write the section", rows

print("author failure message: OK")
