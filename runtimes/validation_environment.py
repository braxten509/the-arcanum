"""Isolated, runtime-declared dependencies used only while validating a tome.

A tome declares *what* it needs with ``[runtime].validationDependencies``.  The
named runtime declares *how* environment-scoped packages are provisioned with
argv-only commands and environment substitutions.  Project-scoped package
managers are handled by ``runtimes.command_runtime.CommandRuntime`` inside each scratch
project instead (for example, NuGet packages in a temporary .NET project).

Nothing here installs into a learner workspace or the host interpreter.  Shared
validation environments live under .tome-build/validation-envs and are content
addressed by the complete provisioning contract.
"""
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import tomllib

from .config import find_runtime_profile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join(REPO, ".tome-build")
RUNTIME_CONFIG_DIR = os.path.join(REPO, "global-configs", "runtimes")
ENV_ROOT = os.path.join(BUILD_DIR, "validation-envs")
_ENV_TOKEN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def headless_validation_env(base=None):
    """Return an environment that cannot open automated work on the user's desktop.

    Tome workers and validators execute authored programs. Those programs may create a
    real window in normal mode, so inheriting DISPLAY/WAYLAND_DISPLAY makes every repeated
    validation visibly interrupt the desktop. SDL's dummy drivers keep Pygame programs
    executable while removing display variables is a runtime-neutral backstop for other
    GUI toolkits.
    """
    env = dict(os.environ if base is None else base)
    for key in ("DISPLAY", "WAYLAND_DISPLAY", "MIR_SOCKET"):
        env.pop(key, None)
    env["SDL_VIDEODRIVER"] = "dummy"
    env["SDL_AUDIODRIVER"] = "dummy"
    env["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    return env


class ValidationEnvironmentError(RuntimeError):
    """The declared validation dependency contract could not be provisioned."""


def _load_toml(path):
    with open(path, "rb") as handle:
        return tomllib.load(handle)


def validation_runtime_config(tid):
    """Return language defaults merged with this tome's runtime table."""
    manifest = os.path.join(REPO, "tomes", tid, "tome.toml")
    try:
        tome = _load_toml(manifest)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValidationEnvironmentError(
            f"cannot read tomes/{tid}/tome.toml before dependency provisioning: {exc}") from exc
    runtime = tome.get("runtime") or {}
    if not isinstance(runtime, dict):
        return {}
    name = runtime.get("name") or "custom"
    defaults = {}
    if isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_-]+", name):
        try:
            profile = find_runtime_profile(RUNTIME_CONFIG_DIR, name)
            if profile:
                defaults = _load_toml(profile)
        except tomllib.TOMLDecodeError as exc:
            raise ValidationEnvironmentError(
                f"runtime {name!r} cannot be read for dependency provisioning: {exc}") from exc
    return {**defaults, **runtime}


def declared_dependencies(tid):
    value = validation_runtime_config(tid).get("validationDependencies") or []
    return list(value) if isinstance(value, list) else []


def _expand(value, directory, base_env):
    value = str(value).replace("{dir}", directory)
    return _ENV_TOKEN.sub(lambda match: base_env.get(match.group(1), match.group(0)), value)


def _argv(command, directory, package=None):
    out = []
    for arg in command:
        value = str(arg).replace("{dir}", directory)
        if package is not None:
            value = value.replace("{package}", package)
        out.append(value)
    return out


def _contract(config):
    deps = config.get("validationDependencies") or []
    create = config.get("validationCreateCommand") or []
    package = config.get("validationPackageCommand") or []
    project_package = config.get("validationProjectPackageCommand") or []
    # A runtime's ordinary packageCommand is safe here because CommandRuntime only
    # invokes it inside a validator-created scratch project, never in learner files.
    if not project_package and not package:
        project_package = config.get("packageCommand") or []
    env = config.get("validationEnv") or {}
    return {
        "protocol": 1,
        "runtime": config.get("name") or "custom",
        "dependencies": deps,
        "create": create,
        "package": package,
        "projectPackage": project_package,
        "env": env,
    }


def _key(contract):
    encoded = json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def _environment_path(contract):
    runtime = re.sub(r"[^A-Za-z0-9_-]", "-", str(contract["runtime"])) or "custom"
    return os.path.join(ENV_ROOT, f"{runtime}-{_key(contract)}")


def _ready_overrides(contract):
    if not contract["dependencies"] or not contract["package"]:
        return {}
    directory = _environment_path(contract)
    marker = os.path.join(directory, ".arcanum-ready.json")
    if not os.path.isfile(marker):
        raise ValidationEnvironmentError(
            "the isolated validation environment is not provisioned; restart the harness "
            "phase so it can prepare the declared dependencies")
    base = os.environ.copy()
    return {str(key): _expand(value, directory, base)
            for key, value in contract["env"].items()}


def ready_validation_environment(tid):
    """Environment overrides for an already-provisioned tome dependency set."""
    return _ready_overrides(_contract(validation_runtime_config(tid)))


def validation_subprocess_env(tid):
    """A complete, dependency-ready, headless worker/validator environment."""
    env = os.environ.copy()
    env.update(ready_validation_environment(tid))
    return headless_validation_env(env)


def _run(command, directory, env, label, package=None):
    argv = _argv(command, directory, package)
    try:
        proc = subprocess.run(argv, cwd=REPO, env=env, capture_output=True, text=True,
                              timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValidationEnvironmentError(f"{label} failed to start: {exc}") from exc
    if proc.returncode:
        output = ((proc.stdout or "") + (proc.stderr or "")).strip()[-3000:]
        raise ValidationEnvironmentError(
            f"{label} exited {proc.returncode}: {output or '(no output)'}")


def ensure_validation_environment(tid):
    """Provision declared environment packages and return worker env overrides.

    Project-package-only runtimes return an empty override: their dependencies are
    installed later in each isolated scratch project by CommandRuntime.
    """
    config = validation_runtime_config(tid)
    contract = _contract(config)
    deps = contract["dependencies"]
    if not deps:
        return {}
    if (not isinstance(deps, list)
            or any(not isinstance(dep, str) or not dep.strip()
                   or dep.lstrip().startswith("-")
                   or any(ord(ch) < 32 for ch in dep) for dep in deps)):
        raise ValidationEnvironmentError(
            "validationDependencies must be an array of non-empty package strings")
    for key in ("create", "package", "projectPackage"):
        command = contract[key]
        if (not isinstance(command, list)
                or any(not isinstance(arg, str) or not arg for arg in command)):
            raise ValidationEnvironmentError(
                f"the validation dependency {key} command must be an argv array")
    if (not isinstance(contract["env"], dict)
            or any(not isinstance(key, str) or not isinstance(value, str)
                   for key, value in contract["env"].items())):
        raise ValidationEnvironmentError("validationEnv must be a string-to-string table")
    if not contract["package"]:
        if contract["projectPackage"]:
            return {}
        raise ValidationEnvironmentError(
            f"runtime {contract['runtime']!r} declares validationDependencies but defines "
            "neither validationPackageCommand nor a scratch-project packageCommand")

    directory = _environment_path(contract)
    marker = os.path.join(directory, ".arcanum-ready.json")
    # Environments are content addressed by the complete provisioning contract and
    # publish their marker only after every package is installed.  The author sandbox
    # intentionally sees this shared cache read-only, so a ready cache hit must remain
    # a genuinely read-only operation instead of opening the provisioning lock in a+
    # mode.  A missing marker still takes the locked, harness-owned provisioning path.
    if os.path.isfile(marker):
        return _ready_overrides(contract)

    os.makedirs(ENV_ROOT, exist_ok=True)
    lock_path = directory + ".lock"
    with open(lock_path, "a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not os.path.isfile(marker):
            if os.path.isdir(directory):
                shutil.rmtree(directory)
            os.makedirs(directory)
            try:
                base = os.environ.copy()
                provision_env = base.copy()
                provision_env.update({str(key): _expand(value, directory, base)
                                      for key, value in contract["env"].items()})
                if contract["create"]:
                    _run(contract["create"], directory, provision_env,
                         f"creating the {contract['runtime']} validation environment")
                for dependency in deps:
                    _run(contract["package"], directory, provision_env,
                         f"installing validation dependency {dependency!r}", dependency)
                with open(os.path.join(directory, ".arcanum-ready.json"), "w",
                          encoding="utf-8") as handle:
                    json.dump({"protocol": contract["protocol"],
                               "runtime": contract["runtime"],
                               "dependencies": deps}, handle, sort_keys=True)
                    handle.write("\n")
            except Exception:
                shutil.rmtree(directory, ignore_errors=True)
                raise
    return _ready_overrides(contract)
