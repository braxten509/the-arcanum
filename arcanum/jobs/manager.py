"""Job lifecycle, deduplication, background execution, and terminal results."""
from __future__ import annotations

import threading
import uuid
from typing import Callable

from .models import JobRecord
from .store import InMemoryJobStore


class JobManager:
    def __init__(self, store: InMemoryJobStore | None = None):
        self.store = store or InMemoryJobStore()

    def find_running(self, *, kind: str, **matches) -> dict | None:
        for record in self.store.all():
            value = record.to_dict()
            if record.kind == kind and record.status == "running" and all(
                    value.get(key) == expected for key, expected in matches.items()):
                return value
        return None

    def create(self, kind: str, *, job_id: str | None = None,
               status: str = "running", **fields) -> dict:
        """Create a caller-driven job without exposing repository mutation."""
        job_id = job_id or uuid.uuid4().hex[:12]
        self.store.create(JobRecord(job_id, kind, "queued", fields=fields))
        if status != "queued":
            self.store.update(job_id, status=status)
        return self.status(job_id)

    def all(self, *, kind: str | None = None, status: str | None = None) -> tuple[dict, ...]:
        rows = tuple(record.to_dict() for record in self.store.all())
        return tuple(row for row in rows
                     if (kind is None or row.get("kind") == kind)
                     and (status is None or row.get("status") == status))

    def update(self, job_id: str, *, status: str | None = None, **fields) -> dict:
        return self.store.update(job_id, status=status, **fields).to_dict()

    def transform(self, job_id: str, transform) -> dict:
        return self.store.transform(job_id, transform).to_dict()

    def append(self, job_id: str, field: str, value, *, limit: int | None = None,
               **fields) -> dict:
        def mutate(status, current):
            values = list(current.get(field) or [])
            values.append(value)
            if limit is not None:
                values = values[-limit:]
            current.update(fields)
            current[field] = values
            return status, current
        return self.transform(job_id, mutate)

    def start(self, kind: str, handler: Callable[[str], dict], *,
              job_id: str | None = None, **fields) -> dict:
        job_id = job_id or uuid.uuid4().hex[:12]
        self.store.create(JobRecord(job_id, kind, "queued", fields=fields))
        self.store.update(job_id, status="running")

        def run() -> None:
            try:
                result = handler(job_id)
                if self.status(job_id).get("status") == "running":
                    self.store.update(job_id, status="done", result=result)
            except Exception as exc:
                if self.status(job_id).get("status") == "running":
                    self.store.update(job_id, status="error", error=str(exc)[:2_000])

        threading.Thread(target=run, daemon=True, name=f"arcanum-{kind}-{job_id}").start()
        return self.status(job_id)

    def completed(self, kind: str, result: dict, *, job_id: str | None = None,
                  **fields) -> dict:
        job_id = job_id or uuid.uuid4().hex[:12]
        self.store.create(JobRecord(job_id, kind, "queued", fields=fields))
        self.store.update(job_id, status="running")
        self.store.update(job_id, status="done", result=result)
        return self.status(job_id)

    def cancel(self, job_id: str) -> dict:
        record = self.store.update(job_id, status="cancelled")
        return record.to_dict()

    def status(self, job_id: str) -> dict:
        record = self.store.get(job_id)
        return record.to_dict() if record else {"status": "unknown"}

    def is_running(self, job_id: str) -> bool:
        return self.status(job_id).get("status") == "running"
