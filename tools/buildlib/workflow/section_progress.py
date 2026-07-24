"""Lightweight Phase-3 progress sidecar IO, safe from any worker cwd."""
import json
import os
import shlex
import time

from .. import BUILD_DIR, REPO


SECTION_PROGRESS_STATES = ("authoring", "repairing", "validating", "complete")


def section_progress_path(tid):
    return os.path.join(BUILD_DIR, f"{tid}.section-progress.json")


def write_section_progress(tid, sid, index, total, state, batch=0, batches=0):
    """Write the exact live position shared by the worker, harness, and Bindery UI."""
    if state not in SECTION_PROGRESS_STATES:
        raise ValueError(f"unknown section progress state: {state}")
    payload = {"section": str(sid), "index": int(index), "total": int(total),
               "state": state, "batch": int(batch), "batches": int(batches),
               "updatedAt": time.time()}
    path = section_progress_path(tid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"))
        handle.write("\n")
    return path


def clear_section_progress(tid):
    try:
        os.remove(section_progress_path(tid))
    except OSError:
        pass


def section_progress_shell_command(tid, sid, index, total, state, batch, batches):
    argv = ["python3", os.path.join(
        REPO, "tools", "workflow", "report_section_progress.py"),
            tid, sid, str(index), str(total), state,
            "--batch", str(batch), "--batches", str(batches)]
    return shlex.join(argv)
