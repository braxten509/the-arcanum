"""Learner state application policy, including protected evidence and safe reset."""
from __future__ import annotations

import json
import os
import shutil
import time

from runtimes.common import atomic_write

from arcanum.settings import GLOBAL_STATE_KEYS, UserSettingsStore
from arcanum.workspace.models import has_progress

from .json_store import LearningStateStore


class LearnerStateService:
    def __init__(self, workspaces, jobs, user_settings: UserSettingsStore):
        self.workspaces = workspaces
        self.jobs = jobs
        self.user_settings = user_settings

    def _store(self, tome_id: str) -> LearningStateStore:
        save_root = self.workspaces.ensure_save(tome_id)
        return LearningStateStore(self.workspaces.state_path(tome_id),
                                  os.path.join(save_root, "evidence-log.jsonl"))

    def read(self, tome_id: str) -> dict:
        data = self._store(tome_id).read()
        global_settings = self.user_settings.read()
        for key in GLOBAL_STATE_KEYS:
            if key in global_settings:
                data[key] = global_settings[key]
        return data

    def save(self, tome_id: str, incoming: dict) -> dict:
        if not isinstance(incoming, dict):
            raise ValueError("state must be an object")
        body = dict(incoming)
        reader_values = {key: body.pop(key) for key in GLOBAL_STATE_KEYS if key in body}
        if reader_values:
            self.user_settings.merge(reader_values)
        path = self.workspaces.state_path(tome_id)
        body = self._store(tome_id).merge_client(body)
        old = self._store(tome_id).read() if os.path.exists(path) else None
        if has_progress(old) and not has_progress(body):
            raise ValueError("refused: would erase progress")
        if has_progress(old):
            atomic_write(path + ".bak", json.dumps(old, indent=1))
        atomic_write(path, json.dumps(body, indent=1))
        return {"ok": True, "savedAt": time.time()}

    def reset(self, tome_id: str, confirmation: str) -> dict:
        if confirmation != "reset-progress":
            raise ValueError("reset confirmation is required")
        if any(job.get("tome") == tome_id for job in self.jobs.all(status="running")):
            raise RuntimeError("finish or cancel the active tome job before resetting")
        root = os.path.realpath(self.workspaces.ensure_save(tome_id))
        parent = os.path.realpath(self.workspaces.catalog.paths.tome(tome_id))
        if os.path.basename(root) != "save" or os.path.dirname(root) != parent:
            raise ValueError("refused unsafe save path")
        shutil.rmtree(root)
        os.makedirs(root, exist_ok=True)
        return {"ok": True}
