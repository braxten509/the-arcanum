#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools")]

from buildlib.course_map.author_spec import materialize_author_spec
from buildlib.phase2_research import validate_ledger


def main():
    parser = argparse.ArgumentParser(
        description="Materialize the Phase-2 proposal from its compact author spec.")
    parser.add_argument("build_id", metavar="BUILD_ID")
    args = parser.parse_args()
    build_id = args.build_id
    ok, report = validate_ledger(build_id)
    if not ok:
        print(report)
        raise SystemExit(1)
    value = materialize_author_spec(build_id)
    print(f"MATERIALIZED_PHASE2_MAP={len(value.get('sections') or [])}_SECTIONS")


if __name__ == "__main__":
    main()
