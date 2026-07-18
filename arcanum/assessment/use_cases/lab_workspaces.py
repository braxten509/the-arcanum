"""Isolated mastery-lab workspace creation and bounded writes."""
from __future__ import annotations

import os

from arcanum_core.ids import is_stable_id
from runtimes.common import atomic_write, safe_join

MAX_FILES = 400
MAX_FILE_BYTES = 500_000


class LabWorkspaceStore:
    def __init__(self, save_root: str):
        self.root = os.path.join(save_root, "mastery-lab-workspaces")

    def path(self, family_id: str, variant_id: str) -> str:
        if not is_stable_id(family_id) or not is_stable_id(variant_id):
            raise ValueError("mastery-lab family/variant ids must be stable")
        return os.path.join(self.root, family_id, variant_id)

    def seed(self, family_id: str, variant_id: str, files: list[dict]) -> str:
        workspace = self.path(family_id, variant_id)
        if os.path.isdir(workspace):
            return workspace
        os.makedirs(workspace, exist_ok=False)
        self.write(family_id, variant_id, files)
        return workspace

    def write(self, family_id: str, variant_id: str, files: list[dict]) -> None:
        if not isinstance(files, list) or len(files) > MAX_FILES:
            raise ValueError("mastery-lab workspace exceeds the file-count limit")
        workspace = self.path(family_id, variant_id)
        os.makedirs(workspace, exist_ok=True)
        for row in files:
            if not isinstance(row, dict) or set(row) != {"path", "content"}:
                raise ValueError("mastery-lab files require only path and content")
            content = row.get("content")
            if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_FILE_BYTES:
                raise ValueError("mastery-lab file content is invalid or too large")
            target = safe_join(workspace, str(row.get("path") or ""))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            atomic_write(target, content)

    def files(self, family_id: str, variant_id: str, runtime) -> list[dict]:
        workspace = self.path(family_id, variant_id)
        files = []
        for directory, dirnames, names in os.walk(workspace):
            dirnames[:] = sorted(name for name in dirnames
                                  if not name.startswith(".") and not os.path.islink(
                                      os.path.join(directory, name)))
            for name in sorted(names):
                full = os.path.join(directory, name)
                if os.path.islink(full) or os.path.getsize(full) > MAX_FILE_BYTES:
                    continue
                try:
                    data = open(full, "rb").read(MAX_FILE_BYTES + 1)
                except OSError:
                    continue
                if len(data) > MAX_FILE_BYTES or b"\0" in data:
                    continue
                files.append({"path": os.path.relpath(full, workspace).replace(os.sep, "/"),
                              "content": data.decode("utf-8", errors="replace")})
                if len(files) >= MAX_FILES:
                    return files
        return files
