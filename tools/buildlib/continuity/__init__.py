"""Versioned, machine-checked Phase-3 handoffs and obligation claims.

The sealed course map owns and projects planned work.  A v3 handoff contains only
author-owned discoveries, public contracts, artifact state, and typed fulfillment
evidence.  Authors never transcribe sealed obligations or completion state.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil

from .. import BUILD_DIR, REPO
from ..course_map import (OBLIGATION_DONE_KEYS, OBLIGATION_KEYS, OBLIGATION_KINDS,
                         OBLIGATION_OPTIONAL_KEYS, OBLIGATION_RE, build_id_from_plan,
                         load_course_map, map_path)
from ..course_map.seed import continuity_obligations
from .schema import (CONTRACT_KEYS, FULFILLMENT_KEYS, HANDOFF_KEYS,
                                HANDOFF_V2_KEYS, HANDOFF_VERSION, LEGACY_KEYS,
                                MAX_DISCOVERED_OBLIGATIONS, MAX_HANDOFF_BYTES,
                                SUPPORTED_HANDOFF_VERSIONS,
                                exact_keys as _exact_keys,
                                has_completion_key as _has_completion_key,
                                strings as _strings)


def handoff_dir(tid):
    return os.path.join(BUILD_DIR, f"{tid}.handoffs")


def handoff_path(tid, sid):
    return os.path.join(handoff_dir(tid), f"{sid}.json")


def handoffs_exist(tid):
    return os.path.isdir(handoff_dir(tid))


def reset_handoffs(tid):
    shutil.rmtree(handoff_dir(tid), ignore_errors=True)


def _load(path):
    try:
        if os.path.getsize(path) > MAX_HANDOFF_BYTES:
            return None, f"handoff exceeds {MAX_HANDOFF_BYTES} bytes"
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"handoff is missing or invalid JSON: {exc}"
    return value, ""


def read_handoff(tid, sid):
    value, problem = _load(handoff_path(tid, sid))
    return value if not problem and isinstance(value, dict) else None


def handoff_digest(tid, sid):
    path = handoff_path(tid, sid)
    try:
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except OSError:
        return ""


def planned_edges(plan_path, ids):
    """Legacy/readable projection of Phase 1's `sNN -> sMM` continuity edges."""
    try:
        text = open(plan_path, encoding="utf-8").read()
    except OSError:
        return []
    positions, parsed = {sid: index for index, sid in enumerate(ids)}, []
    for item in continuity_obligations(text, ids):
        origin, target = item["origin"], item["target"]
        parsed.append({"id": item["id"], "origin": origin, "target": target,
                       "requirement": item["requirement"],
                       "valid_order": (origin in positions and target in positions
                                       and positions[origin] < positions[target])})
    return parsed


def _map(plan_path):
    build_id = build_id_from_plan(plan_path)
    if not build_id or not os.path.isfile(map_path(build_id)):
        return build_id, None
    try:
        return build_id, load_course_map(build_id)
    except ValueError:
        return build_id, None


def _empty_fulfillment(oid):
    return {"id": oid, "evidence_locations": [], "capability_ids": [], "proof_ids": [],
            "acceptance_ids": [], "observed_result": ""}


def handoff_discoveries(data, course=None):
    """Return only author-owned discovered obligations from any supported handoff.

    V2 mixed sealed map copies and discoveries in one ``obligations`` array.  Filtering
    known map ids here keeps old verified handoffs readable without importing their
    redundant copies into derived state.  V3 stores only ``discoveries``.
    """
    if not isinstance(data, dict):
        return []
    source = (data.get("discoveries") if data.get("version") == HANDOFF_VERSION
              else data.get("obligations"))
    if not isinstance(source, list):
        return []
    planned_ids = {item.get("id") for item in (course or {}).get("plannedObligations", [])
                   if isinstance(item, dict)}
    return [item for item in source
            if isinstance(item, dict) and item.get("id") not in planned_ids]


def _write_handoff(path, value):
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temp, path)


def migrate_v2(data, sid, course):
    """Remove machine-owned map copies while preserving every author-owned claim."""
    if not isinstance(data, dict) or data.get("version") != 2:
        return data
    return {
        "version": HANDOFF_VERSION,
        "section": data.get("section", sid),
        "artifact_state": data.get("artifact_state", ""),
        "public_contracts": data.get("public_contracts", []),
        "discoveries": handoff_discoveries(data, course),
        "fulfillments": data.get("fulfillments", []),
    }


def handoff_skeleton(sid, ids, plan_path=None, course=None):
    course = course or (_map(plan_path)[1] if plan_path else None)
    if course:
        planned = course.get("plannedObligations", [])
        return {
            "version": HANDOFF_VERSION, "section": sid, "artifact_state": "",
            "public_contracts": [],
            "discoveries": [],
            "fulfillments": [_empty_fulfillment(item["id"]) for item in planned
                             if item.get("target") == sid],
        }
    outgoing, fulfills = [], []
    for edge in planned_edges(plan_path, ids) if plan_path else []:
        if edge["origin"] == sid:
            outgoing.append({"id": edge["id"], "target": edge["target"], "location": "",
                             "requirement": edge["requirement"], "reason": ""})
        elif edge["target"] == sid:
            fulfills.append({"id": edge["id"], "location": "", "evidence": ""})
    return {"version": 1, "section": sid, "artifact_state": "", "public_contracts": [],
            "future_obligations": outgoing, "temporary_artifacts": [],
            "fulfills": fulfills}


def prepare_handoff(tid, sid, reset=False, ids=None, plan_path=None):
    path = handoff_path(tid, sid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    initialize = reset or not os.path.exists(path) or os.path.getsize(path) == 0
    if initialize and ids is not None:
        _write_handoff(path, handoff_skeleton(sid, ids, plan_path))
    elif ids is not None and plan_path:
        data, problem = _load(path)
        course = _map(plan_path)[1]
        if not problem and isinstance(data, dict) and data.get("version") == 2 and course:
            _write_handoff(path, migrate_v2(data, sid, course))
    return path


def migrate_v1(data, sid):
    """Normalize a legacy handoff without inventing proof or a checkmark."""
    obligations = []
    if not isinstance(data, dict):
        return None
    for kind, source, requirement_key, owner_key in (
            ("future-requirement", "future_obligations", "requirement", "requirement"),
            ("temporary-retirement", "temporary_artifacts", "retirement", "artifact")):
        for item in data.get(source, []) if isinstance(data.get(source), list) else []:
            if not isinstance(item, dict):
                continue
            obligations.append({
                "id": item.get("id", ""), "origin": sid, "target": item.get("target", ""),
                "kind": kind, "owner": item.get(owner_key, ""),
                "location": item.get("location", ""),
                "requirement": item.get(requirement_key, ""),
                "reason": item.get("reason", "legacy v1 claim requires v2 verification"),
                "doneWhen": {"evidenceLocations": [], "capabilityIds": [], "proofIds": [],
                             "acceptanceIds": [], "observedResult": "legacy claim needs proof"},
            })
    fulfillments = []
    for item in data.get("fulfills", []) if isinstance(data.get("fulfills"), list) else []:
        if isinstance(item, dict):
            location = item.get("location")
            fulfillments.append({"id": item.get("id", ""),
                                 "evidence_locations": [location] if location else [],
                                 "capability_ids": [], "proof_ids": [], "acceptance_ids": [],
                                 "observed_result": item.get("evidence", "")})
    return {"version": HANDOFF_VERSION, "section": sid,
            "artifact_state": data.get("artifact_state", ""),
            "public_contracts": data.get("public_contracts", []),
            "discoveries": obligations, "fulfillments": fulfillments}


def _safe_location(tid, sid, raw):
    if not isinstance(raw, str) or not raw.strip():
        return False
    root = os.path.realpath(os.path.join(REPO, "tomes", tid, "sections", sid))
    relative = raw.split("#", 1)[0]
    legacy_prefix = f"sections/{sid}/"
    if relative.startswith(legacy_prefix):
        relative = relative[len(legacy_prefix):]
    target = os.path.realpath(os.path.join(root, relative))
    return target.startswith(root + os.sep) and os.path.isfile(target)


def _legacy_validate(tid, sid, ids, data, plan_path):
    problems = _exact_keys(data, LEGACY_KEYS, "legacy handoff")
    if not isinstance(data, dict):
        return problems
    if data.get("version") != 1 or data.get("section") != sid:
        problems.append("legacy handoff version/section does not match")
    if len(str(data.get("artifact_state") or "").strip()) < 20:
        problems.append("artifact_state must describe the cumulative learner artifact")
    positions = {value: index for index, value in enumerate(ids)}
    introduced = {}
    for list_name in ("future_obligations", "temporary_artifacts"):
        items = data.get(list_name)
        if not isinstance(items, list):
            problems.append(f"{list_name} must be an array")
            continue
        for item in items:
            if not isinstance(item, dict):
                problems.append(f"{list_name} entries must be objects")
                continue
            oid, target = item.get("id"), item.get("target")
            if not OBLIGATION_RE.fullmatch(str(oid or "")) or not str(oid).startswith(sid + "-"):
                problems.append(f"legacy obligation {oid!r} must begin with {sid}-")
            if target not in positions or positions[target] <= positions.get(sid, -1):
                problems.append(f"legacy obligation {oid!r} must target a later section")
            if not _safe_location(tid, sid, item.get("location")):
                problems.append(f"legacy obligation {oid!r} location does not exist")
            introduced[oid] = item
    for edge in planned_edges(plan_path, ids) if plan_path else []:
        if edge["origin"] == sid:
            item = introduced.get(edge["id"])
            if not item or item.get("target") != edge["target"]:
                problems.append(f"missing planned legacy obligation {edge['id']}")
    return problems


def _prior_obligations(tid, sid, ids, course):
    planned = (course or {}).get("plannedObligations", [])
    superseded = {item.get("supersedes") for item in planned if isinstance(item, dict)
                  and item.get("supersedes")}
    out = {item["id"]: item for item in planned
           if item.get("origin") in ids[:ids.index(sid)] and item["id"] not in superseded}
    accepted = set()
    if course:
        try:
            from ..course.state import derive_course_state
            state = derive_course_state(course["buildId"], write=False)
            accepted = {row["id"] for row in state["sections"]
                        if row["status"] == "verified"}
        except (OSError, ValueError, KeyError):
            accepted = set()
    for origin in ids[:ids.index(sid)]:
        if origin not in accepted:
            continue
        data = read_handoff(tid, origin)
        if not data or data.get("version") not in SUPPORTED_HANDOFF_VERSIONS:
            continue
        for item in handoff_discoveries(data, course):
            if (isinstance(item, dict) and item.get("id") not in out
                    and item.get("id") not in superseded):
                out[item["id"]] = item
    return out


def validate_handoff(tid, sid, ids, plan_path=None):
    path = handoff_path(tid, sid)
    data, load_problem = _load(path)
    prefix = os.path.relpath(path, REPO)
    if load_problem:
        return False, f"{prefix}: {load_problem}"
    if isinstance(data, dict) and data.get("version") == 1:
        problems = _legacy_validate(tid, sid, ids, data, plan_path)
        return (not problems, "" if not problems else prefix + ":\n- " + "\n- ".join(problems))
    version = data.get("version") if isinstance(data, dict) else None
    expected_keys = HANDOFF_V2_KEYS if version == 2 else HANDOFF_KEYS
    problems = _exact_keys(data, expected_keys, "handoff")
    if not isinstance(data, dict):
        return False, prefix + ":\n- " + "\n- ".join(problems)
    if version not in SUPPORTED_HANDOFF_VERSIONS:
        problems.append(
            f"version must be one of {list(SUPPORTED_HANDOFF_VERSIONS)}; new handoffs use "
            f"version {HANDOFF_VERSION}")
    if data.get("section") != sid:
        problems.append(f"section must be {sid}")
    state = data.get("artifact_state")
    if not isinstance(state, str) or not 20 <= len(state.strip()) <= 1600:
        problems.append("artifact_state must be 20 through 1600 characters")
    if _has_completion_key(data):
        problems.append("handoffs may not author completion/checkmark fields")
    build_id, course = _map(plan_path)
    if build_id and not course:
        problems.append("the sealed course map is missing, corrupt, or stale")
    positions = {value: index for index, value in enumerate(ids)}
    capabilities = {cap for section in (course or {}).get("sections", [])
                    for cap in section.get("capabilities", [])}
    proofs = set(ids)
    acceptance = set((course or {}).get("acceptanceScenarios", []))
    contracts = data.get("public_contracts")
    if not isinstance(contracts, list):
        problems.append("public_contracts must be an array")
        contracts = []
    for index, item in enumerate(contracts):
        label = f"public_contracts[{index}]"
        problems += _exact_keys(item, CONTRACT_KEYS, label)
        if isinstance(item, dict):
            if not _safe_location(tid, sid, item.get("location")):
                problems.append(f"{label}.location must name an existing current-section file")
            for key in CONTRACT_KEYS:
                if not isinstance(item.get(key), str) or not item[key].strip():
                    problems.append(f"{label}.{key} must be a non-empty string")
            for key, maximum in (("name", 120), ("location", 300), ("promise", 500)):
                if isinstance(item.get(key), str) and len(item[key]) > maximum:
                    problems.append(f"{label}.{key} exceeds {maximum} characters")
    field = "obligations" if version == 2 else "discoveries"
    authored = data.get(field)
    if not isinstance(authored, list):
        problems.append(f"{field} must be an array")
        authored = []
    planned_all = {item["id"]: item for item in (course or {}).get("plannedObligations", [])
                   if isinstance(item, dict) and item.get("id")}
    planned = {oid: item for oid, item in planned_all.items() if item.get("origin") == sid}
    discovered_count = sum(1 for item in authored
                           if isinstance(item, dict) and item.get("id") not in planned_all)
    if discovered_count > MAX_DISCOVERED_OBLIGATIONS:
        problems.append(
            f"discovered obligations exceeds {MAX_DISCOVERED_OBLIGATIONS} items; "
            "use a validated map amendment to consolidate")
    introduced = {}
    discoveries = []
    for index, item in enumerate(authored):
        label = f"{field}[{index}]"
        problems += _exact_keys(item, OBLIGATION_KEYS, label, OBLIGATION_OPTIONAL_KEYS)
        if not isinstance(item, dict):
            continue
        oid, target = item.get("id"), item.get("target")
        if oid in planned_all:
            if version == 2 and oid in planned and item == planned[oid]:
                continue  # readable compatibility for already-verified v2 handoffs
            if version == 2:
                problems.append(
                    f"planned obligation {oid} differs from the sealed map; remove its handoff copy")
            else:
                problems.append(
                    f"{label} repeats sealed obligation {oid}; planned work is harness-projected")
            continue
        discoveries.append(item)
        if not OBLIGATION_RE.fullmatch(str(oid or "")) or not str(oid).startswith(sid + "-"):
            problems.append(f"{label}.id must be a stable kebab id beginning {sid}-")
        if oid in introduced:
            problems.append(f"duplicate obligation id {oid!r}")
        introduced[oid] = item
        if item.get("origin") != sid:
            problems.append(f"{label}.origin must be {sid}")
        if target not in positions or positions.get(target, -1) <= positions.get(sid, -1):
            problems.append(f"{label}.target must be a real later section")
        if item.get("kind") not in OBLIGATION_KINDS:
            problems.append(f"{label}.kind is invalid")
        if not _safe_location(tid, sid, item.get("location")):
            problems.append(f"{label}.location must name an existing current-section file")
        for key in ("owner", "requirement", "reason"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                problems.append(f"{label}.{key} must be a non-empty string")
        for key, maximum in (("owner", 240), ("location", 300),
                             ("requirement", 500), ("reason", 500)):
            if isinstance(item.get(key), str) and len(item[key]) > maximum:
                problems.append(f"{label}.{key} exceeds {maximum} characters")
        done = item.get("doneWhen")
        problems += _exact_keys(done, OBLIGATION_DONE_KEYS, f"{label}.doneWhen")
        if isinstance(done, dict):
            for key in ("evidenceLocations", "capabilityIds", "proofIds", "acceptanceIds"):
                problems += _strings(done.get(key), f"{label}.doneWhen.{key}")
            observed = done.get("observedResult")
            if not isinstance(observed, str) or len(observed.strip()) < 8:
                problems.append(f"{label}.doneWhen.observedResult is incomplete")
            elif len(observed) > 500:
                problems.append(f"{label}.doneWhen.observedResult exceeds 500 characters")
        if "supersedes" in item:
            problems.append(f"{label} may supersede only through the sealed amendment path")
    if sid == ids[-1] and discoveries:
        problems.append("the final section may not create discovered future work")
    prior = _prior_obligations(tid, sid, ids, course)
    due = {oid: item for oid, item in prior.items() if item.get("target") == sid}
    fulfillments = data.get("fulfillments")
    if not isinstance(fulfillments, list):
        problems.append("fulfillments must be an array")
        fulfillments = []
    claimed = {}
    for index, item in enumerate(fulfillments):
        label = f"fulfillments[{index}]"
        problems += _exact_keys(item, FULFILLMENT_KEYS, label)
        if not isinstance(item, dict):
            continue
        oid = item.get("id")
        if oid in claimed:
            problems.append(f"duplicate fulfillment id {oid!r}")
        claimed[oid] = item
        if oid not in due:
            problems.append(f"{label} claims an unknown, closed, or not-yet-due obligation")
            continue
        for key, valid in (("capability_ids", capabilities), ("proof_ids", proofs),
                           ("acceptance_ids", acceptance)):
            problems += _strings(item.get(key), f"{label}.{key}", maximum=160)
            for value in item.get(key) or []:
                if value not in valid:
                    problems.append(f"{label}.{key} cites nonexistent id {value!r}")
        locations = item.get("evidence_locations")
        problems += _strings(locations, f"{label}.evidence_locations", allow_empty=False,
                             maximum=300)
        for location in locations or []:
            if not _safe_location(tid, sid, location):
                problems.append(f"{label} evidence location does not exist: {location!r}")
        observed = item.get("observed_result")
        if not isinstance(observed, str) or len(observed.strip()) < 8:
            problems.append(f"{label}.observed_result must state what was actually observed")
        elif len(observed) > 500:
            problems.append(f"{label}.observed_result exceeds 500 characters")
        required = due[oid].get("doneWhen") or {}
        for source, target_key in (("capabilityIds", "capability_ids"),
                                   ("proofIds", "proof_ids"),
                                   ("acceptanceIds", "acceptance_ids")):
            missing = set(required.get(source) or []) - set(item.get(target_key) or [])
            if missing:
                problems.append(f"{label} is missing required {target_key}: {sorted(missing)}")
        required_locations = set(required.get("evidenceLocations") or [])
        if required_locations - set(locations or []):
            problems.append(f"{label} is missing required evidence locations: "
                            f"{sorted(required_locations - set(locations or []))}")
    missing_due = sorted(set(due) - set(claimed))
    if missing_due:
        problems.append("fulfillments is missing obligations due now: " + ", ".join(missing_due))
    return (not problems, "" if not problems else prefix + ":\n- " + "\n- ".join(problems))


def validate_all_handoffs(tid, ids, plan_path=None):
    reports, discovered = [], set()
    course = _map(plan_path)[1] if plan_path else None
    for sid in ids:
        clean, report = validate_handoff(tid, sid, ids, plan_path)
        if not clean:
            reports.append(report)
        data = read_handoff(tid, sid) or {}
        if data.get("version") in SUPPORTED_HANDOFF_VERSIONS:
            for item in handoff_discoveries(data, course):
                oid = item.get("id") if isinstance(item, dict) else None
                if oid in discovered:
                    reports.append(f"duplicate obligation id across handoffs: {oid}")
                discovered.add(oid)
    return not reports, "\n".join(reports)


def continuity_prompt(tid, sid, ids, plan_path=None):
    rel = os.path.relpath(handoff_path(tid, sid), REPO)
    return ("\n\n===== HANDOFF v2 CLAIM PROTOCOL =====\n"
            f"Write the exact current-section proposal at `{rel}`. The sealed map and harness "
            "project every planned obligation; never copy one into this author-writable handoff. "
            "Add only genuine discovered future work under `discoveries`, cite existing "
            "current-section evidence for every due fulfillment, run the assigned check, and stop. "
            "Do not add completion/checkmark booleans; only the harness closes obligations.\n"
            "===== END HANDOFF v2 CLAIM PROTOCOL =====")


def reconciliation_prompt(tid, ids, plan_path=None):
    clean, report = validate_all_handoffs(tid, ids, plan_path)
    course = _map(plan_path)[1] if plan_path else None
    rows = []
    for sid in ids:
        data = read_handoff(tid, sid)
        rows.append(f"- {sid}: " + ("missing" if not data else
                    f"v{data.get('version')} discoveries={len(handoff_discoveries(data, course))} "
                    f"fulfillments={len(data.get('fulfillments', []))}"))
    return ("\n\n===== WHOLE-TOME CONTINUITY AUDIT =====\n"
            f"Deterministic handoff gate: {'CLOSED' if clean else 'BROKEN'}\n"
            + (report + "\n" if report else "") + "\n".join(rows))
