#!/usr/bin/env python3
import sys as _command_sys
from pathlib import Path as _CommandPath
_COMMAND_REPO = _CommandPath(__file__).resolve().parents[2]
_command_sys.path[:0] = [str(_COMMAND_REPO), str(_COMMAND_REPO / "tools")]

"""Small deterministic transitions used by the single tome author."""
import argparse
import os

from buildlib import BUILD_DIR
from buildlib.workflow.checkpoints import finalize_arc, maybe_rename
from buildlib.course_map import seed_course_map, seal_course_map
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
        seed_course_map(args.build_id, plan)
        print(f"Prepared Phase 2: {len(specs)} section skeletons and a complete-map proposal "
              f"in tomes/{args.build_id}.")
    else:
        sealed = seal_course_map(args.build_id)
        current = maybe_rename(args.build_id, plan)
        print(f"SEALED_COURSE_MAP={sealed['digest']}")
        print(f"CURRENT_TOME={current}")


if __name__ == "__main__":
    main()
