#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""Mechanism ordering, demand union, and cached prerequisite-review policy."""
import json
import io
import os
import sys
import tempfile
import urllib.request
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from buildlib.mechanism_contract import (authored_problems, candidate_with_findings,
                                         validate_map_contract)
from buildlib.prerequisites import review as prerequisite_review


lesson = {"id": "s01.l01", "kind": "lesson", "introduces": ["function-definition"]}
working = {"id": "s01.working", "kind": "working", "mechanisms": ["function-definition"]}
section = {"id": "s01", "nodes": [lesson, working]}
course = {
    "version": 4,
    "mechanismContract": {
        "version": 1,
        "coverageStart": "s01",
        "mechanisms": [{"id": "function-definition", "label": "function definition",
                        "kind": "syntax-form", "owner": "s01.l01"}],
    },
    "sections": [section],
}
positions = {"s01": (1, -1), "s01.l01": (1, 0), "s01.working": (1, 1)}
assert not validate_map_contract(course, [section], positions, detailed=True, map_version=4)
too_late = json.loads(json.dumps(course))
too_late["mechanismContract"]["mechanisms"][0]["owner"] = "s01.l02"
assert any("owner must name" in item or "match" in item for item in
           validate_map_contract(too_late, [section], positions, detailed=True, map_version=4))

actual = {
    "lessons": [{"id": "s01-l01", "introduces": ["function-definition"],
                 "exercises": [{"mechanisms": ["function-definition"]}]}],
    "freestyle": {"mechanisms": ["function-definition"],
                  "rubric": [{"mechanisms": ["function-definition"]}],
                  "referenceSteps": [{"mechanisms": ["function-definition"]}]},
    "proof": {"mechanisms": []},
}
assert not authored_problems(course, actual, "s01")
missing_guided = json.loads(json.dumps(actual))
missing_guided["lessons"][0]["exercises"][0]["mechanisms"] = []
assert any("lack guided exercise demand" in item for item in
           authored_problems(course, missing_guided, "s01"))
missing_working_course = json.loads(json.dumps(course))
missing_working_course["sections"][0]["nodes"][1]["mechanisms"] = []
missing_working = json.loads(json.dumps(actual))
missing_working["freestyle"]["mechanisms"] = []
missing_working["freestyle"]["rubric"][0]["mechanisms"] = []
missing_working["freestyle"]["referenceSteps"][0]["mechanisms"] = []
assert any("absent from the chapter Working demand" in item for item in
           authored_problems(missing_working_course, missing_working, "s01"))
typing_only = json.loads(json.dumps(actual))
typing_only["lessons"][0]["exercises"][0].update({"id": "s01-l01-d1", "type": "type"})
typing_only["lessons"][0]["concepts"] = [
    {"id": "function-definition", "practice": "s01-l01-d1"}]
assert any("as its only guided practice" in item for item in
           authored_problems(course, typing_only, "s01"))
missing_demand = json.loads(json.dumps(actual))
missing_demand["freestyle"]["rubric"][0]["mechanisms"] = []
missing_demand["freestyle"]["referenceSteps"][0]["mechanisms"] = []
assert any("exactly equal the union" in item for item in
           authored_problems(course, missing_demand, "s01"))

undeclared_delete = json.loads(json.dumps(actual))
undeclared_delete["freestyle"]["referenceSteps"][0].update({
    "mode": "delete", "mechanisms": ["function-definition"]})
assert any("mode='delete' must declare an introduced file-deletion" in item for item in
           authored_problems(course, undeclared_delete, "s01"))
undeclared_lesson_delete = json.loads(json.dumps(actual))
undeclared_lesson_delete["lessons"][0]["artifactSteps"] = [{
    "mode": "delete", "mechanisms": ["function-definition"]}]
assert any("s01.l01.artifactSteps[0] mode='delete'" in item for item in
           authored_problems(course, undeclared_lesson_delete, "s01"))

delete_course = json.loads(json.dumps(course))
delete_course["mechanismContract"]["mechanisms"].append({
    "id": "terminal-delete-file", "label": "terminal file-deletion action",
    "kind": "tool-action", "owner": "s01.l01"})
delete_course["sections"][0]["nodes"][0]["introduces"].append("terminal-delete-file")
delete_course["sections"][0]["nodes"][1]["mechanisms"].append("terminal-delete-file")
declared_delete = json.loads(json.dumps(actual))
declared_delete["lessons"][0]["introduces"].append("terminal-delete-file")
declared_delete["lessons"][0]["exercises"][0]["mechanisms"].append(
    "terminal-delete-file")
declared_delete["lessons"][0]["artifactSteps"] = [{
    "mode": "delete",
    "mechanisms": ["function-definition", "terminal-delete-file"],
}]
declared_delete["freestyle"]["mechanisms"].append("terminal-delete-file")
declared_delete["freestyle"]["referenceSteps"][0].update({
    "mode": "delete",
    "mechanisms": ["function-definition", "terminal-delete-file"],
})
assert not authored_problems(delete_course, declared_delete, "s01")

retirement_course = json.loads(json.dumps(course))
retirement_course["sections"].append({
    "id": "s02", "nodes": [
        {"id": "s02.l01", "kind": "lesson", "introduces": []},
        {"id": "s02.working", "kind": "working", "mechanisms": []},
    ],
})
retirement_course["artifactContract"] = {
    "version": 1,
    "artifacts": [{
        "artifact": "temporary.txt", "ownerWorking": "s01.working",
        "disposition": "retires", "retireBy": "s02",
    }],
}
retirement_positions = {
    "s01": (0, -1), "s01.l01": (0, 0), "s01.working": (0, 1),
    "s02": (1, -1), "s02.l01": (1, 0), "s02.working": (1, 1),
}
assert any("file-deletion tool-action mechanism must be owned" in item for item in
           validate_map_contract(
               retirement_course, retirement_course["sections"], retirement_positions,
               detailed=True, map_version=4))
retirement_course["mechanismContract"]["mechanisms"].append({
    "id": "terminal-delete-file", "label": "terminal file-deletion action",
    "kind": "tool-action", "owner": "s02.l01",
})
retirement_course["sections"][1]["nodes"][0]["introduces"].append(
    "terminal-delete-file")
assert not validate_map_contract(
    retirement_course, retirement_course["sections"], retirement_positions,
    detailed=True, map_version=4)

finding = {
    "id": "function-call", "label": "function call", "kind": "syntax-form",
    "owner": "s01.l01", "demands": ["s01.l01", "s01.working"],
    "closestExisting": ["function-definition"],
    "semanticDelta": "Invoking an existing function is a distinct state transition from defining it.",
}
expanded = candidate_with_findings(course, "s01", [finding])
added = expanded["mechanismContract"]["mechanisms"][-1]
assert added == {"id": "function-call", "label": "function call",
                 "kind": "syntax-form", "owner": "s01.l01"}
assert "function-call" in expanded["sections"][0]["nodes"][0]["introduces"]
assert "function-call" in expanded["sections"][0]["nodes"][1]["mechanisms"]
future_course = json.loads(json.dumps(course))
future_course["sections"].append({
    "id": "s02", "nodes": [
        {"id": "s02.l01", "kind": "lesson", "introduces": ["function-call"]},
        {"id": "s02.working", "kind": "working", "mechanisms": ["function-call"]}],
})
future_course["mechanismContract"]["mechanisms"].append({
    "id": "function-call", "label": "function call", "kind": "syntax-form",
    "owner": "s02.l01"})
late_collision = {**finding, "id": "invoke-function",
                  "closestExisting": ["function-call"]}
try:
    candidate_with_findings(future_course, "s01", [late_collision])
except ValueError as exc:
    assert "sealed future mechanism" in str(exc)
else:
    raise AssertionError("future-neighbor mechanism was auto-added ahead of its owner")

with tempfile.TemporaryDirectory() as root:
    old_build = prerequisite_review.BUILD_DIR
    old_failure_root = prerequisite_review.VALIDATOR_FAILURE_DIR
    prerequisite_review.BUILD_DIR = root
    prerequisite_review.VALIDATOR_FAILURE_DIR = os.path.join(root, "validator-failures")
    try:
        with open(os.path.join(root, "demo.launch.json"), "w", encoding="utf-8") as handle:
            json.dump({"author": {"kind": "codex-cli", "model": "legacy"},
                       "validator": {"kind": "claude-cli", "model": "audit"},
                       "authors": {
                           "phase12": {"kind": "claude-cli", "model": "arc"},
                           "phase37": {"kind": "codex-cli", "model": "sections"},
                           "phase8": {"kind": "opencode-cli", "model": "finish"}},
                       "gate": {"prior_level": "2", "prior_knowledge": "names and literals"}},
                      handle)
        assert prerequisite_review._configuration("demo")[1]["model"] == "audit"
        sources = [{"path": "tomes/demo/sections/s01/lessons/l01.toml", "node": "s01.l01"},
                   {"path": "tomes/demo/sections/s01/freestyle.toml", "node": "s01.working"}]
        calls = []
        def adapter(prompt, _reviewer):
            calls.append(prompt)
            return {"outcome": "PASS", "citations": sources,
                    "reasons": ["Every required mechanism has complete first-use evidence."],
                    "missingMechanisms": []}
        with patch.object(prerequisite_review, "load_course_map", return_value=course), \
                patch.object(prerequisite_review, "section_evidence_packet",
                             return_value=("bounded packet", sources)):
            first = prerequisite_review.review_prerequisites("demo", "s01", adapter=adapter)
            second = prerequisite_review.review_prerequisites("demo", "s01", adapter=adapter)
        assert first["status"] == "PASS" and not first["cached"]
        assert second["status"] == "PASS" and second["cached"]
        assert len(calls) == 1
        assert not os.path.exists(prerequisite_review.validator_failure_dir("demo"))
        assert "Start is 2/3 (MODERATE DENSITY)" in calls[0]
        assert "one major concept family per lesson" in calls[0]
        assert "Lesson Depth controls explanatory thoroughness" in calls[0]
        assert "observable-interaction" in calls[0]
        assert "does not own the operations that interpret or act" in " ".join(calls[0].split())
        assert "one transferable semantic responsibility, not one surface spelling" in calls[0]
        assert "They do not get separate owners merely because their tokens differ" in calls[0]
        assert "demands is ALWAYS a JSON ARRAY" in calls[0]
        assert '"demands":["s01.l01","s01.working"]' in calls[0]
        assert '"closestExisting":["nearest-sealed-mechanism"]' in calls[0]

        # An evidence-backed FAIL is actionable even when optional amendment
        # metadata is malformed. The author gets its reasons; no retry or Terra call occurs.
        os.remove(prerequisite_review.result_path("demo", "s01"))
        os.remove(prerequisite_review.calls_path("demo"))
        with open(os.path.join(root, "demo.launch.json"), "w", encoding="utf-8") as handle:
            json.dump({"validator": {"kind": "codex-cli", "model": "gpt-5.6-luna",
                                      "effort": "medium"},
                       "gate": {"prior_level": "2", "prior_knowledge": "names and literals"}},
                      handle)
        routed = []
        def actionable_malformed(_prompt, reviewer):
            routed.append(reviewer["model"])
            finding = {"id": "function-call", "label": "function call",
                       "kind": "syntax-form", "owner": "s01.l01",
                       "closestExisting": ["broad-capability-not-a-mechanism"],
                       "semanticDelta": "Calling existing behavior is distinct from defining it.",
                       "demands": ["s01.l01", "s01.working"]}
            return {"outcome": "FAIL", "citations": sources,
                    "reasons": ["A definitive audit finding."],
                    "missingMechanisms": [finding]}
        trace = io.StringIO()
        with redirect_stdout(trace), \
                patch.object(prerequisite_review, "load_course_map", return_value=course), \
                patch.object(prerequisite_review, "section_evidence_packet",
                             return_value=("bounded packet", sources)):
            actionable = prerequisite_review.review_prerequisites(
                "demo", "s01", adapter=actionable_malformed)
        assert actionable["status"] == "FAIL"
        assert actionable["reasons"] == ["A definitive audit finding."]
        assert actionable["missingMechanisms"] == []
        assert routed == ["gpt-5.6-luna"]
        trace_lines = [line for line in trace.getvalue().splitlines()
                       if line.startswith("AI VALIDATOR CALL")]
        assert len(trace_lines) == 2 and "CALL START" in trace_lines[0]
        assert "CALL COMPLETE" in trace_lines[1] and "(FAIL)" in trace_lines[1]
        with open(prerequisite_review.calls_path("demo"), encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle]
        assert len(rows) == 1 and rows[0]["malformed"] is True
        assert rows[0]["contract"] == prerequisite_review.AUDIT_CONTRACT_VERSION
        failure_files = sorted(os.listdir(prerequisite_review.validator_failure_dir("demo")))
        assert len(failure_files) == 1
        with open(os.path.join(prerequisite_review.validator_failure_dir("demo"),
                               failure_files[0]), encoding="utf-8") as handle:
            archived = json.load(handle)
        assert archived["stage"] == "audit" and archived["malformed"] is True
        assert archived["recordedAt"].endswith("Z") and archived["blockerSignature"]

        # A malformed PASS is not safe. Luna gets one precise schema repair prompt.
        os.remove(prerequisite_review.result_path("demo", "s01"))
        os.remove(prerequisite_review.calls_path("demo"))
        routed, prompts = [], []
        def malformed_pass_then_repaired(prompt, reviewer):
            routed.append(reviewer["model"])
            prompts.append(prompt)
            value = {"outcome": "PASS", "citations": sources,
                     "reasons": ["All sealed nodes are complete."], "missingMechanisms": []}
            if "FORMAT CORRECTION RETRY" not in prompt:
                value["unexpected"] = True
            return value
        trace = io.StringIO()
        with redirect_stdout(trace), \
                patch.object(prerequisite_review, "load_course_map", return_value=course), \
                patch.object(prerequisite_review, "section_evidence_packet",
                             return_value=("repair packet", sources)):
            repaired = prerequisite_review.review_prerequisites(
                "demo", "s01", adapter=malformed_pass_then_repaired)
        assert repaired["status"] == "PASS"
        assert routed == ["gpt-5.6-luna", "gpt-5.6-luna"]
        assert "MECHANICAL ERRORS TO CORRECT" in prompts[1]
        assert '"function-definition"' in prompts[1]
        trace_lines = [line for line in trace.getvalue().splitlines()
                       if line.startswith("AI VALIDATOR CALL")]
        assert len(trace_lines) == 2 and "CALL START" in trace_lines[0]
        assert "CALL COMPLETE" in trace_lines[1] and "(PASS)" in trace_lines[1]

        # A prior definitive Luna failure must never turn a later definitive
        # Luna failure into an escalation merely because it is repeated.
        os.remove(prerequisite_review.result_path("demo", "s01"))
        routed = []
        def definitive_fail(_prompt, reviewer):
            routed.append(reviewer["model"])
            return {"outcome": "FAIL", "citations": sources,
                    "reasons": ["The sealed mechanism exists but its teaching is incomplete."],
                    "missingMechanisms": []}
        with patch.object(prerequisite_review, "load_course_map", return_value=course), \
                patch.object(prerequisite_review, "section_evidence_packet",
                             return_value=("changed bounded packet", sources)):
            definitive = prerequisite_review.review_prerequisites(
                "demo", "s01", adapter=definitive_fail)
        assert definitive["status"] == "FAIL"
        assert routed == ["gpt-5.6-luna"]
        assert len(os.listdir(prerequisite_review.validator_failure_dir("demo"))) == 3

        # Luna is the cheap first pass. Uncertainty escalates exactly once to Terra,
        # with no author/tool session involved in either test adapter invocation.
        os.remove(prerequisite_review.result_path("demo", "s01"))
        os.remove(prerequisite_review.calls_path("demo"))
        with open(os.path.join(root, "demo.launch.json"), "w", encoding="utf-8") as handle:
            json.dump({"validator": {"kind": "codex-cli", "model": "gpt-5.6-luna",
                                      "effort": "medium"},
                       "gate": {"prior_level": "2", "prior_knowledge": "names and literals"}},
                      handle)
        routed = []
        def uncertain_then_terra(_prompt, reviewer):
            routed.append(reviewer["model"])
            outcome = "UNCERTAIN" if "luna" in reviewer["model"] else "PASS"
            return {"outcome": outcome, "citations": sources,
                    "reasons": ["Escalation fixture."], "missingMechanisms": []}
        trace = io.StringIO()
        with redirect_stdout(trace), \
                patch.object(prerequisite_review, "load_course_map", return_value=course), \
                patch.object(prerequisite_review, "section_evidence_packet",
                             return_value=("bounded packet", sources)):
            escalated = prerequisite_review.review_prerequisites(
                "demo", "s01", adapter=uncertain_then_terra)
        assert escalated["status"] == "PASS"
        assert routed == ["gpt-5.6-luna", "gpt-5.6-terra"]
        assert len(os.listdir(prerequisite_review.validator_failure_dir("demo"))) == 4
        trace_lines = [line for line in trace.getvalue().splitlines()
                       if line.startswith("AI VALIDATOR CALL")]
        assert len(trace_lines) == 2 and "CALL START" in trace_lines[0]
        assert "CALL COMPLETE" in trace_lines[1] and "(PASS)" in trace_lines[1]
        assert "after Luna UNCERTAIN" in trace.getvalue()
        archived_statuses = []
        for name in os.listdir(prerequisite_review.validator_failure_dir("demo")):
            with open(os.path.join(prerequisite_review.validator_failure_dir("demo"), name),
                      encoding="utf-8") as handle:
                archived_statuses.append(json.load(handle)["status"])
        assert "UNCERTAIN" in archived_statuses

        # Provider/transport failures have no verdict, but they are still one
        # validator failure and must receive their own timestamped record.
        os.remove(prerequisite_review.result_path("demo", "s01"))
        os.remove(prerequisite_review.calls_path("demo"))
        def infrastructure_failure(_prompt, _reviewer):
            raise RuntimeError("simulated validator transport failure")
        try:
            with patch.object(prerequisite_review, "load_course_map", return_value=course), \
                    patch.object(prerequisite_review, "section_evidence_packet",
                                 return_value=("bounded packet", sources)):
                prerequisite_review.review_prerequisites(
                    "demo", "s01", adapter=infrastructure_failure)
        except RuntimeError as exc:
            assert "infrastructure failed" in str(exc)
        else:
            raise AssertionError("validator infrastructure failure was not surfaced")
        assert len(os.listdir(prerequisite_review.validator_failure_dir("demo"))) == 5
        with open(prerequisite_review.calls_path("demo"), encoding="utf-8") as handle:
            infrastructure_row = json.loads(handle.read())
        assert infrastructure_row["status"] == "ERROR"
        assert infrastructure_row["infrastructure"] is True

        # The direct API request has no tools or Flex routing, uses Structured Output,
        # and places the stable policy before the dynamic section packet.
        response_value = {
            "id": "resp_test", "output_text": json.dumps({
                "outcome": "PASS", "citations": sources, "reasons": ["clean"],
                "missingMechanisms": []}),
            "usage": {"input_tokens": 1200, "input_tokens_details": {
                "cached_tokens": 800, "cache_write_tokens": 200},
                "output_tokens": 40, "output_tokens_details": {"reasoning_tokens": 12},
                "total_tokens": 1240},
        }
        captured = {}
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self): return json.dumps(response_value).encode("utf-8")
        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data)
            captured["timeout"] = timeout
            return FakeResponse()
        api_prompt = prerequisite_review._prompt(
            "packet", "s01", sources, "names and literals", 2)
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), \
                patch.object(urllib.request, "urlopen", side_effect=fake_urlopen):
            _raw, meta = prerequisite_review._api_adapter(
                api_prompt, {"kind": "codex-cli", "model": "gpt-5.6-luna",
                             "effort": "medium"})
        payload = captured["payload"]
        assert "tools" not in payload and "service_tier" not in payload
        assert payload["text"]["format"]["type"] == "json_schema"
        assert payload["text"]["format"]["strict"] is True
        assert payload["input"][0]["role"] == "developer"
        assert payload["input"][1]["role"] == "user"
        assert payload["prompt_cache_options"] == {"mode": "explicit"}
        assert meta["usage"] == {"inputTokens": 1200, "freshInputTokens": 200,
                                  "cachedInputTokens": 800, "cacheWriteTokens": 200, "outputTokens": 40,
                                  "reasoningTokens": 12, "totalTokens": 1240}
    finally:
        prerequisite_review.BUILD_DIR = old_build
        prerequisite_review.VALIDATOR_FAILURE_DIR = old_failure_root

print("prerequisite mechanism/audit tests: OK")
