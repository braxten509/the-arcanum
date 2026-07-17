#!/usr/bin/env python3
import sys as _command_sys
from pathlib import Path as _CommandPath
_COMMAND_REPO = _CommandPath(__file__).resolve().parents[2]
_command_sys.path[:0] = [str(_COMMAND_REPO), str(_COMMAND_REPO / "tools")]

"""Run the bounded AI-tool trace mirror for one live forge job."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arcanum.forge.tool_trace import mirror_tool_trace


def main():
    parser = argparse.ArgumentParser(description="Mirror a forge worker's real tool calls")
    parser.add_argument("--job", required=True, help="forge job id")
    parser.add_argument("--pid", required=True, type=int, help="root build_tome.py pid")
    args = parser.parse_args()
    mirror_tool_trace(args.job, args.pid)


if __name__ == "__main__":
    main()

