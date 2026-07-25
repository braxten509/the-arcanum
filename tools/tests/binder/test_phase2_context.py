#!/usr/bin/env python3
"""Fresh Phase-2 context follows a Phase-1 rename and exposes generic commands."""
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from tools.workflow.context import render_phase2_context


with tempfile.TemporaryDirectory() as temporary:
    repo = Path(temporary)
    build_dir = repo / ".tome-build"
    author_root = build_dir / "original.course-map-author"
    tome = repo / "tomes" / "renamed-tome"
    runtimes = repo / "global-configs" / "runtimes"
    author_root.mkdir(parents=True)
    tome.mkdir(parents=True)
    runtimes.mkdir(parents=True)

    (build_dir / "original.plan.md").write_text(
        "# BUILD PLAN\n"
        "- **Starting level (1-10):** 1\n"
        "- **Tome id renamed by the harness:** `original` -> `renamed-tome`\n"
        "## Arc\nFresh authoring contract.\n",
        encoding="utf-8")
    seed_path = build_dir / "original.course-map.seed.json"
    seed_path.write_text(json.dumps({
        "sections": [{"id": "s01", "title": "One", "promise": "A result",
                      "lessonCount": 1}],
        "acceptanceScenarios": ["fresh-result"],
        "artifactContract": {"artifacts": [
            {"artifact": "work/result", "ownerWorking": "s01.working",
             "disposition": "ships"},
        ]},
        "masteryEvidence": {"standaloneLabCount": 0},
    }), encoding="utf-8")
    (tome / "tome.toml").write_text(
        '[runtime]\nname = "agnostic"\nexternalWorkspace = true\n'
        'projectFile = "project.file"\n'
        '[acceptance]\nversion = 1\nscenarios = ["fresh-result"]\n',
        encoding="utf-8")
    (runtimes / "agnostic.toml").write_text(
        'command = ["runner", "{file}"]\n'
        'scaffoldCommand = ["creator", "{dir}"]\n'
        'deliveryCreateCommand = ["stager", "{env}"]\n'
        '[assessmentCommands]\nbuild = ["checker", "{entry}"]\n',
        encoding="utf-8")

    output = io.StringIO()
    with patch.object(render_phase2_context, "REPO", repo), \
            patch.object(render_phase2_context, "BUILD_DIR", str(build_dir)), \
            patch.object(render_phase2_context, "seed_path",
                         return_value=str(seed_path)), \
            patch.object(render_phase2_context, "spec_root",
                         return_value=str(author_root)), \
            patch.object(render_phase2_context, "ledger_path",
                         return_value=str(build_dir / "original.phase2-research.json")), \
            patch.object(render_phase2_context, "audit_path",
                         return_value=str(author_root / "audit.json")), \
            patch.object(sys, "argv", ["render_phase2_context.py", "original"]), \
            redirect_stdout(output):
        render_phase2_context.main()

    rendered = output.getvalue()
    packet_text = rendered.split("PHASE 2 BOUNDED CONTEXT\n", 1)[1].split(
        "\nSEALED PHASE 1 ARC\n", 1)[0]
    packet = json.loads(packet_text)
    assert "materialize" not in packet
    assert packet["authority"]["version"] == 7
    assert packet["authority"]["startingLevel"] == 1
    assert packet["authority"]["maxFamiliesPerLesson"] == 1
    production = packet["authority"]["artifactProduction"]
    assert production["allowedModes"] == ["authored", "copied", "generated", "packaged"]
    assert production["inputPolicyByMode"]["generated"] == "optional"
    assert "never forbid a production mode" in production["inputPolicyMeaning"]
    assert packet["authority"]["research"]["maximumSources"] == 6
    assert packet["authority"]["repairOwnership"]["generatedProposalRepairable"] is False
    assert packet["authority"]["repairOwnership"]["runtimeProfileRepairable"] is True
    assert "component mechanisms" in packet["authority"]["capabilityCoverage"]["meaning"]
    assert "planned continuity obligation" in packet[
        "authority"]["continuityCoverage"]["meaning"]
    assert "branch never depends" in packet["authority"]["failurePaths"]["meaning"]
    runtime = packet["mechanicalObligations"]["runtime"]
    assert runtime["profile"] == "agnostic"
    assert runtime["externalWorkspace"] is True
    assert runtime["commands"]["command"] == ["runner", "{file}"]
    assert runtime["commands"]["scaffoldCommand"] == ["creator", "{dir}"]
    assert runtime["commands"]["deliveryCreateCommand"] == ["stager", "{env}"]
    assert runtime["commands"]["assessmentCommands"] == {
        "build": ["checker", "{entry}"]}
    assert packet["edit"]["audit"].endswith("original.course-map-author/audit.json")
    assert packet["edit"]["manifest"] == "tomes/renamed-tome/tome.toml"
    assert packet["edit"]["tomeSkeleton"] == "tomes/renamed-tome"
    assert packet["edit"]["runtimeProfile"] == "global-configs/runtimes/agnostic.toml"
    assert packet["mechanicalObligations"]["acceptanceScenarios"] == ["fresh-result"]
    assert packet["mechanicalObligations"]["artifactProductionRows"] == [{
        "artifact": "work/result", "ownerWorking": "s01.working",
        "disposition": "ships"}]
    assert any("Learner-written canonical source" in item for item in
               packet["mechanicalObligations"]["requiredAudits"])
    assert any("productionDependsOn" in item for item in
               packet["mechanicalObligations"]["requiredAudits"])
    assert any("status-before-branch" in item for item in
               packet["mechanicalObligations"]["requiredAudits"])
    assert any("planned continuity obligation" in item for item in
               packet["mechanicalObligations"]["requiredAudits"])
    assert any("before the first project source" in item for item in
               packet["mechanicalObligations"]["requiredAudits"])

print("Phase-2 renamed-tome bounded context: OK")
