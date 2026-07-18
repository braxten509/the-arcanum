"""Runtime-neutral snippet/project execution orchestration."""
from __future__ import annotations

from runtimes import common as runtime_common
from runtimes.validation_environment import (ValidationEnvironmentError,
                                             ensure_validation_environment,
                                             validation_subprocess_env)


class ExecutionService:
    def __init__(self, catalog, workspaces):
        self.catalog = catalog
        self.workspaces = workspaces

    def run_snippet(self, tome_id: str, code: str, stdin: str = "") -> dict:
        runtime = self.catalog.snippet_runtime(tome_id)
        try:
            ensure_validation_environment(tome_id)
            environment = validation_subprocess_env(tome_id)
        except ValidationEnvironmentError as exc:
            return {"ok": False, "output": f"validation dependencies: {exc}"}
        return runtime.run_snippet(self.workspaces.snippet_base(tome_id), code, stdin,
                                   env=environment)

    def snippet_diagnostics(self, tome_id: str, code: str) -> dict:
        runtime = self.catalog.snippet_runtime(tome_id)
        try:
            ensure_validation_environment(tome_id)
            environment = validation_subprocess_env(tome_id)
        except ValidationEnvironmentError as exc:
            return {"ok": False, "diags": [],
                    "output": f"validation dependencies: {exc}"}
        return runtime.snippet_diagnostics(
            self.workspaces.snippet_base(tome_id), code, env=environment)

    def run_project(self, tome_id: str, files: list[dict], stdin: str = "") -> dict:
        self.workspaces.write_files(tome_id, files)
        return self.catalog.runtime(tome_id).run_project(
            self.workspaces.project_dir(tome_id), stdin)

    @staticmethod
    def cancel_current() -> dict:
        return {"ok": True, "cancelled": runtime_common.cancel_current()}

    def diagnostics(self, tome_id: str, files: list[dict]) -> dict:
        self.workspaces.write_files(tome_id, files)
        return self.catalog.runtime(tome_id).build_diagnostics(
            self.workspaces.project_dir(tome_id))

    def add_package(self, tome_id: str, package: str) -> dict:
        return self.catalog.runtime(tome_id).add_package(
            self.workspaces.project_dir(tome_id), package)
