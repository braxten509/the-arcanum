"""Durable per-turn token costs and lifetime phase/section rollups."""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
import time
from datetime import datetime, timezone


TURN_LIMIT = 500
USAGE_KEYS = ("inputTokens", "freshInputTokens", "cachedInputTokens",
              "cacheWriteTokens", "outputTokens", "reasoningTokens", "totalTokens")
PRICING_VERSION = "openai-standard-2026-07-17"
PRICING_SOURCE = "https://developers.openai.com/api/docs/pricing"

# USD per one million tokens. Unknown models remain logged with an explicitly
# incomplete dollar total; token accounting must never invent a price.
MODEL_PRICES = {
    "gpt-5.6-sol": {"freshInput": 5.0, "cachedInput": 0.5,
                    "cacheWriteInput": 6.25, "output": 30.0},
    "gpt-5.6-terra": {"freshInput": 2.5, "cachedInput": 0.25,
                      "cacheWriteInput": 3.125, "output": 15.0},
    "gpt-5.6-luna": {"freshInput": 1.0, "cachedInput": 0.1,
                     "cacheWriteInput": 1.25, "output": 6.0},
}


def turns_path(build_dir, build_id):
    return os.path.join(build_dir, f"{build_id}.ai-costs.jsonl")


def totals_path(build_dir, build_id):
    return os.path.join(build_dir, f"{build_id}.ai-cost-totals.jsonl")


def _state_path(build_dir, build_id):
    return os.path.join(build_dir, f"{build_id}.ai-cost-state.json")


def _lock_path(build_dir, build_id):
    return os.path.join(build_dir, f"{build_id}.ai-costs.lock")


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, type(default)) else default
    except (OSError, ValueError):
        return default


def _atomic_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".ai-cost-", suffix=".tmp",
                                     dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        try:
            os.remove(temporary)
        except OSError:
            pass


def _atomic_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".ai-cost-", suffix=".tmp",
                                     dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False,
                                        separators=(",", ":")) + "\n")
        os.replace(temporary, path)
    finally:
        try:
            os.remove(temporary)
        except OSError:
            pass


def _read_jsonl(path):
    rows = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        pass
    return rows


def _usage(value):
    if not isinstance(value, dict):
        return None
    normalized = {key: max(0, int(value.get(key) or 0)) for key in USAGE_KEYS}
    if not value.get("freshInputTokens") and normalized["inputTokens"]:
        normalized["freshInputTokens"] = max(
            0, normalized["inputTokens"] - normalized["cachedInputTokens"]
            - normalized["cacheWriteTokens"])
    if not normalized["totalTokens"]:
        normalized["totalTokens"] = (normalized["inputTokens"]
                                      + normalized["outputTokens"])
    return normalized


def _delta(current, previous):
    if not previous:
        return current
    # A counter decrease means a provider-side session/reset boundary.
    if any(current[key] < int(previous.get(key) or 0) for key in USAGE_KEYS):
        return current
    return {key: current[key] - int(previous.get(key) or 0) for key in USAGE_KEYS}


def _cost(model, usage):
    rates = MODEL_PRICES.get(str(model or ""))
    if not usage or not rates:
        return None, rates
    amount = (
        usage["freshInputTokens"] * rates["freshInput"]
        + usage["cachedInputTokens"] * rates["cachedInput"]
        + usage["cacheWriteTokens"] * rates["cacheWriteInput"]
        + usage["outputTokens"] * rates["output"]
    ) / 1_000_000
    return round(amount, 9), rates


def _bucket():
    return {"turnCount": 0, "pricedTurns": 0, "unpricedTurns": 0,
            "usage": {key: 0 for key in USAGE_KEYS},
            "apiEquivalentUsd": 0.0, "directApiUsd": 0.0}


def _add(bucket, usage, equivalent, direct):
    bucket["turnCount"] += 1
    if equivalent is None:
        bucket["unpricedTurns"] += 1
    else:
        bucket["pricedTurns"] += 1
        bucket["apiEquivalentUsd"] = round(
            float(bucket["apiEquivalentUsd"]) + equivalent, 9)
        bucket["directApiUsd"] = round(
            float(bucket["directApiUsd"]) + direct, 9)
    if usage:
        for key in USAGE_KEYS:
            bucket["usage"][key] += usage[key]


def _section_ids(build_dir, build_id, state):
    path = os.path.join(build_dir, f"{build_id}.course-map.json")
    course = _read_json(path, {})
    ids = [str(row.get("id")) for row in course.get("sections") or []
           if isinstance(row, dict) and row.get("id")]
    observed = list((state.get("sections") or {}).keys())
    return list(dict.fromkeys([*ids, *observed]))


def _summary_row(build_id, scope, value, *, phase, section=None):
    return {
        "version": 1, "type": scope, "buildId": build_id,
        "phase": phase, **({"section": section} if section else {}),
        "turnCount": value["turnCount"], "pricedTurns": value["pricedTurns"],
        "unpricedTurns": value["unpricedTurns"],
        "pricingComplete": value["unpricedTurns"] == 0,
        "usage": value["usage"],
        "apiEquivalentUsd": round(float(value["apiEquivalentUsd"]), 9),
        "directApiUsd": round(float(value["directApiUsd"]), 9),
        "pricingVersion": PRICING_VERSION, "pricingSource": PRICING_SOURCE,
    }


def _write_totals(build_dir, build_id, state):
    phases = state.setdefault("phases", {})
    sections = state.setdefault("sections", {})
    rows = []
    for phase in range(1, 9):
        value = phases.setdefault(str(phase), _bucket())
        rows.append(_summary_row(build_id, "phase-total", value, phase=phase))
    for section in _section_ids(build_dir, build_id, state):
        value = sections.setdefault(section, _bucket())
        rows.append(_summary_row(build_id, "section-total", value,
                                 phase=3, section=section))
    _atomic_jsonl(totals_path(build_dir, build_id), rows)


def record_ai_turn(build_dir, build_id, *, phase, role, stage, kind, model,
                   effort="", transport="cli", status="complete", section=None,
                   session_id="", usage=None, usage_mode="turn", started_at=None,
                   ended_at=None, response_id=""):
    """Append one AI invocation and update non-trimmable lifetime totals."""
    if transport == "test-adapter":
        return None
    os.makedirs(build_dir, exist_ok=True)
    ended_at = float(ended_at or time.time())
    started_at = float(started_at or ended_at)
    current_usage = _usage(usage)
    lock = open(_lock_path(build_dir, build_id), "a+", encoding="utf-8")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        state = _read_json(_state_path(build_dir, build_id), {})
        state.setdefault("version", 1)
        counters = state.setdefault("lastCounters", {})
        counter_key = "|".join((str(role), str(kind), str(model), str(session_id)))
        turn_usage = current_usage
        if current_usage and usage_mode == "cumulative" and session_id:
            turn_usage = _delta(current_usage, counters.get(counter_key))
            counters[counter_key] = current_usage
        equivalent, rates = _cost(model, turn_usage)
        direct = equivalent if transport == "responses-api" and equivalent is not None else 0.0
        phase = int(phase)
        phase_bucket = state.setdefault("phases", {}).setdefault(str(phase), _bucket())
        _add(phase_bucket, turn_usage, equivalent, direct)
        if phase == 3 and section:
            section_bucket = state.setdefault("sections", {}).setdefault(str(section), _bucket())
            _add(section_bucket, turn_usage, equivalent, direct)
        row = {
            "version": 1, "type": "ai-turn", "buildId": build_id,
            "at": ended_at,
            "timestamp": datetime.fromtimestamp(ended_at, timezone.utc).isoformat(),
            "startedAt": started_at, "durationSeconds": round(max(0, ended_at-started_at), 3),
            "phase": phase, **({"section": str(section)} if section else {}),
            "role": str(role), "stage": str(stage), "status": str(status),
            "kind": str(kind), "model": str(model), "effort": str(effort or ""),
            "transport": str(transport), "sessionId": str(session_id or ""),
            "usage": turn_usage, "usageMode": str(usage_mode),
            "counterUsage": current_usage if usage_mode == "cumulative" else None,
            "pricingStatus": ("priced" if equivalent is not None
                              else "usage-unavailable" if not turn_usage else "model-unpriced"),
            "pricingVersion": PRICING_VERSION, "pricingSource": PRICING_SOURCE,
            "ratesPerMillion": rates, "apiEquivalentUsd": equivalent,
            "directApiUsd": direct if equivalent is not None else None,
        }
        if response_id:
            row["responseId"] = str(response_id)
        rows = [*_read_jsonl(turns_path(build_dir, build_id)), row]
        # Keep the 500 records nearest to now, then retain chronological readability.
        retention_now = time.time()
        rows = sorted(
            rows, key=lambda item: abs(retention_now-float(item.get("at") or 0)))[:TURN_LIMIT]
        rows.sort(key=lambda item: float(item.get("at") or 0))
        _atomic_jsonl(turns_path(build_dir, build_id), rows)
        _write_totals(build_dir, build_id, state)
        state["updatedAt"] = ended_at
        _atomic_json(_state_path(build_dir, build_id), state)
        return row
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()


def ensure_cost_totals(build_dir, build_id):
    """Materialize zero-valued phase and sealed-section rows before the first turn."""
    os.makedirs(build_dir, exist_ok=True)
    lock = open(_lock_path(build_dir, build_id), "a+", encoding="utf-8")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        state = _read_json(_state_path(build_dir, build_id), {})
        state.setdefault("version", 1)
        state.setdefault("lastCounters", {})
        detail = turns_path(build_dir, build_id)
        if not os.path.exists(detail):
            _atomic_jsonl(detail, [])
        _write_totals(build_dir, build_id, state)
        _atomic_json(_state_path(build_dir, build_id), state)
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()
