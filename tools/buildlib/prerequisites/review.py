"""Mandatory, cached first-use completeness audit for beginner courses."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request

from .. import BUILD_DIR, REPO, VALIDATOR_FAILURE_DIR
from ..status_log import emit_status_line
from ..runtime.agent_runtime import scoped_runner_command
from ..runtime.events import assistant_text, session_id_from_line, usage_from_line
from ..course.alignment import actual_lesson_id
from ..course_map import load_course_map
from .prompt import (DYNAMIC_MARKER,
                                  format_repair_prompt as _format_repair_prompt,
                                  prerequisite_prompt as _prompt,
                                  result_schema as _result_schema)
from . import records as _records
from .result import (FINDING_KEYS, RESULT_KEYS,
                     actionable_failure as _actionable_failure,
                     extract_json as _extract_json,
                     validate as _validate,
                     validate_detailed as _validate_detailed)
from ..workflow.prompts import START_PACING
from ..runtime.runners import author_runner
from arcanum.tomes import resolve_working_tid


MAX_SECTION_PACKET_CHARS = 200_000
AUDIT_CONTRACT_VERSION = 5
RESPONSES_URL = "https://api.openai.com/v1/responses"
API_TIMEOUT_SECONDS = 900
API_MAX_OUTPUT_TOKENS = 2_500


def result_path(build_id, sid):
    return os.path.join(BUILD_DIR, f"{build_id}.prerequisite-reviews", f"{sid}.json")


def calls_path(build_id):
    return _records.calls_path(BUILD_DIR, build_id)


def validator_failure_dir(build_id):
    return _records.failure_dir(VALIDATOR_FAILURE_DIR, build_id)


def review_call_count(build_id):
    return _records.review_call_count(BUILD_DIR, build_id)


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


def _write(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temp, path)


def _configuration(build_id):
    launch = _read(os.path.join(BUILD_DIR, f"{build_id}.launch.json"), {}) or {}
    gate = launch.get("gate") or {}
    try:
        start = int(gate.get("prior_level") or 0)
    except (TypeError, ValueError):
        start = 0
    bindery = launch.get("bindery") or {}
    validator = launch.get("validator") or bindery.get("validator") or {}
    return start, validator, str(gate.get("prior_knowledge") or "")


def _context(build_id):
    plan = os.path.join(BUILD_DIR, f"{build_id}.plan.md")
    try:
        with open(plan, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        text = ""
    return resolve_working_tid(build_id, text)


def _node_file(tid, node):
    sid = node["id"].split(".", 1)[0]
    root = os.path.join(REPO, "tomes", tid, "sections", sid)
    if node["kind"] == "working":
        return os.path.join(root, "freestyle.toml")
    lesson = actual_lesson_id(node["id"]).split("-", 1)[1]
    return os.path.join(root, "lessons", lesson + ".toml")


def section_evidence_packet(build_id, section):
    """Build the bounded, citable packet for one mandatory section audit."""
    tid = _context(build_id)
    course = load_course_map(build_id)
    sources, source_blocks = [], []
    for node in section.get("nodes") or []:
        path = _node_file(tid, node)
        relative = os.path.relpath(path, REPO).replace(os.sep, "/")
        try:
            with open(path, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
        except OSError as exc:
            raise ValueError(
                f"validator evidence file is unavailable: {relative}: {exc}") from exc
        sources.append({"path": relative, "node": node["id"]})
        numbered = "\n".join(
            f"{index:04d}: {line}" for index, line in enumerate(lines, 1))
        source_blocks.append(
            f"===== CITABLE SOURCE {node['id']} | {relative} =====\n{numbered}")
    performance_ids = {node.get("id") for node in section.get("nodes") or []}
    performances = [item for item in (course.get("languageMastery") or {}).get(
        "performances", []) if item.get("workingId") in performance_ids]
    mechanism_contract = course.get("mechanismContract")
    section_order = {item.get("id"): index
                     for index, item in enumerate(course.get("sections") or [])}
    current_index = section_order.get(section.get("id"), -1)
    records = list((mechanism_contract or {}).get("mechanisms") or [])
    available = [item for item in records if section_order.get(
        str(item.get("owner") or "").split(".", 1)[0], 999) <= current_index]
    future = [[item.get("id"), item.get("owner")] for item in records
              if item not in available]
    if isinstance(mechanism_contract, dict):
        mechanism_contract = {**mechanism_contract, "mechanisms": available}
    packet = json.dumps({
        "mapVersion": 1,
        "section": section,
        "languageMastery": ({**(course.get("languageMastery") or {}),
                              "performances": performances}
                             if course.get("languageMastery") else None),
        "mechanismContract": mechanism_contract,
        "sources": sources,
    }, ensure_ascii=False, sort_keys=True, indent=2)
    packet += ("\n\n===== SEALED FUTURE MECHANISM INDEX [id, owner] =====\n"
               + json.dumps(future, ensure_ascii=False, separators=(",", ":")))
    packet += "\n\n" + "\n\n".join(source_blocks)
    if len(packet) > MAX_SECTION_PACKET_CHARS:
        raise ValueError(
            f"validator evidence for {section.get('id')} is {len(packet)} characters; "
            f"the deterministic section budget is {MAX_SECTION_PACKET_CHARS}")
    return packet, sources


def _cli_adapter(prompt, validator):
    spec = f"{validator['kind']}:{validator['model']}" + (
        f"@{validator['effort']}" if validator.get("effort") else "")
    display, command, input_mode = author_runner(spec, "--validator-ai")
    kind = str(validator.get("kind") or "")
    if kind == "codex-cli":
        position = command.index("-") if "-" in command else len(command)
        command[position:position] = ["--json"]
    elif kind == "claude-cli":
        command += ["--output-format", "stream-json", "--verbose"]
    elif kind == "opencode-cli":
        position = command.index("run") + 1
        command[position:position] = ["--format", "json"]
    if input_mode == "arg":
        command = [*command, prompt]
    wrapped = scoped_runner_command(display, command, REPO, [], REPO)
    process = subprocess.run(
        wrapped, cwd=REPO, input=prompt if input_mode == "stdin" else None,
        capture_output=True, text=True, timeout=900)
    if process.returncode:
        raise RuntimeError(f"validator process exited {process.returncode}")
    answers, usage, session_id = [], None, ""
    for line in process.stdout.splitlines():
        answer = assistant_text(line)
        if answer:
            answers.append(answer)
        observed = usage_from_line(line)
        if observed:
            usage = observed
        if not session_id:
            session_id = session_id_from_line(line)
    return ("\n".join(answers) if answers else process.stdout), {
        "transport": "cli", "kind": kind, "model": validator["model"],
        "effort": validator.get("effort", ""), "usage": usage,
        "sessionId": session_id,
    }


def _response_text(response):
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    blocks = []
    for item in response.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                blocks.append(content["text"])
            elif content.get("type") == "refusal":
                raise RuntimeError("Validator AI refused the bounded prerequisite audit")
    if not blocks:
        raise RuntimeError("Responses API returned no structured output text")
    return "\n".join(blocks)


def _usage(response):
    usage = response.get("usage") or {}
    inputs = usage.get("input_tokens_details") or {}
    outputs = usage.get("output_tokens_details") or {}
    input_tokens = int(usage.get("input_tokens") or 0)
    cached_tokens = int(inputs.get("cached_tokens") or 0)
    cache_write_tokens = int(inputs.get("cache_write_tokens") or 0)
    return {
        "inputTokens": input_tokens,
        "freshInputTokens": max(0, input_tokens - cached_tokens - cache_write_tokens),
        "cachedInputTokens": cached_tokens,
        "cacheWriteTokens": cache_write_tokens,
        "outputTokens": int(usage.get("output_tokens") or 0),
        "reasoningTokens": int(outputs.get("reasoning_tokens") or 0),
        "totalTokens": int(usage.get("total_tokens") or 0),
    }


def _openai_key():
    key = str(os.environ.get("OPENAI_API_KEY") or "").strip()
    if key:
        return key
    try:
        from arcanum.config import read_settings
        return str((((read_settings().get("ai") or {}).get("keys") or {}).get("openai"))
                   or "").strip()
    except (OSError, TypeError, ValueError):
        return ""


def _api_adapter(prompt, validator, key=None):
    key = str(key or _openai_key()).strip()
    if not key:
        raise RuntimeError("no OpenAI API key is configured in Settings or OPENAI_API_KEY")
    static, marker, dynamic = prompt.partition(DYNAMIC_MARKER)
    if not marker:
        raise RuntimeError("Validator AI prompt is missing its stable/dynamic cache boundary")
    effort = str(validator.get("effort") or "medium")
    if effort not in ("none", "minimal", "low", "medium", "high", "xhigh"):
        effort = "medium"
    payload = {
        "model": validator["model"],
        "reasoning": {"effort": effort},
        "input": [
            {"role": "developer", "content": [{
                "type": "input_text", "text": static.strip(),
                "prompt_cache_breakpoint": {"mode": "explicit"},
            }]},
            {"role": "user", "content": [{"type": "input_text", "text": dynamic.strip()}]},
        ],
        "text": {"verbosity": "low", "format": {
            "type": "json_schema", "name": "arcanum_prerequisite_audit",
            "strict": True, "schema": _result_schema(),
        }},
        "max_output_tokens": API_MAX_OUTPUT_TOKENS,
        "prompt_cache_key": f"arcanum-prerequisite-v{AUDIT_CONTRACT_VERSION}",
        "prompt_cache_options": {"mode": "explicit"},
        "store": False,
    }
    request = urllib.request.Request(
        RESPONSES_URL, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[-1200:]
        raise RuntimeError(f"Responses API HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Responses API request failed: {exc}") from exc
    return _response_text(value), {
        "transport": "responses-api", "kind": "openai-api",
        "model": validator["model"], "effort": effort, "usage": _usage(value),
        "responseId": str(value.get("id") or ""),
    }


def _default_adapter(prompt, validator):
    # Codex login remains the zero-API-cost fallback. When an API key is present,
    # the read-only Validator AI uses one no-tools Structured Output request instead.
    key = _openai_key()
    if (validator.get("kind") == "codex-cli" and key
            and str(validator.get("model") or "").startswith("gpt-")):
        return _api_adapter(prompt, validator, key)
    return _cli_adapter(prompt, validator)


def _append_call(build_id, sid, packet, result, meta, *, raw=None, stage="audit",
                 escalated_from="", malformed=False):
    return _records.append_ai_call(
        BUILD_DIR, VALIDATOR_FAILURE_DIR, build_id, sid, packet, result, meta,
        raw=raw, stage=stage, escalated_from=escalated_from, malformed=malformed,
        contract=AUDIT_CONTRACT_VERSION)


def _append_infrastructure_failure(build_id, sid, packet, validator, error, *,
                                   stage="audit", escalated_from=""):
    return _records.append_ai_infrastructure_failure(
        BUILD_DIR, VALIDATOR_FAILURE_DIR, build_id, sid, packet, validator, error,
        stage=stage, contract=AUDIT_CONTRACT_VERSION, escalated_from=escalated_from)


def review_usage_summary(build_id):
    return _records.review_usage_summary(BUILD_DIR, build_id)


def _invoke(prompt, validator, adapter):
    if adapter:
        return adapter(prompt, validator), {
            "transport": "test-adapter", "model": validator.get("model", ""), "usage": None}
    return _default_adapter(prompt, validator)


def review_prerequisites(build_id, sid, *, adapter=None):
    start, validator, prior = _configuration(build_id)
    if start > 3:
        return {"status": "not-required", "reasons": [], "missingMechanisms": [],
                "cached": False}
    if start < 1:
        raise RuntimeError("prerequisite audit cannot read the sealed starting level")
    if not validator.get("kind") or not validator.get("model"):
        raise RuntimeError("mandatory section audit has no Validator AI configuration")
    course = load_course_map(build_id)
    known_mechanisms = {
        item.get("id") for item in (course.get("mechanismContract") or {}).get(
            "mechanisms", []) if isinstance(item, dict) and item.get("id")}
    section = next(item for item in course["sections"] if item["id"] == sid)
    packet, sources = section_evidence_packet(build_id, section)
    packet += "\n\n===== EXHAUSTIVE PRIOR KNOWLEDGE =====\n" + prior
    packet += (f"\n\n===== LESSON PACING =====\nStart {start}/3 — "
               f"{START_PACING[start][0]}: {START_PACING[start][1]}")
    fingerprint_input = json.dumps({
        "contract": AUDIT_CONTRACT_VERSION, "packet": packet,
        "validator": {key: validator.get(key) for key in ("kind", "model", "effort")},
    }, ensure_ascii=False, sort_keys=True)
    fingerprint = hashlib.sha256(fingerprint_input.encode("utf-8")).hexdigest()
    cached = _read(result_path(build_id, sid), {}) or {}
    if cached.get("fingerprint") == fingerprint and isinstance(cached.get("result"), dict):
        return {**cached["result"], "cached": True}
    prompt = _prompt(packet, sid, sources, prior, start)
    audit_label = (f"prerequisite completeness {sid} › "
                   f"{validator.get('kind')} {validator.get('model')}")
    emit_status_line(f"AI VALIDATOR CALL START [{time.time():.3f}] › {audit_label}",
                     build_id, build_dir=BUILD_DIR)
    try:
        raw, meta = _invoke(prompt, validator, adapter)
    except Exception as exc:
        _append_infrastructure_failure(build_id, sid, packet, validator, exc)
        emit_status_line(f"AI VALIDATOR CALL FAILED [{time.time():.3f}] › {audit_label}",
                         build_id, build_dir=BUILD_DIR)
        raise RuntimeError(f"section Validator AI infrastructure failed: {exc}") from exc
    result, errors = _validate_detailed(raw, sources, sid, known_mechanisms)
    malformed = bool(errors)
    model = str(validator.get("model") or "")
    _append_call(build_id, sid, packet, result, meta, raw=raw, malformed=malformed)
    actionable = _actionable_failure(raw, result, sources)
    if malformed and actionable is None:
        try:
            repaired_raw, repair_meta = _invoke(
                _format_repair_prompt(prompt, raw, errors, known_mechanisms),
                validator, adapter)
        except Exception as exc:
            _append_infrastructure_failure(
                build_id, sid, packet, validator, exc, stage="format-repair")
        else:
            result, errors = _validate_detailed(
                repaired_raw, sources, sid, known_mechanisms)
            malformed = bool(errors)
            _append_call(build_id, sid, packet, result, repair_meta, raw=repaired_raw,
                         stage="format-repair", malformed=malformed)
            actionable = _actionable_failure(repaired_raw, result, sources)
    if actionable is not None:
        result, malformed = actionable, False
    should_escalate = ("luna" in model.lower()
                       and (malformed or result["status"] == "UNCERTAIN"))
    final_label = audit_label
    if should_escalate:
        terra = {**validator, "model": re.sub("luna", "terra", model,
                                               flags=re.IGNORECASE),
                 "effort": validator.get("effort") or "medium"}
        why = "UNCERTAIN" if result["status"] == "UNCERTAIN" else "unusable output"
        final_label = (f"prerequisite completeness {sid} › {terra.get('kind')} "
                       f"{terra.get('model')} (after Luna {why})")
        try:
            raw, terra_meta = _invoke(prompt, terra, adapter)
        except Exception as exc:
            _append_infrastructure_failure(
                build_id, sid, packet, terra, exc, stage="escalation",
                escalated_from=model)
            emit_status_line(
                f"AI VALIDATOR CALL FAILED [{time.time():.3f}] › {final_label}", build_id,
                build_dir=BUILD_DIR)
            raise RuntimeError(f"section Validator AI escalation failed: {exc}") from exc
        result, _errors = _validate_detailed(raw, sources, sid, known_mechanisms)
        _append_call(build_id, sid, packet, result, terra_meta, raw=raw,
                     stage="escalation", escalated_from=model)
    emit_status_line(
        f"AI VALIDATOR CALL COMPLETE [{time.time():.3f}] ({result['status']}) › "
        f"{final_label}", build_id, build_dir=BUILD_DIR)
    _write(result_path(build_id, sid), {"fingerprint": fingerprint, "result": result})
    return {**result, "cached": False}
