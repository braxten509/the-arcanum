#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""Deterministic regressions for strict Phase-2 graph and artifact contracts."""
import copy
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from buildlib import course_map
from buildlib.skeleton.integrity import (artifact_inventory, delivery_contract,
                                         phase1_problems, phase2_alignment_problems,
                                         seed_contract)


PLAN_BODY = """
**Artifact lifecycle:** `src/app.txt` ships; `scratch.txt` retires in s02; `dist/app` ships.
**Artifact ownership:** src/app.txt @ s01.working -> ships; scratch.txt @ s01.working -> retires@s02; dist/app @ s02.working -> ships
**Section list:**
1. **s01 — Establish:** establish the learner-owned implementation and a temporary probe
2. **s02 — Deliver:** retire the probe and deliver the cumulative implementation
"""
V3_PLAN_BODY = """
**Finished tool:** A standalone executable that runs outside the authoring environment.
**Artifact lifecycle:** `src/app.txt` ships; `scratch.txt` retires in s02; `dist/app` ships; `requirements.txt` ships.
**Artifact ownership:** src/app.txt @ s01.working -> ships; scratch.txt @ s01.working -> retires@s02; dist/app @ s02.working -> ships; requirements.txt @ s02.working -> ships
**Delivery contract:** mode = package; artifact = dist/app; requirements = requirements.txt
**Section list:**
1. **s01 — Establish:** establish the learner-owned implementation and a temporary probe
2. **s02 — Deliver:** retire the probe and deliver the cumulative implementation
"""
records, problems = artifact_inventory(PLAN_BODY)
assert not problems and len(records) == 3
assert not phase1_problems(
    "- **Skeleton integrity contract:** 1\n", PLAN_BODY, ["s01", "s02"])
assert not phase1_problems(
    "- **Skeleton integrity contract:** 2\n", PLAN_BODY, ["s01", "s02"])
delivery, delivery_problems = delivery_contract(V3_PLAN_BODY)
assert not delivery_problems and delivery == {
    "mode": "package", "artifact": "dist/app", "requirements": "requirements.txt"}
assert not phase1_problems(
    "- **Skeleton integrity contract:** 3\n", V3_PLAN_BODY, ["s01", "s02"])
for malformed_path in ("dist/app/", "dist//app", "./dist/app", "dist/./app"):
    malformed_delivery = V3_PLAN_BODY.replace("artifact = dist/app",
                                               f"artifact = {malformed_path}")
    _delivery, malformed_problems = delivery_contract(malformed_delivery)
    assert any("stable relative path" in item for item in malformed_problems)
trailing_records, trailing_problems = artifact_inventory(
    "**Artifact ownership:** dist/app/ @ s02.working -> ships")
assert trailing_records and any("stable relative path" in item for item in trailing_problems)
v3_seed = seed_contract("- **Skeleton integrity contract:** 3\n" + V3_PLAN_BODY)
assert v3_seed["version"] == 3 and v3_seed["delivery"] == delivery
RUNTIME_PLAN_BODY = """
**Finished tool:** A learner-authored source entrypoint run from its project workspace.
**Artifact lifecycle:** `src/app.txt` ships.
**Artifact ownership:** src/app.txt @ s01.working -> ships
**Delivery contract:** mode = runtime; artifact = src/app.txt; requirements = none
**Section list:**
1. **s01 — Establish:** establish the learner-owned implementation
2. **s02 — Verify:** verify the cumulative implementation in its project workspace
"""
runtime_full_plan = (
    "- **Skeleton integrity contract:** 3\n"
    "- **Delivery-lock rule:** A packaged, standalone, installable, or distributable "
    "promise requires package mode.\n"
    "## Arc (Phase 1 fills this in, later phases read it)\n"
    + RUNTIME_PLAN_BODY)
assert not phase1_problems(
    runtime_full_plan, RUNTIME_PLAN_BODY, ["s01", "s02"])
assert seed_contract(runtime_full_plan)["delivery"] == {
    "mode": "runtime", "artifact": "src/app.txt", "requirements": None}
runtime_downgrade = V3_PLAN_BODY.replace(
    "mode = package; artifact = dist/app; requirements = requirements.txt",
    "mode = runtime; artifact = src/app.txt; requirements = none")
assert any("promises packaging or standalone distribution" in item for item in phase1_problems(
    "- **Skeleton integrity contract:** 3\n", runtime_downgrade, ["s01", "s02"]))
try:
    seed_contract("- **Skeleton integrity contract:** 3\n" + runtime_downgrade)
except ValueError as exc:
    assert "packaging promise requires package mode" in str(exc)
else:
    raise AssertionError("seed_contract accepted a packaged outcome as runtime delivery")
v2_lifecycle_gap = PLAN_BODY.replace("; `dist/app` ships.", ".")
assert any("omits owned artifacts: dist/app" in item for item in phase1_problems(
    "- **Skeleton integrity contract:** 2\n", v2_lifecycle_gap, ["s01", "s02"]))
bad_records, bad_problems = artifact_inventory(
    "**Artifact ownership:** /absolute @ s01.working -> ships; "
    "scratch @ s02.working -> retires@s01")
assert bad_records and bad_problems
assert any("after its owner" in item for item in phase1_problems(
    "- **Skeleton integrity contract:** 1\n",
    "**Artifact ownership:** scratch @ s02.working -> retires@s01",
    ["s01", "s02"]))

no_first_working_artifact = """
**Artifact lifecycle:** `src/app.txt` ships.
**Artifact ownership:** src/app.txt @ s02.working -> ships
"""
assert any("cannot populate s01.working" in item for item in phase1_problems(
    "- **Skeleton integrity contract:** 2\n",
    no_first_working_artifact,
    ["s01", "s02"]))

artifact_gap = """
**Artifact lifecycle:** `scratch.txt` retires in s02; `src/app.txt` ships.
**Artifact ownership:** scratch.txt @ s01.working -> retires@s02; src/app.txt @ s03.working -> ships
"""
gap_problems = phase1_problems(
    "- **Skeleton integrity contract:** 2\n", artifact_gap, ["s01", "s02", "s03"])
assert any("cannot populate s02.working" in item for item in gap_problems)
assert not any("cannot populate s01.working" in item for item in gap_problems)
assert not any("cannot populate s03.working" in item for item in gap_problems)


def detailed():
    value = {
        "version": 1, "revision": 1, "buildId": "strict-demo",
        "planSha256": hashlib.sha256(b"plan").hexdigest(),
        "bounds": {"minSections": 2, "maxSections": 40},
        "graduateContract": "The learner builds and verifies a cumulative delivered tool.",
        "graduateCapabilities": ["cap-one", "cap-two"],
        "masteryPerformances": ["The final Working proves independent integration."],
        "acceptanceScenarios": ["starts", "ships"],
        "artifactContract": {"version": 1, "artifacts": records},
        "sections": [], "plannedObligations": [],
    }
    cumulative = []
    for number in (1, 2):
        sid = f"s{number:02d}"
        capabilities = [f"cap-{number}-a", f"cap-{number}-b", f"cap-{number}-c"]
        cumulative.extend(capabilities)
        section = {
            "id": sid, "ordinal": number, "title": f"Section {number}",
            "promise": f"Complete cumulative milestone number {number}.",
            "capabilities": capabilities,
            "dependsOn": [] if number == 1 else ["s01"],
            "projectMilestone": f"Complete cumulative milestone number {number}.",
            "doneWhen": {"checks": ["continuity", "section-replay", "section-source"]},
            "nodes": [],
        }
        for lesson_number, capability in enumerate(capabilities, 1):
            dependencies = ([] if number == 1 and lesson_number == 1 else
                            [f"{sid}.l{lesson_number - 1:02d}"] if lesson_number > 1 else
                            ["s01.working"])
            section["nodes"].append({
                "id": f"{sid}.l{lesson_number:02d}", "kind": "lesson",
                "title": f"Lesson {number}.{lesson_number}", "teaches": [capability],
                "dependsOn": dependencies,
                "doneWhen": {"checks": ["learner-construction", "lesson-source"]},
            })
        artifacts = (["src/app.txt", "scratch.txt"] if number == 1
                     else ["src/app.txt", "dist/app"])
        section["nodes"].append({
            "id": f"{sid}.working", "kind": "working", "title": f"Working {number}",
            "requires": list(cumulative), "dependsOn": [f"{sid}.l03"],
            "projectMilestone": section["projectMilestone"],
            "learnerOwnedArtifacts": artifacts,
            "doneWhen": {"checks": ["learner-construction", "working-replay"]},
        })
        value["sections"].append(section)
    value["graduateCapabilities"] = [capability for section in value["sections"]
                                     for capability in section["capabilities"]]
    return value


valid = detailed()
assert not course_map.validate_course_map(valid, detailed=True)

flat = copy.deepcopy(valid)
flat["sections"][0]["nodes"][1]["dependsOn"] = []
assert any("previous lesson" in item or "prerequisite" in item
           for item in course_map.validate_course_map(flat, detailed=True))

detached_working = copy.deepcopy(valid)
detached_working["sections"][1]["nodes"][-1]["dependsOn"] = ["s01.working"]
assert any("final lesson" in item
           for item in course_map.validate_course_map(detached_working, detailed=True))

missing_shipped = copy.deepcopy(valid)
missing_shipped["sections"][1]["nodes"][-1]["learnerOwnedArtifacts"].remove("src/app.txt")
assert any("retain shipped 'src/app.txt'" in item
           for item in course_map.validate_course_map(missing_shipped, detailed=True))

undeclared = copy.deepcopy(valid)
undeclared["sections"][1]["nodes"][-1]["learnerOwnedArtifacts"].append("mystery.bin")
assert any("absent from Artifact ownership" in item
           for item in course_map.validate_course_map(undeclared, detailed=True))

not_retired = copy.deepcopy(valid)
not_retired["sections"][1]["nodes"][-1]["learnerOwnedArtifacts"].append("scratch.txt")
assert any("must be absent" in item
           for item in course_map.validate_course_map(not_retired, detailed=True))

# V2 proves the declared owner is the first Working that can contain an artifact.
v2 = copy.deepcopy(valid)
v2["artifactContract"]["version"] = 2
assert not course_map.validate_course_map(v2, detailed=True)
early = copy.deepcopy(v2)
early["sections"][0]["nodes"][-1]["learnerOwnedArtifacts"].append("dist/app")
assert any("before declared owner s02.working" in item
           for item in course_map.validate_course_map(early, detailed=True))
legacy_early = copy.deepcopy(valid)
legacy_early["sections"][0]["nodes"][-1]["learnerOwnedArtifacts"].append("dist/app")
assert not any("before declared owner" in item
               for item in course_map.validate_course_map(legacy_early, detailed=True))

# V2 Phase 2 also binds runtime/proof/package paths to shipped inventory entries.
alignment_contract = copy.deepcopy(v2["artifactContract"])
manifest = {"runtime": {"entryFile": "src/app.txt"}}
proof_sections = [
    {"proof": {"mode": "run", "expectedFiles": ["src/app.txt", "replace-me.txt"]}},
    {"proof": {"mode": "package", "expectedFiles": ["src/app.txt"],
               "requirementsFile": "requirements.txt", "artifactPath": "dist/app"}},
]
alignment_problems = phase2_alignment_problems(
    alignment_contract, PLAN_BODY, manifest, proof_sections)
assert any("requirements.txt" in item for item in alignment_problems)
alignment_contract["artifacts"].append({
    "artifact": "requirements.txt", "ownerWorking": "s02.working",
    "disposition": "ships",
})
complete_lifecycle = PLAN_BODY.replace(
    "`dist/app` ships.", "`dist/app` ships; `requirements.txt` ships.")
assert not phase2_alignment_problems(
    alignment_contract, complete_lifecycle, manifest, proof_sections)
assert not phase2_alignment_problems(
    {**alignment_contract, "version": 1}, "", manifest, proof_sections)

# V3 makes the Phase-1 delivery mode and exact paths immutable in Phase 2.
v3_contract = copy.deepcopy(alignment_contract)
v3_contract["version"] = 3
v3_contract["delivery"] = {
    "mode": "package", "artifact": "dist/app", "requirements": "requirements.txt"}
v3_map = copy.deepcopy(v2)
v3_map["artifactContract"] = copy.deepcopy(v3_contract)
v3_map["sections"][-1]["nodes"][-1]["learnerOwnedArtifacts"].append("requirements.txt")
assert not course_map.validate_course_map(v3_map, detailed=True)
v3_manifest = {
    "runtime": {"entryFile": "src/app.txt"},
    "acceptance": {"artifact": "package"},
}
assert not phase2_alignment_problems(
    v3_contract, V3_PLAN_BODY, v3_manifest, proof_sections)
downgraded_manifest = copy.deepcopy(v3_manifest)
downgraded_manifest["acceptance"]["artifact"] = "runtime"
assert any("must exactly preserve" in item for item in phase2_alignment_problems(
    v3_contract, V3_PLAN_BODY, downgraded_manifest, proof_sections))
run_final = copy.deepcopy(proof_sections)
run_final[-1]["proof"]["mode"] = "run"
assert any("proof mode must be package" in item for item in phase2_alignment_problems(
    v3_contract, V3_PLAN_BODY, v3_manifest, run_final))
substituted_path = copy.deepcopy(proof_sections)
substituted_path[-1]["proof"]["artifactPath"] = "dist/easier-output"
assert any("artifactPath must exactly preserve" in item for item in phase2_alignment_problems(
    v3_contract, V3_PLAN_BODY, v3_manifest, substituted_path))

print("skeleton-integrity contract tests: OK")
