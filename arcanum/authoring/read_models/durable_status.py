"""Read-only projection of durable authoring sidecars for the HTTP status API."""
from __future__ import annotations

import json
import os
import re


_BUILD_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def _safe_id(build_id: str) -> str:
    value = str(build_id or "")
    if not _BUILD_ID.fullmatch(value):
        raise ValueError("bad build id")
    return value


def load_conversation(build_root: str, build_id: str, limit: int = 120) -> list[dict]:
    path = os.path.join(build_root, f"{_safe_id(build_id)}.conversation.jsonl")
    try:
        with open(path, encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    return [row for row in rows if isinstance(row, dict)][-max(1, int(limit)):]


def public_course_status(build_root: str, build_id: str) -> dict:
    path = os.path.join(build_root, f"{_safe_id(build_id)}.course-state.json")
    with open(path, encoding="utf-8") as handle:
        state = json.load(handle)
    sections = state.get("sections") or []
    active = state.get("activeObligations") or []
    return {
        "mapDigest": state.get("mapDigest", ""),
        "currentSection": state.get("currentSection", ""),
        "spine": [{key: row.get(key) for key in (
            "id", "title", "milestone", "status", "mark", "statusLabel")}
                  for row in sections if isinstance(row, dict)],
        "openObligations": len(active),
        "dueObligations": sum(1 for item in active if isinstance(item, dict)
                              and (item.get("dueNow") or item.get("overdue"))),
        "blockers": list(state.get("blockers") or []),
        "validatorAi": dict(state.get("validatorAi") or {}),
    }
