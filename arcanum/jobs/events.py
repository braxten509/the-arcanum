"""Append-only job events kept separate from status and result payloads."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import threading
from time import time


@dataclass(frozen=True)
class JobEvent:
    job_id: str
    sequence: int
    name: str
    payload: dict
    created_at: float = field(default_factory=time)

    def to_dict(self) -> dict:
        return {"jobId": self.job_id, "sequence": self.sequence, "name": self.name,
                "payload": deepcopy(self.payload), "createdAt": self.created_at}


class InMemoryJobEventStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: dict[str, list[JobEvent]] = {}

    def append(self, job_id: str, name: str, payload: dict | None = None) -> JobEvent:
        if not job_id or not name:
            raise ValueError("job events require a job id and name")
        with self._lock:
            rows = self._events.setdefault(job_id, [])
            event = JobEvent(job_id, len(rows) + 1, name, deepcopy(payload or {}))
            rows.append(event)
            return deepcopy(event)

    def all(self, job_id: str) -> tuple[JobEvent, ...]:
        with self._lock:
            return tuple(deepcopy(row) for row in self._events.get(job_id, ()))
