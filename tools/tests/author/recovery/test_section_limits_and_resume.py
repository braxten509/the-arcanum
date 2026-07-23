#!/usr/bin/env python3
"""Section cost-governor and saved-session recovery checks."""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from tools.buildlib import single_author  # noqa: E402

# The section governor is cost-only. Repeated validation failures do not pause an
# unpriced section; a priced section pauses only when it reaches its chosen hard stop.
assert not single_author.section_repair_limit_reached(None)
assert not single_author.section_repair_limit_reached(
    {"apiEquivalentUsd": 1.999})
assert single_author.section_repair_limit_reached(
    {"apiEquivalentUsd": 2.0})
assert not single_author.section_repair_limit_reached(
    {"apiEquivalentUsd": 200.0}, hard_cost=None)
with tempfile.TemporaryDirectory() as cost_root:
    with open(os.path.join(cost_root, "unlimited.launch.json"), "w",
              encoding="utf-8") as handle:
        json.dump({"sectionCostLimitUsd": None}, handle)
    with open(os.path.join(cost_root, "numeric.launch.json"), "w",
              encoding="utf-8") as handle:
        json.dump({"sectionCostLimitUsd": 14.125}, handle)
    with patch.object(single_author, "BUILD_DIR", cost_root):
        assert single_author.configured_section_cost_limit("unlimited") is None
        assert single_author.configured_section_cost_limit(
            "unlimited", claude_author=True) is None
        assert single_author.configured_section_cost_limit("numeric") == 14.125
        assert single_author.configured_section_cost_limit(
            "numeric", claude_author=True) == 28.25

# A saved Codex thread that exits 1 before emitting any model output gets one
# fresh-session retry. Real diagnostics and already-fresh failures remain visible.
from buildlib.single_author.session.recovery import (
    codex_fresh_session_recovery_prompt, recoverable_codex_resume_failure)
assert recoverable_codex_resume_failure(
    "codex-cli", "author", "saved-thread", "exit code 1")
assert not recoverable_codex_resume_failure(
    "codex-cli", "author", "", "exit code 1")
assert not recoverable_codex_resume_failure(
    "codex-cli", "author", "saved-thread", "exit code 1\nprovider quota exhausted")
assert not recoverable_codex_resume_failure(
    "claude-cli", "author", "saved-thread", "exit code 1")
fresh_recovery = codex_fresh_session_recovery_prompt("Phase 3 section s01")
assert "fresh session" in fresh_recovery
assert "files on disk" in fresh_recovery
