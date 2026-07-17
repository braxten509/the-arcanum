#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""Run the canonical Verisearch tome through the Phase 8 structural gate.

This is deliberately an integration test: by default it executes every runnable
solution and starter, exercises the installed-tome loader, and applies --strict.
Use --no-run only for a quick static check while editing.
"""
import argparse
import os
import subprocess
import sys


REPO = str(_BOOTSTRAP_REPO)
VALIDATOR = os.path.join(REPO, "tools", "validate_tome.py")
GOLDEN_TOME = os.path.join(REPO, "tomes", "verisearch")


def main():
    parser = argparse.ArgumentParser(description="Strictly validate the golden Verisearch tome.")
    parser.add_argument("--no-run", action="store_true",
                        help="skip toolchain execution for a faster static-only check")
    args = parser.parse_args()

    cmd = [sys.executable, VALIDATOR, GOLDEN_TOME, "--strict"]
    if args.no_run:
        cmd.append("--no-run")
    result = subprocess.run(cmd, cwd=REPO)
    if result.returncode:
        sys.exit(result.returncode)
    mode = "static" if args.no_run else "full runtime"
    print(f"golden tome strict validation ({mode}): OK")


if __name__ == "__main__":
    main()
