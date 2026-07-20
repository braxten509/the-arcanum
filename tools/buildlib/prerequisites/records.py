"""Durable call accounting and one-file-per-validator-failure archives."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone

from ..ai_costs import record_ai_turn


RAW_LIMIT = 50_000


def calls_path(build_dir, build_id):
    return os.path.join(build_dir, f"{build_id}.prerequisite-review.calls.jsonl")


def failure_dir(archive_root, build_id):
    return os.path.join(archive_root, _slug(build_id, "unknown-build"))


def _slug(value, fallback):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "")).strip(".-_")
    return (cleaned or fallback)[:96]


def _clock():
    now_ns = time.time_ns()
    seconds, nanos = divmod(now_ns, 1_000_000_000)
    moment = datetime.fromtimestamp(seconds, timezone.utc)
    iso = moment.strftime("%Y-%m-%dT%H:%M:%S") + f".{nanos:09d}Z"
    filename = moment.strftime("%Y-%m-%dT%H-%M-%S") + f".{nanos:09d}Z"
    return now_ns / 1_000_000_000, iso, filename


def _signature(status, reasons, missing, quality=()):
    normalized = {
        "status": str(status or ""),
        "reasons": [" ".join(str(reason).lower().split()) for reason in reasons or []],
        "missingMechanisms": [
            {key: item.get(key) for key in ("id", "owner", "demands", "closestExisting")}
            for item in missing or [] if isinstance(item, dict)
        ],
        "qualityFindings": [
            {key: item.get(key) for key in (
                "path", "node", "category", "criterion", "evidenceLines")}
            for item in quality or [] if isinstance(item, dict)
        ],
    }
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_failure(archive_root, build_id, sid, label, payload):
    timestamp_unix, timestamp, filename_stamp = _clock()
    payload = {"version": 1, "recordedAt": timestamp,
               "recordedAtUnix": timestamp_unix, **payload}
    folder = failure_dir(archive_root, build_id)
    os.makedirs(folder, exist_ok=True)
    stem = "__".join((_slug(filename_stamp, "time"), _slug(sid, "unknown-section"),
                      _slug(label, "validator-failure")))
    path = os.path.join(folder, stem + ".json")
    counter = 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{stem}__{counter}.json")
        counter += 1
    fd, temp = tempfile.mkstemp(prefix=".validator-failure-", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp, path)
    finally:
        try:
            os.remove(temp)
        except OSError:
            pass
    return path


def _write_planning_failure(archive_root, build_id, sid, label, *, phase, stage,
                            status, model, transport, escalated_from, report,
                            report_truncated=False):
    """Archive a Phase-1/2 review as the human-readable Markdown the model wrote."""
    _timestamp_unix, timestamp, filename_stamp = _clock()
    folder = failure_dir(archive_root, build_id)
    os.makedirs(folder, exist_ok=True)
    stem = "__".join((_slug(filename_stamp, "time"), _slug(sid, "unknown-phase"),
                      _slug(label, "validator-failure")))
    path = os.path.join(folder, stem + ".md")
    counter = 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{stem}__{counter}.md")
        counter += 1
    metadata = [
        "# Planning Validator Review",
        "",
        f"- Recorded: `{timestamp}`",
        f"- Build: `{build_id}`",
        f"- Phase: `{int(phase)}`",
        f"- Stage: `{stage}`",
        f"- Status: `{status}`",
        f"- Model: `{model or 'unknown'}`",
        f"- Transport: `{transport or 'unknown'}`",
    ]
    if escalated_from:
        metadata.append(f"- Escalated from: `{escalated_from}`")
    metadata.extend(("", "## Validator report", "", str(report or "").strip()
                     or "No readable validator report was returned."))
    if report_truncated:
        metadata.extend(("", "_The archived report was truncated at the safety limit._"))
    fd, temporary = tempfile.mkstemp(
        prefix=".validator-failure-", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(metadata).rstrip() + "\n")
        os.replace(temporary, path)
    finally:
        try:
            os.remove(temporary)
        except OSError:
            pass
    return path


def _raw_text(raw):
    if raw is None:
        return "", False
    text = raw if isinstance(raw, str) else json.dumps(
        raw, ensure_ascii=False, sort_keys=True, default=str)
    return (text[:RAW_LIMIT], len(text) > RAW_LIMIT)


def append_ai_call(build_dir, archive_root, build_id, sid, packet, result, meta, *,
                   raw=None, stage="audit", escalated_from="", malformed=False,
                   contract=0, phase=3, unit_kind="section", audit_kind="section"):
    """Append compact accounting and archive every non-PASS AI call separately."""
    phase = int(phase)
    row = {"at": time.time(), "contract": contract, "phase": phase,
           "unitKind": unit_kind, "unit": sid, "auditKind": audit_kind,
           "packetChars": len(packet), "stage": stage, "status": result["status"],
           "transport": meta.get("transport", "test-adapter"),
           "model": meta.get("model", ""), "usage": meta.get("usage")}
    if unit_kind == "section":
        row["section"] = sid
    if meta.get("responseId"):
        row["responseId"] = meta["responseId"]
    if escalated_from:
        row["escalatedFrom"] = escalated_from
    if malformed:
        row["malformed"] = True
    with open(calls_path(build_dir, build_id), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    record_ai_turn(
        build_dir, build_id, phase=phase,
        section=sid if unit_kind == "section" else None,
        role="validator", stage=stage,
        kind=meta.get("kind") or meta.get("transport") or "validator-ai",
        model=meta.get("model", ""), effort=meta.get("effort", ""),
        transport=meta.get("transport", "test-adapter"), status=result["status"],
        session_id=meta.get("sessionId", ""), usage=meta.get("usage"),
        usage_mode="turn", response_id=meta.get("responseId", ""))
    if result["status"] == "PASS":
        return None
    raw_text, raw_truncated = _raw_text(raw)
    reasons = list(result.get("reasons") or [])
    missing = list(result.get("missingMechanisms") or [])
    quality = list(result.get("qualityFindings") or [])
    phase_findings = list(result.get("findings") or [])
    if audit_kind == "planning":
        report = raw_text or str(result.get("report") or "").strip()
        if not report:
            report = "\n\n".join(str(reason) for reason in reasons)
        return _write_planning_failure(
            archive_root, build_id, sid,
            f"ai-{stage}-{meta.get('model') or 'unknown'}-{result['status']}",
            phase=phase, stage=stage, status=result["status"],
            model=meta.get("model", ""),
            transport=meta.get("transport", "test-adapter"),
            escalated_from=escalated_from, report=report,
            report_truncated=raw_truncated)
    return _write_failure(archive_root, build_id, sid,
                          f"ai-{stage}-{meta.get('model') or 'unknown'}-{result['status']}", {
        "kind": "validator-ai", "buildId": build_id, "phase": phase,
        "unitKind": unit_kind, "unit": sid, "auditKind": audit_kind,
        **({"section": sid} if unit_kind == "section" else {}), "stage": stage,
        "status": result["status"], "model": meta.get("model", ""),
        "transport": meta.get("transport", "test-adapter"),
        "escalatedFrom": escalated_from, "malformed": bool(malformed),
        "reasons": reasons, "citations": list(result.get("citations") or []),
        "missingMechanisms": missing,
        "nodeReviews": list(result.get("nodeReviews") or []),
        "qualityFindings": quality,
        "guidance": list(result.get("guidance") or []),
        "checks": list(result.get("checks") or []),
        "findings": phase_findings,
        "blockerSignature": _signature(
            result["status"], reasons, missing, [*quality, *phase_findings]),
        "rawResponse": raw_text, "rawResponseTruncated": raw_truncated,
        **({"responseId": meta["responseId"]} if meta.get("responseId") else {}),
    })


def append_ai_infrastructure_failure(build_dir, archive_root, build_id, sid, packet,
                                     validator, error, *, stage="audit", contract=0,
                                     escalated_from="", phase=3, unit_kind="section",
                                     audit_kind="section"):
    """Record a provider/transport failure even though no verdict could be parsed."""
    model = str(validator.get("model") or "")
    reason = str(error or "validator infrastructure failed")
    phase = int(phase)
    row = {"at": time.time(), "contract": contract, "phase": phase,
           "unitKind": unit_kind, "unit": sid, "auditKind": audit_kind,
           "packetChars": len(packet), "stage": stage, "status": "ERROR",
           "transport": str(validator.get("kind") or "unknown"), "model": model,
           "usage": None, "infrastructure": True}
    if unit_kind == "section":
        row["section"] = sid
    if escalated_from:
        row["escalatedFrom"] = escalated_from
    with open(calls_path(build_dir, build_id), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    record_ai_turn(
        build_dir, build_id, phase=phase,
        section=sid if unit_kind == "section" else None,
        role="validator", stage=stage,
        kind=str(validator.get("kind") or "validator-ai"), model=model,
        effort=str(validator.get("effort") or ""), transport="cli",
        status="infrastructure-error", usage=None, usage_mode="turn")
    if audit_kind == "planning":
        return _write_planning_failure(
            archive_root, build_id, sid,
            f"ai-{stage}-{model or 'unknown'}-error",
            phase=phase, stage=stage, status="ERROR", model=model,
            transport=str(validator.get("kind") or "unknown"),
            escalated_from=escalated_from, report=reason)
    return _write_failure(archive_root, build_id, sid,
                          f"ai-{stage}-{model or 'unknown'}-error", {
        "kind": "validator-ai", "buildId": build_id, "phase": phase,
        "unitKind": unit_kind, "unit": sid, "auditKind": audit_kind,
        **({"section": sid} if unit_kind == "section" else {}), "stage": stage,
        "status": "ERROR", "model": model,
        "transport": str(validator.get("kind") or "unknown"),
        "escalatedFrom": escalated_from, "malformed": False,
        "reasons": [reason], "citations": [], "missingMechanisms": [],
        "nodeReviews": [], "qualityFindings": [],
        "blockerSignature": _signature("ERROR", [reason], []),
        "rawResponse": "", "rawResponseTruncated": False,
    })


def archive_section_failure(archive_root, build_id, sid, report, *, map_digest="",
                            section_sha256=""):
    """Keep every final deterministic/AI section-gate failure instead of overwriting history."""
    full_reason = str(report or "deterministic validation failed")
    reason = full_reason[-RAW_LIMIT:]
    return _write_failure(archive_root, build_id, sid, "section-gate-fail", {
        "kind": "section-gate", "buildId": build_id, "section": sid,
        "stage": "section-gate", "status": "FAIL", "reasons": [reason],
        "mapDigest": map_digest, "sectionSha256": section_sha256,
        "reportTruncated": len(full_reason) > RAW_LIMIT,
        "blockerSignature": _signature("FAIL", [reason], []),
    })


def review_call_count(build_dir, build_id):
    try:
        with open(calls_path(build_dir, build_id), encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())
    except OSError:
        return 0


def review_usage_summary(build_dir, build_id):
    keys = ("inputTokens", "freshInputTokens", "cachedInputTokens", "cacheWriteTokens",
            "outputTokens", "reasoningTokens", "totalTokens")
    totals, api_calls = {key: 0 for key in keys}, 0
    try:
        with open(calls_path(build_dir, build_id), encoding="utf-8") as handle:
            for line in handle:
                usage = json.loads(line).get("usage")
                if not isinstance(usage, dict):
                    continue
                api_calls += 1
                for key in totals:
                    totals[key] += int(usage.get(key) or 0)
    except (OSError, ValueError, TypeError):
        pass
    return {"apiCalls": api_calls, **totals}
