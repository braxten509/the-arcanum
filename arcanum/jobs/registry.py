"""Explicit, versioned registry of supported background-job families."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JobHandlerSpec:
    kind: str
    version: int
    capabilities: tuple[str, ...]
    execution: str


class JobHandlerRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, JobHandlerSpec] = {}

    def register(self, spec: JobHandlerSpec) -> None:
        if not isinstance(spec, JobHandlerSpec):
            raise TypeError("job registration requires a JobHandlerSpec")
        if not spec.kind:
            raise ValueError("job kind cannot be empty")
        if spec.kind in self._entries:
            raise ValueError(f"duplicate job kind {spec.kind!r}")
        if spec.version < 1:
            raise ValueError(f"job kind {spec.kind!r} needs a positive version")
        if not spec.capabilities or any(not item for item in spec.capabilities):
            raise ValueError(f"job kind {spec.kind!r} needs capabilities")
        if spec.execution not in {"managed", "external-process", "completed"}:
            raise ValueError(f"job kind {spec.kind!r} has invalid execution ownership")
        self._entries[spec.kind] = spec

    def get(self, kind: str) -> JobHandlerSpec:
        try:
            return self._entries[kind]
        except KeyError as exc:
            available = ", ".join(sorted(self._entries)) or "none"
            raise ValueError(
                f"unregistered job kind {kind!r}; available: {available}") from exc

    def entries(self) -> tuple[JobHandlerSpec, ...]:
        return tuple(self._entries[key] for key in sorted(self._entries))

    def validate_references(self, kinds: tuple[str, ...] | list[str]) -> None:
        missing = sorted(set(kinds).difference(self._entries))
        if missing:
            raise ValueError("unregistered job references: " + ", ".join(missing))


def default_registry() -> JobHandlerRegistry:
    registry = JobHandlerRegistry()
    specs = (
        JobHandlerSpec("learner-assessment", 1, ("snapshot", "assessment", "receipt"),
                       "managed"),
        JobHandlerSpec("generate-variant", 1, ("generation", "verification", "cache"),
                       "managed"),
        JobHandlerSpec("semantic-review", 1, ("review", "findings"), "managed"),
        JobHandlerSpec("grade-working", 1, ("legacy-grading", "ai-review"),
                       "external-process"),
        JobHandlerSpec("binder-amend", 1, ("authoring", "checkpoint", "trace"),
                       "external-process"),
        JobHandlerSpec("forge-build", 1, ("authoring", "validation", "trace"),
                       "external-process"),
        # Public forge payloads historically expose `kind: build`; retain it as an
        # explicit compatibility registration until that response contract is versioned.
        JobHandlerSpec("build", 1, ("forge-compatibility", "process", "trace"),
                       "external-process"),
    )
    for spec in specs:
        registry.register(spec)
    return registry
