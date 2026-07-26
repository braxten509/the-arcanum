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
from tools.buildlib.prerequisites.prompt import prerequisite_prompt, verify_prompt


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


def test_verify_pass_asks_only_about_open_findings():
    """Rounds 2-4 must send the verify prompt, not a full audit whose answer is then discarded.

    The saving is entirely in what gets asked: a full audit buys every source in the section
    plus a nodeReview per source. If the `verify` kwarg ever stops being passed the gate still
    works and nothing fails — it just quietly costs four full audits again.
    """
    prior = _quality("l07", [117, 123], "wrong const")
    prior_fp = next(iter(finding_fingerprints({"qualityFindings": [prior]})))
    entry = {"status": "open", "kind": "quality", "node": "s01.l07",
             "path": prior["path"], "category": "technical-correctness",
             "lines": [117, 123], "repair": "fix l07", "evidence": "wrong const"}
    with tempfile.TemporaryDirectory() as tmp:
        original = section_review.BUILD_DIR
        section_review.BUILD_DIR = tmp
        try:
            _setup(tmp, launch={"sectionAiReviewMode": "gate"})
            folder = os.path.join(tmp, "t.section-findings")
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, "s01.json"), "w", encoding="utf-8") as f:
                json.dump({"pass": 1, "findings": {prior_fp: entry}}, f)
            seen = {}

            def capture(build_id, sid, **kwargs):
                seen.update(kwargs)
                return {"status": "PASS"}

            with patch.object(section_review, "review_prerequisites", capture):
                section_review.review_section("t", {"section": "s01"})
            assert set(seen.get("verify") or {}) == {prior_fp}, seen

            # The discovery pass is a real audit and must NOT be narrowed to a finding list.
            with open(os.path.join(folder, "s01.json"), "w", encoding="utf-8") as f:
                json.dump({"pass": 0, "findings": {}}, f)
            seen.clear()
            with patch.object(section_review, "review_prerequisites", capture):
                section_review.review_section("t", {"section": "s01"})
            assert seen.get("verify") is None, seen
        finally:
            section_review.BUILD_DIR = original

    # A pre-change ledger has findings with no node. Narrowing the packet to that citation set
    # would leave the model judging an empty evidence list, so it must fall back to the full one.
    from tools.buildlib.prerequisites import review as prerequisite_review
    seen_nodes = {}
    scratch = tempfile.TemporaryDirectory()
    with scratch, patch.object(prerequisite_review, "BUILD_DIR", scratch.name), \
            patch.object(prerequisite_review, "_configuration",
                      return_value=(5, {"kind": "k", "model": "m"}, "", 5, 3)), \
            patch.object(prerequisite_review, "load_course_map",
                         return_value={"sections": [{"id": "s01", "nodes": []}]}), \
            patch.object(prerequisite_review, "section_evidence_packet",
                         side_effect=lambda _b, _s, only=None: (
                             seen_nodes.setdefault("only", only), ("packet", []))[1]), \
            patch.object(prerequisite_review, "_invoke", return_value=("PASS", {})):
        prerequisite_review.review_prerequisites(
            "t", "s01", verify={"fp": {"kind": "quality", "repair": "r"}})
    assert seen_nodes["only"] is None, seen_nodes

    # The prompt must hand back the exact identity fields, or a still-open finding gets a
    # fresh fingerprint on re-report, reads as absent to `reconcile`, and is recorded resolved.
    text = verify_prompt("PACKET", "s01", [entry])
    assert "s01.l07" in text and "[117,123]" in text and "fix l07" in text
    assert "nodeReviews" not in text.split("Omit nodeReviews")[0], \
        "a verify pass that still asks for nodeReviews saves nothing on output"
    full = prerequisite_prompt("PACKET", "s01", [{"path": "p", "node": "n"}], "", 5, 5, 3)
    assert len(text) < len(full) / 3, (len(text), len(full))


if __name__ == "__main__":
    test_mode_budgets()
    test_gate_verify_pass()
    test_verify_pass_asks_only_about_open_findings()
    print("ok")
