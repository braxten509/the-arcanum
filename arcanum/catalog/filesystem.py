"""Filesystem-backed, copy-on-read tome manifest repository."""
from __future__ import annotations

from copy import deepcopy
import os
import threading
import tomllib

from .paths import TomePaths


class ManifestRepository:
    def __init__(self, paths: TomePaths):
        self.paths = paths
        self._lock = threading.RLock()
        self._cache: dict[str, tuple[int, dict]] = {}

    def load(self, tome_id: str) -> dict:
        path = self.paths.manifest(tome_id)
        stamp = os.stat(path).st_mtime_ns
        with self._lock:
            cached = self._cache.get(tome_id)
            if not cached or cached[0] != stamp:
                with open(path, "rb") as handle:
                    value = tomllib.load(handle)
                self._cache[tome_id] = (stamp, value)
            return deepcopy(self._cache[tome_id][1])

    def clear(self, tome_id: str | None = None) -> None:
        with self._lock:
            if tome_id is None:
                self._cache.clear()
            else:
                self._cache.pop(tome_id, None)
