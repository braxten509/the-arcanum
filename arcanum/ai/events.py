"""Provider-neutral structured event parsing shared by runtime adapters."""
from __future__ import annotations

import json


def assistant_text(line: str) -> str:
    try:
        row = json.loads(line)
    except ValueError:
        return ""
    if not isinstance(row, dict):
        return ""
    item = row.get("item")
    if (row.get("type") == "item.completed" and isinstance(item, dict)
            and item.get("type") == "agent_message"):
        return str(item.get("text") or "")
    if row.get("type") == "assistant":
        message = row.get("message")
        content = (message.get("content") or []) if isinstance(message, dict) else []
        if not isinstance(content, list):
            return ""
        return "\n".join(str(block.get("text") or "") for block in content
                         if isinstance(block, dict) and block.get("type") == "text")
    part = row.get("part") or row.get("message") or {}
    if isinstance(part, dict) and part.get("type") in ("text", "assistant"):
        return str(part.get("text") or part.get("content") or "")
    return ""


def usage_from_line(line: str) -> dict | None:
    """Normalize provider turn-usage rows without assuming one CLI schema."""
    try:
        row = json.loads(line)
    except ValueError:
        return None
    if not isinstance(row, dict):
        return None
    usage = row.get("usage") or row.get("token_usage")
    if not isinstance(usage, dict):
        item = row.get("item")
        usage = item.get("usage") if isinstance(item, dict) else None
    if not isinstance(usage, dict):
        return None
    input_details = usage.get("input_tokens_details") or {}
    output_details = usage.get("output_tokens_details") or {}
    if isinstance(input_details, dict):
        usage = {**input_details, **usage}
    if isinstance(output_details, dict):
        usage = {**output_details, **usage}
    anthropic_cache_read = usage.get("cache_read_input_tokens")
    anthropic_cache_write = usage.get("cache_creation_input_tokens")
    if anthropic_cache_write is None and isinstance(usage.get("cache_creation"), dict):
        anthropic_cache_write = sum(
            int(value or 0) for value in usage["cache_creation"].values()
            if isinstance(value, (int, float)))
    aliases = {
        "inputTokens": ("input_tokens", "inputTokens"),
        "cachedInputTokens": ("cached_input_tokens", "cachedInputTokens",
                              "cached_tokens", "cache_read_input_tokens"),
        "cacheWriteTokens": ("cache_write_tokens", "cacheWriteTokens",
                             "cache_creation_input_tokens"),
        "outputTokens": ("output_tokens", "outputTokens"),
        "reasoningTokens": ("reasoning_tokens", "reasoningTokens"),
        "totalTokens": ("total_tokens", "totalTokens"),
    }
    normalized = {}
    for target, names in aliases.items():
        value = next((usage.get(name) for name in names
                      if usage.get(name) is not None), None)
        if isinstance(value, (int, float)):
            normalized[target] = int(value)
    if isinstance(anthropic_cache_write, (int, float)):
        normalized["cacheWriteTokens"] = int(anthropic_cache_write)
    if (isinstance(anthropic_cache_read, (int, float))
            or isinstance(anthropic_cache_write, (int, float))):
        fresh = normalized.get("inputTokens", 0)
        normalized["cachedInputTokens"] = int(anthropic_cache_read or 0)
        normalized["cacheWriteTokens"] = int(anthropic_cache_write or 0)
        normalized["freshInputTokens"] = fresh
        normalized["inputTokens"] = (fresh + normalized["cachedInputTokens"]
                                     + normalized["cacheWriteTokens"])
    elif "inputTokens" in normalized:
        normalized["freshInputTokens"] = max(
            0, normalized["inputTokens"] - normalized.get("cachedInputTokens", 0)
            - normalized.get("cacheWriteTokens", 0))
    return normalized or None


def opencode_output_session_id(line: str) -> str:
    try:
        row = json.loads(line)
    except ValueError:
        return ""
    if not isinstance(row, dict):
        return ""
    part = row.get("part")
    return str(row.get("sessionID") or (
        part.get("sessionID") if isinstance(part, dict) else "") or "")


def session_id_from_line(line: str) -> str:
    try:
        row = json.loads(line)
    except ValueError:
        return ""
    if not isinstance(row, dict):
        return ""
    part = row.get("part")
    return str(row.get("thread_id") or row.get("session_id") or row.get("sessionID")
               or (part.get("sessionID") if isinstance(part, dict) else "") or "")
