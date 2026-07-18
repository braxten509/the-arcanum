#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""Self-check for validatelib's language-agnostic teeth: does the expectRe gate,
the --run pre-solved detector, and the padded-prose language guard actually fire?

    python3 tools/tests/validation/test_validatelib.py

Needs python3 on PATH (it IS the toolchain for the synthetic tome below).
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validatelib import (REPO, clear_findings, legacy_current_findings,
                         set_build_phase, warn)  # noqa: E402
from validatelib.content import (check_content, check_exercise, check_freestyle, check_section,
                                 is_shouting_title)  # noqa: E402
from validatelib.content.coverage import (check_capability_ledger,
                                  check_canonical_type_regressions)  # noqa: E402
from validatelib.content.depth import (check_economy_totals, check_padded_prose,
                               check_taught_before_used, check_verbatim_prose)  # noqa: E402
from validatelib.execute import (STARTER_RUN_TIMEOUT, _project_build_result, _run_one_file,
                                 check_snippets, check_starters_run)  # noqa: E402
from validatelib.phase2 import check_tooling_contract  # noqa: E402
from validatelib.content.structure import check_meta, check_placeholders, check_runtime  # noqa: E402
from validatelib.themes import (check_sigil_palette_uniqueness,
                                check_theme_distinctness)  # noqa: E402


def findings():
    out = list(legacy_current_findings())
    clear_findings()
    return out


def main():
    # Harness phases promote only obligations already owned by that phase.  Future
    # work stays a warning; host-only advisories never become errors.
    set_build_phase(3)
    warn("content", "section debt", phase=3)
    warn("content", "future attack debt", phase=4)
    warn("advisory", "host limitation", phase=2)
    got = findings()
    assert [level for level, _, _ in got] == ["ERROR", "WARN", "WARN"], got
    set_build_phase(None)

    set_build_phase(3)
    check_content({}, [{"id": "s01", "lessons": [{
        "id": "s01-l01", "body": "word " * 220, "readings": [],
    }]}], "tome.toml", include_manifest=False)
    got = findings()
    assert any(level == "ERROR" and "median lesson body" in message
               for level, _, message in got), got
    assert any("canonical math strips HTML tags" in message
               and "raise at least 1" in message and "s01/s01-l01=220" in message
               for _, _, message in got), got
    assert any(level == "ERROR" and "zero [[lessons.readings]]" in message
               for level, _, message in got), got
    set_build_phase(None)

    callback_sections = [
        {"id": "s01", "lessons": [{"id": "l01", "body": "Use player_speed.",
                                      "exercises": []}]},
        {"id": "s02", "lessons": [{"id": "l01", "body": "Track max_health.",
                                      "exercises": []}]},
        {"id": "s03", "lessons": [{"id": "l01", "body": "Add enemy_hp.",
                                      "exercises": [{"type": "text", "answer": "enemy_hp"}]}]},
    ]
    check_taught_before_used(callback_sections)
    got = findings()
    assert any("player_speed (s01)" in message and "capability slug" in message
               for _, _, message in got), got

    # TODO is valid in student starter code, but not in authored prose beside it.
    with tempfile.TemporaryDirectory() as d:
        placeholder_path = Path(d) / "section.toml"
        placeholder_path.write_text(
            'body = "Finished teaching prose"\nstarter = "# TODO: student writes this"\n',
            encoding="utf-8")
        check_placeholders([str(placeholder_path)])
        assert not findings(), "intentional student TODO was mistaken for author scaffolding"
        placeholder_path.write_text(
            'body = "TODO: author still owes this"\nstarter = "# TODO: student writes this"\n',
            encoding="utf-8")
        check_placeholders([str(placeholder_path)])
        assert any("placeholder" in msg for _, _, msg in findings())

    # Repeated cumulative source is expected in an evolving project and is not copied
    # prose. Actual repeated teaching prose must still trip the 14-word shingle gate.
    repeated_code = " ".join(f"token{i}" for i in range(20))
    prose_a = "This first explanation is deliberately unique and teaches the opening concept clearly."
    prose_b = "This second explanation takes a different route and teaches the later concept clearly."
    sections = [{"id": "s01", "lessons": [
        {"id": "s01-l01", "body": f"<p>{prose_a}</p><pre><code>{repeated_code}</code></pre>"},
        {"id": "s01-l02", "body": f"<p>{prose_b}</p><pre><code>{repeated_code}</code></pre>"},
    ]}]
    check_verbatim_prose(sections)
    assert not findings(), "repeated cumulative code was misclassified as copied prose"
    copied = "Every careful learner should receive a distinct explanation before applying the new idea in their project today"
    sections[0]["lessons"][0]["body"] = f"<p>{copied}.</p>"
    sections[0]["lessons"][1]["body"] = f"<p>{copied} again.</p>"
    check_verbatim_prose(sections)
    got = findings()
    assert any(label == "anti-template" and "repeat verbatim" in msg
               for _, label, msg in got), got

    # Catalog descriptions sell the artifact positively; scope cuts stay in the plan.
    meta = {"id": "test", "name": "Test", "description":
            "Build a working game. The course stops short of multiplayer.",
            "author": "The Arcanum", "version": "0.1.0", "favicon": "*"}
    check_meta({"meta": meta}, "tome.toml")
    got = findings()
    assert any(lv == "WARN" and "public shelf copy" in msg for lv, _, msg in got), got
    meta["description"] = "Build a working game. The course stops at local play: no networking."
    check_meta({"meta": meta}, "tome.toml")
    got = findings()
    assert any(lv == "WARN" and "public shelf copy" in msg for lv, _, msg in got), got
    meta["description"] = "Build a working single-player game with maps and combat."
    check_meta({"meta": meta}, "tome.toml")
    assert not findings(), "positive catalog description was falsely flagged"

    # Display titles share one casing contract: prose titles use Title Case while
    # short acronyms remain legal. This guards both section and lesson callers.
    assert is_shouting_title("TEMPERING III // STOP THE CLOCK")
    assert not is_shouting_title("Tempering III // Stop the Clock")
    assert not is_shouting_title("JSON")
    section = {"id": "s01", "codename": "CHAPTER I // TEST", "title": "Test Chapter",
               "build": "Build", "brief": "Brief", "freestyle": None,
               "lessons": [{"id": "s01-l01", "title": "TEMPERING I // ONE FOREMAN",
                            "body": "<p>Body</p>", "exercises": []}]}
    check_section(section, "s01", "s01", set(), set())
    got = findings()
    assert any(lv == "WARN" and label == "content" and "lesson 's01-l01'" in msg
               and "ALL CAPS" in msg for lv, label, msg in got), got

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

    # A graphical starter that keeps its event loop alive gets only the short
    # starter probe; reference solutions retain the runtime's full timeout.
    looping = [{"id": "s01", "lessons": [{"id": "l1", "exercises": [
        {"type": "write", "id": "loop", "starter": "while True: pass", "expect": "X"},
    ]}]}]
    with patch("validatelib.execute._run_one_file", return_value=(True, "")) as run_file, \
         tempfile.TemporaryDirectory() as d:
        check_starters_run(d, m, looping)
    assert any(call.args[2] == STARTER_RUN_TIMEOUT for call in run_file.call_args_list), \
        run_file.call_args_list
    findings()

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

    # 2e. Economy balance uses finite course rewards as its base. Hex-defense money is
    #     real but repeatable, so adding one bounty per tier invents a guaranteed total.
    economy_sections = [{"id": "s01", "lessons": [{"id": "l1", "exercises": [
        {"id": "e1", "points": 600},
    ]}], "freestyle": {"reward": 400}}]
    with tempfile.TemporaryDirectory() as d:
        balanced = {"economy": {"ranks": [[0, "NOVICE"], [1120, "MASTER"]]},
                    "progression": {"intrusionTiers": [{"min": 0, "time": 90,
                                                         "bounty": 900, "pool": [{}]}]}}
        check_economy_totals(d, balanced, economy_sections)
        assert not findings(), "repeatable hex bounty was folded into the finite economy base"

        too_high = {**balanced, "economy": {"ranks": [[0, "NOVICE"], [1160, "MASTER"]]}}
        check_economy_totals(d, too_high, economy_sections)
        got = findings()
        assert any(lv == "WARN" and "fixed face-value earnings 1000" in msg
                   and "repeatable hex-defense bounties pay 900–900 per win" in msg
                   for lv, _, msg in got), got

        no_hex = {"economy": {"ranks": [[0, "NOVICE"], [1160, "MASTER"]]}}
        check_economy_totals(d, no_hex, economy_sections)
        got = findings()
        assert any(lv == "WARN" and "no hex-defense bonus income" in msg
                   for lv, _, msg in got), got

        too_low = {"economy": {"ranks": [[0, "NOVICE"], [840, "MASTER"]]}}
        check_economy_totals(d, too_low, economy_sections)
        got = findings()
        assert any(lv == "WARN" and "far below fixed face-value earnings 1000 by more than 15%"
                   in msg for lv, _, msg in got), got

    # 2f. An exercise can parse while rendering as blank or impossible in the client.
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

    # A tome's default is its visible identity. A palette barely beyond the
    # optional-variant floor must not ship as a renamed Vellum first impression.
    almost_vellum = {"defaults": {"theme": "signature"}, "themes": [
        {"id": "signature", "vars": {}},
    ]}
    with patch("validatelib.themes._palette_dist", return_value=9.0):
        check_theme_distinctness(almost_vellum, "L")
    got = findings()
    assert any("default mean channel distance 9.0 < 10" in msg for _, _, msg in got), got

    # 5. New scaffolds carry a cumulative capability ledger: a capstone can require
    #    only ids taught in this or earlier lessons, never a future lesson.
    ledger = {"content": {"capabilityLedger": True}, "runtime": {"name": "python"}}
    sections = [
        {"id": "s01", "lessons": [{"id": "s01-l01", "teaches": ["project-open"]}],
         "freestyle": {"requires": ["project-open"]}},
        {"id": "s02", "lessons": [{"id": "s02-l01", "teaches": ["save-data"]}],
         "freestyle": {"requires": ["project-open", "future-api"]}},
    ]
    check_capability_ledger(ledger, sections)
    got = findings()
    assert any(lv == "ERROR" and label == "coverage" and "future-api" in msg
               for lv, label, msg in got), got

    external_caps = ["tool-install", "tool-create-open", "tool-navigate",
                     "tool-edit-save", "tool-run-test", "tool-diagnose"]
    external = {"content": {"capabilityLedger": True},
                "runtime": {"name": "dotnet", "language": "C#", "externalWorkspace": True}}
    sections = [
        {"id": "s01", "lessons": [{"id": "s01-l01", "teaches": external_caps}],
         "freestyle": {"requires": external_caps}},
        {"id": "s02", "lessons": [{"id": "s02-l01", "teaches": ["tool-deliver"]}],
         "freestyle": {"requires": ["tool-deliver"]}},
    ]
    check_capability_ledger(external, sections)
    assert not findings(), "complete external-tool capability loop false-flagged"

    # An honest Phase-2 skeleton still contains TODO lesson bodies. Its incomplete
    # ledger should guide the author with warnings, not deadlock the non-strict phase.
    wip_sections = [
        {"id": "s01", "lessons": [{"id": "s01-l01", "body": "<p>TODO: author me</p>",
                                     "teaches": ["replace-me"]}],
         "freestyle": {"requires": ["replace-me"]}},
    ]
    check_capability_ledger(external, wip_sections)
    got = findings()
    assert got and all(lv == "WARN" for lv, _, _ in got), got

    # The Phase-0 tooling choice is a Phase-2 blocker too; it must not disappear merely
    # because finished-content checks are intentionally skipped in skeleton mode.
    check_tooling_contract(external, wip_sections, "tome.toml", tooling="internal")
    got = findings()
    assert any(lv == "ERROR" and "tooling gate = internal" in msg
               for lv, _, msg in got), got

    # 6. A later complete-looking C# class may add members, but must not silently
    #    drop the earlier public/private contract. Member-only patches are safe.
    csharp = {"runtime": {"name": "dotnet", "language": "C#", "editorLang": "csharp"}}
    sections = [{"id": "s01", "lessons": [
        {"id": "s01-l01", "body": '''<pre><code>public class Health
{
    private int maxHP;
    public int CurrentHP { get; private set; }
    public void TakeDamage(int amount) { CurrentHP -= amount; }
    public void Heal(int amount) { CurrentHP += amount; }
}</code></pre>'''},
        {"id": "s01-l02", "body": '''<pre><code>public class Health
{
    public int CurrentHP { get; private set; }
    public void TakeDamage(int amount) { CurrentHP -= amount; }
}</code></pre>'''},
    ]}]
    check_canonical_type_regressions(csharp, sections)
    got = findings()
    assert any(lv == "WARN" and label == "coverage" and "Heal" in msg and "maxHP" in msg
               for lv, label, msg in got), got

    sections[0]["lessons"][1]["body"] = '''<pre><code>public void Restore(int hp)
{
    CurrentHP = hp;
}</code></pre>'''
    check_canonical_type_regressions(csharp, sections)
    assert not findings(), "explicit member-only patch false-flagged as a whole-class regression"

    # A Phase-2-authored runtime file must report its TOML parse failure directly;
    # otherwise the later "no command" symptom sends the worker to the wrong repair.
    runtime_path = Path(REPO) / "global-configs" / "runtimes" / "selftest-invalid.toml"
    try:
        runtime_path.write_text("command = [\"python3\"\n", encoding="utf-8")
        check_runtime({"runtime": {"name": "selftest-invalid"}}, "test", "tome.toml")
        got = findings()
        assert any(lv == "ERROR" and str(runtime_path.name) in label
                   and "does not parse as TOML" in msg for lv, label, msg in got), got
    finally:
        runtime_path.unlink(missing_ok=True)

    # Runtime-writing phases also need a schema gate: TOML can parse while argv values
    # still crash the generic engine, a bad diagnostic regex still crashes compilation,
    # or an entry path escapes the learner project.
    runtime_path = Path(REPO) / "global-configs" / "runtimes" / "selftest-invalid-shape.toml"
    try:
        runtime_path.write_text(
            'command = "python3"\nentryFile = "../escape.py"\ndiagRegex = "(["\n'
            'diagIgnore = ["**"]\n',
            encoding="utf-8")
        check_runtime({"runtime": {"name": "selftest-invalid-shape"}}, "test", "tome.toml")
        got = findings()
        assert any(lv == "ERROR" and "command must be an array" in msg
                   for lv, _, msg in got), got
        assert any(lv == "ERROR" and "entryFile must stay inside" in msg
                   for lv, _, msg in got), got
        assert any(lv == "ERROR" and "diagRegex is not a valid" in msg
                   for lv, _, msg in got), got
        assert any(lv == "ERROR" and "diagIgnore[0] is not a valid" in msg
                   for lv, _, msg in got), got
    finally:
        runtime_path.unlink(missing_ok=True)

    # 7. A freestyle may not call the final method merely because its receiver was
    #    mentioned; the method implementation itself must appear in a lesson first.
    sections = [{"id": "s01", "brief": "", "lessons": [
        {"id": "s01-l01", "body": "<p>Create the inventory object.</p>", "exercises": []},
    ], "freestyle": {"brief": "<p>Call <code>inventory.Consume()</code>.</p>",
                       "xray": "", "rubric": []}}]
    check_taught_before_used(sections)
    got = findings()
    assert any(lv == "WARN" and label == "coverage" and "inventory.Consume" in msg
               for lv, label, msg in got), got

    print("ok: schema, runtime proof, prose/theme guards, capability ledger and cumulative types")


if __name__ == "__main__":
    main()
