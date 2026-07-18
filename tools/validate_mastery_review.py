#!/usr/bin/env python3
"""Validate one Phase-8 mastery semantic-congruence receipt."""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tools")]

from tools.buildlib import BUILD_DIR
from tools.buildlib.mastery_evidence.review import validate_semantic_review


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("build_id")
    parser.add_argument("tome")
    args = parser.parse_args()
    clean, report = validate_semantic_review(
        BUILD_DIR, args.build_id, os.path.join(ROOT, "tomes", args.tome))
    print(("PASS " if clean else "ERROR ") + report)
    raise SystemExit(0 if clean else 1)


if __name__ == "__main__":
    main()
