"""Starter, snippet, exercise, and economy runtime regression cases."""

import os
import sys
import tempfile
from unittest.mock import patch

from validatelib.content import check_content, check_exercise, check_freestyle
from validatelib.content.depth import check_economy_totals
from validatelib.execute import (STARTER_RUN_TIMEOUT, _project_build_result, _run_one_file,
                                 check_snippets, check_starters_run)

from .support import findings


def run_runtime_cases():
    # 1. expectRe must compile — an invalid pattern is an unwinnable lab (ERROR)…
    check_exercise({"id": "w1", "type": "write", "expectRe": "([", "hint": "h"}, "L", set())
    assert any(lv == "ERROR" and "expectRe" in msg for lv, _, msg in findings()), "bad expectRe not flagged"
    # …but a JS-style named group is legal to the engine and must NOT flag.
    check_exercise({"id": "w2", "type": "write", "expectRe": "(?<ok>ok)", "hint": "h"}, "L", set())
    assert not any("expectRe" in msg for _, _, msg in findings()), "JS named group false-errored"

    # 2. --run: a starter whose untouched output already satisfies expectRe is PRE-SOLVED,
    # and a starter that cannot build is an ERROR — via the tome's own toolchain (python).
    manifest = {"runtime": {"name": "python"}}
    sections = [{"id": "s01", "lessons": [{"id": "l1", "exercises": [
        {"type": "write", "id": "solved", "starter": "print('ok')", "expectRe": "^ok$"},
        {"type": "write", "id": "broken", "starter": "def (:"},
    ]}]}]
    with tempfile.TemporaryDirectory() as directory:
        check_starters_run(directory, manifest, sections)
    got = findings()
    assert any("PRE-SOLVED" in msg and "solved" in msg for _, _, msg in got), got
    assert any("does not BUILD" in msg and "broken" in msg for _, _, msg in got), got

    # A graphical starter that keeps its event loop alive gets only the short
    # starter probe; reference solutions retain the runtime's full timeout.
    looping = [{"id": "s01", "lessons": [{"id": "l1", "exercises": [
        {"type": "write", "id": "loop", "starter": "while True: pass", "expect": "X"},
    ]}]}]
    with patch("validatelib.execute._run_one_file", return_value=(True, "")) as run_file, \
         tempfile.TemporaryDirectory() as directory:
        check_starters_run(directory, manifest, looping)
    assert any(call.args[2] == STARTER_RUN_TIMEOUT for call in run_file.call_args_list), \
        run_file.call_args_list
    findings()

    # 2b. --run: a `solution` must run cleanly and print output the grader accepts;
    # a wrong expect is caught the moment the author's own solution disagrees.
    sections = [{"id": "s01", "lessons": [{"id": "l1", "exercises": [
        {"type": "write", "id": "good", "solution": "print('KEY 42')", "expect": "KEY 42"},
        {"type": "write", "id": "wrong-expect", "solution": "print('KEY 41')", "expect": "KEY 42"},
        {"type": "write", "id": "unverified", "expect": "X"},
    ]}]}]
    with tempfile.TemporaryDirectory() as directory:
        check_starters_run(directory, manifest, sections)
    got = findings()
    assert any(lv == "ERROR" and "wrong-expect" in msg and "does not satisfy expect" in msg
               for lv, _, msg in got), got
    assert not any("'good'" in msg and lv == "ERROR" for lv, _, msg in got), got
    assert any("no `solution`" in msg for _, _, msg in got), got

    # Direct validator invocations from a graphical shell must still run authored
    # starters and solutions without access to the user's desktop.
    leaky_env = os.environ.copy()
    leaky_env.update({"DISPLAY": ":88", "WAYLAND_DISPLAY": "wayland-88",
                      "SDL_VIDEODRIVER": "x11", "SDL_AUDIODRIVER": "pulseaudio"})
    env_probe = ("import os; print('|'.join((os.getenv('DISPLAY', '<unset>'), "
                 "os.getenv('WAYLAND_DISPLAY', '<unset>'), os.getenv('SDL_VIDEODRIVER', ''), "
                 "os.getenv('SDL_AUDIODRIVER', ''), os.getenv('PYGAME_HIDE_SUPPORT_PROMPT', ''))))")
    ok, out = _run_one_file([sys.executable], "main.py", 5, env_probe, env=leaky_env)
    assert ok and out.strip() == "<unset>|<unset>|dummy|dummy|1", out

    # 2c. Project compilers report warnings alongside errors. A warning must not turn a
    # deliberately incomplete starter into a false "does not BUILD" failure.
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

    # Proof-v1 code kinds are promises, not decoration. Project-only runtimes must compile
    # each runnable block in their trusted scratch scaffold while ignoring fragments and
    # terminal transcripts that the cumulative artifact proof owns.
    class FakeProjectRuntime:
        build_cmd = ["fake-build"]
        check_cmd = []

        def __init__(self):
            self.sources = []

        def available(self):
            return True

        def snippet_diagnostics(self, _scratch, source):
            self.sources.append(source)
            if "BROKEN_RUNNABLE" in source:
                return {"ok": True, "diags": [{
                    "file": "Program.cs", "line": 1, "col": 1, "sev": "error",
                    "msg": "synthetic C# compiler rejection",
                }]}
            return {"ok": True, "diags": []}

    fake_runtime = FakeProjectRuntime()
    classified = [{"id": "s01", "lessons": [{
        "id": "s01-l01",
        "body": ('<pre><code data-kind="terminal">BROKEN_RUNNABLE</code></pre>'
                 '<pre><code data-kind="replacement">BROKEN_RUNNABLE</code></pre>'
                 '<pre><code data-kind="runnable">// Complete runnable example\n'
                 'Console.WriteLine("checked");</code></pre>'),
    }]}]
    with patch("runtimes.for_config", return_value=fake_runtime) as runtime_factory:
        check_snippets({"runtime": {"name": "dotnet", "scaffoldCommand": []}}, classified)
    assert not findings(), "non-runnable proof-v1 blocks leaked into snippet compilation"
    assert len(fake_runtime.sources) == 1 and "checked" in fake_runtime.sources[0]
    scratch_config = runtime_factory.call_args.args[0]
    assert scratch_config == {"name": "dotnet"}, scratch_config

    classified[0]["lessons"][0]["body"] = (
        '<pre><code data-kind="runnable">// Complete runnable example\n'
        'BROKEN_RUNNABLE</code></pre>')
    with patch("runtimes.for_config", return_value=fake_runtime):
        check_snippets({"runtime": {"name": "dotnet", "scaffoldCommand": []}}, classified)
    got = findings()
    assert any(lv == "ERROR" and "synthetic C# compiler rejection" in msg
               for lv, _, msg in got), got

    # 2d. missing points / reward / mc bool answer — the NaN-purse class of breakage.
    check_exercise({"id": "p1", "type": "text", "answer": "x", "hint": "h"}, "L", set())
    assert any("points" in msg and lv == "ERROR" for lv, _, msg in findings()), "missing points not flagged"
    check_exercise({"id": "p2", "type": "mc", "points": 15, "choices": ["a", "b"], "answer": True,
                    "whyWrong": "w", "hint": "h"}, "L", set())
    assert any("integer index" in msg for _, _, msg in findings()), "bool mc answer not flagged"
    check_freestyle({"title": "t", "brief": "b", "xray": "x",
                     "rubric": [{"criterion": "c", "weight": 100}]}, "L")
    assert any("reward" in msg and lv == "ERROR" for lv, _, msg in findings()), "missing reward not flagged"

    # Legacy Workings may distinguish a quality grade from hard completion gates.
    valid_working = {
        "title": "t", "brief": "b", "xray": "x", "reward": 100,
        "rubric": [{
            "criterion": "Correctness", "weight": 100, "essential": True,
            "minimumScore": 7,
        }],
        "verification": [{
            "id": "tests", "command": "tests", "required": True,
            "expect": {"exitCode": 0, "regex": "passed"},
        }],
    }
    check_freestyle(valid_working, "L")
    assert not findings(), "valid essential rubric and CLI verification were rejected"
    invalid_working = {
        **valid_working,
        "rubric": [{
            "criterion": "Correctness", "weight": 100,
            "minimumScore": 11,
        }],
        "verification": [{
            "id": "tests", "command": "tests",
            "expect": {"fileRegex": "(", "typo": True},
        }],
    }
    check_freestyle(invalid_working, "L")
    got = findings()
    assert any("minimumScore requires essential" in msg for _, _, msg in got), got
    assert any("minimumScore must be between" in msg for _, _, msg in got), got
    assert any("unknown keys" in msg and "typo" in msg for _, _, msg in got), got
    assert any("fileRegex is invalid" in msg for _, _, msg in got), got
    assert any("fileRegex requires expect.path" in msg for _, _, msg in got), got
    check_content(
        {"runtime": {"name": "custom", "assessmentCommands": {
            "tests": ["python3", "-m", "pytest"],
        }}},
        [{"id": "s01", "lessons": [], "freestyle": valid_working}],
        "fixture", include_manifest=False)
    got = findings()
    assert not any("verification command" in msg for _, _, msg in got), got
    check_content(
        {"runtime": {"name": "custom"}},
        [{"id": "s01", "lessons": [], "freestyle": valid_working}],
        "fixture", include_manifest=False)
    got = findings()
    assert any("verification command 'tests' is not registered" in msg
               for _, _, msg in got), got

    # 2e. Economy balance uses finite course rewards as its base. Hex-defense money is
    # real but repeatable, so adding one bounty per tier invents a guaranteed total.
    economy_sections = [{"id": "s01", "lessons": [{"id": "l1", "exercises": [
        {"id": "e1", "points": 600},
    ]}], "freestyle": {"reward": 400}}]
    with tempfile.TemporaryDirectory() as directory:
        balanced = {"economy": {"ranks": [[0, "NOVICE"], [1120, "MASTER"]]},
                    "progression": {"intrusionTiers": [{"min": 0, "time": 90,
                                                         "bounty": 900, "pool": [{}]}]}}
        check_economy_totals(directory, balanced, economy_sections)
        assert not findings(), "repeatable hex bounty was folded into the finite economy base"

        too_high = {**balanced, "economy": {"ranks": [[0, "NOVICE"], [1160, "MASTER"]]}}
        check_economy_totals(directory, too_high, economy_sections)
        got = findings()
        assert any(lv == "WARN" and "fixed face-value earnings 1000" in msg
                   and "repeatable hex-defense bounties pay 900–900 per win" in msg
                   for lv, _, msg in got), got

        no_hex = {"economy": {"ranks": [[0, "NOVICE"], [1160, "MASTER"]]}}
        check_economy_totals(directory, no_hex, economy_sections)
        got = findings()
        assert any(lv == "WARN" and "no hex-defense bonus income" in msg
                   for lv, _, msg in got), got

        too_low = {"economy": {"ranks": [[0, "NOVICE"], [840, "MASTER"]]}}
        check_economy_totals(directory, too_low, economy_sections)
        got = findings()
        assert any(lv == "WARN" and "far below fixed face-value earnings 1000 by more than 15%"
                   in msg for lv, _, msg in got), got

    # 2f. An exercise can parse while rendering as blank or impossible in the client.
    # These are schema errors, not editorial advice.
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
