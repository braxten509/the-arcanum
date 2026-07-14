#!/usr/bin/env python3
"""Phase 8 escalates autonomously on reviewer death and review-cap failure."""
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from buildlib import review  # noqa: E402


def exercise(codes, max_loops):
    verdicts = iter([None] * len(codes) + ["PASS"])
    selected = []
    replacement = ("codex-cli replacement", ["replacement"], "stdin")

    def scoped(name, command, *_args):
        selected.append(name)
        return command

    with tempfile.TemporaryDirectory() as tmp, \
            patch.object(review, "MAX_STUDENT_LOOPS", max_loops), \
            patch.object(review, "read_tooling", return_value="internal"), \
            patch.object(review, "read_verdict", side_effect=lambda *_args: next(verdicts)), \
            patch.object(review, "read_findings", return_value="blocking gap"), \
            patch.object(review, "review_findings_clear", return_value=True), \
            patch.object(review, "review_pass_eligible", return_value=True), \
            patch.object(review, "phase_sidecars", return_value=[]), \
            patch.object(review, "prepare_phase_writable_paths", return_value=[]), \
            patch.object(review, "scoped_runner_command", side_effect=scoped), \
            patch.object(review, "preflight_recovery_runner", return_value=True), \
            patch.object(review, "ensure_validation_environment", return_value={}), \
            patch.object(review, "validation_subprocess_env", return_value=os.environ.copy()), \
            patch.object(review, "review_inventory", return_value={}), \
            patch.object(review, "review_changes", return_value=[]), \
            patch.object(review, "run_agent", side_effect=codes), \
            patch.object(review, "validate_shipping", return_value=(True, "")), \
            patch.object(review, "inventory", return_value={}), \
            patch.object(review, "shrinkage", return_value=[]), \
            patch.object(review, "selected_runtime_config", return_value=None), \
            patch.object(review, "runtime_config_scope_violations", return_value=[]):
        paths = tuple(os.path.join(tmp, name) for name in
                      ("plan.md", "verdict", "findings.json", "shrink-ok"))
        result = review.run_student_review(
            "tome", "Student review", "body", ("claude-cli original", ["original"], "stdin"),
            ("plan.md", "verdict", "findings.json"), paths,
            {}, {}, 0, [], 0, "", "", 1, 1, 1, [],
            runner_chain=[
                ("claude-cli original", ["original"], "stdin"), replacement])
    assert result is None, result
    return selected


# A nonzero reviewer exit asks for a replacement immediately, then retries the same round.
selected = exercise([1, 0], 4)
assert selected == ["claude-cli original", "codex-cli replacement"], selected

# A cleanly exiting reviewer that still cannot PASS asks before extending the round budget.
selected = exercise([0, 0], 2)
assert selected == ["claude-cli original", "codex-cli replacement"], selected

print("phase 8 autonomous review escalation: OK")
