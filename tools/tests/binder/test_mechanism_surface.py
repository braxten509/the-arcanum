#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""A sealed spelling used before its owner lesson must fail without paying an AI.

Reproduces the single most-cited recorded Validator AI finding: "s02.l01 uses
print in its first runnable example, but the sealed owner python-print-call is
s02.l03". The author declared no mechanism there, so the id-level ordering gate
saw nothing; only reading the code catches it.
"""
import copy

from buildlib.course.surface import surface_problems
from buildlib.mechanism_contract import detect_problems, validate_map_contract


def mechanism(mid, owner, detect, kind="syntax-form"):
    return {"id": mid, "label": mid.replace("-", " "), "kind": kind,
            "owner": owner, "detect": detect}


COURSE = {
    "version": 4,
    "mechanismContract": {
        "version": 1,
        "coverageStart": "s01",
        "mechanisms": [
            mechanism("python-print-call", "s01.l03", ["print("]),
            mechanism("python-comment-line", "s01.l02", ["#"]),
            mechanism("iterable-collection", "s01.l01", [], kind="technical-term"),
        ],
    },
    "sections": [{
        "id": "s01",
        "nodes": [
            {"id": "s01.l01", "kind": "lesson", "introduces": ["iterable-collection"]},
            {"id": "s01.l02", "kind": "lesson", "introduces": ["python-comment-line"]},
            {"id": "s01.l03", "kind": "lesson", "introduces": ["python-print-call"]},
            {"id": "s01.working", "kind": "working", "mechanisms": []},
        ],
    }],
}


def section(l01_code="value = 1\n", body="", rubric_desc="", proof_content=""):
    return {
        "lessons": [
            {"id": "s01-l01", "body": body,
             "exercises": [{"id": "e1", "code": l01_code}]},
            {"id": "s01-l02", "exercises": [{"id": "e2", "code": "# a note\n"}]},
            {"id": "s01-l03", "exercises": [{"id": "e3", "code": 'print("hi")\n'}]},
        ],
        "freestyle": {"rubric": [{"desc": rubric_desc}]},
        "proof": {"content": proof_content},
    }


def main():
    assert not surface_problems(COURSE, section(), "s01"), "a clean section must pass"

    # The recorded failure: print used two lessons before python-print-call owns it.
    found = surface_problems(COURSE, section(l01_code='print("hi")\n'), "s01")
    assert len(found) == 1, found
    assert "s01.l01.exercises[0]" in found[0] and "'print('" in found[0], found[0]
    assert "s01.l03" in found[0], found[0]

    # print at its owner and after it is fine; so is the same word inside a
    # longer identifier, which a plain substring match would have flagged.
    assert not surface_problems(COURSE, section(l01_code="blueprint = 1\n"), "s01")
    assert not surface_problems(COURSE, section(l01_code="sprinkle()\n"), "s01")

    # A comment mark in l01 precedes python-comment-line in l02.
    assert surface_problems(COURSE, section(l01_code="# early\n"), "s01")

    # Prose is scanned only through its code spans, never its English.
    assert not surface_problems(
        COURSE, section(body="<p>Later you will print( things.</p>"), "s01")
    assert surface_problems(
        COURSE, section(body="<p>Later: <code>print(&quot;x&quot;)</code></p>"), "s01")

    # A Working rubric and the proof packet sit at the working node, which is
    # after every lesson, so already-owned spellings there are legitimate.
    assert not surface_problems(COURSE, section(rubric_desc="`print(x)`"), "s01")
    assert not surface_problems(COURSE, section(proof_content='print("ok")'), "s01")

    # A mechanism with no fixed spelling opts out by declaring an empty list;
    # it simply contributes no scan, and the paid audit still judges it.
    assert not detect_problems([], "m")
    assert not detect_problems(["print(", "#"], "m")
    assert detect_problems("print(", "m"), "a bare string is not a detect list"
    assert detect_problems([""], "m") and detect_problems(["   "], "m")
    assert not detect_problems(["import "], "m"), "a trailing space is significant"
    assert detect_problems(["a"], "m"), "a one-character word matches everything"
    assert not detect_problems(["#"], "m"), "a one-character symbol is specific"
    assert detect_problems(["#", "#"], "m")

    # Sections before coverageStart, and pre-v4 maps, are outside the contract.
    early = copy.deepcopy(COURSE)
    early["mechanismContract"]["coverageStart"] = "s02"
    early["sections"].append({"id": "s02", "nodes": []})
    assert not surface_problems(early, section(l01_code='print("hi")\n'), "s01")
    assert not surface_problems({**COURSE, "version": 3},
                                section(l01_code='print("hi")\n'), "s01")

    # A map sealed before `detect` existed must still load. A seal is a promise:
    # adding a required key cannot retroactively invalidate finished work.
    legacy = copy.deepcopy(COURSE)
    for record in legacy["mechanismContract"]["mechanisms"]:
        record.pop("detect")
    positions = {"s01.l01": (0, 0), "s01.l02": (0, 1),
                 "s01.l03": (0, 2), "s01.working": (0, 3)}
    assert not validate_map_contract(legacy, legacy["sections"], positions,
                                     detailed=False, map_version=4), "v4 has no detect"
    assert validate_map_contract(legacy, legacy["sections"], positions,
                                 detailed=False, map_version=6), "v6 requires detect"
    # It just scans nothing, so its sections keep relying on the paid audit.
    assert not surface_problems(legacy, section(l01_code='print("hi")\n'), "s01")

    print("ok: a spelling used before its sealed owner fails mechanically")


if __name__ == "__main__":
    main()
