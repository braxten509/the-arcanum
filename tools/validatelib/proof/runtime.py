"""Cumulative executable replay, acceptance, package proof, and evidence receipts."""
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile

from arcanum.assessment.contracts import load_working_contract
from arcanum.assessment.scenarios import evaluate_expectation
import runtimes.common as runtime_common
from tome_proof import (apply_step, learner_project_path, proof_evidence_path,
                        proof_fingerprint, safe_project_path, section_capabilities,
                        step_lists)

from .. import REPO, err


def _normalize(value):
    return "\n".join(line.rstrip() for line in
                     str(value or "").replace("\r\n", "\n").splitlines()).strip()


def _stream_text(value):
    return (value.decode("utf-8", errors="replace")
            if isinstance(value, bytes) else str(value or ""))


def _active_capabilities(section, proof, active, supersedes):
    protects = proof.get("protects")
    if isinstance(protects, list):
        return list(protects)
    return section_capabilities(section)


def _run_proof(runtime, project, proof, env):
    result = runtime.run_project(project, proof.get("stdin") or "",
                                 args=proof.get("runArgs") or [], env=env)
    if not result.get("ok"):
        return False, str(result.get("output") or "")[-3000:], result
    actual = _normalize(result.get("output"))
    if "expectRaw" in proof:
        raw = str(result.get("stdout") or "")
        if raw != str(proof["expectRaw"]):
            return False, (f"raw stdout mismatch; expected {proof['expectRaw']!r}, "
                           f"got {raw!r}"), result
    elif proof.get("expectRegex"):
        if not re.fullmatch(str(proof["expectRegex"]), actual, re.S):
            return False, f"output did not full-match expectRegex; got {actual!r}", result
    elif actual != _normalize(proof.get("expect")):
        return False, (f"output mismatch; expected {_normalize(proof.get('expect'))!r}, "
                       f"got {actual!r}"), result
    return True, actual, result


def _acceptance_output(output, acceptance, label, challenged=None):
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
    expected_status = "FAIL" if challenged else "PASS"
    if report.get("version") != 1 or report.get("status") != expected_status:
        err("proof", f"{label} acceptance must report version=1 and status={expected_status}")
        return False
    results = report.get("scenarios")
    if not isinstance(results, dict) or list(results) != scenarios or any(
            not isinstance(value, bool) for value in results.values()):
        err("proof", f"{label} acceptance scenarios must exactly report every planned id as a "
            f"boolean in order; expected {scenarios}, got {results!r}")
        return False
    if challenged:
        if results.get(challenged) is not False:
            err("proof", f"{label} negative control must make scenario {challenged!r} false; "
                f"got {results!r}")
            return False
    elif any(value is not True for value in results.values()):
        err("proof", f"{label} acceptance scenarios must exactly report every planned id true; "
            f"expected {scenarios}, got {results!r}")
        return False
    return True


def _run_acceptance(runtime, project, acceptance, env, label, challenged=None):
    if acceptance.get("mode") == "guided":
        return True, "guided acceptance reserved for fresh human evaluation", {}
    run_env = dict(env)
    if challenged:
        run_env["ARCANUM_ACCEPTANCE_CHALLENGE"] = challenged
        run_env["ARCANUM_ACCEPTANCE_CHALLENGE_VERSION"] = "1"
    result = runtime.run_project(project, "", args=acceptance.get("runArgs") or [], env=run_env)
    if not result.get("ok"):
        command = result.get("command") or []
        rendered = shlex.join(str(part) for part in command) if command else "(command unavailable)"
        err("proof", f"{label} acceptance run failed while executing {rendered}. "
            "The acceptance path must bypass the ordinary interactive/input loop, terminate "
            "within the runtime timeout, and emit its JSON receipt.\n"
            + str(result.get("output") or "")[-3000:])
        return False, str(result.get("output") or ""), result
    return (_acceptance_output(result.get("output"), acceptance, label, challenged),
            result.get("output"), result)


def _constant_acceptance_receipt(runtime, project, acceptance):
    """Reject the common literal-PASS adapter before trusting its output.

    This intentionally stays language-neutral. It looks only for a source region that embeds
    the complete success receipt: literal PASS plus every scenario assigned a literal true.
    Computed booleans and a status derived from observed state remain valid.
    """
    scenarios = acceptance.get("scenarios") or []
    if not scenarios or acceptance.get("mode") != "run":
        return None
    status = re.compile(r"[\"']?status[\"']?\s*[:=]\s*[\"']PASS[\"']", re.I)
    literal_true = {
        scenario: re.compile(
            rf"[\"']{re.escape(str(scenario))}[\"']\s*[:=]\s*(?:true|True|1)\b")
        for scenario in scenarios
    }
    for rel, source in runtime.collect_code(project):
        if status.search(source) and all(pattern.search(source) for pattern in literal_true.values()):
            return rel
    return None


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


def _run_working_assessment(tome_path, runtime, project, section, env, rows):
    """Execute the authored hidden checks against the reconstructed reference project."""
    sid = str(section.get("id") or "?")
    try:
        contract = load_working_contract(
            tome_path, sid, section.get("freestyle") or {})
    except (OSError, ValueError) as exc:
        err("assessment", f"{sid} hidden assessment could not load: {exc}")
        return False
    for scenario in contract.scenarios:
        if scenario.kind == "guided-observation":
            continue
        try:
            command = runtime.assessment_command(
                scenario.command_ref, project, scenario.args)
            process = subprocess.run(
                command, cwd=project, env=env, input=scenario.stdin,
                capture_output=True, text=True, timeout=scenario.timeout)
            output = runtime_common.join_output(process.stdout, process.stderr)
            result = {
                "exitCode": process.returncode,
                "output": output,
                "stdout": process.stdout or "",
                "stderr": process.stderr or "",
                "timedOut": False,
            }
        except subprocess.TimeoutExpired as exc:
            stdout, stderr = _stream_text(exc.stdout), _stream_text(exc.stderr)
            result = {
                "exitCode": None,
                "output": runtime_common.join_output(stdout, stderr),
                "stdout": stdout,
                "stderr": stderr,
                "timedOut": True,
            }
        except (OSError, ValueError) as exc:
            err("assessment", f"{sid} hidden scenario {scenario.id!r} could not run: {exc}")
            return False
        passed, problems = evaluate_expectation(scenario.expect, result, project)
        if result.get("timedOut"):
            problems.append("command timed out")
        elif "exitCode" not in scenario.expect and result.get("exitCode") != 0:
            problems.append(f"exit code was {result.get('exitCode')}, expected 0")
        if problems or not passed:
            err("assessment", f"{sid} hidden scenario {scenario.id!r} failed: "
                + "; ".join(dict.fromkeys(problems or ["expectation failed"])))
            return False
        rows.append({
            "id": f"assessment:{sid}/{scenario.id}",
            "section": sid,
            "scenario": scenario.id,
            "mode": scenario.kind,
            "status": "pass",
            "command": list(command),
            "output": _normalize(result.get("output")),
            "exit": result.get("exitCode"),
        })
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
            clean, detail, result = _run_proof(runtime, project, proof, env)
            if not clean:
                kind = "milestone" if checkpoint == owner else "regression"
                err("proof", f"{checkpoint} {kind}: active proof {owner} failed: {detail}")
                return False
            row["command"] = result.get("command") or []
            row["output"] = _normalize(result.get("output"))
            row["exit"] = result.get("exit")
        elif mode == "build":
            row["commands"] = built.get("commands") or []
            row["output"] = _normalize(built.get("output"))
            row["exit"] = built.get("exit")
        elif mode == "package":
            # The final source acceptance and clean-environment package gate run once below.
            row["status"] = "deferred-package"
        rows.append(row)
    return True


def _persist_evidence(tome_path, manifest, sections, rows, project):
    installed = os.path.realpath(os.path.dirname(tome_path)) == os.path.realpath(
        os.path.join(REPO, "tomes"))
    if not installed:
        return
    tid = os.path.basename(os.path.realpath(tome_path))
    path = proof_evidence_path(REPO, tid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {"version": 2, "tome": tid,
               "fingerprint": proof_fingerprint(manifest, sections),
               "learnerProject": os.path.relpath(project, REPO).replace(os.sep, "/"),
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


def _persistent_project(tome_path, persist):
    installed = os.path.realpath(os.path.dirname(tome_path)) == os.path.realpath(
        os.path.join(REPO, "tomes"))
    if not persist or not installed:
        return None
    tid = os.path.basename(os.path.realpath(tome_path))
    return learner_project_path(REPO, tid)


def replay(tome_path, manifest, sections, run_section=None, persist=False,
           source_only=False):
    """Replay the learner journey, then cold-start and challenge the final artifact.

    ``source_only`` is the bounded repair checkpoint: it proves reconstructed source,
    ordinary launch, and every acceptance challenge without paying for packaging. The
    harness-owned final gate always leaves it false and still proves the deliverable.
    """
    from runtimes import for_config, resolve_config
    from runtimes.delivery import package_project, run_artifact
    try:
        from runtimes.validation_environment import headless_validation_env
    except ModuleNotFoundError:
        from runtimes.validation_environment import headless_validation_env

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
    persistent = _persistent_project(tome_path, persist)
    temporary = None
    if persistent:
        if os.path.islink(persistent) or os.path.isfile(persistent):
            os.remove(persistent)
        elif os.path.isdir(persistent):
            shutil.rmtree(persistent)
        os.makedirs(os.path.dirname(persistent), exist_ok=True)
        project = persistent
    else:
        temporary = tempfile.TemporaryDirectory(prefix="arcanum-proof-")
        project = os.path.join(temporary.name, project_name)
    retained = (f" Reconstructed learner project retained at "
                f"{os.path.relpath(project, REPO)}." if persistent else "")
    try:
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
            hardened = ((manifest.get("mastery") or {})
                        .get("sourceEvidenceVersion") == 1)
            if hardened and not _run_working_assessment(
                    tome_path, runtime, project, section, env, rows):
                return False

        declared = ((manifest.get("content") or {}).get("sections")
                    if isinstance(manifest.get("content"), dict) else []) or []
        complete = bool(target and declared and str(target[-1].get("id")) ==
                        str(declared[-1]))
        acceptance = manifest.get("acceptance") or {}
        if complete and acceptance.get("mode") == "run":
            built = runtime.verify_project(project, env=env)
            if not built.get("ok"):
                err("proof", "final reconstructed learner project did not build/check:\n"
                    + str(built.get("output") or "")[-3000:] + retained)
                return False
            rows.append({"id": "project:final-build", "mode": "build", "status": "pass",
                         "commands": built.get("commands") or [],
                         "output": _normalize(built.get("output")), "exit": built.get("exit")})

            launch_stdin = acceptance.get("launchStdin") if "launchStdin" in acceptance else None
            launched = runtime.smoke_project(project, launch_stdin, env=env)
            if not launched.get("ok"):
                err("proof", "ordinary entrypoint cold-start failed before a learner could use "
                    "the artifact:\n" + str(launched.get("output") or "")[-5000:] + retained)
                return False
            rows.append({"id": "launch:ordinary", "mode": "run", "status": "pass",
                         "command": launched.get("command") or [],
                         "outcome": launched.get("outcome"),
                         "observedSeconds": launched.get("observedSeconds"),
                         "output": _normalize(launched.get("output")),
                         "exit": launched.get("exit")})

            constant = _constant_acceptance_receipt(runtime, project, acceptance)
            if constant:
                err("proof", f"acceptance adapter in {constant!r} embeds a constant PASS receipt "
                    "with every scenario set to literal true; compute each result from exercised "
                    "domain behavior instead" + retained)
                return False
            rows.append({"id": "acceptance:anti-constant", "mode": "static",
                         "status": "pass", "filesChecked": len(runtime.collect_code(project))})

        if complete:
            clean, output, result = _run_acceptance(
                runtime, project, acceptance, env, "source artifact")
            if not clean:
                return False
            rows.append({"id": "acceptance:source", "mode": acceptance.get("mode"),
                         "status": "pass", "scenarios": acceptance.get("scenarios") or [],
                         "runArgs": acceptance.get("runArgs") or [],
                         "command": result.get("command") or [],
                         "output": _normalize(output), "exit": result.get("exit")})
            if acceptance.get("mode") == "run":
                challenges_clean = True
                for scenario in acceptance.get("scenarios") or []:
                    clean, output, result = _run_acceptance(
                        runtime, project, acceptance, env,
                        f"source artifact challenge {scenario!r}", challenged=scenario)
                    if not clean:
                        challenges_clean = False
                        continue
                    rows.append({"id": f"acceptance:negative:{scenario}", "mode": "run",
                                 "status": "pass", "challengedScenario": scenario,
                                 "command": result.get("command") or [],
                                 "output": _normalize(output), "exit": result.get("exit")})
                if not challenges_clean:
                    return False

            final = target[-1]
            final_proof = final.get("proof") or {}
            if final_proof.get("mode") == "package" and not source_only:
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
                             "requirementsFile": final_proof.get("requirementsFile"),
                             "commands": packaged.get("commands") or [],
                             "output": _normalize(packaged.get("output"))})
                rows.append({"id": "acceptance:package", "mode": "run", "status": "pass",
                             "scenarios": acceptance.get("scenarios") or [],
                             "runArgs": acceptance.get("runArgs") or [],
                             "command": result.get("command") or [],
                             "output": _normalize(result.get("output")),
                             "exit": result.get("exit")})
                package_challenges_clean = True
                for scenario in acceptance.get("scenarios") or []:
                    challenge_env = dict(env)
                    challenge_env["ARCANUM_ACCEPTANCE_CHALLENGE"] = scenario
                    challenge_env["ARCANUM_ACCEPTANCE_CHALLENGE_VERSION"] = "1"
                    result = run_artifact(
                        packaged["artifact"], acceptance.get("runArgs") or [],
                        env=challenge_env, timeout=runtime_config.get("runTimeout") or 60)
                    if not result.get("ok"):
                        err("proof", f"packaged artifact challenge {scenario!r} failed to run:\n"
                            + str(result.get("output") or "")[-3000:])
                        package_challenges_clean = False
                        continue
                    if not _acceptance_output(result.get("output"), acceptance,
                                              f"packaged artifact challenge {scenario!r}",
                                              challenged=scenario):
                        package_challenges_clean = False
                        continue
                    rows.append({"id": f"acceptance:package-negative:{scenario}",
                                 "mode": "run", "status": "pass",
                                 "challengedScenario": scenario,
                                 "command": result.get("command") or [],
                                 "output": _normalize(result.get("output")),
                                 "exit": result.get("exit")})
                if not package_challenges_clean:
                    return False
        if persist and complete:
            _persist_evidence(tome_path, manifest, sections, rows, project)
        return True
    finally:
        if temporary is not None:
            temporary.cleanup()
