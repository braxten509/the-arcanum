"""Rebuildable harness truth for course-map nodes and obligation lifecycle."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import tomllib

from .. import BUILD_DIR, REPO
from .alignment import actual_lesson_id
from ..course_map import load_course_map
from ..continuity import (SUPPORTED_HANDOFF_VERSIONS, handoff_digest,
                         handoff_discoveries, handoff_path, read_handoff,
                         validate_handoff)
from arcanum.tomes import resolve_working_tid


STATE_VERSION = 1
STATUS_MARKS = {"planned": "○", "authored": "◐", "current": "▶", "verified": "✓",
                "blocked": "!"}
STATUS_LABELS = {key: key.replace("-", " ") for key in STATUS_MARKS}


def _path(build_id, suffix):
    return os.path.join(BUILD_DIR, f"{build_id}.{suffix}")


def state_path(build_id):
    return _path(build_id, "course-state.json")


def evidence_dir(build_id):
    return _path(build_id, "course-evidence")


def failure_dir(build_id):
    return _path(build_id, "course-failures")


def receipt_path(build_id, sid):
    return os.path.join(evidence_dir(build_id), f"{sid}.json")


def failure_path(build_id, sid):
    return os.path.join(failure_dir(build_id), f"{sid}.json")


def _atomic_json(path, value):
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp",
                                dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp, path)
    finally:
        try:
            os.remove(temp)
        except OSError:
            pass


def _read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
        return value
    except (OSError, ValueError, json.JSONDecodeError):
        return default


def _sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def tree_digest(path):
    """Stable digest of file names and bytes; mtimes never create checkmarks."""
    if not os.path.exists(path):
        return ""
    digest = hashlib.sha256()
    if os.path.isfile(path):
        with open(path, "rb") as handle:
            digest.update(handle.read())
        return digest.hexdigest()
    for root, dirs, files in os.walk(path):
        dirs[:] = sorted(name for name in dirs if name not in ("save", "__pycache__"))
        for name in sorted(files):
            full = os.path.join(root, name)
            relative = os.path.relpath(full, path).replace(os.sep, "/")
            digest.update(relative.encode("utf-8") + b"\0")
            try:
                with open(full, "rb") as handle:
                    digest.update(handle.read())
            except OSError:
                digest.update(b"<unreadable>")
            digest.update(b"\0")
    return digest.hexdigest()


def _context(build_id):
    plan = _path(build_id, "plan.md")
    try:
        with open(plan, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        text = ""
    return resolve_working_tid(build_id, text), plan


def _section_path(tid, sid):
    deep = os.path.join(REPO, "tomes", tid, "sections", sid)
    return deep if os.path.isdir(deep) else deep + ".toml"


def section_digest(tid, sid):
    return tree_digest(_section_path(tid, sid))


def shared_course_digest(tid):
    """Hash manifest/runtime evidence shared by every cumulative section gate."""
    manifest_path = os.path.join(REPO, "tomes", tid, "tome.toml")
    paths = [manifest_path]
    try:
        with open(manifest_path, "rb") as handle:
            manifest = tomllib.load(handle)
        runtime = str((manifest.get("runtime") or {}).get("name") or "").strip()
        if runtime:
            paths.append(os.path.join(REPO, "global-configs", "runtimes", runtime + ".toml"))
    except (OSError, tomllib.TOMLDecodeError, AttributeError):
        pass
    value = hashlib.sha256()
    for path in paths:
        value.update(os.path.relpath(path, REPO).encode("utf-8") + b"\0")
        value.update(tree_digest(path).encode("ascii") + b"\0")
    return value.hexdigest()


def _section_authored(section, tid):
    try:
        import tome_layout
        actual = tome_layout.load_section(os.path.join(REPO, "tomes", tid), section["id"])
    except Exception:
        return False
    planned = [node for node in section["nodes"] if node["kind"] == "lesson"]
    lessons = actual.get("lessons") or []
    if [str(item.get("id") or "") for item in lessons if isinstance(item, dict)] != [
            actual_lesson_id(node["id"]) for node in planned]:
        return False
    if any(list(item.get("teaches") or []) != list(node["teaches"])
           for item, node in zip(lessons, planned) if isinstance(item, dict)):
        return False
    working = next(node for node in section["nodes"] if node["kind"] == "working")
    freestyle = actual.get("freestyle") or {}
    if not isinstance(freestyle, dict) or list(freestyle.get("requires") or []) != list(working["requires"]):
        return False
    path = _section_path(tid, section["id"])
    for root, _dirs, files in os.walk(path) if os.path.isdir(path) else [(os.path.dirname(path), [], [os.path.basename(path)])]:
        for name in files:
            if not name.endswith(".toml"):
                continue
            try:
                text = open(os.path.join(root, name), encoding="utf-8").read()
            except OSError:
                return False
            if any(marker in text for marker in ("TODO", "FIXME", "replace-me")):
                return False
    return True


def required_checks(section):
    checks = set((section.get("doneWhen") or {}).get("checks") or [])
    for node in section.get("nodes") or []:
        checks.update((node.get("doneWhen") or {}).get("checks") or [])
    return sorted(checks)


def _progress(build_id, tid):
    for key in (build_id, tid):
        value = _read_json(_path(key, "section-progress.json"), {}) or {}
        if value.get("section"):
            return value
    return {}


def _receipt_valid(build_id, tid, section, course):
    sid = section["id"]
    receipt = _read_json(receipt_path(build_id, sid), {}) or {}
    reasons = []
    if receipt.get("version") != 1:
        reasons.append("verification receipt is missing")
    if receipt.get("mapDigest") != course["digest"]:
        reasons.append("map digest changed")
    if receipt.get("sectionSha256") != section_digest(tid, sid):
        reasons.append("owned section evidence changed")
    if receipt.get("sharedCourseSha256") != shared_course_digest(tid):
        reasons.append("shared tome or runtime evidence changed")
    if receipt.get("handoffSha256") != handoff_digest(tid, sid):
        reasons.append("sealed handoff changed")
    checks = {item.get("id"): item.get("status") for item in receipt.get("checks", [])
              if isinstance(item, dict)}
    missing = [check for check in required_checks(section) if checks.get(check) != "passed"]
    if missing:
        reasons.append("required deterministic checks are absent: " + ", ".join(missing))
    return not reasons, reasons, receipt


def _failure_current(build_id, tid, sid, course):
    failure = _read_json(failure_path(build_id, sid), {}) or {}
    return bool(failure and failure.get("mapDigest") == course["digest"]
                and failure.get("sectionSha256") == section_digest(tid, sid)), failure


def _closure(obligation, fulfillment, receipt, valid):
    return {"id": obligation["id"], "origin": obligation["origin"],
            "target": obligation["target"], "kind": obligation["kind"],
            "requirement": obligation["requirement"],
            "status": "closed",
            "fulfillment": fulfillment, "targetEvidence": receipt.get("reportSha256", "")}


def derive_course_state(build_id, write=True):
    """Recompute truth from the sealed map, authored files, handoffs, and receipts."""
    os.makedirs(evidence_dir(build_id), exist_ok=True)
    os.makedirs(failure_dir(build_id), exist_ok=True)
    course = load_course_map(build_id)
    tid, plan = _context(build_id)
    ids = [section["id"] for section in course["sections"]]
    progress = _progress(build_id, tid)
    current_sid = progress.get("section") if progress.get("section") in ids else ""
    from ..prerequisites.review import review_call_count, review_usage_summary
    validator_calls = review_call_count(build_id)
    validator_usage = review_usage_summary(build_id)
    validity, receipts, failures, sections_out = {}, {}, {}, []
    chain_clean = True
    for section in course["sections"]:
        sid = section["id"]
        own_valid, stale, receipt = _receipt_valid(build_id, tid, section, course)
        failure_current, failure = _failure_current(build_id, tid, sid, course)
        verified = chain_clean and own_valid
        validity[sid], receipts[sid], failures[sid] = verified, receipt, failure
        authored = _section_authored(section, tid)
        if verified:
            status = "verified"
        elif failure_current or (receipt and stale) or (not chain_clean and receipt):
            status = "blocked"
        elif sid == current_sid:
            status = "current"
        else:
            status = "authored" if authored else "planned"
        nodes = [{"id": node["id"], "kind": node["kind"], "title": node["title"],
                  "status": status, "mark": STATUS_MARKS[status],
                  "statusLabel": STATUS_LABELS[status]}
                 for node in section["nodes"]]
        blockers = list(stale if receipt else [])
        if failure_current:
            blockers.append(str(failure.get("report") or "deterministic validation failed")[-2000:])
        if not chain_clean and receipt:
            blockers.append("an earlier section lost valid evidence")
        sections_out.append({"id": sid, "ordinal": section["ordinal"],
                             "title": section["title"],
                             "milestone": section["projectMilestone"], "status": status,
                             "mark": STATUS_MARKS[status], "statusLabel": STATUS_LABELS[status],
                             "nodes": nodes, "blockers": blockers})
        chain_clean = verified
    obligations = {item["id"]: item for item in course.get("plannedObligations", [])}
    for section in course["sections"]:
        sid = section["id"]
        if not validity.get(sid):
            continue
        handoff = read_handoff(tid, sid) or {}
        if handoff.get("version") not in SUPPORTED_HANDOFF_VERSIONS:
            continue
        for item in handoff_discoveries(handoff, course):
            obligations[item["id"]] = item
    active, archive = [], []
    superseded_by = {item.get("supersedes"): item for item in obligations.values()
                     if isinstance(item, dict) and item.get("supersedes")}
    order = {sid: index for index, sid in enumerate(ids)}
    effective_current = current_sid or next(
        (row["id"] for row in sections_out if row["status"] != "verified"),
        ids[-1])
    current_index = order.get(effective_current, len(ids) - 1)
    for oid, obligation in sorted(obligations.items()):
        if oid in superseded_by:
            replacement = superseded_by[oid]
            archive.append({"id": oid, "origin": obligation["origin"],
                            "target": obligation["target"], "kind": obligation["kind"],
                            "requirement": obligation["requirement"], "status": "superseded",
                            "supersededBy": replacement["id"],
                            "revisionReason": replacement["revisionReason"]})
            continue
        target = obligation.get("target")
        target_handoff = read_handoff(tid, target) or {}
        fulfillment = next((item for item in target_handoff.get("fulfillments", [])
                            if isinstance(item, dict) and item.get("id") == oid), None)
        valid = bool(validity.get(target) and fulfillment)
        if fulfillment and valid:
            archive.append(_closure(obligation, fulfillment, receipts.get(target, {}), valid))
        if not valid:
            row = dict(obligation)
            row["dueNow"] = target == effective_current
            row["overdue"] = target in order and order[target] < current_index
            active.append(row)
    due = [item for item in active if item["dueNow"] or item["overdue"]]
    blockers = []
    for item in due:
        blockers.append(f"{item['id']} is {'overdue' if item['overdue'] else 'due now'}")
    for section in sections_out:
        blockers.extend(f"{section['id']}: {item}" for item in section["blockers"])
    source = {"map": course["digest"], "sections": [(row["id"], row["status"],
               section_digest(tid, row["id"]), handoff_digest(tid, row["id"]))
               for row in sections_out], "active": active, "archive": archive,
              "shared": shared_course_digest(tid)}
    state = {"version": STATE_VERSION, "buildId": build_id, "tomeId": tid,
             "mapDigest": course["digest"],
             "sourceDigest": _sha_bytes(json.dumps(source, sort_keys=True,
                                                    separators=(",", ":")).encode("utf-8")),
             "currentSection": effective_current, "sections": sections_out,
             "activeObligations": active, "closedArchive": archive,
             "blockers": blockers,
             "validatorAi": {"callCount": validator_calls, **validator_usage}}
    if write:
        _atomic_json(state_path(build_id), state)
    return state


def record_section_verification(build_id, sid, report):
    course = load_course_map(build_id)
    tid, plan = _context(build_id)
    section = next((item for item in course["sections"] if item["id"] == sid), None)
    if not section:
        raise ValueError(f"unknown course-map section {sid!r}")
    ids = [item["id"] for item in course["sections"]]
    clean, handoff_report = validate_handoff(tid, sid, ids, plan)
    if not clean:
        raise ValueError("cannot record a checkmark from an invalid handoff: " + handoff_report)
    from .alignment import validate_tome_alignment
    aligned, alignment_report = validate_tome_alignment(build_id, os.path.join(REPO, "tomes", tid), sid)
    if not aligned:
        raise ValueError("cannot record a checkmark from map drift: " + alignment_report)
    report_text = str(report or "")
    report_hash = _sha_bytes(report_text.encode("utf-8"))
    checks = [{"id": check, "status": "passed", "reportSha256": report_hash,
               "evidence": (os.path.relpath(handoff_path(tid, sid), REPO)
                            if check == "continuity" else
                            os.path.relpath(_section_path(tid, sid), REPO))}
              for check in required_checks(section)]
    receipt = {"version": 1, "buildId": build_id, "section": sid,
               "mapDigest": course["digest"], "sectionSha256": section_digest(tid, sid),
               "sharedCourseSha256": shared_course_digest(tid),
               "handoffSha256": handoff_digest(tid, sid),
               "reportSha256": report_hash, "checks": checks}
    _atomic_json(receipt_path(build_id, sid), receipt)
    try:
        os.remove(failure_path(build_id, sid))
    except OSError:
        pass
    return derive_course_state(build_id)


def record_section_failure(build_id, sid, report):
    course = load_course_map(build_id)
    tid, _plan = _context(build_id)
    ids = [section["id"] for section in course["sections"]]
    if sid not in ids:
        raise ValueError(f"unknown course-map section {sid!r}")
    for affected in ids[ids.index(sid):]:
        try:
            os.remove(receipt_path(build_id, affected))
        except OSError:
            pass
    text = str(report or "deterministic validation failed")[-12000:]
    _atomic_json(failure_path(build_id, sid), {
        "version": 1, "section": sid, "mapDigest": course["digest"],
        "sectionSha256": section_digest(tid, sid), "report": text,
        "reportSha256": _sha_bytes(text.encode("utf-8")),
    })
    return derive_course_state(build_id)


def refresh_course_verifications(build_id, report):
    """Reissue affected receipts only after a clean cumulative harness gate."""
    course = load_course_map(build_id)
    state = derive_course_state(build_id)
    first = next((row["ordinal"] - 1 for row in state["sections"]
                  if row["status"] != "verified"), None)
    if first is None:
        return state
    from ..prerequisites.review import review_prerequisites
    for section in course["sections"][first:]:
        validation = review_prerequisites(build_id, section["id"])
        if validation.get("status") not in ("PASS", "not-required"):
            raise ValueError(f"Validator AI did not re-pass {section['id']}: "
                             + "; ".join(validation.get("reasons") or []))
        state = record_section_verification(build_id, section["id"], report)
    unfinished = [row["id"] for row in state["sections"]
                  if row["status"] != "verified"]
    if unfinished or state["activeObligations"]:
        raise ValueError("cumulative verification did not close course truth: sections="
                         f"{unfinished}, obligations="
                         f"{[item['id'] for item in state['activeObligations']]}")
    return state


def invalidate_from(build_id, sid):
    course = load_course_map(build_id)
    ids = [section["id"] for section in course["sections"]]
    if sid not in ids:
        raise ValueError(f"unknown invalidation boundary {sid!r}")
    for owner in ids[ids.index(sid):]:
        for path in (receipt_path(build_id, owner), failure_path(build_id, owner)):
            try:
                os.remove(path)
            except OSError:
                pass
    return derive_course_state(build_id)


def clear_course_state(build_id, evidence=False):
    for path in (state_path(build_id),):
        try:
            os.remove(path)
        except OSError:
            pass
    if evidence:
        shutil.rmtree(evidence_dir(build_id), ignore_errors=True)
        shutil.rmtree(failure_dir(build_id), ignore_errors=True)


def public_course_status(build_id):
    state = derive_course_state(build_id)
    return {"mapDigest": state["mapDigest"], "currentSection": state["currentSection"],
            "spine": [{key: row[key] for key in ("id", "title", "milestone", "status",
                                                  "mark", "statusLabel")}
                      for row in state["sections"]],
            "openObligations": len(state["activeObligations"]),
            "dueObligations": sum(1 for item in state["activeObligations"]
                                  if item["dueNow"] or item["overdue"]),
            "blockers": state["blockers"], "validatorAi": state["validatorAi"]}
