"""Live subprocess handles kept outside JSON-safe job records."""
from __future__ import annotations

import os
import signal
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

    @staticmethod
    def terminate_process(process: object, sig=signal.SIGTERM) -> bool:
        pid = getattr(process, "pid", None)
        if not isinstance(pid, int) or pid < 1:
            return False
        try:
            if hasattr(os, "killpg"):
                os.killpg(os.getpgid(pid), sig)
            else:
                os.kill(pid, sig)
            return True
        except (ProcessLookupError, PermissionError, OSError):
            try:
                process.send_signal(sig)
                return True
            except (AttributeError, ProcessLookupError, PermissionError, OSError):
                return False

    @staticmethod
    def terminate_pid(pid: int, sig=signal.SIGTERM) -> bool:
        class _PidProcess:
            def __init__(self, value):
                self.pid = value

        return ProcessStore.terminate_process(_PidProcess(pid), sig)

    def terminate(self, job_id: str, sig=signal.SIGTERM) -> bool:
        process = self.pop(job_id)
        return bool(process and self.terminate_process(process, sig))
