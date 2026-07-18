"""Role-neutral qualitative-review port used by assessment."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class QualitativeRequest:
    tome_id: str
    node_id: str
    language: str
    criteria: tuple[dict, ...]
    deterministic: tuple[dict, ...]
    public_requirements: tuple[dict, ...]
    source_files: tuple[tuple[str, str], ...]
    rationale: str


@dataclass(frozen=True)
class QualitativeResponse:
    scores: tuple[dict, ...]
    provider: str
    model: str
    evidence_hash: str
    feedback: str = ""


class QualitativeProvider(Protocol):
    def score(self, request: QualitativeRequest) -> QualitativeResponse: ...


class MissingQualitativeProvider:
    def score(self, _request: QualitativeRequest) -> QualitativeResponse:
        raise RuntimeError("this assessment has qualitative criteria but no grader is configured")
