#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""Cross-pass finding ledger + tiebreak escalation in the mandatory section audit."""
import json
import os
import tempfile
from unittest.mock import patch

from buildlib.prerequisites import review as prerequisite_review


course = {
    "version": 4,
    "mechanismContract": {"version": 1, "coverageStart": "s01", "mechanisms": [
        {"id": "function-definition", "label": "fn", "kind": "syntax-form",
         "owner": "s01.l01"}]},
    "sections": [{"id": "s01", "nodes": [
        {"id": "s01.l01", "kind": "lesson", "introduces": ["function-definition"]},
        {"id": "s01.working", "kind": "working", "mechanisms": ["function-definition"]}]}],
}
sources = [{"path": "tomes/demo/sections/s01/lessons/l01.toml", "node": "s01.l01"},
           {"path": "tomes/demo/sections/s01/freestyle.toml", "node": "s01.working"}]
citations = [{"path": item["path"], "node": item["node"]} for item in sources]
finding = {"path": sources[0]["path"], "node": sources[0]["node"],
           "category": "technical-correctness", "evidenceLines": [2, 4],
           "evidence": "The count-three solution prints the wrong exit status.",
           "requiredRepair": "Correct the exit-status computation and reteach the syscall."}


def audit_result(outcome="PASS", quality=None):
    quality = list(quality or [])
    failed = {(item["path"], item["node"]) for item in quality}
    return {
        "outcome": outcome, "citations": citations,
        "reasons": ["A cited section-quality finding." if quality
                    else "Every node has concrete evidence."],
        "missingMechanisms": [],
        "nodeReviews": [{
            "path": item["path"], "node": item["node"],
            "judgment": "FAIL" if (item["path"], item["node"]) in failed else "PASS",
            "evidenceLines": [1, 1],
            "evidence": "Concrete teaching and independent practice appear here.",
        } for item in sources],
        "qualityFindings": quality,
    }


def _launch(root, build_id, tiebreak):
    payload = {"validator": {"kind": "codex-cli", "model": "luna"},
               "gate": {"prior_level": "2", "prior_knowledge": "x", "depth": "7",
                        "mastery": "3"}}
    if tiebreak:
        payload["tiebreakValidator"] = {"kind": "claude-cli", "model": "terra"}
    with open(os.path.join(root, f"{build_id}.launch.json"), "w", encoding="utf-8") as handle:
        json.dump(payload, handle)


def _review(build_id, adapter, tag):
    # A distinct packet per pass mimics an author edit so the content cache misses.
    def packet_fn(_build_id, _section, _only_nodes=None):
        return (f"bounded packet {tag}", sources)

    with patch.object(prerequisite_review, "load_course_map", return_value=course), \
            patch.object(prerequisite_review, "section_evidence_packet", side_effect=packet_fn):
        return prerequisite_review.review_prerequisites(build_id, "s01", adapter=adapter)


with tempfile.TemporaryDirectory() as root:
    old_build = prerequisite_review.BUILD_DIR
    old_failure = prerequisite_review.VALIDATOR_FAILURE_DIR
    prerequisite_review.BUILD_DIR = root
    prerequisite_review.VALIDATOR_FAILURE_DIR = os.path.join(root, "validator-failures")
    try:
        # --- withdraw: the stronger auditor does not reproduce the stuck finding -----------
        _launch(root, "withdraw", tiebreak=True)
        routed = []

        def withdraw_adapter(_prompt, reviewer):
            routed.append(reviewer["model"])
            return audit_result("PASS") if reviewer["model"] == "terra" \
                else audit_result("FAIL", [finding])

        first = _review("withdraw", withdraw_adapter, "a")
        assert first["status"] == "FAIL" and not first["cached"], first["status"]
        assert routed == ["luna"], routed  # no escalation on first sighting
        assert len(first["findingDiff"]["new"]) == 1
        assert not first["findingDiff"]["persisting"]

        second = _review("withdraw", withdraw_adapter, "b")
        # Same finding survived the edit -> luna then terra; terra clears it -> section PASSES.
        assert routed == ["luna", "luna", "terra"], routed
        assert second["status"] == "PASS", second["status"]
        assert len(second["findingDiff"]["resolved"]) == 1
        assert second["findingDiff"]["openCount"] == 0

        # --- confirm: the stronger auditor reproduces it -> stays blocked, marked escalated -
        _launch(root, "confirm", tiebreak=True)
        confirm_routed = []

        def confirm_adapter(_prompt, reviewer):
            confirm_routed.append(reviewer["model"])
            return audit_result("FAIL", [finding])  # both models see the real defect

        assert _review("confirm", confirm_adapter, "a")["status"] == "FAIL"
        confirmed = _review("confirm", confirm_adapter, "b")
        assert confirm_routed == ["luna", "luna", "terra"], confirm_routed
        assert confirmed["status"] == "FAIL", confirmed["status"]
        persisting = confirmed["findingDiff"]["persisting"]
        assert len(persisting) == 1 and persisting[0]["occurrences"] == 2
        assert persisting[0]["escalated"] is True

        # --- no tiebreak configured: ledger still tracks, but no second opinion is spent ----
        _launch(root, "solo", tiebreak=False)
        solo_routed = []

        def solo_adapter(_prompt, reviewer):
            solo_routed.append(reviewer["model"])
            return audit_result("FAIL", [finding])

        _review("solo", solo_adapter, "a")
        _review("solo", solo_adapter, "b")
        assert solo_routed == ["luna", "luna"], solo_routed  # never escalates without config
    finally:
        prerequisite_review.BUILD_DIR = old_build
        prerequisite_review.VALIDATOR_FAILURE_DIR = old_failure

print("finding ledger + escalation tests: OK")
