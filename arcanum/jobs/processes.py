"""Live subprocess handles kept outside JSON-safe job records."""
from __future__ import annotations

import threading


class ProcessStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._processes: dict[str, object] = {}

    def put(self, job_id: str, process: object) -> None:
        with self._lock:
            if job_id in self._processes:
                raise ValueError(f"job {job_id!r} already owns a process")
            self._processes[job_id] = process

    def get(self, job_id: str) -> object | None:
        with self._lock:
            return self._processes.get(job_id)

    def pop(self, job_id: str) -> object | None:
        with self._lock:
            return self._processes.pop(job_id, None)
