#!/usr/bin/env python3
"""Phase 1 and 2 planning reviews use useful Markdown, never a response schema."""
import json
import os
import sys
import tempfile
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from tools.buildlib import ai_costs
from tools.buildlib import planning_review
from tools.buildlib.prerequisites import records as review_records
from tools.buildlib.prerequisites import transport as validator_transport


def audit_report(phase, sources, outcome="PASS", fail_criterion=""):
    """Return deliberately unstructured Markdown with no machine field names."""
    citation_path = next(source["path"] for source in sources
                         if source["repairable"])
    final = "FAIL" if fail_criterion else outcome
    paragraphs = [
        f"{final} — I reviewed the complete bounded Phase {phase} evidence and the "
        "judgment below explains the planning quality in enough detail for the author.",
    ]
    for criterion, _description in planning_review.PHASE_CRITERIA[phase]:
        if criterion == fail_criterion:
            paragraphs.append(
                f"{criterion} does not yet pass. `{citation_path}:1-1` leaves the "
                "dependency ambiguous. Repair only that statement so the route teaches "
                "the prerequisite before it is demanded, while preserving clean work.")
        else:
            paragraphs.append(
                f"{criterion} is supported by `{citation_path}:1-1`, which keeps the "
                "declared learner route coherent and gives observable proof.")
    return "\n\n".join(paragraphs)


def remove_cached(build_id, phase):
    path = planning_review.result_path(build_id, phase)
    if os.path.exists(path):
        os.remove(path)


with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    failure_dir = os.path.join(root, "validator-failures")
    tome = os.path.join(root, "tomes", "course")
    runtimes = os.path.join(root, "global-configs", "runtimes")
    os.makedirs(build_dir)
    os.makedirs(tome)
    os.makedirs(runtimes)
    with open(os.path.join(build_dir, "demo.plan.md"), "w", encoding="utf-8") as handle:
        handle.write("## Arc\nA coherent project arc.\n")
    with open(os.path.join(build_dir, "demo.course-map.proposal.json"),
              "w", encoding="utf-8") as handle:
        json.dump({"version": 1, "sections": [{"id": "s01"}]}, handle, indent=2)
    author_root = os.path.join(build_dir, "demo.course-map-author")
    os.makedirs(os.path.join(author_root, "sections"))
    for name, value in (
            ("course.json", {"graduateCapabilities": [], "languageMastery": {"performances": []}}),
            ("mechanisms.json", {"mechanismContract": {"version": 1,
                                                        "coverageStart": "s01",
                                                        "mechanisms": []}}),
            ("obligations.json", {"plannedObligations": []}),
            ("audit.json", {"version": 1, "mechanisms": [],
                            "artifactProduction": []})):
        with open(os.path.join(author_root, name), "w", encoding="utf-8") as handle:
            json.dump(value, handle)
    with open(os.path.join(author_root, "sections", "s01.json"),
              "w", encoding="utf-8") as handle:
        json.dump({"capabilities": [], "languagePractice": [], "dependsOn": [],
                   "nodes": [], "projectMilestone": "demo"}, handle)
    with open(os.path.join(tome, "tome.toml"), "w", encoding="utf-8") as handle:
        handle.write(
            'id = "course"\nname = "Course"\n[content]\nsections = ["s01"]\n'
            '[runtime]\nname = "python"\n')
    os.makedirs(os.path.join(tome, "sections", "s01"))
    with open(os.path.join(tome, "sections", "s01", "section.toml"),
              "w", encoding="utf-8") as handle:
        handle.write(
            'id = "s01"\n[proof]\nmode = "package"\n'
            'requirementsFile = "requirements.txt"\nartifactPath = "dist/course.tar"\n')
    os.makedirs(os.path.join(tome, "sections", "s99"))
    with open(os.path.join(tome, "sections", "s99", "section.toml"),
              "w", encoding="utf-8") as handle:
        handle.write('id = "s99"\n[proof]\nmode = "guided"\n')
    with open(os.path.join(runtimes, "python.toml"), "w", encoding="utf-8") as handle:
        handle.write('name = "python"\ncommand = ["python3", "{file}"]\n')
    with open(os.path.join(build_dir, "demo.launch.json"), "w", encoding="utf-8") as handle:
        json.dump({
            "concept": "Teach one complete project",
            "validator": {"kind": "codex-cli", "model": "gpt-5.6-luna",
                          "effort": "medium"},
            "gate": {"prior_level": "2", "depth": "6", "mastery": "3",
                     "project_scope": "3"},
        }, handle)

    with patch.object(planning_review, "BUILD_DIR", build_dir), \
            patch.object(planning_review, "REPO", root), \
            patch.object(planning_review, "VALIDATOR_FAILURE_DIR", failure_dir):
        phase1_packet, phase1_sources = planning_review.phase_evidence_packet(
            "demo", 1, "course", {"concept": "Teach one complete project"})
        assert len(phase1_sources) == 1 and phase1_sources[0]["repairable"]
        assert "OPERATOR CALIBRATION" in phase1_packet
        assert ".tome-build/demo.plan.md" in phase1_packet

        calls = []

        def pass_adapter(prompt, validator):
            calls.append((prompt, validator["model"]))
            return audit_report(1, phase1_sources)

        first = planning_review.review_planning_phase(
            "demo", 1, "course", adapter=pass_adapter)
        second = planning_review.review_planning_phase(
            "demo", 1, "course", adapter=pass_adapter)
        assert first["status"] == "PASS" and not first["cached"]
        assert second["status"] == "PASS" and second["cached"]
        assert len(calls) == 1
        assert "ordinary Markdown prose, never JSON" in calls[0][0]
        assert "No heading, label, field name" in calls[0][0]
        assert "concept-alignment" in calls[0][0]
        assert "Semantic feasibility, prerequisite planning" in calls[0][0]
        assert "concrete tool-action ownership" not in calls[0][0]
        assert planning_review.DYNAMIC_MARKER in calls[0][0]

        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({
                    "id": "resp_phase_1",
                    "output_text": audit_report(1, phase1_sources),
                    "usage": {"input_tokens": 100, "output_tokens": 20,
                              "total_tokens": 120},
                }).encode("utf-8")

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResponse()

        phase1_review_prompt = planning_review.planning_prompt(
            1, phase1_packet, phase1_sources)
        assert phase1_review_prompt.count(planning_review.planning_authority(1)) == 1
        assert planning_review.planning_dynamic_authority(
            "demo", 1, {"concept": "Teach one complete project"},
            build_dir=build_dir) in phase1_review_prompt
        assert "runtime repair must never put a Makefile" in phase1_review_prompt
        assert "requirements field is not a generic source inventory" in phase1_review_prompt
        with patch.object(validator_transport, "_openai_key", return_value="test-key"), \
                patch.object(validator_transport.urllib.request, "urlopen",
                             side_effect=fake_urlopen):
            raw, api_meta = planning_review._invoke(
                phase1_review_prompt,
                {"kind": "openai-api", "model": "gpt-5.6-luna", "effort": "medium"},
                1)
        assert raw.startswith("PASS")
        assert api_meta["transport"] == "responses-api"
        assert captured["payload"]["text"] == {"verbosity": "low"}
        assert captured["payload"]["prompt_cache_key"] == "arcanum-phase-1-quality-v14"
        assert captured["payload"]["max_output_tokens"] == 2500
        assert "tools" not in captured["payload"]

        with open(review_records.calls_path(build_dir, "demo"),
                  encoding="utf-8") as handle:
            phase1_row = json.loads(handle.read())
        assert phase1_row["phase"] == 1
        assert phase1_row["unitKind"] == "phase"
        assert phase1_row["unit"] == "phase-1"
        assert phase1_row["auditKind"] == "planning"
        assert "section" not in phase1_row

        review_records.append_ai_call(
            build_dir, failure_dir, "accounting", "phase-2", "packet",
            {"status": "PASS", "reasons": ["clean"], "report": "PASS and clean"},
            {"transport": "responses-api", "kind": "openai-api",
             "model": "gpt-5.6-luna", "effort": "medium",
             "usage": {"inputTokens": 100, "freshInputTokens": 100,
                       "outputTokens": 20, "totalTokens": 120}},
            phase=2, unit_kind="phase", audit_kind="planning", contract=3)
        with open(ai_costs.turns_path(build_dir, "accounting"), encoding="utf-8") as handle:
            accounted = json.loads(handle.read())
        assert accounted["phase"] == 2 and accounted["role"] == "validator"
        assert "section" not in accounted

        phase2_packet, phase2_sources = planning_review.phase_evidence_packet(
            "demo", 2, "course", {"concept": "Teach one complete project"})
        assert len(phase2_sources) == 10
        plan_source = phase2_sources[0]
        assert not plan_source["repairable"]
        proposal_source = next(source for source in phase2_sources
                               if source["path"].endswith("course-map.proposal.json"))
        assert not proposal_source["repairable"]
        assert any(source["path"].endswith("course-map-author/audit.json")
                   and source["repairable"] for source in phase2_sources)
        assert any(source["path"].endswith("sections/s01/section.toml")
                   and source["repairable"] for source in phase2_sources)
        assert "course-map.proposal.json" in phase2_packet
        assert "course-map-author/audit.json" in phase2_packet
        assert "course-map-author/sections/s01.json" in phase2_packet
        assert "tomes/course/sections/s01/section.toml" in phase2_packet
        assert "tomes/course/sections/s99/section.toml" not in phase2_packet
        assert 'artifactPath = "dist/course.tar"' in phase2_packet
        assert "global-configs/runtimes/python.toml" in phase2_packet
        assert "HARNESS PHASE 2 AUTHORITY" in phase2_packet
        assert '"generated": "optional"' in phase2_packet
        assert '"allowedModes"' in phase2_packet
        assert "never forbid a production mode" in phase2_packet
        assert '"maximumSources": 6' in phase2_packet
        assert '"generatedProposalRepairable": false' in phase2_packet
        phase2_prompt = planning_review.planning_prompt(2, phase2_packet, phase2_sources)
        assert phase2_prompt.count(planning_review.planning_authority(2)) == 1
        assert planning_review.planning_dynamic_authority(
            "demo", 2, {"concept": "Teach one complete project"},
            build_dir=build_dir) in phase2_prompt
        repairable_line = next(line for line in phase2_prompt.splitlines()
                               if line.startswith("REPAIRABLE PATHS:"))
        assert plan_source["path"] not in repairable_line
        assert "prerequisite-order" in phase2_prompt
        assert "Learner-facing lessons are still intentional placeholders" in " ".join(
            phase2_prompt.split())
        assert "standaloneLabCount 0 requires no variant family" in " ".join(
            phase2_prompt.split())
        assert "A Working performance must retain an empty variantFamilyId" in " ".join(
            phase2_prompt.split())
        assert "not by requiring one lesson or one family per individual mechanism" in " ".join(
            phase2_prompt.split())
        assert "Do not demand distinct family labels merely because paired mechanisms" in " ".join(
            phase2_prompt.split())
        assert "a decision plus its displayed result" in " ".join(
            phase2_prompt.split())
        assert "a deliberately triggered failure plus observation" in " ".join(
            phase2_prompt.split())
        assert "For Start 1, the deterministic gate requires one family per lesson" in " ".join(
            phase2_prompt.split())
        assert "prerequisite comes first in the ordered introduces list" in " ".join(
            phase2_prompt.split())
        assert "legacy plan" in phase2_prompt
        assert "superseded only by the authority's narrow same-family" in " ".join(
            phase2_prompt.split())
        assert "A generated artifact may truthfully have zero artifact inputs" in " ".join(
            phase2_prompt.split())
        assert "correct encoding is mode `run` plus artifact `package`" in " ".join(
            phase2_prompt.split())
        assert "nested sealed-delivery copy" in " ".join(phase2_prompt.split())
        assert "Never request a `packageProof` key" in " ".join(phase2_prompt.split())
        assert "All four production modes are allowed" in " ".join(
            phase2_prompt.split())
        assert "they never forbid the mode itself" in " ".join(
            phase2_prompt.split())
        assert "written by the learner are authored" in " ".join(
            phase2_prompt.split())
        assert "maximum of six official or primary sources" in " ".join(
            phase2_prompt.split())
        assert "Tooling external or both requires a truthful" in " ".join(
            phase2_prompt.split())
        assert "# CONTRACT CONFLICT" in phase2_prompt
        assert "Issues found: N" in phase2_prompt
        assert "This does not suppress semantically omitted" in " ".join(
            phase2_prompt.split())
        assert "capability-component owner order" in " ".join(phase2_prompt.split())
        assert "failure-path edge direction" in " ".join(phase2_prompt.split())
        assert "planned continuity carry-forward" in " ".join(phase2_prompt.split())
        assert "productionDependsOn" in phase2_prompt
        followup_prompt = planning_review.planning_prompt(
            2, phase2_packet, phase2_sources,
            prior_review={"status": "FAIL", "report": "FAIL: preserve the five-lesson spine."})
        assert "ACCUMULATED PREVIOUS REVIEW CONTRACTS" in followup_prompt
        assert "verify every still-applicable prior finding is fixed" in " ".join(
            followup_prompt.split())
        assert "preserve the five-lesson spine" in followup_prompt
        assert "exact per-section lessonCount values" in followup_prompt
        accumulated_prompt = planning_review.planning_prompt(
            2, phase2_packet, phase2_sources,
            prior_reviews=[
                {"status": "FAIL", "report": "FAIL: repair the first build mechanism."},
                {"status": "FAIL", "report": "FAIL: repair the cleanup mechanism."},
            ])
        assert "PRIOR REVIEW 1" in accumulated_prompt
        assert "repair the first build mechanism" in accumulated_prompt
        assert "PRIOR REVIEW 2" in accumulated_prompt
        assert "repair the cleanup mechanism" in accumulated_prompt
        assert "old finding was invalid" in accumulated_prompt
        phase1_followup = planning_review.planning_prompt(
            1, phase1_packet, phase1_sources,
            prior_review={"status": "FAIL", "report": "FAIL: clarify the arc."})
        assert "explicit Phase-1 policy above" in phase1_followup
        assert "explicit Phase-2 rules above" not in phase1_followup

        # Presentation is not a contract. Helpful prose with a verdict is usable even
        # without headings, criterion records, field names, or prescribed citations.
        freeform = (
            "PASS — The arc is coherent and the bounded plan gives the learner a credible "
            "route from foundations to the finished artifact. The cited source supports "
            "the sequence, ownership, delivery, and proof obligations without exposing "
            "any repair that should block this transition.")
        good, errors = planning_review.validate_result(freeform, 2, phase2_sources)
        assert not errors and good["status"] == "PASS" and good["report"] == freeform
        assert good["issueCount"] == 0
        inferred_pass, errors = planning_review.validate_result(
            "The bounded evidence is complete and all planning criteria are satisfied. "
            "The route is coherent, feasible, learner-owned, and backed by an observable "
            "clean-start delivery journey, so there are no material repairs or blockers.",
            2, phase2_sources)
        assert not errors and inferred_pass["status"] == "PASS"
        inferred, errors = planning_review.validate_result(
            "Detailed observations cover scope, sequence, ownership, and delivery across "
            "the bounded source. The writer gives useful evidence and repair context but "
            "never provides a clear overall disposition for the harness.",
            2, phase2_sources)
        assert not errors and inferred["status"] == "FAIL"
        assert inferred["issueCount"] == 1
        counted, errors = planning_review.validate_result(
            "# FAIL\n\nIssues found: 3\n\nThree root repairs remain.",
            2, phase2_sources)
        assert not errors and counted["issueCount"] == 3
        terse_pass, errors = planning_review.validate_result(
            "PASS — looks good.", 2, phase2_sources)
        assert not errors and terse_pass["status"] == "PASS"
        conflict_text = (
            "# CONTRACT CONFLICT\n\nThe sealed lesson count and sealed mandatory arc "
            "cannot both be satisfied by any permitted Phase-2 source.")
        conflict, errors = planning_review.validate_result(
            conflict_text, 2, phase2_sources)
        assert not errors and conflict["status"] == "FAIL"
        assert conflict["contractConflict"] is True
        assert planning_review.is_contract_conflict_report(conflict_text)
        phase1_conflict, errors = planning_review.validate_result(
            conflict_text, 1, phase1_sources)
        assert not errors and phase1_conflict["contractConflict"] is False

        # A useful FAIL is authoritative and cached after one Luna call in both phases.
        # The exact Markdown is archived and handed to the author unchanged.
        for phase, sources in ((1, phase1_sources), (2, phase2_sources)):
            remove_cached("demo", phase)
            routed = []
            expected = audit_report(phase, sources, fail_criterion=(
                "arc-sequencing" if phase == 1 else "prerequisite-order"))

            def useful_fail(_prompt, validator, report=expected):
                routed.append(validator["model"])
                return report

            failed = planning_review.review_planning_phase(
                "demo", phase, "course", adapter=useful_fail)
            cached_failed = planning_review.review_planning_phase(
                "demo", phase, "course",
                adapter=lambda _prompt, _validator: (_ for _ in ()).throw(
                    AssertionError("usable FAIL was not cached")))
            assert failed["status"] == "FAIL" and not failed["cached"]
            assert cached_failed["status"] == "FAIL" and cached_failed["cached"]
            assert cached_failed["planningContractCycle"] is True
            assert planning_review.PLANNING_CONTRACT_CYCLE_MARKER in (
                planning_review.review_report(phase, cached_failed))
            assert routed == ["gpt-5.6-luna"]
            assert planning_review.review_report(phase, failed) == expected

        calls_file = review_records.calls_path(build_dir, "demo")
        with open(calls_file, encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
        useful_fail_rows = [row for row in rows if row["status"] == "FAIL"]
        assert useful_fail_rows
        assert all(not row.get("malformed", False) for row in useful_fail_rows)

        archived = os.listdir(os.path.join(failure_dir, "demo"))
        assert archived and all(name.endswith(".md") for name in archived)
        archive_text = "\n".join(
            open(os.path.join(failure_dir, "demo", name), encoding="utf-8").read()
            for name in archived)
        assert "# Planning Validator Review" in archive_text
        assert "arc-sequencing does not yet pass" in archive_text
        assert "prerequisite-order does not yet pass" in archive_text

        # A terse but readable answer is a normal FAIL packet. It never buys a
        # formatting retry or a call to another model.
        remove_cached("demo", 1)
        routed, prompts = [], []

        def terse_failure(prompt, validator):
            routed.append(validator["model"])
            prompts.append(prompt)
            return "Needs repair."

        terse = planning_review.review_planning_phase(
            "demo", 1, "course", adapter=terse_failure)
        assert terse["status"] == "FAIL"
        assert routed == ["gpt-5.6-luna"]
        assert terse["report"] == "Needs repair."

        # Ambiguity is a FAIL, not a third stopping state, and still costs one call.
        remove_cached("demo", 1)
        routed = []

        def ambiguous_validator(_prompt, validator):
            routed.append(validator["model"])
            return "I cannot verify the dependency order from the supplied evidence."

        ambiguous = planning_review.review_planning_phase(
            "demo", 1, "course", adapter=ambiguous_validator)
        assert ambiguous["status"] == "FAIL"
        assert routed == ["gpt-5.6-luna"]

        # Fingerprint history is durable: A -> B -> A is stopped before another
        # Luna call even when a worker restart would have erased in-memory counters.
        remove_cached("demo", 2)
        course_file = os.path.join(author_root, "course.json")
        with open(course_file, encoding="utf-8") as handle:
            state_a = json.load(handle)
        cycle_calls = []

        def cycle_fail_a(_prompt, _validator):
            cycle_calls.append("A")
            return audit_report(2, phase2_sources, fail_criterion="prerequisite-order")

        first_a = planning_review.review_planning_phase(
            "demo", 2, "course", adapter=cycle_fail_a)
        assert first_a["status"] == "FAIL" and cycle_calls == ["A"]
        state_b = json.loads(json.dumps(state_a))
        state_b["graduateCapabilities"] = [{"id": "different-evidence"}]
        with open(course_file, "w", encoding="utf-8") as handle:
            json.dump(state_b, handle)

        def cycle_fail_b(_prompt, _validator):
            cycle_calls.append("B")
            return audit_report(2, phase2_sources, fail_criterion="pacing-density")

        second_b = planning_review.review_planning_phase(
            "demo", 2, "course", adapter=cycle_fail_b)
        assert second_b["status"] == "FAIL" and cycle_calls == ["A", "B"]
        with open(course_file, "w", encoding="utf-8") as handle:
            json.dump(state_a, handle)
        repeated_a = planning_review.review_planning_phase(
            "demo", 2, "course",
            adapter=lambda *_args: (_ for _ in ()).throw(
                AssertionError("repeated evidence bought another Luna call")))
        assert repeated_a["status"] == "FAIL" and repeated_a["cached"]
        assert repeated_a["planningContractCycle"] is True
        assert planning_review.is_planning_contract_cycle_report(
            planning_review.review_report(2, repeated_a))

        # A contract or prompt-policy change invalidates prior review prose as well
        # as its evidence fingerprint, even if a maintainer forgets a manual version bump.
        # Otherwise a corrected prompt can feed the obsolete demand straight back to Luna.
        remove_cached("demo", 2)
        with open(planning_review.result_path("demo", 2), "w", encoding="utf-8") as handle:
            json.dump({
                "contract": planning_review.AUDIT_CONTRACT_VERSION,
                "policyFingerprint": "obsolete-policy",
                "validator": {"kind": "codex-cli", "model": "gpt-5.6-luna",
                              "effort": "medium"},
                "fingerprint": "obsolete",
                "result": {"status": "FAIL", "report": "split every paired family"},
                "history": [
                    {"status": "FAIL", "report": "one mechanism must equal one family"}],
            }, handle)
        refreshed_prompts = []

        def refreshed_contract(prompt, _validator):
            refreshed_prompts.append(prompt)
            return audit_report(2, phase2_sources)

        refreshed = planning_review.review_planning_phase(
            "demo", 2, "course", adapter=refreshed_contract)
        assert refreshed["status"] == "PASS" and not refreshed["cached"]
        assert len(refreshed_prompts) == 1
        assert "split every paired family" not in refreshed_prompts[0]
        assert "one mechanism must equal one family" not in refreshed_prompts[0]
        with open(planning_review.result_path("demo", 2), encoding="utf-8") as handle:
            refreshed_cache = json.load(handle)
        assert refreshed_cache["policyFingerprint"] == (
            planning_review.planning_policy_fingerprint(2))

        try:
            planning_review.review_planning_phase(
                "demo", 3, "course", adapter=pass_adapter)
        except ValueError as exc:
            assert "only for Phase 1 and Phase 2" in str(exc)
        else:
            raise AssertionError("planning review unexpectedly accepted Phase 3")

print("planning Validator AI Markdown gates: OK")
