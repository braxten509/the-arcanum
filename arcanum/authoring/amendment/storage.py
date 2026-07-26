"""Durable Binder state, review history, and recovery checkpoints."""
from __future__ import annotations

import json
import os
import re
import shutil


def amend_state_path(build_dir, tome):
    return os.path.join(build_dir, f"{tome}.amend.json")


def save_amend_state(build_dir, state):
    os.makedirs(build_dir, exist_ok=True)
    try:
        with open(amend_state_path(build_dir, state["tome"]), "w",
                  encoding="utf-8") as handle:
            json.dump(state, handle)
    except OSError:
        pass


def load_amend_state(build_dir, tome):
    try:
        with open(amend_state_path(build_dir, tome),
                  encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def clear_amend_state(build_dir, tome):
    try:
        os.remove(amend_state_path(build_dir, tome))
    except OSError:
        pass


def amend_log_path(build_dir, tome):
    return os.path.join(build_dir, f"{tome}.amend-log.json")


def save_amend_record(build_dir, tome, record):
    """Append one finished Binder run to this tome's durable amendment ledger.

    Job state lives in memory, so without this a run's turn count, cost, and final
    validator report are gone the moment the server restarts -- which is precisely
    when someone asks what that run actually did. Bounded to the last 40 runs.
    """
    path = amend_log_path(build_dir, tome)
    try:
        with open(path, encoding="utf-8") as handle:
            rows = json.load(handle)
        rows = rows if isinstance(rows, list) else []
    except (OSError, ValueError):
        rows = []
    rows.append(record)
    temporary = path + ".tmp"
    try:
        os.makedirs(build_dir, exist_ok=True)
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(rows[-40:], handle, ensure_ascii=False, indent=1)
            handle.write("\n")
        os.replace(temporary, path)
    except OSError:
        try:
            os.remove(temporary)
        except OSError:
            pass


def forget_amend_record(build_dir, tome, job_id):
    """Drop one run from the ledger; return whether a row was actually removed.

    Only a run that never finished can be dropped. A finished run is the record of an edit
    that is on disk right now -- deleting that leaves the tome changed with nothing saying
    who changed it, which is the opposite of what a ledger is for.
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]+", str(tome or "")):
        raise ValueError("invalid tome id")
    path = amend_log_path(build_dir, tome)
    try:
        with open(path, encoding="utf-8") as handle:
            rows = json.load(handle)
    except (OSError, ValueError):
        return False
    if not isinstance(rows, list):
        return False
    kept = [row for row in rows
            if not (isinstance(row, dict) and str(row.get("jobId") or "") == str(job_id)
                    and row.get("status") != "done")]
    if len(kept) == len(rows):
        return False
    temporary = path + ".tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(kept, handle, ensure_ascii=False, indent=1)
            handle.write("\n")
        os.replace(temporary, path)
    except OSError:
        try:
            os.remove(temporary)
        except OSError:
            pass
        return False
    return True


def review_metadata_path(root, report_rel):
    name = os.path.basename(str(report_rel or ""))
    if not re.fullmatch(r"[A-Za-z0-9_-]+-\d{8}-\d{6}\.md", name):
        raise ValueError("invalid review report path")
    return os.path.join(root, "reviews", ".binder-history", name + ".json")


def save_review_metadata(root, report_rel, metadata):
    path = review_metadata_path(root, report_rel)
    temporary = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(
                metadata, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
        os.replace(temporary, path)
    except OSError:
        try:
            os.remove(temporary)
        except OSError:
            pass


def review_verdict(report):
    """Return the authoritative opening recommendation instead of a tail."""
    text = str(report or "").strip()
    heading = "## Recommendation and implementation order"
    start = text.find(heading)
    if start < 0:
        return text[:6000]
    next_section = text.find("\n## ", start + len(heading))
    return text[start:next_section if next_section >= 0 else None].strip()[:12000]


def amend_history(build_dir, tome):
    """Finished Binder builds for this tome, newest first.

    The job store is in memory, so the panel that shows a run's cost is empty the moment
    the page is reloaded -- which is when someone actually goes looking for it. This reads
    the same fact back off disk. ``validator`` rides along only on a failed run, because
    that is the only time it is worth the payload.
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]+", str(tome or "")):
        return []
    try:
        with open(amend_log_path(build_dir, tome), encoding="utf-8") as handle:
            rows = json.load(handle)
    except (OSError, ValueError):
        return []
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows[-20:]:
        if not isinstance(row, dict):
            continue
        ok = row.get("status") == "done" and row.get("validatorOk") is not False
        # A run that never finished is still an offer: the bench can take its request and
        # mode up again with any hand, and show the feed it reached before it stopped.
        unfinished = row.get("status") != "done"
        setup = row.get("setup") if isinstance(row.get("setup"), dict) else None
        out.append({
            "jobId": str(row.get("jobId") or ""),
            "finishedAt": row.get("finishedAt"),
            "mode": str(row.get("mode") or ""),
            "status": str(row.get("status") or "unknown"),
            "continuations": int(row.get("continuations") or 0),
            "summary": str(row.get("summary") or ""),
            "error": str(row.get("error") or ""),
            "validatorOk": row.get("validatorOk"),
            "validator": "" if ok else str(row.get("validator") or ""),
            "apiCostEstimate": (
                row.get("apiCostEstimate")
                if isinstance(row.get("apiCostEstimate"), dict) else None),
            "unfinished": unfinished,
            "setup": setup if unfinished else None,
            "activity": ([item for item in (row.get("activity") or [])
                          if isinstance(item, dict)] if unfinished else []),
        })
    out.reverse()
    return out


def review_history(root, tome, report_path=""):
    tome = str(tome or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", tome):
        return {"reviews": []} if not report_path else {}
    reviews_dir = os.path.join(root, "reviews")
    pattern = re.compile(rf"^{re.escape(tome)}-(\d{{8}})-(\d{{6}})\.md$")

    def row(name):
        match = pattern.fullmatch(name)
        if not match:
            return None
        relative = f"reviews/{name}"
        metadata = {}
        try:
            with open(review_metadata_path(root, relative),
                      encoding="utf-8") as handle:
                loaded = json.load(handle)
                metadata = loaded if isinstance(loaded, dict) else {}
        except (OSError, ValueError):
            pass
        return {
            "path": relative,
            "createdAt": match.group(1) + match.group(2),
            "providerKind": str(metadata.get("providerKind") or ""),
            "providerModel": str(metadata.get("providerModel") or ""),
            "effort": str(metadata.get("effort") or ""),
            "usage": (
                metadata.get("usage")
                if isinstance(metadata.get("usage"), dict) else None),
            "apiCostEstimate": (
                metadata.get("apiCostEstimate")
                if isinstance(metadata.get("apiCostEstimate"), dict) else None),
        }

    if report_path:
        name = os.path.basename(str(report_path))
        item = row(name)
        if not item or str(report_path) != item["path"]:
            return {}
        try:
            with open(os.path.join(reviews_dir, name),
                      encoding="utf-8") as handle:
                content = handle.read(500_000)
        except OSError:
            return {}
        return {
            **item, "content": content, "summary": review_verdict(content),
        }
    try:
        rows = [
            item for name in os.listdir(reviews_dir)
            if (item := row(name)) is not None
        ]
    except OSError:
        rows = []
    rows.sort(key=lambda item: item["createdAt"], reverse=True)
    return {"reviews": rows}


def checkpoint_path(build_dir, tome_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", str(tome_id or "")):
        raise ValueError("invalid tome id")
    return os.path.join(build_dir, "binder-checkpoints", tome_id)


def tree_signature(root):
    rows = []
    for directory, names, files in os.walk(root):
        names[:] = sorted(name for name in names if name != "save")
        for name in sorted(files):
            path = os.path.join(directory, name)
            with open(path, "rb") as handle:
                rows.append((os.path.relpath(path, root), handle.read()))
    return rows


def checkpoint_tome(root, build_dir, tome_id):
    source = os.path.join(root, "tomes", tome_id)
    checkpoint = checkpoint_path(build_dir, tome_id)
    if os.path.isdir(checkpoint):
        shutil.rmtree(checkpoint)
    os.makedirs(os.path.dirname(checkpoint), exist_ok=True)
    shutil.copytree(source, checkpoint, ignore=shutil.ignore_patterns("save"))


def clear_checkpoint(build_dir, tome_id):
    shutil.rmtree(checkpoint_path(build_dir, tome_id), ignore_errors=True)


def rollback_tome(root, build_dir, tome_id):
    target = os.path.join(root, "tomes", tome_id)
    checkpoint = checkpoint_path(build_dir, tome_id)
    if not os.path.isdir(checkpoint):
        raise RuntimeError("Binder recovery checkpoint is missing")
    for name in os.listdir(target):
        if name == "save":
            continue
        path = os.path.join(target, name)
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
    shutil.copytree(checkpoint, target, dirs_exist_ok=True)
    clear_checkpoint(build_dir, tome_id)


def tome_has_changes(root, build_dir, tome_id):
    return tree_signature(os.path.join(root, "tomes", tome_id)) != tree_signature(
        checkpoint_path(build_dir, tome_id))
