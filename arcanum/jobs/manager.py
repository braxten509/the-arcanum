"""Job lifecycle, deduplication, background execution, and terminal results."""
from __future__ import annotations

import threading
import uuid
from typing import Callable

from .events import InMemoryJobEventStore
from .models import JobRecord
from .registry import JobHandlerRegistry, default_registry
from .store import InMemoryJobStore


class JobManager:
    def __init__(self, store: InMemoryJobStore | None = None, *,
                 registry: JobHandlerRegistry | None = None,
                 events: InMemoryJobEventStore | None = None):
        self.store = store or InMemoryJobStore()
        self.registry = registry or default_registry()
        self.event_store = events or InMemoryJobEventStore()

    def _emit(self, job_id: str, name: str, **payload) -> None:
        self.event_store.append(job_id, name, payload)

    def find_running(self, *, kind: str, **matches) -> dict | None:
        self.registry.get(kind)
        for record in self.store.all():
            value = record.to_dict()
            if record.kind == kind and record.status == "running" and all(
                    value.get(key) == expected for key, expected in matches.items()):
                return value
        return None

    def create(self, kind: str, *, job_id: str | None = None,
               status: str = "running", **fields) -> dict:
        """Create a caller-driven job without exposing repository mutation."""
        self.registry.get(kind)
        job_id = job_id or uuid.uuid4().hex[:12]
        self.store.create(JobRecord(job_id, kind, "queued", fields=fields))
        self._emit(job_id, "created", kind=kind, status="queued")
        if status != "queued":
            self.update(job_id, status=status)
        return self.status(job_id)

    def all(self, *, kind: str | None = None, status: str | None = None) -> tuple[dict, ...]:
        if kind is not None:
            self.registry.get(kind)
        rows = tuple(record.to_dict() for record in self.store.all())
        return tuple(row for row in rows
                     if (kind is None or row.get("kind") == kind)
                     and (status is None or row.get("status") == status))

    def update(self, job_id: str, *, status: str | None = None, **fields) -> dict:
        before = self.store.get(job_id)
        record = self.store.update(job_id, status=status, **fields)
        if before and record.status != before.status:
            self._emit(job_id, "status", previous=before.status, status=record.status)
        return record.to_dict()

    def transform(self, job_id: str, transform) -> dict:
        before = self.store.get(job_id)
        record = self.store.transform(job_id, transform)
        if before and record.status != before.status:
            self._emit(job_id, "status", previous=before.status, status=record.status)
        return record.to_dict()

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
        record = self.transform(job_id, mutate)
        self._emit(job_id, "trace", field=field, value=value)
        return record

    def start(self, kind: str, handler: Callable[[str], dict], *,
              job_id: str | None = None, **fields) -> dict:
        spec = self.registry.get(kind)
        if spec.execution != "managed":
            raise ValueError(f"job kind {kind!r} is not manager-executed")
        job_id = self.create(kind, job_id=job_id, **fields)["id"]

        def run() -> None:
            try:
                result = handler(job_id)
                if self.status(job_id).get("status") == "running":
                    self.complete(job_id, result)
            except Exception as exc:
                if self.status(job_id).get("status") == "running":
                    self.fail(job_id, str(exc)[:2_000])

        threading.Thread(target=run, daemon=True, name=f"arcanum-{kind}-{job_id}").start()
        return self.status(job_id)

    def completed(self, kind: str, result: dict, *, job_id: str | None = None,
                  **fields) -> dict:
        spec = self.registry.get(kind)
        if spec.execution not in {"completed", "external-process"}:
            raise ValueError(f"job kind {kind!r} is not a completed-result adapter")
        job_id = self.create(kind, job_id=job_id, **fields)["id"]
        return self.complete(job_id, result)

    def complete(self, job_id: str, result: dict) -> dict:
        return self.update(job_id, status="done", result=result)

    def fail(self, job_id: str, error: str) -> dict:
        return self.update(job_id, status="error", error=str(error)[:2_000])

    def cancel(self, job_id: str) -> dict:
        return self.update(job_id, status="cancelled")

    def events(self, job_id: str) -> tuple[dict, ...]:
        return tuple(event.to_dict() for event in self.event_store.all(job_id))

    def status(self, job_id: str) -> dict:
        record = self.store.get(job_id)
        return record.to_dict() if record else {"status": "unknown"}

    def is_running(self, job_id: str) -> bool:
        return self.status(job_id).get("status") == "running"
