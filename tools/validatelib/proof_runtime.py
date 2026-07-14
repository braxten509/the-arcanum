"""Cumulative executable replay, acceptance, package proof, and evidence receipts."""
import json
import os
import re
import tempfile

from tome_proof import (apply_step, proof_evidence_path, proof_fingerprint,
                        safe_project_path, section_capabilities, step_lists)

from . import REPO, err


def _normalize(value):
    return "\n".join(line.rstrip() for line in
                     str(value or "").replace("\r\n", "\n").splitlines()).strip()


def _active_capabilities(section, proof, active, supersedes):
    protects = proof.get("protects")
    if isinstance(protects, list):
        return list(protects)
    return section_capabilities(section)


def _run_proof(runtime, project, proof, env):
    result = runtime.run_project(project, proof.get("stdin") or "",
                                 args=proof.get("runArgs") or [], env=env)
    if not result.get("ok"):
        return False, str(result.get("output") or "")[-3000:]
    actual = _normalize(result.get("output"))
    if proof.get("expectRegex"):
        if not re.fullmatch(str(proof["expectRegex"]), actual, re.S):
            return False, f"output did not full-match expectRegex; got {actual!r}"
    elif actual != _normalize(proof.get("expect")):
        return False, (f"output mismatch; expected {_normalize(proof.get('expect'))!r}, "
                       f"got {actual!r}")
    return True, actual


def _acceptance_output(output, acceptance, label):
    try:
        report = json.loads(_normalize(output))
    except (TypeError, json.JSONDecodeError) as exc:
        err("proof", f"{label} did not emit one JSON acceptance object: {exc}")
        return False
    scenarios = acceptance.get("scenarios") or []
    expected = {"version", "status", "scenarios"}
    if not isinstance(report, dict) or set(report) != expected:
        err("proof", f"{label} acceptance JSON keys must be exactly {sorted(expected)}")
        return False
    if report.get("version") != 1 or report.get("status") != "PASS":
        err("proof", f"{label} acceptance must report version=1 and status=PASS")
        return False
    results = report.get("scenarios")
    if (not isinstance(results, dict) or list(results) != scenarios
            or any(value is not True for value in results.values())):
        err("proof", f"{label} acceptance scenarios must exactly report every planned id true; "
            f"expected {scenarios}, got {results!r}")
        return False
    return True


def _run_acceptance(runtime, project, acceptance, env, label):
    if acceptance.get("mode") == "guided":
        return True, "guided acceptance reserved for fresh semantic review"
    result = runtime.run_project(project, "", args=acceptance.get("runArgs") or [], env=env)
    if not result.get("ok"):
        err("proof", f"{label} acceptance run failed:\n"
            + str(result.get("output") or "")[-3000:])
        return False, str(result.get("output") or "")
    return _acceptance_output(result.get("output"), acceptance, label), result.get("output")


def _apply_section(project, section):
    sid = str(section.get("id") or "?")
    for owner, steps in step_lists(section):
        for index, step in enumerate(steps, 1):
            try:
                apply_step(project, step)
            except (OSError, ValueError) as exc:
                err("proof", f"{sid} {owner} step {index} could not replay: {exc}")
                return False
    return True


def _check_files(project, checkpoint, owner, proof):
    for expected in proof.get("expectedFiles") or []:
        path = safe_project_path(expected)
        if path and not os.path.isfile(os.path.join(project, *path.split("/"))):
            kind = "milestone" if checkpoint == owner else "regression"
            err("proof", f"{checkpoint} {kind}: active proof {owner} expected file {path!r} "
                "does not exist")
            return False
    return True


def _checkpoint(runtime, project, checkpoint, active, env, rows):
    executable = [(owner, item) for owner, item in active.items()
                  if item["proof"].get("mode") in ("build", "run", "package")]
    if executable:
        built = runtime.verify_project(project, env=env)
        if not built.get("ok"):
            err("proof", f"{checkpoint} cumulative project did not build/check:\n"
                + str(built.get("output") or "")[-3000:])
            return False
    for owner, item in active.items():
        proof, mode = item["proof"], item["proof"].get("mode")
        if not _check_files(project, checkpoint, owner, proof):
            return False
        row = {"id": f"checkpoint:{checkpoint}/proof:{owner}", "checkpoint": checkpoint,
               "proof": owner, "mode": mode, "status": "pass",
               "capabilities": item["capabilities"],
               "expectedFiles": list(proof.get("expectedFiles") or []),
               "runArgs": list(proof.get("runArgs") or [])}
        if mode == "run":
            clean, detail = _run_proof(runtime, project, proof, env)
            if not clean:
                kind = "milestone" if checkpoint == owner else "regression"
                err("proof", f"{checkpoint} {kind}: active proof {owner} failed: {detail}")
                return False
        elif mode == "package":
            # The final source acceptance and clean-environment package gate run once below.
            row["status"] = "deferred-package"
        rows.append(row)
    return True


def _persist_evidence(tome_path, manifest, sections, rows):
    installed = os.path.realpath(os.path.dirname(tome_path)) == os.path.realpath(
        os.path.join(REPO, "tomes"))
    if not installed:
        return
    tid = os.path.basename(os.path.realpath(tome_path))
    path = proof_evidence_path(REPO, tid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {"version": 1, "tome": tid,
               "fingerprint": proof_fingerprint(manifest, sections),
               "rows": rows}
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def clear_evidence(tome_path):
    tid = os.path.basename(os.path.realpath(tome_path))
    try:
        os.remove(proof_evidence_path(REPO, tid))
    except OSError:
        pass


def replay(tome_path, manifest, sections, run_section=None, persist=False):
    """Replay an authored prefix and rerun every still-active earlier proof after each edit."""
    from runtimes import for_config, resolve_config
    from runtimes.delivery import package_project, run_artifact
    try:
        from buildlib.validation_env import headless_validation_env
    except ModuleNotFoundError:
        from tools.buildlib.validation_env import headless_validation_env

    target = list(sections)
    if run_section:
        ids = [str(section.get("id")) for section in target]
        try:
            target = target[:ids.index(str(run_section)) + 1]
        except ValueError:
            return False
    if persist:
        clear_evidence(tome_path)
    runtime = for_config(manifest.get("runtime") or {})
    runtime_config = resolve_config(manifest.get("runtime") or {})
    project_name = str((manifest.get("runtime") or {}).get("project") or "ProofProject")
    env, rows, active = headless_validation_env(), [], {}
    with tempfile.TemporaryDirectory(prefix="arcanum-proof-") as temp:
        project = os.path.join(temp, project_name)
        try:
            runtime.scaffold(project, project_name)
        except Exception as exc:
            err("proof", f"runtime scaffold failed: {type(exc).__name__}: {exc}")
            return False
        for section in target:
            sid = str(section.get("id") or "?")
            if not _apply_section(project, section):
                return False
            proof = section.get("proof") or {}
            supersedes = [str(item) for item in proof.get("supersedes") or []]
            for retired in supersedes:
                active.pop(retired, None)
            active[sid] = {"proof": proof,
                           "capabilities": _active_capabilities(
                               section, proof, active, supersedes)}
            if not _checkpoint(runtime, project, sid, active, env, rows):
                return False

        complete = len(target) == len(sections)
        acceptance = manifest.get("acceptance") or {}
        if complete:
            clean, output = _run_acceptance(runtime, project, acceptance, env, "source artifact")
            if not clean:
                return False
            rows.append({"id": "acceptance:source", "mode": acceptance.get("mode"),
                         "status": "pass", "scenarios": acceptance.get("scenarios") or [],
                         "runArgs": acceptance.get("runArgs") or [], "output": _normalize(output)})

            final = target[-1]
            final_proof = final.get("proof") or {}
            if final_proof.get("mode") == "package":
                packaged = package_project(runtime_config, project, final_proof, env=env)
                if not packaged.get("ok"):
                    err("proof", "final package proof failed:\n"
                        + str(packaged.get("output") or "")[-5000:])
                    return False
                result = run_artifact(packaged["artifact"], acceptance.get("runArgs") or [],
                                      env=env, timeout=runtime_config.get("runTimeout") or 60)
                if not result.get("ok"):
                    err("proof", "packaged artifact failed to launch:\n"
                        + str(result.get("output") or "")[-3000:])
                    return False
                if not _acceptance_output(result.get("output"), acceptance,
                                          "packaged artifact"):
                    return False
                for row in rows:
                    if row["id"] == f"checkpoint:{final.get('id')}/proof:{final.get('id')}":
                        row["status"] = "pass"
                rows.append({"id": "package:build", "mode": "package", "status": "pass",
                             "artifactPath": final_proof.get("artifactPath"),
                             "requirementsFile": final_proof.get("requirementsFile")})
                rows.append({"id": "acceptance:package", "mode": "run", "status": "pass",
                             "scenarios": acceptance.get("scenarios") or [],
                             "runArgs": acceptance.get("runArgs") or [],
                             "output": _normalize(result.get("output"))})
        if persist and complete:
            _persist_evidence(tome_path, manifest, sections, rows)
    return True
