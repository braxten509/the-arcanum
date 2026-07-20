"""Live subprocess handles kept outside JSON-safe job records."""
from __future__ import annotations

import os
import signal
import threading
import time


def descendants(root_pid: int) -> list[int]:
    """Return root_pid and its current descendants from Linux /proc."""
    children: dict[int, list[int]] = {}
    try:
        entries = os.listdir("/proc")
    except OSError:
        return [int(root_pid)]
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", encoding="utf-8") as handle:
                fields = handle.read().rpartition(")")[2].split()
            children.setdefault(int(fields[1]), []).append(int(entry))
        except (OSError, ValueError, IndexError):
            continue
    found, stack = [], [int(root_pid)]
    while stack:
        pid = stack.pop()
        found.append(pid)
        stack.extend(children.get(pid, ()))
    return found


def _running(pid: int) -> bool:
    """A killed child stays in /proc as a zombie until its parent reaps it."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as handle:
            return handle.read().rpartition(")")[2].split()[0] != "Z"
    except (OSError, IndexError):
        return False


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

    def terminate(self, job_id: str, sig=signal.SIGTERM) -> bool:
        process = self.pop(job_id)
        return bool(process and self.terminate_process(process, sig))

    @staticmethod
    def terminate_tree(pid: int, grace=(3.0, 2.0, 0.5)) -> bool:
        """Stop a job's whole process tree rather than only its own group.

        The build worker and every author CLI turn are spawned with
        ``start_new_session=True``, so each owns a distinct process group. A single
        killpg reaches the worker and leaves the sandbox and provider process running —
        orphaned, still spending, still writing to the tome. Signal every group in the
        tree, escalating only as far as it takes, and report whether it actually died.
        """
        pids = descendants(pid)
        groups = set()
        for value in pids:
            try:
                groups.add(os.getpgid(value))
            except OSError:
                continue

        def alive():
            return any(_running(value) for value in pids)

        for sig, seconds in zip((signal.SIGINT, signal.SIGTERM, signal.SIGKILL), grace):
            if not alive():
                return True
            for group in groups:
                try:
                    os.killpg(group, sig)
                except OSError:
                    continue
            deadline = time.monotonic() + seconds
            while seconds and alive() and time.monotonic() < deadline:
                time.sleep(0.05)
        return not alive()
