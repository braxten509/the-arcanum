"""Project scaffolding, starter files, and bounded source collection."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import runtimes.common as common
from .templates import substitute

MAX_FILES = 400
EXCLUDE_DIRS = {
    "node_modules", "__pycache__", "venv", "bin", "obj", "build", "out", "target",
}
# Reproducibility and evaluation evidence commonly uses these formats regardless
# of the project's primary language. A runtime's codeExt remains additive.
EVIDENCE_EXTENSIONS = {
    ".md", ".txt", ".json", ".jsonl", ".toml", ".yaml", ".yml", ".csv",
}
EVIDENCE_FILENAMES = {
    "Dockerfile", "Makefile", "Modelfile", "Procfile", "Justfile",
}


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

    def collect_code_report(self, project_dir):
        files = []
        omitted = []
        unreadable = []
        unsafe = []
        skip = EXCLUDE_DIRS | self.exclude_dirs
        extensions = tuple(sorted(set(self.CODE_EXT) | EVIDENCE_EXTENSIONS))
        root = os.path.realpath(project_dir)
        for dirpath, dirnames, filenames in os.walk(project_dir):
            kept = []
            for name in sorted(dirnames):
                path = os.path.join(dirpath, name)
                if name.startswith(".") or name in skip:
                    continue
                if os.path.islink(path):
                    unsafe.append(os.path.relpath(path, project_dir) + "/")
                    continue
                kept.append(name)
            dirnames[:] = kept
            for filename in sorted(filenames):
                if filename not in EVIDENCE_FILENAMES and not filename.endswith(extensions):
                    continue
                path = os.path.join(dirpath, filename)
                if os.path.islink(path):
                    unsafe.append(os.path.relpath(path, project_dir))
                    continue
                try:
                    inside = os.path.commonpath((os.path.realpath(path), root)) == root
                except ValueError:
                    inside = False
                if not inside:
                    unsafe.append(os.path.relpath(path, project_dir))
                    continue
                if len(files) >= MAX_FILES:
                    omitted.append(os.path.relpath(
                        os.path.join(dirpath, filename), project_dir))
                    continue
                try:
                    with open(path, encoding="utf-8", errors="replace") as handle:
                        files.append((os.path.relpath(path, project_dir), handle.read()))
                except OSError:
                    unreadable.append(os.path.relpath(path, project_dir))
        return {
            "files": files,
            "limit": MAX_FILES,
            "omitted": omitted,
            "unreadable": unreadable,
            "unsafe": unsafe,
            "complete": not omitted and not unreadable and not unsafe,
        }

    def collect_code(self, project_dir):
        return self.collect_code_report(project_dir)["files"]
