"""Turn a provider's cumulative usage counter into one turn's honest delta.

Some CLIs report a lifetime session total rather than per-turn usage, so the
harness charges the difference from the previous turn. Everything that can go
wrong with that baseline lives here: normalizing a partial usage record, taking
the difference, spotting a session reset, finding the previous counter across a
mid-session model swap, and refusing a delta no wall clock could have produced.
"""
from __future__ import annotations

import os

# cacheWrite1hTokens is a subset of cacheWriteTokens, not another input bucket: it
# rides along so the two cache-write prices can be told apart, and is deliberately
# absent from the freshInputTokens subtraction below.
USAGE_KEYS = ("inputTokens", "freshInputTokens", "cachedInputTokens",
              "cacheWriteTokens", "cacheWrite1hTokens",
              "outputTokens", "reasoningTokens", "totalTokens")
# Sanity ceiling for one cumulative-counter turn. Well above any real CLI decode
# rate, so it only ever fires on a broken counter baseline, never on a fast turn.
MAX_OUTPUT_TOKENS_PER_SECOND = float(
    os.environ.get("ARCANUM_MAX_OUTPUT_TOKENS_PER_SECOND", "400"))
MIN_TURN_SECONDS = 5.0    # a 0.2s turn's rate is noise, not evidence


def normalize(value):
    """Fill in the derived token fields a provider left out."""
    if not isinstance(value, dict):
        return None
    normalized = {key: max(0, int(value.get(key) or 0)) for key in USAGE_KEYS}
    if not value.get("freshInputTokens") and normalized["inputTokens"]:
        normalized["freshInputTokens"] = max(
            0, normalized["inputTokens"] - normalized["cachedInputTokens"]
            - normalized["cacheWriteTokens"])
    if not normalized["totalTokens"]:
        normalized["totalTokens"] = (normalized["inputTokens"]
                                     + normalized["outputTokens"])
    return normalized


def delta(current, previous):
    if not previous:
        return current
    # A counter decrease means a provider-side session/reset boundary.
    if any(current[key] < int(previous.get(key) or 0) for key in USAGE_KEYS):
        return current
    return {key: current[key] - int(previous.get(key) or 0) for key in USAGE_KEYS}


def implausible_delta(usage, seconds):
    """Return a reason when a turn's tokens could not have been produced in its wall clock.

    When the baseline is wrong -- a mid-session model swap writing a second
    counter key, a resumed thread that predates the ledger -- the "difference" is
    the whole session, and one 2-minute turn gets billed for hours of work. Real
    CLI turns land between 18 and 65 output tokens per second; the run that
    motivated this check reported 1,691.
    """
    if not usage:
        return ""
    output = int(usage.get("outputTokens") or 0)
    elapsed = max(float(seconds or 0), MIN_TURN_SECONDS)
    rate = output / elapsed
    if rate <= MAX_OUTPUT_TOKENS_PER_SECOND:
        return ""
    return (f"{output} output tokens in {float(seconds or 0):.1f}s is "
            f"{rate:.0f} tokens/second, over the {MAX_OUTPUT_TOKENS_PER_SECOND}/s "
            "ceiling; the cumulative-counter baseline is wrong")


def counter_key(role, kind, session_id):
    return "|".join((str(role), str(kind), str(session_id)))


def previous_counter(counters, role, kind, model, session_id):
    """Read new session-scoped counters and migrate the former model-scoped key.

    Codex can resume one cumulative-usage session with a different model. The model
    must select the rate for the new delta, but it must not reset the token counter.
    """
    key = counter_key(role, kind, session_id)
    if key in counters:
        return key, counters[key]
    legacy = "|".join((str(role), str(kind), str(model), str(session_id)))
    if legacy in counters:
        return key, counters[legacy]
    prefix, suffix = f"{role}|{kind}|", f"|{session_id}"
    candidates = [value for name, value in counters.items()
                  if str(name).startswith(prefix) and str(name).endswith(suffix)
                  and isinstance(value, dict)]
    previous = max(candidates, key=lambda value: int(value.get("totalTokens") or 0),
                   default=None)
    return key, previous
