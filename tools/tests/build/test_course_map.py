#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""Focused contract tests for bounds, graph validation, sealing, and digest drift."""
import copy
import json
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from buildlib import course_map
from buildlib.course_map import author_spec
from buildlib import phase2_research
from buildlib.course.amend import amend_course_map
from buildlib.course.limits import (mastery_section_cap,
                                    mastery_section_count_error)
from buildlib.course_map.seed import artifact_lifecycle_obligations
from buildlib.skeleton import parse_section_list


PLAN = """# BUILD PLAN — demo
**Graduate ledger:** The learner can build and verify the promised tool.
**Mastery proof:** The final Working requires independent transfer and a justified choice.
**Acceptance scenarios:** starts-clean -> finishes-clean
**Lesson counts:** s01=3; s02=3
**Continuity map:**
s01 -> s02: preserve the public value contract through the final integration
**Artifact lifecycle:** no temporary artifact ships
**Section list:**
1. **s01 — Establish the Contract:** teach and build the stable first capability
2. **s02 — Complete the Integration:** integrate the first capability into the delivered outcome
"""


def detailed(seed):
    value = copy.deepcopy(seed)
    value["graduateCapabilities"] = ["first-capability", "integrated-outcome"]
    first_caps = ["first-capability", "first-practice", "first-proof"]
    final_caps = ["integrated-outcome", "integration-practice", "integration-proof"]
    value["sections"][0]["capabilities"] = first_caps
    value["sections"][0]["nodes"] = [
        {"id": f"s01.l{index:02d}", "kind": "lesson", "title": f"First Lesson {index}",
         "teaches": [capability],
         "introduces": [],
         "dependsOn": [] if index == 1 else [f"s01.l{index - 1:02d}"],
         "validationDependencies": [],
         "doneWhen": {"checks": ["lesson-source", "learner-construction"]}}
        for index, capability in enumerate(first_caps, 1)
    ] + [
        {"id": "s01.working", "kind": "working", "title": "Build the Contract",
         "requires": first_caps, "dependsOn": ["s01.l03"],
         "mechanisms": [],
         "validationDependencies": [],
         "projectMilestone": value["sections"][0]["projectMilestone"],
         "learnerOwnedArtifacts": ["src/contract.txt"],
         "doneWhen": {"checks": ["working-replay", "learner-construction"]}},
    ]
    value["sections"][1]["capabilities"] = final_caps
    value["sections"][1]["dependsOn"] = ["s01"]
    value["sections"][1]["nodes"] = [
        {"id": f"s02.l{index:02d}", "kind": "lesson", "title": f"Integration {index}",
         "teaches": [capability],
         "introduces": [],
         "dependsOn": ["s01.working"] if index == 1 else [f"s02.l{index - 1:02d}"],
         "validationDependencies": [],
         "doneWhen": {"checks": ["lesson-source", "learner-construction"]}}
        for index, capability in enumerate(final_caps, 1)
    ] + [
        {"id": "s02.working", "kind": "working", "title": "Deliver It",
         "requires": first_caps + final_caps,
         "mechanisms": [],
         "dependsOn": ["s01.working", "s02.l03"],
         "validationDependencies": [],
         "projectMilestone": value["sections"][1]["projectMilestone"],
         "learnerOwnedArtifacts": ["dist/delivered.txt"],
         "doneWhen": {"checks": ["working-replay", "learner-construction"]}},
    ]
    obligation = value["plannedObligations"][0]
    obligation.update({"owner": "public value contract", "location": "lessons/l01.toml",
                       "reason": "The final integration consumes the stable contract.",
                       "doneWhen": {"evidenceLocations": ["lessons/l01.toml"],
                                    "capabilityIds": ["integrated-outcome"],
                                    "proofIds": ["s02"], "acceptanceIds": ["finishes-clean"],
                                    "observedResult": "The final integration preserves the value."}})
    return value


def section_list(count):
    return "**Section list:**\n" + "\n".join(
        f"{number}. **s{number:02d} — Section {number}:** necessary capability milestone {number}"
        for number in range(1, count + 1))


with tempfile.TemporaryDirectory() as root:
    old_build, old_repo = course_map.BUILD_DIR, course_map.REPO
    old_author_build, old_author_repo = author_spec.BUILD_DIR, author_spec.REPO
    old_research_build, old_research_repo = phase2_research.BUILD_DIR, phase2_research.REPO
    course_map.BUILD_DIR, course_map.REPO = os.path.join(root, ".tome-build"), root
    author_spec.BUILD_DIR, author_spec.REPO = course_map.BUILD_DIR, root
    phase2_research.BUILD_DIR, phase2_research.REPO = course_map.BUILD_DIR, root
    os.makedirs(course_map.BUILD_DIR)
    plan = os.path.join(course_map.BUILD_DIR, "demo.plan.md")
    with open(plan, "w", encoding="utf-8") as handle:
        handle.write(PLAN)
    try:
        seed = course_map.seed_course_map("demo", plan)
        assert len(seed["sections"]) == 2
        assert seed["version"] == 6
        assert [section["lessonCount"] for section in seed["sections"]] == [3, 3]
        author_spec.initialize_author_spec("demo", seed)
        assert author_spec.materialize_author_spec("demo") == seed
        phase2_research.initialize_ledger("demo", "external")
        research_ok, research_report = phase2_research.validate_ledger("demo")
        assert not research_ok and "official or primary source" in research_report
        phase2_research.initialize_ledger("demo", "internal")
        assert phase2_research.validate_ledger("demo")[0]
        proposal = detailed(seed)
        for sid in ("s01", "s02"):
            os.makedirs(os.path.join(root, "tomes", "demo", "sections", sid,
                                     "lessons"), exist_ok=True)
            with open(os.path.join(root, "tomes", "demo", "sections", sid,
                                   "lessons", "l01.toml"), "w", encoding="utf-8") as handle:
                handle.write('[[lessons]]\nid="placeholder"\n')
        with open(course_map.proposal_path("demo"), "w", encoding="utf-8") as handle:
            json.dump(proposal, handle)
        clean, report = course_map.validate_proposal("demo")
        assert clean, report
        sealed = course_map.seal_course_map("demo")
        assert course_map.load_course_map("demo")["digest"] == sealed["digest"]
        candidate = copy.deepcopy(sealed)
        candidate["sections"][1]["title"] = "Audited Final Title"
        with patch("buildlib.course.state.invalidate_from") as invalidate:
            sealed = amend_course_map(
                "demo", candidate, "Clarify the final milestone without changing its contract")
        invalidate.assert_called_once_with("demo", "s02")
        assert sealed["revision"] == 2
        journal = course_map._read_json(course_map.amendment_path("demo"))
        assert journal[-1]["oldDigest"] != journal[-1]["newDigest"]

        superseding = copy.deepcopy(sealed)
        original_obligation = superseding["plannedObligations"][0]
        replacement = copy.deepcopy(original_obligation)
        replacement.update({
            "id": "s01-plan-s02-revised",
            "supersedes": original_obligation["id"],
            "revisionReason": "Replace the active contract with a clearer audited equivalent.",
        })
        superseding["plannedObligations"].append(replacement)
        with patch("buildlib.course.state.derive_course_state", return_value={
                "activeObligations": [original_obligation]}), \
                patch("buildlib.course.state.invalidate_from"):
            sealed = amend_course_map(
                "demo", superseding, "Supersede the active contract through the audited path")
        assert sealed["plannedObligations"][-1]["supersedes"] == original_obligation["id"]

        try:
            amend_course_map(
                "demo", sealed, "Attempt an audited but content-free plan revision")
            raise AssertionError("a no-op amendment created a new sealed revision")
        except course_map.CourseMapError as exc:
            assert "does not change" in str(exc)

        missing = copy.deepcopy(proposal)
        missing["sections"][1]["nodes"] = missing["sections"][1]["nodes"][:-1]
        assert any("exactly one Working" in item
                   for item in course_map.validate_course_map(missing, seed=seed))
        cyclic = copy.deepcopy(proposal)
        cyclic["sections"][0]["dependsOn"] = ["s02"]
        assert any("dependency" in item for item in course_map.validate_course_map(cyclic, seed=seed))
        unknown = copy.deepcopy(proposal)
        unknown["surprise"] = True
        assert any("unknown keys" in item
                   for item in course_map.validate_course_map(unknown, seed=seed))
        global_location = copy.deepcopy(proposal)
        global_location["plannedObligations"][0]["location"] = "sections/s01/section.toml"
        assert any("relative to its owning section" in item
                   for item in course_map.validate_course_map(global_location, seed=seed))
        missing_location = copy.deepcopy(proposal)
        missing_location["plannedObligations"][0]["location"] = "missing.toml"
        assert any("does not name an existing s01 file" in item
                   for item in course_map.validate_map_locations("demo", missing_location))
        bad_reference = copy.deepcopy(proposal)
        bad_reference["plannedObligations"][0]["doneWhen"]["proofIds"] = ["s99"]
        assert any("nonexistent id 's99'" in item
                   for item in course_map.validate_course_map(bad_reference, seed=seed))
        missing_contract = copy.deepcopy(proposal)
        missing_contract["sections"][0]["nodes"][1]["doneWhen"]["checks"] = ["working-replay"]
        assert any("learner-construction" in item
                   for item in course_map.validate_course_map(missing_contract, seed=seed))
        missing_package_packet = copy.deepcopy(proposal)
        del missing_package_packet["sections"][1]["nodes"][0]["validationDependencies"]
        assert any("validationDependencies" in item
                   for item in course_map.validate_course_map(
                       missing_package_packet, seed=seed))
        illegal_supersession = copy.deepcopy(proposal)
        illegal_supersession["plannedObligations"][0].update({
            "supersedes": "s01-plan-s02-older",
            "revisionReason": "Phase 2 may not author a supersession claim.",
        })
        assert any("audited amendment path" in item
                   for item in course_map.validate_course_map(illegal_supersession, seed=seed))

        tampered = course_map.load_course_map("demo")
        tampered["sections"][0]["title"] = "Tampered"
        with open(course_map.map_path("demo"), "w", encoding="utf-8") as handle:
            json.dump(tampered, handle)
        try:
            course_map.load_course_map("demo")
            raise AssertionError("tampered map was trusted")
        except course_map.CourseMapError as exc:
            assert "digest" in str(exc)
        with open(course_map.map_path("demo"), "w", encoding="utf-8") as handle:
            json.dump(sealed, handle)
        with open(plan, "a", encoding="utf-8") as handle:
            handle.write("\nunaudited plan change\n")
        try:
            course_map.load_course_map("demo")
            raise AssertionError("plan drift was trusted")
        except course_map.CourseMapError as exc:
            assert "planSha256" in str(exc)
    finally:
        course_map.BUILD_DIR, course_map.REPO = old_build, old_repo
        author_spec.BUILD_DIR, author_spec.REPO = old_author_build, old_author_repo
        phase2_research.BUILD_DIR, phase2_research.REPO = old_research_build, old_research_repo

for rejected in (1, 41):
    try:
        parse_section_list(section_list(rejected))
        raise AssertionError(f"{rejected} sections were accepted")
    except ValueError as exc:
        assert "2 through 40" in str(exc)
assert len(parse_section_list(section_list(2))) == 2
assert len(parse_section_list(section_list(40))) == 40
assert [mastery_section_cap(1, scope) for scope in range(1, 6)] == [4, 6, 8, 10, 12]
assert mastery_section_cap(2, 1) == 40
assert not mastery_section_count_error(8, 1, 3)
assert "at most 8 sections" in mastery_section_count_error(9, 1, 3)
retirements = artifact_lifecycle_obligations(
    "**Artifact lifecycle:** s01's temporary fixture is replaced in s02; "
    "s02's fallback deliberately ships", ["s01", "s02"])
assert len(retirements) == 1 and retirements[0]["kind"] == "temporary-retirement"
physical_retirements = artifact_lifecycle_obligations(
    "**Artifact lifecycle:**\n"
    "- s01's temporary fixture is replaced in s02\n"
    "- s02's debug probe is retired in s03", ["s01", "s02", "s03"])
assert [(item["origin"], item["target"]) for item in physical_retirements] == [
    ("s01", "s02"), ("s02", "s03")]

for path in ("tools/buildlib/workflow/prompts.py", "tome-workflow/phase-1-concept-arc.md",
             "tome-workflow/phase-2-skeleton-voice.md",
             "tome-workflow/phase-8-student-review.md",
             "tome-authoring/2-tome-toml.md", "tome-authoring/3-chapters.md"):
    text = open(os.path.join(_BOOTSTRAP_REPO, path),
                encoding="utf-8").read().lower()
    assert "single" + "-section" not in text and "single" + " section" not in text
    assert "one" + "-section course" not in text and "one" + " section course" not in text
    assert "4–6, a " + "broad" not in text and "12" + "–15" not in text

generic_prompt_paths = (
    "tools/buildlib/workflow/prompts.py",
    "tome-workflow/phase-1-concept-arc.md",
    "tome-workflow/phase-2-skeleton-voice.md",
    "tome-workflow/support/section-author.md",
    "tome-workflow/phase-8-student-review.md",
)
generic_prompt_text = "\n".join(
    open(os.path.join(_BOOTSTRAP_REPO, path),
         encoding="utf-8").read().lower()
    for path in generic_prompt_paths
)
for required in ("prerequisite topology rule", "transitive prerequisite closure",
                 "observable-interaction closure",
                 "capability honesty rule", "capability id as binding semantic scope",
                 "foundation cadence rule", "verification cadence rule",
                 "dependency installability rule",
                 "milestone coherence rule",
                 "curriculum capacity rule", "transfer distribution rule",
                 "cold-start dependency walk", "materially exercise"):
    assert required in generic_prompt_text
for forbidden in ("python requires classes", "python finish", "pytest assertions"):
    assert forbidden not in generic_prompt_text
print("course-map bounds/schema/seal tests: OK")
