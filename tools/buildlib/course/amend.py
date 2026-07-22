"""Explicit, audited amendment path for a sealed course map."""
import copy
import os

from ..course_map import (MAP_VERSION, CourseMapError, _atomic_json, _read_json,
                         amendment_path, digest, load_course_map, map_path,
                         validate_course_map, validate_map_locations)
from ..mechanism_contract import upgrade_map as _upgrade_mechanism_contract


def _upgrade_location_contract(value, prior_version):
    """Mechanically translate pre-v3 global placeholders during an audited amendment."""
    if int(prior_version or 0) >= 3:
        return
    for item in value.get("plannedObligations", []):
        if not isinstance(item, dict):
            continue
        origin, target = str(item.get("origin") or ""), str(item.get("target") or "")
        if item.get("location") == f"sections/{origin}":
            item["location"] = "section.toml"
        done = item.get("doneWhen") or {}
        prefix = f"sections/{target}/"
        done["evidenceLocations"] = [
            location[len(prefix):] if isinstance(location, str) and location.startswith(prefix)
            else location
            for location in done.get("evidenceLocations") or []
        ]


def _upgrade_lesson_count_contract(value, prior_version):
    """Seal the already-authored lesson count when an older map enters v6."""
    if int(prior_version or 0) >= 6:
        return
    for section in value.get("sections", []):
        if isinstance(section, dict):
            section["lessonCount"] = sum(
                1 for node in section.get("nodes") or []
                if isinstance(node, dict) and node.get("kind") == "lesson")


def amend_course_map(build_id, candidate, reason):
    if not isinstance(reason, str) or len(reason.strip()) < 12:
        raise CourseMapError("an amendment needs a specific reason of at least 12 characters")
    if not isinstance(candidate, dict):
        raise CourseMapError("an amendment candidate must be a complete course-map object")
    old = load_course_map(build_id)
    revised = copy.deepcopy(candidate)
    revised.pop("digest", None)
    _upgrade_location_contract(revised, old.get("version"))
    _upgrade_mechanism_contract(revised, old.get("version"))
    # An amendment preserves a legacy schema rather than manufacturing new Phase-1
    # authority after authoring has begun. New builds already enter at MAP_VERSION.
    if int(old.get("version") or 0) >= 6:
        _upgrade_lesson_count_contract(revised, old.get("version"))
        revised["version"] = MAP_VERSION
    else:
        revised["version"] = old.get("version")
    revised["revision"] = old["revision"] + 1
    for key in ("buildId", "planSha256", "bounds"):
        if revised.get(key) != old.get(key):
            raise CourseMapError(f"an amendment may not change {key}")
    problems = (validate_course_map(revised, detailed=True)
                + validate_map_locations(build_id, revised))
    if problems:
        raise CourseMapError("course-map amendment is invalid:\n- " + "\n- ".join(problems))
    old_sections = {s["id"]: s for s in old["sections"]}
    new_sections = {s["id"]: s for s in revised["sections"]}
    changed = [sid for sid in sorted(set(old_sections) | set(new_sections))
               if old_sections.get(sid) != new_sections.get(sid)]
    top_level = {key: {"old": old.get(key), "new": revised.get(key)}
                 for key in ("graduateContract", "graduateCapabilities",
                             "masteryPerformances", "languageMastery",
                             "acceptanceScenarios")
                 if old.get(key) != revised.get(key)}
    if top_level:
        changed = [section["id"] for section in revised["sections"]]
    obligations_changed = old.get("plannedObligations") != revised.get("plannedObligations")
    if obligations_changed and not changed:
        old_obligations = {item.get("id"): item for item in old.get("plannedObligations", [])
                           if isinstance(item, dict)}
        new_obligations = {item.get("id"): item for item in revised.get("plannedObligations", [])
                           if isinstance(item, dict)}
        changed_items = [item for oid in set(old_obligations) | set(new_obligations)
                         for item in (old_obligations.get(oid), new_obligations.get(oid))
                         if item is not None and old_obligations.get(oid) != new_obligations.get(oid)]
        changed = sorted({item.get("origin") for item in changed_items if item.get("origin")})
    if not changed and not top_level and not obligations_changed:
        raise CourseMapError("the amendment candidate does not change the sealed plan")
    superseding = [item for item in revised.get("plannedObligations", [])
                   if isinstance(item, dict) and item.get("supersedes")]
    if superseding:
        old_by_id = {item["id"]: item for item in old.get("plannedObligations", [])}
        new_claims = [item for item in superseding if old_by_id.get(item["id"]) != item]
        if new_claims:
            from .state import derive_course_state
            active_ids = {item["id"] for item in derive_course_state(build_id)["activeObligations"]}
            for item in new_claims:
                if item["id"] in old_by_id:
                    raise CourseMapError("an existing obligation cannot gain a supersedes claim")
                if item["supersedes"] not in active_ids:
                    raise CourseMapError(
                        f"{item['id']} may supersede only an active earlier obligation")
    revised["digest"] = digest(revised)
    order = [section["id"] for section in revised["sections"]]
    earliest = min((order.index(sid) for sid in changed if sid in order), default=0)
    carried, receipt_updates = [], []
    if changed:
        from .state import _read_json as read_receipt
        from .state import receipt_path
        for sid in order[:earliest]:
            path = receipt_path(build_id, sid)
            receipt = read_receipt(path, {}) or {}
            if receipt.get("mapDigest") != old["digest"]:
                continue
            receipt["carriedFromMapDigest"] = old["digest"]
            receipt["mapDigest"] = revised["digest"]
            receipt["mapRevision"] = revised["revision"]
            receipt_updates.append((path, receipt))
            carried.append(sid)
    journal = _read_json(amendment_path(build_id)) if os.path.exists(amendment_path(build_id)) else []
    journal.append({"revision": revised["revision"], "reason": reason.strip(),
                    "oldDigest": old["digest"], "newDigest": revised["digest"],
                    "changedSections": changed, "topLevelChanges": top_level,
                    "carriedSections": carried,
                    "oldValues": {sid: old_sections.get(sid) for sid in changed},
                    "newValues": {sid: new_sections.get(sid) for sid in changed}})
    _atomic_json(map_path(build_id), revised)
    try:
        _atomic_json(amendment_path(build_id), journal)
    except Exception:
        _atomic_json(map_path(build_id), old)
        raise
    if receipt_updates:
        from .state import _atomic_json as write_receipt
        for path, receipt in receipt_updates:
            write_receipt(path, receipt)
    if changed:
        from .state import invalidate_from
        invalidate_from(build_id, order[earliest])
    return revised
