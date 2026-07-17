#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""Focused tests for language-targeted Mastery 1-5 contracts."""
import copy
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from buildlib import course_map
from buildlib.workflow.checkpoints import arc_written
from buildlib.language_mastery import (authored_mastery_problems, phase1_contract_problems,
                                       seed_contract, validate_map_contract)
from buildlib.workflow.prompts import write_plan


ARC = """# BUILD PLAN — language-demo
- **Mastery (1-5):** 3
- **Language mastery contract:** 1
- **Language foundation contract:** 1

## Arc
**Language:** Python
**Graduate ledger:** The learner CAN design, test, debug, and refactor Python modules,
including routine failure recovery and verification; still CANNOT maintain a distributed Python service.
**Language mastery:** Python — Finish 3/5: independently transfer Python mechanisms into novel integrated problems and justify choices.
**Language capability spine:** language-control-flow -> language-function-boundaries -> language-collection-modeling -> language-error-recovery -> language-verification
**Language foundation coverage:** data = language-collection-modeling; control = language-control-flow; decomposition = language-function-boundaries; failure = language-error-recovery; verification = language-verification
**Language performances:** s03.working = novel-transfer + rationale: independently extend the project with a new Python data boundary; s03.working = novel-transfer: diagnose and repair an unfamiliar Python integration fault
**Mastery proof:** Python independence is graded by two distinct s03 Working requirements, with implementation withheld and one recorded rationale.
**Daily drivers:** growable collection = CAN; key-value = CAN; strings = CAN; errors = CAN.
"""
IDS = ["s01", "s02", "s03"]


assert not phase1_contract_problems(ARC, ARC, IDS)
contract = seed_contract(ARC, IDS)
assert contract["language"] == "Python" and contract["level"] == 3
assert len(contract["capabilityIds"]) == 5
assert contract["foundationCapabilities"]["failure"] == "language-error-recovery"
assert [item["id"] for item in contract["performances"]] == [
    "language-performance-s03-01", "language-performance-s03-02"]

wrong_target = ARC.replace("Python — Finish 3/5", "Pygame — Finish 3/5")
assert any("repeat **Language:**" in item
           for item in phase1_contract_problems(wrong_target, wrong_target, IDS))
project_caps = ARC.replace("language-control-flow", "player-movement")
assert any("language-*" in item
           for item in phase1_contract_problems(project_caps, project_caps, IDS))
one_performance = ARC.replace(
    "; s03.working = novel-transfer: diagnose and repair an unfamiliar Python integration fault",
    "")
assert any("at least 2" in item
           for item in phase1_contract_problems(one_performance, one_performance, IDS))
early = ARC.replace("s03.working = novel-transfer + rationale", "s01.working = novel-transfer + rationale")
assert any("must be late" in item
           for item in phase1_contract_problems(early, early, IDS))
missing_foundation = ARC.replace(
    "**Language foundation coverage:** data = language-collection-modeling; control = language-control-flow; decomposition = language-function-boundaries; failure = language-error-recovery; verification = language-verification\n",
    "")
assert any("foundation coverage" in item
           for item in phase1_contract_problems(missing_foundation, missing_foundation, IDS))
errors_scoped_out = ARC.replace("errors = CAN", "errors = CANNOT")
assert any("errors = CAN" in item
           for item in phase1_contract_problems(errors_scoped_out, errors_scoped_out, IDS))
files_are_not_verification = ARC.replace("language-verification", "language-files")
assert any("does not establish verification" in item
           for item in phase1_contract_problems(
               files_are_not_verification, files_are_not_verification, IDS))

ARC_V2 = (ARC
          .replace("**Language foundation contract:** 1",
                   "**Language foundation contract:** 2")
          .replace("language-error-recovery -> language-verification",
                   "language-error-recovery -> language-class-design -> "
                   "language-module-boundaries -> language-comprehensions -> "
                   "language-verification")
          .replace("failure = language-error-recovery; verification = language-verification",
                   "abstraction = language-class-design; modularity = "
                   "language-module-boundaries; failure = language-error-recovery; "
                   "verification = language-verification"))
assert not phase1_contract_problems(ARC_V2, ARC_V2, IDS)
contract_v2 = seed_contract(ARC_V2, IDS)
assert contract_v2["foundationVersion"] == 2
assert contract_v2["foundationCapabilities"]["abstraction"] == "language-class-design"
generic_abstraction = ARC_V2.replace("language-class-design", "language-abstraction")
assert any("concrete structured-abstraction" in item
           for item in phase1_contract_problems(
               generic_abstraction, generic_abstraction, IDS))
wrong_python_idiom = ARC_V2.replace("language-class-design", "language-record-modeling")
assert any("Python Finish 3–5" in item and "class" in item
           for item in phase1_contract_problems(
               wrong_python_idiom, wrong_python_idiom, IDS))
ARC_V2_LEVEL2 = (ARC
                 .replace("**Mastery (1-5):** 3", "**Mastery (1-5):** 2")
                 .replace("**Language foundation contract:** 1",
                          "**Language foundation contract:** 2")
                 .replace("Python — Finish 3/5", "Python — Finish 2/5"))
assert not phase1_contract_problems(ARC_V2_LEVEL2, ARC_V2_LEVEL2, IDS), (
    "Mastery 2 must retain the five-role project-first contract without forcing classes")


def mapped_contract():
    value = copy.deepcopy(contract)
    caps = value["capabilityIds"]
    value["performances"][0]["capabilityIds"] = caps[:2]
    value["performances"][1]["capabilityIds"] = caps[2:]
    sections = []
    practices = [caps[:2], caps[1:3], caps]
    for index, (sid, practice) in enumerate(zip(IDS, practices), 1):
        performance_ids = [item["id"] for item in value["performances"]
                           if item["workingId"] == f"{sid}.working"]
        sections.append({
            "id": sid, "ordinal": index, "languagePractice": practice,
            "nodes": [{"id": f"{sid}.working", "kind": "working",
                       "requires": practice, "masteryPerformances": performance_ids}],
        })
    owners = {capability: (f"s01.l{index:02d}", 1)
              for index, capability in enumerate(caps, 1)}
    return value, sections, owners


mapped, sections, owners = mapped_contract()
assert not validate_map_contract(mapped, sections, owners, mapped["capabilityIds"], True)

framework_only = copy.deepcopy(mapped)
framework_only["performances"][1]["capabilityIds"] = []
assert any("assess every foundation capability" in item
           for item in validate_map_contract(
               framework_only, sections, owners, mapped["capabilityIds"], True))

unobservable_verification = copy.deepcopy(mapped)
unobservable_verification["performances"][1]["description"] = (
    "independently extend the unfamiliar serialized storage boundary")
assert any("observable verification" in item
           for item in validate_map_contract(
               unobservable_verification, sections, owners, mapped["capabilityIds"], True))

missing_practice = copy.deepcopy(sections)
missing_practice[1]["languagePractice"] = []
assert any("languagePractice must not be empty" in item
           for item in validate_map_contract(
               mapped, missing_practice, owners, mapped["capabilityIds"], True))

not_required = copy.deepcopy(sections)
not_required[2]["nodes"][0]["requires"] = mapped["capabilityIds"][:-1]
assert any("must require" in item
           for item in validate_map_contract(
               mapped, not_required, owners, mapped["capabilityIds"], True))

project_only_graduation = ["player-movement"]
assert any("must be graduateCapabilities" in item
           for item in validate_map_contract(
               mapped, sections, owners, project_only_graduation, True))

missing_assessment = copy.deepcopy(sections)
missing_assessment[2]["nodes"][0]["masteryPerformances"] = []
assert any("masteryPerformances must exactly match" in item
           for item in validate_map_contract(
               mapped, missing_assessment, owners, mapped["capabilityIds"], True))


def mapped_v2_contract():
    value = copy.deepcopy(contract_v2)
    caps = value["capabilityIds"]
    value["performances"][0]["capabilityIds"] = caps[:4]
    value["performances"][1]["capabilityIds"] = caps[4:]
    practices = [list(caps), list(caps), list(caps)]
    mapped_sections = []
    for index, (sid, practice) in enumerate(zip(IDS, practices), 1):
        performance_ids = [item["id"] for item in value["performances"]
                           if item["workingId"] == f"{sid}.working"]
        mapped_sections.append({
            "id": sid, "ordinal": index, "languagePractice": practice,
            "nodes": [{"id": f"{sid}.working", "kind": "working",
                       "requires": practice, "masteryPerformances": performance_ids}],
        })
    mapped_owners = {capability: (f"s01.l{index:02d}", 1)
                     for index, capability in enumerate(caps, 1)}
    return value, mapped_sections, mapped_owners


mapped_v2, sections_v2, owners_v2 = mapped_v2_contract()
assert not validate_map_contract(
    mapped_v2, sections_v2, owners_v2, mapped_v2["capabilityIds"], True)
nonfoundation = "language-comprehensions"
under_practiced = copy.deepcopy(sections_v2)
under_practiced[0]["languagePractice"].remove(nonfoundation)
under_practiced[1]["languagePractice"].remove(nonfoundation)
assert any("at least two Workings" in item for item in validate_map_contract(
    mapped_v2, under_practiced, owners_v2, mapped_v2["capabilityIds"], True))
not_final = copy.deepcopy(sections_v2)
not_final[2]["nodes"][0]["requires"].remove(nonfoundation)
assert any("final Working" in item for item in validate_map_contract(
    mapped_v2, not_final, owners_v2, mapped_v2["capabilityIds"], True))
not_late_assessed = copy.deepcopy(mapped_v2)
not_late_assessed["performances"][1]["capabilityIds"].remove(nonfoundation)
assert any("every declared language capability" in item
           for item in validate_map_contract(
               not_late_assessed, sections_v2, owners_v2,
               mapped_v2["capabilityIds"], True))
late_verification_owner = copy.deepcopy(owners_v2)
verification_capability = mapped_v2["foundationCapabilities"]["verification"]
late_verification_owner[verification_capability] = ("s03.l01", 3)
assert any("verification capability" in item for item in validate_map_contract(
    mapped_v2, sections_v2, late_verification_owner,
    mapped_v2["capabilityIds"], True))

with tempfile.TemporaryDirectory() as tome:
    root = os.path.join(tome, "sections", "s03")
    os.makedirs(root)
    with open(os.path.join(root, "section.toml"), "w", encoding="utf-8") as handle:
        handle.write('id = "s03"\n')
    ids = [item["id"] for item in mapped["performances"]]
    with open(os.path.join(root, "freestyle.toml"), "w", encoding="utf-8") as handle:
        handle.write(f'''[freestyle]
masteryPerformances = {json.dumps(ids)}

[[freestyle.rubric]]
criterion = "Independent language boundary"
weight = 50
masteryPerformance = "{ids[0]}"
languageCapabilities = {json.dumps(mapped["performances"][0]["capabilityIds"])}
rationaleRequired = true

[[freestyle.rubric]]
criterion = "Independent language diagnosis"
weight = 50
masteryPerformance = "{ids[1]}"
languageCapabilities = {json.dumps(mapped["performances"][1]["capabilityIds"])}
''')
    authored_course = {
        "languageMastery": mapped,
        "sections": [{"id": "s03", "nodes": sections[2]["nodes"]}],
    }
    assert not authored_mastery_problems(authored_course, tome)
    text = open(os.path.join(root, "freestyle.toml"), encoding="utf-8").read()
    with open(os.path.join(root, "freestyle.toml"), "w", encoding="utf-8") as handle:
        handle.write(text.replace("rationaleRequired = true", "rationaleRequired = false"))
    assert any("rationaleRequired = true" in item
               for item in authored_mastery_problems(authored_course, tome))

print("language-mastery contract tests: OK")


FULL_PLAN = ARC + """
**Acceptance scenarios:** boots-clean -> language-transfer-proved
**Continuity map:** s01 -> s03: preserve the language module boundary through final transfer
**Artifact lifecycle:** no temporary artifact ships
**Section list:**
1. **s01 — Learn the Language Core:** establish language values, control, and function boundaries
2. **s02 — Model a Useful System:** apply language collections and error boundaries in the project
3. **s03 — Transfer Independently:** solve novel project requirements through independent language use
"""


with tempfile.TemporaryDirectory() as root:
    old_build, old_repo = course_map.BUILD_DIR, course_map.REPO
    course_map.BUILD_DIR, course_map.REPO = os.path.join(root, ".tome-build"), root
    os.makedirs(course_map.BUILD_DIR)
    plan = os.path.join(course_map.BUILD_DIR, "language-demo.plan.md")
    with open(plan, "w", encoding="utf-8") as handle:
        handle.write(FULL_PLAN)
    try:
        seed = course_map.seed_course_map("language-demo", plan)
        assert "including routine failure recovery" in seed["graduateContract"]
        proposal = copy.deepcopy(seed)
        language_caps = proposal["languageMastery"]["capabilityIds"]
        domain_caps = [f"project-capability-{index}" for index in range(1, 5)]
        proposal["graduateCapabilities"] = language_caps + domain_caps
        owned = [
            [language_caps[0], language_caps[1], domain_caps[0]],
            [language_caps[2], language_caps[3], domain_caps[1]],
            [language_caps[4], domain_caps[2], domain_caps[3]],
        ]
        practices = [language_caps[:2], language_caps[1:4], language_caps]
        taught_so_far = []
        for number, section in enumerate(proposal["sections"], 1):
            sid = section["id"]
            section["capabilities"] = owned[number - 1]
            section["languagePractice"] = practices[number - 1]
            section["dependsOn"] = [] if number == 1 else [f"s{number - 1:02d}"]
            section["nodes"] = []
            for lesson_number, capability in enumerate(owned[number - 1], 1):
                section["nodes"].append({
                    "id": f"{sid}.l{lesson_number:02d}", "kind": "lesson",
                    "title": f"Language Lesson {number}.{lesson_number}",
                    "teaches": [capability],
                    "introduces": [],
                    "validationDependencies": [],
                    "dependsOn": ([] if number == 1 and lesson_number == 1 else
                                  [f"{sid}.l{lesson_number - 1:02d}"] if lesson_number > 1 else
                                  [f"s{number - 1:02d}.working"]),
                    "doneWhen": {"checks": ["learner-construction", "lesson-source"]},
                })
            taught_so_far += owned[number - 1]
            performance_ids = [item["id"] for item in proposal["languageMastery"]["performances"]
                               if item["workingId"] == f"{sid}.working"]
            section["nodes"].append({
                "id": f"{sid}.working", "kind": "working", "title": f"Working {number}",
                "requires": list(dict.fromkeys(taught_so_far + practices[number - 1])),
                "mechanisms": [],
                "validationDependencies": [],
                "dependsOn": [f"{sid}.l03"],
                "projectMilestone": section["projectMilestone"],
                "learnerOwnedArtifacts": [f"src/stage_{number}.txt"],
                "masteryPerformances": performance_ids,
                "doneWhen": {"checks": ["learner-construction", "working-replay"]},
            })
        proposal["languageMastery"]["performances"][0]["capabilityIds"] = language_caps[:2]
        proposal["languageMastery"]["performances"][1]["capabilityIds"] = language_caps[2:]
        obligation = proposal["plannedObligations"][0]
        obligation["doneWhen"] = {
            "evidenceLocations": ["freestyle.toml"],
            "capabilityIds": [language_caps[-1]], "proofIds": ["s03"],
            "acceptanceIds": ["language-transfer-proved"],
            "observedResult": "The final Working preserves and independently extends the boundary.",
        }
        problems = course_map.validate_course_map(proposal, detailed=True, seed=seed)
        assert not problems, "\n".join(problems)
        for sid, relative in (("s01", "section.toml"), ("s03", "freestyle.toml")):
            path = os.path.join(root, "tomes", "language-demo", "sections", sid, relative)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write('title="placeholder"\n')
        with open(course_map.proposal_path("language-demo"), "w", encoding="utf-8") as handle:
            json.dump(proposal, handle)
        sealed = course_map.seal_course_map("language-demo")
        assert sealed["languageMastery"]["level"] == 3
    finally:
        course_map.BUILD_DIR, course_map.REPO = old_build, old_repo

print("language-mastery sealed-map integration tests: OK")


COMPLETE_ARC = """
**Finished tool:** A tested command-line field journal built by the learner in Python.
**Language:** Python
**Project name:** Field Journal
**Mentor persona:** A patient systems cartographer who explains failures precisely.
**Student term:** apprentice cartographer
**Visual identity:** Ink blue, parchment cream, and compact map-grid ornament.
**Tooling fit:** external — COMPATIBLE: Python and its test runner are installed, taught, and diagnosed through the real terminal workflow.
**Difficulty spine:** Python data modeling, function boundaries, collection choice, error recovery, and deterministic testing at the selected finish.
**Graduate ledger:** The learner CAN design classes, compose modules, test, debug, and refactor Python independently; still CANNOT maintain a distributed Python service.
**Language mastery:** Python — Finish 3/5: independently transfer Python mechanisms into novel integrated problems and justify choices.
**Language capability spine:** language-syntax-values -> language-control-flow -> language-functions -> language-scope -> language-collections -> language-comprehensions -> language-iteration -> language-class-objects -> language-composition -> language-modules-packages -> language-import-boundaries -> language-typing -> language-files-paths -> language-json-data-serialization -> language-standard-library-pathlib -> language-exceptions -> language-context-resources -> language-testing-verification -> language-debug-diagnosis -> language-environment-venv -> language-cli-argparse -> language-packaging-pyproject
**Language foundation coverage:** data = language-collections; control = language-control-flow; decomposition = language-functions; abstraction = language-class-objects; modularity = language-modules-packages; failure = language-exceptions; verification = language-testing-verification
**Language performances:** s03.working = novel-transfer + rationale: independently extend the project with a new Python data boundary; s03.working = novel-transfer: diagnose and repair an unfamiliar Python integration fault
**Mastery proof:** Python independence is graded by two distinct s03 Working requirements with implementation withheld, observable tests, and a recorded rationale for the data boundary.
**Daily drivers:** growable collection = CAN; key-value = CAN; strings = CAN; errors = CAN.
**Continuity map:** s01 -> s03: preserve the public Python module boundary and error contract through final transfer
**Artifact lifecycle:** `src/journal.py` deliberately ships; `dist/journal` deliberately ships; `requirements.txt` deliberately ships; s01 temporary debug output is removed in s03.
**Artifact ownership:** src/journal.py @ s01.working -> ships; dist/journal @ s03.working -> ships; requirements.txt @ s03.working -> ships
**Delivery contract:** mode = package; artifact = dist/journal; requirements = requirements.txt
**Acceptance proof:** From a clean folder, create the Python package, run its tests, record and query journal data, recover from a malformed record, complete the novel extension, and launch the delivered command.
**Acceptance scenarios:** creates-package -> records-entry -> recovers-error -> language-transfer-proved
**Section list:**
1. **s01 — Establish Python Foundations:** establish language-syntax-values, language-control-flow, language-functions, language-scope, language-testing-verification, language-debug-diagnosis, and language-environment-venv
2. **s02 — Model Journal Data:** teach language-collections, language-comprehensions, language-iteration, language-class-objects, language-composition, language-modules-packages, language-import-boundaries, language-typing, language-files-paths, language-json-data-serialization, language-standard-library-pathlib, language-exceptions, and language-context-resources
3. **s03 — Transfer and Deliver:** apply language-cli-argparse and language-packaging-pyproject in independent delivery
"""

with tempfile.TemporaryDirectory() as root:
    plan = os.path.join(root, "complete.plan.md")
    answers = [("Prior knowledge", "none"), ("Starting level (1-10)", "2"),
               ("Project scope (1-5)", "3"), ("Lesson depth (1-10)", "7"),
               ("Mastery (1-5)", "3"), ("Tooling", "external")]
    write_plan(plan, "complete", answers, "Teach Python through a field journal")
    with open(plan, "a", encoding="utf-8") as handle:
        handle.write(COMPLETE_ARC)
    clean, report = arc_written(plan, "complete.plan.md")
    assert clean, report
    with open(plan, encoding="utf-8") as handle:
        profiled = seed_contract(handle.read(), IDS)
    assert profiled["coverageProfileVersion"] == 1
    assert "packaging" in profiled["coverageAreaIds"]
    assert len(profiled["capabilityIds"]) >= 14
    base = open(plan, encoding="utf-8").read()
    with open(plan, "w", encoding="utf-8") as handle:
        handle.write(base.replace(
            "language-environment-venv -> language-cli-argparse",
            "language-environment-cli-argparse"))
    clean, report = arc_written(plan, "complete.plan.md")
    assert not clean and "distinct capability ids" in report
    late_verification = base.replace(
        ", language-testing-verification, language-debug-diagnosis",
        ", language-debug-diagnosis").replace(
            "apply language-cli-argparse and language-packaging-pyproject",
            "apply language-testing-verification, language-cli-argparse, and "
            "language-packaging-pyproject")
    with open(plan, "w", encoding="utf-8") as handle:
        handle.write(late_verification)
    clean, report = arc_written(plan, "complete.plan.md")
    assert not clean and "verification cadence is too late" in report
    with open(plan, "w", encoding="utf-8") as handle:
        handle.write(base)
    no_verification = open(plan, encoding="utf-8").read().replace(
        "diagnose and repair an unfamiliar Python integration fault",
        "repair an unfamiliar Python integration fault")
    with open(plan, "w", encoding="utf-8") as handle:
        handle.write(no_verification)
    clean, report = arc_written(plan, "complete.plan.md")
    assert not clean and "observable verification" in report
    with open(plan, "w", encoding="utf-8") as handle:
        handle.write(no_verification.replace(
            "repair an unfamiliar Python integration fault",
            "diagnose and repair an unfamiliar Python integration fault"))
    text = open(plan, encoding="utf-8").read()
    with open(plan, "w", encoding="utf-8") as handle:
        handle.write(text.replace(
            "**Language capability spine:** language-syntax-values -> language-control-flow -> language-functions -> language-scope -> language-collections -> language-comprehensions -> language-iteration -> language-class-objects -> language-composition -> language-modules-packages -> language-import-boundaries -> language-typing -> language-files-paths -> language-json-data-serialization -> language-standard-library-pathlib -> language-exceptions -> language-context-resources -> language-testing-verification -> language-debug-diagnosis -> language-environment-venv -> language-cli-argparse -> language-packaging-pyproject\n",
            ""))
    clean, report = arc_written(plan, "complete.plan.md")
    assert not clean and "Language capability spine" in report

print("language-mastery Phase-1 checkpoint tests: OK")
