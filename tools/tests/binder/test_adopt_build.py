#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""A build finished before the map and handoff contracts must still be reviewable.

Every gate a reviewer is graded by loads the sealed course map and the per-section
handoffs. Both are harness-owned, so a build predating them fails on "no such file"
-- a report naming work no reviewer is permitted to do. Adoption reconstructs them
from the tome so the review is graded on the teaching instead of the build's age.
"""
import contextlib
import json
import os

from buildlib.course_map import validate_course_map, validate_map_locations
from buildlib.course_map.adopt import AdoptionError, adopted_course_map, adopt_handoffs
from buildlib.single_author.full_review import validate_report


def fake_section(sid, lessons=4, requires=("cap-a",)):
    return {
        "id": sid, "title": f"Section {sid}", "brief": f"<p>Build the {sid} slice.</p>",
        "build": f"Deliver the {sid} milestone.",
        "lessons": [{"id": f"{sid}-l{index:02d}", "title": f"{sid} lesson {index}",
                     "teaches": [f"cap-{sid}-{index}"]}
                    for index in range(1, lessons + 1)],
        "freestyle": {"title": f"{sid} Working", "requires": list(requires),
                      "brief": "Submit <code>src/app.py</code> and <code>reports/out.txt</code>."},
    }


BUILD_ID = "adopt-selftest"


@contextlib.contextmanager
def in_memory_tome(sections, ids, extra=None, plan=True):
    """Stand a fake tome and its plan in front of adoption, touching no real build.

    ``plan=False`` is the pre-plan build: the file adoption would have to write itself.
    """
    import buildlib.course_map.adopt as module
    import tome_layout
    from buildlib import BUILD_DIR
    manifest = {
        "meta": {"id": BUILD_ID, "description": "A tome adopted after the fact."},
        "content": {"sections": ids},
        "narrative": {"objective": "Ship one proven artifact the learner built alone."},
        **(extra or {}),
    }
    path = os.path.join(BUILD_DIR, f"{BUILD_ID}.plan.md")
    os.makedirs(BUILD_DIR, exist_ok=True)
    saved_manifest, saved_load = module._manifest, tome_layout.load_section
    module._manifest = lambda tome_path: manifest
    tome_layout.load_section = lambda path, sid: sections[sid]
    if plan:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("# BUILD PLAN — adopt selftest\n")
    try:
        yield module
    finally:
        module._manifest, tome_layout.load_section = saved_manifest, saved_load
        with contextlib.suppress(OSError):
            os.remove(path)


def adopt(sections, ids):
    with in_memory_tome(sections, ids) as module:
        return module.adopted_course_map(BUILD_ID, BUILD_ID)


def wired(ids):
    """Sections whose Workings grade exactly what the tome taught up to that point."""
    sections = {sid: fake_section(sid) for sid in ids}
    taught = []
    for sid in ids:
        taught += [cap for lesson in sections[sid]["lessons"] for cap in lesson["teaches"]]
        sections[sid]["freestyle"]["requires"] = list(taught)
    return sections


def main():
    ids = ["s01", "s02"]
    sections = {sid: fake_section(sid) for sid in ids}
    taught = {sid: [cap for lesson in sections[sid]["lessons"] for cap in lesson["teaches"]]
              for sid in ids}
    sections["s01"]["freestyle"]["requires"] = taught["s01"]
    # The last Working grades everything taught, which is what a graduate holds.
    sections["s02"]["freestyle"]["requires"] = taught["s01"] + taught["s02"]

    course = adopt(sections, ids)
    # An adopted map clears the same gate a planned one does; there is no softer seal.
    problems = (validate_course_map(course, detailed=True)
                + validate_map_locations(BUILD_ID, course))
    assert not problems, problems
    assert course["adoptedFromTome"] == BUILD_ID
    assert [section["id"] for section in course["sections"]] == ids
    assert course["sections"][0]["nodes"][-1]["id"] == "s01.working"
    assert course["sections"][0]["capabilities"] == taught["s01"]
    assert course["graduateCapabilities"] == taught["s01"] + taught["s02"]
    # Artifacts come from the code spans the Working brief already quotes.
    assert course["sections"][0]["nodes"][-1]["learnerOwnedArtifacts"] == [
        "src/app.py", "reports/out.txt"]
    # Nothing is invented: no mechanism ledger, no obligations nobody agreed to.
    assert "mechanismContract" not in course
    assert course["plannedObligations"] == []

    # A tome too thin to describe fails loudly rather than sealing a fiction.
    thin = dict(sections, s01=fake_section("s01", lessons=1))
    try:
        adopt(thin, ids)
        raise AssertionError("a 1-lesson section must not adopt")
    except AdoptionError as exc:
        assert "1 lessons" in str(exc), exc

    _handoff_check()
    _planless_check()
    _plan_check()
    _report_check()
    _sweep_check()
    _reseal_check()
    print("ok: a pre-contract build adopts into the same sealed contract")


def _planless_check():
    """A build with no plan adopts nothing, says so, and is not an error.

    Every contract hangs off the Phase-1 plan -- the map is sealed against its digest --
    so adoption used to raise "cannot read the build plan". That reached the Binder as an
    unfixable access failure naming the very tome it had been asked to mend, and writing
    a plan here instead would certify a harness guess as an author's promise.
    """
    from buildlib import BUILD_DIR
    from buildlib.continuity import handoff_path
    from buildlib.course_map import map_path
    from buildlib.course_map.adopt import adopt_build
    build = "adopt-planless-selftest"
    assert not os.path.exists(os.path.join(BUILD_DIR, f"{build}.plan.md"))
    notes = adopt_build(build, build)
    assert len(notes) == 1 and "no plan" in notes[0], notes
    assert not os.path.exists(map_path(build)), "a planless build must seal no map"
    assert not os.path.exists(os.path.dirname(handoff_path(build, "s01"))), \
        "and must not leave handoffs no gate will ever read"


def _plan_check():
    """A planless tome can be given the plan that puts it under the full shipping gate.

    Only the two machine-owned fields may be reconstructed, and only by copying: the
    acceptance journey the later gate compares against `[acceptance] scenarios`, and the
    mastery dial the manifest may not drift from. `**Section list:**` stays absent so
    nothing can seed a fresh course map from a reconstruction, and the plan is written
    only when a sealed map can actually be built from the tome -- a plan without one
    would grade the tome worse than the tome validator alone.
    """
    from buildlib import BUILD_DIR
    from buildlib.course_map.plan import acceptance
    from buildlib.skeleton import SECTION_LIST_LABEL
    from buildlib.workflow.adopted_plan import adopt_plan, adopted_plan_text
    ids = ["s01", "s02"]
    path = os.path.join(BUILD_DIR, f"{BUILD_ID}.plan.md")
    sidecar = os.path.join(BUILD_DIR, f"{BUILD_ID}.result.json")
    extra = {"acceptance": {"scenarios": ["first-run", "second-run"]}}
    with in_memory_tome(wired(ids), ids, extra=extra, plan=False) as module:
        try:
            notes = adopt_plan(BUILD_ID, BUILD_ID)
            assert len(notes) == 1 and "adopted build plan" in notes[0], notes
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            assert acceptance(text) == ["first-run", "second-run"], text
            # A reconstruction must never be mistakable for a seedable promise: the label
            # the skeleton scaffolder keys off is absent, mentioned only inside the note.
            assert not SECTION_LIST_LABEL.search(text), text
            assert "RECONSTRUCTED, NOT PROMISED" in text
            # The plan the map is digested against is the one just written.
            assert not validate_course_map(
                module.adopted_course_map(BUILD_ID, BUILD_ID), detailed=True)
            # An existing plan is what the sealed map is digested against: never rewritten.
            assert adopt_plan(BUILD_ID, BUILD_ID) == []
            # An adopted tome is finished, and every listing that walks *.plan.md reads
            # "abandoned build" from a missing `done` result. Without this sidecar a
            # shipped tome sits in UNFINISHED WORKINGS and in the catalog's drafts.
            with open(sidecar, encoding="utf-8") as handle:
                assert json.load(handle)["status"] == "done"
        finally:
            for leftover in (path, sidecar):
                with contextlib.suppress(OSError):
                    os.remove(leftover)

    # A tome no honest map can be built from keeps its old gate instead of a broken one.
    shared = wired(ids)
    shared["s02"]["lessons"][1]["teaches"] = list(shared["s02"]["lessons"][0]["teaches"])
    with in_memory_tome(shared, ids, plan=False):
        try:
            adopt_plan(BUILD_ID, BUILD_ID)
            raise AssertionError("a tome that cannot be photographed must not get a plan")
        except AdoptionError as exc:
            assert "teaching owners" in str(exc) or "re-teach" in str(exc), exc
        assert not os.path.exists(path), "and the refused plan must not be left behind"
        assert not os.path.exists(sidecar), "nor a result claiming a build that never ran"
        # …and the command says so as a note. An error would abort the ordinary adoption
        # and reach the Binder as "the tome's contracts could not be prepared", which reads
        # like the amendment itself failed rather than a fact about an older tome.
        import io
        import sys as system
        import sync_contracts
        out = io.StringIO()
        saved = system.argv
        system.argv = ["sync_contracts.py", "plan", BUILD_ID]
        try:
            with contextlib.redirect_stdout(out):
                code = sync_contracts.main()
        finally:
            system.argv = saved
        assert code == 0, code
        # The Binder's harness matches that note to hand the CAUSE to the agent as work, so
        # the phrase is a contract between the two sides, not just operator prose.
        from arcanum.authoring.amendment.gate import PLAN_REFUSED
        assert PLAN_REFUSED in out.getvalue(), out.getvalue()
        assert out.getvalue().split(PLAN_REFUSED, 1)[1].split(": ", 1)[1].strip(), \
            "the note must carry the cause after the first colon"
        assert not os.path.exists(path)

    # A mastery tome with no shipped contract cannot be gated on one nobody may write.
    with in_memory_tome(wired(ids), ids, extra={"mastery": {"level": 4}}, plan=False):
        # The dial is copied from the manifest, never chosen: the mastery gate compares them.
        assert "- **Mastery (1-5):** 4" in adopted_plan_text(BUILD_ID)
        try:
            adopt_plan(BUILD_ID, BUILD_ID)
            raise AssertionError("a mastery tome with no evidence file must not adopt")
        except AdoptionError as exc:
            assert "mastery-evidence.json" in str(exc), exc
        assert not os.path.exists(path)


def _reseal_check():
    """An adopted map is re-photographed after an authorized edit; a planned one is not.

    The Binder may legitimately add a lesson, and the map records what the tome teaches,
    so the two drift apart and the shipping gate blocks on a difference nobody disputes.
    Re-sealing settles it for an ADOPTED map only -- that map was always just a picture
    of the tome. A planned map is a promise made before the work, and a promise that
    rewrites itself to match the outcome proves nothing, so it must be left to fail.
    """
    import buildlib.course_map as course_map
    from buildlib.course_map import amendment_path, load_course_map, map_path
    from buildlib.course_map import proposal_path, seed_path
    from buildlib.course_map.adopt import adopt_course_map, reconcile_adopted_map
    ids = ["s01", "s02"]
    sections = wired(ids)
    with in_memory_tome(sections, ids):
        try:
            sealed = adopt_course_map(BUILD_ID, BUILD_ID)
            # An edit that changes nothing the map records is a no-op, and a no-op is not a
            # failure. This also catches the schema drifting apart: the candidate is rebuilt
            # from the tome every time, so it must still compare equal to the sealed map.
            assert reconcile_adopted_map(BUILD_ID, BUILD_ID, "nothing was edited") == ""

            sections["s02"]["lessons"].append(
                {"id": "s02-l05", "title": "s02 lesson 5", "teaches": ["cap-s02-5"]})
            sections["s02"]["freestyle"]["requires"].append("cap-s02-5")
            note = reconcile_adopted_map(
                BUILD_ID, BUILD_ID, "Binder selftest: the amendment added a lesson")
            assert "re-sealed" in note, note
            revised = load_course_map(BUILD_ID)
            assert revised["revision"] == sealed["revision"] + 1, revised["revision"]
            assert "cap-s02-5" in revised["graduateCapabilities"], revised
            # The seal's own identity is never what moves, and neither is its schema: a
            # newer map version binds the tome too, so modernizing the map of a finished
            # course would demand edits to content the amendment never touched.
            assert revised["buildId"] == sealed["buildId"]
            assert revised["planSha256"] == sealed["planSha256"]
            assert revised["version"] == sealed["version"], revised["version"]
            assert "mechanismContract" not in revised, "an adopted map claims no mechanisms"
            with open(amendment_path(BUILD_ID), encoding="utf-8") as handle:
                assert "added a lesson" in handle.read(), "the reason must be journalled"

            planned = {key: value for key, value in revised.items()
                       if key != "adoptedFromTome"}
            original = course_map.load_course_map
            course_map.load_course_map = lambda _bid: planned
            try:
                assert reconcile_adopted_map(
                    BUILD_ID, BUILD_ID, "a planned map is a promise, not a photograph") == ""
            finally:
                course_map.load_course_map = original
        finally:
            for path in (map_path, seed_path, proposal_path, amendment_path):
                try:
                    os.remove(path(BUILD_ID))
                except OSError:
                    pass


def _sweep_check():
    """A defect in one section must reach the reviewer, not be pooled away tome-wide."""
    from buildlib import measure
    seen = []

    def fake(tid, sid, tooling, plan_rel):
        seen.append(sid)
        return (False, "ERROR anti-template: mc answers never land on index [3]") \
            if sid == "s02" else (True, "-- clean")

    original = measure.validate_section
    measure.validate_section = fake
    try:
        ok, report = measure.validate_every_section("homunculus", "both", "plan.md")
        assert seen == [f"s{n:02d}" for n in range(1, 11)], seen
        assert not ok
        # Named by section, so the reviewer knows which bank to respread.
        assert report.startswith("section s02:"), report
        assert "index [3]" in report
        # A tome whose manifest cannot be read fails loudly instead of sweeping nothing.
        ok, report = measure.validate_every_section("no-such-tome", "both", "plan.md")
        assert not ok and "cannot read" in report, report
    finally:
        measure.validate_section = original


def _handoff_check():
    """A created handoff must be blank, so its own gate demands the reviewer write it."""
    from buildlib.continuity import handoff_path
    from buildlib.continuity.schema import HANDOFF_KEYS
    tid = BUILD_ID
    created = adopt_handoffs(tid, ["s01", "s02"])
    try:
        assert created == ["s01", "s02"], created
        with open(handoff_path(tid, "s01"), encoding="utf-8") as handle:
            value = json.load(handle)
        assert set(value) == HANDOFF_KEYS, value
        assert value["artifact_state"] == "", "the harness must not invent author prose"
        # Already-written handoffs are an author's words and are never overwritten.
        value["artifact_state"] = "The project builds and its report is preserved."
        with open(handoff_path(tid, "s01"), "w", encoding="utf-8") as handle:
            json.dump(value, handle)
        assert adopt_handoffs(tid, ["s01", "s02"]) == []
        with open(handoff_path(tid, "s01"), encoding="utf-8") as handle:
            assert json.load(handle)["artifact_state"].startswith("The project builds")
    finally:
        import shutil
        from buildlib.continuity import handoff_dir
        shutil.rmtree(handoff_dir(tid), ignore_errors=True)


def _report_check():
    """Deleting stray debris is asked for, so it must not fail the reviewer's own attestation."""
    from buildlib.single_author import full_review
    from buildlib import BUILD_DIR
    build_id, tid = "adopt-report-selftest", "adopt-report-selftest"
    present = ["tomes/x/tome.toml", "tomes/x/sections/s01/section.toml"]
    original = full_review.inventory
    full_review.inventory = lambda value: list(present)
    path = full_review.evidence_path(build_id)
    os.makedirs(BUILD_DIR, exist_ok=True)

    def write(reviewed, findings=()):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "reviewMode": "thorough-full-tome", "sampling": False,
                       "filesReviewed": list(reviewed), "findings": list(findings),
                       "unresolvedFindings": [], "summary": "reviewed everything"}, handle)

    try:
        write(present)
        assert validate_report(build_id, tid)[0]

        # A path attested but now gone is the deletion the prompt asked for.
        gone = present + ["tomes/x/sections/s11/stray.toml"]
        write(gone, [{"file": "tomes/x/sections/s11/stray.toml",
                      "issue": "section folder absent from the manifest",
                      "resolution": "deleted the stray folder"}])
        ok, report = validate_report(build_id, tid)
        assert ok, report

        # A path that still exists but was never in the inventory is a fabrication.
        write(present + ["AGENTS.md"])
        ok, report = validate_report(build_id, tid)
        assert not ok and "unexpected" in report, report

        # Skipping a real inventory file is still sampling.
        write(present[:1])
        ok, report = validate_report(build_id, tid)
        assert not ok and "missing" in report, report
    finally:
        full_review.inventory = original
        try:
            os.remove(path)
        except OSError:
            pass


if __name__ == "__main__":
    main()
