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
