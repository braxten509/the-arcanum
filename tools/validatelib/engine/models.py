"""Typed input context for one validator service run."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValidationContext:
    tome_path: str
    run: bool = False
    tooling: str | None = None
    phase2_skeleton: bool = False
    run_section: str | None = None
    require_proof_v1: bool = False
    build_plan: str | None = None
    source_only: bool = False
    build_phase: int | None = None
    manifest: dict = field(default_factory=dict)
    sections: list[dict] = field(default_factory=list)
    public_payload: dict | None = None

    @property
    def profile(self) -> str:
        if self.phase2_skeleton:
            return "phase2"
        if self.run_section:
            return "section"
        return "shipping" if self.run else "fast"
