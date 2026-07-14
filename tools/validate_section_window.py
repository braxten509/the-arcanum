#!/usr/bin/env python3
"""Gate continuity and anti-template quality across an authored Phase-3 prefix.

The ordinary per-section gate catches schema and capability errors. This checkpoint runs
after a few adjacent sections in the SAME warm worker so repeated prose, uniform exercise
grids, and broken continuity contracts are repaired before those patterns spread through
the rest of the course. Future scaffold sections are intentionally excluded.
"""
import argparse
import os
import sys
import tomllib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tome_layout
from buildlib.continuity import validate_handoff
from validatelib import _findings
from validatelib.content import check_anti_template
from validatelib.depth import check_padded_prose, check_verbatim_prose


def section_ids(tome_path):
    try:
        with open(os.path.join(tome_path, "tome.toml"), "rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return []
    return [str(value) for value in ((data.get("content") or {}).get("sections") or [])]


def main():
    parser = argparse.ArgumentParser(
        description="Validate continuity and anti-template quality through one section.")
    parser.add_argument("tome", help="path to the tome folder, e.g. tomes/verisearch")
    parser.add_argument("--through", required=True, help="last completed section id")
    parser.add_argument("--plan", required=True, help="Phase 1 plan with the continuity map")
    args = parser.parse_args()

    tome_path = os.path.abspath(args.tome.rstrip(os.sep))
    tid = os.path.basename(tome_path)
    ids = section_ids(tome_path)
    if args.through not in ids:
        print(f"ERROR quality-window: {args.through!r} is not in tome.toml [content].sections")
        return 1
    prefix = ids[:ids.index(args.through) + 1]
    sections_data = []
    problems = []
    for sid in prefix:
        try:
            sections_data.append(tome_layout.load_section(tome_path, sid))
        except Exception as exc:
            problems.append(f"section {sid} cannot load: {exc}")
        clean, report = validate_handoff(tid, sid, ids, os.path.abspath(args.plan))
        if not clean:
            problems.append(report or f"section {sid} handoff failed without a diagnostic")

    _findings.clear()
    if len(sections_data) >= 2:
        check_anti_template(sections_data)
        check_verbatim_prose(sections_data)
        check_padded_prose(sections_data)
    for level, label, message in _findings:
        problems.append(f"{level} {label}: {message}")

    if problems:
        for problem in problems:
            for line in str(problem).splitlines() or ["failed without a diagnostic"]:
                print(f"ERROR quality-window: {line}")
    print(f"-- quality window {prefix[0]}..{args.through}: "
          f"{'clean' if not problems else f'{len(problems)} blocker(s)'}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
