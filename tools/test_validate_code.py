#!/usr/bin/env python3
"""Self-check for validate_code.py: does it count, filter, and skip correctly?

    python3 tools/test_validate_code.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate_code import offenders  # noqa: E402


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

    assert found == [(20, os.path.join("nested", "deep", "huge.java")), (12, "big.py")], found
    print("ok: 2 offenders, longest first; exts filtered, vendor + dotdirs skipped")


if __name__ == "__main__":
    main()
