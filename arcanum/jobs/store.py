"""One-lock in-memory job repository with copy-on-read semantics."""
from __future__ import annotations

from copy import deepcopy
import threading

from .models import JobRecord, validate_transition


class InMemoryJobStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: dict[str, JobRecord] = {}

    def create(self, record: JobRecord) -> JobRecord:
        with self._lock:
            if record.id in self._records:
                raise ValueError(f"duplicate job id {record.id!r}")
            self._records[record.id] = deepcopy(record)
            return deepcopy(record)

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            value = self._records.get(job_id)
            return deepcopy(value) if value else None

    def all(self) -> tuple[JobRecord, ...]:
        with self._lock:
            return tuple(deepcopy(row) for row in self._records.values())

    def update(self, job_id: str, *, status: str | None = None, **fields) -> JobRecord:
        with self._lock:
            current = self._records.get(job_id)
            if not current:
                raise KeyError(job_id)
            target = status or current.status
            validate_transition(current.status, target)
            merged = {**current.fields, **deepcopy(fields)}
            value = JobRecord(current.id, current.kind, target, current.created_at, merged)
            self._records[job_id] = value
            return deepcopy(value)

    def replace_fields(self, job_id: str, fields: dict, *,
                       status: str | None = None) -> JobRecord:
        """Replace a record's payload atomically while preserving its identity metadata."""
        with self._lock:
            current = self._records.get(job_id)
            if not current:
                raise KeyError(job_id)
            target = status or current.status
            validate_transition(current.status, target)
            value = JobRecord(current.id, current.kind, target, current.created_at,
                              deepcopy(fields))
            self._records[job_id] = value
            return deepcopy(value)

    def transform(self, job_id: str, transform) -> JobRecord:
        """Apply one payload/status transformation under the repository lock."""
        with self._lock:
            current = self._records.get(job_id)
            if not current:
                raise KeyError(job_id)
            status, fields = transform(current.status, deepcopy(current.fields))
            validate_transition(current.status, status)
            value = JobRecord(current.id, current.kind, status, current.created_at,
                              deepcopy(fields))
            self._records[job_id] = value
            return deepcopy(value)
