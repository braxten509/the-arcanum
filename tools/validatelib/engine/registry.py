"""Explicit validator check registry and immutable gate profiles."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from arcanum_core.findings import Finding

from ..session import finding_scope
from .models import ValidationContext


@dataclass(frozen=True)
class CheckSpec:
    check_id: str
    version: int
    run: Callable[[ValidationContext], Iterable[Finding] | None]
    cost: str = "fast"
    capabilities: tuple[str, ...] = ()
    applies: Callable[[ValidationContext], bool] = lambda _context: True


class CheckRegistry:
    def __init__(self) -> None:
        self._checks: dict[str, CheckSpec] = {}
        self._profiles: dict[str, tuple[str, ...]] = {}

    def register(self, spec: CheckSpec) -> None:
        if not spec.check_id or spec.version < 1:
            raise ValueError("validator checks require a non-empty id and positive version")
        if spec.check_id in self._checks:
            raise ValueError(f"duplicate validator check {spec.check_id!r}")
        if spec.cost not in {"fast", "io", "process", "network", "ai"}:
            raise ValueError(f"unknown validator check cost {spec.cost!r}")
        self._checks[spec.check_id] = spec

    def profile(self, profile_id: str, check_ids: Iterable[str]) -> None:
        if profile_id in self._profiles:
            raise ValueError(f"duplicate validator profile {profile_id!r}")
        ids = tuple(check_ids)
        unknown = [check_id for check_id in ids if check_id not in self._checks]
        if unknown:
            raise ValueError("validator profile references unknown checks: "
                             + ", ".join(unknown))
        if len(ids) != len(set(ids)):
            raise ValueError(f"validator profile {profile_id!r} repeats a check")
        self._profiles[profile_id] = ids

    def run(self, profile_id: str, context: ValidationContext) -> tuple[Finding, ...]:
        try:
            check_ids = self._profiles[profile_id]
        except KeyError as exc:
            raise ValueError(f"unknown validator profile {profile_id!r}") from exc
        findings = []
        for check_id in check_ids:
            spec = self._checks[check_id]
            if not spec.applies(context):
                continue
            with finding_scope(context.build_phase) as emitted:
                returned = spec.run(context)
            findings.extend(emitted)
            if returned:
                findings.extend(item for item in returned if isinstance(item, Finding))
        return tuple(findings)

    def check_ids(self) -> tuple[str, ...]:
        return tuple(self._checks)

    def profile_ids(self) -> tuple[str, ...]:
        return tuple(self._profiles)
