"""Legacy freestyle grading and Oracle role services."""
import difflib
import hashlib
import json
import os
import re
import subprocess
import time

from runtimes.common import atomic_write

from ..config import GRADE_TIMEOUT, GRADER_MODELS, ORACLE_TIMEOUT, read_json
from ..jobs import JobManager
from ..ai import AiRequest, AiService
from ..ai.contracts.errors import ProviderConfigurationError

FALLBACK_GRADER = "qwen2.5:14b"  # strongest installed Ollama model; overridable per-request from settings
ORACLE_MODEL = "llama3.1:8b"


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


def extract_json(text):
    """Pull the first JSON object out of possibly-noisy LLM text."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in grader output")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("unbalanced JSON in grader output")


def build_grade_prompt(payload, files, prev, rt, pdir):
    section = payload.get("sectionTitle", "")
    brief = payload.get("brief", "")
    rubric = payload.get("rubric", [])
    language = payload.get("language") or getattr(rt, "LANGUAGE", None) or rt.NAME
    persona = payload.get("persona") or "THE MAGISTER"
    student = payload.get("studentTerm") or "apprentice"
    scale = payload.get("gradeScale") or "S|A|B|C|D|F"
    build_label = payload.get("buildLabel") or f"{rt.NAME} build"  # no per-language branch; the runtime names itself
    build_out = rt.try_build(pdir)

    parts = [
        f"You are the grader inside a {language} learning game. A student learning {language} submitted their "
        "freestyle project for the section below. Grade it strictly against the rubric.",
        "You have read-only access to this tome and the surrounding repository. You may read supporting "
        "course/runtime files, execute trusted repository Python for verification, use /tmp, and search/fetch "
        "the web for current official conventions. Do not modify project files.",
        "",
        f"SECTION: {section}",
        f"ASSIGNMENT BRIEF: {brief}",
        "",
        "HOW TO READ THE BRIEF: it is written in the game's in-world, themed voice. Grade every "
        "requirement by its INTENT, not its literal flavor wording. A requirement is a hard, exact "
        "spec ONLY when it is stated concretely — an exact output string in quotes or code font, a "
        "named command/token, or an explicit word like 'exactly'. Where wording is atmospheric or "
        "vague, accept any reasonable implementation and do NOT dock points for not matching the "
        "flavor. Resolve ambiguity in the student's favor and lean on the rubric below.",
        "",
    ]
    parts.append("RUBRIC (score each criterion 0-10; weights sum to 100):")
    for r in rubric:
        parts.append(f"- [{r['weight']}%] {r['criterion']}: {r['desc']}")
    parts.append("")
    parts.append(
        f"CONVENTIONS & IDIOM: where a criterion concerns style, readability, or craft, judge it against "
        f"real-world {language} conventions — idiomatic naming and casing, brace/layout style, consistent "
        "formatting, and idiomatic use of the constructs this section teaches. Anchor these judgments in "
        f"the language's official or de-facto community style guide (for example: Microsoft's C# Coding "
        "Conventions, PEP 8 for Python, gofmt for Go, the Ruby Style Guide) — recall that guide and apply "
        "it. Judge only conventions you are certain that guide states; never invent house rules or import "
        "another language's style. Name each convention breach concretely in that criterion's comment and "
        "state the pattern to follow, so the student learns the convention, not just the score. Expect "
        "only the conventions a learner at this section could know.")
    parts.append("")
    parts.append(f"COMPILER OUTPUT of `{build_label}`:\n{build_out[:4000]}")
    parts.append("")
    parts.append("STUDENT CODE (entire workspace):")
    for rel, content in files:
        parts.append(f"\n===== FILE: {rel} =====\n{content[:20000]}")
    if prev and prev.get("result", {}).get("scores"):
        parts.append("\nPREVIOUS SUBMISSION: this student already had this project graded. Previous scores:")
        for s in prev["result"]["scores"]:
            parts.append(f"- {s.get('criterion')}: {s.get('score')}/10 — {s.get('comment', '')}")
        old, cur = prev.get("files", {}), dict(files)
        diff = []
        for name in sorted(set(old) | set(cur)):
            if old.get(name, "") != cur.get(name, ""):
                diff += difflib.unified_diff(old.get(name, "").splitlines(), cur.get(name, "").splitlines(),
                                             fromfile="previous/" + name, tofile="current/" + name, lineterm="")
        parts.append("\nDIFF since the previously graded submission:")
        parts.append("\n".join(diff)[:20000] or "(no changes)")
        parts.append(
            "\nSCORE STABILITY RULE (mandatory): a criterion's score MUST be exactly the previous score "
            "unless the diff above changes code relevant to that criterion. Never raise or lower a criterion "
            "the diff does not touch. Only re-judge what actually changed.")
    parts.append("""
Respond with ONLY a JSON object, no prose before or after, exactly this shape:
{
  "scores": [{"criterion": "<name>", "score": <0-10>, "comment": "<1-2 sentences, direct, specific>"}],
  "total": <0-100 weighted total>,
  "grade": "<%SCALE%>",  // S=flawless+elegant, A>=90, B>=80, C>=70, D>=60, F<60
  "feedback": "<3-6 sentences of overall feedback in the voice of a gruff but fair ops mentor codenamed %PERSONA%. Address the student as '%STUDENT%'. Be specific about what to improve. No spoiler solutions.>",
  "bestLine": "<quote the single best line/idea in their code, or empty string>"
}
Grade honestly. A beginner who met every goal with working, readable code deserves an A.
Reserve S for code that would pass review from a senior %LANG% dev. Do not inflate.
Grade code and observable behavior ONLY. Do NOT deduct for tone, phrasing, verbosity, or stylistic
wording of the program's output text (e.g. a message feeling "redundant" or off-tone versus the brief) —
if the required output elements are present and correct, that aspect earns full marks. Deduct only for
missing or broken functionality, bugs, or code-quality issues the rubric explicitly names."""
                 .replace("%SCALE%", scale).replace("%PERSONA%", persona)
                 .replace("%STUDENT%", student).replace("%LANG%", language))
    return "\n".join(parts)


def _grade_with_ai(ai: AiService, provider: str, model: str, prompt: str,
                   tome_root: str, *, key: str = "", command: str = "",
                   effort: str = "") -> dict:
    response = ai.complete(provider, AiRequest(
        role="legacy-working-grader", model=model, input=prompt,
        timeout=GRADE_TIMEOUT, workspace=tome_root,
        allowed_tools=("read_repo_file", "list_repo_files", "run_repo_python"),
        web_allowed=True, effort=effort, api_key=key, custom_command=command,
        response_schema={"scores": "array", "total": "number", "grade": "string"},
        trace={"legacy": True}))
    return extract_json(response.text)


def run_grader(job_id, payload, jid, job_manager: JobManager, catalog, workspaces,
               ai: AiService):
    # jid comes from the request handler (query param) — the body has no tome key,
    # so resolving here again would misroute grading to the first installed tome
    rt = catalog.runtime(jid)
    pdir = workspaces.project_dir(jid)
    gdir = workspaces.grades_dir(jid)
    sid = payload.get("sectionId", "x")
    files = rt.collect_code(pdir)
    ws_hash = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
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

    prompt = build_grade_prompt(payload, files, last, rt, pdir)
    tome_root = catalog.paths.tome(jid)
    last_err = "no model attempted"

    def finish(result, model):
        result["model"] = model
        result["gradedAt"] = time.time()
        job_manager.update(job_id, status="done", result=result)
        atomic_write(os.path.join(gdir, f"{sid}-{int(time.time())}.json"),
                     json.dumps(result, indent=2))
        atomic_write(last_path, json.dumps(
            {"hash": ws_hash, "grader": grader_sig, "files": dict(files), "result": result}, indent=2))

    if kind == "claude-cli":
        attempts = [("claude-cli", m, "") for m in ([model] if model else GRADER_MODELS)]
    else:
        attempts = [(kind, model, key)]

    for kind, model, key in attempts:
        try:
            result = _grade_with_ai(ai, kind, model, prompt, tome_root,
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
            result = _grade_with_ai(ai, "ollama", fb, prompt, tome_root)
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
