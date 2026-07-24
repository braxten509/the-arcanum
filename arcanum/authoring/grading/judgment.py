"""Prompt construction and isolated AI judgement for legacy Workings."""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets

from ...ai import AiRequest, AiService
from ...config import GRADE_TIMEOUT

MAX_PROMPT_FILE_CHARS = 20_000


def extract_json(text):
    """Pull the first JSON object out of possibly-noisy LLM text."""
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if match:
        text = match.group(1)
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in grader output")
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:index + 1])
    raise ValueError("unbalanced JSON in grader output")


def build_grade_prompt(payload, files, prev, runtime, project_dir,
                       verification, workspace_hashes=None):
    section = payload.get("sectionTitle", "")
    brief = payload.get("brief", "")
    rubric = payload.get("rubric", [])
    language = (
        payload.get("language") or getattr(runtime, "LANGUAGE", None)
        or runtime.NAME)
    persona = payload.get("persona") or "THE MAGISTER"
    student = payload.get("studentTerm") or "apprentice"
    scale = payload.get("gradeScale") or "S|A|B|C|D|F"

    parts = [
        f"You are the grader inside a {language} learning game. A student "
        f"learning {language} submitted their freestyle project for the "
        "section below. Grade it strictly against the rubric.",
        "You have recursive read-only access to the submitted project "
        "directory. Inspect supporting files there when needed. Do not assume "
        "access to any parent, sibling, tome, repository, or web content. "
        "Do not modify the project.",
        "",
        f"SECTION: {section}",
        f"ASSIGNMENT BRIEF: {brief}",
        "",
        "HOW TO READ THE BRIEF: it is written in the game's in-world, themed "
        "voice. Grade every requirement by its INTENT, not its literal flavor "
        "wording. A requirement is a hard, exact spec ONLY when it is stated "
        "concretely — an exact output string in quotes or code font, a named "
        "command/token, or an explicit word like 'exactly'. Where wording is "
        "atmospheric or vague, accept any reasonable implementation and do "
        "NOT dock points for not matching the flavor. Resolve ambiguity in "
        "the student's favor and lean on the rubric below.",
        "",
        "RUBRIC (score each criterion 0-10; weights sum to 100):",
    ]
    for row in rubric:
        essential = (
            f" [ESSENTIAL: requires {row.get('minimumScore', 6)}/10]"
            if row.get("essential") is True else "")
        parts.append(
            f"- [{row['weight']}%]{essential} {row['criterion']}: "
            f"{row['desc']}")
    parts.extend([
        "",
        f"CONVENTIONS & IDIOM: where a criterion concerns style, readability, "
        f"or craft, judge it against real-world {language} conventions — "
        "idiomatic naming and casing, brace/layout style, consistent "
        "formatting, and idiomatic use of the constructs this section teaches. "
        "Anchor these judgments in the language's official or de-facto "
        "community style guide (for example: Microsoft's C# Coding "
        "Conventions, PEP 8 for Python, gofmt for Go, the Ruby Style Guide) — "
        "recall that guide and apply it. Judge only conventions you are certain "
        "that guide states; never invent house rules or import another "
        "language's style. Name each convention breach concretely in that "
        "criterion's comment and state the pattern to follow, so the student "
        "learns the convention, not just the score. Expect only the conventions "
        "a learner at this section could know.",
        "",
        "HARNESS VERIFICATION (sandboxed; these results are authoritative):",
    ])
    if verification:
        for item in verification:
            status = "PASS" if item["passed"] else "FAIL"
            requirement = "required" if item["required"] else "advisory"
            parts.append(
                f"\n===== {status}: {item['label']} "
                f"({requirement}) =====\n{item['output'] or '(no output)'}")
            if item["problems"]:
                parts.append("Problems: " + "; ".join(item["problems"]))
    else:
        parts.append(
            "(no verification commands were declared by this Working/runtime)")
    parts.extend([
        "",
        "SELECTED TEXT EVIDENCE (included for convenience; inspect the "
        "read-only project as needed):",
    ])
    for relative, content in files:
        parts.append(
            f"\n===== FILE: {relative} =====\n"
            f"{content[:MAX_PROMPT_FILE_CHARS]}")
    if prev and prev.get("result", {}).get("scores"):
        parts.append(
            "\nPREVIOUS SUBMISSION: this student already had this project "
            "graded. Previous scores:")
        for score in prev["result"]["scores"]:
            parts.append(
                f"- {score.get('criterion')}: {score.get('score')}/10 — "
                f"{score.get('comment', '')}")
        old_files = prev.get("files") or {}
        old_hashes = prev.get("fileHashes") or {
            name: hashlib.sha256(content.encode()).hexdigest()
            for name, content in old_files.items()
        }
        current_hashes = workspace_hashes or {
            name: hashlib.sha256(content.encode()).hexdigest()
            for name, content in files
        }
        changed = sorted(
            name for name in set(old_hashes) | set(current_hashes)
            if old_hashes.get(name) != current_hashes.get(name))
        parts.append("\nFILES changed since the previously graded submission:")
        parts.append(
            "\n".join(f"- {name}" for name in changed) or "(no changes)")
        parts.append(
            "\nSCORE STABILITY RULE (mandatory): a criterion's score MUST be "
            "exactly the previous score unless a changed file above contains "
            "work relevant to that criterion. Never raise or lower a criterion "
            "the changed files do not touch. Only re-judge what actually changed.")
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


def grade_with_ai(ai: AiService, provider: str, model: str, prompt: str,
                  project_root: str, *, key: str = "", command: str = "",
                  effort: str = "") -> dict:
    """Run one grader with read-only access to the captured workspace."""
    build_id = "grade-" + secrets.token_hex(10)
    from ...platform import agent_scratch
    scratch = agent_scratch.prepare(build_id)
    try:
        response = ai.complete(provider, AiRequest(
            role="legacy-working-grader", model=model, input=prompt,
            timeout=GRADE_TIMEOUT, workspace=project_root,
            allowed_tools=("read_workspace_file", "list_workspace_files"),
            effort=effort, api_key=key, custom_command=command,
            response_schema={
                "scores": "array", "total": "number", "grade": "string",
            },
            trace={"legacy": True},
            readonly_paths=(project_root,),
            permission_paths={
                "system_read": [
                    path for path in (
                        "/usr", "/bin", "/lib", "/lib64", "/usr/local",
                        "/etc", "/opt", "/proc",
                    ) if os.path.exists(path)
                ],
                "system_both": [scratch, "/dev"],
                "read": [project_root],
                "both": [],
                "execute": [],
                "seal_repo": False,
            },
            state_scope={
                "build_id": build_id,
                "role": "grader",
                "phase": 0,
                "section": "",
            }))
    finally:
        agent_scratch.remove(build_id)
    return extract_json(response.text)
