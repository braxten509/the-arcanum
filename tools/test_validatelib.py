#!/usr/bin/env python3
"""Self-check for validatelib's language-agnostic teeth: does the expectRe gate,
the --run pre-solved detector, and the padded-prose language guard actually fire?

    python3 tools/test_validatelib.py

Needs python3 on PATH (it IS the toolchain for the synthetic tome below).
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validatelib import _findings  # noqa: E402
from validatelib.content import check_exercise, check_freestyle  # noqa: E402
from validatelib.depth import check_padded_prose  # noqa: E402
from validatelib.execute import _project_build_result, check_starters_run  # noqa: E402
from validatelib.themes import check_sigil_palette_uniqueness  # noqa: E402


def findings():
    out, _findings[:] = list(_findings), []
    return out


def main():
    # 1. expectRe must compile — an invalid pattern is an unwinnable lab (ERROR)…
    check_exercise({"id": "w1", "type": "write", "expectRe": "([", "hint": "h"}, "L", set())
    assert any(lv == "ERROR" and "expectRe" in msg for lv, _, msg in findings()), "bad expectRe not flagged"
    # …but a JS-style named group is legal to the engine and must NOT flag.
    check_exercise({"id": "w2", "type": "write", "expectRe": "(?<ok>ok)", "hint": "h"}, "L", set())
    assert not any("expectRe" in msg for _, _, msg in findings()), "JS named group false-errored"

    # 2. --run: a starter whose untouched output already satisfies expectRe is PRE-SOLVED,
    #    and a starter that cannot build is an ERROR — via the tome's own toolchain (python).
    m = {"runtime": {"name": "python"}}
    secs = [{"id": "s01", "lessons": [{"id": "l1", "exercises": [
        {"type": "write", "id": "solved", "starter": "print('ok')", "expectRe": "^ok$"},
        {"type": "write", "id": "broken", "starter": "def (:"},
    ]}]}]
    with tempfile.TemporaryDirectory() as d:
        check_starters_run(d, m, secs)
    got = findings()
    assert any("PRE-SOLVED" in msg and "solved" in msg for _, _, msg in got), got
    assert any("does not BUILD" in msg and "broken" in msg for _, _, msg in got), got

    # 2b. --run: a `solution` must run cleanly and print output the grader accepts;
    #     a wrong expect is caught the moment the author's own solution disagrees.
    secs = [{"id": "s01", "lessons": [{"id": "l1", "exercises": [
        {"type": "write", "id": "good", "solution": "print('KEY 42')", "expect": "KEY 42"},
        {"type": "write", "id": "wrong-expect", "solution": "print('KEY 41')", "expect": "KEY 42"},
        {"type": "write", "id": "unverified", "expect": "X"},
    ]}]}]
    with tempfile.TemporaryDirectory() as d:
        check_starters_run(d, m, secs)
    got = findings()
    assert any(lv == "ERROR" and "wrong-expect" in msg and "does not satisfy expect" in msg
               for lv, _, msg in got), got
    assert not any("'good'" in msg and lv == "ERROR" for lv, _, msg in got), got
    assert any("no `solution`" in msg for _, _, msg in got), got

    # 2c. Project compilers report warnings alongside errors. A warning must not turn a
    #     deliberately incomplete starter into a false "does not BUILD" failure.
    ok, _ = _project_build_result({"ok": True, "diags": [
        {"file": "Program.cs", "line": 3, "col": 8, "sev": "warning",
         "msg": "The variable 'archive' is assigned but its value is never used"},
    ]}, "Program.cs")
    assert ok, "project compiler warning falsely failed the build gate"
    ok, detail = _project_build_result({"ok": True, "diags": [
        {"file": "Program.cs", "line": 3, "col": 8, "sev": "error",
         "msg": "; expected"},
    ]}, "Program.cs")
    assert not ok and "; expected" in detail, "project compiler error escaped the build gate"

    # 2d. missing points / reward / mc bool answer — the NaN-purse class of breakage.
    check_exercise({"id": "p1", "type": "text", "answer": "x", "hint": "h"}, "L", set())
    assert any("points" in msg and lv == "ERROR" for lv, _, msg in findings()), "missing points not flagged"
    check_exercise({"id": "p2", "type": "mc", "points": 15, "choices": ["a", "b"], "answer": True,
                    "whyWrong": "w", "hint": "h"}, "L", set())
    assert any("integer index" in msg for _, _, msg in findings()), "bool mc answer not flagged"
    check_freestyle({"title": "t", "brief": "b", "xray": "x",
                     "rubric": [{"criterion": "c", "weight": 100}]}, "L")
    assert any("reward" in msg and lv == "ERROR" for lv, _, msg in findings()), "missing reward not flagged"

    # 2e. An exercise can parse while rendering as blank or impossible in the client.
    #     These are schema errors, not editorial advice.
    cases = [
        ({"id": "blank", "type": "text", "points": 15, "answer": "x", "hint": "h"}, "prompt"),
        ({"id": "mc-empty", "type": "mc", "points": 15, "prompt": "pick", "choices": ["", "b"],
          "answer": 1, "whyWrong": "w", "hint": "h"}, "non-empty string"),
        ({"id": "mc-dupe", "type": "mc", "points": 15, "prompt": "pick", "choices": ["Same", " same "],
          "answer": 0, "whyWrong": "w", "hint": "h"}, "distinct"),
        ({"id": "fill-blank", "type": "fill", "points": 20, "prompt": "complete", "code": "x = 1",
          "answer": "1", "hint": "h"}, "____"),
        ({"id": "type-reps", "type": "type", "points": 12, "prompt": "copy", "code": "x", "reps": 0},
         "positive integer"),
    ]
    for exercise, needle in cases:
        check_exercise(exercise, "L", set())
        got = findings()
        assert any(lv == "ERROR" and needle in msg for lv, _, msg in got), (exercise, got)

    # 3. padded-prose guard: identical paragraphs in a language with no English glue
    #    words must NOT cross-match (the all-'*' skeleton trap).
    para = "<p>" + " ".join(f"palabra{i} misma cosa distinta" for i in range(20)) + "</p>"
    secs = [{"id": "s01", "lessons": [{"id": "a", "body": para}, {"id": "b", "body": para}]}]
    check_padded_prose(secs)
    assert not findings(), "non-English identical paragraphs false-flagged"
    # …while the same trick in English (glue intact) still fires.
    para = ("<p>" + "The ward is set on the line and the rune will hold it there for now. " * 6 + "</p>")
    secs = [{"id": "s01", "lessons": [{"id": "a", "body": para}, {"id": "b", "body": para}]}]
    check_padded_prose(secs)
    assert any("sentence frames" in msg for _, _, msg in findings()), "English template clone missed"

    # 4. A complete four-ink sigil set may appear only once among authored tome
    #    themes. Reordering the same four colors still duplicates the set, while
    #    changing any one color clears it. Global skins are not scanned.
    sigil = {f"sigil-{i}": f"#00000{i}" for i in range(1, 5)}
    current = {"themes": [{"id": "ember", "vars": sigil}]}
    with tempfile.TemporaryDirectory() as d:
        root = Path(d) / "tomes"
        current_dir = root / "current"
        other_dir = root / "other"
        global_dir = Path(d) / "skins" / "global"
        current_dir.mkdir(parents=True)
        other_dir.mkdir(parents=True)
        global_dir.mkdir(parents=True)
        reordered = [sigil[f"sigil-{i}"] for i in (4, 3, 2, 1)]
        (other_dir / "themes.toml").write_text(
            "[[themes]]\nid = \"echo\"\n\n[themes.vars]\n" +
            "\n".join(f"sigil-{i} = \"{color}\"" for i, color in enumerate(reordered, 1)) + "\n"
        )
        (global_dir / "skin.toml").write_text(
            "id = \"global\"\n[vars]\n" +
            "\n".join(f"sigil-{i} = \"{sigil[f'sigil-{i}']}\"" for i in range(1, 5)) + "\n"
        )
        check_sigil_palette_uniqueness(current, current_dir, "L", root)
        got = findings()
        assert any(lv == "ERROR" and "other/echo" in msg and "sigil color set" in msg
                   for lv, _, msg in got), got
        assert not any("global/global" in msg for _, _, msg in got), got

        changed = dict(sigil)
        changed["sigil-4"] = "#000005"
        current = {"themes": [{"id": "ember", "vars": changed}]}
        check_sigil_palette_uniqueness(current, current_dir, "L", root)
        assert not findings(), "one changed sigil ink should make the set unique"

    print("ok: exercise schema, expectRe, --run proof, padded-prose and sigil-palette guards")


if __name__ == "__main__":
    main()
