"""No-shell command execution inside a bounded bubblewrap sandbox."""
from __future__ import annotations

from dataclasses import dataclass
import os
import resource
import shutil
import subprocess


class SandboxUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class SandboxPolicy:
    network: bool = False
    memory_bytes: int = 1_000_000_000
    cpu_seconds: int = 120
    output_bytes: int = 200_000
    read_paths: tuple[str, ...] = ()


def _limits(policy: SandboxPolicy):
    def apply() -> None:
        resource.setrlimit(resource.RLIMIT_CPU, (policy.cpu_seconds, policy.cpu_seconds + 1))
        resource.setrlimit(resource.RLIMIT_AS, (policy.memory_bytes, policy.memory_bytes))
        resource.setrlimit(resource.RLIMIT_FSIZE, (100_000_000, 100_000_000))
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
        os.setsid()
    return apply


class SandboxRunner:
    def __init__(self, executable: str | None = None):
        self.executable = executable or shutil.which("bwrap") or ""

    def available(self) -> bool:
        return bool(self.executable and os.path.isfile(self.executable))

    def _argv(self, command: list[str], cwd: str, policy: SandboxPolicy,
              env: dict[str, str]) -> list[str]:
        if not self.available():
            raise SandboxUnavailable("bubblewrap isolation is required for learner evidence")
        argv = [self.executable, "--die-with-parent", "--new-session", "--unshare-pid",
                "--unshare-ipc", "--unshare-uts", "--clearenv"]
        if not policy.network:
            argv.append("--unshare-net")
        mounted = set()
        for path in ("/usr", "/bin", "/lib", "/lib64", "/usr/local", "/etc", "/opt"):
            if os.path.exists(path):
                argv += ["--ro-bind", path, path]
                mounted.add(os.path.realpath(path))
        for path in policy.read_paths:
            real = os.path.realpath(path)
            if os.path.exists(real) and real not in mounted:
                argv += ["--ro-bind", real, real]
                mounted.add(real)
        argv += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
                 "--bind", cwd, cwd, "--chdir", cwd]
        for key, value in sorted(env.items()):
            argv += ["--setenv", key, value]
        return [*argv, "--", *command]

    def run(self, command: list[str] | tuple[str, ...], *, cwd: str, stdin: str = "",
            timeout: int = 30, policy: SandboxPolicy | None = None,
            env: dict[str, str] | None = None) -> dict:
        if not isinstance(command, (list, tuple)) or not command:
            raise ValueError("assessment command must be a non-empty argv array")
        if any(not isinstance(arg, str) or not arg or "\0" in arg for arg in command):
            raise ValueError("assessment argv contains an invalid argument")
        policy = policy or SandboxPolicy()
        command = list(command)
        if not os.path.isabs(command[0]):
            resolved = shutil.which(command[0])
            if not resolved:
                raise ValueError(f"assessment executable {command[0]!r} is unavailable")
            command[0] = resolved
        base_path = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/bin"
        clean_env = {"PATH": base_path, "HOME": "/tmp",
                     "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
        for key, value in (env or {}).items():
            if key in {"LANG", "LC_ALL"} and isinstance(value, str):
                clean_env[key] = value
        argv = self._argv(command, os.path.realpath(cwd), policy, clean_env)
        try:
            process = subprocess.run(argv, input=stdin, text=True, capture_output=True,
                                     timeout=timeout, preexec_fn=_limits(policy))
            output = (process.stdout + ("\n" + process.stderr if process.stderr else "")).strip()
            clipped = len(output.encode("utf-8", errors="replace")) > policy.output_bytes
            if clipped:
                output = output[-policy.output_bytes:]
            return {"passed": process.returncode == 0, "argv": list(command),
                    "exitCode": process.returncode, "output": output,
                    "timedOut": False, "outputClipped": clipped}
        except subprocess.TimeoutExpired as exc:
            output = ((exc.stdout or "") + (exc.stderr or ""))[-policy.output_bytes:]
            return {"passed": False, "argv": list(command), "exitCode": None,
                    "output": output, "timedOut": True, "outputClipped": False}
