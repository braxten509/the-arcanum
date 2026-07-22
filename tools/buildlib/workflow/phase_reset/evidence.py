"""Erase durable evidence owned by a restarted phase or section."""
from __future__ import annotations

import json
import os
import re
import tempfile


RESTART_EVIDENCE_SIDECARS = (
    "phase-ai-reviews",
    "prerequisite-reviews",
    "prerequisite-review.calls.jsonl",
    "author-usage.jsonl",
    "conversation.jsonl.bak",
    "reset-stash",
)

_PHASE_FILE_RE = re.compile(r"^phase-([1-8])\.json$")
_SECTION_FILE_RE = re.compile(r"^(s[0-9]{2,3})\.json$")
_ARCHIVE_UNIT_RE = re.compile(r"__(phase-[1-8]|s[0-9]{2,3})__")


def _remove(path):
    if os.path.isdir(path) and not os.path.islink(path):
        import shutil
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def _atomic_jsonl(path, rows):
    if not rows:
        _remove(path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".restart-evidence-", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False,
                                        separators=(",", ":")) + "\n")
        os.replace(temporary, path)
    finally:
        try:
            os.remove(temporary)
        except OSError:
            pass


def _filter_jsonl(path, keep):
    rows, before = [], 0
    try:
        with open(path, encoding="utf-8") as handle:
            for raw in handle:
                before += 1
                try:
                    row = json.loads(raw)
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if isinstance(row, dict) and keep(row):
                    rows.append(row)
    except OSError:
        return 0
    _atomic_jsonl(path, rows)
    return before - len(rows)


def _remove_matching_files(folder, discard):
    removed = 0
    try:
        names = os.listdir(folder)
    except OSError:
        return 0
    for name in names:
        path = os.path.join(folder, name)
        if os.path.isfile(path) and discard(name):
            _remove(path)
            removed += 1
    try:
        if not os.listdir(folder):
            os.rmdir(folder)
    except OSError:
        pass
    return removed


def rewind_phase_evidence(build_dir, archive_root, build_id, phase):
    """Remove review/history artifacts produced by ``phase`` or anything later."""
    phase = int(phase)
    removed = 0
    calls = os.path.join(build_dir, f"{build_id}.prerequisite-review.calls.jsonl")

    def keep_call(row):
        try:
            return int(row.get("phase") or 0) < phase
        except (TypeError, ValueError):
            return False

    removed += _filter_jsonl(calls, keep_call)
    reviews = os.path.join(build_dir, f"{build_id}.phase-ai-reviews")
    removed += _remove_matching_files(
        reviews, lambda name: bool((match := _PHASE_FILE_RE.fullmatch(name))
                                   and int(match.group(1)) >= phase))
    if phase <= 3:
        path = os.path.join(build_dir, f"{build_id}.prerequisite-reviews")
        if os.path.exists(path):
            _remove(path)
            removed += 1

    archive = os.path.join(archive_root, build_id)

    def discard_archive(name):
        match = _ARCHIVE_UNIT_RE.search(name)
        if not match:
            return False
        unit = match.group(1)
        if unit.startswith("phase-"):
            return int(unit.split("-", 1)[1]) >= phase
        return phase <= 3

    removed += _remove_matching_files(archive, discard_archive)
    for suffix in ("author-usage.jsonl", "conversation.jsonl.bak"):
        path = os.path.join(build_dir, f"{build_id}.{suffix}")
        if os.path.exists(path):
            _remove(path)
            removed += 1
    stash = os.path.join(build_dir, f"{build_id}.reset-stash")
    if os.path.exists(stash):
        _remove(stash)
        removed += 1
    return removed


def rewind_section_evidence(build_dir, archive_root, build_id, sections):
    """Remove review/history artifacts for the restarted Phase-3 section range."""
    sections = {str(section) for section in sections}
    removed = 0
    calls = os.path.join(build_dir, f"{build_id}.prerequisite-review.calls.jsonl")
    def keep_call(row):
        try:
            phase = int(row.get("phase") or 0)
        except (TypeError, ValueError):
            return False
        unit = str(row.get("section") or row.get("unit") or "")
        return not (phase == 3 and unit in sections)

    removed += _filter_jsonl(calls, keep_call)
    reviews = os.path.join(build_dir, f"{build_id}.prerequisite-reviews")
    removed += _remove_matching_files(
        reviews, lambda name: bool((match := _SECTION_FILE_RE.fullmatch(name))
                                   and match.group(1) in sections))
    archive = os.path.join(archive_root, build_id)
    removed += _remove_matching_files(
        archive, lambda name: bool((match := _ARCHIVE_UNIT_RE.search(name))
                                   and match.group(1) in sections))
    for suffix in ("author-usage.jsonl", "conversation.jsonl.bak"):
        path = os.path.join(build_dir, f"{build_id}.{suffix}")
        if os.path.exists(path):
            _remove(path)
            removed += 1
    return removed
