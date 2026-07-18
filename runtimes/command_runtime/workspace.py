"""Project scaffolding, starter files, and bounded source collection."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import runtimes.common as common
from .templates import substitute

MAX_FILES = 400
EXCLUDE_DIRS = {"node_modules", "__pycache__", "venv", "bin", "obj", "build", "out", "target"}


class WorkspaceMixin:
    def project_file(self, project_name):
        return self.project_file_tpl.replace("{project}", project_name)

    def scaffold(self, project_dir, project_name):
        if os.path.isfile(os.path.join(project_dir, self.project_file(project_name))):
            return "already exists"
        os.makedirs(project_dir, exist_ok=True)
        if self.scaffold_cmd:
            process = subprocess.run(
                substitute(self.scaffold_cmd, project=project_name, dir=project_dir),
                capture_output=True, text=True, timeout=self.build_timeout)
            if process.returncode != 0:
                raise RuntimeError(process.stdout + process.stderr)
            return "created"
        common.atomic_write(os.path.join(project_dir, self.entry), self.starter)
        return "created"

    def required_files(self, project_name):
        files = [self.entry]
        project_file = self.project_file(project_name)
        if project_file != self.entry and project_file not in files:
            files.append(project_file)
        return files

    def _scaffold_to(self, target_dir, project_name):
        process = subprocess.run(
            substitute(self.scaffold_cmd, project=project_name, dir=target_dir),
            capture_output=True, text=True, timeout=self.build_timeout)
        if process.returncode != 0:
            raise RuntimeError(process.stdout + process.stderr)

    def seed_workspace(self, project_dir, project_name, force=False, only_missing=False):
        """Seed required files without touching existing learner work by default."""
        os.makedirs(project_dir, exist_ok=True)
        required = self.required_files(project_name)
        existing = [path for path in required if os.path.isfile(os.path.join(project_dir, path))]
        missing = [path for path in required if path not in existing]
        if existing and not force and not only_missing:
            return {"ok": False, "conflicts": existing, "missing": missing, "seeded": []}
        if only_missing and not missing:
            return {"ok": True, "conflicts": existing, "missing": [], "seeded": []}
        if self.scaffold_cmd:
            if only_missing:
                temporary = tempfile.mkdtemp()
                try:
                    self._scaffold_to(temporary, project_name)
                    seeded = []
                    for path in missing:
                        source = os.path.join(temporary, path)
                        if os.path.isfile(source):
                            target = os.path.join(project_dir, path)
                            os.makedirs(os.path.dirname(target) or project_dir, exist_ok=True)
                            shutil.copyfile(source, target)
                            seeded.append(path)
                    return {"ok": True, "conflicts": existing, "missing": missing,
                            "seeded": seeded}
                finally:
                    shutil.rmtree(temporary, ignore_errors=True)
            self._scaffold_to(project_dir, project_name)
            return {"ok": True, "conflicts": existing, "missing": missing, "seeded": required}
        if not only_missing or self.entry in missing:
            common.atomic_write(os.path.join(project_dir, self.entry), self.starter)
            return {"ok": True, "conflicts": existing, "missing": missing,
                    "seeded": [self.entry]}
        return {"ok": True, "conflicts": existing, "missing": missing, "seeded": []}

    def starter_content(self, project_name, relative):
        if not self.scaffold_cmd:
            return self.starter if relative == self.entry else ""
        temporary = tempfile.mkdtemp()
        try:
            self._scaffold_to(temporary, project_name)
            path = os.path.join(temporary, relative)
            if os.path.isfile(path):
                with open(path, encoding="utf-8", errors="replace") as handle:
                    return handle.read()
            return ""
        finally:
            shutil.rmtree(temporary, ignore_errors=True)

    def collect_code(self, project_dir):
        files = []
        skip = EXCLUDE_DIRS | self.exclude_dirs
        for dirpath, dirnames, filenames in os.walk(project_dir):
            dirnames[:] = sorted(name for name in dirnames
                                  if not name.startswith(".") and name not in skip)
            for filename in sorted(filenames):
                if not filename.endswith(self.CODE_EXT):
                    continue
                if len(files) >= MAX_FILES:
                    return files
                path = os.path.join(dirpath, filename)
                try:
                    with open(path, encoding="utf-8", errors="replace") as handle:
                        files.append((os.path.relpath(path, project_dir), handle.read()))
                except OSError:
                    pass
        return files
