#!/usr/bin/env python3
import sys as _command_sys
from pathlib import Path as _CommandPath
_COMMAND_REPO = _CommandPath(__file__).resolve().parents[2]
_command_sys.path[:0] = [str(_COMMAND_REPO), str(_COMMAND_REPO / "tools")]

"""Report the sole author's current phase for the Forge UI."""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from buildlib import BUILD_DIR
from buildlib.single_author.gate import PHASES


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("build_id")
    parser.add_argument("phase", type=int, choices=range(1, 9))
    parser.add_argument("state", choices=("working", "validating", "complete"))
    args = parser.parse_args()
    path = os.path.join(BUILD_DIR, f"{args.build_id}.progress")
    prior = {}
    try:
        with open(path, encoding="utf-8") as handle:
            prior = json.load(handle)
    except (OSError, ValueError):
        pass
    started = (prior.get("phaseStartedAt") if prior.get("phase") == args.phase
               else time.time())
    payload = {"phase": args.phase, "phaseTitle": PHASES[args.phase - 1],
               "state": args.state, "phaseStartedAt": started, "updatedAt": time.time()}
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"))
        handle.write("\n")
    print(f"> Phase {args.phase} — {PHASES[args.phase - 1]} [{args.state}]")


if __name__ == "__main__":
    main()
