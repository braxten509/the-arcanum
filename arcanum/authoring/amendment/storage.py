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
