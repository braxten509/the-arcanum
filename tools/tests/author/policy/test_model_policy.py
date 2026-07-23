#!/usr/bin/env python3
"""The Bindery's approved OpenRouter construction hand has explicit policy guidance."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from arcanum.authoring.model_policy import model_guidance


guidance = model_guidance("openrouter/deepseek/deepseek-v4-pro", ["medium", "high"])
assert guidance["known"]
assert guidance["advised"]["writer"]
assert guidance["advised"]["sections"]
assert not guidance["advised"]["reviewer"]
assert guidance["efforts"]["writer"] == ["high"]
assert guidance["efforts"]["sections"] == ["high"]

print("OpenRouter DeepSeek construction policy: OK")
