"""Versioned AI role registry independent of provider transports."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AiRoleSpec:
    role_id: str
    version: int
    capabilities: tuple[str, ...]


class AiRoleRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, AiRoleSpec] = {}

    def register(self, spec: AiRoleSpec) -> None:
        if not isinstance(spec, AiRoleSpec):
            raise TypeError("AI role registration requires an AiRoleSpec")
        if not spec.role_id:
            raise ValueError("AI role id cannot be empty")
        if spec.role_id in self._entries:
            raise ValueError(f"duplicate AI role {spec.role_id!r}")
        if spec.version < 1:
            raise ValueError(f"AI role {spec.role_id!r} needs a positive version")
        if not spec.capabilities or any(not item for item in spec.capabilities):
            raise ValueError(f"AI role {spec.role_id!r} needs capabilities")
        self._entries[spec.role_id] = spec

    def get(self, role_id: str) -> AiRoleSpec:
        try:
            return self._entries[role_id]
        except KeyError as exc:
            available = ", ".join(sorted(self._entries)) or "none"
            raise ValueError(
                f"unregistered AI role {role_id!r}; available: {available}") from exc

    def entries(self) -> tuple[AiRoleSpec, ...]:
        return tuple(self._entries[key] for key in sorted(self._entries))
