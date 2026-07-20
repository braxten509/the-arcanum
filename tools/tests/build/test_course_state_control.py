#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""Derived state, self-pruning obligations, evidence invalidation, and prompt tail."""
import copy
import json
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from buildlib import continuity, course_map
from buildlib.course.amend import amend_course_map
from buildlib.course import control as course_control
from buildlib.course import state as course_state
from buildlib.prerequisites import review as prerequisite_review


PLAN = """# BUILD PLAN — demo
**Graduate ledger:** The learner can own all three cumulative capabilities.
**Mastery proof:** The final Working independently integrates all taught capabilities.
**Acceptance scenarios:** clean-start -> delivered
**Continuity map:**
s01 -> s03: preserve the first public contract in the delivered integration
**Artifact lifecycle:** all temporary examples retire before delivery
**Section list:**
1. **s01 — First Capability:** build the stable first public capability contract
2. **s02 — Middle Capability:** extend the artifact with a separate middle capability
3. **s03 — Delivered Integration:** integrate and deliver every cumulative capability
"""


def make_map(seed):
    value = copy.deepcopy(seed)
    value["graduateCapabilities"] = ["cap-one", "cap-two", "cap-three"]
    cumulative = []
    for number, section in enumerate(value["sections"], 1):
        sid, capability = section["id"], f"cap-{'one two three'.split()[number - 1]}"
        capabilities = [capability, f"{capability}-practice", f"{capability}-proof"]
        cumulative.extend(capabilities)
        section["capabilities"] = capabilities
        section["dependsOn"] = [] if number == 1 else [f"s{number - 1:02d}"]
        lessons = [{"id": f"{sid}.l{index:02d}", "kind": "lesson",
                    "title": f"Lesson {number}.{index}", "teaches": [owned],
                    "introduces": [],
                    "dependsOn": ([] if number == 1 else [f"s{number - 1:02d}.working"])
                    if index == 1 else [f"{sid}.l{index - 1:02d}"],
                    "validationDependencies": [],
                    "doneWhen": {"checks": ["lesson-source", "learner-construction"]}}
                   for index, owned in enumerate(capabilities, 1)]
        working = {"id": f"{sid}.working", "kind": "working", "title": f"Working {number}",
                   "requires": list(cumulative), "dependsOn": [lessons[-1]["id"]],
                   "mechanisms": [],
                   "validationDependencies": [],
                   "projectMilestone": section["projectMilestone"],
                   "learnerOwnedArtifacts": [f"src/{sid}.txt"],
                   "doneWhen": {"checks": ["working-replay", "learner-construction"]}}
        section["nodes"] = [*lessons, working]
    obligation = value["plannedObligations"][0]
    obligation.update({"owner": "first public contract", "location": "lessons/l01.toml",
                       "reason": "The delivered integration consumes the first contract.",
                       "doneWhen": {"evidenceLocations": ["lessons/l01.toml"],
                                    "capabilityIds": ["cap-three"], "proofIds": ["s03"],
                                    "acceptanceIds": ["delivered"],
                                    "observedResult": "The delivery preserves the first contract."}})
    return value


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def handoff(course, sid):
    planned = course["plannedObligations"]
    data = {"version": 3, "section": sid,
            "artifact_state": f"The cumulative learner artifact is valid after {sid}.",
            "public_contracts": [],
            "discoveries": [],
            "fulfillments": []}
    if sid == "s03":
        data["fulfillments"] = [{"id": planned[0]["id"],
                                 "evidence_locations": ["lessons/l01.toml"],
                                 "capability_ids": ["cap-three"], "proof_ids": ["s03"],
                                 "acceptance_ids": ["delivered"],
                                 "observed_result": "The delivered proof preserved the contract."}]
    return data


with tempfile.TemporaryDirectory() as root:
    build = os.path.join(root, ".tome-build")
    os.makedirs(build)
    modules = (course_map, course_state, continuity, prerequisite_review, course_control)
    old = [(module, module.BUILD_DIR, module.REPO) for module in modules]
    for module in modules:
        module.BUILD_DIR, module.REPO = build, root
    try:
        plan = os.path.join(build, "demo.plan.md")
        write(plan, PLAN)
        seed = course_map.seed_course_map("demo", plan)
        proposal = make_map(seed)
        for sid in ("s01", "s02", "s03"):
            write(os.path.join(root, "tomes", "demo", "sections", sid,
                               "lessons", "l01.toml"), '[[lessons]]\nid="placeholder"\n')
        write(course_map.proposal_path("demo"), json.dumps(proposal))
        course = course_map.seal_course_map("demo")
        write(os.path.join(build, "demo.launch.json"), json.dumps({
            "gate": {"prior_level": "5"},
            "validator": {"kind": "codex-cli", "model": "validator"},
        }))
        write(os.path.join(root, "tomes", "demo", "tome.toml"),
              '[meta]\nid="demo"\n[content]\nsections=["s01","s02","s03"]\n')
        for number, section in enumerate(course["sections"], 1):
            sid = section["id"]
            write(os.path.join(root, "tomes", "demo", "sections", sid, "section.toml"),
                  f'id="{sid}"\ntitle="Section {number}"\n[proof]\nmechanisms=[]\n')
            working = next(node for node in section["nodes"] if node["kind"] == "working")
            required = ",".join(json.dumps(item) for item in working["requires"])
            write(os.path.join(root, "tomes", "demo", "sections", sid, "freestyle.toml"),
                  f'[freestyle]\ntitle="Working {number}"\nrequires=[{required}]\nmechanisms=[]\n')
            for index, capability in enumerate(section["capabilities"], 1):
                write(os.path.join(root, "tomes", "demo", "sections", sid, "lessons",
                                   f"l{index:02d}.toml"),
                      f'[[lessons]]\nid="{sid}-l{index:02d}"\ntitle="Lesson {number}.{index}"\n'
                      f'teaches=["{capability}"]\nintroduces=[]\n')
            write(continuity.handoff_path("demo", sid), json.dumps(handoff(course, sid)))

        write(os.path.join(build, "demo.section-progress.json"),
              json.dumps({"section": "s01", "index": 1, "total": 3,
                          "state": "validating"}))
        course_state.record_section_verification("demo", "s01", "all deterministic checks passed")
        state = course_state.derive_course_state("demo")
        assert state["sections"][0]["status"] == "verified"
        assert [item["id"] for item in state["activeObligations"]] == [
            "s01-plan-s03-01"]
        failed = course_state.record_section_failure("demo", "s01", "injected gate failure")
        assert failed["sections"][0]["status"] == "blocked"
        assert not os.path.exists(course_state.receipt_path("demo", "s01"))
        archived = os.listdir(os.path.join(root, "validator-failures", "demo"))
        assert len(archived) == 1 and archived[0].endswith(".json")
        with open(os.path.join(root, "validator-failures", "demo", archived[0]),
                  encoding="utf-8") as handle:
            failure_record = json.load(handle)
        assert failure_record["kind"] == "section-gate"
        assert failure_record["recordedAt"].endswith("Z")
        assert failure_record["reasons"] == ["injected gate failure"]
        course_state.record_section_verification("demo", "s01", "repaired checks passed")

        write(os.path.join(build, "demo.section-progress.json"),
              json.dumps({"section": "s02", "index": 2, "total": 3,
                          "state": "authoring"}))
        original_obligation = course["plannedObligations"][0]
        replacement = copy.deepcopy(original_obligation)
        replacement.update({
            "id": "s02-plan-s03-consolidated", "origin": "s02",
            "owner": "consolidated public contract", "location": "lessons/l01.toml",
            "requirement": "Preserve the consolidated public contract in delivery.",
            "reason": "An audited discovery consolidated the active delivery contract.",
            "supersedes": original_obligation["id"],
            "revisionReason": "Consolidate the active contract without erasing its audit history.",
        })
        candidate = copy.deepcopy(course_map.load_course_map("demo"))
        candidate["plannedObligations"].append(replacement)
        course = amend_course_map(
            "demo", candidate, "Consolidate an active obligation through the audited path")
        amended_state = course_state.derive_course_state("demo")
        assert amended_state["sections"][0]["status"] == "verified"
        assert [item["id"] for item in amended_state["activeObligations"]] == [replacement["id"]]
        assert any(item["id"] == original_obligation["id"]
                   and item["status"] == "superseded"
                   for item in amended_state["closedArchive"])
        s03_handoff = continuity.read_handoff("demo", "s03")
        s03_handoff["fulfillments"] = [{
            "id": replacement["id"], "evidence_locations": ["lessons/l01.toml"],
            "capability_ids": ["cap-three"], "proof_ids": ["s03"],
            "acceptance_ids": ["delivered"],
            "observed_result": "The delivery preserved the consolidated contract.",
        }]
        write(continuity.handoff_path("demo", "s03"), json.dumps(s03_handoff))
        tail = course_control.prompt_tail("demo", "s02", log=False)
        assert "LATER s03 — s02-plan-s03-consolidated" in tail
        assert "s01-plan-s03-01" not in tail
        assert "- s01 -> s01.working @ tomes/demo/sections/s01/freestyle.toml" in tail
        assert tail.endswith(course_control.END_MARKER)
        assert course_control.prompt_tail("demo", "s02", log=False) == tail
        for prefix in ("initial", "next", "repair", "resume", "model switch", "premature stop"):
            assert course_control.append_course_control(prefix, "demo", "s02", log=False).endswith(tail)

        before = course_state.derive_course_state("demo")
        os.remove(course_state.state_path("demo"))
        rebuilt = course_state.derive_course_state("demo")
        assert rebuilt["sourceDigest"] == before["sourceDigest"]
        write(course_state.state_path("demo"), '{"complete":true}')
        assert course_state.derive_course_state("demo")["sections"][0]["status"] == "verified"

        course_state.record_section_verification("demo", "s02", "all checks passed")
        write(os.path.join(build, "demo.section-progress.json"),
              json.dumps({"section": "s03", "index": 3, "total": 3,
                          "state": "validating"}))
        finished = course_state.record_section_verification("demo", "s03", "all checks passed")
        assert not finished["activeObligations"]
        assert {item["status"] for item in finished["closedArchive"]} == {
            "closed", "superseded"}

        with open(os.path.join(root, "tomes", "demo", "sections", "s01", "lessons", "l01.toml"),
                  "a", encoding="utf-8") as handle:
            handle.write("# evidence changed\n")
        stale = course_state.derive_course_state("demo")
        assert [row["status"] for row in stale["sections"]] == ["blocked", "blocked", "blocked"]
        assert stale["activeObligations"][0]["id"] == "s02-plan-s03-consolidated"
        with patch.object(prerequisite_review, "review_prerequisites",
                          return_value={"status": "PASS"}) as section_audit:
            refreshed = course_state.refresh_course_verifications(
                "demo", "clean cumulative replay")
        assert section_audit.call_count == 3
        assert [row["status"] for row in refreshed["sections"]] == [
            "verified", "verified", "verified"]
        assert not refreshed["activeObligations"]

        candidate = copy.deepcopy(course_map.load_course_map("demo"))
        candidate["sections"][2]["title"] = "Audited Delivered Integration"
        amend_course_map(
            "demo", candidate, "Clarify only the final integration title after review")
        amended = course_state.derive_course_state("demo")
        assert [row["status"] for row in amended["sections"]] == [
            "verified", "verified", "current"]
        journal = course_map._read_json(course_map.amendment_path("demo"))
        assert journal[-1]["carriedSections"] == ["s01", "s02"]
        course_state.record_section_verification("demo", "s03", "amended final proof passed")

        manifest = os.path.join(root, "tomes", "demo", "tome.toml")
        with open(manifest, "a", encoding="utf-8") as handle:
            handle.write("# shared course evidence changed\n")
        shared_stale = course_state.derive_course_state("demo")
        assert [row["status"] for row in shared_stale["sections"]] == [
            "blocked", "blocked", "blocked"]
        with patch.object(prerequisite_review, "review_prerequisites",
                          return_value={"status": "PASS"}) as section_audit:
            shared_refreshed = course_state.refresh_course_verifications(
                "demo", "clean replay after shared evidence change")
        assert section_audit.call_count == 3
        assert all(row["status"] == "verified" for row in shared_refreshed["sections"])

    finally:
        for module, build_dir, repo in old:
            module.BUILD_DIR, module.REPO = build_dir, repo

print("course-state/control/obligation tests: OK")
