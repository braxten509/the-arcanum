#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""An author CLI that stops computing must end the turn, not hold the build forever."""
import tempfile
import time

from tools.buildlib.single_author import AuthorSession  # noqa: E402
from tools.buildlib.single_author.session import turn  # noqa: E402


def author_session(script):
    folder = tempfile.mkdtemp(prefix="author-stall-")
    turn.BUILD_DIR = folder
    turn.initial_runner = lambda kind, model, effort: ("fake", ["sh", "-c", script], "none")
    turn.scoped_runner_command = lambda display, cmd, *args, **kwargs: cmd
    turn.ensure_cost_totals = lambda *args, **kwargs: None
    turn.record_ai_turn = lambda *args, **kwargs: None
    turn.runner_session = lambda *args, **kwargs: None
    turn.current_unit = lambda *args, **kwargs: None
    session = AuthorSession("stall-proof", "fake-cli", "test", "", "", "external")
    session.state = lambda *args, **kwargs: None
    session._writable = lambda: []
    session._readonly = lambda: []
    return session


turn.STALL_SECONDS = 2.0
turn.STALL_POLL_SECONDS = 0.5

# A CLI that prints and then sleeps forever holds no connection and burns no CPU. This is
# the opencode hang that wedged a real build behind a 900-second timeout.
started = time.monotonic()
outcome, message = author_session('echo \'{"type":"start"}\'; sleep 600').run_turn("write it")
elapsed = time.monotonic() - started
assert outcome == "failed", outcome
assert "stopped responding" in message, message
# The whole point is not waiting out the old 900s ceiling.
assert elapsed < 60, elapsed

# A CLI burning CPU is working, however quiet it is. Silence alone must never end a turn.
turn.STALL_SECONDS = 3.0
started = time.monotonic()
outcome, _message = author_session(
    'echo \'{"type":"start"}\'; end=$((SECONDS+6)); while [ $SECONDS -lt $end ]; do :; done'
).run_turn("write it")
assert outcome == "complete", outcome
assert time.monotonic() - started >= 5, "the busy turn must have run to completion"

print("author stall detection: OK")
