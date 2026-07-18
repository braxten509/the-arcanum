"""Compatibility facade for the single TOML-driven command runtime.

Language behavior remains configuration-only. Cohesive filesystem, diagnostic,
snippet, and execution operations live under :mod:`runtimes.command_runtime`.

Important runtime TOML keys include ``command``, ``runCommand``, ``buildCommand``,
``checkCommand``, ``scaffoldCommand``, ``packageCommand``, ``entryFile``,
``validationDependencies``, and the optional trusted ``assessmentCommands`` table.
All command values are argv arrays; shell strings are never accepted.
"""
from __future__ import annotations

import os
import shutil

from .command_runtime import (DiagnosticsMixin, ExecutionMixin, SnippetMixin,
                              WorkspaceMixin)

RUN_TIMEOUT = 60


class CommandRuntime(WorkspaceMixin, DiagnosticsMixin, SnippetMixin, ExecutionMixin):
    """One configuration-driven runtime for every supported language."""

    def __init__(self, cfg):
        self.NAME = cfg.get("name") or "custom"
        self.LANGUAGE = cfg.get("language") or self.NAME
        self.cmd = list(cfg.get("command") or [])
        self.run_cmd = list(cfg.get("runCommand") or [])
        self.snippet_run_cmd = list(cfg.get("snippetRunCommand") or [])
        self.build_cmd = list(cfg.get("buildCommand") or [])
        self.check_cmd = list(cfg.get("checkCommand") or [])
        self.scaffold_cmd = list(cfg.get("scaffoldCommand") or [])
        self.package_cmd = list(cfg.get("packageCommand") or [])
        self.validation_dependencies = list(cfg.get("validationDependencies") or [])
        self.validation_shared_environment = bool(cfg.get("validationPackageCommand"))
        project_package = cfg.get("validationProjectPackageCommand") or []
        if not project_package and not cfg.get("validationPackageCommand"):
            project_package = self.package_cmd
        self.validation_project_package_cmd = list(project_package)
        self.assessment_commands = {
            str(name): list(argv)
            for name, argv in (cfg.get("assessmentCommands") or {}).items()
            if isinstance(argv, list)
        }
        self.diag_re = cfg.get("diagRegex") or ""
        self.entry = cfg.get("entryFile") or "main.txt"
        self.starter = cfg.get("starterCode") or ""
        self.project_file_tpl = cfg.get("projectFile") or self.entry
        self.exclude_dirs = set(cfg.get("excludeDirs") or [])
        self.build_timeout = cfg.get("buildTimeout") or 180
        self.run_timeout = cfg.get("runTimeout") or RUN_TIMEOUT
        extension = cfg.get("newFileExt") or os.path.splitext(self.entry)[1] or ".txt"
        self.CODE_EXT = tuple(cfg.get("codeExt") or (extension, ".md", ".txt", ".json"))

    def _exe(self):
        for argv in (self.cmd, self.run_cmd, self.build_cmd):
            if argv:
                return argv[0]
        return None

    def available(self):
        executable = self._exe()
        return bool(executable and shutil.which(executable))
