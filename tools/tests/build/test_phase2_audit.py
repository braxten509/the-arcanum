#!/usr/bin/env python3
"""Language-neutral Phase-2 audit closes mechanisms and artifact transitions."""
import copy
import json
import os
import sys
import tempfile
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tools")]

from tools.buildlib.phase2_audit import audit_problems, phase2_authority
from tools.buildlib.course_map import author_spec

module_text = open(os.path.join(ROOT, "tools", "buildlib", "phase2_audit.py"),
                   encoding="utf-8").read().lower()
for language_specific in ("nasm", "gcc", "sdl2", "cargo", "javac", "pytest"):
    assert language_specific not in module_text


PLAN = """- **Starting level (1-10):** 1
**Lesson counts:** s01=2; s02=1
"""

COURSE = {
    "mechanismContract": {"mechanisms": [
        {"id": "edit-source", "label": "create and edit source", "kind": "tool-action",
         "owner": "s01.l01"},
        {"id": "compile-source", "label": "transform source into a runnable artifact",
         "kind": "build-command", "owner": "s01.l02"},
        {"id": "copy-package", "label": "copy the runnable artifact into delivery",
         "kind": "tool-action", "owner": "s02.l01"},
    ]},
    "artifactContract": {"artifacts": [
        {"artifact": "src/main.code", "ownerWorking": "s01.working",
         "disposition": "ships"},
        {"artifact": "build/app", "ownerWorking": "s01.working",
         "disposition": "retires", "retireBy": "s02"},
        {"artifact": "dist/app", "ownerWorking": "s02.working",
         "disposition": "ships"},
    ]},
    "sections": [
        {"id": "s01", "languagePractice": ["language-values"], "nodes": [
            {"id": "s01.l01", "kind": "lesson", "introduces": ["edit-source"]},
            {"id": "s01.l02", "kind": "lesson", "introduces": ["compile-source"]},
            {"id": "s01.working", "kind": "working",
             "mechanisms": ["edit-source", "compile-source"]},
        ]},
        {"id": "s02", "languagePractice": ["language-control"], "nodes": [
            {"id": "s02.l01", "kind": "lesson", "introduces": ["copy-package"]},
            {"id": "s02.working", "kind": "working",
             "mechanisms": ["edit-source", "compile-source", "copy-package"]},
        ]},
    ],
}

AUDIT = {
    "version": 1,
    "mechanisms": [
        {"id": "edit-source", "family": "source-authoring", "dependsOn": []},
        {"id": "compile-source", "family": "build-pipeline",
         "dependsOn": ["edit-source"]},
        {"id": "copy-package", "family": "delivery-transition",
         "dependsOn": ["compile-source"]},
    ],
    "artifactProduction": [
        {"artifact": "src/main.code", "ownerWorking": "s01.working",
         "mode": "authored", "inputs": [], "mechanisms": ["edit-source"]},
        {"artifact": "build/app", "ownerWorking": "s01.working",
         "mode": "generated", "inputs": ["src/main.code"],
         "mechanisms": ["compile-source"]},
        {"artifact": "dist/app", "ownerWorking": "s02.working",
         "mode": "copied", "inputs": ["build/app"],
         "mechanisms": ["copy-package"]},
    ],
}


assert not audit_problems(AUDIT, COURSE, PLAN)
authority = phase2_authority(PLAN)
assert authority["version"] == 7
assert "cumulativeWorkingMechanisms" in authority
assert authority["startingLevel"] == 1
assert authority["maxFamiliesPerLesson"] == 1
assert authority["nodeDoneWhen"] == {
    "shape": "a JSON object with the sole key checks; never a bare array",
    "lesson": {"checks": ["learner-construction", "lesson-source"]},
    "working": {"checks": ["learner-construction", "working-replay"]},
    "masteryLab": {"checks": ["learner-evidence", "variant-proof"]},
}
assert authority["artifactProduction"]["allowedModes"] == [
    "authored", "copied", "generated", "packaged"]
assert authority["artifactProduction"]["inputPolicyByMode"] == {
    "authored": "forbidden", "generated": "optional",
    "copied": "required", "packaged": "required"}
assert "never forbid a production mode" in authority[
    "artifactProduction"]["inputPolicyMeaning"]
assert "learner creates the canonical artifact" in authority[
    "artifactProduction"]["modeMeaning"]["authored"]
assert "productionDependsOn" in authority[
    "artifactProduction"]["productionPrerequisiteClosure"]
assert "component mechanisms" in authority["capabilityCoverage"]["meaning"]
assert "planned continuity obligation" in authority["continuityCoverage"]["meaning"]
assert "branch never depends" in authority["failurePaths"]["meaning"]
assert "precede the first project source" in authority["externalCleanStart"]["meaning"]
assert authority["research"]["maximumSources"] == 6
assert authority["research"]["requiredWhenTooling"] == ["external", "both"]
assert authority["acceptanceManifest"]["packageDeliveryEncoding"] == {
    "mode": "run", "artifact": "package"}
assert authority["acceptanceManifest"]["compactCourseMapPackageProofAllowed"] is False
assert "nested acceptance.sealedDelivery" in authority[
    "acceptanceManifest"]["forbiddenRepairs"]
assert authority["repairOwnership"]["generatedProposalRepairable"] is False

# New runs use audit v2. Production prerequisites are a deliberately narrower
# graph than teaching prerequisites, so artifact rows close over only operations
# actually needed to create that artifact.
AUDIT_V2 = copy.deepcopy(AUDIT)
AUDIT_V2.update({
    "version": 2,
    "capabilityCoverage": [],
    "continuityCoverage": [],
    "failurePaths": [],
})
for mechanism in AUDIT_V2["mechanisms"]:
    mechanism["productionDependsOn"] = []
next(item for item in AUDIT_V2["mechanisms"]
     if item["id"] == "compile-source")["productionDependsOn"] = ["edit-source"]
next(item for item in AUDIT_V2["mechanisms"]
     if item["id"] == "copy-package")["productionDependsOn"] = ["compile-source"]
AUDIT_V2["artifactProduction"][1]["mechanisms"] = ["edit-source", "compile-source"]
AUDIT_V2["artifactProduction"][2]["mechanisms"] = [
    "edit-source", "compile-source", "copy-package"]
assert not audit_problems(AUDIT_V2, COURSE, PLAN)
assert not audit_problems(AUDIT_V2, COURSE, PLAN, required_version=2)
assert any("version 1 is legacy read-only input" in item
           for item in audit_problems(AUDIT, COURSE, PLAN, required_version=2))

open_production = copy.deepcopy(AUDIT_V2)
open_production["artifactProduction"][1]["mechanisms"] = ["compile-source"]
assert any("not closed over production prerequisites" in item
           for item in audit_problems(open_production, COURSE, PLAN))

invalid_production_edge = copy.deepcopy(AUDIT_V2)
invalid_production_edge["mechanisms"][0]["productionDependsOn"] = ["copy-package"]
assert any("outside its teaching dependency closure" in item
           for item in audit_problems(invalid_production_edge, COURSE, PLAN))

late_capability = copy.deepcopy(COURSE)
late_capability["sections"][0]["nodes"][0]["teaches"] = ["combined-build-skill"]
late_coverage = copy.deepcopy(AUDIT_V2)
late_coverage["capabilityCoverage"] = [{
    "capability": "combined-build-skill",
    "mechanisms": ["edit-source", "compile-source"],
}]
assert any("claimed before component mechanisms" in item
           for item in audit_problems(late_coverage, late_capability, PLAN))

continuity_course = copy.deepcopy(COURSE)
continuity_course["plannedObligations"] = [{
    "id": "preserve-build", "target": "s02",
}]
continuity_audit = copy.deepcopy(AUDIT_V2)
continuity_audit["continuityCoverage"] = [{
    "obligation": "preserve-build", "mechanisms": ["compile-source"],
}]
assert not audit_problems(continuity_audit, continuity_course, PLAN)
broken_continuity = copy.deepcopy(continuity_course)
broken_continuity["sections"][1]["nodes"][-1]["mechanisms"].remove("compile-source")
assert any("Working omits preserved mechanisms" in item
           for item in audit_problems(continuity_audit, broken_continuity, PLAN))

clean_start = copy.deepcopy(COURSE)
clean_start["sections"][0]["nodes"][0]["teaches"] = ["tool-edit-save"]
clean_start["sections"][0]["nodes"][1]["teaches"] = [
    "tool-install", "tool-diagnose"]
external_plan = PLAN + "- **Tooling:** external\n"
assert any("external clean start requires" in item
           for item in audit_problems(AUDIT, clean_start, external_plan))

failure_course = copy.deepcopy(COURSE)
failure_course["mechanismContract"]["mechanisms"].extend([
    {"id": "status-observation", "label": "observe a failed operation status",
     "kind": "syntax-form", "owner": "s03.l01"},
    {"id": "diagnostic-query", "label": "obtain the failure diagnostic",
     "kind": "api", "owner": "s03.l01"},
    {"id": "failure-branch", "label": "branch on the failed status",
     "kind": "syntax-form", "owner": "s03.l01"},
    {"id": "failure-cleanup", "label": "release resources after failure",
     "kind": "syntax-form", "owner": "s03.l01"},
])
failure_course["sections"].append({
    "id": "s03", "languagePractice": ["language-failure"], "nodes": [
        {"id": "s03.l01", "kind": "lesson", "introduces": [
            "status-observation", "diagnostic-query", "failure-branch",
            "failure-cleanup"]},
        {"id": "s03.working", "kind": "working", "mechanisms": [
            "edit-source", "compile-source", "status-observation",
            "diagnostic-query", "failure-branch", "failure-cleanup"]},
    ],
})
failure_audit = copy.deepcopy(AUDIT_V2)
failure_audit["mechanisms"].extend([
    {"id": "status-observation", "family": "failure-handling",
     "dependsOn": ["compile-source"], "productionDependsOn": []},
    {"id": "diagnostic-query", "family": "failure-handling",
     "dependsOn": ["status-observation"], "productionDependsOn": []},
    {"id": "failure-branch", "family": "failure-handling",
     "dependsOn": ["status-observation"], "productionDependsOn": []},
    {"id": "failure-cleanup", "family": "failure-handling",
     "dependsOn": ["failure-branch"], "productionDependsOn": []},
])
failure_audit["failurePaths"] = [{
    "id": "runtime-failure",
    "status": ["status-observation"],
    "branches": ["failure-branch"],
    "diagnostics": ["diagnostic-query"],
    "cleanup": ["failure-cleanup"],
}]
assert not audit_problems(failure_audit, failure_course, PLAN)

reversed_failure = copy.deepcopy(failure_audit)
next(item for item in reversed_failure["mechanisms"]
     if item["id"] == "failure-branch")["dependsOn"].append("diagnostic-query")
assert any("cannot depend on later diagnostic" in item
           for item in audit_problems(reversed_failure, failure_course, PLAN))

missing_mechanism = copy.deepcopy(AUDIT)
missing_mechanism["mechanisms"].pop()
assert any("missing exact ledger entries" in item
           for item in audit_problems(missing_mechanism, COURSE, PLAN))

late_dependency = copy.deepcopy(AUDIT)
late_dependency["mechanisms"][0]["dependsOn"] = ["copy-package"]
assert any("is later than owner" in item
           for item in audit_problems(late_dependency, COURSE, PLAN))

open_working = copy.deepcopy(COURSE)
open_working["sections"][1]["nodes"][-1]["mechanisms"].remove("compile-source")
assert any("not transitively closed" in item
           for item in audit_problems(AUDIT, open_working, PLAN))

dense = copy.deepcopy(AUDIT)
dense["mechanisms"][1]["family"] = "different-foundation"
dense_course = copy.deepcopy(COURSE)
dense_course["sections"][0]["nodes"][0]["introduces"].append("compile-source")
assert any("Starting level 1 permits at most 1" in item
           for item in audit_problems(dense, dense_course, PLAN))

missing_input = copy.deepcopy(AUDIT)
missing_input["artifactProduction"][1]["inputs"] = []
assert not audit_problems(missing_input, COURSE, PLAN)

missing_copy_input = copy.deepcopy(AUDIT)
missing_copy_input["artifactProduction"][2]["inputs"] = []
assert any("mode copied requires at least one input" in item
           for item in audit_problems(missing_copy_input, COURSE, PLAN))

missing_package_input = copy.deepcopy(AUDIT)
missing_package_input["artifactProduction"][2].update({"mode": "packaged", "inputs": []})
assert any("mode packaged requires at least one input" in item
           for item in audit_problems(missing_package_input, COURSE, PLAN))

same_lesson = copy.deepcopy(COURSE)
same_lesson["mechanismContract"]["mechanisms"][1]["owner"] = "s01.l01"
same_lesson["sections"][0]["nodes"][0]["introduces"] = [
    "edit-source", "compile-source"]
same_lesson["sections"][0]["nodes"][1]["introduces"] = []
same_family = copy.deepcopy(AUDIT)
same_family["mechanisms"][1]["family"] = "source-authoring"
assert not audit_problems(same_family, same_lesson, PLAN)

reversed_same_lesson = copy.deepcopy(same_lesson)
reversed_same_lesson["sections"][0]["nodes"][0]["introduces"] = [
    "compile-source", "edit-source"]
assert any("must appear first" in item
           for item in audit_problems(same_family, reversed_same_lesson, PLAN))

cross_family_same_lesson = copy.deepcopy(AUDIT)
assert any("cross-family mechanism" in item
           for item in audit_problems(cross_family_same_lesson, same_lesson, PLAN))

wrong_producer = copy.deepcopy(AUDIT)
wrong_producer["artifactProduction"][2]["mechanisms"] = ["unknown-copy"]
assert any("absent from s02.working" in item
           for item in audit_problems(wrong_producer, COURSE, PLAN))

cycle = copy.deepcopy(AUDIT)
cycle["artifactProduction"][0]["mode"] = "generated"
cycle["artifactProduction"][0]["inputs"] = ["dist/app"]
assert any("artifact production cycle" in item
           for item in audit_problems(cycle, COURSE, PLAN))

# Exercise the real compact-source materializer in a fresh build directory. The
# resulting proposal must be derived from authored files, never supplied as the
# test fixture or edited directly.
with tempfile.TemporaryDirectory() as temporary:
    build_dir = os.path.join(temporary, ".tome-build")
    os.makedirs(build_dir)
    seed_file = os.path.join(build_dir, "fresh.course-map.seed.json")
    proposal_file = os.path.join(build_dir, "fresh.course-map.proposal.json")
    with open(seed_file, "w", encoding="utf-8") as handle:
        json.dump(COURSE, handle)
    with open(os.path.join(build_dir, "fresh.plan.md"), "w", encoding="utf-8") as handle:
        handle.write(PLAN)
    with patch.object(author_spec, "BUILD_DIR", build_dir), \
            patch.object(author_spec, "seed_path", return_value=seed_file), \
            patch.object(author_spec, "proposal_path", return_value=proposal_file):
        author_spec.initialize_author_spec("fresh", COURSE)
        audit_file = os.path.join(
            build_dir, "fresh.course-map-author", "audit.json")
        with open(audit_file, "w", encoding="utf-8") as handle:
            json.dump(AUDIT_V2, handle)
        previewed = author_spec.materialize_author_preview("fresh")
        preview_file = author_spec.preview_path("fresh")
        assert os.path.isfile(preview_file)
        assert not os.path.exists(proposal_file)
        with open(preview_file, encoding="utf-8") as handle:
            assert json.load(handle) == previewed
        materialized = author_spec.materialize_author_spec("fresh")
        # New Phase-2 materialization may never downgrade to the legacy v1 shape.
        with open(audit_file, "w", encoding="utf-8") as handle:
            json.dump(AUDIT, handle)
        try:
            author_spec.materialized_author_spec("fresh")
        except author_spec.CourseMapError as error:
            assert "version 1 is legacy read-only input" in str(error)
        else:
            raise AssertionError("new Phase 2 accepted a legacy v1 audit")
        with open(audit_file, "w", encoding="utf-8") as handle:
            json.dump(AUDIT_V2, handle)
        section_file = os.path.join(
            build_dir, "fresh.course-map-author", "sections", "s01.json")
        with open(section_file, encoding="utf-8") as handle:
            section_spec = json.load(handle)
        section_spec["languagePractice"] = []
        with open(section_file, "w", encoding="utf-8") as handle:
            json.dump(section_spec, handle)
        try:
            author_spec.materialized_author_spec("fresh")
        except author_spec.CourseMapError as error:
            assert "removed sealed Phase-1 minimums: language-values" in str(error)
        else:
            raise AssertionError("Phase 2 removed a sealed language-practice minimum")
    assert os.path.isfile(proposal_file)
    with open(proposal_file, encoding="utf-8") as handle:
        persisted = json.load(handle)
    assert persisted == materialized
    assert persisted["mechanismContract"] == COURSE["mechanismContract"]
    assert persisted["artifactContract"] == COURSE["artifactContract"]
    assert [section["nodes"] for section in persisted["sections"]] == [
        section["nodes"] for section in COURSE["sections"]]
    assert all("projectMilestone" in section for section in persisted["sections"])

# The human-facing contracts must not quietly reintroduce requirements that the
# deterministic authority rejects or assign generated output back to the author.
phase1_guide = open(os.path.join(ROOT, "tome-workflow", "phase-1-concept-arc.md"),
                    encoding="utf-8").read()
calibration_source = open(os.path.join(ROOT, "tools", "buildlib", "workflow", "prompts.py"),
                          encoding="utf-8").read()
phase2_guide = open(os.path.join(ROOT, "tome-workflow", "phase-2-skeleton-voice.md"),
                    encoding="utf-8").read()
single_author_guide = open(os.path.join(ROOT, "tome-workflow", "single-author.md"),
                           encoding="utf-8").read()
assert "cross-family prerequisite requires an earlier lesson" in phase1_guide
assert "a cross-family prerequisite requires an earlier lesson" in calibration_source
assert "This decides mechanism identity, not lesson-family" in calibration_source
assert "`generated` may have zero artifact inputs" in phase2_guide
assert "same-lesson dependency is valid only" in phase2_guide
assert "proposal is generated, read-only evidence" in single_author_guide
assert "Also complete `.tome-build/BUILD_ID.course-map.proposal.json`" not in single_author_guide

print("Phase-2 mechanism and artifact-production audit: OK")
