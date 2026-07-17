#!/usr/bin/env python3
import sys as _command_sys
from pathlib import Path as _CommandPath
_COMMAND_REPO = _CommandPath(__file__).resolve().parents[2]
_command_sys.path[:0] = [str(_COMMAND_REPO), str(_COMMAND_REPO / "tools")]

"""Explicitly validate, audit, and reseal one course-map amendment."""
import argparse
import json
import os
import sys

ROOT = str(_COMMAND_REPO)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools.buildlib.course.amend import amend_course_map


def main():
    parser = argparse.ArgumentParser(
        description="Apply a complete replacement map through the audited amendment gate.")
    parser.add_argument("build_id")
    parser.add_argument("candidate", help="complete candidate course-map JSON")
    parser.add_argument("--reason", required=True, help="specific reason for changing the sealed plan")
    args = parser.parse_args()
    try:
        with open(args.candidate, encoding="utf-8") as handle:
            candidate = json.load(handle)
        amended = amend_course_map(args.build_id, candidate, args.reason)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"course-map amendment refused: {exc}") from exc
    print(f"resealed map revision {amended['revision']} at {amended['digest']}")


if __name__ == "__main__":
    main()
