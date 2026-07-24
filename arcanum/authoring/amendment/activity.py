"""Projection of verbose provider events into the Binder transcript."""
from __future__ import annotations

import json
import time
from datetime import datetime

from ...ai.events import assistant_text
from ...forge.tool_trace import format_tool_event, tool_events


def activity_rows(provider_kind, line):
    try:
        record = json.loads(line)
    except (TypeError, ValueError):
        return []
    if not isinstance(record, dict):
        return []
    provider = {
        "codex-cli": "codex",
        "claude-cli": "claude",
        "opencode-cli": "opencode",
        "antigravity-cli": "antigravity",
    }.get(provider_kind, "")
    rows = []
    occurred_at = time.time()
    event_stamp = str(
        record.get("timestamp") or datetime.now().astimezone().isoformat())
    message = assistant_text(line).strip()
    if message:
        rows.append({
            "kind": "assistant", "text": message, "at": occurred_at,
        })

    events = list(tool_events(provider, record))
    item = record.get("item")
    if provider == "codex" and isinstance(item, dict):
        item_type = str(item.get("type") or "")
        detail, tool = "", ""
        if item_type == "command_execution":
            tool, detail = "shell", str(item.get("command") or "")
        elif item_type in {"mcp_tool_call", "tool_call"}:
            tool = str(item.get("tool") or item.get("name") or item_type)
            detail = json.dumps(
                item.get("arguments") or item.get("input") or {},
                ensure_ascii=False, separators=(",", ":"))
        elif item_type in {"web_search", "web_search_call"}:
            tool = "web_search"
            detail = str(item.get("query") or item.get("action") or "")
        elif item_type in {"file_change", "file_changes"}:
            changes = item.get("changes") or []
            paths = [
                str(change.get("path") or "") for change in changes
                if isinstance(change, dict) and change.get("path")
            ]
            tool, detail = "file_change", ", ".join(paths)
        if tool and detail:
            events.append({
                "at": event_stamp, "provider": provider,
                "tool": tool, "detail": detail,
            })
    part = record.get("part")
    if (provider == "opencode" and isinstance(part, dict)
            and part.get("type") == "tool"):
        events.extend(tool_events(provider, {
            "type": "tool",
            "timestamp": event_stamp,
            "tool": part.get("tool"),
            "state": part.get("state") or {},
        }))
    for event in events:
        if not event.get("at"):
            event["at"] = event_stamp
        rows.append({
            "kind": "tool",
            "text": format_tool_event(event),
            "at": occurred_at,
        })
    return rows
