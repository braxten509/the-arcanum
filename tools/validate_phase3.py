#!/usr/bin/env python3
"""Complete Phase-3 gate: normal validator + authored sections + final quality window."""
import argparse
import os
import subprocess
import sys

from buildlib import REPO
from buildlib.measure import section_window_validator_argv, validator_argv
from buildlib.course.alignment import validate_tome_alignment
from buildlib.course_map import build_id_from_plan
from validatelib.phase3 import tome_completion_problems, tome_section_ids


def _run(command):
    result = subprocess.run(command, cwd=REPO, env=os.environ.copy(),
                            capture_output=True, text=True)
    report = (result.stdout + result.stderr).strip()
    if report:
        print(report)
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(
        description="Validate complete Phase-3 authorship, execution, continuity, and quality.")
    parser.add_argument("tome", help="path to the installed tome, e.g. tomes/verisearch")
    parser.add_argument("--plan", required=True, help="Phase-1 plan containing continuity edges")
    parser.add_argument("--tooling", choices=("internal", "external", "both"), default=None)
    parser.add_argument("--strict", action="store_true",
                        help="also gate non-advisory warnings for Phase 7/8 shipping")
    parser.add_argument("--run", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    tome_path = os.path.abspath(args.tome.rstrip(os.sep))
    tid = os.path.basename(tome_path)
    base_clean = _run(validator_argv(
        tid, phase=7 if args.strict else 3, tooling=args.tooling, run=args.run,
        phase_only=not args.strict,
        plan_rel=os.path.relpath(os.path.abspath(args.plan), REPO)))

    completion = tome_completion_problems(tome_path)
    for problem in completion:
        print(f"ERROR phase3-complete: {problem}")
    print(f"-- Phase 3 authored completion: "
          f"{'clean' if not completion else f'{len(completion)} blocker(s)'}")

    ids = tome_section_ids(tome_path)
    build_id = build_id_from_plan(os.path.abspath(args.plan))
    try:
        map_clean, map_report = validate_tome_alignment(build_id, tome_path)
    except ValueError as exc:
        map_clean, map_report = False, str(exc)
    if not map_clean:
        for line in map_report.splitlines() or ["failed without a diagnostic"]:
            print(f"ERROR course-map: {line}")
    print(f"-- Phase 3 sealed-map alignment: {'clean' if map_clean else 'error(s)'}")
    quality_clean = False
    if ids:
        quality_clean = _run(section_window_validator_argv(
            tid, ids[-1], os.path.relpath(os.path.abspath(args.plan), REPO)))
    else:
        print("ERROR quality-window: no sections are available for the final window")
    return 0 if base_clean and not completion and quality_clean and map_clean else 1


if __name__ == "__main__":
    sys.exit(main())
