"""Mirror the AI runner's real tool calls into a tiny browser-readable snapshot.

The forge harness deliberately keeps stdout concise, so Codex/Claude tool traffic is not
available there.  Both CLIs do, however, keep an append-only JSONL session and hold that
file open while they work.  Follow the session owned by the build process tree and expose
only the last three literal tool calls; this gives the operator real evidence without
turning the Bindery into an unbounded terminal.
"""
from collections import deque
from datetime import datetime
import json
import os
import re
import time

from .config import WEB

TOOL_TRACE_LINES = 3
TOOL_TRACE_CHARS = 360
TOOL_TRACE_DIR = os.path.join(WEB, ".forge-trace")
_CODEX_SESSION_PART = os.sep + ".codex" + os.sep + "sessions" + os.sep
_CLAUDE_SESSION_PART = os.sep + ".claude" + os.sep + "projects" + os.sep
_JS_STRING_RE = re.compile(r'(?<![A-Za-z0-9_])["\']?cmd["\']?\s*:\s*("(?:\\.|[^"\\])*")', re.S)
_JS_TEMPLATE_RE = re.compile(r"(?<![A-Za-z0-9_])[\"']?cmd[\"']?\s*:\s*`((?:\\.|[^`])*)`", re.S)
_NESTED_TOOL_RE = re.compile(r"\btools\.([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_PATCH_FILE_RE = re.compile(r"\*\*\*\s+(?:Add|Update|Delete) File:\s*([^\n\\]+)")


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


def runner_session(root_pid):
    """Find the Codex or Claude JSONL file held open by this build's live worker."""
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
            if not provider or not os.path.isfile(target):
                continue
            try:
                stamp = os.stat(target).st_mtime_ns
            except OSError:
                continue
            candidates.append((stamp, provider, target))
    if not candidates:
        return _claude_session_from_processes(pids)
    _, provider, path = max(candidates)
    return provider, path


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
    return "claude", max(candidates)[1]


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
        if name == "Bash" and isinstance(args, dict):
            detail = args.get("command") or json.dumps(args, ensure_ascii=False, separators=(",", ":"))
        elif isinstance(args, dict) and args.get("file_path"):
            detail = str(args["file_path"])
            extras = [f"{key}={args[key]}" for key in ("offset", "limit") if key in args]
            if extras:
                detail += " " + " ".join(extras)
        else:
            detail = json.dumps(args, ensure_ascii=False, separators=(",", ":"))
        out.append(_event(timestamp, "claude", name, detail))
    return out


def tool_events(provider, record):
    if provider == "codex":
        return codex_tool_events(record)
    if provider == "claude":
        return claude_tool_events(record)
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
    """Incrementally parse complete JSONL records and retain three actual tool calls."""
    def __init__(self, provider, path):
        self.provider = provider
        self.path = path
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


def _write_snapshot(job_id, payload):
    os.makedirs(TOOL_TRACE_DIR, mode=0o700, exist_ok=True)
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "", str(job_id)) or "unknown"
    target = os.path.join(TOOL_TRACE_DIR, safe_id + ".json")
    temporary = target + f".{os.getpid()}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    os.chmod(temporary, 0o600)
    os.replace(temporary, target)


def mirror_tool_trace(job_id, build_pid, interval=0.75):
    """Follow a build until it exits, updating its bounded static trace snapshot."""
    follower = None
    missing = 0
    _write_snapshot(job_id, {"active": False, "provider": "", "updatedAt": time.time(), "lines": []})
    while os.path.exists(f"/proc/{int(build_pid)}"):
        current = runner_session(build_pid)
        if current:
            missing = 0
            provider, path = current
            if not follower or (follower.provider, follower.path) != current:
                follower = SessionFollower(provider, path)
            events = follower.poll()
            _write_snapshot(job_id, {
                "active": True,
                "provider": provider,
                "updatedAt": time.time(),
                "lines": [format_tool_event(event) for event in events[-TOOL_TRACE_LINES:]],
            })
        else:
            missing += 1
            # Do not leave a previous phase's worker calls masquerading as current. A short
            # grace avoids flicker while /proc changes underneath one scan.
            if missing >= 3:
                follower = None
                _write_snapshot(job_id, {"active": False, "provider": "", "updatedAt": time.time(), "lines": []})
        time.sleep(max(0.2, float(interval)))
    _write_snapshot(job_id, {"active": False, "provider": "", "updatedAt": time.time(), "lines": []})
