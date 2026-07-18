#!/usr/bin/env python3
"""Hard dependency and registry architecture gate."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.architecture.models import load_policy
from tools.architecture.rules import check_all


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate Arcanum architecture boundaries")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--policy", default=str(ROOT / "global-configs" /
                                                "architecture-policy.toml"))
    args = parser.parse_args(argv)
    findings = check_all(str(Path(args.root).resolve()), load_policy(args.policy))
    for finding in findings:
        print(finding.render())
    print(f"-- {len(findings)} architecture violation(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
