"""Compact Phase-2 author surface and deterministic full-map materializer."""
from __future__ import annotations

import copy
import json
import os

from .. import BUILD_DIR, REPO
from ..language_mastery import seeded_practice_problems
from ..phase2_audit import audit_path, audit_problems, initialize_audit
from . import CourseMapError, _atomic_json, _read_json, proposal_path, seed_path


def spec_root(build_id):
    return os.path.join(BUILD_DIR, f"{build_id}.course-map-author")


def preview_path(build_id):
    """Generated Phase-2 preview inside the author's writable compact-spec root."""
    return os.path.join(spec_root(build_id), "materialized-preview.json")


def _spec_path(build_id, name):
    return os.path.join(spec_root(build_id), name)


def _exact_keys(value, expected, label):
    if not isinstance(value, dict):
        raise CourseMapError(f"{label} must be a JSON object")
    if set(value) != set(expected):
        raise CourseMapError(
            f"{label} keys must be exactly {', '.join(sorted(expected))}")


def _language_performance_spec(source):
    language = source.get("languageMastery") if isinstance(source, dict) else None
    performances = language.get("performances") if isinstance(language, dict) else []
    return {"performances": [
        {"id": str(item.get("id") or ""),
         "capabilityIds": copy.deepcopy(item.get("capabilityIds") or [])}
        for item in performances or [] if isinstance(item, dict)
    ]}


def _apply_language_performance_spec(value, authored):
    _exact_keys(authored, {"performances"}, "course.json.languageMastery")
    records = authored.get("performances")
    if not isinstance(records, list):
        raise CourseMapError("course.json.languageMastery.performances must be an array")
    language = value.get("languageMastery")
    seeded = language.get("performances") if isinstance(language, dict) else []
    if len(records) != len(seeded or []):
        raise CourseMapError(
            "course.json.languageMastery.performances must preserve every seeded performance")
    for index, record in enumerate(records):
        label = f"course.json.languageMastery.performances[{index}]"
        _exact_keys(record, {"id", "capabilityIds"}, label)
        original = seeded[index]
        if record.get("id") != original.get("id"):
            raise CourseMapError(f"{label}.id must preserve {original.get('id')!r}")
        capabilities = record.get("capabilityIds")
        if not isinstance(capabilities, list) or any(
                not isinstance(item, str) or not item.strip() for item in capabilities):
            raise CourseMapError(f"{label}.capabilityIds must be an array of capability ids")
        original["capabilityIds"] = copy.deepcopy(capabilities)


def initialize_author_spec(build_id, source=None):
    """Split the writable map fields into bounded files; sealed seed fields stay absent."""
    # A generated proposal is output, never a source of authorship. Reinitializing
    # Phase 2 must therefore start from the sealed Phase-1 seed unless the Phase-1
    # transition explicitly supplies that same seed in memory.
    if source is None:
        source = _read_json(seed_path(build_id))
    root = spec_root(build_id)
    os.makedirs(os.path.join(root, "sections"), exist_ok=True)
    _atomic_json(_spec_path(build_id, "course.json"), {
        "graduateCapabilities": copy.deepcopy(source.get("graduateCapabilities") or []),
        "languageMastery": _language_performance_spec(source),
    })
    _atomic_json(_spec_path(build_id, "mechanisms.json"), {
        "mechanismContract": copy.deepcopy(source.get("mechanismContract") or {}),
    })
    _atomic_json(_spec_path(build_id, "obligations.json"), {
        "plannedObligations": copy.deepcopy(source.get("plannedObligations") or []),
    })
    initialize_audit(build_id, source, overwrite=True, build_dir=BUILD_DIR)
    for section in source.get("sections") or []:
        sid = str(section.get("id") or "")
        if not sid:
            continue
        _atomic_json(os.path.join(root, "sections", f"{sid}.json"), {
            "capabilities": copy.deepcopy(section.get("capabilities") or []),
            "languagePractice": copy.deepcopy(section.get("languagePractice") or []),
            "dependsOn": copy.deepcopy(section.get("dependsOn") or []),
            "nodes": copy.deepcopy(section.get("nodes") or []),
            "projectMilestone": str(section.get("projectMilestone") or section.get("promise") or ""),
        })
    return root


def materialized_author_spec(build_id):
    """Build the full proposal in memory from sealed seed plus compact author files."""
    seed = _read_json(seed_path(build_id))
    root = spec_root(build_id)
    if not os.path.isdir(root):
        raise CourseMapError(
            f"{os.path.relpath(root, REPO)} is missing; restart Phase 2 or initialize its author spec")
    course = _read_json(_spec_path(build_id, "course.json"))
    mechanisms = _read_json(_spec_path(build_id, "mechanisms.json"))
    obligations = _read_json(_spec_path(build_id, "obligations.json"))
    audit = _read_json(audit_path(build_id, BUILD_DIR))
    _exact_keys(course, {"graduateCapabilities", "languageMastery"}, "course.json")
    _exact_keys(mechanisms, {"mechanismContract"}, "mechanisms.json")
    _exact_keys(obligations, {"plannedObligations"}, "obligations.json")
    value = copy.deepcopy(seed)
    value["graduateCapabilities"] = copy.deepcopy(course["graduateCapabilities"])
    _apply_language_performance_spec(value, course["languageMastery"])
    value.update(mechanisms)
    value.update(obligations)
    for index, section in enumerate(value.get("sections") or []):
        sid = section.get("id")
        authored = _read_json(os.path.join(root, "sections", f"{sid}.json"))
        expected = {"capabilities", "languagePractice", "dependsOn", "nodes", "projectMilestone"}
        _exact_keys(authored, expected, f"sections/{sid}.json")
        value["sections"][index].update(authored)
    practice_errors = seeded_practice_problems(seed.get("sections"), value.get("sections"))
    if practice_errors:
        raise CourseMapError(
            "Phase 2 language practice is invalid:\n- " + "\n- ".join(practice_errors))
    try:
        plan_text = open(os.path.join(BUILD_DIR, f"{build_id}.plan.md"), encoding="utf-8").read()
    except OSError as exc:
        raise CourseMapError(f"Phase 2 audit cannot read the sealed plan: {exc}") from exc
    # Compact Phase-2 sources are new authorship, even when a build is resumed.
    # Legacy v1 remains readable by the general audit library but cannot pass this
    # materialization boundary and omit the v2-only closure tables.
    audit_errors = audit_problems(audit, value, plan_text, required_version=2)
    if audit_errors:
        raise CourseMapError("Phase 2 audit is invalid:\n- " + "\n- ".join(audit_errors))
    return value


def materialize_author_spec(build_id):
    value = materialized_author_spec(build_id)
    _atomic_json(proposal_path(build_id), value)
    return value


def materialize_author_preview(build_id):
    """Write a disposable deterministic preview without exposing the sealed proposal."""
    value = materialized_author_spec(build_id)
    _atomic_json(preview_path(build_id), value)
    return value
