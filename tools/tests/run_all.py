#!/usr/bin/env python3
"""Run every test under tools/tests and fail loudly if any of them fails.

Most files here are plain scripts full of top-level `assert`s, not pytest
cases, so `pytest tools/tests` silently collected almost none of them and a
single duplicate basename made it collect nothing at all. Each file is run as
its own subprocess instead: that is what these scripts already expect, and one
crashing test cannot take the rest of the run with it.

    python3 tools/tests/run_all.py [-k SUBSTRING] [-j N] [-v]

Exit 0 = every test passed. Exit 1 = at least one failed.
"""
import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TESTS = os.path.join(REPO, "tools", "tests")


def discover(pattern=""):
    """Every tools/tests/**/test_*.py, sorted, optionally filtered."""
    found = []
    for base, dirs, files in os.walk(TESTS):
        dirs[:] = [d for d in dirs if d != "__pycache__" and not d.startswith(".")]
        found += [os.path.join(base, f) for f in files
                  if f.startswith("test_") and f.endswith(".py")]
    return sorted(p for p in found if pattern in os.path.relpath(p, REPO))


def run(path):
    """Return (relative path, ok, seconds, combined output)."""
    started = time.monotonic()
    # cwd=REPO because the scripts resolve fixtures and tools/ relative to it.
    process = subprocess.run([sys.executable, path], cwd=REPO, timeout=900,
                             capture_output=True, text=True)
    return (os.path.relpath(path, REPO), process.returncode == 0,
            time.monotonic() - started,
            (process.stdout or "") + (process.stderr or ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-k", default="", help="only run paths containing this substring")
    ap.add_argument("-j", type=int, default=min(8, os.cpu_count() or 1),
                    help="parallel workers")
    ap.add_argument("-v", action="store_true", help="show output from passing tests too")
    args = ap.parse_args()

    paths = discover(args.k)
    if not paths:
        print(f"no tests matched {args.k!r}")
        return 1
    # The browser tests each start a real server and drive a real chromium;
    # two at once fight over the port and the shared .cache profile.
    parallel = [p for p in paths if os.sep + "browser" + os.sep not in p]
    serial = [p for p in paths if os.sep + "browser" + os.sep in p]
    failed = []

    def report(result):
        rel, ok, seconds, output = result
        print(f"{'PASS' if ok else 'FAIL'} {seconds:6.1f}s  {rel}", flush=True)
        if not ok:
            failed.append((rel, output))
        elif args.v and output.strip():
            print(output.rstrip())

    with ThreadPoolExecutor(max_workers=args.j) as pool:
        for result in pool.map(run, parallel):
            report(result)
    for path in serial:
        report(run(path))
    for rel, output in failed:
        print(f"\n{'=' * 70}\nFAILED {rel}\n{'=' * 70}\n{output.rstrip()}")
    print(f"\n-- {len(paths) - len(failed)}/{len(paths)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
