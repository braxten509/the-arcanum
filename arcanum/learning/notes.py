"""Marginalia: what the reader writes about the tome while walking it."""
from __future__ import annotations

import json
import os
import re
import time
import uuid

MAX_TEXT = 4000
MAX_QUOTE = 1200
MAX_WHERE = 200


class TomeNotesStore:
    """One append-only JSONL of reader notes per tome, kept outside the save file.

    A note is a complaint about the course, not progress through it, so it lives in
    notes/<tome>.jsonl rather than the learner state: tomes/*/save/ is gitignored and
    RESET-PROGRESS deletes it wholesale, and the note that says "s04 l02 asks for a
    method the lesson never taught" has to survive exactly the replay that found it.
    """

    def __init__(self, root: str):
        self.root = root

    def path(self, tome_id: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", str(tome_id or "")):
            raise ValueError("bad tome id")
        return os.path.join(self.root, "notes", f"{tome_id}.jsonl")

    def _read(self, tome_id: str) -> list[dict]:
        try:
            with open(self.path(tome_id), encoding="utf-8") as handle:
                lines = handle.readlines()
        except OSError:
            return []
        out = []
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue  # a half-written or hand-edited line loses itself, not the file
            if isinstance(row, dict) and row.get("id"):
                out.append(row)
        return out

    def list(self, tome_id: str) -> dict:
        """Newest first — the margin is read from the most recent complaint back."""
        return {"notes": list(reversed(self._read(tome_id)))}

    def add(self, tome_id: str, text: str, where: str = "", quote: str = "") -> dict:
        text = str(text or "").strip()[:MAX_TEXT]
        if not text:
            raise ValueError("a note needs something written in it")
        note = {
            "id": uuid.uuid4().hex[:12], "at": time.time(), "text": text,
            "where": str(where or "").strip()[:MAX_WHERE],
            "quote": str(quote or "").strip()[:MAX_QUOTE],
        }
        path = self.path(tome_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(note, ensure_ascii=False) + "\n")
        return note

    def remove(self, tome_id: str, note_id: str) -> bool:
        rows = self._read(tome_id)
        kept = [row for row in rows if row.get("id") != str(note_id or "")]
        if len(kept) == len(rows):
            return False
        path = self.path(tome_id)
        temporary = path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            for row in kept:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.replace(temporary, path)
        return True
