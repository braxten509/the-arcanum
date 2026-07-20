"""Durable, bounded Forge lifecycle history owned by the authoring adapter."""
from __future__ import annotations

import json
import os
import re
import tempfile
import time

from arcanum.config import BUILD_DIR

STATUS_LOG_LINES = 500
_FLOOR_KEY = "clearedAt"
_BUILD_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_AI_COMPLETE_RE = re.compile(
    r"AI VALIDATOR CALL COMPLETE \[([0-9]+(?:\.[0-9]+)?)\] \(([^)]+)\) "
    r"› ((?:prerequisite completeness|section quality) s\d+|"
    r"phase [12] (?:arc|map) quality)(?: (recovery-retry|escalation))? "
    r"› [^\s]+ ([^\s]+)(?: \(after [^)]+\))?$")
_VALIDATOR_RE = re.compile(
    r"^(?:VALIDATOR COMMAND|AI VALIDATOR CALL) (?:START|COMPLETE|FAILED)\b")
_GPT_COST_RE = re.compile(
    r"^GPT API-EQUIVALENT COST COMPLETE \[[0-9]+(?:\.[0-9]+)?\] "
    r"› PHASE ([1-8]) (?:(SECTION [A-Za-z0-9_-]+)|TOTAL)\b")


def _gpt_cost_scope(line: str) -> tuple[str, str] | None:
    match = _GPT_COST_RE.search(str(line or ""))
    return (match.group(1), match.group(2) or "TOTAL") if match else None


def status_path(build_dir: str, build_id: str) -> str:
    return os.path.join(build_dir, f"{build_id}.status-log.jsonl")


def _valid_build_id(build_id: str) -> str:
    value = str(build_id or "")
    return value if _BUILD_ID_RE.fullmatch(value) else ""


def _read_rows(path: str) -> list[tuple[float, str]]:
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


def _read_floor(path: str) -> float:
    """Timestamp of the last clear, below which recovered history is not replayed."""
    try:
        with open(path, encoding="utf-8") as handle:
            for raw in handle:
                try:
                    row = json.loads(raw)
                    if isinstance(row, dict) and _FLOOR_KEY in row:
                        return float(row[_FLOOR_KEY] or 0)
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
    except OSError:
        pass
    return 0.0


def _write_rows(path: str, rows: list[tuple[float, str]], floor: float = 0.0) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".status-log-", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            if floor:
                handle.write(json.dumps({_FLOOR_KEY: floor},
                                        separators=(",", ":")) + "\n")
            for at, line in rows[-STATUS_LOG_LINES:]:
                handle.write(json.dumps({"at": at, "line": line}, ensure_ascii=False,
                                        separators=(",", ":")) + "\n")
        os.replace(temporary, path)
    finally:
        try:
            os.remove(temporary)
        except OSError:
            pass


def append_status_line(build_id: str, line: str, *, build_dir: str = BUILD_DIR,
                       at: float | None = None) -> None:
    build_id, line = _valid_build_id(build_id), str(line or "").strip()
    if not build_id or not line:
        return
    path = status_path(build_dir, build_id)
    rows = _read_rows(path)
    scope = _gpt_cost_scope(line)
    if scope:
        # Resumes and phase rewinds update the lifetime total in place instead
        # of duplicating a stale completion amount in the Forge trace.
        rows = [(seen_at, seen_line) for seen_at, seen_line in rows
                if _gpt_cost_scope(seen_line) != scope]
    rows.append((float(time.time() if at is None else at), line[:4000]))
    _write_rows(path, rows, _read_floor(path))


def emit_status_line(line: str, build_id: str = "", *, build_dir: str = BUILD_DIR) -> None:
    append_status_line(build_id or os.environ.get("ARCANUM_BUILD_ID", ""), line,
                       build_dir=build_dir)
    print(line, flush=True)


def rewind_status_log(build_id: str, phase: int, *, build_dir: str = BUILD_DIR) -> int:
    """Return the durable status log to a restarted phase boundary.

    Two kinds of row live here and they rewind differently. Cost completions carry
    their own phase, so only the restarted range is dropped and earlier spend stays
    on the ledger. Validator traffic is a live account of what the author is doing
    right now — after a destructive rewind every one of those rows describes work
    that no longer exists, so the whole tool history goes.
    """
    build_id, phase = _valid_build_id(build_id), int(phase)
    if not build_id or phase not in range(1, 9):
        raise ValueError("valid build id and phase 1-8 are required")
    path = status_path(build_dir, build_id)
    rows = _read_rows(path)
    retained = [(at, line) for at, line in rows
                if not _VALIDATOR_RE.search(line)
                and not (_gpt_cost_scope(line)
                         and int(_gpt_cost_scope(line)[0]) >= phase)]
    _write_rows(path, retained, time.time())
    return len(rows) - len(retained)


def clear_run_history(build_id: str, *, build_dir: str = BUILD_DIR) -> int:
    """Empty the Forge history panes for a run that has ended.

    Every row here narrates the abandoned run: validator traffic describes a session
    nobody is in, and the cost rows are a display of spend, not the record of it. The
    record lives in the ai-cost ledger the running total reads, and is untouched.
    """
    build_id = _valid_build_id(build_id)
    if not build_id:
        return 0
    path = status_path(build_dir, build_id)
    if not any(os.path.exists(candidate) for candidate in (
            path, os.path.join(build_dir, f"{build_id}.prerequisite-review.calls.jsonl"))):
        return 0
    rows = _read_rows(path)
    # Always rewritten, even with nothing to drop, so the floor lands and the validator's
    # own journal cannot replay the cleared history.
    # ponytail: last-writer-wins against a dying worker's final append; the worst case is
    # one resurrected row, not a corrupt file.
    _write_rows(path, [], time.time())
    return len(rows)


def _legacy_ai_rows(build_dir: str, build_id: str,
                    durable: list[tuple[float, str]],
                    floor: float = 0.0) -> list[tuple[float, str]]:
    exact = []
    for _at, line in durable:
        match = _AI_COMPLETE_RE.search(line)
        if match:
            label = match.group(3) + (f" {match.group(4)}" if match.group(4) else "")
            exact.append((float(match.group(1)), match.group(2), label,
                          match.group(5)))
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
        current_contracts = {}
        for row in call_rows:
            audit_kind = str(row.get("auditKind") or "section")
            try:
                current_contracts[audit_kind] = max(
                    current_contracts.get(audit_kind, 0), int(row.get("contract") or 0))
            except (TypeError, ValueError):
                continue
        for row in call_rows:
            try:
                audit_kind = str(row.get("auditKind") or "section")
                current_contract = current_contracts.get(audit_kind, 0)
                if current_contract and int(row.get("contract") or 0) != current_contract:
                    continue
                at = float(row.get("at") or 0)
                section = str(row.get("section") or "")
                phase = int(row.get("phase") or 0)
                status = str(row.get("status") or "UNKNOWN")
                model = str(row.get("model") or "unknown-model")
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if audit_kind == "planning" and phase in (1, 2):
                audit_label = f"phase {phase} {'arc' if phase == 1 else 'map'} quality"
            elif re.fullmatch(r"s\d+", section):
                audit_label = (("section quality" if int(row.get("contract") or 0) >= 6
                                else "prerequisite completeness") + f" {section}")
            else:
                continue
            if not at or at <= floor:
                continue
            stage = str(row.get("stage") or "audit")
            stage_label = "" if stage == "audit" else f" {stage}"
            call_label = audit_label + stage_label
            if any(abs(at - seen_at) < 2 and status == seen_status
                   and seen_label in (audit_label, call_label) and model == seen_model
                   for seen_at, seen_status, seen_label, seen_model in exact):
                continue
            recovered.append((at, f"AI VALIDATOR CALL COMPLETE [{at:.3f}] ({status}) "
                                  f"› {call_label} "
                                  f"› {kind} {model}"))
    except OSError:
        pass
    return recovered


def load_status_lines(build_id: str, *, build_dir: str = BUILD_DIR) -> list[str]:
    build_id = _valid_build_id(build_id)
    if not build_id:
        return []
    path = status_path(build_dir, build_id)
    durable = _read_rows(path)
    # The validator's own call journal is never truncated, so a clear has to say how
    # far back its replay may reach or the cleared history walks straight back in.
    rows = [*durable, *_legacy_ai_rows(build_dir, build_id, durable, _read_floor(path))]
    rows.sort(key=lambda item: (item[0], item[1]))
    return [line for _at, line in rows[-STATUS_LOG_LINES:]]
