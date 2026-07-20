#!/usr/bin/env python3
"""Narrow CLI boundary around the authoring harness phase-reset transaction."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from tools.buildlib.workflow.phase_reset import reset_tome_to_phase, reset_tome_to_section


def main(argv: list[str]) -> int:
    if len(argv) not in (3, 4):
        print(json.dumps({"ok": False,
                          "error": "usage: reset_tome_phase.py TOME PHASE [SECTION]"}))
        return 2
    try:
        result = (reset_tome_to_section(argv[1], argv[3]) if len(argv) == 4
                  else reset_tome_to_phase(argv[1], int(argv[2])))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps({"ok": True, "result": result}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
