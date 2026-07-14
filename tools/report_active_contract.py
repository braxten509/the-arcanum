#!/usr/bin/env python3
"""Print the current harness-owned ship-lifecycle proof contract."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from buildlib.behavior_contract import contract, render  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tome", help="installed tome path, e.g. tomes/glimmerfen")
    parser.add_argument("--before", help="show the contract immediately before this section")
    args = parser.parse_args()
    tid = os.path.basename(os.path.abspath(args.tome.rstrip(os.sep)))
    data = contract(tid, args.before)
    print(render(tid, args.before, data=data))
    return 1 if data.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
