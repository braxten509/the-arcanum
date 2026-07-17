#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""Mechanism ordering, demand union, and cached prerequisite-review policy."""
import json
import os
import sys
import tempfile
import urllib.request
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from buildlib.mechanism_contract import authored_problems, validate_map_contract
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
                 "exercises": [{"mechanisms": ["function-definition"]}],
                 "artifactSteps": [{"mechanisms": ["function-definition"]}]}],
    "freestyle": {"mechanisms": ["function-definition"],
                  "rubric": [{"mechanisms": ["function-definition"]}],
                  "referenceSteps": [{"mechanisms": ["function-definition"]}]},
    "proof": {"mechanisms": []},
}
assert not authored_problems(course, actual, "s01")
missing_demand = json.loads(json.dumps(actual))
missing_demand["freestyle"]["rubric"][0]["mechanisms"] = []
missing_demand["freestyle"]["referenceSteps"][0]["mechanisms"] = []
assert any("exactly equal the union" in item for item in
           authored_problems(course, missing_demand, "s01"))

with tempfile.TemporaryDirectory() as root:
    old_build = prerequisite_review.BUILD_DIR
    prerequisite_review.BUILD_DIR = root
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
        assert "Start is 2/3 (MODERATE DENSITY)" in calls[0]
        assert "one major concept family per lesson" in calls[0]
        assert "Lesson Depth controls explanatory thoroughness" in calls[0]
        assert "observable-interaction" in calls[0]
        assert "does not own the operations that interpret or act" in " ".join(calls[0].split())
        assert "demands is ALWAYS a JSON ARRAY" in calls[0]
        assert '"demands":["s01.l01","s01.working"]' in calls[0]

        # A weak provider that returns a definitive verdict with string-valued
        # demands gets one provider-neutral format prompt before any escalation.
        os.remove(prerequisite_review.result_path("demo", "s01"))
        os.remove(prerequisite_review.calls_path("demo"))
        with open(os.path.join(root, "demo.launch.json"), "w", encoding="utf-8") as handle:
            json.dump({"validator": {"kind": "codex-cli", "model": "gpt-5.6-luna",
                                      "effort": "medium"},
                       "gate": {"prior_level": "2", "prior_knowledge": "names and literals"}},
                      handle)
        routed = []
        def malformed_then_repaired(prompt, reviewer):
            routed.append(reviewer["model"])
            finding = {"id": "function-definition", "label": "function definition",
                       "kind": "syntax-form", "owner": "s01.l01",
                       "demands": (["s01.l01", "s01.working"]
                                   if "FORMAT CORRECTION RETRY" in prompt
                                   else "s01.l01 and the Working")}
            return {"outcome": "FAIL", "citations": sources,
                    "reasons": ["A definitive audit finding."],
                    "missingMechanisms": [finding]}
        with patch.object(prerequisite_review, "load_course_map", return_value=course), \
                patch.object(prerequisite_review, "section_evidence_packet",
                             return_value=("bounded packet", sources)):
            repaired = prerequisite_review.review_prerequisites(
                "demo", "s01", adapter=malformed_then_repaired)
        assert repaired["status"] == "FAIL"
        assert repaired["missingMechanisms"][0]["demands"] == ["s01.l01", "s01.working"]
        assert routed == ["gpt-5.6-luna", "gpt-5.6-luna"]
        with open(prerequisite_review.calls_path("demo"), encoding="utf-8") as handle:
            repair_rows = [json.loads(line) for line in handle]
        assert repair_rows[0]["malformed"] is True
        assert repair_rows[0]["contract"] == prerequisite_review.AUDIT_CONTRACT_VERSION
        assert "malformed" not in repair_rows[1]

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
        with patch.object(prerequisite_review, "load_course_map", return_value=course), \
                patch.object(prerequisite_review, "section_evidence_packet",
                             return_value=("bounded packet", sources)):
            escalated = prerequisite_review.review_prerequisites(
                "demo", "s01", adapter=uncertain_then_terra)
        assert escalated["status"] == "PASS"
        assert routed == ["gpt-5.6-luna", "gpt-5.6-terra"]

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

print("prerequisite mechanism/audit tests: OK")
