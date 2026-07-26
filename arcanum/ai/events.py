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


def error_text(line: str) -> str:
    """Recover a concise provider error from one structured CLI event."""
    try:
        row = json.loads(line)
    except ValueError:
        return ""
    if not isinstance(row, dict):
        return ""
    values = []
    if row.get("type") == "error":
        values.append(row.get("message"))
    error = row.get("error")
    if isinstance(error, dict):
        values.append(error.get("message") or error.get("name"))
    elif isinstance(error, str):
        values.append(error)
    payload = row.get("payload")
    if isinstance(payload, dict):
        nested = payload.get("error")
        if isinstance(nested, dict):
            values.append(nested.get("message") or nested.get("name"))
        elif isinstance(nested, str):
            values.append(nested)
    return next((str(value).strip() for value in reversed(values)
                 if str(value or "").strip()), "")


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
    creation = usage.get("cache_creation")
    creation = creation if isinstance(creation, dict) else {}
    if anthropic_cache_write is None and creation:
        anthropic_cache_write = sum(
            int(value or 0) for value in creation.values()
            if isinstance(value, (int, float)))
    # Reported apart because they are priced apart: the extended TTL costs 2x base
    # input against the 5-minute default's 1.25x. A subset of cacheWriteTokens, so
    # every existing total that sums the input side stays correct.
    cache_write_1h = creation.get("ephemeral_1h_input_tokens")
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
    if isinstance(cache_write_1h, (int, float)):
        normalized["cacheWrite1hTokens"] = int(cache_write_1h)
    elif "inputTokens" in normalized:
        normalized["freshInputTokens"] = max(
            0, normalized["inputTokens"] - normalized.get("cachedInputTokens", 0)
            - normalized.get("cacheWriteTokens", 0))
    return normalized or None


def step_tokens_from_line(line: str) -> dict | None:
    """Return one completed step's token counts, for live progress display.

    Deliberately narrower than ``usage_from_line``: this reads opencode's per-step
    ``step_finish`` schema, whose counts a caller can sum as steps land.  Schemas that
    report cumulative per-turn usage are not wired here, because summing those would
    double count; they stay pending until the turn ends and usage is recorded.
    """
    try:
        row = json.loads(line)
    except ValueError:
        return None
    if not isinstance(row, dict):
        return None
    part = row.get("part")
    tokens = part.get("tokens") if isinstance(part, dict) else None
    if not isinstance(tokens, dict):
        return None

    def count(value) -> int:
        return int(value) if isinstance(value, (int, float)) else 0

    cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
    fresh = count(tokens.get("input"))
    counts = {
        "input": fresh + count(cache.get("read")) + count(cache.get("write")),
        "output": count(tokens.get("output")),
        "reasoning": count(tokens.get("reasoning")),
    }
    counts["total"] = count(tokens.get("total")) or sum(counts.values())
    return counts if counts["total"] else None


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
