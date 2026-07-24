#!/usr/bin/env python3
"""Cross-tome privacy and completeness guarantees for legacy Working grading."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from arcanum.authoring.grader import (
    _grade_with_ai, finalize_grade_result, grading_disclosure,
    run_verification, verification_specs,
)
from arcanum.authoring.services.legacy_grading import LegacyGradingService
from arcanum.ai import AiResponse
from arcanum.ai.repository_tools import execute as execute_tool
from arcanum.assessment.snapshot import SnapshotError, create_snapshot
from arcanum.platform.agent_commands import scoped_shell_command
from runtimes.command_runtime import workspace as workspace_module
from runtimes.command_runtime.workspace import WorkspaceMixin
from runtimes.command_runtime.runtime import CommandRuntime


class FixtureRuntime(WorkspaceMixin):
    CODE_EXT = (".py",)
    exclude_dirs = set()


def test_collector_includes_shared_evidence_formats_and_named_build_files():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        for relative in (
            "main.py", "settings.toml", "events.jsonl", "Modelfile",
            "notes.md", ".env", "artifact.lock", "node_modules/vendor.py",
            ".git/config.py",
        ):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(relative, encoding="utf-8")
        report = FixtureRuntime().collect_code_report(str(root))
        names = {name for name, _content in report["files"]}
        assert names == {
            "main.py", "settings.toml", "events.jsonl", "Modelfile", "notes.md",
        }
        assert report["complete"] is True


def test_collector_reports_every_file_omitted_by_the_hard_limit():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        for index in range(5):
            (root / f"{index}.py").write_text(str(index), encoding="utf-8")
        original = workspace_module.MAX_FILES
        workspace_module.MAX_FILES = 2
        try:
            report = FixtureRuntime().collect_code_report(str(root))
        finally:
            workspace_module.MAX_FILES = original
        assert len(report["files"]) == 2
        assert report["omitted"] == ["2.py", "3.py", "4.py"]
        assert report["complete"] is False


def test_disclosure_token_binds_exact_files_and_remote_destination():
    report = {"limit": 400, "omitted": [], "unreadable": []}
    payload = {
        "sectionId": "s01",
        "grader": {"kind": "anthropic", "model": "model-a"},
    }
    first = grading_disclosure(payload, [("main.py", "one")], report)
    changed_file = grading_disclosure(payload, [("main.py", "two")], report)
    changed_model = grading_disclosure(
        {**payload, "grader": {"kind": "anthropic", "model": "model-b"}},
        [("main.py", "one")], report)
    assert first["remote"] is True
    assert first["files"] == [{"path": "main.py", "bytes": 3}]
    assert first["promptFiles"] == [{
        "path": "main.py", "characters": 3, "sentCharacters": 3,
        "truncated": False,
    }]
    assert "sha256" not in first["files"][0]
    assert len({first["consentToken"], changed_file["consentToken"],
                changed_model["consentToken"]}) == 3
    assert grading_disclosure(
        {"sectionId": "s01", "grader": {"kind": "ollama", "model": "local"}},
        [], report)["remote"] is False


def test_grader_provider_receives_only_read_only_project_access():
    captured = {}

    class FakeAi:
        def complete(self, provider, request):
            captured["provider"] = provider
            captured["request"] = request
            assert Path(request.workspace).is_dir()
            assert (Path(request.workspace) / "main.py").is_file()
            return AiResponse(provider, request.model, (
                '{"scores":[],"total":0,"grade":"F","feedback":"","bestLine":""}'
            ))

    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        (project / "main.py").write_text("print('graded')", encoding="utf-8")
        result = _grade_with_ai(
            FakeAi(), "anthropic", "fixture", "evidence", str(project), key="test")
        request = captured["request"]
        assert result["grade"] == "F"
        assert request.allowed_tools == (
            "read_workspace_file", "list_workspace_files")
        assert request.web_allowed is False
        assert request.permission_paths["read"] == [request.workspace]
        assert request.readonly_paths == (request.workspace,)
        assert request.state_scope["role"] == "grader"


def test_workspace_tools_are_recursive_and_cannot_escape_the_project():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        (project / "nested").mkdir(parents=True)
        (project / "nested" / "evidence.txt").write_text(
            "complete evidence", encoding="utf-8")
        listed = __import__("json").loads(execute_tool(
            "list_workspace_files", {"contains": "evidence"}, str(project)))
        assert listed["files"] == ["nested/evidence.txt"]
        read = __import__("json").loads(execute_tool(
            "read_workspace_file",
            {"path": "nested/evidence.txt", "offset": 9, "maxCharacters": 8},
            str(project)))
        assert read["content"] == "evidence"
        try:
            execute_tool("read_workspace_file", {"path": "../../etc/passwd"}, str(project))
        except ValueError as exc:
            assert "outside the approved workspace" in str(exc)
        else:
            raise AssertionError("workspace read tool escaped its approved root")


def test_disclosure_rejects_symlinks_in_recursive_scope():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        (project / "main.py").write_text("ok", encoding="utf-8")
        (project / "outside.txt").symlink_to("/etc/hosts")
        report = FixtureRuntime().collect_code_report(str(project))
        try:
            grading_disclosure(
                {"sectionId": "s01", "grader": {
                    "kind": "anthropic", "model": "remote",
                }}, report["files"], report, str(project))
        except SnapshotError as exc:
            assert "unsupported symlink" in str(exc)
        else:
            raise AssertionError("recursive grading scope accepted a symlink")


def test_consent_and_cache_hash_cover_non_prompt_files():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        (project / "main.py").write_text("ok", encoding="utf-8")
        artifact = project / "artifact.bin"
        artifact.write_bytes(b"\x00first")
        report = FixtureRuntime().collect_code_report(str(project))
        payload = {"sectionId": "s01", "grader": {
            "kind": "anthropic", "model": "remote",
        }}
        first = grading_disclosure(payload, report["files"], report, str(project))
        artifact.write_bytes(b"\x00second")
        second = grading_disclosure(payload, report["files"], report, str(project))
        assert first["consentToken"] != second["consentToken"]
        assert first["workspaceHash"] != second["workspaceHash"]


def test_custom_grader_shell_can_read_project_but_not_its_sibling():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        project = root / "project"
        scratch = root / "scratch"
        project.mkdir()
        scratch.mkdir()
        (project / "main.txt").write_text("visible", encoding="utf-8")
        (root / "secret.txt").write_text("outside", encoding="utf-8")
        permissions = {
            "system_read": [
                path for path in ("/usr", "/bin", "/lib", "/lib64", "/etc", "/proc")
                if Path(path).exists()
            ],
            "system_both": [str(scratch), "/dev"],
            "read": [str(project)],
            "both": [],
            "execute": [],
        }
        command = scoped_shell_command(
            "test -r main.txt && test ! -w main.txt && test ! -e ../secret.txt",
            str(project), permissions)
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr


def test_essential_failure_keeps_the_letter_grade_but_blocks_passing():
    result = finalize_grade_result({
        "scores": [
            {"criterion": "Safety", "score": 5, "comment": "One unsafe edge remains."},
            {"criterion": "Craft", "score": 10, "comment": "Excellent construction."},
        ],
        "grade": "A",
        "feedback": "Strong overall.",
    }, [
        {"criterion": "Safety", "weight": 10, "desc": "Safe",
         "essential": True, "minimumScore": 6},
        {"criterion": "Craft", "weight": 90, "desc": "Craft"},
    ], [])
    assert result["total"] == 95 and result["grade"] == "A"
    assert result["essentialPassed"] is False
    assert result["verificationPassed"] is True
    assert result["passed"] is False


def test_required_cli_failure_keeps_the_grade_but_blocks_passing():
    result = finalize_grade_result({
        "scores": [{
            "criterion": "Craft", "score": 9.5,
            "comment": "The submitted source is polished.",
        }],
        "grade": "A",
    }, [
        {"criterion": "Craft", "weight": 100, "desc": "Craft"},
    ], [{
        "id": "tests", "command": "tests", "label": "Project tests",
        "required": True, "passed": False, "exitCode": 1,
    }])
    assert result["total"] == 95 and result["grade"] == "A"
    assert result["scorePassed"] is True
    assert result["verificationPassed"] is False
    assert result["passed"] is False


def test_declared_verification_runs_in_a_disposable_sandbox():
    runtime = CommandRuntime({
        "name": "fixture", "version": 1,
        "capabilities": ["project", "assessment"],
        "language": "Fixture", "entryFile": "main.txt",
        "command": ["python3"], "newFileExt": ".txt",
        "assessmentCommands": {
            "test": [
                "python3", "-c",
                "from pathlib import Path; "
                "assert Path('main.txt').read_text() == 'learner'; "
                "Path('generated.txt').write_text('verified')",
            ],
        },
    })
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        (project / "main.txt").write_text("learner", encoding="utf-8")
        with create_snapshot(str(project)) as snapshot:
            specs = verification_specs({"verification": [{
                "id": "tests", "command": "test", "label": "Project tests",
                "required": True,
            }]}, runtime)
            outcome = run_verification(runtime, snapshot, specs)
            assert outcome[0]["passed"] is True
            assert (Path(snapshot.work) / "generated.txt").read_text() == "verified"
        assert not (project / "generated.txt").exists()


def test_snapshot_discloses_private_and_dependency_exclusions():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        (project / "main.py").write_text("print('ok')", encoding="utf-8")
        (project / ".env").write_text("TOKEN=private", encoding="utf-8")
        (project / ".venv").mkdir()
        (project / ".venv" / "installed.py").write_text("dependency", encoding="utf-8")
        with create_snapshot(str(project)) as snapshot:
            assert [row["path"] for row in snapshot.manifest] == ["main.py"]
            excluded = {row["path"]: row["reason"] for row in snapshot.excluded}
            assert excluded[".env"] == "private-name policy"
            assert excluded[".venv/"] == "dependency/cache/output policy"


def test_service_requires_remote_consent_before_creating_a_job():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        (root / "main.py").write_text("print('safe')", encoding="utf-8")

        class Catalog:
            @staticmethod
            def runtime(_tome):
                return FixtureRuntime()

            @staticmethod
            def assemble(_tome):
                return {
                    "runtime": {"name": "fixture", "language": "Fixture"},
                    "narrative": {},
                    "sections": [{
                        "id": "s01", "codename": "ONE", "title": "First",
                        "freestyle": {
                            "brief": "Build it",
                            "rubric": [{
                                "criterion": "Works", "weight": 100, "desc": "Works",
                            }],
                        },
                    }],
                }

        class Workspaces:
            @staticmethod
            def write_files(_tome, _files):
                return None

            @staticmethod
            def project_dir(_tome):
                return str(root)

        class Jobs:
            @staticmethod
            def find_running(**_keys):
                return {"id": "existing"}

        service = LegacyGradingService(Jobs(), Catalog(), Workspaces(), None)
        remote = {
            "sectionId": "s01",
            "rubric": [{"criterion": "Client override", "weight": 100}],
            "verification": [{"id": "evil", "command": "evil"}],
            "grader": {"kind": "anthropic", "model": "remote"},
        }
        preview = service.preview("fixture", remote)
        assert preview["gradingContract"]["rubric"] == [{
            "criterion": "Works", "weight": 100, "desc": "Works",
        }]
        assert preview["gradingContract"]["verification"] == []
        payload, status = service.submit("fixture", remote)
        assert status == 409
        assert "explicit consent" in payload["error"]

        local = {"sectionId": "s01", "grader": {
            "kind": "ollama", "model": "local",
        }}
        payload, status = service.submit("fixture", local)
        assert status == 200 and payload["existing"] is True


if __name__ == "__main__":
    test_collector_includes_shared_evidence_formats_and_named_build_files()
    test_collector_reports_every_file_omitted_by_the_hard_limit()
    test_disclosure_token_binds_exact_files_and_remote_destination()
    test_grader_provider_receives_only_read_only_project_access()
    test_workspace_tools_are_recursive_and_cannot_escape_the_project()
    test_disclosure_rejects_symlinks_in_recursive_scope()
    test_consent_and_cache_hash_cover_non_prompt_files()
    test_custom_grader_shell_can_read_project_but_not_its_sibling()
    test_essential_failure_keeps_the_letter_grade_but_blocks_passing()
    test_required_cli_failure_keeps_the_grade_but_blocks_passing()
    test_declared_verification_runs_in_a_disposable_sandbox()
    test_snapshot_discloses_private_and_dependency_exclusions()
    test_service_requires_remote_consent_before_creating_a_job()
    print("legacy grading safety tests: OK")
