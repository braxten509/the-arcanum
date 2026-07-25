#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""A wrong cumulative-counter baseline must not be billed as one turn.

Reproduces the real failure: one 147-second author turn was charged $14.30
because a mid-section model swap wrote a second counter key, so the harness read
a baseline of ~0 and treated a whole 33M-token session as that turn's delta.
"""
import json
import tempfile

from buildlib import ai_costs


def turn(build_dir, session, total_input, output, seconds, model="gpt-5.6-terra"):
    return ai_costs.record_ai_turn(
        build_dir, "b1", phase=3, role="author", stage="author", kind="codex-cli",
        model=model, section="s01", session_id=session, usage_mode="cumulative",
        started_at=1000.0, ended_at=1000.0 + seconds,
        usage={"inputTokens": total_input, "outputTokens": output,
               "totalTokens": total_input + output})


def main():
    assert not ai_costs.implausible_delta(
        {"outputTokens": 9_000}, 147), "a normal 61 tok/s turn must price normally"
    assert ai_costs.implausible_delta({"outputTokens": 248_000}, 147)
    assert not ai_costs.implausible_delta(None, 1)

    with tempfile.TemporaryDirectory() as build_dir:
        first = turn(build_dir, "s-1", 800_000, 9_000, 147)
        assert first["pricingStatus"] == "priced", first["pricingStatus"]
        assert first["usage"]["outputTokens"] == 9_000
        billed = float(first["apiEquivalentUsd"] or 0)
        assert billed > 0

        # Same session, a model swap resets the counter the harness can see.
        second = turn(build_dir, "s-1", 33_000_000, 257_000, 147, model="gpt-5.6-sol")
        assert second["pricingStatus"] == "implausible-counter-delta", second
        assert second["apiEquivalentUsd"] is None
        assert second["rejectedUsage"]["outputTokens"] == 248_000
        assert "1687 tokens/second" in second["rejectedReason"], second["rejectedReason"]

        # The rejected turn stayed out of every total, and the refreshed counter
        # makes the very next turn's delta correct again.
        third = turn(build_dir, "s-1", 33_010_000, 258_000, 200)
        assert third["pricingStatus"] == "priced"
        assert third["usage"]["outputTokens"] == 1_000, third["usage"]

        with open(ai_costs._state_path(build_dir, "b1"), encoding="utf-8") as handle:
            state = json.load(handle)
        section = state["sections"]["s01"]
        assert section["usage"]["outputTokens"] == 10_000, section["usage"]
        assert section["turnCount"] == 3 and section["unpricedTurns"] == 1, section

    print("ok: an implausible cumulative-counter delta is rejected, not billed")


if __name__ == "__main__":
    main()
