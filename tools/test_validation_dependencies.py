#!/usr/bin/env python3
"""Focused regressions for runtime-neutral validation dependency provisioning."""
import json
import os
import pathlib
import sys
import tempfile
import textwrap
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from buildlib import validation_env
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


def main():
    test_environment_dependencies_are_isolated_cached_and_exported()
    test_project_dependencies_install_once_in_scratch_only()
    print("ok validation dependencies: environment + project isolation/cache")


if __name__ == "__main__":
    main()
