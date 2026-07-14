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
from validatelib.proof import check_future_tome_proof, check_no_bundled_media  # noqa: E402
from buildlib import review_evidence  # noqa: E402
from tome_proof import proof_fingerprint, public_section  # noqa: E402
import tome_layout  # noqa: E402
from new_tome import SECTION_TEMPLATE, render  # noqa: E402
from split_tome import migrate_section  # noqa: E402


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
import sys

def result():
    return "guided"

if "--arcanum-acceptance" in sys.argv:
    print(json.dumps({"version": 1, "status": "PASS", "scenarios": {"launch": True, "finished-result": True}}, separators=(",", ":")))
elif "--arcanum-proof" in sys.argv:
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


def findings_for(data, run=False, manifest_data=None):
    _findings.clear()
    with tempfile.TemporaryDirectory() as root:
        check_future_tome_proof(root, manifest_data or manifest(), [data], run=run)
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
        evidence_rows = ["checkpoint:s01/proof:s01", "acceptance:source"]
        evidence = Path(root, ".tome-build", "demo.proof-evidence.json")
        evidence.parent.mkdir()
        evidence.write_text(json.dumps({"version": 1, "tome": "demo",
                                        "fingerprint": fingerprint,
                                        "rows": [{"id": row, "status": "pass"}
                                                 for row in evidence_rows]}), encoding="utf-8")
        report = {"version": 2, "evidenceFingerprint": fingerprint,
                  "evidenceRowsReviewed": evidence_rows,
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
            step["content"] = step["content"].replace(', "finished-result": True', "")
            if "find" in step:
                step["find"] = step["find"].replace(', "finished-result": True', "")
    replay = findings_for(bad, run=True)
    assert any("acceptance scenarios must exactly report every planned id true" in message
               for _level, _label, message in replay), replay


def check_clean_package_gate():
    packaged = section()
    packaged["proof"] = {"mode": "package", "expectedFiles": ["main.py", "requirements.txt"],
                         "requirementsFile": "requirements.txt",
                         "packageArgs": ["fixture-build"], "artifactPath": "dist/proof-app"}
    packaged["lessons"][0]["artifactSteps"].append({
        "id": "s01-requirements", "path": "requirements.txt", "mode": "write",
        "instruction": "Create the exact dependency manifest used by the clean package proof.",
        "content": "fixture-dependency==1\n"})
    create = ("import pathlib,sys; pathlib.Path(sys.argv[1]).mkdir(parents=True)")
    install = ("import pathlib,sys; req=pathlib.Path(sys.argv[2]).read_text(); "
               "assert req=='fixture-dependency==1\\n'; "
               "pathlib.Path(sys.argv[1],'installed').write_text('yes')")
    build = ("import os,pathlib,sys; assert pathlib.Path(sys.argv[2],'installed').is_file(); "
             "p=pathlib.Path(sys.argv[1]); p.parent.mkdir(parents=True,exist_ok=True); "
             "p.write_text('#!" + sys.executable + "\\nimport json,os\\nassert \\\"VIRTUAL_ENV\\\" not in os.environ and \\\"PYTHONPATH\\\" not in os.environ\\nprint(json.dumps({\\\"version\\\":1,\\\"status\\\":\\\"PASS\\\",\\\"scenarios\\\":{\\\"launch\\\":True,\\\"finished-result\\\":True}},separators=(\\\",\\\",\\\":\\\")))\\n'); "
             "os.chmod(p,0o755)")
    package_manifest = manifest()
    package_manifest["acceptance"]["artifact"] = "package"
    package_manifest["runtime"].update({
        "deliveryCreateCommand": [sys.executable, "-c", create, "{env}"],
        "deliveryInstallCommand": [sys.executable, "-c", install, "{env}", "{requirements}"],
        "deliveryBuildCommand": [sys.executable, "-c", build, "{artifact}", "{env}"],
    })
    with patch.dict(os.environ, {"VIRTUAL_ENV": "/dirty-validation-env",
                                 "PYTHONPATH": "/dirty-python-path"}):
        clean = findings_for(packaged, run=True, manifest_data=package_manifest)
    assert not [finding for finding in clean if finding[0] == "ERROR"], clean

    missing = copy.deepcopy(packaged)
    missing["proof"]["artifactPath"] = "dist/missing-app"
    broken_manifest = copy.deepcopy(package_manifest)
    broken_manifest["runtime"]["deliveryBuildCommand"] = [sys.executable, "-c", "print('no artifact')"]
    replay = findings_for(missing, run=True, manifest_data=broken_manifest)
    assert any("delivery build did not create" in message
               for _level, _label, message in replay), replay


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
    check_bundled_media_gate()
    check_harness_owned_review()
    check_split_layout_round_trip()
    check_cumulative_regression_contract()
    check_acceptance_scenario_gate()
    check_clean_package_gate()
    print("future tome proof: OK (replay, teaching, assets, harness verdict, legacy isolation)")


if __name__ == "__main__":
    main()
