"""Shared platform boundary for every agentic AI CLI launched by Arcanum.

The repository is readable and executable, network access is retained, system/provider
temporary state is writable, and project writes are limited to explicit task paths.
"""
import ast
import json
import os
import py_compile
import shutil


# Validator code an author must never read or run. The harness exclusively executes gates;
# authors only edit their assigned unit and mark it validating. The boundary remains sealed
# here so an author cannot inspect checker implementation to shape content around hidden checks.
# Each package is replaced by a sourceless-bytecode mirror for import compatibility with shared
# read-only helpers; no author workflow depends on executing a validator.
#
# The two tiers differ in how much they actually hide. A module the mirror OMITS is gone
# outright. A module it KEEPS is bytecode: no source, no comments, no line-level control
# flow, and the greps a real author ran come back empty -- but identifiers and string
# literals survive, so `strings` still recovers error text. Keep as little as possible.
SEALED_PACKAGES = {
    # The deterministic section gate stays sourceless inside the author sandbox.
    "tools/validatelib": (),
    # Shared author-side imports reach review bookkeeping but not the Validator AI. The only
    # permitted live entry points are
    # review_call_count/review_usage_summary, which both delegate to records.py. So the
    # rubric ships as a stub that satisfies review.py's `from .prompt import ...` and
    # raises if anything ever actually reaches for it.
    "tools/buildlib/prerequisites": ("prompt.py", "result.py", "transport.py"),
}

_STUB_PREAMBLE = '''"""Sealed inside the author sandbox: names only, no implementation."""


class _Sealed:
    def __init__(self, name):
        self._sealed_name = name

    def _refuse(self, *_args, **_kwargs):
        raise RuntimeError(
            f"{self._sealed_name} is sealed inside the author sandbox; the harness "
            "runs the Validator AI itself, outside this boundary")

    __call__ = _refuse
    __getattr__ = _refuse
    __iter__ = _refuse
    __str__ = _refuse

'''


def _stub_source(path):
    """A same-shaped stand-in for one sealed module: its public names, no bodies.

    Importers bind these names at module load, so the stub must expose every one or the
    import fails. Each is a sentinel that raises on use rather than a plausible default,
    so a future code path that genuinely needs the real module fails loudly instead of
    grading against an empty rubric.
    """
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    names = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            names.extend(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
    return _STUB_PREAMBLE + "".join(
        f"{name} = _Sealed({name!r})\n"
        for name in dict.fromkeys(n for n in names if not n.startswith("__")))


def _bytecode_mirror(repo, relative, stubbed=()):
    """Build (or refresh) the sourceless-bytecode copy of one sealed package.

    Modules named in ``stubbed`` are replaced by name-only stand-ins; the rest are
    compiled from their real source. Nothing readable is written either way.
    """
    source = os.path.join(repo, relative)
    mirror = os.path.join(repo, ".cache", "sealed-bytecode", relative.replace("/", "."))
    modules = [(root, name)
               for root, _dirs, files in os.walk(source) for name in sorted(files)
               if name.endswith(".py")]
    newest = max((os.path.getmtime(os.path.join(root, name))
                  for root, name in modules), default=0)
    # ponytail: rebuilt whenever a source file is newer than the mirror. Two authors
    # starting at once may build it twice and write identical bytes; a lock would cost
    # more than the duplicated work.
    if os.path.isdir(mirror) and os.path.getmtime(mirror) >= newest:
        return mirror
    staging = f"{mirror}.staging-{os.getpid()}"
    shutil.rmtree(staging, ignore_errors=True)
    for root, name in modules:
        origin = os.path.join(root, name)
        target = os.path.join(staging, os.path.relpath(root, source), name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if name in stubbed:
            with open(target, "w", encoding="utf-8") as handle:
                handle.write(_stub_source(origin))
            origin = target
        py_compile.compile(origin, cfile=target + "c", doraise=True)
        if os.path.exists(target):        # keep bytecode only; source never ships
            os.unlink(target)
    os.makedirs(os.path.dirname(mirror), exist_ok=True)
    shutil.rmtree(mirror, ignore_errors=True)
    os.replace(staging, mirror)
    return mirror


def _sealed_binds(repo):
    """``--ro-bind`` pairs replacing each sealed package with its bytecode mirror."""
    binds = []
    for relative, stubbed in SEALED_PACKAGES.items():
        target = os.path.join(repo, relative)
        if os.path.isdir(target):
            binds.extend(("--ro-bind", _bytecode_mirror(repo, relative, stubbed), target))
    return binds


def resolve_bin(cmd):
    """Resolve a CLI without depending on the web server's deliberately small PATH."""
    if not cmd:
        raise RuntimeError("empty AI runner command")
    if os.path.isabs(cmd[0]):
        return list(cmd)
    extra = os.pathsep.join((os.path.expanduser("~/.local/bin"), "/usr/local/bin", "/usr/bin"))
    found = shutil.which(cmd[0], path=os.environ.get("PATH", "") + os.pathsep + extra)
    if not found:
        raise RuntimeError(f"AI runner binary {cmd[0]!r} is not installed")
    return [found, *cmd[1:]]


def provider_for(cmd):
    executable = os.path.basename(os.path.expanduser(cmd[0])) if cmd else ""
    providers = {"claude": "claude", "codex": "codex", "agy": "antigravity",
                 "opencode": "opencode"}
    try:
        return providers[executable]
    except KeyError:
        raise RuntimeError(
            f"AI runner executable {executable or '<empty>'!r} has no Arcanum access policy"
        ) from None


def _state_dirs(provider):
    home = os.path.expanduser("~")
    candidates = {
        "claude": (os.path.join(home, ".claude"), os.path.join(home, ".cache", "claude")),
        "codex": (os.path.join(home, ".codex"),),
        "antigravity": (os.path.join(home, ".gemini"),
                        os.path.join(home, ".cache", "antigravity")),
        "opencode": (os.path.join(home, ".config", "opencode"),
                     os.path.join(home, ".cache", "opencode"),
                     os.path.join(home, ".local", "share", "opencode"),
                     os.path.join(home, ".local", "state", "opencode")),
    }[provider]
    return [p for p in candidates if os.path.exists(p)]


def _persistent_memory_dirs(provider, cwd):
    """Provider memory stores to replace with empty, process-local filesystems.

    Session/auth state remains writable through ``_state_dirs`` so resume and accounting keep
    working. These narrower mounts win later and make existing memory invisible while ensuring any
    attempted write disappears with the worker process.
    """
    home = os.path.expanduser("~")
    if provider == "codex":
        candidates = [os.path.join(home, ".codex", "memories")]
    elif provider == "claude":
        claude = os.path.join(home, ".claude")
        candidates = [os.path.join(claude, "memory"),
                      os.path.join(claude, "agent-memory")]
        projects = os.path.join(claude, "projects")
        project_key = os.path.realpath(cwd).replace(os.sep, "-")
        candidates.append(os.path.join(projects, project_key, "memory"))
        try:
            for entry in os.scandir(projects):
                memory = os.path.join(entry.path, "memory")
                if entry.is_dir() and os.path.isdir(memory):
                    candidates.append(memory)
        except OSError:
            pass
    else:
        return []
    paths = []
    for candidate in candidates:
        # Bubblewrap cannot place a nested mount on a missing target beneath the read-only root.
        # Create only the empty provider-owned mount point before entering the namespace.
        try:
            os.makedirs(candidate, exist_ok=True)
        except OSError:
            continue
        path = os.path.realpath(candidate)
        if os.path.isdir(path) and path not in paths:
            paths.append(path)
    return paths


def _replace_flag_value(cmd, flag, value):
    out = list(cmd)
    if flag in out:
        i = out.index(flag)
        if i + 1 >= len(out):
            raise RuntimeError(f"runner flag {flag} has no value")
        out[i + 1] = value
    else:
        out.extend((flag, value))
    return out


def _claude_command(cmd, repo, web_allowed=True):
    out = _replace_flag_value(cmd, "--permission-mode", "auto")
    if "--safe-mode" not in out:
        # Harness prompts are self-contained. User hooks, project customizations,
        # and auto-memory can block a completed read-only validator or scoped author
        # on unrelated repository checks, so every harness-owned Claude role runs
        # without those ambient behaviors while retaining normal OAuth/session auth.
        out.insert(1, "--safe-mode")
    # A one-shot grader used to pass `--tools ""`; remove it so repo reads, trusted Python,
    # and current-source lookup are actually available. Bubblewrap remains the write boundary.
    while "--tools" in out:
        i = out.index("--tools")
        del out[i:i + 2]
    allowed = [
            f"Read(//{repo.lstrip('/')}/**)", "Bash", "Edit", "Write", "MultiEdit",
            "NotebookEdit",
        ]
    if web_allowed:
        allowed += ["WebSearch", "WebFetch(domain:*)"]
    settings = {
        # Keep resumable session history, but disable Claude's separate cross-session auto-memory.
        "autoMemoryEnabled": False,
        "permissions": {"allow": allowed},
        # The outer mount namespace is authoritative and works uniformly for every provider.
        # Avoid stacking Claude's nested sandbox, which cannot express file-level sidecars.
        "sandbox": {"enabled": False},
    }
    return [*out, "--settings", json.dumps(settings, separators=(",", ":"))]


def _codex_command(cmd, web_allowed=True):
    out = list(cmd)
    exec_i = out.index("exec") if "exec" in out else 1
    memory_setting = "features.memories=false"
    if not any(out[index:index + 2] == ["-c", memory_setting]
               for index in range(len(out) - 1)):
        out[exec_i:exec_i] = ["-c", memory_setting]
        exec_i += 2
    if web_allowed and "--search" not in out:
        out.insert(exec_i, "--search")
        exec_i += 1
    if not web_allowed:
        out = [item for item in out if item != "--search"]
    if "resume" in out[exec_i + 1:]:
        # `codex exec resume` has no -s/--sandbox flag. The outer bwrap is the actual
        # project boundary, so use Codex's explicit externally-sandboxed automation mode.
        while "-s" in out:
            i = out.index("-s")
            del out[i:i + 2]
        if "--dangerously-bypass-approvals-and-sandbox" not in out:
            out.insert(out.index("resume") + 1,
                       "--dangerously-bypass-approvals-and-sandbox")
        return out
    return _replace_flag_value(out, "-s", "danger-full-access")


def _opencode_command(cmd):
    out = [a for a in cmd if a != "--dangerously-skip-permissions"]
    if "--auto" not in out:
        out.insert(out.index("run") + 1 if "run" in out else 1, "--auto")
    return out


def _normalized_command(provider, cmd, repo, web_allowed=True):
    if provider == "claude":
        return _claude_command(cmd, repo, web_allowed)
    if provider == "codex":
        return _codex_command(cmd, web_allowed)
    if provider == "opencode":
        return _opencode_command(cmd)
    # Antigravity has no narrower unattended approval mode. The outer mount namespace
    # makes its skip-permissions mode safe for project files.
    out = list(cmd)
    if "--dangerously-skip-permissions" not in out:
        out.insert(1, "--dangerously-skip-permissions")
    return out


def scoped_runner_command(name, cmd, cwd, writable_paths, repo, readonly_paths=(),
                          hidden_paths=(), web_allowed=True, permission_paths=None):
    """Wrap one agent CLI with repo-read/web/temp plus explicitly scoped project writes.

    `writable_paths` must already exist. They may be directories (normal tome/section work)
    or individual files (review/build sidecars). Unknown future CLIs fail closed.
    """
    provider = provider_for(cmd)
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise RuntimeError(f"AI runner {name} requires bubblewrap (bwrap) for scoped access")
    cwd = os.path.realpath(cwd)
    if not os.path.exists(cwd):
        raise RuntimeError(f"AI runner cwd does not exist: {cwd}")
    strict = permission_paths is not None
    wrapped = [bwrap, "--die-with-parent", "--new-session", "--unshare-pid"]
    if strict:
        # Project access is declared in a role TOML. Keep the OS/runtime available without
        # re-mounting the host root, which would defeat that declaration.
        system_read = permission_paths.get("system_read") or []
        system_both = permission_paths.get("system_both") or []
        for path in system_read:
            if path != "/proc":
                wrapped.extend(("--ro-bind", path, path))
        if "/proc" in system_read:
            wrapped.extend(("--proc", "/proc"))
        for path in system_both:
            if path == "/dev":
                wrapped.extend(("--dev-bind", "/dev", "/dev"))
            else:
                wrapped.extend(("--bind", path, path))
        resolved = resolve_bin(_normalized_command(provider, cmd, repo, web_allowed))
        for path in dict.fromkeys((os.path.dirname(resolved[0]),
                                   os.path.dirname(os.path.realpath(resolved[0])),
                                   os.path.expanduser("~/.local/lib"))):
            if os.path.isdir(path):
                wrapped.extend(("--ro-bind", path, path))
        for path in dict.fromkeys([*(permission_paths.get("read") or []),
                                   *(permission_paths.get("both") or []),
                                   *(permission_paths.get("execute") or []),
                                   *readonly_paths]):
            if os.path.exists(path):
                wrapped.extend(("--ro-bind", path, path))
    else:
        resolved = None
        wrapped.extend(("--ro-bind", "/", "/", "--proc", "/proc", "--dev-bind", "/dev", "/dev"))
    if provider == "opencode":
        # OpenCode prunes its shared session database before creating a new session.
        # A large store can leave the CLI alive but permanently pre-session, so a
        # headless forge run must not block author startup on that maintenance path.
        wrapped.extend(("--setenv", "OPENCODE_DISABLE_PRUNE", "true"))
    elif provider == "claude":
        # Native belt-and-suspenders guard: Claude does not even initialize auto-memory.
        wrapped.extend(("--setenv", "CLAUDE_CODE_DISABLE_AUTO_MEMORY", "1"))
    # /tmp is the system's root temporary directory. Honour /temp too on hosts that have it.
    if not strict:
        for temp_root in ("/tmp", "/temp"):
            if os.path.isdir(temp_root):
                wrapped.extend(("--bind", temp_root, temp_root))
    memory_dirs = _persistent_memory_dirs(provider, cwd)
    mounts = [*_state_dirs(provider), *writable_paths]
    seen = set()
    for raw in mounts:
        path = os.path.realpath(raw)
        if path in seen:
            continue
        if not os.path.exists(path):
            raise RuntimeError(f"AI writable path does not exist: {path}")
        seen.add(path)
        wrapped.extend(("--bind", path, path))
    # Re-seal harness-owned files/directories after any broader writable parent mount.
    # The later mount wins, so a writable .tome-build can still contain immutable maps,
    # state, receipts, snapshots, and prior handoffs.
    for raw in readonly_paths:
        path = os.path.realpath(raw)
        if not os.path.exists(path):
            continue
        wrapped.extend(("--ro-bind", path, path))
    # Recovery/audit history is harness-only. In particular, hiding .git prevents a
    # restarted author from reconstructing the abandoned unit with `git show`.
    hidden = [os.path.join(os.path.realpath(repo), ".git"), *hidden_paths]
    for raw in hidden:
        path = os.path.realpath(raw)
        if not os.path.exists(path) or path in seen:
            continue
        seen.add(path)
        if os.path.isdir(path):
            wrapped.extend(("--tmpfs", path))
        else:
            wrapped.extend(("--ro-bind", "/dev/null", path))
    # Provider state is broadly writable for auth/session continuity, but persistent memory is
    # neither an input nor an output of a tome job. Empty process-local overlays prevent workers
    # from reading old tome memories and make attempted memory writes non-persistent.
    for path in memory_dirs:
        wrapped.extend(("--tmpfs", path))
    # Last, so the bytecode mirrors win over any broader repo mount above them.
    wrapped.extend(_sealed_binds(os.path.realpath(repo)))
    wrapped.extend(("--chdir", cwd))
    return [*wrapped, *(resolved if resolved is not None else resolve_bin(_normalized_command(
        provider, cmd, repo, web_allowed)))]


def section_runner_command(name, cmd, section_dir, repo, writable_sidecars=()):
    """Section-scoped runner plus exact harness-owned handoff files, when supplied."""
    return scoped_runner_command(name, cmd, section_dir,
                                 [section_dir, *writable_sidecars], repo)


def scoped_shell_command(command, cwd):
    """Read-only project boundary for the explicitly configured custom grader command."""
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise RuntimeError("custom AI command requires bubblewrap (bwrap)")
    wrapped = [bwrap, "--die-with-parent", "--new-session", "--unshare-pid",
               "--ro-bind", "/", "/", "--proc", "/proc", "--dev-bind", "/dev", "/dev"]
    for temp_root in ("/tmp", "/temp"):
        if os.path.isdir(temp_root):
            wrapped.extend(("--bind", temp_root, temp_root))
    return [*wrapped, "--chdir", os.path.realpath(cwd), "/bin/sh", "-lc", command]
