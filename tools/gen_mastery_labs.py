#!/usr/bin/env python3
"""Generate and executable-verify one future tome's offline mastery-lab bank."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tools")]

from arcanum.authoring.grader import extract_json
from arcanum.models import cli_text
from arcanum.tomes import load_manifest, runtime_for, tome_dir
from tools.buildlib.mastery_evidence.variants import VariantGenerator


class CliSemanticReviewer:
    def __init__(self, kind: str, model: str, tome_root: str):
        self.kind, self.model, self.tome_root = kind, model, tome_root

    def review(self, candidate: dict) -> dict:
        prompt = (
            "Review this randomized language-learning challenge for ambiguity, hidden requirements, "
            "framework substitution, language misconception, capability/task mismatch, context-distance "
            "mislabeling, and answer leakage. Do not judge executable correctness; the harness owns that. "
            "Return only JSON {\"passed\":bool,\"problems\":[strings]}.\n\n"
            + json.dumps(candidate, ensure_ascii=False, sort_keys=True))
        raw = cli_text(self.kind, prompt, self.model, 420, self.tome_root)
        result = extract_json(raw)
        bound = json.dumps({"candidate": candidate, "result": result, "provider": self.kind,
                            "model": self.model}, sort_keys=True, separators=(",", ":"))
        return {"passed": result.get("passed") is True,
                "problems": list(result.get("problems") or []),
                "provider": self.kind, "model": self.model,
                "evidenceHash": hashlib.sha256(bound.encode("utf-8")).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("tome")
    parser.add_argument("--provider", required=True,
                        choices=("claude-cli", "antigravity-cli", "codex-cli", "opencode-cli"))
    parser.add_argument("--model", required=True)
    parser.add_argument("--lab", help="generate only this lab TOML basename")
    args = parser.parse_args()
    root = tome_dir(args.tome)
    reviewer = CliSemanticReviewer(args.provider, args.model, root)
    generator = VariantGenerator(runtime_for(args.tome), reviewer)
    matches = []
    for section in (load_manifest(args.tome).get("content") or {}).get("sections") or []:
        lab_root = os.path.join(root, "sections", str(section), "mastery-labs")
        if not os.path.isdir(lab_root):
            continue
        matches += [os.path.join(lab_root, name) for name in sorted(os.listdir(lab_root))
                    if name.endswith(".toml") and (not args.lab or name == args.lab)]
    if not matches:
        raise SystemExit("no matching mastery-lab TOML files")
    for path in matches:
        result = generator.generate(root, path)
        print(f"{os.path.relpath(path, root)}: {result.generated} generated, "
              f"{result.reused} reused ({len(result.variant_ids)} verified)")


if __name__ == "__main__":
    main()
