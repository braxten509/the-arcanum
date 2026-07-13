#!/usr/bin/env python3
"""Phase 8 must pause for operator approval on reviewer death and review-cap failure."""
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from buildlib import review  # noqa: E402


def exercise(codes, max_loops):
    verdicts = iter([None] * len(codes) + ["PASS"])
    selected = []
    requests = []
    replacement = ("codex-cli replacement", ["replacement"], "stdin")

    def scoped(name, command, *_args):
        selected.append(name)
        return command

    def choose(*args, **kwargs):
        requests.append({"args": args, "report": kwargs.get("report")})
        return replacement, 1

    with tempfile.TemporaryDirectory() as tmp, \
            patch.object(review, "MAX_STUDENT_LOOPS", max_loops), \
            patch.object(review, "read_tooling", return_value="internal"), \
            patch.object(review, "read_verdict", side_effect=lambda _path: next(verdicts)), \
            patch.object(review, "read_findings", return_value="blocking gap"), \
            patch.object(review, "review_findings_clear", return_value=True), \
            patch.object(review, "review_pass_eligible", return_value=True), \
            patch.object(review, "phase_sidecars", return_value=[]), \
            patch.object(review, "phase_writable_paths", return_value=[]), \
            patch.object(review, "scoped_runner_command", side_effect=scoped), \
            patch.object(review, "review_inventory", return_value={}), \
            patch.object(review, "review_changes", return_value=[]), \
            patch.object(review, "run_agent", side_effect=codes), \
            patch.object(review, "validate", return_value=(True, "")), \
            patch.object(review, "inventory", return_value={}), \
            patch.object(review, "shrinkage", return_value=[]), \
            patch.object(review, "selected_runtime_config", return_value=None), \
            patch.object(review, "runtime_config_scope_violations", return_value=[]), \
            patch.object(review, "request_runner", side_effect=choose):
        paths = tuple(os.path.join(tmp, name) for name in
                      ("plan.md", "verdict", "findings.json", "shrink-ok"))
        result = review.run_student_review(
            "tome", "Student review", "body", ("claude-cli original", ["original"], "stdin"),
            ("plan.md", "verdict", "findings.json"), paths,
            {}, {}, 0, [], 0, "", "", 1, 1, 1, [],
            build_id="launch-id", ask_on_death=True)
    assert result is None, result
    return selected, requests


# A nonzero reviewer exit asks for a replacement immediately, then retries the same round.
selected, requests = exercise([1, 0], 4)
assert selected == ["claude-cli original", "codex-cli replacement"], selected
assert len(requests) == 1 and requests[0]["report"] is None, requests
assert requests[0]["args"][0] == "launch-id", requests

# A cleanly exiting reviewer that still cannot PASS asks before extending the round budget.
selected, requests = exercise([0, 0], 2)
assert selected == ["claude-cli original", "codex-cli replacement"], selected
assert len(requests) == 1 and requests[0]["report"] == "blocking gap", requests

print("phase 8 retry approval: OK")
