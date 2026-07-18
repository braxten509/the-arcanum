"""Persisted assignment and verified challenge-package contracts."""
from __future__ import annotations

from dataclasses import dataclass

from ..ids import is_stable_id


@dataclass(frozen=True)
class VariantAssignment:
    family_id: str
    variant_id: str
    variant_hash: str
    seed: str
    assigned_at: str
    attempt: int
    abandoned: bool = False


@dataclass(frozen=True)
class VariantPackage:
    version: int
    family_id: str
    variant_id: str
    title: str
    brief: str
    axes: tuple[tuple[str, str], ...]
    public_root: str
    hidden_root: str
    reference_root: str
    mutation_roots: tuple[str, ...]
    content_hash: str

    def validate(self) -> None:
        if self.version != 1:
            raise ValueError("variant package version must be 1")
        if not is_stable_id(self.family_id) or not is_stable_id(self.variant_id):
            raise ValueError("variant family/id must be stable")
        if not self.title.strip() or not self.brief.strip():
            raise ValueError("variant title and brief are required")
        if len(dict(self.axes)) != len(self.axes):
            raise ValueError("variation axis names must be unique")
        if len(self.content_hash) != 64:
            raise ValueError("variant content hash must be SHA-256")
