"""Durable per-turn token costs and lifetime phase/section rollups."""
from __future__ import annotations

import fcntl
import json
import os
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from arcanum.ai.economics.estimation import cache_write_cost
from .costing import (GPT_MODELS, MODEL_PRICES, PRICED_MODELS, PRICING_SOURCE,
                      PRICING_VERSION)
from .costing.counters import (
    USAGE_KEYS,
    counter_key as _counter_key,
    delta as _delta,
    implausible_delta,
    normalize as _usage,
    previous_counter as _previous_counter,
)
from .costing.storage import (
    atomic_json as _atomic_json,
    atomic_jsonl as _atomic_jsonl,
    read_json as _read_json,
    read_jsonl as _read_jsonl,
)


TURN_LIMIT = 500
USD_CENT = Decimal("0.01")


def turns_path(build_dir, build_id):
    return os.path.join(build_dir, f"{build_id}.ai-costs.jsonl")


def totals_path(build_dir, build_id):
    return os.path.join(build_dir, f"{build_id}.ai-cost-totals.jsonl")


def _state_path(build_dir, build_id):
    return os.path.join(build_dir, f"{build_id}.ai-cost-state.json")


def _lock_path(build_dir, build_id):
    return os.path.join(build_dir, f"{build_id}.ai-costs.lock")


def _cost(model, usage):
    rates = MODEL_PRICES.get(str(model or ""))
    if not usage or not rates:
        return None, rates
    amount = (
        usage["freshInputTokens"] * rates["freshInput"]
        + usage["cachedInputTokens"] * rates["cachedInput"]
        + cache_write_cost(usage, rates)
        + usage["outputTokens"] * rates["output"]
    ) / 1_000_000
    return round(amount, 9), rates


def estimate_api_equivalent_cost(model, usage):
    """Price one non-API turn as if its reported usage used the matching API.

    Binder and other CLI surfaces use this projection without writing a durable
    build ledger. Unknown models or absent token usage remain explicitly unpriced.
    """
    normalized = _usage(usage)
    amount, rates = _cost(model, normalized)
    if amount is None:
        return None
    return {
        "model": str(model or ""),
        "usd": amount,
        "usage": normalized,
        "rates": dict(rates),
        "pricingVersion": PRICING_VERSION,
        "pricingSource": PRICING_SOURCE,
    }


def _bucket():
    return {"turnCount": 0, "pricedTurns": 0, "unpricedTurns": 0,
            "apiTurnCount": 0, "apiUnpricedTurns": 0,
            "claudeTurnCount": 0,
            "gptTurnCount": 0, "gptUnpricedTurns": 0,
            "usage": {key: 0 for key in USAGE_KEYS},
            "apiEquivalentUsd": 0.0, "directApiUsd": 0.0}


def _normalize_bucket(bucket):
    defaults = _bucket()
    for key, value in defaults.items():
        if key == "usage":
            current = bucket.setdefault("usage", {})
            for usage_key in USAGE_KEYS:
                current.setdefault(usage_key, 0)
        elif key not in bucket:
            # Older ledgers predate GPT-specific completeness counters. Every
            # priced turn in those ledgers used one of the verified GPT rates.
            if key in ("apiTurnCount", "gptTurnCount"):
                bucket[key] = int(bucket.get("gptTurnCount")
                                  or bucket.get("pricedTurns") or 0)
            elif key == "apiUnpricedTurns":
                bucket[key] = int(bucket.get("gptUnpricedTurns") or 0)
            else:
                bucket[key] = value
    return bucket


def _add(bucket, usage, equivalent, direct, *, tracked_model=False,
         claude_model=False, gpt_model=False):
    _normalize_bucket(bucket)
    bucket["turnCount"] += 1
    if tracked_model:
        bucket["apiTurnCount"] += 1
        if equivalent is None:
            bucket["apiUnpricedTurns"] += 1
    if claude_model:
        bucket["claudeTurnCount"] += 1
    if gpt_model:
        bucket["gptTurnCount"] += 1
        if equivalent is None:
            bucket["gptUnpricedTurns"] += 1
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


def _combined_buckets(values):
    combined = _bucket()
    for raw in values:
        value = _normalize_bucket(raw)
        for key in ("turnCount", "pricedTurns", "unpricedTurns",
                    "apiTurnCount", "apiUnpricedTurns",
                    "claudeTurnCount",
                    "gptTurnCount", "gptUnpricedTurns"):
            combined[key] += int(value.get(key) or 0)
        for key in USAGE_KEYS:
            combined["usage"][key] += int(value["usage"].get(key) or 0)
        for key in ("apiEquivalentUsd", "directApiUsd"):
            combined[key] = round(float(combined[key]) + float(value.get(key) or 0), 9)
    return combined


def _section_ids(build_dir, build_id, state):
    path = os.path.join(build_dir, f"{build_id}.course-map.json")
    course = _read_json(path, {})
    ids = [str(row.get("id")) for row in course.get("sections") or []
           if isinstance(row, dict) and row.get("id")]
    observed = list((state.get("sections") or {}).keys())
    return list(dict.fromkeys([*ids, *observed]))


def _summary_row(build_id, scope, value, *, phase, section=None):
    value = _normalize_bucket(value)
    return {
        "version": 1, "type": scope, "buildId": build_id,
        "phase": phase, **({"section": section} if section else {}),
        "turnCount": value["turnCount"], "pricedTurns": value["pricedTurns"],
        "unpricedTurns": value["unpricedTurns"],
        "pricingComplete": value["unpricedTurns"] == 0,
        "apiTurnCount": value["apiTurnCount"],
        "apiUnpricedTurns": value["apiUnpricedTurns"],
        "apiPricingComplete": value["apiUnpricedTurns"] == 0,
        "claudeTurnCount": value["claudeTurnCount"],
        "gptTurnCount": value["gptTurnCount"],
        "gptUnpricedTurns": value["gptUnpricedTurns"],
        "gptPricingComplete": value["gptUnpricedTurns"] == 0,
        "usage": value["usage"],
        "apiEquivalentUsd": round(float(value["apiEquivalentUsd"]), 9),
        "directApiUsd": round(float(value["directApiUsd"]), 9),
        "pricingVersion": PRICING_VERSION, "pricingSource": PRICING_SOURCE,
    }


def _write_totals(build_dir, build_id, state):
    phases = state.setdefault("phases", {})
    sections = state.setdefault("sections", {})
    section_ids = _section_ids(build_dir, build_id, state)
    section_values = [sections.setdefault(section, _bucket())
                      for section in section_ids]
    rows = []
    for phase in range(1, 9):
        stored = phases.setdefault(str(phase), _bucket())
        # Phase 3 is definitionally the sum of its sealed section units. Do not
        # let an unattributed or rounded phase bucket drift from those rows.
        value = _combined_buckets(section_values) if phase == 3 else stored
        rows.append(_summary_row(build_id, "phase-total", value, phase=phase))
    for section, value in zip(section_ids, section_values):
        rows.append(_summary_row(build_id, "section-total", value,
                                 phase=3, section=section))
    _atomic_jsonl(totals_path(build_dir, build_id), rows)


def record_ai_turn(build_dir, build_id, *, phase, role, stage, kind, model,
                   effort="", transport="cli", status="complete", section=None,
                   session_id="", usage=None, usage_mode="turn", started_at=None,
                   ended_at=None, response_id="", usage_baseline=None):
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
        turn_usage = current_usage
        if current_usage and usage_mode == "cumulative" and session_id:
            counter_key, previous = _previous_counter(
                counters, role, kind, model, session_id)
            if usage_baseline is not None:
                # A resumed provider thread may predate this build or ledger. Its
                # trace supplies the exact counter immediately before this turn,
                # so lifetime history can never be charged to the current unit.
                previous = _usage(usage_baseline)
            turn_usage = _delta(current_usage, previous)
            counters[counter_key] = current_usage
        rejected = implausible_delta(
            turn_usage, ended_at - started_at) if usage_mode == "cumulative" else ""
        rejected_usage = None
        if rejected:
            # Charging this would both misreport the run and trip the section
            # budget pause on money nobody spent. Drop it from every total, keep
            # the whole delta on the row, and let the refreshed counter above
            # make the next turn's baseline correct.
            print(f"AI COST WARNING › rejected an implausible turn delta › {rejected}",
                  flush=True)
            rejected_usage, turn_usage = turn_usage, None
        equivalent, rates = _cost(model, turn_usage)
        tracked_model = str(model or "") in PRICED_MODELS
        claude_model = str(model or "").startswith("claude-")
        gpt_model = str(model or "") in GPT_MODELS
        direct = equivalent if transport == "responses-api" and equivalent is not None else 0.0
        phase = int(phase)
        phase_bucket = state.setdefault("phases", {}).setdefault(str(phase), _bucket())
        _add(phase_bucket, turn_usage, equivalent, direct,
             tracked_model=tracked_model, claude_model=claude_model,
             gpt_model=gpt_model)
        if phase == 3 and section:
            section_bucket = state.setdefault("sections", {}).setdefault(str(section), _bucket())
            _add(section_bucket, turn_usage, equivalent, direct,
                 tracked_model=tracked_model, claude_model=claude_model,
                 gpt_model=gpt_model)
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
            "counterBaseline": (_usage(usage_baseline)
                                if usage_mode == "cumulative"
                                and usage_baseline is not None else None),
            **({"rejectedUsage": rejected_usage, "rejectedReason": rejected}
               if rejected else {}),
            "pricingStatus": ("implausible-counter-delta" if rejected
                              else "priced" if equivalent is not None
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


def rewind_ai_costs(build_dir, build_id, phase):
    """Discard visible accounting for ``phase`` onward after a phase restart.

    Provider cumulative-counter baselines remain internal so a resumed provider
    session cannot make discarded tokens reappear in the rebuilt phase.
    """
    phase = int(phase)
    if phase not in range(1, 9):
        raise ValueError("phase must be between 1 and 8")
    lock = open(_lock_path(build_dir, build_id), "a+", encoding="utf-8")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        prior = _read_json(_state_path(build_dir, build_id), {})
        all_rows = _read_jsonl(turns_path(build_dir, build_id))
        retained = []
        for row in all_rows:
            try:
                if int(row.get("phase") or 0) < phase:
                    retained.append(row)
            except (TypeError, ValueError):
                retained.append(row)
        # State buckets are non-trimmable lifetime totals; the detail journal is
        # intentionally capped at TURN_LIMIT and therefore cannot rebuild them.
        phases = {}
        for key, value in (prior.get("phases") or {}).items():
            try:
                if int(key) < phase:
                    phases[str(key)] = value
            except (TypeError, ValueError):
                continue
        state = {
            "version": 1,
            "lastCounters": dict(prior.get("lastCounters") or {}),
            "phases": phases,
            "sections": (dict(prior.get("sections") or {}) if phase > 3 else {}),
        }
        _atomic_jsonl(turns_path(build_dir, build_id), retained)
        _write_totals(build_dir, build_id, state)
        state["updatedAt"] = time.time()
        _atomic_json(_state_path(build_dir, build_id), state)
        return len(all_rows) - len(retained)
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()


def rewind_ai_cost_sections(build_dir, build_id, sections):
    from .costing.rewind import rewind_sections
    return rewind_sections(build_dir, build_id, sections)


def api_equivalent_completion_cost(build_dir, build_id, *, phase, section=None):
    """Return priced Claude/GPT API-equivalent cost at one unit boundary."""
    phase = int(phase)
    lock = open(_lock_path(build_dir, build_id), "a+", encoding="utf-8")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
        state = _read_json(_state_path(build_dir, build_id), {})
        if phase == 3 and section is None:
            section_ids = _section_ids(build_dir, build_id, state)
            buckets = [_normalize_bucket((state.get("sections") or {}).get(sid, _bucket()))
                       for sid in section_ids]
            value = _combined_buckets(buckets)
            # The visible Phase-3 amount is the exact sum of the visible,
            # cent-rounded section amounts, as requested by the UI contract.
            displayed = sum(
                (Decimal(str(bucket.get("apiEquivalentUsd") or 0)).quantize(
                    USD_CENT, rounding=ROUND_HALF_UP) for bucket in buckets), Decimal("0"))
        else:
            values = state.get("sections") if section else state.get("phases")
            key = str(section) if section else str(phase)
            value = _normalize_bucket((values or {}).get(key, _bucket()))
            displayed = Decimal(str(value.get("apiEquivalentUsd") or 0)).quantize(
                USD_CENT, rounding=ROUND_HALF_UP)
        if int(value.get("apiTurnCount") or 0) == 0:
            return None
        return {
            "phase": phase, **({"section": str(section)} if section else {}),
            "sectionCount": len(section_ids) if phase == 3 and section is None else None,
            "apiTurnCount": int(value.get("apiTurnCount") or 0),
            "apiUnpricedTurns": int(value.get("apiUnpricedTurns") or 0),
            "gptTurnCount": int(value.get("gptTurnCount") or 0),
            "gptUnpricedTurns": int(value.get("gptUnpricedTurns") or 0),
            "apiEquivalentUsd": round(float(value.get("apiEquivalentUsd") or 0), 9),
            "displayUsd": float(displayed),
            "pricingVersion": PRICING_VERSION, "pricingSource": PRICING_SOURCE,
        }
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()


def gpt_completion_cost(build_dir, build_id, *, phase, section=None):
    """Compatibility alias for the provider-neutral completion-cost report."""
    return api_equivalent_completion_cost(
        build_dir, build_id, phase=phase, section=section)


def completed_cost_line(build_dir, build_id, *, phase, section=None, at=None):
    """Format one user-facing Claude/GPT API-equivalent completion line."""
    report = api_equivalent_completion_cost(
        build_dir, build_id, phase=phase, section=section)
    if not report:
        return ""
    if section:
        target = f"PHASE 3 SECTION {section}"
    elif int(phase) == 3:
        target = f"PHASE 3 TOTAL · SUM OF {report['sectionCount']} SECTIONS"
    else:
        target = f"PHASE {int(phase)} TOTAL"
    priced = report["apiTurnCount"] - report["apiUnpricedTurns"]
    amount = (f"${report['displayUsd']:.2f}" if priced
              else "UNAVAILABLE")
    if priced and report["apiUnpricedTurns"]:
        amount += "+"
    if report["apiUnpricedTurns"]:
        amount += (f" · PARTIAL: {report['apiUnpricedTurns']} AI TURN"
                   f"{'S' if report['apiUnpricedTurns'] != 1 else ''} LACKED TOKEN USAGE")
    return (f"AI API-EQUIVALENT COST COMPLETE [{float(at or time.time()):.3f}] "
            f"› {target} › {amount}")


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
