"""Capability, cumulative type, runtime schema, and usage contract cases."""

from pathlib import Path

from validatelib import REPO
from validatelib.content.coverage import (check_capability_ledger,
                                          check_canonical_type_regressions)
from validatelib.content.depth import check_taught_before_used
from validatelib.content.structure import check_runtime
from validatelib.phase2 import check_tooling_contract

from .support import findings


def run_contract_cases():
    # 5. New scaffolds carry a cumulative capability ledger: a capstone can require
    # only ids taught in this or earlier lessons, never a future lesson.
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
    # drop the earlier public/private contract. Member-only patches are safe.
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
    # mentioned; the method implementation itself must appear in a lesson first.
    sections = [{"id": "s01", "brief": "", "lessons": [
        {"id": "s01-l01", "body": "<p>Create the inventory object.</p>", "exercises": []},
    ], "freestyle": {"brief": "<p>Call <code>inventory.Consume()</code>.</p>",
                       "xray": "", "rubric": []}}]
    check_taught_before_used(sections)
    got = findings()
    assert any(lv == "WARN" and label == "coverage" and "inventory.Consume" in msg
               for lv, label, msg in got), got
