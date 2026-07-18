#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""The single-author Bindery exposes every installed CLI model without role policy."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arcanum.authoring.adapters.forge_lifecycle import _author, _reviewer  # noqa: E402
from arcanum.ai.catalog import model_census  # noqa: E402
from tools.buildlib.runtime.runners import author_runner  # noqa: E402


census = model_census()
providers = [provider for provider in census["bindery"]
             if provider.get("installed") is not False]
assert providers and all(provider["models"] for provider in providers)
assert "quality" not in census
for provider in providers:
    for row in provider["models"]:
        assert len(row) == 4, (provider["id"], row)
        assert row[0] and row[1]
    first = provider["models"][0]
    picked = _author({"author": {"kind": provider["kind"], "model": first[0]}})
    assert picked["model"] == first[0]
    reviewed = _reviewer({"reviewer": {"kind": provider["kind"], "model": first[0]}})
    assert reviewed["model"] == first[0]
    display, command, input_mode = author_runner(f"{provider['kind']}:{first[0]}")
    assert first[0] in display and command and input_mode in ("arg", "stdin")

# Formerly policy-denied choices are deliberately legal now.
assert _author({"author": {"kind": "claude-cli", "model": "claude-haiku-4-5"}})
assert _author({"author": {"kind": "antigravity-cli",
                           "model": "Gemini 3.5 Flash (Low)"}})
assert _reviewer({}) is None
print("single-author model census: OK")
