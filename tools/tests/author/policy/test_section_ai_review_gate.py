#!/usr/bin/env python3
"""The per-section Validator AI has three modes: off, one advisory pass, or one enforced gate."""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from tools.buildlib.single_author import section_review
from tools.buildlib.prerequisites.ledger import finding_fingerprints


def _quality(node, lines, evid):
    return {"path": f"tomes/t/sections/s01/{node}.toml", "node": f"s01.{node}",
            "category": "technical-correctness", "evidenceLines": lines,
            "evidence": evid, "requiredRepair": f"fix {node}"}


def _setup(tmp, *, launch=None, ledger_pass=None, bid="t", sid="s01"):
    if launch is not None:
        with open(os.path.join(tmp, f"{bid}.launch.json"), "w", encoding="utf-8") as f:
            json.dump(launch, f)
    if ledger_pass is not None:
        folder = os.path.join(tmp, f"{bid}.section-findings")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, f"{sid}.json"), "w", encoding="utf-8") as f:
            json.dump({"pass": ledger_pass, "findings": {}}, f)


def test_mode_budgets():
    with tempfile.TemporaryDirectory() as tmp:
        original = section_review.BUILD_DIR
        section_review.BUILD_DIR = tmp
        try:
            # Single pass: one run only.
            _setup(tmp, launch={"sectionAiReviewMode": "pass"}, ledger_pass=0)
            assert section_review._mode("t") == "pass"
            assert section_review.should_run("t", "s01") is True
            _setup(tmp, launch={"sectionAiReviewMode": "pass"}, ledger_pass=1)
            assert section_review.should_run("t", "s01") is False

            # Single gate: discovery pass plus up to three verify passes, then mechanical-only.
            _setup(tmp, launch={"sectionAiReviewMode": "gate"}, ledger_pass=0)
            assert section_review.should_run("t", "s01") is True
            _setup(tmp, launch={"sectionAiReviewMode": "gate"}, ledger_pass=1)
            assert section_review.should_run("t", "s01") is True
            _setup(tmp, launch={"sectionAiReviewMode": "gate"}, ledger_pass=2)
            assert section_review.should_run("t", "s01") is True
            _setup(tmp, launch={"sectionAiReviewMode": "gate"}, ledger_pass=3)
            assert section_review.should_run("t", "s01") is True
            _setup(tmp, launch={"sectionAiReviewMode": "gate"}, ledger_pass=4)
            assert section_review.should_run("t", "s01") is False

            # A resumed section past many passes stays skipped, never re-looped.
            _setup(tmp, launch={"sectionAiReviewMode": "gate"}, ledger_pass=19)
            assert section_review.should_run("t", "s01") is False

            # Off: never run, regardless of pass count.
            _setup(tmp, launch={"sectionAiReviewMode": "off"}, ledger_pass=0)
            assert section_review.should_run("t", "s01") is False

            # Back-compat with the retired boolean.
            _setup(tmp, launch={"sectionAiReview": False}, ledger_pass=0)
            assert section_review._mode("t") == "off"
            assert section_review.should_run("t", "s01") is False
            _setup(tmp, launch={"sectionAiReview": True}, ledger_pass=0)
            assert section_review._mode("t") == "pass"

            # Missing flag defaults to pass; missing ledger counts as zero passes.
            _setup(tmp, launch={}, ledger_pass=None)
            assert section_review.should_run("t", "s01") is True

            # Missing launch.json defaults to pass too.
            os.remove(os.path.join(tmp, "t.launch.json"))
            assert section_review._mode("t") == "pass"
        finally:
            section_review.BUILD_DIR = original


def test_gate_verify_pass():
    """Single Gate's second run re-checks only the first pass's findings; new issues drop out."""
    prior = _quality("l07", [117, 123], "wrong const")
    prior_fp = next(iter(finding_fingerprints({"qualityFindings": [prior]})))
    unit = {"section": "s01"}
    with tempfile.TemporaryDirectory() as tmp:
        original = section_review.BUILD_DIR
        section_review.BUILD_DIR = tmp
        try:
            _setup(tmp, launch={"sectionAiReviewMode": "gate"})
            folder = os.path.join(tmp, "t.section-findings")
            os.makedirs(folder, exist_ok=True)
            ledger_path = os.path.join(folder, "s01.json")
            with open(ledger_path, "w", encoding="utf-8") as f:
                json.dump({"pass": 1, "findings": {prior_fp: {"status": "open", "kind": "quality"}}}, f)

            # Prior finding resolved; the model raised only a brand-new issue -> gate PASSes.
            resolved = {"status": "FAIL", "qualityFindings": [_quality("l09", [5, 8], "new")]}
            with patch.object(section_review, "review_prerequisites", return_value=resolved):
                ok, report = section_review.review_section("t", unit)
            assert ok is True and report == "", (ok, report)

            # Prior finding persists -> gate FAILs, and only the gated finding is reported.
            persists = {"status": "FAIL", "reasons": ["s01.l07 still wrong"],
                        "qualityFindings": [_quality("l07", [119, 124], "still wrong"),
                                            _quality("l09", [5, 8], "new")]}
            with patch.object(section_review, "review_prerequisites", return_value=persists), \
                    patch.object(section_review, "record_section_failure"):
                ok, report = section_review.review_section("t", unit)
            assert ok is False and "l07" in report and "l09" not in report, (ok, report)
        finally:
            section_review.BUILD_DIR = original


if __name__ == "__main__":
    test_mode_budgets()
    test_gate_verify_pass()
    print("ok")
