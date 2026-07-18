"""Language-neutral runtime command declarations used by assessment."""
from __future__ import annotations

from dataclasses import dataclass

from ..ids import is_stable_id


@dataclass(frozen=True)
class RuntimeCommand:
    id: str
    argv: tuple[str, ...]
    timeout: int
    network: bool = False

    def validate(self) -> None:
        if not is_stable_id(self.id) or not self.argv or any(not arg for arg in self.argv):
            raise ValueError("runtime command requires a stable id and non-empty argv")
        if not 1 <= self.timeout <= 300:
            raise ValueError("runtime command timeout must be 1 through 300")
