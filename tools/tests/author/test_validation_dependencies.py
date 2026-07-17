#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""Focused regressions for runtime-neutral validation dependency provisioning."""
import builtins
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from buildlib import measure
from buildlib.runtime import validation_env
from buildlib.course_map import validation_dependency_alignment_problems
from buildlib.course.dependencies import external_workspace_capability_alignment_problems
from runtimes import common as runtime_common
from runtimes.generic import CommandRuntime


def test_environment_dependencies_are_isolated_cached_and_exported():
    with tempfile.TemporaryDirectory() as root:
        repo = pathlib.Path(root)
        (repo / "tomes" / "demo").mkdir(parents=True)
        runtimes = repo / "global-configs" / "runtimes"
        runtimes.mkdir(parents=True)
        (repo / "tomes" / "demo" / "tome.toml").write_text(textwrap.dedent("""
            [runtime]
            name = "fake"
            validationDependencies = ["alpha>=1", "beta"]
        """), encoding="utf-8")
        create_script = (
            "import pathlib,sys; pathlib.Path(sys.argv[1], 'created').write_text('yes')")
        package_script = (
            "import pathlib,sys; p=pathlib.Path(sys.argv[1], 'installed'); "
            "p.write_text((p.read_text() if p.exists() else '') + sys.argv[2] + '\\n')")
        (runtimes / "fake.toml").write_text(textwrap.dedent(f"""
            command = [{json.dumps(sys.executable)}]
            validationCreateCommand = [{json.dumps(sys.executable)}, "-c", {json.dumps(create_script)}, "{{dir}}"]
            validationPackageCommand = [{json.dumps(sys.executable)}, "-c", {json.dumps(package_script)}, "{{dir}}", "{{package}}"]
            validationEnv = {{ FAKE_SITE = "{{dir}}/site", PATH = "{{dir}}/bin:{{PATH}}" }}
        """), encoding="utf-8")

        env_root = repo / ".tome-build" / "validation-envs"
        with patch.multiple(validation_env, REPO=str(repo),
                            RUNTIME_CONFIG_DIR=str(runtimes), ENV_ROOT=str(env_root)):
            overrides = validation_env.ensure_validation_environment("demo")
            assert overrides["FAKE_SITE"].endswith("/site")
            assert overrides["PATH"].endswith(os.environ.get("PATH", ""))
            environment = pathlib.Path(overrides["FAKE_SITE"]).parent
            assert (environment / "created").read_text() == "yes"
            installed = environment / "installed"
            assert installed.read_text().splitlines() == ["alpha>=1", "beta"]
            validation_env.ensure_validation_environment("demo")
            assert installed.read_text().splitlines() == ["alpha>=1", "beta"]


def test_ready_environment_cache_hit_is_read_only():
    with tempfile.TemporaryDirectory() as root:
        repo = pathlib.Path(root)
        (repo / "tomes" / "demo").mkdir(parents=True)
        runtimes = repo / "global-configs" / "runtimes"
        runtimes.mkdir(parents=True)
        (repo / "tomes" / "demo" / "tome.toml").write_text(textwrap.dedent("""
            [runtime]
            name = "fake"
            validationDependencies = ["alpha"]
        """), encoding="utf-8")
        package_script = (
            "import pathlib,sys; pathlib.Path(sys.argv[1], 'installed').write_text(sys.argv[2])")
        (runtimes / "fake.toml").write_text(textwrap.dedent(f"""
            validationPackageCommand = [{json.dumps(sys.executable)}, "-c", {json.dumps(package_script)}, "{{dir}}", "{{package}}"]
            validationEnv = {{ FAKE_SITE = "{{dir}}/site" }}
        """), encoding="utf-8")

        env_root = repo / ".tome-build" / "validation-envs"
        with patch.multiple(validation_env, REPO=str(repo),
                            RUNTIME_CONFIG_DIR=str(runtimes), ENV_ROOT=str(env_root)):
            expected = validation_env.ensure_validation_environment("demo")
            real_open = builtins.open

            def read_only_open(path, mode="r", *args, **kwargs):
                if os.fspath(path).endswith(".lock") and any(flag in mode for flag in "awx+"):
                    raise OSError(30, "Read-only file system", os.fspath(path))
                return real_open(path, mode, *args, **kwargs)

            with patch("builtins.open", side_effect=read_only_open):
                assert validation_env.ensure_validation_environment("demo") == expected


def test_project_dependencies_install_once_in_scratch_only():
    with tempfile.TemporaryDirectory() as root:
        script = ("import pathlib,sys; p=pathlib.Path(sys.argv[1], 'packages'); "
                  "p.write_text((p.read_text() if p.exists() else '') + sys.argv[2] + '\\n')")
        runtime = CommandRuntime({
            "name": "project-test",
            "validationDependencies": ["first@2", "second"],
            "packageCommand": [sys.executable, "-c", script, "{dir}", "{package}"],
        })
        runtime._install_validation_project_dependencies(root)
        runtime._install_validation_project_dependencies(root)
        assert pathlib.Path(root, "packages").read_text().splitlines() == ["first@2", "second"]
        assert not pathlib.Path(root).parent.joinpath("packages").exists()


def test_shared_environment_does_not_require_a_project_installer():
    runtime = CommandRuntime({
        "name": "shared-test",
        "command": [sys.executable],
        "entryFile": "main.py",
        "validationDependencies": ["already-in-the-shared-environment"],
        "validationPackageCommand": [sys.executable, "-m", "pip", "install", "{package}"],
    })
    with tempfile.TemporaryDirectory() as root:
        result = runtime.run_snippet(root, 'print("shared env works")\n', "", env=os.environ.copy())
        assert result["ok"] and result["output"] == "shared env works", result


def test_runtime_atomic_write_creates_nested_entry_parent():
    with tempfile.TemporaryDirectory() as root:
        entry = os.path.join(root, "src", "example", "main.py")
        runtime_common.atomic_write(entry, "print('ready')\n")
        assert pathlib.Path(entry).read_text(encoding="utf-8") == "print('ready')\n"
        assert not pathlib.Path(entry + ".tmp").exists()


def test_automated_validation_environment_cannot_reach_the_desktop():
    inherited = {
        "PATH": os.environ.get("PATH", ""),
        "DISPLAY": ":77",
        "WAYLAND_DISPLAY": "wayland-77",
        "MIR_SOCKET": "mir-77",
        "SDL_VIDEODRIVER": "x11",
        "SDL_AUDIODRIVER": "pulseaudio",
    }
    headless = validation_env.headless_validation_env(inherited)
    assert "DISPLAY" not in headless
    assert "WAYLAND_DISPLAY" not in headless
    assert "MIR_SOCKET" not in headless
    assert headless["SDL_VIDEODRIVER"] == "dummy"
    assert headless["SDL_AUDIODRIVER"] == "dummy"
    assert headless["PYGAME_HIDE_SUPPORT_PROMPT"] == "1"
    assert inherited["DISPLAY"] == ":77", "the caller's environment was mutated"


def test_harness_provisions_declared_dependencies_before_validation():
    events = []
    completed = subprocess.CompletedProcess(["validator"], 0, "clean", "")
    with patch.object(measure, "ensure_validation_environment",
                      side_effect=lambda tid: events.append(("provision", tid))), \
            patch.object(measure, "validation_subprocess_env",
                         side_effect=lambda tid: events.append(("environment", tid)) or {}), \
            patch.object(measure.subprocess, "run", return_value=completed) as run:
        result = measure._run_harness_command(["validator"], "demo", announce=False)
    assert result is completed
    assert events == [("provision", "demo"), ("environment", "demo")]
    run.assert_called_once()


def test_unstructured_validator_failure_is_harness_owned():
    crashed = subprocess.CompletedProcess(
        ["validator"], 1, "ERROR unrelated: later content finding\n",
        "Traceback (most recent call last):\nModuleNotFoundError: arcanum")
    with patch.object(measure, "ensure_validation_environment"), \
            patch.object(measure, "validation_subprocess_env", return_value={}), \
            patch.object(measure.subprocess, "run", return_value=crashed):
        try:
            measure._run_harness_command(["validator"], "demo", announce=False)
        except measure.ValidatorInfrastructureError as exc:
            assert "ModuleNotFoundError" in str(exc)
        else:
            raise AssertionError("raw validator traceback was treated as authored content")

    authored = subprocess.CompletedProcess(
        ["validator"], 1, "ERROR content: repair this lesson\n", "")
    with patch.object(measure, "ensure_validation_environment"), \
            patch.object(measure, "validation_subprocess_env", return_value={}), \
            patch.object(measure.subprocess, "run", return_value=authored):
        assert measure._run_harness_command(
            ["validator"], "demo", announce=False) is authored


def test_phase2_reconciles_node_packages_before_manifest_becomes_read_only():
    proposal = {
        "version": 2,
        "sections": [{
            "id": "s10",
            "nodes": [{
                "id": "s10.l01",
                "kind": "lesson",
                "validationDependencies": ["pytest"],
            }],
        }],
    }
    pygame_only = {"runtime": {"validationDependencies": ["pygame"]}}
    problems = validation_dependency_alignment_problems(proposal, pygame_only)
    assert any("pytest" in problem and "Phase 3 cannot edit tome.toml" in problem
               for problem in problems)
    assert any("pygame" in problem and "not assigned" in problem for problem in problems)
    complete = {"runtime": {"validationDependencies": ["pygame", "pytest"]}}
    proposal["sections"][0]["nodes"].append({
        "id": "s10.working", "kind": "working",
        "validationDependencies": ["pygame"],
    })
    assert not validation_dependency_alignment_problems(proposal, complete)


def test_phase2_keeps_external_workspace_map_achievable():
    proposal = {
        "sections": [
            {"nodes": [
                {"kind": "lesson", "teaches": ["tool-install"]},
                {"kind": "working", "requires": []},
            ]},
            {"nodes": [
                {"kind": "lesson", "teaches": ["package-project"]},
                {"kind": "working", "requires": ["package-project"]},
            ]},
        ],
    }
    manifest = {"runtime": {"externalWorkspace": True}}
    problems = external_workspace_capability_alignment_problems(proposal, manifest)
    assert any("tool-create-open" in problem and "Phase 3 cannot add" in problem
               for problem in problems)
    assert any("teach tool-deliver" in problem for problem in problems)
    assert any("require tool-deliver" in problem for problem in problems)

    proposal["sections"][0]["nodes"][0]["teaches"] = [
        "tool-install", "tool-create-open", "tool-navigate", "tool-edit-save",
        "tool-run-test", "tool-diagnose",
    ]
    proposal["sections"][-1]["nodes"][0]["teaches"].append("tool-deliver")
    proposal["sections"][-1]["nodes"][1]["requires"].append("tool-deliver")
    assert not external_workspace_capability_alignment_problems(proposal, manifest)
    assert not external_workspace_capability_alignment_problems(
        {"sections": []}, {"runtime": {"externalWorkspace": False}})


def main():
    test_environment_dependencies_are_isolated_cached_and_exported()
    test_ready_environment_cache_hit_is_read_only()
    test_project_dependencies_install_once_in_scratch_only()
    test_shared_environment_does_not_require_a_project_installer()
    test_runtime_atomic_write_creates_nested_entry_parent()
    test_automated_validation_environment_cannot_reach_the_desktop()
    test_harness_provisions_declared_dependencies_before_validation()
    test_unstructured_validator_failure_is_harness_owned()
    test_phase2_reconciles_node_packages_before_manifest_becomes_read_only()
    test_phase2_keeps_external_workspace_map_achievable()
    print("ok validation dependencies: isolation/cache + live snippet + headless execution")


if __name__ == "__main__":
    main()
