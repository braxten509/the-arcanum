"""Explicit authoring phase registry with duplicate and gap rejection."""
from __future__ import annotations

from .models import PhaseDefinition


class PhaseRegistry:
    def __init__(self) -> None:
        self._definitions: dict[int, PhaseDefinition] = {}
        self._ids: dict[str, int] = {}

    def register(self, definition: PhaseDefinition) -> None:
        if definition.phase < 1 or not definition.phase_id or not definition.title:
            raise ValueError("authoring phases require ordinal, id, and title")
        if definition.phase in self._definitions:
            raise ValueError(f"duplicate authoring phase {definition.phase}")
        if definition.phase_id in self._ids:
            raise ValueError(f"duplicate authoring phase id {definition.phase_id!r}")
        if definition.unit_kind not in {"phase", "section"}:
            raise ValueError(f"unknown authoring unit kind {definition.unit_kind!r}")
        if definition.version < 1:
            raise ValueError(f"authoring phase {definition.phase_id!r} needs a positive version")
        if (not definition.capabilities
                or any(not isinstance(item, str) or not item for item in definition.capabilities)):
            raise ValueError(f"authoring phase {definition.phase_id!r} needs capabilities")
        self._definitions[definition.phase] = definition
        self._ids[definition.phase_id] = definition.phase

    def seal(self) -> "PhaseRegistry":
        phases = sorted(self._definitions)
        if phases != list(range(1, len(phases) + 1)):
            raise ValueError("authoring phase ordinals must be contiguous from 1")
        if phases and not self._definitions[phases[-1]].final:
            raise ValueError("the last authoring phase must be terminal")
        if any(self._definitions[phase].final for phase in phases[:-1]):
            raise ValueError("only the last authoring phase may be terminal")
        return self

    def get(self, phase: int) -> PhaseDefinition:
        try:
            return self._definitions[int(phase)]
        except (KeyError, TypeError, ValueError) as exc:
            available = ", ".join(str(item) for item in sorted(self._definitions)) or "none"
            raise ValueError(
                f"unknown authoring phase {phase!r}; available: {available}"
            ) from exc

    def validate_references(self, phases: list[int] | tuple[int, ...]) -> None:
        missing = sorted(set(phases).difference(self._definitions))
        if missing:
            raise ValueError("unknown authoring phase references: "
                             + ", ".join(str(item) for item in missing))

    def next(self, phase: int) -> PhaseDefinition | None:
        current = self.get(phase)
        return None if current.final else self.get(current.phase + 1)

    def definitions(self) -> tuple[PhaseDefinition, ...]:
        return tuple(self._definitions[key] for key in sorted(self._definitions))
