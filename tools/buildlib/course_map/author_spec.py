"""Compact Phase-2 author surface and deterministic full-map materializer."""
from __future__ import annotations

import copy
import json
import os

from .. import BUILD_DIR, REPO
from . import CourseMapError, _atomic_json, _read_json, proposal_path, seed_path


def spec_root(build_id):
    return os.path.join(BUILD_DIR, f"{build_id}.course-map-author")


def _spec_path(build_id, name):
    return os.path.join(spec_root(build_id), name)


def _exact_keys(value, expected, label):
    if not isinstance(value, dict):
        raise CourseMapError(f"{label} must be a JSON object")
    if set(value) != set(expected):
        raise CourseMapError(
            f"{label} keys must be exactly {', '.join(sorted(expected))}")


def initialize_author_spec(build_id, source=None):
    """Split the writable map fields into bounded files; sealed seed fields stay absent."""
    source = source or (_read_json(proposal_path(build_id))
                        if os.path.isfile(proposal_path(build_id))
                        else _read_json(seed_path(build_id)))
    root = spec_root(build_id)
    os.makedirs(os.path.join(root, "sections"), exist_ok=True)
    _atomic_json(_spec_path(build_id, "course.json"), {
        "graduateCapabilities": copy.deepcopy(source.get("graduateCapabilities") or []),
    })
    _atomic_json(_spec_path(build_id, "mechanisms.json"), {
        "mechanismContract": copy.deepcopy(source.get("mechanismContract") or {}),
    })
    _atomic_json(_spec_path(build_id, "obligations.json"), {
        "plannedObligations": copy.deepcopy(source.get("plannedObligations") or []),
    })
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
    _exact_keys(course, {"graduateCapabilities"}, "course.json")
    _exact_keys(mechanisms, {"mechanismContract"}, "mechanisms.json")
    _exact_keys(obligations, {"plannedObligations"}, "obligations.json")
    value = copy.deepcopy(seed)
    value.update(course)
    value.update(mechanisms)
    value.update(obligations)
    for index, section in enumerate(value.get("sections") or []):
        sid = section.get("id")
        authored = _read_json(os.path.join(root, "sections", f"{sid}.json"))
        expected = {"capabilities", "languagePractice", "dependsOn", "nodes", "projectMilestone"}
        _exact_keys(authored, expected, f"sections/{sid}.json")
        value["sections"][index].update(authored)
    return value


def materialize_author_spec(build_id):
    value = materialized_author_spec(build_id)
    _atomic_json(proposal_path(build_id), value)
    return value
