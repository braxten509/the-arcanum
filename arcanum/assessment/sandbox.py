"""No-shell command execution inside a bounded bubblewrap sandbox."""
from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import os
import resource
import signal
import shutil
import subprocess
import tempfile


class SandboxUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class SandboxPolicy:
    network: bool = False
    memory_bytes: int = 1_000_000_000
    cpu_seconds: int = 120
    output_bytes: int = 200_000
    read_paths: tuple[str, ...] = ()
    allowed_environment: tuple[str, ...] = (
        "LANG", "LC_ALL", "PATH", "VIRTUAL_ENV", "DOTNET_ROOT", "JAVA_HOME",
    )


def policy_for_runtime(runtime, policy: SandboxPolicy | None = None) -> SandboxPolicy:
    """Merge only trusted profile-owned read resources into a sandbox policy."""
    base = policy or SandboxPolicy()
    read_paths = tuple(dict.fromkeys((
        *base.read_paths, *getattr(runtime, "assessment_read_paths", ()))))
    allowed = tuple(dict.fromkeys((
        *base.allowed_environment,
        *getattr(runtime, "assessment_environment", {}).keys())))
    return replace(base, read_paths=read_paths, allowed_environment=allowed)


def environment_for_runtime(runtime, environment: dict[str, str] | None = None) -> dict[str, str]:
    configured = dict(getattr(runtime, "assessment_environment", {}))
    configured.update(environment or {})
    return configured


@lru_cache(maxsize=1)
def _systemd_scope() -> str:
    """Return a working user-scope launcher for real-memory accounting."""
    executable = shutil.which("systemd-run") or ""
    if not executable:
        return ""
    try:
        probe = subprocess.run(
            [executable, "--user", "--scope", "--quiet",
             "--property=MemoryMax=16777216", "/usr/bin/true"],
            capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return executable if probe.returncode == 0 else ""


def _limits(policy: SandboxPolicy, address_space_limit: bool):
    def apply() -> None:
        resource.setrlimit(resource.RLIMIT_CPU, (policy.cpu_seconds, policy.cpu_seconds + 1))
        if address_space_limit:
            resource.setrlimit(resource.RLIMIT_AS, (policy.memory_bytes, policy.memory_bytes))
        resource.setrlimit(resource.RLIMIT_FSIZE, (100_000_000, 100_000_000))
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
        os.setsid()
    return apply


def _captured_output(handle, limit: int) -> tuple[str, str, bool]:
    handle.flush()
    handle.seek(0, os.SEEK_END)
    size = handle.tell()
    handle.seek(max(0, size - limit))
    raw = handle.read().decode("utf-8", errors="replace")
    return raw.strip(), raw, size > limit


class SandboxRunner:
    def __init__(self, executable: str | None = None):
        self.executable = executable or shutil.which("bwrap") or ""

    def available(self) -> bool:
        return bool(self.executable and os.path.isfile(self.executable))

    def _argv(self, command: list[str], cwd: str, home: str,
              policy: SandboxPolicy, env: dict[str, str]) -> list[str]:
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
        if home != "/tmp":
            argv += ["--bind", home, home]
        for key, value in sorted(env.items()):
            argv += ["--setenv", key, value]
        return [*argv, "--", *command]

    def run(self, command: list[str] | tuple[str, ...], *, cwd: str, stdin: str = "",
            timeout: int = 30, policy: SandboxPolicy | None = None,
            env: dict[str, str] | None = None, home: str | None = None) -> dict:
        if not isinstance(command, (list, tuple)) or not command:
            raise ValueError("assessment command must be a non-empty argv array")
        if any(not isinstance(arg, str) or not arg or "\0" in arg for arg in command):
            raise ValueError("assessment argv contains an invalid argument")
        policy = policy or SandboxPolicy()
        if policy.memory_bytes < 1 or policy.cpu_seconds < 1 or policy.output_bytes < 1:
            raise ValueError("assessment resource limits must be positive")
        command = list(command)
        real_cwd = os.path.realpath(cwd)
        sandbox_home = os.path.realpath(home) if home else "/tmp"
        if home:
            assessment_root = os.path.dirname(real_cwd)
            if (not os.path.isdir(sandbox_home)
                    or os.path.commonpath((assessment_root, sandbox_home)) != assessment_root):
                raise ValueError("assessment home must be inside the disposable snapshot")
        base_path = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/bin"
        clean_env = {"PATH": base_path, "HOME": sandbox_home,
                     "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
        for key, value in (env or {}).items():
            if key in policy.allowed_environment and isinstance(value, str) and "\0" not in value:
                clean_env[key] = value
        if not os.path.isabs(command[0]):
            # Resolve against the PATH that exists inside bubblewrap. The host PATH
            # may prefer aliases such as /sbin/python3 even though /sbin is not one
            # of the sandbox's mounted roots, producing an infrastructure-looking
            # execvp failure before learner code can run.
            resolved = shutil.which(command[0], path=clean_env["PATH"])
            if not resolved:
                raise ValueError(f"assessment executable {command[0]!r} is unavailable")
            command[0] = resolved
        argv = self._argv(command, real_cwd, sandbox_home, policy, clean_env)
        scope = _systemd_scope()
        address_space_limit = not bool(scope)
        if scope:
            argv = [scope, "--user", "--scope", "--quiet",
                    f"--property=MemoryMax={policy.memory_bytes}",
                    "--property=MemorySwapMax=0", "--", *argv]
        try:
            with tempfile.TemporaryFile(mode="w+b") as capture:
                process = subprocess.Popen(
                    argv, stdin=subprocess.PIPE, stdout=capture, stderr=subprocess.STDOUT,
                    text=True, preexec_fn=_limits(policy, address_space_limit))
                try:
                    process.communicate(stdin, timeout=timeout)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.communicate()
                    output, raw_output, clipped = _captured_output(
                        capture, policy.output_bytes)
                    return {"passed": False, "argv": list(command), "exitCode": None,
                            "output": output, "rawOutput": raw_output, "timedOut": True,
                            "outputClipped": clipped,
                            "memoryBoundary": "cgroup-v2" if scope
                            else "rlimit-address-space"}
                output, raw_output, clipped = _captured_output(
                    capture, policy.output_bytes)
                return {"passed": process.returncode == 0, "argv": list(command),
                        "exitCode": process.returncode, "output": output,
                        "rawOutput": raw_output,
                        "timedOut": False, "outputClipped": clipped,
                        "memoryBoundary": "cgroup-v2" if scope
                        else "rlimit-address-space"}
        except OSError as exc:
            return {"passed": False, "argv": list(command), "exitCode": None,
                    "output": f"assessment process could not start: {exc}",
                    "timedOut": False, "outputClipped": False,
                    "memoryBoundary": "cgroup-v2" if scope else "rlimit-address-space"}
