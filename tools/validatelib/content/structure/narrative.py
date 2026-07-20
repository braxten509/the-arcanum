"""The [narrative] table: objective, boot/grading line counts, completion text."""
from ... import err, warn


def check_narrative(m, label):
    nar = m.get("narrative", {})
    if not isinstance(nar, dict) or not str(nar.get("objective", "")).strip():
        err(label, "[narrative] objective is required and must be non-empty — "
                   "the server refuses to load a tome without it")
        return
    nboot = len(nar.get("bootLines", []) or [])
    ngrade = len(nar.get("gradingLines", []) or [])
    if not 8 <= nboot <= 12:
        warn("content", f"[narrative] bootLines has {nboot} line(s) — spec wants 8–12 "
             "(establish the fiction, the mentor, and the commission)", phase=2)
    if not 6 <= ngrade <= 8:
        warn("content", f"[narrative] gradingLines has {ngrade} line(s) — spec wants 6–8 "
             "in-character lines", phase=2)
    if not str(nar.get("completeText", "")).strip():
        warn("content", "[narrative] completeText is missing — the course-complete screen "
             "falls back to generic engine text instead of this tome's voice at its biggest "
             "moment", phase=2)
