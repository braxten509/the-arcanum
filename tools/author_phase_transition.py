#!/usr/bin/env python3
"""Small deterministic transitions used by the single tome author."""
import argparse
import os

from buildlib import BUILD_DIR
from buildlib.checkpoints import finalize_arc, maybe_rename
from buildlib.skeleton import scaffold_sections


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("build_id")
    parser.add_argument("phase", type=int, choices=(1, 2))
    args = parser.parse_args()
    plan = os.path.join(BUILD_DIR, f"{args.build_id}.plan.md")
    if args.phase == 1:
        finalize_arc(plan)
        specs = scaffold_sections(args.build_id, plan)
        print(f"Prepared Phase 2: {len(specs)} section skeletons in tomes/{args.build_id}.")
    else:
        current = maybe_rename(args.build_id, plan)
        print(f"CURRENT_TOME={current}")


if __name__ == "__main__":
    main()
