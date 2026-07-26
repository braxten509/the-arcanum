#!/usr/bin/env python3
"""Reader marginalia: appended, listed newest-first, struck out, and reset-proof."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from arcanum.learning import TomeNotesStore

with tempfile.TemporaryDirectory() as root:
    notes = TomeNotesStore(root)

    assert notes.list("verisearch") == {"notes": []}, "an unwritten margin is empty, not an error"

    first = notes.add("verisearch", "  s04 l02 asks for a method the lesson never taught  ",
                      where="S04 / Reading a source", quote="call ParseAll() here")
    second = notes.add("verisearch", "the grader's tone is wrong in s09")
    assert first["id"] != second["id"], "two notes must not share an id"
    assert first["text"] == "s04 l02 asks for a method the lesson never taught", first
    assert first["quote"] == "call ParseAll() here", first
    assert second["where"] == "" and second["quote"] == "", second

    listed = notes.list("verisearch")["notes"]
    assert [n["id"] for n in listed] == [second["id"], first["id"]], "newest note reads first"

    # A note is about the course, so it must not live where RESET-PROGRESS reaches:
    # LearnerStateService.reset rmtree's tomes/<id>/save/ entirely.
    path = notes.path("verisearch")
    assert os.path.join("tomes", "verisearch", "save") not in path, path
    assert path == os.path.join(root, "notes", "verisearch.jsonl"), path
    assert sum(1 for _ in open(path, encoding="utf-8")) == 2, "one line per note"

    notes.add("homunculus", "different tome, different margin")
    assert [n["text"] for n in notes.list("homunculus")["notes"]] == [
        "different tome, different margin"], "margins are scoped to one tome"

    assert notes.remove("verisearch", first["id"]) is True
    assert notes.remove("verisearch", first["id"]) is False, "striking twice is not an error state"
    assert [n["id"] for n in notes.list("verisearch")["notes"]] == [second["id"]]
    assert not os.path.exists(path + ".tmp"), "the rewrite must not leave a temp file behind"

    for bad in ("", "../etc", "veri/search", "veri search"):
        try:
            notes.path(bad)
        except ValueError:
            continue
        raise AssertionError(f"tome id {bad!r} must not resolve to a notes path")

    try:
        notes.add("verisearch", "   ")
    except ValueError:
        pass
    else:
        raise AssertionError("an empty note must be refused, not stored")

    # A line mangled by hand must cost that line, not the whole margin.
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("{not json\n")
        handle.write(json.dumps({"text": "no id"}) + "\n")
    assert [n["id"] for n in notes.list("verisearch")["notes"]] == [second["id"]]

print("tome notes store: OK")
