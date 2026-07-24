"""Legacy freestyle grading and Oracle role services."""
import hashlib
import json
import os
import re
import subprocess
import time

from runtimes.common import atomic_write

from ..assessment.sandbox import (SandboxRunner, environment_for_runtime,
                                  policy_for_runtime)
from ..assessment.scenarios import evaluate_expectation
from ..assessment.snapshot import SnapshotError, create_snapshot
from ..config import GRADE_TIMEOUT, GRADER_MODELS, ORACLE_TIMEOUT, read_json
from ..jobs import JobManager
from ..ai import AiService
from ..ai.contracts.errors import ProviderConfigurationError
from .grading.judgment import (
    MAX_PROMPT_FILE_CHARS, build_grade_prompt, extract_json,
    grade_with_ai as _grade_with_ai,
)

FALLBACK_GRADER = "qwen2.5:14b"  # strongest installed Ollama model; overridable per-request from settings
ORACLE_MODEL = "llama3.1:8b"
MAX_PROMPT_FILE_CHARS = 20_000


def _snapshot_access(snapshot, project):
    return {
        "root": os.path.realpath(project),
        "files": [{
            "path": row["path"], "bytes": row["size"], "sha256": row["sha256"],
        } for row in snapshot.manifest],
        "excluded": list(snapshot.excluded),
        "totalBytes": sum(row["size"] for row in snapshot.manifest),
    }


def grading_disclosure(payload, files, report, project="", access=None):
    """Describe and bind the recursive read-only scope for one judgement."""
    grader = payload.get("grader") or {}
    provider = str(grader.get("kind") or "claude-cli")
    model = str(grader.get("model") or "")
    if access is None and project:
        with create_snapshot(project) as snapshot:
            access = _snapshot_access(snapshot, project)
    access = access or {
        "root": "", "files": [{
            "path": rel,
            "bytes": len(content.encode()),
            "sha256": hashlib.sha256(content.encode()).hexdigest(),
        } for rel, content in files],
        "excluded": [], "totalBytes": sum(
            len(content.encode()) for _rel, content in files),
    }
    manifest = {
        "version": 1,
        "sectionId": str(payload.get("sectionId") or "x"),
        "provider": provider,
        "model": model,
        "promptFiles": [{
            "path": rel,
            "sha256": hashlib.sha256(content.encode()).hexdigest(),
            "characters": len(content),
            "sentCharacters": min(len(content), MAX_PROMPT_FILE_CHARS),
            "truncated": len(content) > MAX_PROMPT_FILE_CHARS,
        } for rel, content in files],
        "accessRoot": access["root"],
        "accessFiles": access["files"],
        "excluded": access["excluded"],
        "gradingContract": {
            "brief": str(payload.get("brief") or ""),
            "rubric": payload.get("rubric") or [],
            "verification": payload.get("verification") or [],
        },
    }
    token = hashlib.sha256(json.dumps(
        manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    access_hashes = {
        item["path"]: item["sha256"] for item in manifest["accessFiles"]
    }
    workspace_hash = hashlib.sha256(json.dumps(
        access_hashes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "ok": True,
        "version": 1,
        "provider": provider,
        "model": model,
        "remote": provider != "ollama",
        "isolated": True,
        "files": [{"path": item["path"], "bytes": item["bytes"]}
                  for item in manifest["accessFiles"]],
        "fileCount": len(manifest["accessFiles"]),
        "totalBytes": access["totalBytes"],
        "accessRoot": access["root"],
        "recursive": True,
        "readOnly": True,
        "promptFiles": [{
            key: value for key, value in item.items() if key != "sha256"
        } for item in manifest["promptFiles"]],
        "promptFileLimit": int(report.get("limit") or 0),
        "promptOmitted": list(report.get("omitted") or []),
        "excluded": manifest["excluded"],
        "gradingContract": manifest["gradingContract"],
        "complete": True,
        "consentToken": token,
        "workspaceHash": workspace_hash,
        "_accessFileHashes": access_hashes,
        "sourceCache": "hashes and judgement only; learner file contents are not copied",
    }


def collect_grading_disclosure(payload, jid, catalog, workspaces):
    runtime = catalog.runtime(jid)
    project = workspaces.project_dir(jid)
    with create_snapshot(
            project, excluded_dirs=tuple(getattr(runtime, "exclude_dirs", ()))) as snapshot:
        report = runtime.collect_code_report(snapshot.source)
        disclosure = grading_disclosure(
            payload, report["files"], report, project,
            access=_snapshot_access(snapshot, project))
    disclosure.pop("_accessFileHashes", None)
    return disclosure


def start_grader_smoke(jid, payload, job_manager: JobManager, catalog):
    """Create a deterministic completed job for the live route/status smoke gate."""
    sid = str(payload.get("sectionId") or "")
    loaded = catalog.assemble(jid)
    section = next((item for item in (loaded.get("sections") or [])
                    if str(item.get("id")) == sid), None)
    rubric = ((section or {}).get("freestyle") or {}).get("rubric") or []
    if not section or not rubric:
        return {"ok": False, "error": "smoke section or freestyle rubric is missing"}, 400
    result = {"total": 0, "grade": "F", "scores": [],
              "model": "deterministic route smoke", "smoke": True}
    job = job_manager.completed("grade-working", result, section=sid, tome=jid, smoke=True)
    job_id = job["id"]
    return {"ok": True, "jobId": job_id, "smoke": True}, 200


def verification_specs(payload, runtime):
    raw = payload.get("verification")
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise ValueError("freestyle verification must be an array")
    build_cmd = getattr(runtime, "build_cmd", None)
    assessment_commands = getattr(runtime, "assessment_commands", {}) or {}
    if not raw and (build_cmd or assessment_commands.get("build")):
        raw = [{"id": "build", "command": "build", "label": "Project build",
                "required": True}]
    specs = []
    for index, item in enumerate(raw):
        if isinstance(item, str):
            item = {"id": item, "command": item, "label": item, "required": True}
        if not isinstance(item, dict):
            raise ValueError(f"verification[{index}] must be a table")
        allowed = {"id", "command", "label", "required", "args", "stdin",
                   "timeout", "expect"}
        unknown = set(item) - allowed
        if unknown:
            raise ValueError(
                f"verification[{index}] has unknown keys: {', '.join(sorted(unknown))}")
        command_ref = str(item.get("command") or "").strip()
        spec_id = str(item.get("id") or command_ref).strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", spec_id):
            raise ValueError(f"verification[{index}] needs a stable id")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", command_ref):
            raise ValueError(f"verification[{index}] needs a registered command")
        args = item.get("args") or []
        if not isinstance(args, list) or any(not isinstance(arg, str) for arg in args):
            raise ValueError(f"verification[{index}].args must be a string array")
        timeout = item.get(
            "timeout", min(300, int(getattr(runtime, "build_timeout", 120) or 120)))
        if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 300:
            raise ValueError(f"verification[{index}].timeout must be 1 through 300")
        expect = item.get("expect") or {"exitCode": 0}
        if not isinstance(expect, dict):
            raise ValueError(f"verification[{index}].expect must be a table")
        expect_keys = {"exitCode", "exact", "raw", "regex", "json", "path",
                       "fileRegex"}
        unknown_expect = set(expect) - expect_keys
        if unknown_expect:
            raise ValueError(
                f"verification[{index}].expect has unknown keys: "
                + ", ".join(sorted(unknown_expect)))
        if ("exitCode" in expect
                and (not isinstance(expect["exitCode"], int)
                     or isinstance(expect["exitCode"], bool))):
            raise ValueError(
                f"verification[{index}].expect.exitCode must be an integer")
        for key in ("regex", "fileRegex"):
            if key in expect:
                try:
                    re.compile(str(expect[key]))
                except re.error as exc:
                    raise ValueError(
                        f"verification[{index}].expect.{key} is invalid: {exc}") from exc
        if "fileRegex" in expect and "path" not in expect:
            raise ValueError(
                f"verification[{index}].expect.fileRegex requires path")
        specs.append({
            "id": spec_id,
            "command": command_ref,
            "label": str(item.get("label") or spec_id).strip(),
            "required": item.get("required") is not False,
            "args": args,
            "stdin": str(item.get("stdin") or ""),
            "timeout": timeout,
            "expect": expect,
        })
    if len({item["id"] for item in specs}) != len(specs):
        raise ValueError("freestyle verification ids must be unique")
    return specs


def run_verification(runtime, snapshot, specs):
    sandbox = SandboxRunner()
    policy = policy_for_runtime(runtime)
    environment = environment_for_runtime(runtime)
    outcomes = []
    for spec in specs:
        command = runtime.assessment_command(
            spec["command"], snapshot.work, spec["args"])
        result = sandbox.run(
            command, cwd=snapshot.work, stdin=spec["stdin"],
            timeout=spec["timeout"], policy=policy, env=environment,
            home=snapshot.home)
        expectation_passed, problems = evaluate_expectation(
            spec["expect"], result, snapshot.work)
        completed = (result.get("exitCode") is not None
                     and not result.get("timedOut")
                     and not result.get("outputClipped"))
        exit_explicit = "exitCode" in spec["expect"]
        process_passed = completed and (exit_explicit or bool(result.get("passed")))
        outcomes.append({
            "id": spec["id"],
            "command": spec["command"],
            "label": spec["label"],
            "required": spec["required"],
            "passed": process_passed and expectation_passed,
            "exitCode": result.get("exitCode"),
            "timedOut": bool(result.get("timedOut")),
            "outputClipped": bool(result.get("outputClipped")),
            "output": str(result.get("output") or "")[-4_000:],
            "problems": problems,
        })
    return outcomes


def finalize_grade_result(result, rubric, verification):
    returned = {
        str(row.get("criterion") or "").strip(): row
        for row in (result.get("scores") or []) if isinstance(row, dict)
    }
    scores = []
    essential = []
    weighted = 0.0
    for item in rubric:
        criterion = str(item.get("criterion") or "").strip()
        row = returned.get(criterion) or {}
        try:
            score = max(0.0, min(10.0, float(row.get("score", 0))))
        except (TypeError, ValueError):
            score = 0.0
        score_value = int(score) if score.is_integer() else round(score, 1)
        scores.append({
            "criterion": criterion,
            "score": score_value,
            "comment": str(row.get("comment") or
                           "The grader returned no score for this criterion."),
            "essential": item.get("essential") is True,
        })
        weighted += score / 10 * float(item.get("weight") or 0)
        if item.get("essential") is True:
            minimum = float(item.get("minimumScore", 6))
            essential.append({
                "criterion": criterion,
                "score": score_value,
                "minimumScore": minimum,
                "passed": score >= minimum,
            })
    total = max(0, min(100, round(weighted)))
    model_grade = str(result.get("grade") or "").upper()
    grade = ("S" if total == 100 and model_grade == "S" else
             "A" if total >= 90 else "B" if total >= 80 else
             "C" if total >= 70 else "D" if total >= 60 else "F")
    essential_passed = all(item["passed"] for item in essential)
    verification_passed = all(
        item["passed"] for item in verification if item["required"])
    return {
        **result,
        "scores": scores,
        "total": total,
        "grade": grade,
        "essential": essential,
        "essentialPassed": essential_passed,
        "verification": verification,
        "verificationPassed": verification_passed,
        "scorePassed": total >= 60,
        "passed": total >= 60 and essential_passed and verification_passed,
    }


def run_grader(job_id, payload, jid, job_manager: JobManager, catalog, workspaces,
               ai: AiService):
    # jid comes from the request handler (query param) — the body has no tome key,
    # so resolving here again would misroute grading to the first installed tome
    rt = catalog.runtime(jid)
    project = workspaces.project_dir(jid)
    try:
        with create_snapshot(
                project,
                excluded_dirs=tuple(getattr(rt, "exclude_dirs", ()))) as snapshot:
            return _run_grader_snapshot(
                job_id, payload, jid, job_manager, catalog, workspaces, ai,
                rt, project, snapshot)
    except (SnapshotError, ValueError) as exc:
        job_manager.update(job_id, status="error", error=str(exc))
    except Exception as exc:
        job_manager.update(job_id, status="error", error=str(exc)[:500])


def _run_grader_snapshot(job_id, payload, jid, job_manager, catalog, workspaces,
                         ai, rt, project, snapshot):
    gdir = workspaces.grades_dir(jid)
    sid = payload.get("sectionId", "x")
    report = rt.collect_code_report(snapshot.source)
    files = report["files"]
    disclosure = grading_disclosure(
        payload, files, report, project,
        access=_snapshot_access(snapshot, project))
    if disclosure["remote"] and payload.get("consentToken") != disclosure["consentToken"]:
        job_manager.update(
            job_id, status="error",
            error="grading evidence or provider changed after consent; preview it again")
        return
    specs = verification_specs(payload, rt)
    verification = run_verification(rt, snapshot, specs)
    contract_hash = hashlib.sha256(json.dumps({
        "brief": payload.get("brief") or "",
        "rubric": payload.get("rubric") or [],
        "verification": specs,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    verification_hash = hashlib.sha256(json.dumps(
        verification, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    ws_hash = hashlib.sha256(
        f"{disclosure['workspaceHash']}:{contract_hash}:{verification_hash}".encode()
    ).hexdigest()
    last_path = os.path.join(gdir, f"last-{sid}.json")
    last = read_json(last_path, None)

    g = payload.get("grader") or {}
    kind, model, key = g.get("kind", "claude-cli"), g.get("model", ""), g.get("key", "")
    command = g.get("command", "")  # only used by the "other" (custom CLI) provider
    effort = str(g.get("effort") or "")
    grader_sig = f"{kind}/{model}"  # recorded with the judgement; NOT part of the cache key

    # identical code to the last judged submission → the same grade stands, even if the
    # selected grader changed since: re-judging unchanged work would only churn scores.
    # (the card labels these "the prior judgement stands", naming the model that judged.
    # to force a second opinion, edit the code or delete save/grades/last-<sid>.json)
    if last and last.get("hash") == ws_hash and last.get("result"):
        result = dict(last["result"])
        result["cached"] = True
        job_manager.update(job_id, status="done", result=result)
        return

    prompt = build_grade_prompt(
        payload, files, last, rt, snapshot.work, verification,
        disclosure["_accessFileHashes"])
    last_err = "no model attempted"

    def finish(result, model):
        result = finalize_grade_result(
            result, payload.get("rubric") or [], verification)
        result["model"] = model
        result["gradedAt"] = time.time()
        job_manager.update(job_id, status="done", result=result)
        atomic_write(os.path.join(gdir, f"{sid}-{int(time.time())}.json"),
                     json.dumps(result, indent=2))
        atomic_write(last_path, json.dumps({
            "hash": ws_hash,
            "grader": grader_sig,
            "fileHashes": disclosure["_accessFileHashes"],
            "result": result,
        }, indent=2))

    if kind == "claude-cli":
        attempts = [("claude-cli", m, "") for m in ([model] if model else GRADER_MODELS)]
    else:
        attempts = [(kind, model, key)]

    for kind, model, key in attempts:
        try:
            result = _grade_with_ai(ai, kind, model, prompt, snapshot.work,
                                    key=key, command=command, effort=effort)
            return finish(result, model)
        except ProviderConfigurationError as e:
            # a misconfiguration (e.g. a model that doesn't exist): surface it as-is
            # and STOP — silently grading with the local fallback would hide the mistake.
            job_manager.update(job_id, status="error", error=f"{kind}: {e}")
            return
        except subprocess.TimeoutExpired:
            last_err = f"{kind}/{model}: timed out after {GRADE_TIMEOUT}s"
        except Exception as e:
            last_err = f"{kind}/{model}: {str(e)[:500]}"

    # main grader failed — fall back to the local model (unless that IS what just failed)
    fb = payload.get("fallbackModel") or FALLBACK_GRADER
    if not (kind == "ollama" and model == fb):
        try:
            result = _grade_with_ai(ai, "ollama", fb, prompt, snapshot.work)
            return finish(result, fb + " (local fallback)")
        except Exception as e:
            last_err += f"; ollama {fb}: {str(e)[:300]}"
    job_manager.update(job_id, status="error", error=last_err)


def ask_oracle(question, context, model=None, language="code", kind="ollama", jid="",
               *, ai: AiService, catalog, key: str = "", effort: str = ""):
    """One question to the selected oracle backend — a local Ollama model (default)
    or any of the login CLIs (claude/agy/codex). Returns text or a friendly error."""
    prompt = (
        f"You are the ORACLE, a terse mentor spirit dwelling in a crystal ball inside an arcane {language} learning game. "
        f"The student is learning {language} by building the artifact described in the current tome; "
        "do not assume it is a CLI, GUI, game, or library unless the lesson context says so. Answer clearly and "
        "concisely (a few short paragraphs max, code snippets welcome). Do NOT write whole "
        "solutions to their assignments — explain concepts and point them the right way. You have read-only "
        "access to this tome and repository, may execute trusted repository Python, use /tmp, and search/fetch "
        "the web for current documentation; do not modify project files.\n"
        f"CURRENT LESSON CONTEXT: {context[:12000]}\n\nSTUDENT QUESTION (they are programming in {language}): {question[:2000]}"
    )
    model = model or (ORACLE_MODEL if kind == "ollama" else "")
    try:
        answer = ai.complete(kind, AiRequest(
            role="oracle", model=model, input=prompt, timeout=ORACLE_TIMEOUT,
            workspace=catalog.paths.tome(jid),
            allowed_tools=("read_repo_file", "list_repo_files", "run_repo_python"),
            web_allowed=True, effort=effort, api_key=key,
            trace={"tome": jid})).text.strip()
        return {"ok": True, "answer": answer or "(the oracle said nothing)", "model": model}
    except Exception as e:
        return {"ok": False,
                "answer": f"THE ORB IS DARK — the {kind} spirit did not answer ({str(e)[:300]})"}
