"""Read-only local repository tools exposed to API-backed AI roles."""
import json
import os
import shutil
import subprocess

from ..config import ROOT


_SPECS = [
    ("read_repo_file", "Read one UTF-8 text file under the Arcanum repository.", {
        "type": "object", "properties": {"path": {"type": "string"}},
        "required": ["path"], "additionalProperties": False,
    }),
    ("list_repo_files", "List repository-relative files whose paths contain a text fragment.", {
        "type": "object", "properties": {"contains": {"type": "string"}},
        "required": ["contains"], "additionalProperties": False,
    }),
    ("run_repo_python", "Execute a trusted Python file from this repository read-only; /tmp is writable.", {
        "type": "object", "properties": {
            "path": {"type": "string"},
            "args": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
        }, "required": ["path", "args"], "additionalProperties": False,
    }),
]


def openai_tools():
    return [{"type": "function", "name": name, "description": desc,
             "parameters": schema, "strict": True} for name, desc, schema in _SPECS]


def anthropic_tools():
    return [{"name": name, "description": desc, "input_schema": schema}
            for name, desc, schema in _SPECS]


def _repo_path(raw, suffix=None):
    path = os.path.realpath(os.path.join(ROOT, str(raw or "")))
    try:
        inside = os.path.commonpath((path, ROOT)) == ROOT
    except ValueError:
        inside = False
    if not inside or (suffix and not path.endswith(suffix)):
        raise ValueError(f"path is outside the allowed repository scope: {raw!r}")
    return path


def _run_python(path, args, tome_root):
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise RuntimeError("run_repo_python requires bubblewrap")
    cmd = [bwrap, "--die-with-parent", "--new-session", "--ro-bind", "/", "/",
           "--dev-bind", "/dev", "/dev", "--bind", "/tmp", "/tmp",
           "--chdir", tome_root, shutil.which("python3") or "/usr/bin/python3", path,
           *[str(a)[:500] for a in args[:20]]]
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=90, env=env)
    return json.dumps({"exitCode": p.returncode, "stdout": p.stdout[-20000:],
                       "stderr": p.stderr[-10000:]})


def execute(name, inputs, tome_root):
    if name == "read_repo_file":
        path = _repo_path(inputs.get("path"))
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read(50000)
    if name == "list_repo_files":
        needle = str(inputs.get("contains") or "").lower()[:200]
        found = []
        for base, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "monaco", "save")]
            for filename in files:
                rel = os.path.relpath(os.path.join(base, filename), ROOT)
                if needle in rel.lower():
                    found.append(rel)
                    if len(found) >= 400:
                        return "\n".join(found)
        return "\n".join(found)
    if name == "run_repo_python":
        path = _repo_path(inputs.get("path"), ".py")
        return _run_python(path, list(inputs.get("args") or []), tome_root)
    raise ValueError(f"unknown repository tool {name!r}")
