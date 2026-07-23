#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

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

from validatelib.session import legacy_findings as findings  # noqa: E402
from validatelib.proof import runtime as proof_runtime  # noqa: E402
from validatelib.proof import check_future_tome_proof, check_no_bundled_media  # noqa: E402
from buildlib import review_evidence  # noqa: E402
from tome_proof import proof_fingerprint, public_section  # noqa: E402
import tome_layout  # noqa: E402
from new_tome import SECTION_TEMPLATE, render  # noqa: E402
from maintenance.split_tome import migrate_section  # noqa: E402
from proof_tests.regressions import check_clean_package_gate  # noqa: E402
from proof_tests.learner_construction import (check_learner_author_work_order,  # noqa: E402
                                              check_sealed_map_work_order_boundary)


from tome_proof_fixtures import assert_error, findings_for, manifest, section

def check_harness_owned_review():
    assert proof_fingerprint(manifest(), [section()], {"command": ["one"]}) != (
        proof_fingerprint(manifest(), [section()], {"command": ["two"]}))
    with tempfile.TemporaryDirectory() as root:
        tome = Path(root, "tomes", "demo")
        (tome / "sections").mkdir(parents=True)
        (tome / "tome.toml").write_text(
            '[content]\nproofVersion = 1\nsections = ["s01", "s02"]\n'
            '[acceptance]\nversion = 1\nmode = "run"\nartifact = "runtime"\n'
            'runArgs = ["--accept"]\nscenarios = ["launch", "finish"]\ncontrols = []\n',
            encoding="utf-8")
        (tome / "sections" / "s01.toml").write_text(
            'id = "s01"\n[proof]\nmode = "run"\nexpectedFiles = ["main.py"]\n'
            'runArgs = ["--proof", "s01"]\nexpect = "ok"\n'
            '[[lessons]]\nid = "s01-l01"\nteaches = ["one-capability"]\n',
            encoding="utf-8")
        (tome / "sections" / "s02.toml").write_text(
            'id = "s02"\n[proof]\nmode = "run"\nexpectedFiles = ["main.py"]\n'
            'runArgs = ["--proof", "s02"]\nexpect = "ok"\n'
            '[[lessons]]\nid = "s02-l01"\nteaches = ["two-capability"]\n',
            encoding="utf-8")
        findings = Path(root, "findings.json")
        verdict = Path(root, "verdict")
        verdict.write_text("", encoding="utf-8")
        with open(tome / "tome.toml", "rb") as handle:
            manifest_data = __import__("tomllib").load(handle)
        sections_data = [tome_layout.load_section(str(tome), sid) for sid in ("s01", "s02")]
        fingerprint = proof_fingerprint(manifest_data, sections_data)
        evidence_rows = ["checkpoint:s01/proof:s01", "checkpoint:s02/proof:s01",
                         "checkpoint:s02/proof:s02",
                         "project:final-build",
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
                  "sectionsReviewed": ["s01", "s02"],
                  "capabilitiesReviewed": ["one-capability", "two-capability"], "findings": []}
        findings.write_text(json.dumps(report), encoding="utf-8")
        with patch.object(review_evidence, "REPO", root):
            hook = review_evidence.protocol("demo", "findings.json", "read all")
            assert "Do not write PASS" in hook
            assert review_evidence.derived_verdict("demo", str(verdict), str(findings)) == "PASS"
            report["capabilitiesReviewed"] = []
            findings.write_text(json.dumps(report), encoding="utf-8")
            assert review_evidence.derived_verdict("demo", str(verdict), str(findings)) is None
            report["capabilitiesReviewed"] = ["one-capability", "two-capability"]
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
        findings.clear()
        check_no_bundled_media(root, manifest())
        assert any(level == "ERROR" and "media file is bundled" in message
                   for level, _label, message in findings), findings
        generated = manifest()
        generated["runtime"]["starterCode"] = "from PIL import Image\nImage.new('RGB', (8, 8))"
        findings.clear()
        check_no_bundled_media(root, generated)
        assert any(level == "ERROR" and "media synthesis" in message
                   for level, _label, message in findings), findings
        dependent = manifest()
        dependent["runtime"]["starterCode"] = "open('assets/player.png', 'rb')"
        findings.clear()
        check_no_bundled_media(root, dependent)
        assert any(level == "ERROR" and "initial scaffold asset-free" in message
                   for level, _label, message in findings), findings


def check_section_gate_ignores_future_scaffolds():
    authored = section()
    authored["proof"] = {"mode": "build", "expectedFiles": ["main.py"]}
    future = copy.deepcopy(section())
    future["id"] = "s02"
    future["lessons"][0]["id"] = "s02-l01"
    future["lessons"][0]["concepts"] = []
    scoped_manifest = manifest()
    scoped_manifest["content"]["sections"] = ["s01", "s02"]

    findings.clear()
    with tempfile.TemporaryDirectory() as root:
        check_future_tome_proof(
            root, scoped_manifest, [authored, future], run=False, run_section="s01")
    assert not [finding for finding in findings if finding[0] == "ERROR"], findings

    # The exact same future placeholder must remain visible to the complete Phase-3 gate.
    findings.clear()
    with tempfile.TemporaryDirectory() as root:
        check_future_tome_proof(root, scoped_manifest, [authored, future], run=False)
    assert any(level == "ERROR" and "without matching structured concept evidence" in message
               for level, _label, message in findings), findings


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
        assert loaded["lessons"][0]["concepts"]
        assert not loaded["lessons"][0].get("artifactSteps")
        assert loaded["freestyle"]["referenceSteps"]


def check_split_layout_rejects_malformed_lesson_table():
    with tempfile.TemporaryDirectory() as root:
        section_root = Path(root, "sections", "s01")
        (section_root / "lessons").mkdir(parents=True)
        (section_root / "section.toml").write_text('id = "s01"\n', encoding="utf-8")
        (section_root / "lessons" / "l01.toml").write_text(
            'id = "l01"\n[[lessons.readings]]\ntitle = "Reference"\n',
            encoding="utf-8")
        try:
            tome_layout.load_section(root, "s01")
        except ValueError as exc:
            assert "must contain one or more [[lessons]] tables" in str(exc)
        else:
            raise AssertionError("malformed split lesson was accepted")


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
    second["freestyle"]["requires"] = ["second-result"]
    second["freestyle"]["referenceSteps"] = [{
        "id": "s02-reference", "path": "main.py", "mode": "rewrite",
        "preserves": "all-active",
        "instruction": "Privately reconstruct the complete second milestone implementation.",
        "content": bad_source}]
    scoped = manifest()
    scoped["content"]["sections"] = ["s01", "s02"]
    return scoped, [first, second]


def check_cumulative_regression_contract():
    scoped, sections = two_section_regression()
    findings.clear()
    with tempfile.TemporaryDirectory() as root:
        check_future_tome_proof(root, scoped, sections, run=True)
    assert any("s02 regression: active proof s01 failed" in message
               for _level, _label, message in findings), findings

    overwrite = copy.deepcopy(sections)
    overwrite[1]["freestyle"]["referenceSteps"][0]["mode"] = "write"
    overwrite[1]["freestyle"]["referenceSteps"][0].pop("preserves")
    findings.clear()
    with tempfile.TemporaryDirectory() as root:
        check_future_tome_proof(root, scoped, overwrite, run=True)
    assert any("write target 'main.py' already exists" in message
               for _level, _label, message in findings), findings

    missing_declaration = copy.deepcopy(sections[1])
    missing_declaration["freestyle"]["referenceSteps"][0].pop("preserves")
    assert_error(missing_declaration, "must declare preserves = 'all-active'")

    dropped = copy.deepcopy(sections)
    dropped[1]["proof"]["supersedes"] = ["s01"]
    dropped[1]["proof"]["protects"] = ["second-result"]
    findings.clear()
    with tempfile.TemporaryDirectory() as root:
        check_future_tome_proof(root, scoped, dropped, run=False)
    assert any("replacement proof drops active capabilities" in message
               for _level, _label, message in findings), findings


def check_acceptance_scenario_gate():
    bad = section()
    for step in bad["freestyle"]["referenceSteps"]:
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
        findings.clear()
        with patch.object(proof_runtime, "REPO", root):
            check_future_tome_proof(str(tome), manifest(), [section()], run=True)
        assert not [finding for finding in findings if finding[0] == "ERROR"], findings
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
    check_learner_author_work_order(section, findings_for, assert_error)
    check_sealed_map_work_order_boundary(section)
    clean = findings_for(section(), run=True)
    assert not [finding for finding in clean if finding[0] == "ERROR"], clean
    public = public_section(section())
    assert "referenceSteps" not in public["freestyle"]
    assert not public["lessons"][0].get("artifactSteps"), (
        "ordinary lessons should leave project construction to the chapter Working")

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
    bad["freestyle"]["referenceSteps"][0]["path"] = "assets/generated.png"
    assert_error(bad, "AI-authored media is forbidden")

    bad = section()
    bad["freestyle"]["referenceSteps"][0]["content"] += "\nfrom PIL import Image\nImage.new('RGB', (8, 8))\n"
    assert_error(bad, "synthesizes or embeds media")

    bad = section()
    bad["freestyle"]["referenceSteps"][0]["content"] += (
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

    invented_delivery = manifest()
    invented_delivery["acceptance"]["sealedDelivery"] = {
        "mode": "package", "artifact": "dist/app", "requirements": "requirements.txt"}
    invented_findings = findings_for(section(), manifest_data=invented_delivery)
    assert any(level == "ERROR" and "[acceptance] has unknown keys: sealedDelivery" in message
               for level, _label, message in invented_findings), invented_findings

    bad = section()
    bad["proof"] = {"mode": "build", "expectedFiles": ["main.py"]}
    assert_error(bad, "final section of a non-external tome must use a deterministic run")

    legacy = manifest()
    legacy["content"].pop("proofVersion")
    findings.clear()
    with tempfile.TemporaryDirectory() as root:
        check_future_tome_proof(root, legacy, [{}], run=True)
    assert not findings, "legacy tomes must remain outside proof-v1"
    check_section_gate_ignores_future_scaffolds()
    check_truncated_prefix_does_not_run_final_acceptance()
    check_bundled_media_gate()
    check_harness_owned_review()
    check_split_layout_round_trip()
    check_split_layout_rejects_malformed_lesson_table()
    check_cumulative_regression_contract()
    check_acceptance_scenario_gate()
    check_ordinary_launch_and_anti_fake_gates()
    check_persisted_reconstruction_evidence()
    check_clean_package_gate(section, manifest, findings_for)
    print("future tome proof: OK (replay, teaching, assets, harness verdict, legacy isolation)")


if __name__ == "__main__":
    main()
