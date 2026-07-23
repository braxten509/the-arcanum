"""Filesystem inventories used by authoring and review boundary checks."""
import hashlib
import os
import tomllib

from .. import REPO

RUNTIME_CONFIG_DIR = os.path.join(REPO, "global-configs", "runtimes")


def inventory(tid):
    """Return authored files and top-level TOML array lengths for a tome."""
    root = os.path.join(REPO, "tomes", tid)
    files, arrays = set(), {}
    if not os.path.isdir(root):
        return {"files": files, "arrays": arrays}
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d != "save"]
        for name in names:
            path = os.path.join(dirpath, name)
            relative = os.path.relpath(path, root).replace(os.sep, "/")
            files.add(relative)
            if name.endswith(".toml"):
                try:
                    with open(path, "rb") as handle:
                        arrays[relative] = {
                            key: len(value)
                            for key, value in tomllib.load(handle).items()
                            if isinstance(value, list)
                        }
                except Exception:
                    pass
    return {"files": files, "arrays": arrays}


def shrinkage(before, after):
    """Describe files or top-level TOML arrays removed by a phase."""
    problems = [
        f"file DELETED: {path}"
        for path in sorted(before["files"] - after["files"])
    ]
    for path, keys in sorted(before["arrays"].items()):
        current = after["arrays"].get(path)
        if current is None:
            continue
        for key, count in keys.items():
            if current.get(key, 0) < count:
                problems.append(
                    f"{path}: [[{key}]] shrank {count} -> "
                    f"{current.get(key, 0)} entries")
    return problems


def shrink_marks(path):
    """Count explicit shrink justifications in the dedicated sidecar."""
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().count("SHRINK OK")
    except OSError:
        return 0


def runtime_config_inventory(root=RUNTIME_CONFIG_DIR):
    """Return content hashes for the shared runtime-directory write audit."""
    out = {}
    for base, directories, names in os.walk(root):
        directories[:] = sorted(
            child for child in directories if not child.startswith("."))
        for name in sorted(names):
            path = os.path.join(base, name)
            relative = os.path.relpath(path, root).replace(os.sep, "/")
            try:
                with open(path, "rb") as handle:
                    out[relative] = hashlib.sha256(handle.read()).hexdigest()
            except OSError:
                pass
    return out


def review_inventory(tid, runtime_root=RUNTIME_CONFIG_DIR):
    """Hash authored tome files and runtime configs for the Phase-8 audit."""
    root = os.path.join(REPO, "tomes", tid)
    out = {}
    if os.path.isdir(root):
        for dirpath, dirs, names in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d != "save")
            for name in sorted(names):
                path = os.path.join(dirpath, name)
                if not os.path.isfile(path):
                    continue
                key = os.path.relpath(path, REPO).replace(os.sep, "/")
                try:
                    with open(path, "rb") as handle:
                        out[key] = hashlib.sha256(handle.read()).hexdigest()
                except OSError:
                    pass
    for name, digest in runtime_config_inventory(runtime_root).items():
        out[f"global-configs/runtimes/{name}"] = digest
    return out


def review_changes(before, after):
    """Describe authored-file changes between two Phase-8 snapshots."""
    changes = []
    for path in sorted(before.keys() | after.keys()):
        if path not in before:
            kind = "ADDED"
        elif path not in after:
            kind = "DELETED"
        elif before[path] != after[path]:
            kind = "MODIFIED"
        else:
            continue
        changes.append(f"{kind}: {path}")
    return changes


def selected_runtime_config(tid):
    try:
        with open(os.path.join(REPO, "tomes", tid, "tome.toml"), "rb") as handle:
            runtime = tomllib.load(handle).get("runtime")
    except (OSError, tomllib.TOMLDecodeError):
        return None
    if not isinstance(runtime, dict):
        return None
    name = runtime.get("name")
    return str(name) + ".toml" if name else None


def runtime_config_scope_violations(before, allowed, root=RUNTIME_CONFIG_DIR):
    """Reject changes outside the runtime selected by the current tome."""
    after = runtime_config_inventory(root)
    changed = sorted(
        name for name in before.keys() | after.keys()
        if before.get(name) != after.get(name))
    wrong = [name for name in changed if name != allowed]
    return ([
        "runtime config OUT OF SCOPE: " + ", ".join(wrong)
        + f" (this tome selects {allowed or 'no valid runtime'}; "
        "restore every other file)"
    ] if wrong else [])
