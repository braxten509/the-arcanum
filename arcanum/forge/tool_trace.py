"""Mirror the author AI's real tool calls into a browser-readable session history.

The forge harness deliberately keeps stdout concise, so provider tool traffic is not
available there. Follow the Codex/Claude JSONL, OpenCode SQLite session, or Antigravity
full transcript owned by the build process tree and expose a bounded, useful shell history.
"""
from collections import deque
from dataclasses import dataclass
from datetime import datetime
import json
import os
import re
import sqlite3
import time

from ..config import BUILD_DIR, WEB

TOOL_TRACE_LINES = 80
TOOL_TRACE_CHARS = 360
TOOL_TRACE_DIR = os.path.join(WEB, ".forge-trace")
_CODEX_SESSION_PART = os.sep + ".codex" + os.sep + "sessions" + os.sep
_CLAUDE_SESSION_PART = os.sep + ".claude" + os.sep + "projects" + os.sep
_JS_STRING_RE = re.compile(r'(?<![A-Za-z0-9_])["\']?cmd["\']?\s*:\s*("(?:\\.|[^"\\])*")', re.S)
_JS_TEMPLATE_RE = re.compile(r"(?<![A-Za-z0-9_])[\"']?cmd[\"']?\s*:\s*`((?:\\.|[^`])*)`", re.S)
_NESTED_TOOL_RE = re.compile(r"\btools\.([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_PATCH_FILE_RE = re.compile(r"\*\*\*\s+(?:Add|Update|Delete) File:\s*([^\n\\]+)")
_AGY_CONVERSATION_RE = re.compile(r"^(.*[/\\]antigravity-cli)[/\\]conversations[/\\]([0-9a-f-]+)\.db$")


@dataclass(frozen=True)
class TraceSource:
    provider: str
    path: str
    session_id: str = ""


def _descendants(root_pid):
    """Return root_pid and its current descendants from Linux /proc."""
    children = {}
    try:
        proc_entries = os.listdir("/proc")
    except OSError:
        return []
    for entry in proc_entries:
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", encoding="utf-8") as handle:
                fields = handle.read().rpartition(")")[2].split()
            children.setdefault(int(fields[1]), []).append(int(entry))
        except (OSError, ValueError, IndexError):
            continue
    found, stack = [], [int(root_pid)]
    while stack:
        pid = stack.pop()
        found.append(pid)
        stack.extend(children.get(pid, ()))
    return found


def runner_session(root_pid, opencode_session_id=None):
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
            if not provider or not os.path.isfile(target):
                continue
            try:
                stamp = os.stat(target).st_mtime_ns
            except OSError:
                continue
            session_id = (os.path.basename(target).removesuffix(".jsonl")
                          if provider == "claude" else "")
            candidates.append((stamp, TraceSource(provider, target, session_id)))
    opencode = _opencode_session_from_processes(pids, session_id=opencode_session_id)
    if opencode:
        candidates.append(opencode)
    if not candidates:
        return _claude_session_from_processes(pids)
    return max(candidates, key=lambda row: row[0])[1]


def _opencode_session_from_processes(pids, proc_root="/proc", session_id=None):
    """Find the newest OpenCode DB session belonging to a live worker process."""
    # A build trace passes an empty string until OpenCode emits its authoritative id.
    # Do not repeatedly open the shared database during that write-sensitive startup.
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
            db_path = next((os.readlink(os.path.join(pdir, "fd", fd)).removesuffix(" (deleted)")
                            for fd in os.listdir(os.path.join(pdir, "fd"))
                            if os.path.basename(os.readlink(os.path.join(pdir, "fd", fd))
                                                .removesuffix(" (deleted)")) == "opencode.db"), None)
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


def _claude_session_from_processes(pids, proc_root="/proc", projects_root=None):
    """Fallback for Claude versions that append JSONL without holding it open."""
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
                path = os.path.join(project_dir, name)
                candidates.append((os.stat(path).st_mtime_ns, path))
        except OSError:
            continue
    if not candidates:
        return None
    path = max(candidates)[1]
    return TraceSource("claude", path, os.path.basename(path).removesuffix(".jsonl"))


def trace_session_id(source):
    """Return the provider resume id represented by a discovered trace source."""
    if not source:
        return ""
    if source.session_id:
        return source.session_id
    if source.provider == "claude":
        return os.path.basename(source.path).removesuffix(".jsonl")
    if source.provider == "codex":
        try:
            with open(source.path, encoding="utf-8") as handle:
                for _ in range(20):
                    row = json.loads(handle.readline())
                    if row.get("type") == "session_meta":
                        return str((row.get("payload") or {}).get("id") or "")
        except (OSError, ValueError, json.JSONDecodeError):
            return ""
    return ""


def _literal_command(source, start):
    """Extract an exec_command cmd string from the actual Codex JavaScript call."""
    fragment = source[start:]
    match = _JS_STRING_RE.search(fragment)
    if match:
        try:
            return json.loads(match.group(1))
        except (TypeError, ValueError, json.JSONDecodeError):
            return match.group(1)[1:-1]
    match = _JS_TEMPLATE_RE.search(fragment)
    if match:
        return match.group(1).replace("\\n", "\n").replace("\\`", "`")
    return ""


def _argument_expression(source, start):
    """Return the literal first-argument expression for non-shell nested tools."""
    tail = source[start:].lstrip()
    depth, quote, escaped = 0, "", False
    for index, char in enumerate(tail):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in ('"', "'", "`"):
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            if depth == 0:
                return tail[:index].strip().rstrip(",")
            depth -= 1
        elif char == "\n" and depth == 0:
            return tail[:index].strip().rstrip(",")
    return tail.strip().rstrip(",")


def _flatten(value):
    return re.sub(r"[ \t]+", " ", str(value).replace("\r", "").replace("\n", " ↵ ")).strip()


def _preview(value, limit=TOOL_TRACE_CHARS):
    text = _flatten(value)
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _event(timestamp, provider, tool, detail):
    return {"at": timestamp or "", "provider": provider, "tool": tool,
            "detail": _preview(detail)}


def codex_tool_events(record):
    """Extract the real nested tool calls from one Codex session record."""
    if record.get("type") != "response_item":
        return []
    payload = record.get("payload") or {}
    if payload.get("type") != "custom_tool_call":
        return []
    source = str(payload.get("input") or "")
    timestamp = record.get("timestamp") or ""
    out = []
    matches = list(_NESTED_TOOL_RE.finditer(source))
    for i, match in enumerate(matches):
        name = match.group(1)
        if name == "exec_command":
            detail = _literal_command(source, match.end())
        elif name == "apply_patch":
            # Static patches expose their exact target paths; generated patches expose the
            # literal expression (for example patch.join(NL)) actually handed to the tool.
            escaped = source[match.end():].replace("\\n", "\n")
            paths = [p.strip() for p in _PATCH_FILE_RE.findall(escaped)]
            detail = ", ".join(dict.fromkeys(paths)) or _argument_expression(source, match.end())
        else:
            detail = _argument_expression(source, match.end())
        if not detail:
            end = matches[i + 1].start() if i + 1 < len(matches) else len(source)
            detail = source[match.end():end]
        out.append(_event(timestamp, "codex", name, detail))
    if not out:
        out.append(_event(timestamp, "codex", payload.get("name") or "tool", source))
    return out


def _tool_argument_detail(name, args):
    """Keep provider tool arguments literal while making common calls readable."""
    if not isinstance(args, dict):
        return json.dumps(args, ensure_ascii=False, separators=(",", ":"))
    for key in ("command", "CommandLine"):
        if args.get(key):
            return str(args[key])
    file_tools = {"read", "write", "edit", "patch", "view_file", "write_file",
                  "replace", "list_dir", "list_directory"}
    if str(name or "").lower() in file_tools:
        for key in ("filePath", "file_path", "AbsolutePath", "DirectoryPath", "path"):
            if args.get(key):
                detail = str(args[key])
                extras = [f"{extra}={args[extra]}" for extra in
                          ("offset", "limit", "StartLine", "EndLine") if extra in args]
                return detail + ((" " + " ".join(extras)) if extras else "")
    return json.dumps(args, ensure_ascii=False, separators=(",", ":"))


def claude_tool_events(record):
    """Extract Claude tool_use blocks without paraphrasing their arguments."""
    if record.get("type") != "assistant":
        return []
    message = record.get("message") or {}
    content = message.get("content") or []
    timestamp = record.get("timestamp") or ""
    out = []
    for block in content if isinstance(content, list) else []:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        name, args = str(block.get("name") or "tool"), block.get("input") or {}
        detail = _tool_argument_detail(name, args)
        out.append(_event(timestamp, "claude", name, detail))
    return out


def opencode_tool_events(record):
    """Extract literal tool parts from OpenCode's SQLite session store."""
    if record.get("type") != "tool":
        return []
    name = str(record.get("tool") or "tool")
    state = record.get("state") or {}
    return [_event(record.get("timestamp"), "opencode", name,
                   _tool_argument_detail(name, state.get("input") or {}))]


def antigravity_tool_events(record):
    """Extract AGY planner tool calls from its append-only full transcript."""
    calls = record.get("tool_calls") or []
    if record.get("type") != "PLANNER_RESPONSE" or not isinstance(calls, list):
        return []
    timestamp = record.get("created_at") or ""
    return [_event(timestamp, "antigravity", str(call.get("name") or "tool"),
                   _tool_argument_detail(call.get("name"), call.get("args") or {}))
            for call in calls if isinstance(call, dict)]


def tool_events(provider, record):
    if provider == "codex":
        return codex_tool_events(record)
    if provider == "claude":
        return claude_tool_events(record)
    if provider == "opencode":
        return opencode_tool_events(record)
    if provider == "antigravity":
        return antigravity_tool_events(record)
    return []


def format_tool_event(event):
    """One fixed-height UI line: local timestamp, literal tool name, literal argument."""
    stamp = str(event.get("at") or "")
    try:
        stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone().strftime("%H:%M:%S")
    except ValueError:
        stamp = stamp[11:19] if len(stamp) >= 19 else "--:--:--"
    tool = str(event.get("tool") or "tool")
    detail = str(event.get("detail") or "")
    return _preview(f"{stamp}  {tool} › {detail}")


class SessionFollower:
    """Incrementally parse complete JSONL records and retain recent actual tool calls."""
    def __init__(self, provider, path=None):
        source = provider if isinstance(provider, TraceSource) else TraceSource(provider, path)
        self.provider = source.provider
        self.path = source.path
        self.source = source
        self.offset = 0
        self.events = deque(maxlen=TOOL_TRACE_LINES)

    def poll(self):
        try:
            size = os.path.getsize(self.path)
            if size < self.offset:
                self.offset = 0
                self.events.clear()
            with open(self.path, "rb") as handle:
                handle.seek(self.offset)
                data = handle.read()
        except OSError:
            return list(self.events)
        if not data:
            return list(self.events)
        parts = data.split(b"\n")
        complete = parts[:-1]
        self.offset += sum(len(line) + 1 for line in complete)
        for raw in complete:
            if not raw:
                continue
            try:
                record = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            self.events.extend(tool_events(self.provider, record))
        return list(self.events)


class OpenCodeFollower:
    """Read the newest bounded set of tool parts from one OpenCode DB session."""
    def __init__(self, source):
        self.source = source
        self.provider = source.provider
        self.path = source.path

    def poll(self):
        try:
            with sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=0.2) as db:
                rows = db.execute(
                    "SELECT time_created, data FROM part WHERE session_id=? "
                    "AND json_extract(data, '$.type')='tool' "
                    "ORDER BY time_created DESC, id DESC LIMIT ?",
                    (self.source.session_id, TOOL_TRACE_LINES)).fetchall()
        except sqlite3.Error:
            return []
        events = []
        for created, raw in reversed(rows):
            try:
                record = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            record["timestamp"] = datetime.fromtimestamp(
                int(created) / 1000).astimezone().isoformat()
            events.extend(opencode_tool_events(record))
        return events[-TOOL_TRACE_LINES:]


def _follower(source):
    return (OpenCodeFollower(source) if source.provider == "opencode"
            else SessionFollower(source))


def _write_snapshot(job_id, payload):
    os.makedirs(TOOL_TRACE_DIR, mode=0o700, exist_ok=True)
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "", str(job_id)) or "unknown"
    target = os.path.join(TOOL_TRACE_DIR, safe_id + ".json")
    temporary = target + f".{os.getpid()}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    os.chmod(temporary, 0o600)
    os.replace(temporary, target)


def _saved_session_id(build_id):
    if not build_id:
        return None
    try:
        with open(os.path.join(BUILD_DIR, f"{build_id}.session.json"),
                  encoding="utf-8") as handle:
            return str(json.load(handle).get("sessionId") or "")
    except (OSError, ValueError):
        return ""


def mirror_tool_trace(job_id, build_pid, build_id="", interval=0.75):
    """Follow a build until it exits, updating its bounded static trace snapshot."""
    follower = None
    history = deque(maxlen=TOOL_TRACE_LINES)
    current_lines = []
    missing = 0
    last_payload = {"active": False, "provider": "", "sessionId": "",
                    "updatedAt": time.time(), "lines": []}
    _write_snapshot(job_id, last_payload)
    while os.path.exists(f"/proc/{int(build_pid)}"):
        current = runner_session(build_pid, _saved_session_id(build_id))
        if current:
            missing = 0
            provider = current.provider
            if not follower or follower.source != current:
                history.extend(current_lines)
                current_lines = []
                follower = _follower(current)
            events = follower.poll()
            current_lines = [format_tool_event(event)
                             for event in events[-TOOL_TRACE_LINES:]]
            last_payload = {
                "active": True,
                "provider": provider,
                "sessionId": trace_session_id(current),
                "updatedAt": time.time(),
                "lines": [*history, *current_lines][-TOOL_TRACE_LINES:],
            }
            _write_snapshot(job_id, last_payload)
        else:
            missing += 1
            # A paused author has no live child, but its history is still the session truth.
            if missing >= 3:
                last_payload = {**last_payload, "active": False, "updatedAt": time.time()}
                _write_snapshot(job_id, last_payload)
        time.sleep(max(0.2, float(interval)))
    _write_snapshot(job_id, {**last_payload, "active": False, "updatedAt": time.time()})
