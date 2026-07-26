"""Adopt a tome that was authored before the harness contracts it is now gated on.

Two artifacts are reconstructed here: the sealed course map, and the per-section
continuity handoffs. Both are harness-owned, so a reviewer AI staring at "no such
file" can neither create them nor route around them, and the build stalls on a
failure that has nothing to do with the teaching.

Phase 1 seals a map from the build plan and every later gate checks the tome
against it. A tome finished before that contract shipped has neither the map nor
a plan in the format `seed_course_map` can parse, so every gate fails on a
missing file rather than on anything an author or reviewer could repair.

Adoption closes that gap the one honest way left: the authored tome is the only
surviving record of what was planned, so the map is derived from the tome. Be
clear about what that costs. A planned map is a promise made before the work and
can catch the author drifting from it; an adopted map is a photograph taken
after, so it certifies nothing about how the tome was built. It earns its keep
from the moment it is sealed, by pinning the shape every later edit has to hold.
`adoptedFromTome` records which kind it is so nobody reads it as the stronger one.

Adoption stays deliberately mechanical -- ids, titles, teaches, and requires that
already exist in the tome, copied across. It invents no mechanism contract and no
planned obligations, because a guess there would be indistinguishable from an
audited fact later. Sealing goes through `seal_course_map`, the same gate a
planned map passes, so an adopted map is never held to a weaker standard.
"""
from __future__ import annotations

import glob
import html
import json
import os
import re
import tomllib

from .. import BUILD_DIR, REPO
from ..course.limits import MAX_SECTIONS, MIN_SECTIONS
from . import _atomic_json, map_path, proposal_path, seal_course_map, seed_path
from .plan import plan_contract_sha256
from .schema import MAX_PLANNED_LESSONS, MIN_PLANNED_LESSONS, SECTION_CHECKS

# The map records what a tome already contains, so it declares the lowest version
# whose shape the tome can actually fill. v4 would demand a per-node mechanism
# ledger that no pre-v4 tome recorded, and inventing one would hand the free
# surface scan a set of owners nobody ever verified.
ADOPTED_MAP_VERSION = 3
LESSON_CHECKS = ["learner-construction", "lesson-source"]
WORKING_CHECKS = ["learner-construction", "working-replay"]
LAB_CHECKS = ["learner-evidence", "variant-proof"]
# Artifact names are quoted in the Working brief as code spans. Requiring a dot
# keeps prose like `pip install` out without needing to know any file extension.
_CODE_SPAN = re.compile(r"<code>(.*?)</code>", re.S)
_ARTIFACT = re.compile(r"[A-Za-z0-9_./-]+\.[A-Za-z0-9]+\Z")


class AdoptionError(ValueError):
    """The tome does not carry enough structure to reconstruct a map from it."""


def _text(value, limit):
    """Flatten authored HTML to the plain sentence a map field holds."""
    plain = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain[:limit].rstrip() if len(plain) > limit else plain


def _slug(value, fallback):
    slug = re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", str(value or "").lower())).strip("-")
    return slug or fallback


def _artifacts(freestyle, sid):
    """Name the files the Working asks the learner to hand in.

    The brief quotes them as code spans. This is a reconstruction, not a sealed
    author claim, so when nothing looks like a filename the section still adopts
    with one honest placeholder rather than failing the whole tome.
    """
    found = []
    for span in _CODE_SPAN.findall(str((freestyle or {}).get("brief") or "")):
        name = html.unescape(span).strip().strip("/")
        if _ARTIFACT.fullmatch(name) and name not in found:
            found.append(name)
    return found[:12] or [f"{sid}-working-submission"]


def _section_map(tome_path, sid, ordinal, load_section):
    section = load_section(tome_path, sid)
    lessons = [item for item in (section.get("lessons") or []) if isinstance(item, dict)]
    if not MIN_PLANNED_LESSONS <= len(lessons) <= MAX_PLANNED_LESSONS:
        raise AdoptionError(
            f"{sid} has {len(lessons)} lessons; a map can only hold "
            f"{MIN_PLANNED_LESSONS} through {MAX_PLANNED_LESSONS}")
    freestyle = section.get("freestyle")
    if not isinstance(freestyle, dict):
        raise AdoptionError(f"{sid} has no [freestyle] Working to adopt")
    promise = (_text(section.get("brief"), 360) or _text(section.get("title"), 360)
               or f"Section {sid}")
    milestone = _text(section.get("build"), 360) or promise
    nodes, taught = [], []
    for index, lesson in enumerate(lessons, 1):
        teaches = [str(item) for item in (lesson.get("teaches") or [])]
        if not teaches:
            raise AdoptionError(f"{sid} lesson {index} teaches nothing the map can own")
        taught += teaches
        nodes.append({
            "id": f"{sid}.l{index:02d}", "kind": "lesson",
            "title": _text(lesson.get("title"), 120) or f"{sid} lesson {index}",
            "teaches": teaches,
            "dependsOn": [f"{sid}.l{index - 1:02d}"] if index > 1 else [],
            "validationDependencies": [],
            "doneWhen": {"checks": list(LESSON_CHECKS)},
        })
    requires = [str(item) for item in (freestyle.get("requires") or [])]
    if not requires:
        raise AdoptionError(f"{sid}.working requires nothing the map can grade")
    nodes.append({
        "id": f"{sid}.working", "kind": "working",
        "title": _text(freestyle.get("title"), 120) or f"{sid} Working",
        "requires": requires,
        "dependsOn": [f"{sid}.l{len(lessons):02d}"],
        "projectMilestone": milestone,
        "learnerOwnedArtifacts": _artifacts(freestyle, sid),
        "validationDependencies": [],
        "doneWhen": {"checks": list(WORKING_CHECKS)},
    })
    # `capabilities` must equal the lesson teaches owners exactly, and a duplicate
    # would mean two lessons claim the same one -- a real tome fault, not a
    # reconstruction detail, so let the map validator name it rather than dedupe.
    return {
        "id": sid, "ordinal": ordinal, "title": _text(section.get("title"), 120) or sid,
        "promise": promise, "capabilities": taught,
        "dependsOn": [f"s{ordinal - 1:02d}"] if ordinal > 1 else [],
        "nodes": nodes, "projectMilestone": milestone,
        "doneWhen": {"checks": sorted(SECTION_CHECKS)},
    }


def _manifest(tome_path):
    import tomllib
    try:
        with open(os.path.join(tome_path, "tome.toml"), "rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise AdoptionError(f"cannot read tome.toml: {exc}") from exc


def _load_section():
    try:
        import tome_layout
    except ModuleNotFoundError:
        from tools import tome_layout
    return tome_layout.load_section


def _shipped_evidence(tome_path):
    """The mastery contract the tome itself ships, or None.

    `generated/mastery-evidence.json` is the sealed runtime copy of the original
    Phase-1 contract, and an installed tome is already graded against exactly this
    object. Putting it back into the map recovers a lost artifact rather than
    reconstructing one, so it is the single part of an adopted map that still carries
    real Phase-1 authority -- and without it a mastery tome fails its own gate on a
    missing contract no author or reviewer can write.
    """
    try:
        with open(os.path.join(tome_path, "generated", "mastery-evidence.json"),
                  encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _authored_labs(tome_path, sid):
    """Every `[masteryLab]` authored under one section, keyed by the node it grades."""
    labs = {}
    for path in sorted(glob.glob(os.path.join(
            tome_path, "sections", sid, "mastery-labs", "*.toml"))):
        try:
            with open(path, "rb") as handle:
                lab = tomllib.load(handle).get("masteryLab")
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise AdoptionError(f"cannot read the authored mastery lab {path}: {exc}") from exc
        if isinstance(lab, dict) and lab.get("nodeId"):
            labs[str(lab["nodeId"])] = lab
    return labs


def _attach_mastery(sections, tome_path, evidence):
    """Bind the tome's own mastery contract onto the reconstructed nodes.

    Each performance names the node that grades it. On a Working that is one extra id.
    A `.lab` performance grades a standalone mastery lab -- a node kind the lesson and
    Working reconstruction never produces -- so the lab is copied in from the authored
    `[masteryLab]` table, the only surviving statement of those fields. Nothing is
    invented here: where a lab and the sealed performance disagree, the map validator
    is left to say so rather than being handed a reconciled guess.
    """
    by_id = {section["id"]: section for section in sections}
    for performance in sorted(evidence.get("performances") or [],
                              key=lambda item: str((item or {}).get("nodeId") or "")):
        pid, node_id = str(performance.get("id")), str(performance.get("nodeId") or "")
        section = by_id.get(node_id.split(".", 1)[0])
        if not section:
            raise AdoptionError(f"mastery performance {pid!r} grades {node_id!r}, "
                                "which belongs to no section of this tome")
        if ".lab" not in node_id:
            node = next((item for item in section["nodes"] if item["id"] == node_id), None)
            if node is None:
                raise AdoptionError(f"mastery performance {pid!r} grades {node_id!r}, "
                                    "a node this tome does not have")
            node.setdefault("masteryPerformances", []).append(pid)
            continue
        lab = _authored_labs(tome_path, section["id"]).get(node_id)
        if not lab:
            raise AdoptionError(
                f"{node_id} is a sealed mastery lab with no [masteryLab] authored under "
                f"sections/{section['id']}/mastery-labs/")
        lessons = [item for item in section["nodes"] if item["kind"] == "lesson"]
        working = next(index for index, item in enumerate(section["nodes"])
                       if item["kind"] == "working")
        section["nodes"].insert(working, {
            "id": node_id, "kind": "mastery-lab",
            "title": _text(lab.get("title"), 120) or node_id,
            "performanceKind": lab.get("performanceKind"),
            "capabilityIds": [str(item) for item in (lab.get("capabilityIds") or [])],
            "cognitiveTasks": [str(item) for item in (lab.get("cognitiveTasks") or [])],
            "contextRelation": lab.get("contextRelation"),
            "aidPolicy": lab.get("aidPolicy"),
            "variantFamilyId": str(lab.get("variantFamilyId") or ""),
            "rationaleRequired": bool(lab.get("rationaleRequired")),
            "dependsOn": [lessons[-1]["id"]] if lessons else [],
            "validationDependencies": [],
            "doneWhen": {"checks": list(LAB_CHECKS)},
        })


def adopted_course_map(build_id, tome_id):
    """Return a full course map derived from an already-authored tome."""
    tome_path = os.path.join(REPO, "tomes", tome_id)
    manifest = _manifest(tome_path)
    ids = [str(value) for value in ((manifest.get("content") or {}).get("sections") or [])]
    if not MIN_SECTIONS <= len(ids) <= MAX_SECTIONS:
        raise AdoptionError(
            f"tome.toml lists {len(ids)} sections; a map holds "
            f"{MIN_SECTIONS} through {MAX_SECTIONS}")
    plan = os.path.join(BUILD_DIR, f"{build_id}.plan.md")
    try:
        with open(plan, encoding="utf-8") as handle:
            plan_digest = plan_contract_sha256(handle.read())
    except OSError as exc:
        raise AdoptionError(f"cannot read the build plan {plan}: {exc}") from exc
    load_section = _load_section()
    sections = [_section_map(tome_path, sid, ordinal, load_section)
                for ordinal, sid in enumerate(ids, 1)]
    evidence = _shipped_evidence(tome_path) if manifest.get("mastery") else None
    if manifest.get("mastery") and not evidence:
        raise AdoptionError(
            "this tome declares [mastery] but ships no generated/mastery-evidence.json, so "
            "there is no mastery contract left to recover; a map sealed without one fails "
            "the gate on a contract neither an author nor a reviewer is allowed to write")
    if evidence:
        _attach_mastery(sections, tome_path, evidence)
    narrative = manifest.get("narrative") or {}
    meta = manifest.get("meta") or {}
    contract = (_text(narrative.get("objective"), 2400)
                or _text(meta.get("description"), 2400))
    if not contract:
        raise AdoptionError("tome.toml declares no narrative objective to graduate against")
    # A graduate holds what the last Working grades, which is the only
    # end-of-course capability claim the tome actually makes.
    final = next(node for node in reversed(sections[-1]["nodes"])
                 if node["kind"] == "working")
    graduate = list(dict.fromkeys(final["requires"]))
    scenarios = list(dict.fromkeys(
        _slug(section.get("title"), section["id"]) for section in sections))
    return {
        **({"masteryEvidence": evidence} if evidence else {}),
        "version": ADOPTED_MAP_VERSION, "revision": 1, "buildId": build_id,
        "planSha256": plan_digest,
        "bounds": {"minSections": MIN_SECTIONS, "maxSections": MAX_SECTIONS},
        "graduateContract": contract,
        "graduateCapabilities": graduate,
        "masteryPerformances": [contract],
        "acceptanceScenarios": scenarios,
        "sections": sections,
        "plannedObligations": [],
        "adoptedFromTome": tome_id,
    }


def adopt_handoffs(tome_id, section_ids):
    """Create an empty handoff for every section missing one; return the new ids.

    Deliberately empty. `artifact_state` is what the project looks like when a
    section ends, and nothing in the authored tome states it in a form worth
    trusting -- a guess here would be a fact the harness invented and then
    certified as an author's. So the harness creates the file and leaves it
    failing its own gate, which turns an unactionable "no such file" into
    "artifact_state must be 20 through 1600 characters" against a path the
    reviewer can actually write.
    """
    from ..continuity import handoff_path
    from ..continuity.schema import HANDOFF_VERSION
    created = []
    for sid in section_ids:
        path = handoff_path(tome_id, sid)
        if os.path.exists(path) and os.path.getsize(path):
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _atomic_json(path, {
            "version": HANDOFF_VERSION, "section": sid, "artifact_state": "",
            "public_contracts": [], "discoveries": [], "fulfillments": [],
        })
        created.append(sid)
    return created


def adopt_course_map(build_id, tome_id):
    """Seal a map reconstructed from a tome that was authored before maps existed.

    The reconstruction is written to the seed and the proposal and then sealed
    through `seal_course_map`, so an adopted map clears the identical gate a
    planned one does. Reusing that path is the point: a second, gentler seal
    would be a hole every future build could be pushed through.
    """
    value = adopted_course_map(build_id, tome_id)
    _atomic_json(seed_path(build_id), value)
    _atomic_json(proposal_path(build_id), value)
    return seal_course_map(build_id)


def reconcile_adopted_map(build_id, tome_id, reason):
    """Re-seal an ADOPTED map against the tome after a legitimate structural edit.

    Only an adopted map is reconciled, and the distinction is the whole point. A planned
    map is a promise made before the work; re-sealing it to match whatever happened would
    make the promise unfalsifiable, so there the drift stays a gate failure and a person
    decides. An adopted map was only ever a photograph of the tome, so re-photographing
    it after an authorized edit costs nothing that was not already spent.

    The candidate is built by the same function that sealed the original, which is why
    this cannot smuggle anything through: `amend_course_map` then re-digests it, refuses
    to touch buildId, planSha256, or bounds, protects the Phase-1 mastery boundary, and
    journals the reason. Returns a description, or "" when there was nothing to do.
    """
    from ..course.amend import amend_course_map
    from . import CourseMapError, load_course_map
    try:
        old = load_course_map(build_id)
    except CourseMapError:
        return ""
    if not old.get("adoptedFromTome"):
        return ""
    try:
        # upgrade=False: the candidate is rebuilt from the tome at the adopted schema every
        # time, so a map modernized on one reconcile would be handed last-schema nodes on the
        # next. Worse, a newer map version binds the TOME too -- v4 requires a mechanisms
        # array on every exercise -- so migrating the map of a finished course would demand
        # hundreds of edits to content the amendment never touched.
        revised = amend_course_map(
            build_id, adopted_course_map(build_id, tome_id), reason, upgrade=False)
    except CourseMapError as exc:
        # The ordinary no-op: the edit touched nothing the map records. Any other
        # refusal is a real one and must not be swallowed into a silent success.
        if "does not change the sealed plan" in str(exc):
            return ""
        raise
    return (f"re-sealed the adopted course map at revision {revised['revision']} "
            f"so it matches the amended tome")


def adopt_build(build_id, tome_id):
    """Materialize whatever pre-contract artifacts this build is missing.

    Returns a list of plain-language lines describing what was created, or an
    empty list when the build already carries everything. Never overwrites: a
    real sealed map is a promise, and a handoff already written is an author's
    words, so both are left exactly as they are.

    Both contracts hang off the Phase-1 build plan: the map is sealed against the
    plan's digest and every gate that reads a handoff is handed the plan too. A tome
    finished before plans existed has none, and writing one here would certify a
    harness guess as an author's promise. So that case is a FACT about the build,
    reported in one line -- not an error, which is how "no such plan" used to reach
    the Binder as an unfixable "cannot read" against the tome it was asked to mend.
    """
    plan = os.path.join(BUILD_DIR, f"{build_id}.plan.md")
    if not os.path.isfile(plan):
        return [f"this build has no plan at {os.path.relpath(plan, REPO)}, so it has no "
                "sealed course map or continuity handoffs to adopt; the tome validator "
                "is the whole of its gate"]
    notes = []
    if not os.path.exists(map_path(build_id)):
        course = adopt_course_map(build_id, tome_id)
        notes.append(
            f"sealed an adopted course map for {len(course['sections'])} sections "
            f"reconstructed from the authored tome (adoptedFromTome={tome_id})")
    ids = [str(value) for value in
           ((_manifest(os.path.join(REPO, "tomes", tome_id)).get("content") or {})
            .get("sections") or [])]
    created = adopt_handoffs(tome_id, ids)
    if created:
        notes.append(
            f"created empty continuity handoffs for {', '.join(created)}; each one "
            "still needs its artifact_state written")
    return notes
