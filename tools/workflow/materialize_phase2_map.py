#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools")]

from buildlib.course_map.author_spec import (materialize_author_preview,
                                             materialize_author_spec)
from buildlib.course_map import CourseMapError
from buildlib.phase2_research import validate_ledger


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Materialize the Phase-2 proposal from its compact author spec.")
    parser.add_argument("build_id", metavar="BUILD_ID")
    parser.add_argument(
        "--preview", action="store_true",
        help="write the deterministic author-check preview inside the compact spec root")
    args = parser.parse_args(argv)
    build_id = args.build_id
    ok, report = validate_ledger(build_id)
    if not ok:
        details = [line[2:].strip() for line in report.splitlines()
                   if line.startswith("- ")]
        if not details:
            details = [report.strip() or "research ledger validation failed"]
        for detail in details:
            print(f"ERROR phase2-research: {detail}")
        raise SystemExit(1)
    try:
        value = (materialize_author_preview(build_id) if args.preview
                 else materialize_author_spec(build_id))
    except CourseMapError as exc:
        message = str(exc)
        details = [line[2:].strip() for line in message.splitlines()
                   if line.startswith("- ")]
        if details:
            for detail in details:
                print(f"ERROR phase2-author-spec: {detail}")
        else:
            print(f"ERROR phase2-author-spec: {message}")
        raise SystemExit(1) from None
    mode = "PREVIEW" if args.preview else "PROPOSAL"
    print(f"MATERIALIZED_PHASE2_{mode}={len(value.get('sections') or [])}_SECTIONS")


if __name__ == "__main__":
    main()
