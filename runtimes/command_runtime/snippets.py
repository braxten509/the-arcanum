"""Disposable snippet project preparation, diagnosis, and execution."""
from __future__ import annotations

import json
import os
import subprocess

from .. import common
from .templates import file_argv, substitute

SNIPPET_MAX = 20_000


class SnippetMixin:
    def _snippet_dir(self, scratch_base):
        if not self.scaffold_cmd:
            os.makedirs(scratch_base, exist_ok=True)
            try:
                self._install_validation_project_dependencies(scratch_base)
            except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
                return scratch_base, "dependency install failed: " + str(exc)[-500:]
            return scratch_base, None
        project = os.path.join(scratch_base, "Snippet")
        try:
            self.scaffold(project, "Snippet")
            self._install_validation_project_dependencies(project)
        except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
            return project, "scaffold failed: " + str(exc)[-500:]
        return project, None

    def _install_validation_project_dependencies(self, project_dir):
        if not self.validation_dependencies or self.validation_shared_environment:
            return
        if not self.validation_project_package_cmd:
            raise RuntimeError("validation dependencies are declared but this runtime has no "
                               "validation project package command")
        marker = os.path.join(project_dir, ".arcanum-validation-dependencies.json")
        wanted = json.dumps(self.validation_dependencies, separators=(",", ":"))
        try:
            with open(marker, encoding="utf-8") as handle:
                if handle.read() == wanted:
                    return
        except OSError:
            pass
        for dependency in self.validation_dependencies:
            if (not isinstance(dependency, str) or not dependency.strip()
                    or dependency.lstrip().startswith("-")
                    or any(ord(char) < 32 for char in dependency)):
                raise RuntimeError(f"invalid validation dependency {dependency!r}")
            process = subprocess.run(
                substitute(self.validation_project_package_cmd,
                           dir=project_dir, package=dependency),
                cwd=project_dir, capture_output=True, text=True, timeout=600)
            if process.returncode:
                raise RuntimeError((process.stdout + process.stderr)[-3000:])
        common.atomic_write(marker, wanted)

    def snippet_diagnostics(self, scratch_base, code, env=None):
        can_check = bool(self.build_cmd or self.check_cmd)
        if not can_check or len(code) > SNIPPET_MAX or not self.available():
            return {"ok": can_check, "diags": []}
        scratch, error = self._snippet_dir(scratch_base)
        if error:
            return {"ok": False, "diags": [], "output": error}
        with common.snippet_lock:
            if self.build_cmd:
                common.atomic_write(os.path.join(scratch, self.entry), code)
                try:
                    process = subprocess.run(self.build_cmd, cwd=scratch, env=env,
                                             capture_output=True, text=True,
                                             timeout=self.build_timeout)
                except (subprocess.TimeoutExpired, OSError):
                    return {"ok": False, "diags": []}
                output = process.stdout + process.stderr
                diagnostics = [row for row in self._parse_diags(output, scratch, self.entry)
                               if row["file"].endswith(self.entry)]
                if process.returncode and not diagnostics:
                    return {"ok": False, "diags": [],
                            "output": output.strip() or "scratch project build failed"}
                return {"ok": True, "diags": diagnostics}
            path = os.path.join(scratch, "check-" + self.entry)
            common.atomic_write(path, code)
            return {"ok": True, "diags": self._check_file(path, self.entry, env=env)}

    def run_snippet(self, scratch_base, code, stdin_text, env=None):
        if not self.available():
            return {"ok": False, "output": f"ERROR: {self._exe() or self.NAME} not found."}
        if len(code) > SNIPPET_MAX:
            return {"ok": False, "output": "snippet too large"}
        scratch, error = self._snippet_dir(scratch_base)
        if error:
            return {"ok": False, "output": error}
        if self.snippet_run_cmd:
            argv = substitute(self.snippet_run_cmd, dir=scratch, entry=self.entry)
        elif self.cmd:
            argv = file_argv(self.cmd, self.entry)
        else:
            argv = substitute(self.run_cmd, dir=scratch, entry=self.entry)
        try:
            with common.snippet_lock:
                common.atomic_write(os.path.join(scratch, self.entry), code)
                if self.build_cmd:
                    build = subprocess.run(self.build_cmd, cwd=scratch, env=env,
                                           capture_output=True, text=True,
                                           timeout=self.build_timeout)
                    if build.returncode != 0:
                        output = common.join_output(build.stdout, build.stderr)
                        return {"ok": False, "output": output or "(build failed)",
                                "exit": build.returncode}
                process = subprocess.run(argv, cwd=scratch, env=env, input=stdin_text or "",
                                         capture_output=True, text=True,
                                         timeout=common.SNIPPET_TIMEOUT)
            output = common.join_output(process.stdout, process.stderr)
            return {"ok": process.returncode == 0, "output": output or "(no output)",
                    "exit": process.returncode}
        except subprocess.TimeoutExpired:
            return {"ok": False, "output": f"(KILLED: exceeded {common.SNIPPET_TIMEOUT}s — "
                    "infinite loop, or waiting for input the lab didn't provide?)"}
        except OSError as exc:
            return {"ok": False, "output": f"(run failed to start: {exc})"}
