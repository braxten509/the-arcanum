"""Find the live provider session store owned by a build's worker process tree.

The author CLI (Codex/Claude JSONL, OpenCode SQLite, or Antigravity transcript) runs
sandboxed, so its session file lives at a bind-mount source while `/proc/<pid>/fd` shows the
in-namespace path. These helpers walk the descendants, translate the mount back to the host,
and keep the discovered transcript bound to the CLI-emitted session id.
"""
from dataclasses import dataclass
import json
import os
import re
import sqlite3

from ...config import BUILD_DIR
from ...jobs.processes import descendants as _descendants
from ...platform import agent_scratch
from .mounts import host_mount_path

_CODEX_SESSION_PART = os.sep + ".codex" + os.sep + "sessions" + os.sep
_CLAUDE_SESSION_PART = os.sep + ".claude" + os.sep + "projects" + os.sep
_AGY_CONVERSATION_RE = re.compile(r"^(.*[/\\]antigravity-cli)[/\\]conversations[/\\]([0-9a-f-]+)\.db$")


@dataclass(frozen=True)
class TraceSource:
    provider: str
    path: str
    session_id: str = ""


def _trace_path_matches_session(provider, path, session_id):
    """Keep a discovered transcript bound to the CLI-emitted session id."""
    if not session_id or provider not in ("codex", "claude"):
        return True
    return str(path).endswith(f"{session_id}.jsonl")


def runner_session(root_pid, session_id=None):
    """Find the real session store owned by this build's live worker."""
    candidates = []
    pids = _descendants(root_pid)
    for pid in pids:
        fd_dir = f"/proc/{pid}/fd"
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(os.path.join(fd_dir, fd)).removesuffix(" (deleted)")
            except OSError:
                continue
            provider = None
            if _CODEX_SESSION_PART in target and target.endswith(".jsonl"):
                provider = "codex"
            elif _CLAUDE_SESSION_PART in target and target.endswith(".jsonl"):
                provider = "claude"
            else:
                agy = _AGY_CONVERSATION_RE.match(target)
                if agy:
                    transcript = os.path.join(agy.group(1), "brain", agy.group(2),
                                              ".system_generated", "logs", "transcript_full.jsonl")
                    if os.path.isfile(transcript):
                        try:
                            candidates.append((os.stat(transcript).st_mtime_ns,
                                               TraceSource("antigravity", transcript,
                                                           agy.group(2))))
                        except OSError:
                            pass
            if provider and os.path.isabs(target):
                # The author runs sandboxed: its session file lives at a bind-mount source
                # while the fd shows the in-namespace path, which is absent on the host. Map
                # it back the way the opencode branch already does, or isfile() fails here and
                # discovery silently falls through to an unrelated host Claude session.
                host = host_mount_path(f"/proc/{pid}", target, "/proc")
                if host:
                    target = host
            if (not provider or not os.path.isfile(target)
                    or not _trace_path_matches_session(provider, target, session_id)):
                continue
            try:
                stamp = os.stat(target).st_mtime_ns
            except OSError:
                continue
            source_session_id = (os.path.basename(target).removesuffix(".jsonl")
                                 if provider == "claude" else "")
            candidates.append((stamp, TraceSource(provider, target, source_session_id)))
    opencode = _opencode_session_from_processes(pids, session_id=session_id)
    if opencode:
        candidates.append(opencode)
    if not candidates:
        return _claude_session_from_processes(pids, session_id=session_id)
    return max(candidates, key=lambda row: row[0])[1]


def _opencode_session_from_processes(pids, proc_root="/proc", session_id=None):
    """Find the newest OpenCode DB session belonging to a live worker process."""
    # Empty string remains the explicit "wait for the emitted id" mode for any legacy
    # caller whose database might be shared. ``None`` permits process-owned discovery;
    # Forge author workers use it because their database is isolated per unit.
    if session_id == "":
        return None
    candidates = []
    for pid in pids:
        pdir = os.path.join(proc_root, str(pid))
        try:
            with open(os.path.join(pdir, "cmdline"), "rb") as handle:
                argv = [part.decode("utf-8", "replace") for part in handle.read().split(b"\0") if part]
            if not argv or os.path.basename(argv[0]) != "opencode":
                continue
            cwd = os.readlink(os.path.join(pdir, "cwd"))
            started_ms = int(os.stat(pdir).st_ctime * 1000) - 2000
            db_path = None
            for fd in os.listdir(os.path.join(pdir, "fd")):
                try:
                    target = os.readlink(
                        os.path.join(pdir, "fd", fd)).removesuffix(" (deleted)")
                except OSError:
                    continue
                if os.path.basename(target) != "opencode.db":
                    continue
                # `/proc/<pid>/fd` prints the conventional in-namespace path. Translate
                # its bind mount back to the host source; opening the conventional path
                # would expose the shared DB, while SQLite canonicalizes `/proc/pid/root`
                # and can pair the isolated main file with the wrong WAL.
                db_path = (host_mount_path(pdir, target, proc_root)
                           if os.path.isabs(target) else os.path.join(pdir, "fd", fd))
                if os.path.isfile(db_path):
                    break
                db_path = None
            if not db_path or not os.path.isfile(db_path):
                continue
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=0.2) as db:
                if session_id is not None:
                    row = db.execute(
                        "SELECT id, time_updated FROM session WHERE id=? AND directory=? LIMIT 1",
                        (session_id, cwd)).fetchone()
                else:
                    row = db.execute(
                        "SELECT id, time_updated FROM session WHERE directory=? AND time_created>=? "
                        "ORDER BY time_updated DESC LIMIT 1", (cwd, started_ms)).fetchone()
            if row:
                candidates.append((int(row[1]) * 1_000_000,
                                   TraceSource("opencode", db_path, str(row[0]))))
        except (OSError, sqlite3.Error, StopIteration, ValueError):
            continue
    return max(candidates, key=lambda row: row[0]) if candidates else None


def _claude_session_from_processes(pids, proc_root="/proc", projects_root=None,
                                   session_id=None):
    """Fallback for Claude versions that append JSONL without holding it open.

    With a known session id, only that session's file is eligible. A sandboxed author never
    writes into the host projects dir, so an unmatched id yields nothing and the pane stays
    blank rather than binding to an unrelated Claude Code session that shares this cwd.
    """
    projects_root = projects_root or os.path.expanduser("~/.claude/projects")
    candidates = []
    for pid in pids:
        pdir = os.path.join(proc_root, str(pid))
        try:
            with open(os.path.join(pdir, "cmdline"), "rb") as handle:
                argv = [part.decode("utf-8", "replace") for part in handle.read().split(b"\0") if part]
            if not argv or os.path.basename(argv[0]) != "claude":
                continue
            cwd = os.readlink(os.path.join(pdir, "cwd"))
            project_dir = os.path.join(projects_root, cwd.replace(os.sep, "-"))
            for name in os.listdir(project_dir):
                if not name.endswith(".jsonl"):
                    continue
                if session_id and name != f"{session_id}.jsonl":
                    continue
                path = os.path.join(project_dir, name)
                candidates.append((os.stat(path).st_mtime_ns, path))
        except OSError:
            continue
    if not candidates:
        return None
    path = max(candidates)[1]
    return TraceSource("claude", path, os.path.basename(path).removesuffix(".jsonl"))


def saved_session_source(build_id):
    """Resolve the author's own on-disk session store when no live worker holds it open.

    A sandboxed Claude author never keeps its JSONL open (see `_claude_session_from_processes`)
    and writes it under the unit's private provider-state overlay, not host ~/.claude — so
    process/fd discovery finds nothing and the tool-history pane stays blank even while the
    conversation pane (which reads a durable harness copy) stays current. The transcript still
    exists on disk; locate it by the saved session id so a paused or between-turns author still
    streams its real tool history.
    """
    if not build_id:
        return None
    try:
        with open(os.path.join(BUILD_DIR, f"{build_id}.session.json"), encoding="utf-8") as handle:
            saved = json.load(handle)
    except (OSError, ValueError):
        return None
    session_id = str(saved.get("sessionId") or "")
    provider = str(saved.get("kind") or "").split("-", 1)[0]
    if not session_id or provider not in ("claude", "codex", "opencode"):
        return None
    try:
        unit = agent_scratch._unit_root(build_id, "author", int(saved.get("phase") or 0),
                                        str(saved.get("section") or ""))
    except (TypeError, ValueError):
        return None
    root = os.path.join(unit, "provider-state", provider)
    target = "opencode.db" if provider == "opencode" else f"{session_id}.jsonl"
    for base, _dirs, files in os.walk(root):   # os.walk descends dotdirs (.claude) that glob skips
        if target in files:
            return TraceSource(provider, os.path.join(base, target), session_id)
    return None
