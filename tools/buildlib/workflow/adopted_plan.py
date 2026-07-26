"""The Phase-1 build plan reconstructed for a tome finished before plans existed.

Every harness contract hangs off `.tome-build/<build>.plan.md`: the sealed course map is
digested against it, the build id is its basename, and the handoff gates resolve the build
through it. A tome older than that file therefore has no gate at all beyond the tome
validator, and the shipping gate the reviewer is graded against fails on "no such file".

Writing one after the fact is the one place adoption gets close to inventing an author's
promise, so it is kept narrow. Only two plan fields are machine-owned -- the acceptance
journey and the mastery dial -- and both are copied out of `tome.toml` rather than
composed. Everything a fresh build would be judged on (Phase-0 answers, the Arc, the
`**Section list:**` spine) is deliberately absent: a guess there would be
indistinguishable later from an audited promise.
"""
import os
import re

from arcanum.forge.build_state import build_result_status, record_build_result

from .. import BUILD_DIR, REPO
from ..course.limits import MAX_SECTIONS, MIN_SECTIONS
from ..course_map import adopt, validate_course_map
from ..course_map.adopt import AdoptionError

_SCENARIO = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

_PLAN_NOTE = """\
> RECONSTRUCTED, NOT PROMISED. This tome was authored before the harness sealed a
> Phase-1 build plan, so every line below was read back out of the finished tome
> instead of being promised before the work began. There are deliberately no Phase-0
> gate answers, no Arc, and no `**Section list:**` label: a guess at those would be
> indistinguishable later from an audited promise, and a plan a fresh course map can
> be seeded from is exactly what this is not. What it does carry is what the later
> gates read -- the acceptance journey and the mastery dial, copied verbatim from
> `tomes/{tome_id}/tome.toml` -- so this tome can be measured by the same shipping
> gate as every tome built after plans existed."""


def adopted_plan_text(tome_id):
    """Reconstruct the plan fields the later gates read, from the finished tome.

    Only two of them are machine-owned, and both are copied rather than composed: the
    acceptance journey, which `[acceptance] scenarios` must match exactly, and the
    mastery dial, which the manifest may not drift from once this is written. The rest
    is prose for whoever reads the file next.
    """
    tome_path = os.path.join(REPO, "tomes", tome_id)
    manifest = adopt._manifest(tome_path)
    ids = [str(value) for value in ((manifest.get("content") or {}).get("sections") or [])]
    if not MIN_SECTIONS <= len(ids) <= MAX_SECTIONS:
        raise AdoptionError(
            f"tome.toml lists {len(ids)} sections; a plan covers "
            f"{MIN_SECTIONS} through {MAX_SECTIONS}")
    dials = []
    level = (manifest.get("mastery") or {}).get("level")
    if isinstance(level, int) and 1 <= level <= 5:
        dials.append(f"- **Mastery (1-5):** {level}")
    acceptance = manifest.get("acceptance")
    if isinstance(acceptance, dict):
        scenarios = [str(item) for item in (acceptance.get("scenarios") or [])]
        if (len(scenarios) < 2 or len(set(scenarios)) != len(scenarios)
                or any(not _SCENARIO.fullmatch(item) for item in scenarios)):
            raise AdoptionError(
                "[acceptance] scenarios must already be at least two unique kebab-case ids "
                "before a plan can carry that journey; the tome's own contract has to be "
                "fixed first, and a plan cannot invent one")
        # Own paragraph, no list bullet: the gate reads this label only at a line start.
        dials.append("\n**Acceptance scenarios:** " + " -> ".join(scenarios))
    load_section = adopt._load_section()
    rows = []
    for sid in ids:
        section = load_section(tome_path, sid)
        lessons = [item for item in (section.get("lessons") or []) if isinstance(item, dict)]
        rows.append(f"- **{sid} — {adopt._text(section.get('title'), 120) or sid}:** "
                    f"{len(lessons)} lessons, then one Working")
    meta = manifest.get("meta") or {}
    concept = (adopt._text((manifest.get("narrative") or {}).get("objective"), 2400)
               or adopt._text(meta.get("description"), 2400))
    if not concept:
        raise AdoptionError("tome.toml declares no narrative objective or description, "
                            "so there is nothing a plan could state as the concept")
    blocks = [f"# BUILD PLAN — {adopt._text(meta.get('name'), 120) or tome_id} (ADOPTED)",
              f"- **Adopted from tome:** {tome_id}\n" + "\n".join(dials),
              _PLAN_NOTE.format(tome_id=tome_id),
              "## Concept", concept,
              "## Sections as authored", "\n".join(rows)]
    return "\n\n".join(blocks) + "\n"


def _mark_built(build_id, tome_id):
    """Write the completion sidecar a real build writes on its last phase.

    An adopted tome is already finished -- that is the premise of adopting it. But every
    listing that walks `.tome-build/*.plan.md` infers "abandoned build" from the absence of
    a `done` result, so a plan with no sidecar files a shipped tome under UNFINISHED
    WORKINGS and marks it a draft in the catalog. Called only once a plan exists, so a
    refused adoption never claims a build that did not happen.
    """
    if not build_result_status(build_id):
        record_build_result(build_id, tome_id, "done", phase=8,
                            phase_title="Adopted from the finished tome")


def adopt_plan(build_id, tome_id):
    """Write the build plan a tome authored before plans existed never had.

    Refuses to overwrite. An existing plan is the promise the sealed map is digested
    against, so rewriting it would invalidate the map, every handoff gate that resolves
    the build through it, and the acceptance journey all at once.

    A plan is also refused when the tome cannot be photographed by a sealed map, which
    is checked here by reconstructing one and validating it. That order matters: the
    plan is what switches this tome onto the full shipping gate, and switching it there
    with no map the gate can load would leave it measured WORSE than by the tome
    validator alone -- every finding a missing file rather than anything about teaching.
    """
    plan = os.path.join(BUILD_DIR, f"{build_id}.plan.md")
    if os.path.isfile(plan):
        _mark_built(build_id, tome_id)  # heals a plan adopted before the sidecar was written
        return []
    text = adopted_plan_text(tome_id)
    os.makedirs(BUILD_DIR, exist_ok=True)
    temp = plan + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(temp, plan)
    try:
        problems = validate_course_map(
            adopt.adopted_course_map(build_id, tome_id), detailed=True)
    except BaseException:
        os.remove(plan)
        raise
    if problems:
        os.remove(plan)
        owners = sum("multiple teaching owners" in item for item in problems)
        raise AdoptionError(
            f"a sealed course map cannot be reconstructed from this tome, so a plan would "
            f"only gate it against a map that can never exist ({len(problems)} blockers). "
            + (f"{owners} lessons re-teach a capability another lesson already introduces: a "
               "sealed map records exactly one owning lesson per capability, so it has no way "
               "to say which of them introduces it. Give those lessons their own concrete "
               "capability ids and the tome becomes adoptable. " if owners else "")
            + "First blockers:\n- " + "\n- ".join(problems[:8]))
    _mark_built(build_id, tome_id)
    return [f"wrote an adopted build plan at {os.path.relpath(plan, REPO)}, reconstructed "
            "from the tome's own manifest, so this tome is now measured by the full "
            "shipping gate instead of the tome validator alone"]
