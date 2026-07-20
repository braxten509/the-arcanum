"""Provider session identity, applied model, and cumulative token metadata."""
import json
import os
from datetime import datetime

from arcanum.ai.events import usage_from_line


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


def trace_model(source):
    """Return the latest provider-applied model recorded by a live trace."""
    if not source or source.provider != "codex":
        return ""
    model = ""
    try:
        with open(source.path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except (ValueError, json.JSONDecodeError):
                    continue
                payload = row.get("payload") or {}
                if row.get("type") == "turn_context" and payload.get("model"):
                    model = str(payload["model"])
                elif payload.get("type") == "thread_settings_applied":
                    settings = payload.get("thread_settings") or {}
                    if settings.get("model"):
                        model = str(settings["model"])
    except OSError:
        return ""
    return model


def trace_usage(source, before=None):
    """Return cumulative usage for a trace, optionally before an epoch boundary."""
    if not source:
        return {}
    # OpenCode's trace is its shared SQLite database, not a JSONL transcript: reading it
    # as text throws UnicodeDecodeError on the first binary byte. There are no usage rows
    # to find that way, so do not open it at all.
    if source.provider == "opencode":
        return {}
    latest = None
    try:
        with open(source.path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except (ValueError, json.JSONDecodeError):
                    continue
                if before is not None:
                    try:
                        recorded_at = datetime.fromisoformat(
                            str(row.get("timestamp") or "").replace("Z", "+00:00")
                        ).timestamp()
                    except (TypeError, ValueError):
                        continue
                    if recorded_at > float(before):
                        continue
                payload = row.get("payload") or {}
                if (source.provider == "codex" and row.get("type") == "event_msg"
                        and payload.get("type") == "token_count"):
                    info = payload.get("info") or {}
                    usage = info.get("total_token_usage")
                    if isinstance(usage, dict):
                        latest = usage_from_line(json.dumps({"usage": usage})) or latest
                else:
                    latest = usage_from_line(line) or latest
    except (OSError, UnicodeDecodeError):
        return {}
    return latest or {}
