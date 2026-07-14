#!/usr/bin/env python3
"""Fast Phase-3 section gate: tome content plus the owning continuity handoff.

This is deliberately one provider-independent command. A warm whole-tome or bounded-batch
worker fixes it until it exits 0 before advancing; the harness retains the final independent
whole-phase gate.
"""
import argparse
import os
import sys
import tomllib

from buildlib.continuity import validate_handoff
from buildlib.measure import validate
from validatelib.phase3 import load_section_completion


def _section_ids(tome_path):
    try:
        with open(os.path.join(tome_path, "tome.toml"), "rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return []
    return [str(value) for value in ((data.get("content") or {}).get("sections") or [])]


def main():
    parser = argparse.ArgumentParser(
        description="Run the complete fast gate for one Phase-3 section.")
    parser.add_argument("tome", help="path to the tome folder, e.g. tomes/verisearch")
    parser.add_argument("section", help="owning section id, e.g. s03")
    parser.add_argument("--plan", required=True,
                        help="Phase 1 build plan containing the deterministic Continuity map")
    parser.add_argument("--tooling", choices=("internal", "external", "both"), default=None)
    args = parser.parse_args()

    tome_path = os.path.abspath(args.tome.rstrip(os.sep))
    tid = os.path.basename(tome_path)
    ids = _section_ids(tome_path)

    tome_clean, tome_report = validate(
        tid, phase=3, tooling=args.tooling, run=True, run_section=args.section,
        plan_rel=os.path.relpath(os.path.abspath(args.plan),
                                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    if tome_report:
        print(tome_report)
    elif not tome_clean:
        print("ERROR tome-validator: exited nonzero without a diagnostic")

    completion = (load_section_completion(tome_path, args.section)
                  if args.section in ids else [])
    for problem in completion:
        print(f"ERROR section-complete: {problem}")
    print(f"-- section {args.section} authored completion: "
          f"{'clean' if not completion else f'{len(completion)} blocker(s)'}")

    if args.section not in ids:
        handoff_clean = False
        handoff_report = (f"{args.section!r} is not listed in "
                          f"{os.path.relpath(os.path.join(tome_path, 'tome.toml'))}")
    else:
        handoff_clean, handoff_report = validate_handoff(
            tid, args.section, ids, os.path.abspath(args.plan))
    if not handoff_clean:
        for line in handoff_report.splitlines() or ["failed without a diagnostic"]:
            print(f"ERROR handoff: {line}")
    print(f"-- section {args.section} handoff: "
          f"{'clean' if handoff_clean else 'error(s)'}")
    sys.exit(0 if tome_clean and not completion and handoff_clean else 1)


if __name__ == "__main__":
    main()
