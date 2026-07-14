"""Durable cross-server ownership and terminal state for tome builds."""
import json
import os
import re
import time

from .config import BUILD_DIR
from .tomes import load_manifest

BUILD_TOTAL_PHASES = 9
BUILD_PHASE_TITLES = ("Gate", "Concept & arc", "Skeleton & voice", "Sections",
                      "Minigames", "Economy", "Cosmetics", "Validate", "Student review")


def _tome_name(tid):
    try:
        return (load_manifest(tid).get("meta") or {}).get("name") or tid
    except Exception:
        return tid


def _path(slug, suffix):
    return os.path.join(BUILD_DIR, f"{slug}.{suffix}.json")


def save_active_owner(slug, job_id, pid):
    """Persist the owning job id so another server can attach to its trace."""
    try:
        with open(_path(slug, "active"), "w", encoding="utf-8") as f:
            json.dump({"jobId": job_id, "pid": int(pid)}, f)
    except (OSError, TypeError, ValueError):
        pass


def remove_active_owner(slug):
    try:
        os.remove(_path(slug, "active"))
    except OSError:
        pass


def load_active_owner(slug, pid):
    try:
        with open(_path(slug, "active"), encoding="utf-8") as f:
            owner = json.load(f)
        job_id = owner.get("jobId", "")
        if int(owner.get("pid")) == int(pid) and re.fullmatch(r"[A-Za-z0-9_-]+", job_id):
            return job_id
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        pass
    return None


def load_runner_request(slug):
    """Return a live runner/gate approval request written by the harness."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", str(slug or "")):
        return None
    try:
        with open(_path(slug, "runner-request"), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def load_section_progress(tid):
    """Return the exact section/state reported by a live warm Phase-3 worker."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", str(tid or "")):
        return None
    try:
        with open(_path(tid, "section-progress"), encoding="utf-8") as f:
            data = json.load(f)
        section = str(data.get("section") or "")
        index, total = int(data.get("index") or 0), int(data.get("total") or 0)
        state = str(data.get("state") or "")
        if (not re.fullmatch(r"s\d+", section) or index < 1 or total < index
                or state not in ("authoring", "repairing", "validating", "complete")):
            return None
        return {"section": section, "index": index, "total": total, "state": state,
                "batch": int(data.get("batch") or 0),
                "batches": int(data.get("batches") or 0),
                "updatedAt": float(data.get("updatedAt") or 0)}
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def record_build_result(slug, tid, status, phase=0, phase_title="", error=""):
    phase = max(0, min(8, int(phase or 0)))
    data = {"status": status, "kind": "build", "id": slug, "slug": slug,
            "tome": tid, "name": _tome_name(tid), "phase": phase,
            "phaseTitle": phase_title or BUILD_PHASE_TITLES[phase],
            "totalPhases": BUILD_TOTAL_PHASES, "finishedAt": time.time()}
    if error:
        data["error"] = str(error)[-12000:]
    try:
        with open(_path(slug, "result"), "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass
    return data


def build_result_status(slug):
    try:
        with open(_path(slug, "result"), encoding="utf-8") as f:
            data = json.load(f)
        return data if data.get("status") in ("done", "error", "cancelled") else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def record_cancelled_build(slug, tid, phase):
    phase = max(0, min(8, int(phase or 0)))
    data = {"status": "cancelled", "kind": "build", "id": slug, "slug": slug,
            "tome": tid, "name": _tome_name(tid), "phase": phase,
            "phaseTitle": BUILD_PHASE_TITLES[phase], "totalPhases": BUILD_TOTAL_PHASES,
            "cancelledAt": time.time()}
    try:
        with open(_path(slug, "cancelled"), "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass
    record_build_result(slug, tid, "cancelled", phase, data["phaseTitle"])
    return data


def cancelled_build_status(slug):
    try:
        with open(_path(slug, "cancelled"), encoding="utf-8") as f:
            data = json.load(f)
        return data if data.get("status") == "cancelled" else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None
