#!/usr/bin/env python3
"""The same assessment contract runs on an interpreted and a compiled runtime."""
from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from arcanum.assessment.receipts import ReceiptStore
from arcanum.assessment.runner import AssessmentRequest, AssessmentService
from arcanum.assessment.sandbox import SandboxPolicy
from arcanum_core.contracts.assessment import AssessmentContract
from runtimes import for_config
from runtimes.config import RuntimeConfigurationError


def contract() -> AssessmentContract:
    capabilities = ["language-verification", "language-output"]
    return AssessmentContract.from_dict({
        "version": 1,
        "requirements": [
            {"id": "builds", "text": "The project builds from a clean snapshot.",
             "essential": True, "capabilityIds": [capabilities[0]]},
            {"id": "reports-ready", "text": "An ordinary launch prints READY.",
             "essential": True, "capabilityIds": [capabilities[1]]},
        ],
        "scenarios": [
            {"id": "clean-build", "kind": "build", "requirementIds": ["builds"],
             "capabilityIds": [capabilities[0]], "commandRef": "build", "args": [],
             "stdin": "", "expect": {"exitCode": 0}, "timeout": 120, "public": True},
            {"id": "ordinary-run", "kind": "run", "requirementIds": ["reports-ready"],
             "capabilityIds": [capabilities[1]], "commandRef": "run", "args": [],
             "stdin": "", "expect": {"exact": "READY", "exitCode": 0},
             "timeout": 120, "public": False},
            {"id": "cold-launch", "kind": "cold-launch",
             "requirementIds": ["reports-ready"], "capabilityIds": capabilities,
             "commandRef": "run", "args": [], "stdin": "",
             "expect": {"exact": "READY", "exitCode": 0},
             "timeout": 120, "public": False},
        ],
        "rubric": [{"id": "runtime-evidence", "criterion": "Build and launch behavior",
                    "weight": 100, "kind": "deterministic",
                    "assessmentIds": ["clean-build", "ordinary-run", "cold-launch"]}],
    })


def request(runtime_name: str, workspace: Path) -> AssessmentRequest:
    return AssessmentRequest(
        tome_id=f"cross-runtime-{runtime_name}", mastery_level=3,
        node_id="s09.working", performance_id="cross-runtime-proof",
        workspace=str(workspace), aid_policy="cold", support_used=False,
        capability_ids=("language-verification", "language-output"),
        language=runtime_name)


assert shutil.which("python3"), "interpreted runtime fixture requires python3"
assert shutil.which("dotnet"), "compiled runtime fixture requires dotnet"

for profile_name in (ROOT / "global-configs" / "runtimes").glob("*.toml"):
    with profile_name.open("rb") as handle:
        declared = tomllib.load(handle)
    assert declared.get("version") == 1 and declared.get("capabilities"), profile_name.name
    profile = for_config({"name": profile_name.stem})
    assert profile.VERSION == 1 and profile.CAPABILITIES, profile_name.name

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    fixtures = {
        "python": {
            "runtime": for_config({"name": "python"}),
            "files": {"main.py": 'print("READY")\n'},
        },
        "dotnet": {
            "runtime": for_config({
                "name": "dotnet", "project": "EvidenceFixture",
                "runCommand": ["dotnet", "run", "--no-build", "--project", "{dir}"],
            }),
            "files": {
                "Program.cs": 'Console.WriteLine("READY");\n',
                "EvidenceFixture.csproj": (
                    '<Project Sdk="Microsoft.NET.Sdk">\n<PropertyGroup>\n'
                    '<OutputType>Exe</OutputType>\n<TargetFramework>net10.0</TargetFramework>\n'
                    '<ImplicitUsings>enable</ImplicitUsings>\n<Nullable>enable</Nullable>\n'
                    '</PropertyGroup>\n</Project>\n'),
            },
        },
    }
    results = {}
    for runtime_name, fixture in fixtures.items():
        workspace = root / runtime_name / "workspace"
        save = root / runtime_name / "save"
        workspace.mkdir(parents=True); save.mkdir()
        for relative, content in fixture["files"].items():
            (workspace / relative).write_text(content, encoding="utf-8")
        service = AssessmentService(
            fixture["runtime"], ReceiptStore(str(save)),
            sandbox_policy=SandboxPolicy(memory_bytes=1_000_000_000, cpu_seconds=180))
        result = service.assess(request(runtime_name, workspace), contract())
        assert result["essentialPassed"] and result["independent"], (runtime_name, result)
        assert result["weightedTotal"] == 100 and result["grade"] == "A"
        assert [row["kind"] for row in result["scenarios"]] == [
            "build", "run", "cold-launch"]
        assert all(row["memoryBoundary"] in {"cgroup-v2", "rlimit-address-space"}
                   for row in result["scenarios"])
        results[runtime_name] = result

    assert results["python"]["contractHash"] == results["dotnet"]["contractHash"]
    assert results["python"]["workspaceHash"] != results["dotnet"]["workspaceHash"]

engine_sources = "\n".join(
    path.read_text(encoding="utf-8") for path in (ROOT / "arcanum" / "assessment").rglob("*.py"))
assert 'runtime_name == "python"' not in engine_sources
assert 'runtime_name == "dotnet"' not in engine_sources

try:
    for_config({"name": "dotnet", "assessmentReadPaths": ["/home"]})
except RuntimeConfigurationError:
    pass
else:
    raise AssertionError("a tome runtime override granted assessment host access")

print("cross-runtime assessment: Python interpreted + .NET compiled OK")
