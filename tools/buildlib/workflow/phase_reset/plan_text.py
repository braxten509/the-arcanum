"""Rewinding the build plan's own text back to the shape a phase starts with."""
from __future__ import annotations

import re

from ..checkpoints import ARC_CONTRACT, ARC_HEADING


GROUND_TRUTH_RE = re.compile(r"(?m)^## Harness ground truth\b")
RENAME_RE = re.compile(
    r"(?m)^\s*-\s*\*\*Tome id renamed by the harness:\*\*[^\n]*(?:\n|$)")
CALIBRATION_RE = re.compile(r"(?ms)^## Calibration contract\n.*?(?=^## Arc\b)")
GATE_LABELS = ("Prior knowledge", "Starting level (1-10)", "Project scope (1-5)",
               "Lesson depth (1-10)", "Mastery (1-5)", "Tooling")


def reset_plan_text(text, phase):
    """Remove completion evidence and return the plan shape valid at ``phase`` start."""
    phase = int(phase)
    if phase not in range(1, 9):
        raise ValueError("phase must be between 1 and 8")
    match = GROUND_TRUTH_RE.search(text)
    if match:
        text = text[:match.start()].rstrip() + "\n"
    if phase == 1:
        from ..prompts import calibration_contract
        answers = []
        for label in GATE_LABELS:
            answer = re.search(
                rf"(?im)^- \*\*{re.escape(label)}:\*\*\s*(\S.*)$", text)
            if not answer:
                answers = []
                break
            answers.append((label, answer.group(1).strip()))
        if not answers:
            # Phase snapshots from before Project Scope used Breadth 1–10. Preserve their
            # intent through the documented 2:1 compatibility mapping.
            legacy_labels = list(GATE_LABELS)
            legacy_labels[2] = "Breadth (1-10)"
            legacy_answers = []
            for label in legacy_labels:
                answer = re.search(
                    rf"(?im)^- \*\*{re.escape(label)}:\*\*\s*(\S.*)$", text)
                if not answer:
                    legacy_answers = []
                    break
                legacy_answers.append((label, answer.group(1).strip()))
            if legacy_answers:
                breadth = int(legacy_answers[2][1])
                legacy_answers[2] = ("Project scope (1-5)",
                                     str(max(1, min(5, (breadth + 1) // 2))))
                answers = legacy_answers
        if answers:
            refreshed = "## Calibration contract\n" + calibration_contract(answers) + "\n"
            if CALIBRATION_RE.search(text):
                text = CALIBRATION_RE.sub(refreshed, text, count=1)
        head, marker, _old_arc = text.partition("## Arc")
        if not marker:
            raise ValueError("the build plan has no Arc boundary to reset")
        return head + ARC_HEADING + ARC_CONTRACT
    if phase == 2:
        text = RENAME_RE.sub("", text)
    return text.rstrip() + "\n"


def _mastery_from_plan(text):
    match = re.search(r"(?im)^- \*\*Mastery \(1-5\):\*\*\s*([1-5])\s*$", str(text or ""))
    return int(match.group(1)) if match else 1
