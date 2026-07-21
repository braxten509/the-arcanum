"""Live snapshot of the Validator AI call currently in flight.

A section or phase gate is one long silent subprocess: minutes of paid work with
nothing in the session pane between START and COMPLETE.  This publishes a single
*replaceable* row rather than appending history, so progress is visible without
growing the transcript, and the row disappears when the call ends.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time

_BUILD_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
EVENT_KEY = "validator-live"
# A writer killed mid-call cannot clean up after itself, so the reader expires the
# file instead of trusting it. Two missed one-second ticks is already anomalous.
STALE_SECONDS = 30.0


def _safe_id(build_id: str) -> str:
    value = str(build_id or "")
    return value if _BUILD_ID_RE.fullmatch(value) else ""


def path(build_dir: str, build_id: str) -> str:
    build_id = _safe_id(build_id)
    return os.path.join(build_dir, f"{build_id}.validator-live.json") if build_id else ""


def publish(build_dir: str, build_id: str, *, label: str, started: float,
            cpu: float, tokens: dict | None) -> None:
    """Replace the snapshot atomically; a torn read would render as a stale row."""
    target = path(build_dir, build_id)
    if not target:
        return
    payload = {"label": str(label), "started": float(started), "at": time.time(),
               "cpu": max(0.0, float(cpu)), "tokens": dict(tokens or {})}
    try:
        handle, temporary = tempfile.mkstemp(
            prefix=".validator-live-", suffix=".tmp", dir=os.path.dirname(target))
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream)
        os.replace(temporary, target)
    except OSError:
        pass


def clear(build_dir: str, build_id: str) -> None:
    try:
        os.unlink(path(build_dir, build_id))
    except OSError:
        pass


def _elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}m {seconds % 60:02d}s" if seconds >= 60 else f"{seconds}s"


def _tokens(tokens: dict) -> str:
    total = int(tokens.get("total") or 0)
    if not total:
        # Token counts arrive per completed step, so a single-step audit reports
        # nothing until the model stops. Saying so beats displaying a false zero.
        return "tokens pending"
    parts = [f"{int(tokens.get(key) or 0):,} {name}"
             for key, name in (("input", "in"), ("output", "out"),
                               ("reasoning", "reasoning"))
             if int(tokens.get(key) or 0)]
    return f"{total:,} tokens" + (f" ({' / '.join(parts)})" if parts else "")


def row(build_dir: str, build_id: str) -> dict | None:
    """Project the snapshot into one replaceable harness conversation row."""
    try:
        with open(path(build_dir, build_id), encoding="utf-8") as handle:
            live = json.load(handle)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(live, dict):
        return None
    if time.time() - float(live.get("at") or 0) > STALE_SECONDS:
        return None
    started = float(live.get("started") or 0)
    text = (f"Validator AI running › {live.get('label') or 'quality audit'} · "
            f"{_elapsed(time.time() - started)} elapsed · "
            f"CPU {live.get('cpu') or 0:.0f}% · {_tokens(live.get('tokens') or {})}")
    return {"at": started, "kind": "harness", "text": text, "eventKey": EVENT_KEY}


def demo() -> None:
    """Self-check: a published snapshot renders, and an expired one does not."""
    import shutil

    root = tempfile.mkdtemp()
    try:
        assert row(root, "b1") is None, "no snapshot must render no row"
        publish(root, "b1", label="section quality s01", started=time.time() - 75,
                cpu=87.4, tokens={"total": 8030, "input": 8005, "reasoning": 26})
        live = row(root, "b1")
        assert live and live["eventKey"] == EVENT_KEY, live
        assert "1m 15s elapsed" in live["text"], live["text"]
        assert "CPU 87%" in live["text"], live["text"]
        assert "8,030 tokens (8,005 in / 26 reasoning)" in live["text"], live["text"]

        publish(root, "b1", label="x", started=time.time(), cpu=0, tokens={})
        assert "tokens pending" in row(root, "b1")["text"]

        with open(path(root, "b1"), encoding="utf-8") as handle:
            stale = json.load(handle)
        stale["at"] = time.time() - STALE_SECONDS - 1
        with open(path(root, "b1"), "w", encoding="utf-8") as handle:
            json.dump(stale, handle)
        assert row(root, "b1") is None, "an expired snapshot must not render"

        clear(root, "b1")
        assert not os.path.exists(path(root, "b1"))
        assert path(root, "../etc") == "", "a bad build id must not escape the dir"
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print("validator live snapshot: OK")


if __name__ == "__main__":
    demo()
