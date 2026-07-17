#!/usr/bin/env python3
import sys as _command_sys
from pathlib import Path as _CommandPath
_COMMAND_REPO = _CommandPath(__file__).resolve().parents[2]
_command_sys.path[:0] = [str(_COMMAND_REPO), str(_COMMAND_REPO / "tools")]

"""Update the exact Phase-3 section marker consumed by the Bindery UI."""
import argparse

from buildlib.workflow.section_progress import SECTION_PROGRESS_STATES, write_section_progress


def main():
    parser = argparse.ArgumentParser(description="Report warm-batch section progress")
    parser.add_argument("tome")
    parser.add_argument("section")
    parser.add_argument("index", type=int)
    parser.add_argument("total", type=int)
    parser.add_argument("state", choices=SECTION_PROGRESS_STATES)
    parser.add_argument("--batch", type=int, default=0)
    parser.add_argument("--batches", type=int, default=0)
    args = parser.parse_args()
    if args.index < 1 or args.total < args.index:
        parser.error("index must be within 1..total")
    write_section_progress(args.tome, args.section, args.index, args.total, args.state,
                           args.batch, args.batches)


if __name__ == "__main__":
    main()
