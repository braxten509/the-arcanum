"""Internal/external learner workspace policy and filesystem adapter."""
from __future__ import annotations

import json
import os
import subprocess
import sys

from runtimes import common as runtime_common
from runtimes.common import atomic_write

from arcanum.catalog import TomeCatalogService, TomePaths


class WorkspaceService:
    def __init__(self, catalog: TomeCatalogService, paths: TomePaths):
        self.catalog = catalog
        self.paths = paths

    @staticmethod
    def _read_json(path: str, default):
        try:
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            return default

    def ensure_save(self, tome_id: str) -> str:
        path = self.paths.save(tome_id)
        os.makedirs(path, exist_ok=True)
        return path

    def state_path(self, tome_id: str) -> str:
        self.ensure_save(tome_id)
        return self.paths.state(tome_id)

    def grades_dir(self, tome_id: str) -> str:
        path = self.paths.grades(tome_id)
        os.makedirs(path, exist_ok=True)
        return path

    def external_path(self, tome_id: str) -> str:
        workspace = self._read_json(self.state_path(tome_id), {}).get("workspace") or {}
        if workspace.get("enabled"):
            path = os.path.expanduser(workspace.get("dir") or "")
            if os.path.isabs(path) and os.path.isdir(path):
                return path
        return ""

    def project_dir(self, tome_id: str) -> str:
        return self.external_path(tome_id) or os.path.join(
            self.ensure_save(tome_id), "workspace", self.catalog.project_name(tome_id))

    def snapshot_files(self, tome_id: str) -> dict:
        runtime = self.catalog.runtime(tome_id)
        project = self.project_dir(tome_id)
        files = [{"path": path, "content": content}
                 for path, content in runtime.collect_code(project)] if os.path.isdir(project) else []
        project_file = os.path.join(project, runtime.project_file(
            self.catalog.project_name(tome_id)))
        return {"files": files, "exists": os.path.isfile(project_file)}

    def write_files(self, tome_id: str, files: list[dict]) -> None:
        project = self.project_dir(tome_id)
        for item in files or []:
            full = runtime_common.safe_join(project, item["path"])
            os.makedirs(os.path.dirname(full), exist_ok=True)
            atomic_write(full, item["content"])

    def scaffold(self, tome_id: str) -> dict:
        if self.external_path(tome_id):
            return {"ok": True, "result": "external workspace — managed by your own tools"}
        project = self.project_dir(tome_id)
        os.makedirs(os.path.dirname(project), exist_ok=True)
        result = self.catalog.runtime(tome_id).scaffold(
            project, self.catalog.project_name(tome_id))
        return {"ok": True, "result": result}

    def seed_external(self, tome_id: str, directory: str, mode: str = "") -> dict:
        path = os.path.expanduser(directory)
        if not (os.path.isabs(path) and os.path.isdir(path)):
            raise ValueError("not an existing absolute folder")
        runtime = self.catalog.runtime(tome_id)
        if not runtime.available():
            raise RuntimeError(f"{runtime.LANGUAGE} toolchain not found on this machine")
        return runtime.seed_workspace(
            path, self.catalog.project_name(tome_id), force=mode == "force",
            only_missing=mode == "missing")

    @staticmethod
    def check_directory(directory: str) -> dict:
        path = os.path.expanduser(directory)
        return {"abs": os.path.isabs(path), "exists": os.path.exists(path),
                "isdir": os.path.isdir(path)}

    @staticmethod
    def open_directory(directory: str) -> dict:
        path = os.path.expanduser(directory)
        if not (os.path.isabs(path) and os.path.isdir(path)):
            raise ValueError("not an existing absolute folder")
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, path], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        return {"ok": True}

    def starter_file(self, tome_id: str, relative: str) -> dict:
        runtime = self.catalog.runtime(tome_id)
        if not runtime.available():
            raise RuntimeError(f"{runtime.LANGUAGE} toolchain not found on this machine")
        return {"ok": True, "path": relative,
                "content": runtime.starter_content(
                    self.catalog.project_name(tome_id), relative)}

    def snippet_base(self, tome_id: str) -> str:
        return self.paths.snippet(self.catalog.snippet_runtime(tome_id).NAME)
