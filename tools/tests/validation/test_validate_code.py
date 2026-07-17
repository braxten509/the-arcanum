#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""Self-check for validate_code.py: does it count, filter, and skip correctly?

    python3 tools/tests/validation/test_validate_code.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate_code import crowded_directories, offenders  # noqa: E402


def write(root, relpath, lines):
    path = os.path.join(root, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write("x\n" * lines)


def main():
    with tempfile.TemporaryDirectory() as root:
        write(root, "big.py", 12)             # over
        write(root, "exact.js", 10)           # at the limit, not over
        write(root, "small.css", 3)           # under
        write(root, "data.toml", 99)          # not a source ext
        write(root, "monaco/vendor.js", 99)   # skipped tree
        write(root, ".hidden/gen.py", 99)     # skipped dotdir
        write(root, "nested/deep/huge.java", 20)

        found = offenders(root, 10)
        for index in range(9):
            write(root, f"crowded/file-{index}.txt", 1)
        for index in range(20):
            write(root, f"parent/child-{index}/only.txt", 1)
        for excluded in ("__pycache__", "monaco", "tome-authoring", "tome-workflow",
                         "sounds", "tmp", "runtimes"):
            for index in range(12):
                write(root, f"{excluded}/excluded-{index}.txt", 1)
        for index in range(12):
            write(root, f"root-file-{index}.txt", 1)
        crowded = crowded_directories(root, 8)

    assert found == [(20, os.path.join("nested", "deep", "huge.java")), (12, "big.py")], found
    assert crowded == [(9, "crowded")], crowded
    print("ok: line and direct-file limits enforced; children and excluded trees ignored")


if __name__ == "__main__":
    main()
