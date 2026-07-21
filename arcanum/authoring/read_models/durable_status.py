"""Read-only projection of durable authoring sidecars for the HTTP status API."""
from __future__ import annotations

import json
import os
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from ..adapters import validator_live
from ..adapters.status_log import load_status_lines


_BUILD_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_GPT_COST = re.compile(
    r"^GPT API-EQUIVALENT COST COMPLETE "
    r"\[(?P<at>[0-9]+(?:\.[0-9]+)?)\] › PHASE (?P<phase>[1-8]) "
    r"(?:(?:SECTION (?P<section>[A-Za-z0-9_-]+))|TOTAL)\b")
_USD_CENT = Decimal("0.01")


def _safe_id(build_id: str) -> str:
    value = str(build_id or "")
    if not _BUILD_ID.fullmatch(value):
        raise ValueError("bad build id")
    return value


def _cost_conversation_rows(build_root: str, build_id: str) -> list[dict]:
    """Project durable GPT completion totals into the visible conversation."""
    rows = []
    for line in load_status_lines(build_id, build_dir=build_root):
        match = _GPT_COST.match(str(line or ""))
        if not match:
            continue
        timestamp = match.group("at")
        rows.append({
            "at": float(timestamp),
            "kind": "harness",
            "text": line.replace(f" [{timestamp}]", "", 1),
            "eventKey": (f"gpt-cost:{match.group('phase')}:"
                         f"{match.group('section') or 'total'}"),
        })
    return rows


def load_conversation(build_root: str, build_id: str, limit: int = 120) -> list[dict]:
    build_id = _safe_id(build_id)
    path = os.path.join(build_root, f"{build_id}.conversation.jsonl")
    try:
        with open(path, encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
    except (OSError, ValueError, json.JSONDecodeError):
        rows = []
    costs = _cost_conversation_rows(build_root, build_id)
    # The in-flight validator row is replaced on every poll, never appended, so it
    # updates in place and retires itself when the call ends.
    live = validator_live.row(build_root, build_id)
    cost_keys = {row["eventKey"] for row in costs} | {validator_live.EVENT_KEY}
    merged = [row for row in rows if isinstance(row, dict)
              and row.get("eventKey") not in cost_keys]
    merged.extend(costs)
    if live:
        merged.append(live)
    merged.sort(key=lambda row: float(row.get("at") or 0))
    return merged[-max(1, int(limit)):]


def clear_conversation(build_root: str, build_id: str) -> bool:
    """Drop the transcript of a run that ended. Costs live elsewhere and survive."""
    try:
        os.remove(os.path.join(build_root, f"{_safe_id(build_id)}.conversation.jsonl"))
        return True
    except (OSError, ValueError):
        return False


def _dollars(value) -> Decimal:
    try:
        return max(Decimal("0"), Decimal(str(value or 0)))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def load_gpt_running_cost(build_root: str, build_id: str) -> dict | None:
    """Project the cumulative GPT API-equivalent total from the durable ledger.

    The displayed lifetime amount is the sum of the same cent-rounded units shown
    at phase boundaries. Phase 3 keeps its stricter contract: its displayed unit
    is the sum of its individually rounded section totals.
    """
    build_id = _safe_id(build_id)
    path = os.path.join(build_root, f"{build_id}.ai-cost-totals.jsonl")
    rows = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except (ValueError, json.JSONDecodeError):
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        return None

    phases = {int(row.get("phase")): row for row in rows
              if row.get("type") == "phase-total"
              and str(row.get("phase", "")).isdigit()
              and int(row.get("phase")) in range(1, 9)}
    if not phases:
        return None
    gpt_turns = sum(max(0, int(row.get("gptTurnCount") or 0))
                    for row in phases.values())
    if not gpt_turns:
        return None
    gpt_unpriced = sum(max(0, int(row.get("gptUnpricedTurns") or 0))
                       for row in phases.values())
    sections = [row for row in rows if row.get("type") == "section-total"
                and int(row.get("phase") or 0) == 3]
    displayed = Decimal("0")
    for phase in range(1, 9):
        if phase == 3 and sections:
            displayed += sum((_dollars(row.get("apiEquivalentUsd")).quantize(
                _USD_CENT, rounding=ROUND_HALF_UP) for row in sections), Decimal("0"))
        else:
            displayed += _dollars(phases.get(phase, {}).get("apiEquivalentUsd")).quantize(
                _USD_CENT, rounding=ROUND_HALF_UP)
    raw_total = sum((_dollars(row.get("apiEquivalentUsd"))
                     for row in phases.values()), Decimal("0"))
    priced_turns = max(0, gpt_turns - gpt_unpriced)
    source = next((row for row in phases.values()
                   if row.get("pricingVersion") or row.get("pricingSource")), {})
    return {
        "gptTurnCount": gpt_turns,
        "gptPricedTurns": priced_turns,
        "gptUnpricedTurns": gpt_unpriced,
        "gptPricingComplete": gpt_unpriced == 0,
        "apiEquivalentUsd": round(float(raw_total), 9),
        "displayUsd": float(displayed),
        "pricingVersion": source.get("pricingVersion"),
        "pricingSource": source.get("pricingSource"),
    }


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
