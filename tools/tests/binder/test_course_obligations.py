#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""Negative and lifecycle regressions for discovered and planned obligations."""
import copy
import json
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from buildlib import continuity, course_map
from buildlib.course import state as course_state
from buildlib.prerequisites import review as prerequisite_review


PLAN = """# BUILD PLAN — obligations
**Graduate ledger:** The learner owns four cumulative capabilities and ships the result.
**Mastery proof:** The final Working independently integrates every prior contract.
**Acceptance scenarios:** starts-clean -> ships
**Continuity map:**
s01 -> s04: preserve the first public contract through final delivery
**Artifact lifecycle:** s01's temporary probe is retired in s03
**Section list:**
1. **s01 — Establish:** establish the first durable contract
2. **s02 — Extend:** extend the project without breaking the first contract
3. **s03 — Retire:** retire temporary scaffolding and integrate persistence
4. **s04 — Ship:** deliver the complete cumulative project
"""


def detailed(seed):
    value = copy.deepcopy(seed)
    value["graduateCapabilities"] = [f"cap-{number}" for number in range(1, 5)]
    cumulative = []
    for number, section in enumerate(value["sections"], 1):
        sid, capability = section["id"], f"cap-{number}"
        capabilities = [capability, f"{capability}-practice", f"{capability}-proof"]
        cumulative.extend(capabilities)
        section["capabilities"] = capabilities
        section["dependsOn"] = [] if number == 1 else [f"s{number - 1:02d}"]
        lessons = [{
            "id": f"{sid}.l{index:02d}", "kind": "lesson",
            "introduces": [],
            "title": f"Lesson {number}.{index}", "teaches": [owned],
            "dependsOn": ([] if number == 1 else [f"s{number - 1:02d}.working"])
            if index == 1 else [f"{sid}.l{index - 1:02d}"],
            "validationDependencies": [],
            "doneWhen": {"checks": ["lesson-source", "learner-construction"]},
        } for index, owned in enumerate(capabilities, 1)]
        working = {
            "id": f"{sid}.working", "kind": "working", "title": f"Working {number}",
            "mechanisms": [],
            "requires": list(cumulative), "dependsOn": [lessons[-1]["id"]],
            "validationDependencies": [],
            "projectMilestone": section["projectMilestone"],
            "learnerOwnedArtifacts": [f"src/{sid}.txt"],
            "doneWhen": {"checks": ["working-replay", "learner-construction"]},
        }
        section["nodes"] = [*lessons, working]
    for obligation in value["plannedObligations"]:
        target = obligation["target"]
        obligation.update({
            "owner": "first public contract" if obligation["kind"] != "temporary-retirement"
                     else "temporary probe",
            "location": "lessons/l01.toml",
            "reason": "The target integration must prove this approved Arc contract.",
            "doneWhen": {
                "evidenceLocations": ["lessons/l01.toml"],
                "capabilityIds": [f"cap-{int(target[1:])}"],
                "proofIds": [target], "acceptanceIds": [],
                "observedResult": "The target proof demonstrates the required contract.",
            },
        })
    return value


def discovered():
    return {
        "id": "s01-discovered-save-contract", "origin": "s01", "target": "s03",
        "kind": "future-requirement", "owner": "save contract",
        "location": "lessons/l01.toml",
        "requirement": "Preserve the discovered save contract through persistence integration.",
        "reason": "The persistence milestone consumes the contract discovered in s01.",
        "doneWhen": {
            "evidenceLocations": ["lessons/l01.toml"], "capabilityIds": ["cap-3"],
            "proofIds": ["s03"], "acceptanceIds": [],
            "observedResult": "The persistence proof preserves the discovered save contract.",
        },
    }


def fulfillment(item, location="lessons/l01.toml"):
    done = item["doneWhen"]
    return {
        "id": item["id"], "evidence_locations": [location],
        "capability_ids": list(done["capabilityIds"]),
        "proof_ids": list(done["proofIds"]),
        "acceptance_ids": list(done["acceptanceIds"]),
        "observed_result": "The executable target proof observed the required behavior.",
    }


def write(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(value, indent=2) + "\n" if not isinstance(value, str) else value
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


with tempfile.TemporaryDirectory() as root:
    build_dir = os.path.join(root, ".tome-build")
    os.makedirs(build_dir)
    modules = (course_map, course_state, continuity, prerequisite_review)
    previous = [(module, module.BUILD_DIR, module.REPO) for module in modules]
    for module in modules:
        module.BUILD_DIR, module.REPO = build_dir, root
    try:
        plan = os.path.join(build_dir, "demo.plan.md")
        write(plan, PLAN)
        seed = course_map.seed_course_map("demo", plan)
        proposal = detailed(seed)
        for sid in ("s01", "s02", "s03", "s04"):
            write(os.path.join(root, "tomes", "demo", "sections", sid,
                               "lessons", "l01.toml"), '[[lessons]]\nid="placeholder"\n')
        write(course_map.proposal_path("demo"), proposal)
        course = course_map.seal_course_map("demo")
        write(os.path.join(build_dir, "demo.launch.json"), {
            "gate": {"prior_level": "5"},
            "validator": {"kind": "codex-cli", "model": "validator"},
        })
        write(os.path.join(root, "tomes", "demo", "tome.toml"),
              '[meta]\nid="demo"\n[content]\nsections=["s01","s02","s03","s04"]\n')
        for section in course["sections"]:
            sid = section["id"]
            section_root = os.path.join(root, "tomes", "demo", "sections", sid)
            write(os.path.join(section_root, "section.toml"),
                  f'id="{sid}"\n[proof]\nmechanisms=[]\n')
            for index, capability in enumerate(section["capabilities"], 1):
                write(os.path.join(section_root, "lessons", f"l{index:02d}.toml"),
                      f'[[lessons]]\nid="{sid}-l{index:02d}"\ntitle="Lesson"\n'
                      f'teaches=["{capability}"]\nintroduces=[]\n')
            working = next(node for node in section["nodes"] if node["kind"] == "working")
            requires = json.dumps(working["requires"])
            write(os.path.join(section_root, "freestyle.toml"),
                  f'[freestyle]\ntitle="Working"\nrequires={requires}\nmechanisms=[]\n')
            write(continuity.handoff_path("demo", sid),
                  continuity.handoff_skeleton(sid, ["s01", "s02", "s03", "s04"],
                                              plan_path=plan, course=course))

        s01_path = continuity.handoff_path("demo", "s01")
        s01 = continuity.read_handoff("demo", "s01")
        s01["artifact_state"] = "The first cumulative contract exists and has executable proof."
        s01["discoveries"].append(discovered())
        write(s01_path, s01)

        # V2 handoffs with exact projected map copies remain readable, but derived state
        # sees only the author-owned discovery.
        legacy_course = copy.deepcopy(course)
        legacy_planned = next(item for item in legacy_course["plannedObligations"]
                              if item["origin"] == "s01")
        legacy_planned["location"] = "sections/s01"
        legacy_handoff = {key: copy.deepcopy(value) for key, value in s01.items()
                          if key != "discoveries"}
        legacy_handoff["version"] = 2
        legacy_handoff["obligations"] = [legacy_planned, *copy.deepcopy(s01["discoveries"])]
        write(s01_path, legacy_handoff)
        with patch.object(continuity, "_map", return_value=("demo", legacy_course)):
            clean, report = continuity.validate_handoff(
                "demo", "s01", ["s01", "s02", "s03", "s04"], plan)
            assert clean, report
            bad_discovery = copy.deepcopy(legacy_handoff)
            next(item for item in bad_discovery["obligations"]
                 if item["id"] == "s01-discovered-save-contract")["location"] = "sections/s01"
            write(s01_path, bad_discovery)
            clean, report = continuity.validate_handoff(
                "demo", "s01", ["s01", "s02", "s03", "s04"], plan)
            assert not clean and "must name an existing current-section file" in report
        write(s01_path, s01)

        migratable = copy.deepcopy(legacy_handoff)
        migratable["obligations"][0] = copy.deepcopy(next(
            item for item in course["plannedObligations"] if item["origin"] == "s01"))
        write(s01_path, migratable)
        continuity.prepare_handoff(
            "demo", "s01", ids=["s01", "s02", "s03", "s04"], plan_path=plan)
        upgraded = continuity.read_handoff("demo", "s01")
        assert upgraded["version"] == 3
        assert upgraded["discoveries"] == s01["discoveries"]
        assert all(item["id"] != migratable["obligations"][0]["id"]
                   for item in upgraded["discoveries"])
        write(s01_path, s01)

        copied = copy.deepcopy(s01)
        copied["discoveries"].append(next(
            item for item in course["plannedObligations"] if item["origin"] == "s01"))
        write(s01_path, copied)
        clean, report = continuity.validate_handoff(
            "demo", "s01", ["s01", "s02", "s03", "s04"], plan)
        assert not clean and "planned work is harness-projected" in report
        write(s01_path, s01)

        # Discovered claims are not ledger truth until the origin section is harness-verified.
        before = course_state.derive_course_state("demo")
        assert before["sections"][0]["status"] == "authored"
        assert "s01-discovered-save-contract" not in {
            item["id"] for item in before["activeObligations"]}

        authored_mark = copy.deepcopy(s01)
        authored_mark["public_contracts"] = [{"name": "contract", "location": "lessons/l01.toml",
                                                "promise": "kept", "complete": True}]
        write(s01_path, authored_mark)
        clean, report = continuity.validate_handoff("demo", "s01",
                                                     ["s01", "s02", "s03", "s04"], plan)
        assert not clean and "completion/checkmark" in report
        oversized = copy.deepcopy(s01)
        oversized["discoveries"][-1]["reason"] = "x" * 501
        write(s01_path, oversized)
        clean, report = continuity.validate_handoff("demo", "s01",
                                                     ["s01", "s02", "s03", "s04"], plan)
        assert not clean and "reason exceeds 500 characters" in report
        write(s01_path, s01)
        course_state.record_section_verification("demo", "s01", "origin checks passed")
        accepted = course_state.derive_course_state("demo")
        assert "s01-discovered-save-contract" in {
            item["id"] for item in accepted["activeObligations"]}

        # A claim one section early is explicitly rejected.
        s02_path = continuity.handoff_path("demo", "s02")
        s02 = continuity.read_handoff("demo", "s02")
        s02["artifact_state"] = "The second section extends the cumulative executable project."
        s02["fulfillments"] = [fulfillment(discovered())]
        write(s02_path, s02)
        clean, report = continuity.validate_handoff("demo", "s02",
                                                     ["s01", "s02", "s03", "s04"], plan)
        assert not clean and "not-yet-due" in report
        s02["fulfillments"] = []
        write(s02_path, s02)
        course_state.record_section_verification("demo", "s02", "middle checks passed")

        # The due section cannot pass with placeholders or nonexistent evidence.
        s03_path = continuity.handoff_path("demo", "s03")
        s03 = continuity.read_handoff("demo", "s03")
        s03["artifact_state"] = "Persistence now replaces the temporary probe with real behavior."
        write(s03_path, s03)
        try:
            course_state.record_section_verification("demo", "s03", "claimed checks")
            raise AssertionError("missing due fulfillment created a checkmark")
        except ValueError as exc:
            assert "fulfillments is missing obligations due now" in str(exc)
        due_s03 = [item for item in [*course["plannedObligations"], discovered()]
                   if item["target"] == "s03"]
        s03["fulfillments"] = [fulfillment(item) for item in due_s03]
        s03["fulfillments"][0]["evidence_locations"] = ["missing.toml"]
        write(s03_path, s03)
        clean, report = continuity.validate_handoff("demo", "s03",
                                                     ["s01", "s02", "s03", "s04"], plan)
        assert not clean and "does not exist" in report
        s03["fulfillments"] = [fulfillment(item) for item in due_s03]
        write(s03_path, s03)
        state = course_state.record_section_verification("demo", "s03", "due proofs passed")
        assert not any(item["target"] == "s03" for item in state["activeObligations"])
        assert {item["kind"] for item in state["closedArchive"]} >= {
            "temporary-retirement", "future-requirement"}

        # The final section cannot create future work and must close the remaining ledger.
        s04_path = continuity.handoff_path("demo", "s04")
        s04 = continuity.read_handoff("demo", "s04")
        s04["artifact_state"] = "The fourth section packages the complete cumulative project."
        s04["discoveries"] = [dict(discovered(), id="s04-impossible-future", origin="s04")]
        write(s04_path, s04)
        clean, report = continuity.validate_handoff("demo", "s04",
                                                     ["s01", "s02", "s03", "s04"], plan)
        assert not clean and "final section may not create" in report
        s04["discoveries"] = []
        due_s04 = [item for item in course["plannedObligations"] if item["target"] == "s04"]
        s04["fulfillments"] = [fulfillment(item) for item in due_s04]
        write(s04_path, s04)
        finished = course_state.record_section_verification("demo", "s04", "shipping checks passed")
        assert not finished["activeObligations"]
        assert len(finished["closedArchive"]) == 3
    finally:
        for module, build, repo in previous:
            module.BUILD_DIR, module.REPO = build, repo

print("course obligation lifecycle tests: OK")
