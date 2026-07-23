"""Language-neutral Phase-2 mechanism and artifact-production audit.

The course map says what each lesson introduces and each Working demands.  This
sidecar makes the author's prerequisite reasoning explicit enough for the
harness to check before Validator AI: concrete mechanisms have stable
lesson-level pedagogical families and dependencies, and every newly owned
artifact names how it is produced. A family may contain multiple mechanisms in
one teach-practice-observe loop; it is not one category per verb or transition.
"""
from __future__ import annotations

import json
import os
import re

from .. import BUILD_DIR
from ..phase2.research import MAX_SOURCES


AUDIT_KEYS_V1 = {"version", "mechanisms", "artifactProduction"}
AUDIT_KEYS_V2 = AUDIT_KEYS_V1 | {
    "capabilityCoverage", "continuityCoverage", "failurePaths"}
MECHANISM_KEYS_V1 = {"id", "family", "dependsOn"}
MECHANISM_KEYS_V2 = MECHANISM_KEYS_V1 | {"productionDependsOn"}
# Long-running harnesses may retain the v1 function body while a source update is
# installed. Keep the old globals as compatibility aliases so their next mechanical
# repeat remains valid instead of becoming an infrastructure failure.
AUDIT_KEYS = AUDIT_KEYS_V1
MECHANISM_KEYS = MECHANISM_KEYS_V1
PRODUCTION_KEYS = {"artifact", "ownerWorking", "mode", "inputs", "mechanisms"}
CAPABILITY_COVERAGE_KEYS = {"capability", "mechanisms"}
CONTINUITY_COVERAGE_KEYS = {"obligation", "mechanisms"}
FAILURE_PATH_KEYS = {"id", "status", "branches", "diagnostics", "cleanup"}
PRODUCTION_MODES = {"authored", "generated", "copied", "packaged"}
ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
FAMILY_LIMITS = {1: 1, 2: 2, 3: 3}
ARTIFACT_INPUT_POLICIES = {
    "authored": "forbidden",
    "generated": "optional",
    "copied": "required",
    "packaged": "required",
}


def phase2_authority(plan_text: str) -> dict:
    """Return the one language-neutral contract shared by every Phase-2 role."""
    level = _starting_level(plan_text)
    return {
        "version": 7,
        "startingLevel": level,
        "maxFamiliesPerLesson": FAMILY_LIMITS.get(level),
        "nodeDoneWhen": {
            "shape": "a JSON object with the sole key checks; never a bare array",
            "lesson": {"checks": ["learner-construction", "lesson-source"]},
            "working": {"checks": ["learner-construction", "working-replay"]},
            "masteryLab": {"checks": ["learner-evidence", "variant-proof"]},
        },
        "languagePractice": {
            "phase1AllocationIsMinimum": True,
            "meaning": (
                "every section must retain its sealed Phase-1 language-practice allocation; "
                "Phase 2 may add truthful later retrieval but may not remove or replace a minimum"
            ),
        },
        "mechanismFamilies": {
            "meaning": (
                "one coherent lesson-level pedagogical goal, not one family per "
                "mechanism, verb, state transition, or reusable responsibility"
            ),
            "sameLessonDependency": (
                "allowed only when prerequisite and dependent share that coherent family "
                "and the prerequisite appears first in the lesson introduces order; a "
                "cross-family prerequisite requires an earlier lesson"
            ),
        },
        "artifactProduction": {
            "allowedModes": sorted(PRODUCTION_MODES),
            "modeMeaning": {
                "authored": (
                    "the learner creates the canonical artifact; use this for learner-written "
                    "source, configuration, data, documentation, and similar project material"
                ),
                "generated": "a tool creates the artifact from parameters or prior inputs",
                "copied": "an existing artifact is copied without changing its content",
                "packaged": "prior artifacts are assembled into a delivery artifact",
            },
            "inputPolicyByMode": dict(ARTIFACT_INPUT_POLICIES),
            "inputPolicyMeaning": (
                "forbidden, optional, and required describe only the artifact inputs array; "
                "they never forbid a production mode"
            ),
            "mechanisms": "at least one concrete production mechanism is required",
            "productionPrerequisiteClosure": (
                "each production row is transitively closed over the narrower "
                "productionDependsOn graph"
            ),
        },
        "capabilityCoverage": {
            "meaning": (
                "every taught capability names its concrete component mechanisms; every "
                "component owner occurs no later than the capability claim"
            ),
        },
        "continuityCoverage": {
            "meaning": (
                "every planned continuity obligation names the concrete mechanisms preserved "
                "by its target Working"
            ),
        },
        "cumulativeWorkingMechanisms": {
            "meaning": (
                "when a later Working retains any learner-owned artifact named by an earlier "
                "Working, its mechanism list includes every mechanism from that earlier "
                "Working; the retained artifact may be extended but its already-sealed "
                "operations cannot silently disappear"
            ),
        },
        "failurePaths": {
            "meaning": (
                "status observation precedes failure branching; a branch never depends on its "
                "later diagnostic or cleanup, diagnostics depend on status, and cleanup depends "
                "on the branch"
            ),
        },
        "externalCleanStart": {
            "meaning": (
                "with external or both tooling, tool installation and observable diagnostic "
                "verification precede the first project source edit/save lesson"
            ),
        },
        "acceptanceManifest": {
            "meaning": (
                "[acceptance] describes how the harness executes proof; it does not duplicate "
                "the Phase-1 delivery record"
            ),
            "modeValues": {
                "run": "the acceptance journey is executable",
                "guided": "the external-workspace journey is operator-observed",
            },
            "artifactValues": {
                "runtime": "the executable runtime is the proof target",
                "package": "the delivered package is the proof target",
            },
            "packageDeliveryEncoding": {"mode": "run", "artifact": "package"},
            "deliveryDetailsSource": (
                "artifactContract.delivery and the final section package proof contain the "
                "exact artifact path and requirements path"
            ),
            "packageProofLocation": "the final tome section [proof] table",
            "compactCourseMapPackageProofAllowed": False,
            "forbiddenRepairs": [
                "mode = package", "artifact = exact delivery path",
                "requirements in [acceptance]", "nested acceptance.sealedDelivery",
            ],
        },
        "research": {
            "maximumSources": MAX_SOURCES,
            "allowedSources": "official or primary",
            "requiredWhenTooling": ["external", "both"],
        },
        "repairOwnership": {
            "sealedPlanRepairable": False,
            "generatedProposalRepairable": False,
            "compactAuthorFilesRepairable": True,
            "auditRepairable": True,
            "researchLedgerRepairable": True,
            "manifestRepairable": True,
            "tomeSkeletonRepairable": True,
            "runtimeProfileRepairable": True,
        },
    }


def audit_path(build_id: str, build_dir: str | None = None) -> str:
    return os.path.join(build_dir or BUILD_DIR, f"{build_id}.course-map-author", "audit.json")


def default_audit(source: dict) -> dict:
    artifacts = ((source.get("artifactContract") or {}).get("artifacts")
                 if isinstance(source, dict) else []) or []
    return {
        "version": 2,
        "mechanisms": [],
        "capabilityCoverage": [],
        "continuityCoverage": [
            {"obligation": str(item.get("id") or ""), "mechanisms": []}
            for item in (source.get("plannedObligations") or [])
            if isinstance(item, dict)
        ],
        "failurePaths": [],
        "artifactProduction": [
            {
                "artifact": str(item.get("artifact") or ""),
                "ownerWorking": str(item.get("ownerWorking") or ""),
                "mode": "authored",
                "inputs": [],
                "mechanisms": [],
            }
            for item in artifacts if isinstance(item, dict)
        ],
    }


def initialize_audit(build_id: str, source: dict, *, overwrite: bool = False,
                     build_dir: str | None = None) -> str:
    path = audit_path(build_id, build_dir)
    if os.path.isfile(path) and not overwrite:
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(default_audit(source), handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temporary, path)
    return path


def _positions(value: dict) -> dict[str, tuple[int, int]]:
    return {
        str(node.get("id")): (section_index, node_index)
        for section_index, section in enumerate(value.get("sections") or [])
        if isinstance(section, dict)
        for node_index, node in enumerate(section.get("nodes") or [])
        if isinstance(node, dict) and node.get("id")
    }


def _introduction_order(value: dict) -> dict[str, tuple[str, int]]:
    """Map each introduced mechanism to its owner lesson and declared teaching order."""
    return {
        str(mechanism): (str(node.get("id") or ""), mechanism_index)
        for section in value.get("sections") or []
        if isinstance(section, dict)
        for node in section.get("nodes") or []
        if isinstance(node, dict) and node.get("kind") == "lesson"
        for mechanism_index, mechanism in enumerate(node.get("introduces") or [])
        if isinstance(mechanism, str) and mechanism
    }


def _starting_level(plan_text: str) -> int:
    match = re.search(
        r"(?im)^- \*\*Starting level \(1-10\):\*\*\s*(10|[1-9])\s*$",
        str(plan_text or ""))
    return int(match.group(1)) if match else 0


def _tooling_mode(plan_text: str) -> str:
    match = re.search(
        r"(?im)^- \*\*Tooling:\*\*\s*(internal|external|both)\s*$",
        str(plan_text or ""))
    return match.group(1).lower() if match else ""


def _dependency_closure(seed, graph):
    closure = set(seed)
    queue = list(seed)
    while queue:
        current = queue.pop()
        for dependency in graph.get(current, []):
            if dependency not in closure:
                closure.add(dependency)
                queue.append(dependency)
    return closure


def _lesson_positions(value: dict) -> dict[str, tuple[int, int]]:
    return {
        str(node.get("id")): (section_index, lesson_index)
        for section_index, section in enumerate(value.get("sections") or [])
        if isinstance(section, dict)
        for lesson_index, node in enumerate(section.get("nodes") or [])
        if isinstance(node, dict) and node.get("kind") == "lesson" and node.get("id")
    }


def _clean_start_problems(value: dict, plan_text: str) -> list[str]:
    """Require external setup and verification before project source authorship."""
    if _tooling_mode(plan_text) not in {"external", "both"}:
        return []
    sections = [section for section in value.get("sections") or []
                if isinstance(section, dict)]
    if not sections:
        return []
    lessons = [node for node in sections[0].get("nodes") or []
               if isinstance(node, dict) and node.get("kind") == "lesson"]
    owners = {}
    for index, lesson in enumerate(lessons):
        for capability in lesson.get("teaches") or []:
            owners.setdefault(capability, (index, lesson.get("id")))
    authoring = owners.get("tool-edit-save")
    if authoring is None:
        return []
    problems = []
    for capability in ("tool-install", "tool-diagnose"):
        setup = owners.get(capability)
        if setup is None:
            problems.append(
                f"external clean start requires {capability!r} in the first section before "
                "project source authorship")
        elif setup[0] >= authoring[0]:
            problems.append(
                f"external clean start requires {setup[1]} ({capability}) before "
                f"{authoring[1]} (tool-edit-save)")
    return problems


