"""Sealed long-course map contract shared by the Bindery authoring gates.

Phase 1 creates a section-level seed, compact Phase-2 author sources, and an
initial generated proposal. Phase 2 fills every lesson/Working node through the
compact sources; the harness rematerializes and seals the proposal. Only the
harness writes generated or authoritative maps; authors receive them read-only.
"""
from __future__ import annotations

import copy
import json
import os
import re

from .. import BUILD_DIR, REPO
from ..course.limits import MAX_SECTIONS, MIN_SECTIONS
from .codec import canonical_bytes, digest
from .locations import section_reference_problem, validate_locations
from .mastery_performances import expected_working_performances
from .plan import acceptance as _acceptance
from .plan import field as _field
from .plan import lesson_counts as _lesson_counts
from .plan import plan_contract_sha256
from .contracts import validate_semantic_contracts
from ..course.dependencies import validation_dependency_alignment_problems
from .seed import artifact_lifecycle_obligations, continuity_obligations
from .schema import (CAPABILITY_RE, ID_RE, LAB_KEYS, LAB_RE, LESSON_KEYS, LESSON_RE,
                     MAP_VERSION, MAX_PLANNED_LESSONS, MIN_PLANNED_LESSONS,
                     OBLIGATION_DONE_KEYS, OBLIGATION_KEYS, OBLIGATION_KINDS,
                     OBLIGATION_OPTIONAL_KEYS, OBLIGATION_RE, SECTION_CHECKS, SECTION_KEYS,
                     SUPPORTED_MAP_VERSIONS,
                     TOP_KEYS, WORKING_KEYS, check_set as _check_set,
                     done_when as _done_when, keys as _keys,
                     obligation_done as _obligation_done, strings as _strings)
from ..language_mastery.foundations import block_field
from ..language_mastery import seed_contract as seed_language_mastery
from ..language_mastery import validate_map_contract as validate_language_mastery
from ..mastery_evidence import seed_contract as seed_mastery_evidence
from ..mastery_evidence.map_contract import validate_map_contract as validate_mastery_evidence
from ..mechanism_contract import seed_contract as seed_mechanism_contract
from ..mechanism_contract import validate_map_contract as validate_mechanism_contract
from ..skeleton.integrity import contract_problems as validate_artifact_contract
from ..skeleton.integrity import graph_problems as validate_integrity_graph
from ..skeleton.integrity import seed_contract as seed_artifact_contract
from ..skeleton import parse_section_list

class CourseMapError(ValueError):
    """A map cannot become authoritative because its contract is incomplete."""


def build_id_from_plan(plan_file):
    name = os.path.basename(str(plan_file or ""))
    suffix = ".plan.md"
    candidate = name[:-len(suffix)] if name.endswith(suffix) else ""
    return candidate if ID_RE.fullmatch(candidate) else ""


def validate_map_locations(build_id, value):
    return validate_locations(build_id, value, build_dir=BUILD_DIR, repo=REPO)

def _path(build_id, suffix):
    if not ID_RE.fullmatch(str(build_id or "")):
        raise CourseMapError(f"invalid build id {build_id!r}")
    return os.path.join(BUILD_DIR, f"{build_id}.{suffix}")

def seed_path(build_id):
    return _path(build_id, "course-map.seed.json")

def proposal_path(build_id):
    return _path(build_id, "course-map.proposal.json")

def map_path(build_id):
    return _path(build_id, "course-map.json")

def amendment_path(build_id):
    return _path(build_id, "course-map.amendments.json")


def _atomic_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temp, path)


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise CourseMapError(f"{os.path.relpath(path, REPO)} is missing or invalid JSON: {exc}") from exc


def preview_course_map(build_id, text):
    """Build and validate the Phase-1 seed without writing transition artifacts."""
    specs = parse_section_list(text)
    if not MIN_SECTIONS <= len(specs) <= MAX_SECTIONS:
        raise CourseMapError(
            f"Section list must contain {MIN_SECTIONS} through {MAX_SECTIONS} entries; "
            f"found {len(specs)}")
    ids = [spec.sid for spec in specs]
    counts = _lesson_counts(text, ids)
    language_contract = seed_language_mastery(text, ids)
    from ..language_mastery import practice_allocations
    practices, practice_problems = practice_allocations(
        text, ids, (language_contract or {}).get("capabilityIds") or [])
    if practice_problems:
        raise CourseMapError("Phase 1 language practice allocation is invalid:\n- "
                             + "\n- ".join(practice_problems))
    seed_sections = [{
        "id": spec.sid, "ordinal": index, "title": spec.title,
        "promise": spec.promise, "capabilities": [],
        "languagePractice": list(practices.get(spec.sid) or []),
        "dependsOn": [], "nodes": [],
        "projectMilestone": spec.promise,
        "doneWhen": {"checks": sorted(SECTION_CHECKS)},
        **({"lessonCount": counts[spec.sid]} if counts else {}),
    } for index, spec in enumerate(specs, 1)]
    value = {
        "version": MAP_VERSION if counts else 5, "revision": 1, "buildId": build_id,
        "planSha256": plan_contract_sha256(text),
        "bounds": {"minSections": MIN_SECTIONS, "maxSections": MAX_SECTIONS},
        "graduateContract": block_field(text, "Graduate ledger"),
        "graduateCapabilities": [],
        "masteryPerformances": [_field(text, "Mastery proof")],
        "languageMastery": language_contract,
        "mechanismContract": seed_mechanism_contract(ids),
        "acceptanceScenarios": _acceptance(text),
        "sections": seed_sections,
        "plannedObligations": (continuity_obligations(text, ids)
                               + artifact_lifecycle_obligations(text, ids)),
    }
    artifact_contract = seed_artifact_contract(text)
    if artifact_contract is not None:
        value["artifactContract"] = artifact_contract
    evidence_contract = seed_mastery_evidence(text, seed_sections, language_contract)
    if evidence_contract is not None:
        value["masteryEvidence"] = evidence_contract
    problems = validate_course_map(value, detailed=False)
    if problems:
        raise CourseMapError("Phase 1 course map is invalid:\n- " + "\n- ".join(problems))
    return value


def seed_course_map(build_id, plan_file, write=True):
    try:
        with open(plan_file, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        raise CourseMapError(f"could not read plan {plan_file}: {exc}") from exc
    value = preview_course_map(build_id, text)
    if write:
        _atomic_json(seed_path(build_id), value)
        _atomic_json(proposal_path(build_id), value)
    return value


def validate_course_map(value, detailed=True, seed=None):
    """Return every schema/graph problem; never silently normalize omissions."""
    problems = _keys(value, TOP_KEYS, "course map",
                     optional={"digest", "languageMastery", "artifactContract",
                               "mechanismContract", "masteryEvidence"})
    if not isinstance(value, dict):
        return problems
    map_version = value.get("version")
    if map_version not in SUPPORTED_MAP_VERSIONS:
        problems.append(
            f"course map version must be one of {list(SUPPORTED_MAP_VERSIONS)}")
        map_version = MAP_VERSION
    if not isinstance(value.get("revision"), int) or value.get("revision", 0) < 1:
        problems.append("course map revision must be a positive integer")
    if not ID_RE.fullmatch(str(value.get("buildId") or "")):
        problems.append("course map buildId is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(value.get("planSha256") or "")):
        problems.append("course map planSha256 must be a SHA-256 digest")
    if value.get("bounds") != {"minSections": MIN_SECTIONS, "maxSections": MAX_SECTIONS}:
        problems.append(f"bounds must be exactly {MIN_SECTIONS} through {MAX_SECTIONS}")
    for key, maximum in (("graduateContract", 2400),):
        if not isinstance(value.get(key), str) or not value[key].strip():
            problems.append(f"{key} must be a non-empty string")
        elif len(value[key]) > maximum:
            problems.append(f"{key} exceeds {maximum} characters")
    problems += _strings(value.get("graduateCapabilities"), "graduateCapabilities",
                         allow_empty=not detailed)
    problems += _strings(value.get("masteryPerformances"), "masteryPerformances", maximum=2400)
    problems += _strings(value.get("acceptanceScenarios"), "acceptanceScenarios")
    sections = value.get("sections")
    if not isinstance(sections, list):
        return problems + ["sections must be an array"]
    if not MIN_SECTIONS <= len(sections) <= MAX_SECTIONS:
        problems.append(
            f"sections must contain {MIN_SECTIONS} through {MAX_SECTIONS} entries; found {len(sections)}")
    section_ids, node_ids, capability_owners, graph = [], [], {}, {}
    positions = {}
    for index, section in enumerate(sections, 1):
        label = f"sections[{index - 1}]"
        expected_section_keys = (SECTION_KEYS | {"lessonCount"}
                                 if map_version >= 6 else SECTION_KEYS)
        problems += _keys(section, expected_section_keys, label, optional={"languagePractice"})
        if not isinstance(section, dict):
            continue
        sid = section.get("id")
        expected = f"s{index:02d}"
        if sid != expected or section.get("ordinal") != index:
            problems.append(f"{label} must be sequential id {expected} with ordinal {index}")
        section_ids.append(sid)
        positions[sid] = (index, -1)
        if map_version >= 6 and (not isinstance(section.get("lessonCount"), int)
                                 or not MIN_PLANNED_LESSONS <= section["lessonCount"] <= MAX_PLANNED_LESSONS):
            problems.append(
                f"{label}.lessonCount must be an integer from {MIN_PLANNED_LESSONS} "
                f"through {MAX_PLANNED_LESSONS}")
        for key, limit in (("title", 120), ("promise", 360), ("projectMilestone", 360)):
            if not isinstance(section.get(key), str) or not section[key].strip():
                problems.append(f"{label}.{key} must be a non-empty string")
            elif len(section[key]) > limit:
                problems.append(f"{label}.{key} exceeds {limit} characters")
        problems += _strings(section.get("capabilities"), f"{label}.capabilities",
                             allow_empty=not detailed)
        problems += _strings(section.get("dependsOn"), f"{label}.dependsOn", allow_empty=True)
        problems += _done_when(section.get("doneWhen"), f"{label}.doneWhen")
        checks = _check_set(section.get("doneWhen"))
        if detailed and checks is not None and checks != SECTION_CHECKS:
            problems.append(f"{label}.doneWhen.checks must be exactly {sorted(SECTION_CHECKS)}")
        graph[sid] = list(section.get("dependsOn") or [])
        nodes = section.get("nodes")
        if not isinstance(nodes, list):
            problems.append(f"{label}.nodes must be an array")
            continue
        lessons, workings, labs, taught = [], [], [], []
        for node_index, node in enumerate(nodes):
            nlabel = f"{label}.nodes[{node_index}]"
            if not isinstance(node, dict):
                problems.append(f"{nlabel} must be an object")
                continue
            kind = node.get("kind")
            expected_keys = (LESSON_KEYS if kind == "lesson" else
                             WORKING_KEYS if kind == "working" else
                             LAB_KEYS if kind == "mastery-lab" else set())
            if not expected_keys:
                problems.append(f"{nlabel}.kind must be lesson, working, or mastery-lab")
                continue
            if map_version >= 2:
                expected_keys = expected_keys | {"validationDependencies"}
            if map_version >= 4 and kind in ("lesson", "working"):
                expected_keys = expected_keys | {
                    "introduces" if kind == "lesson" else "mechanisms"}
            problems += _keys(node, expected_keys, nlabel,
                              optional={"masteryPerformances"} if kind == "working" else ())
            nid = node.get("id")
            if kind == "lesson":
                lessons.append(node)
                expected_id = f"{sid}.l{len(lessons):02d}"
                if nid != expected_id or not LESSON_RE.fullmatch(str(nid or "")):
                    problems.append(f"{nlabel}.id must be sequential {expected_id}")
                taught += list(node.get("teaches") or [])
                problems += _strings(node.get("teaches"), f"{nlabel}.teaches")
            elif kind == "working":
                workings.append(node)
                if nid != f"{sid}.working":
                    problems.append(f"{nlabel}.id must be {sid}.working")
                problems += _strings(node.get("requires"), f"{nlabel}.requires")
                problems += _strings(node.get("learnerOwnedArtifacts"),
                                     f"{nlabel}.learnerOwnedArtifacts")
                if node.get("projectMilestone") != section.get("projectMilestone"):
                    problems.append(f"{nlabel}.projectMilestone must match its section milestone")
            else:
                labs.append(node)
                expected_id = f"{sid}.lab{len(labs):02d}"
                if nid != expected_id or not LAB_RE.fullmatch(str(nid or "")):
                    problems.append(f"{nlabel}.id must be sequential {expected_id}")
                problems += _strings(node.get("capabilityIds"), f"{nlabel}.capabilityIds")
                problems += _strings(node.get("cognitiveTasks"), f"{nlabel}.cognitiveTasks")
            if not isinstance(node.get("title"), str) or not node["title"].strip():
                problems.append(f"{nlabel}.title must be a non-empty string")
            problems += _strings(node.get("dependsOn"), f"{nlabel}.dependsOn", allow_empty=True)
            if map_version >= 2:
                problems += _strings(
                    node.get("validationDependencies"),
                    f"{nlabel}.validationDependencies", allow_empty=True, maximum=240)
            problems += _done_when(node.get("doneWhen"), f"{nlabel}.doneWhen")
            if isinstance(nid, str):
                node_ids.append(nid)
                positions[nid] = (index, node_index)
                graph[nid] = list(node.get("dependsOn") or [])
            for capability in node.get("teaches", []) if kind == "lesson" else []:
                if not CAPABILITY_RE.fullmatch(str(capability)):
                    problems.append(f"{nlabel}.teaches has invalid capability id {capability!r}")
                if capability in capability_owners:
                    problems.append(f"capability {capability!r} has multiple teaching owners")
                capability_owners[capability] = (nid, index)
        if detailed and not MIN_PLANNED_LESSONS <= len(lessons) <= MAX_PLANNED_LESSONS:
            problems.append(
                f"{label} must contain {MIN_PLANNED_LESSONS} through "
                f"{MAX_PLANNED_LESSONS} planned lessons so its sealed map can satisfy Phase 3")
        if detailed and map_version >= 6 and isinstance(section.get("lessonCount"), int) \
                and len(lessons) != section["lessonCount"]:
            problems.append(
                f"{label} must contain exactly {section['lessonCount']} planned lessons "
                "sealed by Phase 1")
        if detailed and len(workings) != 1:
            problems.append(f"{label} must contain exactly one Working")
        if detailed and set(taught) != set(section.get("capabilities") or []):
            problems.append(f"{label}.capabilities must exactly match its lesson teaches owners")
    if len(section_ids) != len(set(section_ids)):
        problems.append("section ids contain duplicates")
    if detailed and isinstance(seed, dict):
        from ..language_mastery import seeded_practice_problems
        problems += seeded_practice_problems(seed.get("sections"), sections)
    if len(node_ids) != len(set(node_ids)):
        problems.append("node ids contain duplicates")
    known = set(section_ids) | set(node_ids)
    for owner, dependencies in graph.items():
        for dependency in dependencies:
            if dependency not in known:
                problems.append(f"{owner} depends on nonexistent node {dependency!r}")
            elif positions.get(dependency, (999, 999)) >= positions.get(owner, (-1, -1)):
                problems.append(f"{owner} dependency {dependency!r} must be owned earlier")
    visiting, visited = set(), set()
    def visit(node):
        if node in visiting:
            problems.append(f"dependency cycle reaches {node}")
            return
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph.get(node, []):
            if dependency in graph:
                visit(dependency)
        visiting.remove(node)
        visited.add(node)
    for node in graph:
        visit(node)
    if "artifactContract" in value:
        problems += validate_integrity_graph(sections, detailed)
    graduate = value.get("graduateCapabilities") or []
    for capability in graduate:
        if capability not in capability_owners:
            problems.append(f"graduate capability {capability!r} has no teaching owner")
    for section in sections:
        if not isinstance(section, dict):
            continue
        for node in section.get("nodes") or []:
            if not isinstance(node, dict) or node.get("kind") != "working":
                continue
            for capability in node.get("requires") or []:
                owner = capability_owners.get(capability)
                if owner is None:
                    problems.append(f"{node.get('id')} requires untaught capability {capability!r}")
                elif owner[1] > section.get("ordinal", 0):
                    problems.append(f"{node.get('id')} grades {capability!r} before it is taught")
    problems += validate_mechanism_contract(
        value, sections, positions, detailed=detailed, map_version=map_version)
    language_seed = seed.get("languageMastery") if isinstance(seed, dict) else None
    problems += validate_language_mastery(
        value.get("languageMastery"), sections, capability_owners, graduate, detailed,
        seed=language_seed if seed is not None else None,
        expected_working_performances=expected_working_performances(value))
    evidence_seed = seed.get("masteryEvidence") if isinstance(seed, dict) else None
    problems += validate_mastery_evidence(
        value.get("masteryEvidence"), sections, detailed=detailed,
        seed=evidence_seed if seed is not None else None)
    if "artifactContract" in value:
        problems += validate_artifact_contract(value.get("artifactContract"), sections, detailed)
    obligations = value.get("plannedObligations")
    if not isinstance(obligations, list):
        problems.append("plannedObligations must be an array")
        obligations = []
    obligation_ids, superseded_ids = set(), set()
    order = {sid: index for index, sid in enumerate(section_ids)}
    for index, item in enumerate(obligations):
        label = f"plannedObligations[{index}]"
        problems += _keys(item, OBLIGATION_KEYS, label, OBLIGATION_OPTIONAL_KEYS)
        if not isinstance(item, dict):
            continue
        oid, origin, target = item.get("id"), item.get("origin"), item.get("target")
        if not OBLIGATION_RE.fullmatch(str(oid or "")) or not str(oid).startswith(str(origin) + "-"):
            problems.append(f"{label}.id must be a stable kebab id beginning with its origin")
        if oid in obligation_ids:
            problems.append(f"duplicate obligation id {oid!r}")
        obligation_ids.add(oid)
        if origin not in order or target not in order or order.get(origin, 99) >= order.get(target, -1):
            problems.append(f"{label} must target a real later section")
        if item.get("kind") not in OBLIGATION_KINDS:
            problems.append(f"{label}.kind is invalid")
        for key, limit in (("owner", 240), ("location", 300), ("requirement", 500),
                           ("reason", 500)):
            if not isinstance(item.get(key), str) or not item[key].strip():
                problems.append(f"{label}.{key} must be a non-empty string")
            elif len(item[key]) > limit:
                problems.append(f"{label}.{key} exceeds {limit} characters")
        if map_version >= 3:
            location_problem = section_reference_problem(
                item.get("location"), allow_fragment=False)
            if location_problem:
                problems.append(f"{label}.location {location_problem}")
        problems += _obligation_done(item.get("doneWhen"), f"{label}.doneWhen")
        if map_version >= 3 and isinstance(item.get("doneWhen"), dict):
            for location_index, location in enumerate(
                    item["doneWhen"].get("evidenceLocations") or []):
                evidence_problem = section_reference_problem(
                    location, allow_fragment=True)
                if evidence_problem:
                    problems.append(
                        f"{label}.doneWhen.evidenceLocations[{location_index}] "
                        f"{evidence_problem}")
        if ("supersedes" in item) != ("revisionReason" in item):
            problems.append(f"{label} supersedes and revisionReason must appear together")
        if "supersedes" in item:
            supersedes = item.get("supersedes")
            if not OBLIGATION_RE.fullmatch(str(supersedes or "")) or supersedes == oid:
                problems.append(f"{label}.supersedes must name a different stable obligation id")
            if supersedes in superseded_ids:
                problems.append(f"{label}.supersedes duplicates an earlier supersession")
            superseded_ids.add(supersedes)
            revision_reason = item.get("revisionReason")
            if not isinstance(revision_reason, str) or not 12 <= len(revision_reason.strip()) <= 500:
                problems.append(f"{label}.revisionReason must be 12 through 500 characters")
    problems += validate_semantic_contracts(value, capability_owners, section_ids, detailed)
    if seed:
        if any(isinstance(item, dict) and "supersedes" in item for item in obligations):
            problems.append("Phase 2 cannot supersede obligations; use the audited amendment path")
        seed_sections = [(s.get("id"), s.get("ordinal"), s.get("title"), s.get("promise"),
                          s.get("lessonCount"))
                         for s in seed.get("sections", [])]
        proposed = [(s.get("id"), s.get("ordinal"), s.get("title"), s.get("promise"),
                     s.get("lessonCount"))
                    for s in sections if isinstance(s, dict)]
        if proposed != seed_sections:
            problems.append("Phase 2 may expand the approved section spine, not rewrite it")
        for key in ("buildId", "planSha256", "bounds", "graduateContract",
                    "masteryPerformances", "acceptanceScenarios", "artifactContract",
                    "masteryEvidence"):
            if value.get(key) != seed.get(key):
                problems.append(f"Phase 2 may not alter sealed Phase 1 field {key}")
        proposed_obligations = {item.get("id"): item for item in obligations if isinstance(item, dict)}
        for original in seed.get("plannedObligations", []):
            current = proposed_obligations.get(original.get("id"))
            if current is None:
                problems.append(f"Phase 2 removed planned obligation {original.get('id')}")
                continue
            for key in ("id", "origin", "target", "kind", "requirement"):
                if current.get(key) != original.get(key):
                    problems.append(f"Phase 2 altered {key} of planned obligation {original.get('id')}")
    if "digest" in value and value.get("digest") != digest(value):
        problems.append("sealed course map digest does not match its content")
    return problems


def validate_proposal(build_id, proposal_file=None):
    """Validate the sealed proposal or a deterministic author-check preview."""
    seed = _read_json(seed_path(build_id))
    proposal = _read_json(proposal_file or proposal_path(build_id))
    problems = (validate_course_map(proposal, detailed=True, seed=seed)
                + validate_map_locations(build_id, proposal))
    return (not problems, "" if not problems else "course-map proposal:\n- " + "\n- ".join(problems))


def seal_course_map(build_id):
    seed, proposal = _read_json(seed_path(build_id)), _read_json(proposal_path(build_id))
    problems = (validate_course_map(proposal, detailed=True, seed=seed)
                + validate_map_locations(build_id, proposal))
    if problems:
        raise CourseMapError("Phase 2 course-map proposal is invalid:\n- " + "\n- ".join(problems))
    sealed = copy.deepcopy(proposal)
    sealed.pop("digest", None)
    sealed["digest"] = digest(sealed)
    _atomic_json(map_path(build_id), sealed)
    if not os.path.exists(amendment_path(build_id)):
        _atomic_json(amendment_path(build_id), [])
    return sealed


def load_course_map(build_id):
    value = _read_json(map_path(build_id))
    problems = validate_course_map(value, detailed=True)
    plan = os.path.join(BUILD_DIR, f"{build_id}.plan.md")
    try:
        with open(plan, encoding="utf-8") as handle:
            current_plan_digest = plan_contract_sha256(handle.read())
        if value.get("planSha256") != current_plan_digest:
            problems.append("sealed course map planSha256 does not match the current build plan")
    except OSError:
        problems.append("sealed course map cannot verify its missing build plan")
    if problems:
        raise CourseMapError("sealed course map is invalid:\n- " + "\n- ".join(problems))
    return value
