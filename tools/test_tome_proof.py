#!/usr/bin/env python3
"""Regression checks for the future-tome replay and human-sourced asset policy."""
import copy
import os
import sys
import tempfile
import json
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validatelib import _findings  # noqa: E402
from validatelib import proof_runtime  # noqa: E402
from validatelib.proof import check_future_tome_proof, check_no_bundled_media  # noqa: E402
from buildlib import review_evidence  # noqa: E402
from tome_proof import proof_fingerprint, public_section  # noqa: E402
import tome_layout  # noqa: E402
from new_tome import SECTION_TEMPLATE, render  # noqa: E402
from split_tome import migrate_section  # noqa: E402
from proof_package_regressions import check_clean_package_gate  # noqa: E402


def manifest():
    return {
        "content": {"proofVersion": 1, "sections": ["s01"]},
        "runtime": {"name": "python", "project": "ProofProject", "language": "Python"},
        "acceptance": {"version": 1, "mode": "run", "artifact": "runtime",
                       "runArgs": ["--arcanum-acceptance"],
                       "scenarios": ["launch", "finished-result"],
                       "controls": ["input", "clock"]},
    }


def section():
    lesson_source = '''import json
import os
import sys

def result():
    return "guided"

def acceptance_report():
    challenge = os.environ.get("ARCANUM_ACCEPTANCE_CHALLENGE")
    value = result()
    launched = bool(value) and challenge != "launch"
    finished = launched and value == "milestone" and challenge != "finished-result"
    scenarios = {"launch": launched, "finished-result": finished}
    status = "PASS" if all(scenarios.values()) else "FAIL"
    print(json.dumps({"version": 1, "status": status, "scenarios": scenarios}, separators=(",", ":")))

if "--arcanum-acceptance" in sys.argv:
    acceptance_report()
elif "--arcanum-proof" in sys.argv:
    print(result())
else:
    print(result())
'''
    final_source = lesson_source.replace('return "guided"', 'return "milestone"')
    return {
        "id": "s01",
        "proof": {
            "mode": "run",
            "expectedFiles": ["main.py"],
            "runArgs": ["--arcanum-proof", "s01"],
            "expect": "milestone",
        },
        "lessons": [{
            "id": "s01-l01",
            "title": "A real first edit",
            "teaches": ["define-result"],
            "body": '<p>Write and run the function.</p><pre><code data-kind="runnable">print("guided")</code></pre>',
            "concepts": [{
                "id": "define-result",
                "purpose": "Put one reusable result behind a meaningful name.",
                "anatomy": "Read def, the function name, parentheses, colon, and indented body.",
                "example": "The complete main.py project step below defines and calls result.",
                "observable": "The proof run prints the word guided on its own line.",
                "failure": "Missing indentation raises an IndentationError before the program runs.",
                "practice": "s01-l01-e1",
            }],
            "artifactSteps": [{
                "id": "s01-main",
                "path": "main.py",
                "mode": "rewrite",
                "preserves": "all-active",
                "instruction": "From the ProofProject root, replace main.py with this complete file and run it.",
                "content": lesson_source,
            }],
            "readings": [],
            "exercises": [{"id": "s01-l01-e1", "type": "mc"}],
        }],
        "freestyle": {
            "requires": ["define-result"],
            "referenceSteps": [{
                "id": "s01-reference",
                "path": "main.py",
                "mode": "replace",
                "instruction": "Replace the guided return value with the independent milestone value.",
                "find": lesson_source,
                "content": final_source,
            }],
        },
    }


def findings_for(data, run=False, manifest_data=None, source_only=False):
    _findings.clear()
    with tempfile.TemporaryDirectory() as root:
        check_future_tome_proof(
            root, manifest_data or manifest(), [data], run=run,
            source_only=source_only)
    return list(_findings)


def assert_error(data, needle):
    findings = findings_for(data)
    assert any(level == "ERROR" and needle in message for level, _label, message in findings), findings


def check_harness_owned_review():
    assert proof_fingerprint(manifest(), [section()], {"command": ["one"]}) != (
        proof_fingerprint(manifest(), [section()], {"command": ["two"]}))
    with tempfile.TemporaryDirectory() as root:
        tome = Path(root, "tomes", "demo")
        (tome / "sections").mkdir(parents=True)
        (tome / "tome.toml").write_text(
            '[content]\nproofVersion = 1\nsections = ["s01"]\n'
            '[acceptance]\nversion = 1\nmode = "run"\nartifact = "runtime"\n'
            'runArgs = ["--accept"]\nscenarios = ["launch", "finish"]\ncontrols = []\n',
            encoding="utf-8")
        (tome / "sections" / "s01.toml").write_text(
            'id = "s01"\n[proof]\nmode = "run"\nexpectedFiles = ["main.py"]\n'
            'runArgs = ["--proof", "s01"]\nexpect = "ok"\n'
            '[[lessons]]\nid = "s01-l01"\nteaches = ["one-capability"]\n',
            encoding="utf-8")
        findings = Path(root, "findings.json")
        verdict = Path(root, "verdict")
        verdict.write_text("", encoding="utf-8")
        with open(tome / "tome.toml", "rb") as handle:
            manifest_data = __import__("tomllib").load(handle)
        sections_data = [tome_layout.load_section(str(tome), "s01")]
        fingerprint = proof_fingerprint(manifest_data, sections_data)
        evidence_rows = ["checkpoint:s01/proof:s01", "project:final-build",
                         "launch:ordinary", "acceptance:anti-constant",
                         "acceptance:source", "acceptance:negative:launch",
                         "acceptance:negative:finish"]
        evidence = Path(root, ".tome-build", "demo.proof-evidence.json")
        evidence.parent.mkdir()
        learner_project = Path(root, ".tome-build", "demo.learner-project")
        learner_project.mkdir()
        rows = []
        for row in evidence_rows:
            item = {"id": row, "status": "pass"}
            if row == "project:final-build":
                item.update(commands=[["python3", "-m", "compileall"]], output="ok")
            if row == "launch:ordinary" or row == "acceptance:source" or row.startswith(
                    "acceptance:negative:"):
                item.update(command=["python3", "main.py"], output="ok")
            rows.append(item)
        evidence.write_text(json.dumps({"version": 2, "tome": "demo",
                                        "fingerprint": fingerprint,
                                        "learnerProject": ".tome-build/demo.learner-project",
                                        "rows": rows}), encoding="utf-8")
        report = {"version": 3, "evidenceFingerprint": fingerprint,
                  "evidenceRowsReviewed": evidence_rows,
                  "learnerProjectReviewed": ".tome-build/demo.learner-project",
                  "sectionsReviewed": ["s01"],
                  "capabilitiesReviewed": ["one-capability"], "findings": []}
        findings.write_text(json.dumps(report), encoding="utf-8")
        with patch.object(review_evidence, "REPO", root):
            hook = review_evidence.protocol("demo", "findings.json", "read all")
            assert "Do not write PASS" in hook
            assert review_evidence.derived_verdict("demo", str(verdict), str(findings)) == "PASS"
            report["capabilitiesReviewed"] = []
            findings.write_text(json.dumps(report), encoding="utf-8")
            assert review_evidence.derived_verdict("demo", str(verdict), str(findings)) is None
            report["capabilitiesReviewed"] = ["one-capability"]
            findings.write_text(json.dumps(report), encoding="utf-8")
            report["findings"] = [{"file": None, "line": None, "evidenceRow": None,
                                   "issue": "whole-course behavior is not connected",
                                   "severity": "blocking"}]
            findings.write_text(json.dumps(report), encoding="utf-8")
            assert review_evidence.derived_verdict(
                "demo", str(verdict), str(findings)) is None
            report["findings"][0]["evidenceRow"] = "acceptance:source"
            findings.write_text(json.dumps(report), encoding="utf-8")
            assert review_evidence.derived_verdict(
                "demo", str(verdict), str(findings)) == "GAPS REMAIN"
            report["findings"] = []
            findings.write_text(json.dumps(report), encoding="utf-8")
            evidence.unlink()
            assert review_evidence.derived_verdict("demo", str(verdict), str(findings)) is None


def check_bundled_media_gate():
    with tempfile.TemporaryDirectory() as root:
        Path(root, "generated-by-ai.png").write_bytes(b"not really an image")
        _findings.clear()
        check_no_bundled_media(root, manifest())
        assert any(level == "ERROR" and "media file is bundled" in message
                   for level, _label, message in _findings), _findings
        generated = manifest()
        generated["runtime"]["starterCode"] = "from PIL import Image\nImage.new('RGB', (8, 8))"
        _findings.clear()
        check_no_bundled_media(root, generated)
        assert any(level == "ERROR" and "media synthesis" in message
                   for level, _label, message in _findings), _findings
        dependent = manifest()
        dependent["runtime"]["starterCode"] = "open('assets/player.png', 'rb')"
        _findings.clear()
        check_no_bundled_media(root, dependent)
        assert any(level == "ERROR" and "initial scaffold asset-free" in message
                   for level, _label, message in _findings), _findings


def check_section_gate_ignores_future_scaffolds():
    authored = section()
    authored["proof"] = {"mode": "build", "expectedFiles": ["main.py"]}
    future = copy.deepcopy(section())
    future["id"] = "s02"
    future["lessons"][0]["id"] = "s02-l01"
    future["lessons"][0]["concepts"] = []
    scoped_manifest = manifest()
    scoped_manifest["content"]["sections"] = ["s01", "s02"]

    _findings.clear()
    with tempfile.TemporaryDirectory() as root:
        check_future_tome_proof(
            root, scoped_manifest, [authored, future], run=False, run_section="s01")
    assert not [finding for finding in _findings if finding[0] == "ERROR"], _findings

    # The exact same future placeholder must remain visible to the complete Phase-3 gate.
    _findings.clear()
    with tempfile.TemporaryDirectory() as root:
        check_future_tome_proof(root, scoped_manifest, [authored, future], run=False)
    assert any(level == "ERROR" and "without matching structured concept evidence" in message
               for level, _label, message in _findings), _findings


def check_truncated_prefix_does_not_run_final_acceptance():
    authored = section()
    scoped_manifest = manifest()
    scoped_manifest["content"]["sections"] = ["s01", "s02"]
    with tempfile.TemporaryDirectory() as root, \
            patch.object(proof_runtime, "_run_acceptance") as acceptance:
        assert proof_runtime.replay(
            root, scoped_manifest, [authored], run_section="s01", persist=False)
    acceptance.assert_not_called()


def check_split_layout_round_trip():
    with tempfile.TemporaryDirectory() as root:
        sections = Path(root, "sections")
        sections.mkdir()
        source = render(SECTION_TEMPLATE, {"SID": "s01", "ROMAN": "I"})
        source += '''

[[assets]]
id = "player-sprite"
kind = "sprite"
lesson = "s01-l01"
destination = "assets/player.png"
sourceGuidance = "Choose and download a suitable human-made player sprite."
licenseGuidance = "Record its creator, source URL, license, and required attribution."
sources = [{ label = "Asset library", url = "https://example.com/assets", license = "Choose a listed permissive license" }]
'''
        (sections / "s01.toml").write_text(source, encoding="utf-8")
        migrate_section(root, "s01")
        loaded = tome_layout.load_section(root, "s01")
        assert loaded["proof"]["mode"] == "run"
        assert loaded["assets"][0]["destination"] == "assets/player.png"
        assert loaded["lessons"][0]["concepts"] and loaded["lessons"][0]["artifactSteps"]
        assert loaded["freestyle"]["referenceSteps"]


def two_section_regression():
    first = section()
    second = copy.deepcopy(section())
    second["id"] = "s02"
    second["proof"] = {"mode": "run", "expectedFiles": ["main.py"],
                       "runArgs": ["--arcanum-proof", "s02"], "expect": "second"}
    lesson = second["lessons"][0]
    lesson["id"] = "s02-l01"
    lesson["teaches"] = ["second-result"]
    lesson["concepts"][0]["id"] = "second-result"
    lesson["concepts"][0]["practice"] = "s02-l01-e1"
    lesson["exercises"][0]["id"] = "s02-l01-e1"
    bad_source = '''import json
import sys

if "--arcanum-acceptance" in sys.argv:
    print(json.dumps({"version": 1, "status": "PASS", "scenarios": {"launch": True, "finished-result": True}}, separators=(",", ":")))
elif "--arcanum-proof" in sys.argv and "s02" in sys.argv:
    print("second")
'''
    lesson["artifactSteps"] = [{"id": "s02-main", "path": "main.py", "mode": "rewrite",
                                "preserves": "all-active",
                                "instruction": "Replace the current project with the second milestone implementation.",
                                "content": bad_source}]
    second["freestyle"]["requires"] = ["second-result"]
    second["freestyle"]["referenceSteps"] = [{
        "id": "s02-reference", "path": "main.py", "mode": "append",
        "instruction": "Append one final newline after verifying the second milestone behavior.",
        "content": "\n"}]
    scoped = manifest()
    scoped["content"]["sections"] = ["s01", "s02"]
    return scoped, [first, second]


def check_cumulative_regression_contract():
    scoped, sections = two_section_regression()
    _findings.clear()
    with tempfile.TemporaryDirectory() as root:
        check_future_tome_proof(root, scoped, sections, run=True)
    assert any("s02 regression: active proof s01 failed" in message
               for _level, _label, message in _findings), _findings

    overwrite = copy.deepcopy(sections)
    overwrite[1]["lessons"][0]["artifactSteps"][0]["mode"] = "write"
    overwrite[1]["lessons"][0]["artifactSteps"][0].pop("preserves")
    _findings.clear()
    with tempfile.TemporaryDirectory() as root:
        check_future_tome_proof(root, scoped, overwrite, run=True)
    assert any("write target 'main.py' already exists" in message
               for _level, _label, message in _findings), _findings

    missing_declaration = copy.deepcopy(sections[1])
    missing_declaration["lessons"][0]["artifactSteps"][0].pop("preserves")
    assert_error(missing_declaration, "must declare preserves = 'all-active'")

    dropped = copy.deepcopy(sections)
    dropped[1]["proof"]["supersedes"] = ["s01"]
    dropped[1]["proof"]["protects"] = ["second-result"]
    _findings.clear()
    with tempfile.TemporaryDirectory() as root:
        check_future_tome_proof(root, scoped, dropped, run=False)
    assert any("replacement proof drops active capabilities" in message
               for _level, _label, message in _findings), _findings


def check_acceptance_scenario_gate():
    bad = section()
    for _owner, steps in (("lesson", bad["lessons"][0]["artifactSteps"]),
                          ("freestyle", bad["freestyle"]["referenceSteps"])):
        for step in steps:
            step["content"] = step["content"].replace(', "finished-result": finished', "")
            if "find" in step:
                step["find"] = step["find"].replace(', "finished-result": finished', "")
    replay = findings_for(bad, run=True)
    assert any("acceptance scenarios must exactly report every planned id as a boolean" in message
               for _level, _label, message in replay), replay


def check_ordinary_launch_and_anti_fake_gates():
    crashed = section()
    reference = crashed["freestyle"]["referenceSteps"][0]
    reference["content"] = reference["content"].replace(
        "else:\n    print(result())\n", "else:\n    missing_runtime_name()\n")
    replay = findings_for(crashed, run=True)
    assert any("ordinary entrypoint cold-start failed" in message
               and "missing_runtime_name" in message
               for _level, _label, message in replay), replay

    constant = section()
    reference = constant["freestyle"]["referenceSteps"][0]
    reference["content"] = reference["content"].replace(
        "    acceptance_report()\n",
        '    print(json.dumps({"version": 1, "status": "PASS", "scenarios": '
        '{"launch": True, "finished-result": True}}))\n')
    replay = findings_for(constant, run=True)
    assert any("embeds a constant PASS receipt" in message
               for _level, _label, message in replay), replay

    unchallenged = section()
    reference = unchallenged["freestyle"]["referenceSteps"][0]
    reference["content"] = reference["content"].replace(
        'challenge = os.environ.get("ARCANUM_ACCEPTANCE_CHALLENGE")',
        "challenge = None")
    replay = findings_for(unchallenged, run=True)
    assert any("challenge 'launch' acceptance must report version=1 and status=FAIL" in message
               for _level, _label, message in replay), replay
    assert any("challenge 'finished-result' acceptance must report version=1 and status=FAIL"
               in message for _level, _label, message in replay), replay


def check_persisted_reconstruction_evidence():
    with tempfile.TemporaryDirectory() as root:
        tome = Path(root, "tomes", "demo")
        tome.mkdir(parents=True)
        _findings.clear()
        with patch.object(proof_runtime, "REPO", root):
            check_future_tome_proof(str(tome), manifest(), [section()], run=True)
        assert not [finding for finding in _findings if finding[0] == "ERROR"], _findings
        project = Path(root, ".tome-build", "demo.learner-project")
        evidence_path = Path(root, ".tome-build", "demo.proof-evidence.json")
        assert (project / "main.py").is_file(), project
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert evidence["version"] == 2
        assert evidence["learnerProject"] == ".tome-build/demo.learner-project"
        row_ids = [row["id"] for row in evidence["rows"]]
        assert "project:final-build" in row_ids and "launch:ordinary" in row_ids
        assert {"acceptance:negative:launch", "acceptance:negative:finished-result"}.issubset(
            row_ids)


def main():
    clean = findings_for(section(), run=True)
    assert not [finding for finding in clean if finding[0] == "ERROR"], clean
    public = public_section(section())
    assert "referenceSteps" not in public["freestyle"]
    assert public["lessons"][0]["artifactSteps"], "learner-visible project steps were stripped"

    bad = section()
    bad["lessons"][0]["concepts"] = []
    assert_error(bad, "without matching structured concept evidence")

    bad = section()
    bad["lessons"][0]["body"] += "<p>Load assets/player.png before the loop.</p>"
    assert_error(bad, "without a [[assets]] human-sourcing guide")

    sourced = section()
    sourced["lessons"][0]["body"] += "<p>Place assets/player.png beside the source.</p>"
    sourced["assets"] = [{
        "id": "player", "kind": "sprite", "lesson": "s01-l01",
        "destination": "assets/player.png",
        "sourceGuidance": "Choose and download a suitable player sprite, then rename it exactly.",
        "licenseGuidance": "Record the license and creator attribution in your project README.",
        "sources": [{"label": "Asset library", "url": "https://example.com/assets",
                     "license": "Choose a listed permissive license"}],
    }]
    assert not [f for f in findings_for(sourced) if f[0] == "ERROR"]

    bad = section()
    bad["lessons"][0]["artifactSteps"][0]["path"] = "assets/generated.png"
    assert_error(bad, "AI-authored media is forbidden")

    bad = section()
    bad["lessons"][0]["artifactSteps"][0]["content"] += "\nfrom PIL import Image\nImage.new('RGB', (8, 8))\n"
    assert_error(bad, "synthesizes or embeds media")

    bad = section()
    bad["lessons"][0]["artifactSteps"][0]["content"] += (
        "\nimport pygame\npygame.mixer.Sound(buffer=b'generated sound')\n")
    assert_error(bad, "synthesizes or embeds media")

    bad = section()
    bad["proof"]["expect"] = "not the output"
    replay = findings_for(bad, run=True)
    assert any("s01 milestone: active proof s01 failed: output mismatch" in finding[2]
               for finding in replay), replay

    bad = section()
    bad["proof"] = {"mode": "guided", "expectedFiles": ["main.py"],
                    "guidedChecks": ["Observe the first deterministic result.",
                                     "Observe the second deterministic result."]}
    assert_error(bad, "guided proof is allowed only for runtime.externalWorkspace")
    external = manifest()
    external["runtime"]["externalWorkspace"] = True
    assert not [finding for finding in findings_for(bad, manifest_data=external)
                if finding[0] == "ERROR"], "external guided proof should remain available"

    bad = section()
    bad["proof"] = {"mode": "build", "expectedFiles": ["main.py"]}
    assert_error(bad, "final section of a non-external tome must use a deterministic run")

    legacy = manifest()
    legacy["content"].pop("proofVersion")
    _findings.clear()
    with tempfile.TemporaryDirectory() as root:
        check_future_tome_proof(root, legacy, [{}], run=True)
    assert not _findings, "legacy tomes must remain outside proof-v1"
    check_section_gate_ignores_future_scaffolds()
    check_truncated_prefix_does_not_run_final_acceptance()
    check_bundled_media_gate()
    check_harness_owned_review()
    check_split_layout_round_trip()
    check_cumulative_regression_contract()
    check_acceptance_scenario_gate()
    check_ordinary_launch_and_anti_fake_gates()
    check_persisted_reconstruction_evidence()
    check_clean_package_gate(section, manifest, findings_for)
    print("future tome proof: OK (replay, teaching, assets, harness verdict, legacy isolation)")


if __name__ == "__main__":
    main()
