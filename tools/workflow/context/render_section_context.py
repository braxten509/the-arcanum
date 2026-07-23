#!/usr/bin/env python3
"""Render one bounded Phase-3 author packet to replace scattered discovery reads."""
from __future__ import annotations

import sys as _command_sys
from pathlib import Path as _CommandPath
_COMMAND_REPO = _CommandPath(__file__).resolve().parents[3]
_command_sys.path[:0] = [str(_COMMAND_REPO), str(_COMMAND_REPO / "tools")]

import argparse
import json
import os
import sys

REPO = str(_COMMAND_REPO)
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from tools.buildlib.single_author.gate import context  # noqa: E402
from tools.buildlib.continuity import handoff_path  # noqa: E402
from tools.buildlib.course_map import load_course_map  # noqa: E402
from tools.buildlib.phase2.research import ledger_path  # noqa: E402
from tools.buildlib.section_quality_contract import (  # noqa: E402
    section_quality_contract_packet,
    section_quality_settings,
)


MAX_PACKET_CHARS = 180_000
MAX_FILE_CHARS = 80_000


def _read(relative):
    path = os.path.join(REPO, relative)
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        return {"path": relative, "error": str(exc)}
    if len(text) > MAX_FILE_CHARS:
        raise ValueError(f"section context source exceeds {MAX_FILE_CHARS} characters: {relative}")
    return {"path": relative, "text": text}


def render(build_id, sid):
    ctx = context(build_id)
    quality_settings = section_quality_settings(os.path.join(REPO, ".tome-build"), build_id)
    course = load_course_map(build_id)
    sections = course.get("sections") or []
    section = next((item for item in sections if item.get("id") == sid), None)
    if not section:
        raise ValueError(f"section {sid!r} is not in the sealed course map")
    ids = [item["id"] for item in sections]
    section_root = os.path.join(REPO, "tomes", ctx["tid"], "sections", sid)
    section_sources = []
    if os.path.isdir(section_root):
        for root, dirs, files in os.walk(section_root):
            dirs.sort()
            for name in sorted(files):
                if name.endswith((".toml", ".md", ".json", ".py")):
                    section_sources.append(_read(os.path.relpath(
                        os.path.join(root, name), REPO).replace(os.sep, "/")))
    handoffs = [_read(os.path.relpath(handoff_path(ctx["tid"], sid), REPO))]
    index = ids.index(sid)
    if index:
        handoffs.insert(0, _read(os.path.relpath(
            handoff_path(ctx["tid"], ids[index - 1]), REPO)))
    related_obligations = [item for item in course.get("plannedObligations") or []
                           if item.get("origin") == sid or item.get("target") == sid]
    packet = {
        "version": 1,
        "buildId": build_id,
        "tomeId": ctx["tid"],
        "sectionId": sid,
        "tooling": ctx["tooling"],
        "sealedSection": section,
        "languageMastery": course.get("languageMastery"),
        "relatedPlannedObligations": related_obligations,
        "acceptanceScenarios": course.get("acceptanceScenarios") or [],
        # This is the exact stable policy the Validator AI receives. Keeping it in
        # the bounded author packet prevents author/validator prompt drift.
        "sectionQualityContract": section_quality_contract_packet(**quality_settings),
        "phase2Research": _read(os.path.relpath(ledger_path(build_id), REPO)),
        "workflowSources": [
            _read("tome-workflow/phase-3-sections.md"),
            _read("tome-workflow/support/section-author.md"),
            _read("tome-authoring/9-proof-and-assets.md"),
            _read(ctx["plan"]),
            _read(f"tomes/{ctx['tid']}/tome.toml"),
        ],
        "handoffs": handoffs,
        "currentSectionSources": section_sources,
    }
    rendered = json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
    if len(rendered) > MAX_PACKET_CHARS:
        raise ValueError(
            f"section context packet is {len(rendered)} characters; bounded maximum is "
            f"{MAX_PACKET_CHARS}")
    return rendered


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build_id")
    parser.add_argument("section")
    args = parser.parse_args()
    print(render(args.build_id, args.section))


if __name__ == "__main__":
    main()
