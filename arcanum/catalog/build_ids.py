"""Resolve a renamed tome directory from one durable authoring plan."""
from __future__ import annotations

import os
import re


def resolve_working_id(plan_id: str, text: str, tomes_root: str) -> str:
    tome_id = plan_id
    pattern = r"renamed by the harness:\*\*\s*`[^`]+`\s*(?:→|->)\s*`([^`]+)`"
    for match in re.finditer(pattern, text):
        if os.path.isdir(os.path.join(tomes_root, match.group(1))):
            tome_id = match.group(1)
    return tome_id
