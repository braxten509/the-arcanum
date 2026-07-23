#!/usr/bin/env python3
import sys as _command_sys
from pathlib import Path as _CommandPath
_COMMAND_REPO = _CommandPath(__file__).resolve().parents[2]
_command_sys.path[:0] = [str(_COMMAND_REPO), str(_COMMAND_REPO / "tools")]

"""Small deterministic transitions used by the single tome author."""
import argparse
import os

from buildlib import BUILD_DIR
from buildlib.workflow.checkpoints import (finalize_arc, maybe_rename,
                                           preflight_arc_transition)
from buildlib.course_map import seed_course_map, seal_course_map
from buildlib.course_map.author_spec import initialize_author_spec, materialize_author_spec
from buildlib.phase2_research import initialize_ledger
from buildlib.workflow.prompts import read_tooling
from buildlib.skeleton import hydrate_section_scaffolds, scaffold_sections


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("build_id")
    parser.add_argument("phase", type=int, choices=(1, 2))
    args = parser.parse_args()
    plan = os.path.join(BUILD_DIR, f"{args.build_id}.plan.md")
    if args.phase == 1:
        # Fail on every plan-derived seed invariant before mutating the plan or
        # replacing section scaffolds.  The author's Phase-1 validator runs this
        # same side-effect-free preflight.
        preflight_arc_transition(plan, args.build_id)
        finalize_arc(plan)
        specs = scaffold_sections(args.build_id, plan)
        seed = seed_course_map(args.build_id, plan)
        initialize_author_spec(args.build_id, seed)
        initialize_ledger(args.build_id, read_tooling(plan))
        print(f"Prepared Phase 2: {len(specs)} section skeletons in tomes/{args.build_id} "
              f"and compact map sources in .tome-build/{args.build_id}.course-map-author.")
    else:
        materialize_author_spec(args.build_id)
        sealed = seal_course_map(args.build_id)
        current = maybe_rename(args.build_id, plan)
        hydrated = hydrate_section_scaffolds(current, sealed)
        print(f"SEALED_COURSE_MAP={sealed['digest']}")
        print(f"CURRENT_TOME={current}")
        print(f"HYDRATED_SECTION_SCAFFOLDS={len(hydrated)}")


if __name__ == "__main__":
    main()
