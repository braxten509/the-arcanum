"""Structured primary-source receipts for hardened Phase-3 sections."""
from __future__ import annotations

import os
import tomllib
from urllib.parse import urlparse

from arcanum_core.ids import is_stable_id

from .schema import error


def _enabled(manifest: dict) -> bool:
    return (manifest.get("mastery") or {}).get("sourceEvidenceVersion") == 1


def source_findings(tome_root: str, manifest: dict, sections: list[dict]) -> list:
    """Require a bounded, attributable receipt for every authored lesson.

    The receipt deliberately records claims instead of copied documentation. It gives the
    moderate validator a concrete audit target and prevents a writer from merely asserting
    that it researched a command or API.
    """
    if not _enabled(manifest):
        return []
    findings = []
    for section in sections:
        sid = str(section.get("id") or "?")
        path = os.path.join(tome_root, "sections", sid, "research.toml")
        try:
            with open(path, "rb") as handle:
                raw = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            findings.append(error("mastery.sources.file", path,
                                  f"section source receipt is missing or invalid: {exc}", 3))
            continue
        if set(raw) != {"version", "sources"} or raw.get("version") != 1:
            findings.append(error("mastery.sources.shape", path,
                                  "research.toml keys must be exactly version=1 and sources", 3))
            continue
        rows = raw.get("sources")
        if not isinstance(rows, list) or not rows:
            findings.append(error("mastery.sources.empty", path,
                                  "research.toml needs at least one primary-source receipt", 3))
            continue
        sources = {}
        for index, row in enumerate(rows):
            label = f"{path}:source[{index}]"
            if not isinstance(row, dict) or set(row) != {"id", "url", "authority", "claims"}:
                findings.append(error("mastery.sources.row-shape", label,
                                      "source keys must be id, url, authority, claims", 3))
                continue
            source_id, url = row.get("id"), row.get("url")
            parsed = urlparse(url) if isinstance(url, str) else None
            valid_claims = (isinstance(row.get("claims"), list) and row["claims"]
                            and all(isinstance(item, str) and len(item.strip()) >= 12
                                    for item in row["claims"]))
            if (not is_stable_id(source_id) or not parsed or parsed.scheme != "https"
                    or not parsed.netloc or not isinstance(row.get("authority"), str)
                    or len(row["authority"].strip()) < 12 or not valid_claims):
                findings.append(error("mastery.sources.row-value", label,
                                      "source needs a stable id, https URL, substantive authority, "
                                      "and one or more specific claims", 3))
                continue
            if source_id in sources:
                findings.append(error("mastery.sources.duplicate", label,
                                      f"source id {source_id!r} is duplicated", 3))
            else:
                sources[source_id] = url
        used = set()
        for lesson in section.get("lessons") or []:
            if not isinstance(lesson, dict):
                continue
            lid = str(lesson.get("id") or "?")
            source_ids = lesson.get("researchSources")
            if (not isinstance(source_ids, list) or not source_ids
                    or len(source_ids) != len(set(source_ids))
                    or any(item not in sources for item in source_ids)):
                findings.append(error("mastery.sources.lesson", f"sections/{sid}/lessons/{lid}.toml",
                                      "every lesson needs unique researchSources IDs from research.toml", 3))
                continue
            used.update(source_ids)
            for reading in lesson.get("readings") or []:
                if isinstance(reading, dict) and reading.get("url") not in {sources[item] for item in source_ids}:
                    findings.append(error("mastery.sources.reading", f"sections/{sid}/lessons/{lid}.toml",
                                          "each lesson reading must be one of that lesson's source receipts", 3))
        unused = sorted(set(sources) - used)
        if unused:
            findings.append(error("mastery.sources.unused", path,
                                  "source receipts must support a lesson; unused: " + ", ".join(unused), 3))
    return findings
