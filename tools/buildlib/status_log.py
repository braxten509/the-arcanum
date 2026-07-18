"""Durable, bounded Forge status history for resumable tome builds."""
from __future__ import annotations

import json
import os
import re
import tempfile
import time

from . import BUILD_DIR


STATUS_LOG_LINES = 500
_BUILD_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_AI_COMPLETE_RE = re.compile(
    r"AI VALIDATOR CALL COMPLETE \[([0-9]+(?:\.[0-9]+)?)\] \(([^)]+)\) "
    r"› prerequisite completeness (s\d+).*?› [^\n]*?\b([^\s]+)$")


def status_path(build_dir, build_id):
    return os.path.join(build_dir, f"{build_id}.status-log.jsonl")


def _valid_build_id(build_id):
    value = str(build_id or "")
    return value if _BUILD_ID_RE.fullmatch(value) else ""


def _read_rows(path):
    rows = []
    try:
        with open(path, encoding="utf-8") as handle:
            for raw in handle:
                try:
                    row = json.loads(raw)
                    line = str(row.get("line") or "").strip()
                    if line:
                        rows.append((float(row.get("at") or 0), line))
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
    except OSError:
        pass
    return rows


def _write_rows(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".status-log-", suffix=".tmp",
                                     dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for at, line in rows[-STATUS_LOG_LINES:]:
                handle.write(json.dumps({"at": at, "line": line},
                                        ensure_ascii=False, separators=(",", ":")) + "\n")
        os.replace(temporary, path)
    finally:
        try:
            os.remove(temporary)
        except OSError:
            pass


def append_status_line(build_id, line, *, build_dir=BUILD_DIR, at=None):
    """Persist one exact harness lifecycle line and retain the newest 500."""
    build_id = _valid_build_id(build_id)
    line = str(line or "").strip()
    if not build_id or not line:
        return
    path = status_path(build_dir, build_id)
    rows = _read_rows(path)
    rows.append((float(time.time() if at is None else at), line[:4000]))
    _write_rows(path, rows)


def emit_status_line(line, build_id="", *, build_dir=BUILD_DIR):
    """Print a Forge lifecycle line and durably associate it with the active build."""
    append_status_line(build_id or os.environ.get("ARCANUM_BUILD_ID", ""), line,
                       build_dir=build_dir)
    print(line, flush=True)


def _legacy_ai_rows(build_dir, build_id, durable):
    """Recover validator completions recorded before the status sidecar existed."""
    exact = []
    for _at, line in durable:
        match = _AI_COMPLETE_RE.search(line)
        if match:
            exact.append((float(match.group(1)), match.group(2), match.group(3), match.group(4)))
    kind = "validator-ai"
    try:
        with open(os.path.join(build_dir, f"{build_id}.launch.json"),
                  encoding="utf-8") as handle:
            kind = str((json.load(handle).get("validator") or {}).get("kind") or kind)
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    recovered = []
    calls = os.path.join(build_dir, f"{build_id}.prerequisite-review.calls.jsonl")
    call_rows = []
    try:
        with open(calls, encoding="utf-8") as handle:
            for raw in handle:
                try:
                    row = json.loads(raw)
                    if isinstance(row, dict):
                        call_rows.append(row)
                except (ValueError, json.JSONDecodeError):
                    continue
        contracts = [int(row.get("contract") or 0) for row in call_rows
                     if str(row.get("contract") or "").isdigit()]
        current_contract = max(contracts, default=0)
        for row in call_rows:
            try:
                if current_contract and int(row.get("contract") or 0) != current_contract:
                    continue
                at = float(row.get("at") or 0)
                sid = str(row.get("section") or "")
                status = str(row.get("status") or "UNKNOWN")
                model = str(row.get("model") or "unknown-model")
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if not at or not re.fullmatch(r"s\d+", sid):
                continue
            duplicate = any(abs(at - seen_at) < 2 and status == seen_status
                            and sid == seen_sid and model == seen_model
                            for seen_at, seen_status, seen_sid, seen_model in exact)
            if duplicate:
                continue
            stage = str(row.get("stage") or "audit")
            stage_label = "" if stage == "audit" else f" {stage}"
            line = (f"AI VALIDATOR CALL COMPLETE [{at:.3f}] ({status}) › "
                    f"prerequisite completeness {sid}{stage_label} › {kind} {model}")
            recovered.append((at, line))
    except OSError:
        pass
    return recovered


def load_status_lines(build_id, *, build_dir=BUILD_DIR):
    """Load exact history plus honest completion records from pre-sidecar builds."""
    build_id = _valid_build_id(build_id)
    if not build_id:
        return []
    durable = _read_rows(status_path(build_dir, build_id))
    rows = [*durable, *_legacy_ai_rows(build_dir, build_id, durable)]
    rows.sort(key=lambda item: (item[0], item[1]))
    return [line for _at, line in rows[-STATUS_LOG_LINES:]]
