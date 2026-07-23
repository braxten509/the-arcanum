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
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from buildlib.mechanism_contract import (authored_problems, candidate_with_findings,
                                         validate_map_contract)
from buildlib.prerequisites import review as prerequisite_review
from buildlib.section_quality_contract import (SECTION_QUALITY_CONTRACT,
                                                section_quality_authority,
                                                section_quality_contract_packet)


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

cumulative_course = json.loads(json.dumps(course))
cumulative_course["sections"][0]["nodes"][1]["learnerOwnedArtifacts"] = ["src/main.ext"]
cumulative_course["sections"].append({
    "id": "s02", "nodes": [
        {"id": "s02.l01", "kind": "lesson", "introduces": []},
        {"id": "s02.working", "kind": "working", "mechanisms": [],
         "learnerOwnedArtifacts": ["src/main.ext"]},
    ],
})
cumulative_positions = {
    "s01": (0, -1), "s01.l01": (0, 0), "s01.working": (0, 1),
    "s02": (1, -1), "s02.l01": (1, 0), "s02.working": (1, 1),
}
cumulative_problems = validate_map_contract(
    cumulative_course, cumulative_course["sections"], cumulative_positions,
    detailed=True, map_version=4)
assert any("omits their cumulative Working mechanisms" in item
           and "function-definition" in item for item in cumulative_problems)
cumulative_course["sections"][1]["nodes"][1]["mechanisms"] = ["function-definition"]
assert not validate_map_contract(
    cumulative_course, cumulative_course["sections"], cumulative_positions,
    detailed=True, map_version=4)
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

# The Validator AI packet includes the same section-local receipts and deterministic
# scenarios that the mechanical hardened-evidence gate checks.
with tempfile.TemporaryDirectory() as packet_root:
    packet_section = os.path.join(packet_root, "tomes", "demo", "sections", "s01")
    os.makedirs(os.path.join(packet_section, "lessons"))
    for relative, text in (
            ("lessons/l01.toml", "[[lessons]]\nid = \"s01-l01\"\n"),
            ("freestyle.toml", "[freestyle]\ntitle = \"Working\"\n"),
            ("research.toml", "version = 1\n"),
            ("assessment.toml", "version = 1\n")):
        with open(os.path.join(packet_section, relative), "w", encoding="utf-8") as handle:
            handle.write(text)
    old_repo = prerequisite_review.REPO
    prerequisite_review.REPO = packet_root
    try:
        with patch.object(prerequisite_review, "_context", return_value="demo"), \
                patch.object(prerequisite_review, "load_course_map", return_value=course):
            packet, packet_sources = prerequisite_review.section_evidence_packet(
                "demo", course["sections"][0])
    finally:
        prerequisite_review.REPO = old_repo
    packet_paths = {item["path"] for item in packet_sources}
    assert "tomes/demo/sections/s01/research.toml" in packet_paths
    assert "tomes/demo/sections/s01/assessment.toml" in packet_paths
    assert "SECTION RESEARCH RECEIPTS" in packet
    assert "WORKING DETERMINISTIC SCENARIOS" in packet

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
                       "gate": {"prior_level": "2", "prior_knowledge": "names and literals",
                                "depth": "7", "mastery": "3"}},
                      handle)
        assert prerequisite_review._configuration("demo")[1]["model"] == "audit"
        sources = [{"path": "tomes/demo/sections/s01/lessons/l01.toml", "node": "s01.l01"},
                   {"path": "tomes/demo/sections/s01/freestyle.toml", "node": "s01.working"}]
        citations = [{"path": item["path"], "node": item["node"]} for item in sources]
        def audit_result(outcome="PASS", reasons=None, missing=None, quality=None):
            quality = list(quality or [])
            failed = {(item["path"], item["node"]) for item in quality}
            return {
                "outcome": outcome, "citations": citations,
                "reasons": list(reasons or ["Every node has concrete teaching and practice evidence."]),
                "missingMechanisms": list(missing or []),
                "nodeReviews": [{
                    "path": item["path"], "node": item["node"],
                    "judgment": "FAIL" if (item["path"], item["node"]) in failed else "PASS",
                    "evidenceLines": [1, 1],
                    "evidence": "Concrete teaching and independent practice appear in this source.",
                } for item in sources],
                "qualityFindings": quality,
            }
        bounded_sources = [{**item, "lineCount": 5} for item in sources]
        # Plain PASS and FAIL prose are both usable; neither spends another call merely
        # to satisfy a response envelope.
        _parsed, _errors, readable_text_fail = prerequisite_review._classify_output(
            "verdict: FAIL\nsummary: The cited lesson omits an actionable prerequisite.",
            bounded_sources, "s01", {"function-definition"})
        assert readable_text_fail.result["status"] == "FAIL"
        assert not readable_text_fail.unusable
        _parsed, _errors, unsupported_text_pass = prerequisite_review._classify_output(
            "verdict: PASS\nsummary: Everything appears complete.",
            bounded_sources, "s01", {"function-definition"})
        assert unsupported_text_pass.result["status"] == "PASS"
        assert not unsupported_text_pass.unusable
        incomplete_pass = audit_result()
        incomplete_pass["nodeReviews"] = incomplete_pass["nodeReviews"][:-1]
        rejected, errors = prerequisite_review._validate_detailed(
            incomplete_pass, bounded_sources, "s01", {"function-definition"})
        assert rejected["status"] == "FAIL"
        assert any("exactly one row" in error for error in errors)

        shallow = [{
            "path": sources[0]["path"], "node": sources[0]["node"],
            "category": "practice-quality", "evidenceLines": [2, 4],
            "evidence": "The prompt reproduces the complete worked answer from the lesson.",
            "requiredRepair": "Replace it with a different-context construction or debugging task.",
        }]
        quality_fail, errors = prerequisite_review._validate_detailed(
            audit_result("FAIL", ["Independent practice is missing."], quality=shallow),
            bounded_sources, "s01", {"function-definition"})
        assert not errors and quality_fail["status"] == "FAIL"
        assert quality_fail["qualityFindings"][0]["category"] == "practice-quality"
        wrapped_pass, errors = prerequisite_review._validate_detailed(
            "Result follows:\n```json\n" + json.dumps(audit_result()) + "\n```",
            bounded_sources, "s01", {"function-definition"})
        assert not errors and wrapped_pass["status"] == "PASS"
        calls = []
        def adapter(prompt, _reviewer):
            calls.append(prompt)
            return audit_result()
        with patch.object(prerequisite_review, "load_course_map", return_value=course), \
                patch.object(prerequisite_review, "section_evidence_packet",
                             return_value=("bounded packet", sources)):
            first = prerequisite_review.review_prerequisites("demo", "s01", adapter=adapter)
            second = prerequisite_review.review_prerequisites("demo", "s01", adapter=adapter)
        assert first["status"] == "PASS" and not first["cached"]
        assert second["status"] == "PASS" and second["cached"]
        assert len(calls) == 1
        assert not os.path.exists(prerequisite_review.validator_failure_dir("demo"))
        assert "Start is 2/10 (MODERATE DENSITY)" in calls[0]
        assert "LESSON DEPTH: 7/10" in calls[0]
        assert "LANGUAGE MASTERY: 3/5" in calls[0]
        assert "one major concept family per lesson" in calls[0]
        normalized_prompt = " ".join(calls[0].split())
        assert "Lesson Depth controls explanatory thoroughness" in normalized_prompt
        assert "observable-interaction" in calls[0]
        assert "does not own the operations that interpret or act" in " ".join(calls[0].split())
        assert "one transferable semantic responsibility, not one surface spelling" in calls[0]
        assert "They do not get separate owners merely because their tokens differ" in normalized_prompt
        assert "demands is ALWAYS a JSON ARRAY" in calls[0]
        assert '"demands":["s01.l01","s01.working"]' in calls[0]
        assert '"closestExisting":["nearest-sealed-mechanism"]' in calls[0]
        assert "copying a lesson example" in calls[0]
        assert "The Liber Veritatis" in calls[0]
        assert "one review for every VALID SOURCE/NODE PAIR" in calls[0]
        assert "fixed 2,500-output-token validator budget" in calls[0]
        assert SECTION_QUALITY_CONTRACT in calls[0]
        assert "mechanisms co-owned by the same sealed lesson" in calls[0]
        assert "Do not reclassify them as separate families" in calls[0]
        assert "copied verbatim from nearby prose or code is not independent" in calls[0]
        assert "whole-section coverage sweep" in calls[0]
        assert "all five facts" in calls[0]
        assert "clean mechanical gate as semantic evidence" in calls[0]
        assert "HARDENED SOURCE AND ADVERSARIAL EVIDENCE" in calls[0]
        assert ("at least two distinct non-build deterministic scenarios"
                in " ".join(calls[0].split()))
        shared_authority = section_quality_authority(2, "names and literals", 7, 3)
        assert calls[0].count(shared_authority) == 1
        assert prerequisite_review.section_policy_fingerprint(
            2, "names and literals", 7, 3) != prerequisite_review.section_policy_fingerprint(
                2, "names and literals", 8, 3)
        assert section_quality_contract_packet() == {
            "version": 4,
            "text": SECTION_QUALITY_CONTRACT,
            "settings": {"start": 0, "prior": "", "depth": 0, "mastery": 0},
            "authorityText": section_quality_authority(),
        }

        # The quality audit is mandatory above the beginner prerequisite-pacing range too.
        with open(os.path.join(root, "advanced.launch.json"), "w", encoding="utf-8") as handle:
            json.dump({"validator": {"kind": "claude-cli", "model": "audit"},
                       "gate": {"prior_level": "7", "prior_knowledge": "routine fundamentals",
                                "depth": "8", "mastery": "4"}}, handle)
        advanced_calls = []
        def advanced_adapter(prompt, _reviewer):
            advanced_calls.append(prompt)
            return audit_result()
        with patch.object(prerequisite_review, "load_course_map", return_value=course), \
                patch.object(prerequisite_review, "section_evidence_packet",
                             return_value=("bounded packet", sources)):
            advanced = prerequisite_review.review_prerequisites(
                "advanced", "s01", adapter=advanced_adapter)
        assert advanced["status"] == "PASS" and len(advanced_calls) == 1
        assert "Start is 7/10 (PRIOR-KNOWLEDGE CALIBRATED)" in advanced_calls[0]

        # An evidence-backed FAIL is actionable even when optional amendment metadata
        # cannot be extracted. The author gets its prose; no retry or model switch occurs.
        os.remove(prerequisite_review.result_path("demo", "s01"))
        os.remove(prerequisite_review.calls_path("demo"))
        with open(os.path.join(root, "demo.launch.json"), "w", encoding="utf-8") as handle:
            json.dump({"validator": {"kind": "codex-cli", "model": "gpt-5.6-luna",
                                      "effort": "medium"},
                       "gate": {"prior_level": "2", "prior_knowledge": "names and literals"}},
                      handle)
        routed = []
        def actionable_form_free(_prompt, reviewer):
            routed.append(reviewer["model"])
            finding = {"id": "function-call", "label": "function call",
                       "kind": "syntax-form", "owner": "s01.l01",
                       "closestExisting": ["broad-capability-not-a-mechanism"],
                       "semanticDelta": "Calling existing behavior is distinct from defining it.",
                       "demands": ["s01.l01", "s01.working"]}
            return {"verdict": "FAIL", "citations": sources,
                    "summary": "A definitive audit finding.",
                    "missingMechanisms": [finding]}
        trace = io.StringIO()
        with redirect_stdout(trace), \
                patch.object(prerequisite_review, "load_course_map", return_value=course), \
                patch.object(prerequisite_review, "section_evidence_packet",
                             return_value=("bounded packet", sources)):
            actionable = prerequisite_review.review_prerequisites(
                "demo", "s01", adapter=actionable_form_free)
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
        assert len(rows) == 1 and not rows[0].get("malformed", False)
        assert rows[0]["contract"] == prerequisite_review.AUDIT_CONTRACT_VERSION
        failure_files = sorted(os.listdir(prerequisite_review.validator_failure_dir("demo")))
        assert len(failure_files) == 1
        with open(os.path.join(prerequisite_review.validator_failure_dir("demo"),
                               failure_files[0]), encoding="utf-8") as handle:
            archived = json.load(handle)
        assert archived["stage"] == "audit" and not archived.get("malformed", False)
        assert archived["recordedAt"].endswith("Z") and archived["blockerSignature"]

        # A readable PASS needs no normalization or second model call.
        os.remove(prerequisite_review.result_path("demo", "s01"))
        os.remove(prerequisite_review.calls_path("demo"))
        routed, prompts = [], []
        def readable_form_free_pass(prompt, reviewer):
            routed.append(reviewer["model"])
            prompts.append(prompt)
            value = audit_result(reasons=["All sealed nodes are complete."])
            value["status"] = value.pop("outcome")
            value["summary"] = value.pop("reasons")[0]
            for review in value["nodeReviews"]:
                review["verdict"] = review.pop("judgment")
                review["lines"] = "1-1"
                review.pop("evidenceLines")
            value["unexpected"] = True
            return value
        trace = io.StringIO()
        with redirect_stdout(trace), \
                patch.object(prerequisite_review, "load_course_map", return_value=course), \
                patch.object(prerequisite_review, "section_evidence_packet",
                             return_value=("repair packet", sources)):
            repaired = prerequisite_review.review_prerequisites(
                "demo", "s01", adapter=readable_form_free_pass)
        assert repaired["status"] == "PASS"
        assert routed == ["gpt-5.6-luna"]
        trace_lines = [line for line in trace.getvalue().splitlines()
                       if line.startswith("AI VALIDATOR CALL")]
        assert len(trace_lines) == 2 and "CALL START" in trace_lines[0]
        assert "CALL COMPLETE" in trace_lines[1] and "(PASS)" in trace_lines[1]
        with open(prerequisite_review.calls_path("demo"), encoding="utf-8") as handle:
            pass_row = json.loads(handle.read())
        assert pass_row["status"] == "PASS" and not pass_row.get("malformed", False)

        # A PASS that files its own actionable repairs contradicts itself. Take the repairs and
        # fail: a defect the model called non-blocking is still a defect worth fixing, and a
        # second call would only return the findings already in hand.
        os.remove(prerequisite_review.result_path("demo", "s01"))
        os.remove(prerequisite_review.calls_path("demo"))
        routed = []
        def contradicted_pass(_prompt, reviewer):
            routed.append(reviewer["model"])
            value = audit_result(quality=[{
                "path": sources[0]["path"], "node": sources[0]["node"],
                "category": "teaching-depth", "evidenceLines": [1, 1],
                "evidence": "The mechanism is named but its failure path is not explained.",
                "requiredRepair": "Add the observable failure, diagnosis, and guided recovery.",
            }])
            for review in value["nodeReviews"]:
                review["judgment"] = "PASS"  # the contradiction: repairs filed, every node clean
            return value
        with redirect_stdout(io.StringIO()), \
                patch.object(prerequisite_review, "load_course_map", return_value=course), \
                patch.object(prerequisite_review, "section_evidence_packet",
                             return_value=("repair packet", sources)):
            contradicted = prerequisite_review.review_prerequisites(
                "demo", "s01", adapter=contradicted_pass)
        assert contradicted["status"] == "FAIL"
        assert routed == ["gpt-5.6-luna"], "a self-contradicting PASS must not spend a retry"
        assert len(contradicted["qualityFindings"]) == 1, "the filed repair was dropped"

        # A prior definitive Luna failure must never turn a later definitive
        # Luna failure into an escalation merely because it is repeated.
        os.remove(prerequisite_review.result_path("demo", "s01"))
        routed = []
        def definitive_fail(_prompt, reviewer):
            routed.append(reviewer["model"])
            quality = [{
                "path": sources[0]["path"], "node": sources[0]["node"],
                "category": "teaching-depth", "evidenceLines": [1, 1],
                "evidence": "The mechanism is named but its failure path is not explained.",
                "requiredRepair": "Add the observable failure, diagnosis, and guided recovery practice.",
            }]
            return audit_result(
                "FAIL", ["The sealed mechanism exists but its teaching is incomplete."],
                quality=quality)
        with patch.object(prerequisite_review, "load_course_map", return_value=course), \
                patch.object(prerequisite_review, "section_evidence_packet",
                             return_value=("changed bounded packet", sources)):
            definitive = prerequisite_review.review_prerequisites(
                "demo", "s01", adapter=definitive_fail)
        assert definitive["status"] == "FAIL"
        assert routed == ["gpt-5.6-luna"]
        assert len(os.listdir(prerequisite_review.validator_failure_dir("demo"))) == 3

        # Plain prose and ambiguity are readable FAIL packets. They never buy a
        # formatting retry or a call to another model.
        os.remove(prerequisite_review.result_path("demo", "s01"))
        os.remove(prerequisite_review.calls_path("demo"))
        with open(os.path.join(root, "demo.launch.json"), "w", encoding="utf-8") as handle:
            json.dump({"validator": {"kind": "codex-cli", "model": "gpt-5.6-luna",
                                      "effort": "medium"},
                       "gate": {"prior_level": "2", "prior_knowledge": "names and literals"}},
                      handle)
        routed = []
        def ambiguous_validator(_prompt, reviewer):
            routed.append(reviewer["model"])
            return "I cannot verify the cleanup path. Add explicit cleanup teaching."
        trace = io.StringIO()
        with redirect_stdout(trace), \
                patch.object(prerequisite_review, "load_course_map", return_value=course), \
                patch.object(prerequisite_review, "section_evidence_packet",
                             return_value=("bounded packet", sources)):
            ambiguous = prerequisite_review.review_prerequisites(
                "demo", "s01", adapter=ambiguous_validator)
        assert ambiguous["status"] == "FAIL"
        assert "cleanup path" in ambiguous["reasons"][0]
        assert routed == ["gpt-5.6-luna"]
        assert len(os.listdir(prerequisite_review.validator_failure_dir("demo"))) == 4
        trace_lines = [line for line in trace.getvalue().splitlines()
                       if line.startswith("AI VALIDATOR CALL")]
        assert len(trace_lines) == 2
        assert "CALL START" in trace_lines[0]
        assert "CALL COMPLETE" in trace_lines[1] and "(FAIL)" in trace_lines[1]
        archived_statuses = []
        for name in os.listdir(prerequisite_review.validator_failure_dir("demo")):
            with open(os.path.join(prerequisite_review.validator_failure_dir("demo"), name),
                      encoding="utf-8") as handle:
                archived_statuses.append(json.load(handle)["status"])
        assert "FAIL" in archived_statuses
        assert os.path.exists(prerequisite_review.result_path("demo", "s01"))

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

        # Production section validators are deliberately CLI-only so their read-only
        # permission profile and isolated unit state are always applied.
        api_prompt = prerequisite_review._prompt(
            "packet", "s01", sources, "names and literals", 2)
        try:
            prerequisite_review._invoke(
                api_prompt, {"kind": "openai-api", "model": "gpt-5.6-luna",
                             "effort": "medium"}, None)
        except RuntimeError as exc:
            assert "must use Claude CLI or Codex CLI" in str(exc)
        else:
            raise AssertionError("section validator accepted an unscoped direct API transport")
    finally:
        prerequisite_review.BUILD_DIR = old_build
        prerequisite_review.VALIDATOR_FAILURE_DIR = old_failure_root

print("section quality/prerequisite audit tests: OK")
