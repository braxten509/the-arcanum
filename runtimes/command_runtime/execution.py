"""Project command resolution, verification, launch, and package installation."""
from __future__ import annotations

import os
import re
import subprocess

import runtimes.assessment_commands as assessment_commands
import runtimes.common as common
import runtimes.launch_probe as launch_probe
from .templates import file_argv, substitute


class ExecutionMixin:
    def project_command(self, project_dir, args=()):
        argv = (substitute(self.run_cmd, dir=project_dir, entry=self.entry)
                if self.run_cmd else file_argv(self.cmd, self.entry))
        safe_args = []
        for argument in args or ():
            if not isinstance(argument, str) or any(ord(char) < 32 for char in argument):
                raise ValueError(f"invalid project argument {argument!r}")
            safe_args.append(argument)
        return [*argv, *safe_args]

    def assessment_command(self, command_ref, project_dir, args=()):
        return assessment_commands.resolve(self, command_ref, project_dir, args)

    def verify_project(self, project_dir, env=None):
        if not self.available():
            return {"ok": False, "output": f"ERROR: {self._exe() or self.NAME} not found.",
                    "commands": []}
        try:
            if self.build_cmd:
                with common.project_lock:
                    process = subprocess.run(self.build_cmd, cwd=project_dir, env=env,
                                             capture_output=True, text=True,
                                             timeout=self.build_timeout)
                return {"ok": process.returncode == 0,
                        "output": common.join_output(process.stdout, process.stderr)
                                  or "(build produced no output)",
                        "exit": process.returncode, "commands": [list(self.build_cmd)]}
            if self.check_cmd:
                outputs, commands = [], []
                for relative, _source in self.collect_code(project_dir):
                    if not relative.endswith(self.CODE_EXT[0]):
                        continue
                    command = file_argv(self.check_cmd, os.path.join(project_dir, relative))
                    commands.append(command)
                    process = subprocess.run(command, cwd=project_dir, env=env,
                                             capture_output=True, text=True, timeout=30)
                    if process.returncode:
                        outputs.append(common.join_output(process.stdout, process.stderr))
                return {"ok": not outputs, "output": "\n".join(outputs)
                        or "(syntax/build check passed)", "exit": 1 if outputs else 0,
                        "commands": commands}
            return {"ok": True, "output": "(runtime has no separate build step)",
                    "exit": 0, "commands": []}
        except subprocess.TimeoutExpired:
            return {"ok": False, "output": "(build timed out)", "commands": []}
        except OSError as exc:
            return {"ok": False, "output": f"(build failed to start: {exc})", "commands": []}

    def smoke_project(self, project_dir, stdin_text=None, env=None, timeout=None):
        return launch_probe.smoke_project(self, project_dir, stdin_text, env, timeout)

    def run_project(self, project_dir, stdin_text, args=(), env=None, timeout=None):
        if not self.available():
            return {"ok": False, "output": f"ERROR: {self._exe() or self.NAME} not found."}
        try:
            argv = self.project_command(project_dir, args)
        except ValueError as exc:
            return {"ok": False, "output": str(exc), "command": []}
        return common.run_cancellable(argv, stdin_text, timeout or self.run_timeout,
                                      cwd=project_dir, env=env)

    def add_package(self, project_dir, package):
        if not self.package_cmd:
            return {"ok": False,
                    "output": f"package installation is not supported by the {self.NAME} runtime"}
        package = re.sub(r"[^A-Za-z0-9._-]", "", package or "")
        if not package:
            return {"ok": False, "output": "bad package name"}
        process = subprocess.run(substitute(self.package_cmd, dir=project_dir, package=package),
                                 capture_output=True, text=True, timeout=300)
        return {"ok": process.returncode == 0,
                "output": (process.stdout + process.stderr)[-3000:]}
