"""Deterministic near-duplicate and axis-diversity checks for verified variants."""
from __future__ import annotations

import re


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(text).casefold()))


def similarity(left: str, right: str) -> float:
    a, b = tokens(left), tokens(right)
    return 1.0 if not a and not b else (len(a & b) / len(a | b) if a | b else 0.0)


def diversity_problems(variants: list[dict], axes: list[str], threshold: float = 0.88) -> list[str]:
    problems = []
    for axis in axes:
        values = {str((item.get("axes") or {}).get(axis) or "") for item in variants}
        if "" in values or len(values) < 2:
            problems.append(f"variation axis {axis!r} does not materially change across variants")
    for index, left in enumerate(variants):
        for right in variants[index + 1:]:
            # Repeated axis assignments intentionally reuse one executable blueprint.
            # Axis-value checks above own diversity within that blueprint; textual
            # near-duplication is a problem only when supposedly distinct blueprints
            # collapse onto the same challenge.
            if (left.get("blueprintId") and
                    left.get("blueprintId") == right.get("blueprintId")):
                continue
            if similarity(left.get("brief", ""), right.get("brief", "")) >= threshold:
                problems.append(
                    f"variants {left.get('variantId')!r} and {right.get('variantId')!r} are near-duplicates")
    return problems


def structural_signature_count(variants: list[dict]) -> int:
    return len({str(item.get("structuralSignature") or "") for item in variants}
               - {""})
