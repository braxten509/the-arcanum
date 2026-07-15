"""Config-driven clean-environment packaging for proof-v1 final artifacts."""
import os
import subprocess
import tempfile

from tome_proof import safe_project_path

from . import common


def _delivery_cache_dir():
    """Writable cross-replay download/wheel cache; never substitutes for the fresh env."""
    owner = str(os.getuid()) if hasattr(os, "getuid") else "user"
    path = os.path.join(tempfile.gettempdir(), f"arcanum-delivery-cache-{owner}")
    if os.path.islink(path):
        raise OSError(f"delivery cache path is a symlink: {path}")
    os.makedirs(path, mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def _expand(command, values):
    out = []
    for arg in command or []:
        value = str(arg)
        for key, replacement in values.items():
            value = value.replace("{" + key + "}", replacement)
        out.append(value)
    return out


def _run(argv, project, env, timeout, label):
    try:
        result = subprocess.run(argv, cwd=project, env=env, capture_output=True,
                                text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "output": f"{label} failed to start: {exc}",
                "command": list(argv)}
    output = common.join_output(result.stdout, result.stderr)
    if result.returncode:
        return {"ok": False, "output": f"{label} exited {result.returncode}:\n{output}",
                "command": list(argv)}
    return {"ok": True, "output": output or f"({label} completed)",
            "command": list(argv)}


def package_project(runtime_config, project, proof, env=None):
    """Build one real deliverable from exact requirements in a fresh environment.

    The reusable runtime owns all executable command prefixes. The tome may append only
    argument strings to the runtime's delivery build command and name project-relative input
    and output paths. No shell is involved.
    """
    requirements = safe_project_path(proof.get("requirementsFile"))
    artifact = safe_project_path(proof.get("artifactPath"))
    if not requirements or not artifact:
        return {"ok": False, "output": "package proof paths are invalid"}
    requirements_path = os.path.realpath(os.path.join(project, *requirements.split("/")))
    artifact_path = os.path.realpath(os.path.join(project, *artifact.split("/")))
    root = os.path.realpath(project)
    if (not requirements_path.startswith(root + os.sep)
            or not artifact_path.startswith(root + os.sep)):
        return {"ok": False, "output": "package proof path escapes the project"}
    if not os.path.isfile(requirements_path):
        return {"ok": False, "output": f"requirements file {requirements!r} does not exist"}

    environment_dir = os.path.join(project, ".arcanum-delivery-env")
    try:
        cache_dir = _delivery_cache_dir()
    except OSError as exc:
        return {"ok": False, "output": f"delivery cache unavailable: {exc}"}
    values = {"dir": project, "env": environment_dir, "cache": cache_dir,
              "requirements": requirements_path, "artifact": artifact_path}
    commands = [
        ("fresh delivery environment", runtime_config.get("deliveryCreateCommand") or []),
        ("delivery dependency preflight", runtime_config.get("deliveryResolveCommand") or []),
        ("exact requirement install", runtime_config.get("deliveryInstallCommand") or []),
        ("delivery build", [*(runtime_config.get("deliveryBuildCommand") or []),
                            *(proof.get("packageArgs") or [])]),
    ]
    timeout = runtime_config.get("deliveryTimeout") or 900
    outputs, executed = [], []
    for label, command in commands:
        if not command:
            continue
        result = _run(_expand(command, values), project, env, timeout, label)
        outputs.append(result["output"])
        executed.append(result.get("command") or [])
        if not result["ok"]:
            return {"ok": False, "output": "\n".join(outputs), "commands": executed}
    if not os.path.isfile(artifact_path):
        return {"ok": False, "output": "\n".join(outputs + [
            f"delivery build did not create {artifact!r}"]), "commands": executed}
    if not os.access(artifact_path, os.X_OK):
        return {"ok": False, "output": "\n".join(outputs + [
            f"packaged artifact {artifact!r} is not executable"]), "commands": executed}
    return {"ok": True, "output": "\n".join(outputs), "artifact": artifact_path,
            "commands": executed}


def run_artifact(artifact, args=(), env=None, timeout=60):
    safe_args = []
    for arg in args or ():
        if not isinstance(arg, str) or any(ord(ch) < 32 for ch in arg):
            return {"ok": False, "output": f"invalid packaged-artifact argument {arg!r}"}
        safe_args.append(arg)
    clean_env = dict(os.environ if env is None else env)
    virtual_env = clean_env.pop("VIRTUAL_ENV", None)
    clean_env.pop("PYTHONPATH", None)
    clean_env.pop("PYTHONHOME", None)
    clean_env.pop("CONDA_PREFIX", None)
    if virtual_env and clean_env.get("PATH"):
        venv_bin = os.path.realpath(os.path.join(virtual_env, "bin"))
        clean_env["PATH"] = os.pathsep.join(
            entry for entry in clean_env["PATH"].split(os.pathsep)
            if os.path.realpath(entry) != venv_bin)
    clean_env["PYTHONNOUSERSITE"] = "1"
    return common.run_cancellable([artifact, *safe_args], "", timeout, cwd=os.path.dirname(artifact),
                                  env=clean_env)
