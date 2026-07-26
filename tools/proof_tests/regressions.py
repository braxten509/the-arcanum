"""Clean-environment package proof cases shared by the proof regression entrypoint."""
import copy
import fcntl
import os
import sys
import tempfile
from unittest.mock import patch


def check_persistent_project_lock(section, manifest):
    """A tome's persistent learner project is one path, so replays of it must serialise.

    Two validators at once — the publish survey's --strict pass and the Phase 3 gate —
    had one rmtree'ing the tree the other was mid-compile in, which surfaced as
    "MSBUILD : error MSB1009: Project file does not exist. Switch: Verisearch.slnx"
    and was not reproducible when either ran alone.
    """
    from validatelib.proof import runtime as proof_runtime

    def rival_can_lock(path):
        with open(path, "w", encoding="utf-8") as rival:
            try:
                fcntl.flock(rival, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except OSError:
                return False

    with tempfile.TemporaryDirectory() as build:
        project = os.path.join(build, "demo.learner-project")
        os.makedirs(project)
        held = []

        class Probe:
            def scaffold(self, _project, _name):
                held.append(rival_can_lock(project + ".lock"))
                raise RuntimeError("stop the replay once the lock has been observed")

        with patch.object(proof_runtime, "_persistent_project", return_value=project), \
                patch("runtimes.for_config", return_value=Probe()):
            assert not proof_runtime.replay(build, manifest(), [section()], persist=True)
        assert held == [False], "a concurrent replay must block on the shared project"
        assert not os.path.isdir(project), "the stale tree must still be cleared"
        assert rival_can_lock(project + ".lock"), "the lock must be released on the way out"


def check_clean_package_gate(section, manifest, findings_for):
    packaged = section()
    packaged["proof"] = {"mode": "package", "expectedFiles": ["main.py", "requirements.txt"],
                         "requirementsFile": "requirements.txt",
                         "packageArgs": ["fixture-build"], "artifactPath": "dist/proof-app"}
    packaged["freestyle"]["referenceSteps"].append({
        "id": "s01-requirements", "path": "requirements.txt", "mode": "write",
        "instruction": "Create the exact dependency manifest used by the clean package proof.",
        "content": "fixture-dependency==1\n"})
    create = "import pathlib,sys; pathlib.Path(sys.argv[1]).mkdir(parents=True)"
    resolve = ("import pathlib,sys; req=pathlib.Path(sys.argv[2]).read_text(); "
               "assert req=='fixture-dependency==1\\n'; "
               "cache=pathlib.Path(sys.argv[3]); assert cache.is_dir(); "
               "pathlib.Path(sys.argv[1],'resolved').write_text(str(cache))")
    install = ("import pathlib,sys; req=pathlib.Path(sys.argv[2]).read_text(); "
               "assert req=='fixture-dependency==1\\n'; "
               "assert pathlib.Path(sys.argv[1],'resolved').is_file(); "
               "pathlib.Path(sys.argv[1],'installed').write_text('yes')")
    artifact_source = ("#!" + sys.executable + "\nimport json,os\n"
                       "assert 'VIRTUAL_ENV' not in os.environ and 'PYTHONPATH' not in os.environ\n"
                       "challenge=os.environ.get('ARCANUM_ACCEPTANCE_CHALLENGE')\n"
                       "launch=challenge!='launch'\n"
                       "finished=launch and challenge!='finished-result'\n"
                       "scenarios={'launch':launch,'finished-result':finished}\n"
                       "status='PASS' if all(scenarios.values()) else 'FAIL'\n"
                       "print(json.dumps({'version':1,'status':status,'scenarios':scenarios},separators=(',',':')))\n")
    build = ("import os,pathlib,sys; assert pathlib.Path(sys.argv[2],'installed').is_file(); "
             "p=pathlib.Path(sys.argv[1]); p.parent.mkdir(parents=True,exist_ok=True); "
             "p.write_text(sys.argv[3]); os.chmod(p,0o755)")
    package_manifest = manifest()
    package_manifest["acceptance"]["artifact"] = "package"
    package_manifest["runtime"].update({
        "deliveryCreateCommand": [sys.executable, "-c", create, "{env}"],
        "deliveryResolveCommand": [sys.executable, "-c", resolve, "{env}",
                                   "{requirements}", "{cache}"],
        "deliveryInstallCommand": [sys.executable, "-c", install, "{env}", "{requirements}"],
        "deliveryBuildCommand": [sys.executable, "-c", build, "{artifact}", "{env}",
                                 artifact_source],
    })
    with patch.dict(os.environ, {"VIRTUAL_ENV": "/dirty-validation-env",
                                 "PYTHONPATH": "/dirty-python-path"}):
        clean = findings_for(packaged, run=True, manifest_data=package_manifest)
    assert not [finding for finding in clean if finding[0] == "ERROR"], clean

    # Focused source repairs must prove every acceptance challenge but never pay for packaging.
    with patch("runtimes.delivery.package_project") as package:
        source_clean = findings_for(
            packaged, run=True, manifest_data=package_manifest, source_only=True)
    assert not [finding for finding in source_clean if finding[0] == "ERROR"], source_clean
    package.assert_not_called()

    # A cheap resolver failure must stop before dependency installation/build.
    incompatible = copy.deepcopy(package_manifest)
    incompatible["runtime"]["deliveryResolveCommand"] = [
        sys.executable, "-c", "import sys; print('unsupported exact pin'); sys.exit(3)"]
    replay = findings_for(packaged, run=True, manifest_data=incompatible)
    assert any("delivery dependency preflight exited 3" in message
               and "unsupported exact pin" in message
               for _level, _label, message in replay), replay

    missing = copy.deepcopy(packaged)
    missing["proof"]["artifactPath"] = "dist/missing-app"
    broken_manifest = copy.deepcopy(package_manifest)
    broken_manifest["runtime"]["deliveryBuildCommand"] = [
        sys.executable, "-c", "print('no artifact')"]
    replay = findings_for(missing, run=True, manifest_data=broken_manifest)
    assert any("delivery build did not create" in message
               for _level, _label, message in replay), replay
