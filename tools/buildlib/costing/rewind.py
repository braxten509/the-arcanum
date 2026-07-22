"""Section-scoped mutations of the durable AI cost ledger."""
from __future__ import annotations

import fcntl
import time


def rewind_sections(build_dir, build_id, sections):
    """Discard visible Phase-3 accounting for restarted section units."""
    # Imported lazily because ai_costs publicly wires this focused mutation helper.
    from .. import ai_costs as ledger

    sections = {str(section) for section in sections}
    lock = open(ledger._lock_path(build_dir, build_id), "a+", encoding="utf-8")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        prior = ledger._read_json(ledger._state_path(build_dir, build_id), {})
        all_rows = ledger._read_jsonl(ledger.turns_path(build_dir, build_id))
        retained = [row for row in all_rows
                    if not (int(row.get("phase") or 0) == 3
                            and str(row.get("section") or "") in sections)]
        state = {
            "version": 1,
            # The counters are invisible provider baselines, not restart evidence.
            "lastCounters": dict(prior.get("lastCounters") or {}),
            "phases": dict(prior.get("phases") or {}),
            "sections": {key: value for key, value in
                         (prior.get("sections") or {}).items()
                         if str(key) not in sections},
        }
        ledger._atomic_jsonl(ledger.turns_path(build_dir, build_id), retained)
        ledger._write_totals(build_dir, build_id, state)
        state["updatedAt"] = time.time()
        ledger._atomic_json(ledger._state_path(build_dir, build_id), state)
        return len(all_rows) - len(retained)
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()
