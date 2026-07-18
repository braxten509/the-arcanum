"""Shared platform boundary for every agentic AI CLI launched by Arcanum.

The repository is readable and executable, network access is retained, system/provider
temporary state is writable, and project writes are limited to explicit task paths.
"""
import json
import os
import shutil


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


def _claude_command(cmd, repo):
    out = _replace_flag_value(cmd, "--permission-mode", "auto")
    # A one-shot grader used to pass `--tools ""`; remove it so repo reads, trusted Python,
    # and current-source lookup are actually available. Bubblewrap remains the write boundary.
    while "--tools" in out:
        i = out.index("--tools")
        del out[i:i + 2]
    settings = {
        "permissions": {"allow": [
            f"Read(//{repo.lstrip('/')}/**)", "Bash", "Edit", "Write", "MultiEdit",
            "NotebookEdit", "WebSearch", "WebFetch(domain:*)",
        ]},
        # The outer mount namespace is authoritative and works uniformly for every provider.
        # Avoid stacking Claude's nested sandbox, which cannot express file-level sidecars.
        "sandbox": {"enabled": False},
    }
    return [*out, "--settings", json.dumps(settings, separators=(",", ":"))]


def _codex_command(cmd):
    out = list(cmd)
    exec_i = out.index("exec") if "exec" in out else 1
    if "--search" not in out:
        out.insert(exec_i, "--search")
        exec_i += 1
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


def _normalized_command(provider, cmd, repo):
    if provider == "claude":
        return _claude_command(cmd, repo)
    if provider == "codex":
        return _codex_command(cmd)
    if provider == "opencode":
        return _opencode_command(cmd)
    # Antigravity has no narrower unattended approval mode. The outer mount namespace
    # makes its skip-permissions mode safe for project files.
    out = list(cmd)
    if "--dangerously-skip-permissions" not in out:
        out.insert(1, "--dangerously-skip-permissions")
    return out


def scoped_runner_command(name, cmd, cwd, writable_paths, repo, readonly_paths=()):
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
    wrapped = [bwrap, "--die-with-parent", "--new-session", "--unshare-pid",
               "--ro-bind", "/", "/", "--proc", "/proc", "--dev-bind", "/dev", "/dev"]
    if provider == "opencode":
        # OpenCode prunes its shared session database before creating a new session.
        # A large store can leave the CLI alive but permanently pre-session, so a
        # headless forge run must not block author startup on that maintenance path.
        wrapped.extend(("--setenv", "OPENCODE_DISABLE_PRUNE", "true"))
    # /tmp is the system's root temporary directory. Honour /temp too on hosts that have it.
    for temp_root in ("/tmp", "/temp"):
        if os.path.isdir(temp_root):
            wrapped.extend(("--bind", temp_root, temp_root))
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
    wrapped.extend(("--chdir", cwd))
    return [*wrapped, *resolve_bin(_normalized_command(provider, cmd, repo))]


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
