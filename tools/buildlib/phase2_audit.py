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

from . import BUILD_DIR
from .phase2_research import MAX_SOURCES


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


def audit_problems(audit: object, value: object, plan_text: str, *,
                   required_version: int | None = None) -> list[str]:
    """Return deterministic audit defects without language-specific assumptions.

    Legacy readers may omit ``required_version`` and continue accepting v1. New
    Phase-2 authoring passes 2 so an old audit cannot silently bypass the hardened
    production, capability, continuity, and failure-path checks.
    """
    if not isinstance(audit, dict):
        return ["audit.json must be a JSON object"]
    problems = []
    version = audit.get("version")
    if required_version is not None and version != required_version:
        problems.append(
            f"audit.json.version must be {required_version} for Phase 2 authoring; "
            f"version {version!r} is legacy read-only input")
    expected_audit_keys = AUDIT_KEYS_V2 if version == 2 else AUDIT_KEYS_V1
    if set(audit) != expected_audit_keys:
        problems.append(
            f"audit.json keys must be exactly {', '.join(sorted(expected_audit_keys))}")
    if version not in {1, 2}:
        problems.append("audit.json.version must be 1 or 2")
    if not isinstance(value, dict):
        return problems + ["the materialized course map must be an object"]
    problems.extend(_clean_start_problems(value, plan_text))

    map_records = {
        item.get("id"): item
        for item in ((value.get("mechanismContract") or {}).get("mechanisms") or [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    raw_records = audit.get("mechanisms")
    if not isinstance(raw_records, list):
        return problems + ["audit.json.mechanisms must be an array"]
    records = {}
    for index, item in enumerate(raw_records):
        label = f"audit.json.mechanisms[{index}]"
        if not isinstance(item, dict):
            problems.append(f"{label} must be an object")
            continue
        expected_mechanism_keys = MECHANISM_KEYS_V2 if version == 2 else MECHANISM_KEYS_V1
        if set(item) != expected_mechanism_keys:
            problems.append(
                f"{label} keys must be exactly "
                f"{', '.join(sorted(expected_mechanism_keys))}")
        mid = item.get("id")
        if mid in records:
            problems.append(f"{label}.id repeats mechanism {mid!r}")
        records[mid] = item
        if mid not in map_records:
            problems.append(f"{label}.id names unknown mechanism {mid!r}")
        if not ID_RE.fullmatch(str(item.get("family") or "")):
            problems.append(f"{label}.family must be a stable language-neutral kebab id")
        dependencies = item.get("dependsOn")
        if not isinstance(dependencies, list):
            problems.append(f"{label}.dependsOn must be an array")
            continue
        if (any(not isinstance(dep, str) or not dep for dep in dependencies)
                or len(dependencies) != len(set(dependencies))):
            problems.append(f"{label}.dependsOn must contain unique mechanism ids")
        if version == 2:
            production_dependencies = item.get("productionDependsOn")
            if not isinstance(production_dependencies, list):
                problems.append(f"{label}.productionDependsOn must be an array")
            elif (any(not isinstance(dep, str) or not dep
                      for dep in production_dependencies)
                  or len(production_dependencies) != len(set(production_dependencies))):
                problems.append(
                    f"{label}.productionDependsOn must contain unique mechanism ids")
    missing_records = sorted(set(map_records) - set(records))
    if missing_records:
        problems.append("audit.json.mechanisms is missing exact ledger entries: "
                        + ", ".join(missing_records))

    positions = _positions(value)
    introduction_order = _introduction_order(value)
    dependency_graph = {}
    production_graph = {}
    for mid, item in records.items():
        dependencies = item.get("dependsOn") if isinstance(item, dict) else []
        if not isinstance(dependencies, list):
            continue
        dependency_graph[mid] = dependencies
        production_dependencies = (
            item.get("productionDependsOn") if version == 2 and isinstance(item, dict) else [])
        if isinstance(production_dependencies, list):
            production_graph[mid] = production_dependencies
            for dependency in production_dependencies:
                if dependency == mid:
                    problems.append(
                        f"mechanism {mid!r} cannot production-depend on itself")
                elif dependency not in map_records:
                    problems.append(
                        f"mechanism {mid!r} production-depends on unknown mechanism "
                        f"{dependency!r}")
        owner = (map_records.get(mid) or {}).get("owner")
        for dependency in dependencies:
            if dependency == mid:
                problems.append(f"mechanism {mid!r} cannot depend on itself")
                continue
            if dependency not in map_records:
                problems.append(f"mechanism {mid!r} depends on unknown mechanism {dependency!r}")
                continue
            dependency_owner = map_records[dependency].get("owner")
            if positions.get(dependency_owner, (999, 999)) > positions.get(owner, (-1, -1)):
                problems.append(
                    f"mechanism {mid!r} depends on {dependency!r}, but {dependency_owner} "
                    f"is later than owner {owner}")
            elif dependency_owner == owner:
                dependency_family = (records.get(dependency) or {}).get("family")
                if dependency_family != item.get("family"):
                    problems.append(
                        f"mechanism {mid!r} depends on cross-family mechanism {dependency!r} "
                        f"in the same lesson {owner}; give the prerequisite an earlier lesson")
                current_order = introduction_order.get(mid)
                prerequisite_order = introduction_order.get(dependency)
                if (not current_order or not prerequisite_order
                        or prerequisite_order[0] != owner or current_order[0] != owner
                        or prerequisite_order[1] >= current_order[1]):
                    problems.append(
                        f"mechanism {mid!r} depends on {dependency!r} in {owner}, but the "
                        "prerequisite must appear first in that lesson's introduces order")
    visiting, visited = set(), set()

    def visit(mid):
        if mid in visiting:
            problems.append(f"mechanism dependency cycle reaches {mid!r}")
            return
        if mid in visited:
            return
        visiting.add(mid)
        for dependency in dependency_graph.get(mid, []):
            if dependency in dependency_graph:
                visit(dependency)
        visiting.remove(mid)
        visited.add(mid)

    for mid in dependency_graph:
        visit(mid)

    if version == 2:
        for mid, production_dependencies in production_graph.items():
            teaching_closure = _dependency_closure(
                dependency_graph.get(mid, []), dependency_graph)
            outside_teaching_graph = sorted(
                set(production_dependencies) - teaching_closure)
            if outside_teaching_graph:
                problems.append(
                    f"mechanism {mid!r} has production prerequisites outside its "
                    "teaching dependency closure: " + ", ".join(outside_teaching_graph))
        production_visiting, production_visited = set(), set()

        def visit_production(mid):
            if mid in production_visiting:
                problems.append(f"production dependency cycle reaches {mid!r}")
                return
            if mid in production_visited:
                return
            production_visiting.add(mid)
            for dependency in production_graph.get(mid, []):
                if dependency in production_graph:
                    visit_production(dependency)
            production_visiting.remove(mid)
            production_visited.add(mid)

        for mid in production_graph:
            visit_production(mid)

    authority = phase2_authority(plan_text)
    level = authority["startingLevel"]
    family_limit = authority["maxFamiliesPerLesson"]
    for section in value.get("sections") or []:
        if not isinstance(section, dict):
            continue
        nodes = [node for node in section.get("nodes") or [] if isinstance(node, dict)]
        working = next((node for node in nodes if node.get("kind") == "working"), {})
        working_ids = set(working.get("mechanisms") or [])
        introduced = set()
        for node in nodes:
            if node.get("kind") != "lesson":
                continue
            lesson_ids = set(node.get("introduces") or [])
            introduced |= lesson_ids
            families = {
                records[mid].get("family") for mid in lesson_ids
                if mid in records and isinstance(records[mid], dict)
            }
            families.discard(None)
            if family_limit is not None and len(families) > family_limit:
                problems.append(
                    f"{node.get('id')} introduces {len(families)} mechanism families "
                    f"{sorted(families)}; Starting level {level} permits at most "
                    f"{family_limit} in one lesson")
        missing_demands = sorted(introduced - working_ids)
        if missing_demands:
            problems.append(
                f"{working.get('id')} omits mechanisms introduced for its own milestone: "
                + ", ".join(missing_demands))
        closure = set(working_ids)
        queue = list(working_ids)
        while queue:
            current = queue.pop()
            for dependency in dependency_graph.get(current, []):
                if dependency not in closure:
                    closure.add(dependency)
                    queue.append(dependency)
        missing_dependencies = sorted(closure - working_ids)
        if missing_dependencies:
            problems.append(
                f"{working.get('id')} mechanism demand is not transitively closed; add "
                + ", ".join(missing_dependencies))

    if version == 2:
        lesson_positions = _lesson_positions(value)
        capability_owners = {}
        for section in value.get("sections") or []:
            if not isinstance(section, dict):
                continue
            for node in section.get("nodes") or []:
                if not isinstance(node, dict) or node.get("kind") != "lesson":
                    continue
                for capability in node.get("teaches") or []:
                    if isinstance(capability, str) and capability:
                        capability_owners.setdefault(capability, []).append(node.get("id"))
        raw_coverage = audit.get("capabilityCoverage")
        if not isinstance(raw_coverage, list):
            problems.append("audit.json.capabilityCoverage must be an array")
            raw_coverage = []
        coverage = {}
        for index, item in enumerate(raw_coverage):
            label = f"audit.json.capabilityCoverage[{index}]"
            if not isinstance(item, dict):
                problems.append(f"{label} must be an object")
                continue
            if set(item) != CAPABILITY_COVERAGE_KEYS:
                problems.append(
                    f"{label} keys must be exactly "
                    f"{', '.join(sorted(CAPABILITY_COVERAGE_KEYS))}")
            capability = item.get("capability")
            if capability in coverage:
                problems.append(f"{label}.capability repeats {capability!r}")
            coverage[capability] = item
            if capability not in capability_owners:
                problems.append(f"{label}.capability names untaught capability {capability!r}")
            mechanism_ids = item.get("mechanisms")
            if (not isinstance(mechanism_ids, list) or (not mechanism_ids and map_records)
                    or any(not isinstance(mid, str) or not mid for mid in mechanism_ids)
                    or len(mechanism_ids) != len(set(mechanism_ids))):
                problems.append(
                    f"{label}.mechanisms must contain unique concrete mechanism ids")
                continue
            unknown = sorted(set(mechanism_ids) - set(map_records))
            if unknown:
                problems.append(
                    f"{label}.mechanisms names unknown mechanisms: " + ", ".join(unknown))
            owner_positions = [lesson_positions.get(owner, (999, 999))
                               for owner in capability_owners.get(capability, [])]
            first_claim = min(owner_positions, default=(-1, -1))
            late = sorted(mid for mid in mechanism_ids
                          if lesson_positions.get((map_records.get(mid) or {}).get("owner"),
                                                  (999, 999)) > first_claim)
            if late:
                problems.append(
                    f"{label}.capability is claimed before component mechanisms: "
                    + ", ".join(late))
        missing_coverage = sorted(set(capability_owners) - set(coverage))
        if missing_coverage:
            problems.append(
                "audit.json.capabilityCoverage is missing taught capabilities: "
                + ", ".join(missing_coverage))

        obligations = {
            item.get("id"): item
            for item in value.get("plannedObligations") or []
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        working_by_section = {
            section.get("id"): next((
                node for node in section.get("nodes") or []
                if isinstance(node, dict) and node.get("kind") == "working"), {})
            for section in value.get("sections") or [] if isinstance(section, dict)
        }
        raw_continuity = audit.get("continuityCoverage")
        if not isinstance(raw_continuity, list):
            problems.append("audit.json.continuityCoverage must be an array")
            raw_continuity = []
        continuity = {}
        for index, item in enumerate(raw_continuity):
            label = f"audit.json.continuityCoverage[{index}]"
            if not isinstance(item, dict):
                problems.append(f"{label} must be an object")
                continue
            if set(item) != CONTINUITY_COVERAGE_KEYS:
                problems.append(
                    f"{label} keys must be exactly "
                    f"{', '.join(sorted(CONTINUITY_COVERAGE_KEYS))}")
            obligation_id = item.get("obligation")
            if obligation_id in continuity:
                problems.append(f"{label}.obligation repeats {obligation_id!r}")
            continuity[obligation_id] = item
            obligation = obligations.get(obligation_id)
            if obligation is None:
                problems.append(
                    f"{label}.obligation names unknown planned obligation {obligation_id!r}")
                continue
            mechanism_ids = item.get("mechanisms")
            if (not isinstance(mechanism_ids, list) or (not mechanism_ids and map_records)
                    or any(not isinstance(mid, str) or not mid for mid in mechanism_ids)
                    or len(mechanism_ids) != len(set(mechanism_ids))):
                problems.append(
                    f"{label}.mechanisms must contain unique preserved mechanism ids")
                continue
            unknown = sorted(set(mechanism_ids) - set(map_records))
            if unknown:
                problems.append(
                    f"{label}.mechanisms names unknown mechanisms: " + ", ".join(unknown))
            target = obligation.get("target")
            working = working_by_section.get(target) or {}
            target_mechanisms = set(working.get("mechanisms") or [])
            missing_at_target = sorted(set(mechanism_ids) - target_mechanisms)
            if missing_at_target:
                problems.append(
                    f"{label} target {target!r} Working omits preserved mechanisms: "
                    + ", ".join(missing_at_target))
        missing_continuity = sorted(set(obligations) - set(continuity))
        if missing_continuity:
            problems.append(
                "audit.json.continuityCoverage is missing planned obligations: "
                + ", ".join(missing_continuity))

        raw_failure_paths = audit.get("failurePaths")
        if not isinstance(raw_failure_paths, list):
            problems.append("audit.json.failurePaths must be an array")
            raw_failure_paths = []
        failure_ids = set()
        for index, item in enumerate(raw_failure_paths):
            label = f"audit.json.failurePaths[{index}]"
            if not isinstance(item, dict):
                problems.append(f"{label} must be an object")
                continue
            if set(item) != FAILURE_PATH_KEYS:
                problems.append(
                    f"{label} keys must be exactly "
                    f"{', '.join(sorted(FAILURE_PATH_KEYS))}")
            path_id = item.get("id")
            if not ID_RE.fullmatch(str(path_id or "")):
                problems.append(f"{label}.id must be a stable language-neutral kebab id")
            elif path_id in failure_ids:
                problems.append(f"{label}.id repeats failure path {path_id!r}")
            failure_ids.add(path_id)
            role_values = {}
            for role in ("status", "branches", "diagnostics", "cleanup"):
                values = item.get(role)
                allow_empty = role == "cleanup"
                if (not isinstance(values, list) or (not values and not allow_empty)
                        or any(not isinstance(mid, str) or not mid for mid in values)
                        or len(values) != len(set(values))):
                    problems.append(
                        f"{label}.{role} must contain unique mechanism ids")
                    values = []
                unknown = sorted(set(values) - set(map_records))
                if unknown:
                    problems.append(
                        f"{label}.{role} names unknown mechanisms: " + ", ".join(unknown))
                role_values[role] = set(values)
            status = role_values["status"]
            branches = role_values["branches"]
            diagnostics = role_values["diagnostics"]
            cleanup = role_values["cleanup"]
            for branch in branches:
                closure = _dependency_closure(
                    dependency_graph.get(branch, []), dependency_graph)
                missing_status = sorted(status - closure)
                if missing_status:
                    problems.append(
                        f"{label} branch {branch!r} must depend on status mechanisms: "
                        + ", ".join(missing_status))
                invalid = sorted(closure & (diagnostics | cleanup))
                if invalid:
                    problems.append(
                        f"{label} branch {branch!r} cannot depend on later diagnostic or "
                        "cleanup mechanisms: " + ", ".join(invalid))
            for diagnostic in diagnostics:
                closure = _dependency_closure(
                    dependency_graph.get(diagnostic, []), dependency_graph)
                if status and not (closure & status):
                    problems.append(
                        f"{label} diagnostic {diagnostic!r} must depend on a status mechanism")
            for cleanup_mid in cleanup:
                closure = _dependency_closure(
                    dependency_graph.get(cleanup_mid, []), dependency_graph)
                if branches and not (closure & branches):
                    problems.append(
                        f"{label} cleanup {cleanup_mid!r} must depend on a failure branch")

    artifact_contract = value.get("artifactContract") or {}
    artifact_records = {
        item.get("artifact"): item
        for item in artifact_contract.get("artifacts") or []
        if isinstance(item, dict) and isinstance(item.get("artifact"), str)
    } if isinstance(artifact_contract, dict) else {}
    raw_production = audit.get("artifactProduction")
    if not isinstance(raw_production, list):
        return problems + ["audit.json.artifactProduction must be an array"]
    production, artifact_graph = {}, {}
    for index, item in enumerate(raw_production):
        label = f"audit.json.artifactProduction[{index}]"
        if not isinstance(item, dict):
            problems.append(f"{label} must be an object")
            continue
        if set(item) != PRODUCTION_KEYS:
            problems.append(f"{label} keys must be exactly {', '.join(sorted(PRODUCTION_KEYS))}")
        artifact = item.get("artifact")
        if artifact in production:
            problems.append(f"{label}.artifact repeats {artifact!r}")
        production[artifact] = item
        sealed = artifact_records.get(artifact)
        if sealed is None:
            problems.append(f"{label}.artifact names undeclared artifact {artifact!r}")
            continue
        owner = item.get("ownerWorking")
        if owner != sealed.get("ownerWorking"):
            problems.append(
                f"{label}.ownerWorking must preserve {sealed.get('ownerWorking')!r}")
        if item.get("mode") not in PRODUCTION_MODES:
            problems.append(f"{label}.mode must be one of {sorted(PRODUCTION_MODES)}")
        inputs = item.get("inputs")
        if not isinstance(inputs, list) or any(not isinstance(v, str) or not v for v in inputs):
            problems.append(f"{label}.inputs must be an array of artifact paths")
            inputs = []
        elif len(inputs) != len(set(inputs)):
            problems.append(f"{label}.inputs contains duplicates")
        if artifact in inputs:
            problems.append(f"{label}.inputs cannot contain its own artifact")
        input_policy = ARTIFACT_INPUT_POLICIES.get(item.get("mode"))
        if input_policy == "forbidden" and inputs:
            problems.append(f"{label}.mode authored must start without artifact inputs")
        if input_policy == "required" and not inputs:
            problems.append(f"{label}.mode {item.get('mode')} requires at least one input artifact")
        artifact_graph[artifact] = list(inputs)
        for input_artifact in inputs:
            source = artifact_records.get(input_artifact)
            if source is None:
                problems.append(f"{label}.inputs names undeclared artifact {input_artifact!r}")
            elif positions.get(source.get("ownerWorking"), (999, 999)) > positions.get(owner, (-1, -1)):
                problems.append(
                    f"{label}.inputs uses {input_artifact!r} before its owner Working")
        mechanism_ids = item.get("mechanisms")
        if (not isinstance(mechanism_ids, list) or not mechanism_ids
                or any(not isinstance(v, str) or not v for v in mechanism_ids)):
            problems.append(f"{label}.mechanisms must contain at least one mechanism id")
            mechanism_ids = []
        elif len(mechanism_ids) != len(set(mechanism_ids)):
            problems.append(f"{label}.mechanisms contains duplicates")
        working = next((node for section in value.get("sections") or []
                        if isinstance(section, dict)
                        for node in section.get("nodes") or []
                        if isinstance(node, dict) and node.get("id") == owner), {})
        unavailable = sorted(set(mechanism_ids) - set(working.get("mechanisms") or []))
        if unavailable:
            problems.append(
                f"{label}.mechanisms are absent from {owner}: " + ", ".join(unavailable))
        if version == 2:
            production_closure = _dependency_closure(mechanism_ids, production_graph)
            missing_production_dependencies = sorted(
                production_closure - set(mechanism_ids))
            if missing_production_dependencies:
                problems.append(
                    f"{label}.mechanisms is not closed over production prerequisites; add "
                    + ", ".join(missing_production_dependencies))
    missing_artifacts = sorted(set(artifact_records) - set(production))
    if missing_artifacts:
        problems.append("audit.json.artifactProduction is missing declared artifacts: "
                        + ", ".join(missing_artifacts))

    visiting, visited = set(), set()

    def visit_artifact(artifact):
        if artifact in visiting:
            problems.append(f"artifact production cycle reaches {artifact!r}")
            return
        if artifact in visited:
            return
        visiting.add(artifact)
        for input_artifact in artifact_graph.get(artifact, []):
            if input_artifact in artifact_graph:
                visit_artifact(input_artifact)
        visiting.remove(artifact)
        visited.add(artifact)

    for artifact in artifact_graph:
        visit_artifact(artifact)
    return problems
