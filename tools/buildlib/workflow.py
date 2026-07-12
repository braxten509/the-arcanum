"""Workflow phase discovery and the access contract appended to every build prompt."""
import glob
import os
import re

from . import REPO, WORKFLOW_DIR


PHASE_H1 = re.compile(r"#\s*Phase (\d+)\s*—\s*(.*)")


def parse_phases():
    """Return ordered `(number, title, body)` tuples from tome-workflow phase files."""
    phases = []
    for path in glob.glob(os.path.join(WORKFLOW_DIR, "phase-*.md")):
        head, _, body = open(path, encoding="utf-8").read().partition("\n")
        match = PHASE_H1.fullmatch(head.strip())
        if not match:
            raise SystemExit(
                f"{path}: first line must be '# Phase N — Title', got {head.strip()!r}"
            )
        phases.append((int(match.group(1)), match.group(2).strip(), body.strip()))
    if not phases:
        raise SystemExit(f"parsed 0 phases from {WORKFLOW_DIR}/ — where did they go?")
    return sorted(phases)


def access_boundary(tid):
    return (f"\n\n===== AI ACCESS BOUNDARY =====\nThe repository root is {REPO}. "
            "You may read and execute trusted files anywhere in it, use web search/fetch, "
            f"and use /tmp. You may edit the complete tome at tomes/{tid}/ and only the "
            "named build plan/verdict/findings sidecars outside it. Do not edit engine code, "
            "another tome, or unrelated build state. Resolve repo-relative paths against the "
            "repository root.")
