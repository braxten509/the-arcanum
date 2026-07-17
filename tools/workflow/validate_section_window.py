#!/usr/bin/env python3
import sys as _command_sys
from pathlib import Path as _CommandPath
_COMMAND_REPO = _CommandPath(__file__).resolve().parents[2]
_command_sys.path[:0] = [str(_COMMAND_REPO), str(_COMMAND_REPO / "tools")]

"""Gate all Phase-3 quality obligations across an authored prefix.

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
from validatelib import _findings, load_toml, rel
from validatelib.content import check_anti_template, check_content, check_density
from validatelib.content.coverage import check_capability_ledger, check_canonical_type_regressions
from validatelib.content.depth import (check_freestyle_scope, check_name_drift,
                               check_padded_prose, check_presolved_static,
                               check_self_answering, check_taught_before_used,
                               check_verbatim_prose)


def section_ids(tome_path):
    try:
        with open(os.path.join(tome_path, "tome.toml"), "rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return []
    return [str(value) for value in ((data.get("content") or {}).get("sections") or [])]


def main():
    parser = argparse.ArgumentParser(
        description="Validate cumulative Phase-3 quality through one completed section.")
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
    manifest_path = os.path.join(tome_path, "tome.toml")
    manifest, manifest_error = load_toml(manifest_path)
    sections_data = []
    problems = []
    if manifest_error:
        problems.append(f"{rel(manifest_path)}: {manifest_error}")
        manifest = {}
    else:
        try:
            tome_layout.merge_banks(manifest, tome_path)
        except Exception as exc:
            problems.append(f"split banks cannot load: {exc}")
    for sid in prefix:
        try:
            sections_data.append(tome_layout.load_section(tome_path, sid))
        except Exception as exc:
            problems.append(f"section {sid} cannot load: {exc}")
        clean, report = validate_handoff(tid, sid, ids, os.path.abspath(args.plan))
        if not clean:
            problems.append(report or f"section {sid} handoff failed without a diagnostic")

    _findings.clear()
    if sections_data:
        # Only the completed prefix participates: Phase-2 placeholders in future
        # sections cannot dilute medians or manufacture false template findings.
        check_density(sections_data)
        check_content(manifest, sections_data, rel(manifest_path), include_manifest=False)
        check_anti_template(sections_data)
        check_taught_before_used(sections_data)
        check_freestyle_scope(manifest, sections_data)
        check_capability_ledger(manifest, sections_data,
                                course_complete=args.through == ids[-1])
        check_canonical_type_regressions(manifest, sections_data)
        check_verbatim_prose(sections_data)
        check_padded_prose(sections_data)
        check_presolved_static(manifest, sections_data)
        check_name_drift(sections_data)
        check_self_answering(sections_data)
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
