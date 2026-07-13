#!/usr/bin/env python3
"""Build Phase 2's one-lesson-per-section skeleton from an approved Arc."""
import argparse
import os
import sys

from buildlib import REPO
from buildlib.skeleton import scaffold_sections


def main():
    parser = argparse.ArgumentParser(
        description="Deterministically scaffold tome sections from a plan's Section list.")
    parser.add_argument("tome", help="tome id or tomes/<id> path")
    parser.add_argument("--plan", required=True, help="approved .tome-build plan path")
    parser.add_argument("--force", action="store_true",
                        help="replace sections even if they no longer look like TODO scaffolds")
    args = parser.parse_args()
    tid = os.path.basename(args.tome.rstrip(os.sep))
    plan = args.plan if os.path.isabs(args.plan) else os.path.join(REPO, args.plan)
    try:
        specs = scaffold_sections(tid, plan, force=args.force)
    except ValueError as exc:
        sys.exit(f"error: {exc}")
    print(f"scaffolded tomes/{tid}/sections: "
          + ", ".join(spec.sid for spec in specs)
          + " (one Phase 3 placeholder lesson each)")


if __name__ == "__main__":
    main()
