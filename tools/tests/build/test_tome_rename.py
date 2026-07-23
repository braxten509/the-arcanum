#!/usr/bin/env python3
"""A deterministic tome rename updates scaffold comments without rewriting authored values."""
import os
import sys
import tempfile
import tomllib
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from tools.buildlib.workflow import checkpoints


with tempfile.TemporaryDirectory() as temporary:
    repo = Path(temporary)
    source = repo / "tomes" / "untitled-9"
    source.mkdir(parents=True)
    manifest = source / "tome.toml"
    manifest.write_text(
        "# validate: python3 tools/validate_tome.py tomes/untitled-9\n"
        "# attacks: python3 tools/gen_attacks.py untitled-9\n"
        "[meta]\n"
        'id = "untitled-9"\n'
        'note = "untitled-9 is intentionally preserved in authored data"\n'
        "[runtime]\n"
        'project = "SignalCourt"\n',
        encoding="utf-8")
    plan = repo / "plan.md"
    plan.write_text("# plan\n", encoding="utf-8")

    with patch.object(checkpoints, "REPO", str(repo)):
        assert checkpoints.maybe_rename("untitled-9", str(plan)) == "signal-court"

    renamed = repo / "tomes" / "signal-court" / "tome.toml"
    text = renamed.read_text(encoding="utf-8")
    parsed = tomllib.loads(text)
    assert parsed["meta"]["id"] == "signal-court"
    assert parsed["meta"]["note"] == "untitled-9 is intentionally preserved in authored data"
    assert "tomes/signal-court" in text
    assert "gen_attacks.py signal-court" in text
    assert "tomes/untitled-9" not in text
    assert "gen_attacks.py untitled-9" not in text
    assert not source.exists()
    assert "`untitled-9` → `signal-court`" in plan.read_text(encoding="utf-8")

print("tome rename scaffold-comment rewrite: OK")
