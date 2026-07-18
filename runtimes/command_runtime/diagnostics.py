"""Config-driven build, check, and diagnostic parsing."""
from __future__ import annotations

import os
import re
import subprocess

import runtimes.common as common
from .templates import file_argv


class DiagnosticsMixin:
    def _parse_diags(self, output, base, default_file):
        if not self.diag_re:
            return []
        diagnostics, seen = [], set()
        for match in re.finditer(self.diag_re, output, re.MULTILINE):
            groups = match.groupdict()
            filename = groups.get("file") or default_file
            if os.path.isabs(filename):
                filename = os.path.relpath(filename, base)
            key = (filename, groups.get("line"), groups.get("col"),
                   groups.get("code"), groups.get("msg"))
            if key in seen:
                continue
            seen.add(key)
            diagnostics.append({
                "file": filename, "line": int(groups.get("line") or 1),
                "col": int(groups.get("col") or 1), "sev": groups.get("sev") or "error",
                "code": groups.get("code") or "check",
                "msg": (groups.get("msg") or "").strip() or "error",
            })
        return diagnostics

    def _check_file(self, path, relative, env=None):
        try:
            process = subprocess.run(file_argv(self.check_cmd, path), env=env,
                                     capture_output=True, text=True, timeout=30)
        except (subprocess.TimeoutExpired, OSError) as exc:
            return [{"file": relative, "line": 1, "col": 1, "sev": "error",
                     "code": "check", "msg": str(exc)}]
        if process.returncode == 0:
            return []
        output = (process.stdout + "\n" + process.stderr).strip()
        diagnostics = self._parse_diags(output, os.path.dirname(path) or ".", relative)
        for diagnostic in diagnostics:
            diagnostic["file"] = relative
        return diagnostics or [{"file": relative, "line": 1, "col": 1, "sev": "error",
                                "code": "check", "msg": output[-500:] or "check failed"}]

    def try_build(self, project_dir):
        if self.build_cmd:
            if not os.path.isdir(project_dir) or not self.available():
                return "(no build attempted: project or toolchain missing)"
            try:
                with common.project_lock:
                    process = subprocess.run(self.build_cmd, cwd=project_dir,
                                             capture_output=True, text=True,
                                             timeout=self.build_timeout)
                return (process.stdout + process.stderr).strip() or "(build produced no output — success)"
            except subprocess.TimeoutExpired:
                return "(build timed out)"
            except OSError as exc:
                return f"(build failed to start: {exc})"
        if not self.check_cmd:
            return "(this runtime has no build step)"
        problems = []
        for relative, _source in self.collect_code(project_dir):
            if relative.endswith(self.CODE_EXT[0]):
                problems += [f"{row['file']}({row['line']},{row['col']}): error: {row['msg']}"
                             for row in self._check_file(os.path.join(project_dir, relative), relative)]
        return "\n".join(problems) or "(syntax OK — no errors)"

    def build_diagnostics(self, project_dir):
        if self.build_cmd:
            return {"ok": True,
                    "diags": self._parse_diags(self.try_build(project_dir), project_dir, self.entry)}
        diagnostics = []
        if self.check_cmd:
            for relative, _source in self.collect_code(project_dir):
                if relative.endswith(self.CODE_EXT[0]):
                    diagnostics += self._check_file(os.path.join(project_dir, relative), relative)
        return {"ok": True, "diags": diagnostics}
