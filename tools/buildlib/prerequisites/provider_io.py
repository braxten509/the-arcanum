"""Reading a validator CLI's live process output: telemetry, and why a call failed.

Split out of `review.py`, which was over the 500-line gate. The seam is real: nothing here
knows what a section audit is. It turns a provider's stdout stream into a token/CPU ticker
for the operator's pane, and turns a non-zero exit into text a person can act on.
"""
from __future__ import annotations

import json
import re
import time

from arcanum.ai.events import step_tokens_from_line
from arcanum.authoring.adapters import validator_live

from .. import BUILD_DIR


# The pane rebuilds its whole conversation whenever any row's text changes, which drops
# a live text selection. Sampling stays per-second for an honest CPU average; only the
# published row is throttled, so the operator keeps a usable pane during a long gate.
LIVE_PUBLISH_SECONDS = 5.0


def _live_tick(build_id, label, started):
    """Publish CPU and tokens-so-far for the call in flight, a few seconds apart."""
    seen, totals, samples, published = 0, {}, [], 0.0

    def tick(cpu, output):
        nonlocal seen, totals, samples, published
        cut = output.rfind("\n", seen) + 1  # never parse a half-written line
        for line in output[seen:cut].splitlines():
            step = step_tokens_from_line(line)
            if step:
                totals = {key: totals.get(key, 0) + value
                          for key, value in step.items()}
        seen = max(seen, cut)
        samples.append(max(0.0, float(cpu)))
        if time.time() - published < LIVE_PUBLISH_SECONDS:
            return
        published = time.time()
        validator_live.publish(BUILD_DIR, build_id, label=label, started=started,
                               cpu=sum(samples) / len(samples), tokens=totals)
        samples.clear()
    return tick


def _cli_failure_detail(output):
    """Recover the provider's useful failure text from a structured CLI stream."""
    messages = []
    for line in str(output or "").splitlines():
        try:
            row = json.loads(line)
        except (TypeError, ValueError):
            continue
        if not isinstance(row, dict):
            continue
        values = []
        if row.get("type") == "error":
            values.append(row.get("message"))
        error = row.get("error")
        if isinstance(error, dict):
            values.append(error.get("message"))
        elif isinstance(error, str):
            values.append(error)
        payload = row.get("payload")
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                values.append(error.get("message"))
            elif isinstance(error, str):
                values.append(error)
        for value in values:
            text = re.sub(r"\s+", " ", str(value or "")).strip()
            if text and text not in messages:
                messages.append(text)
    if messages:
        return messages[-1][:1200]
    # Some CLIs still fail with plain stderr. Preserve a bounded tail instead of
    # collapsing every provider/auth/quota error to an unactionable exit code.
    tail = [re.sub(r"\s+", " ", line).strip()
            for line in str(output or "").splitlines() if line.strip()]
    return " | ".join(tail[-4:])[-1200:]


def _transient_cli_failure(detail):
    """Distinguish short provider throttles from quotas that require operator action."""
    normalized = re.sub(r"\s+", " ", str(detail or "")).strip().lower()
    if not normalized:
        return False
    if any(marker in normalized for marker in (
            "usage limit", "session limit", "weekly limit", "monthly limit",
            "billing limit", "credit balance", "resets at", "resets ")):
        return False
    return any(marker in normalized for marker in (
        "rate_limit", "rate limit", "too many requests", "http 429", "status 429",
        "resource_exhausted", "resource exhausted", "temporarily unavailable",
        "server overloaded", "overloaded_error", "capacity temporarily",
    ))


