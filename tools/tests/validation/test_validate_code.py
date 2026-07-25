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
from validate_code import (crowded_directories, offenders,  # noqa: E402
                           stale_exemptions)


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

        found, honored_files = offenders(root, 10, {"big.py": 15})
        for index in range(11):
            write(root, f"crowded/file-{index}.txt", 1)
        for index in range(10):
            write(root, f"exactly-ten/file-{index}.txt", 1)
        for index in range(20):
            write(root, f"parent/child-{index}/only.txt", 1)
        for excluded in ("__pycache__", "monaco", "tome-authoring", "tome-workflow",
                         "sounds", "tmp", "runtimes", "validator-failures"):
            for index in range(12):
                write(root, f"{excluded}/excluded-{index}.txt", 1)
        for index in range(12):
            write(root, f"root-file-{index}.txt", 1)
        crowded, honored_dirs = crowded_directories(
            root, 10, {"crowded": 11, "exactly-ten": 12})
        stale = stale_exemptions(root, honored_files, honored_dirs, 10, 10,
                                 {"big.py": 15, "gone.py": 20},
                                 {"crowded": 11, "exactly-ten": 12})

    # big.py declares a 15-line ceiling, so 12 lines is honored, not a violation.
    assert found == [(20, os.path.join("nested", "deep", "huge.java"), 10)], found
    assert honored_files == [(12, "big.py", 15)], honored_files
    # `crowded` fits its declared 11-file ceiling; `exactly-ten` never needed one.
    assert crowded == [], crowded
    assert honored_dirs == [(11, "crowded", 11), (10, "exactly-ten", 12)], honored_dirs
    joined = "\n".join(stale)
    assert "gone.py: declared in [[limits.oversizeFiles]] but the file does not exist" in joined
    assert "exactly-ten: 10 direct files is back under the 10-file limit" in joined
    assert "big.py" not in joined and "crowded:" not in joined, joined
    with open(os.path.join(_BOOTSTRAP_REPO, ".gitignore"), encoding="utf-8") as handle:
        assert "/validator-failures/" in handle.read()
    print("ok: line and direct-file limits enforced; children and excluded trees ignored")


if __name__ == "__main__":
    main()
