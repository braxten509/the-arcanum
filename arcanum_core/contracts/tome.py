"""Compatibility boundary between legacy and evidence-version tomes."""
from __future__ import annotations

from .mastery import MasteryDeclaration


def mastery_declaration(manifest: object) -> MasteryDeclaration | None:
    if not isinstance(manifest, dict):
        raise ValueError("tome manifest must be an object")
    return MasteryDeclaration.from_dict(manifest.get("mastery"))


def uses_mastery_evidence(manifest: object) -> bool:
    return mastery_declaration(manifest) is not None
