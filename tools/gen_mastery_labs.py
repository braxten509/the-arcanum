#!/usr/bin/env python3
"""Generate and executable-verify one future tome's offline mastery-lab bank."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tools")]

from arcanum.ai import AiRequest, build_default_ai_service
from arcanum.ai.json_response import parse_json_object
from arcanum.tomes import load_manifest, runtime_for, tome_dir
from tools.buildlib import BUILD_DIR
from tools.buildlib.mastery_evidence import load_policy
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
        raw = build_default_ai_service().complete(self.kind, AiRequest(
            role="semantic-challenge-reviewer", model=self.model, input=prompt,
            timeout=420, workspace=self.tome_root, response_schema={"passed": "boolean",
                                                                    "problems": "strings"},
            web_allowed=True, trace={"familyId": candidate.get("familyId"),
                                     "variantId": candidate.get("variantId")})).text
        result = parse_json_object(raw)
        bound = json.dumps({"candidate": candidate, "result": result, "provider": self.kind,
                            "model": self.model}, sort_keys=True, separators=(",", ":"))
        return {"passed": result.get("passed") is True,
                "problems": list(result.get("problems") or []),
                "provider": self.kind, "model": self.model,
                "evidenceHash": hashlib.sha256(bound.encode("utf-8")).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("tome")
    parser.add_argument("--provider",
                        choices=("claude-cli", "antigravity-cli", "codex-cli", "opencode-cli"))
    parser.add_argument("--model")
    parser.add_argument("--build-id", help="read the sealed Phase 3-7 author provider/model")
    parser.add_argument("--lab", help="generate only this lab TOML basename")
    args = parser.parse_args()
    provider, model = args.provider, args.model
    if args.build_id:
        try:
            with open(os.path.join(BUILD_DIR, f"{args.build_id}.launch.json"),
                      encoding="utf-8") as handle:
                launch = json.load(handle)
            selected = ((launch.get("authors") or {}).get("phase37")
                        or launch.get("author") or {})
            provider = provider or selected.get("kind")
            model = model or selected.get("model")
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"cannot read the build's generation provider: {exc}")
    if not provider or not model:
        parser.error("provide --provider and --model, or a --build-id with a launch record")
    root = tome_dir(args.tome)
    reviewer = CliSemanticReviewer(provider, model, root)
    generator = VariantGenerator(runtime_for(args.tome), reviewer)
    matches = []
    for section in (load_manifest(args.tome).get("content") or {}).get("sections") or []:
        lab_root = os.path.join(root, "sections", str(section), "mastery-labs")
        if not os.path.isdir(lab_root):
            continue
        matches += [os.path.join(lab_root, name) for name in sorted(os.listdir(lab_root))
                    if name.endswith(".toml") and (not args.lab or name == args.lab)]
    if not matches:
        level = int((load_manifest(args.tome).get("mastery") or {}).get("level") or 0)
        if level in range(1, 6) and load_policy().for_level(level).standalone_labs == 0:
            print("no mastery lab is required by this evidence profile")
            return
        raise SystemExit("no matching mastery-lab TOML files")
    for path in matches:
        result = generator.generate(root, path)
        print(f"{os.path.relpath(path, root)}: {result.generated} generated, "
              f"{result.reused} reused ({len(result.variant_ids)} verified)")


if __name__ == "__main__":
    main()
