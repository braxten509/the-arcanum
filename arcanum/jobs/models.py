"""Pure job states and legal transition policy."""
from __future__ import annotations

from dataclasses import dataclass, field
from time import time

TERMINAL_STATES = frozenset({"done", "error", "cancelled"})
TRANSITIONS = {
    "queued": frozenset({"running", "cancelled", "error"}),
    "running": TERMINAL_STATES,
    "done": frozenset(), "error": frozenset(), "cancelled": frozenset(),
}


def validate_transition(current: str, target: str) -> None:
    if current == target:
        return
    if current not in TRANSITIONS or target not in TRANSITIONS[current]:
        raise ValueError(f"illegal job transition {current!r} -> {target!r}")


@dataclass(frozen=True)
class JobRecord:
    id: str
    kind: str
    status: str = "queued"
    created_at: float = field(default_factory=time)
    fields: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "status": self.status,
                "createdAt": self.created_at, **self.fields}
