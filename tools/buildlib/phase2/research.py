"""Bounded primary-source ledger shared by Phase 2 and downstream authors."""
from __future__ import annotations

import json
import os
import re

from .. import BUILD_DIR, REPO

MAX_SOURCES = 6


def ledger_path(build_id):
    return os.path.join(BUILD_DIR, f"{build_id}.phase2-research.json")


def initialize_ledger(build_id, tooling):
    required = str(tooling).lower() in ("external", "both")
    value = {
        "version": 1,
        "required": required,
        "reason": ("External tooling requires current official or primary-source verification."
                   if required else "No external-tool verification is required."),
        "sources": [],
    }
    path = ledger_path(build_id)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temporary, path)
    return path


def _tooling_from_plan(build_id):
    try:
        with open(os.path.join(BUILD_DIR, f"{build_id}.plan.md"), encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return ""
    match = re.search(r"(?im)^- \*\*Tooling:\*\*\s*(internal|external|both)\s*$", text)
    return match.group(1).lower() if match else ""


def validate_ledger(build_id, tooling=None):
    path = ledger_path(build_id)
    relative = os.path.relpath(path, REPO)
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, ValueError) as exc:
        return False, f"Phase 2 research ledger is missing or invalid: {relative}: {exc}"
    problems = []
    if set(value) != {"version", "required", "reason", "sources"} or value.get("version") != 1:
        problems.append("ledger keys/version do not match research contract v1")
    sources = value.get("sources")
    if not isinstance(sources, list):
        problems.append("sources must be an array")
        sources = []
    if len(sources) > MAX_SOURCES:
        problems.append(f"sources must contain at most {MAX_SOURCES} entries")
    selected_tooling = str(tooling or _tooling_from_plan(build_id)).strip().lower()
    expected_required = selected_tooling in ("external", "both")
    if selected_tooling in ("internal", "external", "both") and value.get("required") is not expected_required:
        problems.append(
            f"required must be {str(expected_required).lower()} for Tooling {selected_tooling}")
    if value.get("required") is True and not sources:
        problems.append("external tooling requires at least one official or primary source")
    for index, source in enumerate(sources):
        label = f"sources[{index}]"
        expected = {"title", "url", "publisher", "supports", "official"}
        if not isinstance(source, dict) or set(source) != expected:
            problems.append(f"{label} keys must be exactly {', '.join(sorted(expected))}")
            continue
        if not re.fullmatch(r"https://\S+", str(source.get("url") or "")):
            problems.append(f"{label}.url must be an https URL")
        if source.get("official") is not True:
            problems.append(f"{label}.official must be true; do not cite aggregators")
        for key in ("title", "publisher", "supports"):
            if not isinstance(source.get(key), str) or not source[key].strip():
                problems.append(f"{label}.{key} must be a non-empty string")
    return (not problems, "" if not problems else "Phase 2 research ledger:\n- " + "\n- ".join(problems))
