"""Mandatory, cached teaching-quality and first-use completeness audit."""
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
from arcanum.platform.agent_commands import scoped_runner_command
from arcanum.jobs.stall import StalledProcess, run_watched
from ..runtime.events import assistant_text, session_id_from_line, usage_from_line
from ..course.alignment import actual_lesson_id
from ..course_map import load_course_map
from ..validator_policy import resolve_validator_output
from .prompt import (DYNAMIC_MARKER,
                                  pacing_contract,
                                  prerequisite_prompt as _prompt,
                                  result_schema as _result_schema,
                                  unusable_response_retry_prompt as _recovery_retry_prompt)
from . import records as _records
from .result import (evidence_supports_verdict,
                     validate_detailed as _validate_detailed)
from ..runtime.runners import author_runner
from arcanum.catalog.build_ids import resolve_working_id


MAX_SECTION_PACKET_CHARS = 200_000
AUDIT_CONTRACT_VERSION = 8
RESPONSES_URL = "https://api.openai.com/v1/responses"
API_TIMEOUT_SECONDS = 900
API_MAX_OUTPUT_TOKENS = 2_500
# Idle means no CPU anywhere in the tree and no established provider connection, so this
# is not a patience budget: a thinking model and a running tool both keep the clock at 0.
STALL_SECONDS = float(os.environ.get("ARCANUM_STALL_SECONDS", "10"))


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
    try:
        depth = int(gate.get("depth") or 0)
    except (TypeError, ValueError):
        depth = 0
    try:
        mastery = int(gate.get("mastery") or 0)
    except (TypeError, ValueError):
        mastery = 0
    bindery = launch.get("bindery") or {}
    validator = launch.get("validator") or bindery.get("validator") or {}
    return start, validator, str(gate.get("prior_knowledge") or ""), depth, mastery


def _context(build_id):
    plan = os.path.join(BUILD_DIR, f"{build_id}.plan.md")
    try:
        with open(plan, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        text = ""
    return resolve_working_id(build_id, text, os.path.join(REPO, "tomes"))


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
        sources.append({"path": relative, "node": node["id"],
                        "lineCount": max(1, len(lines))})
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
    returncode, stdout, stalled = run_watched(
        wrapped, cwd=REPO, stdin_text=prompt if input_mode == "stdin" else None,
        seconds=STALL_SECONDS, timeout=900)
    # A stall that arrives after the verdict is the CLI failing to exit, not failing to
    # answer. Keep the output and let the usual malformed-result path judge it; only an
    # empty stall is an infrastructure failure.
    if stalled and not stdout.strip():
        raise StalledProcess(STALL_SECONDS)
    if returncode and not stalled:
        raise RuntimeError(f"validator process exited {returncode}")
    answers, usage, session_id = [], None, ""
    for line in stdout.splitlines():
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
                raise RuntimeError("Validator AI refused the bounded quality audit")
    if not blocks:
        raise RuntimeError("Responses API returned no output text")
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


def _api_adapter(prompt, validator, key=None, *, schema=None,
                 schema_name="arcanum_section_quality_audit",
                 cache_key=None, max_output_tokens=API_MAX_OUTPUT_TOKENS,
                 plain_text=False):
    key = str(key or _openai_key()).strip()
    if not key:
        raise RuntimeError("no OpenAI API key is configured in Settings or OPENAI_API_KEY")
    static, marker, dynamic = prompt.partition(DYNAMIC_MARKER)
    if not marker:
        raise RuntimeError("Validator AI prompt is missing its stable/dynamic cache boundary")
    effort = str(validator.get("effort") or "medium")
    if effort not in ("none", "minimal", "low", "medium", "high", "xhigh"):
        effort = "medium"
    text_config = {"verbosity": "low"}
    if not plain_text:
        text_config["format"] = {
            "type": "json_schema", "name": schema_name,
            "strict": True, "schema": schema or _result_schema(),
        }
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
        "text": text_config,
        "max_output_tokens": int(max_output_tokens),
        "prompt_cache_key": (cache_key
                             or f"arcanum-section-quality-v{AUDIT_CONTRACT_VERSION}"),
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


def invoke_validator(prompt, validator, *, adapter=None, schema=None,
                     schema_name="arcanum_section_quality_audit", cache_key=None,
                     max_output_tokens=API_MAX_OUTPUT_TOKENS, plain_text=False):
    """Run one configured, read-only Validator AI call with an optional strict schema."""
    if adapter:
        return adapter(prompt, validator), {
            "transport": "test-adapter", "model": validator.get("model", ""), "usage": None}
    # Codex login remains the zero-API-cost fallback. When an API key is present,
    # the read-only Validator AI uses one no-tools Structured Output request instead.
    key = _openai_key()
    if (validator.get("kind") == "codex-cli" and key
            and str(validator.get("model") or "").startswith("gpt-")):
        return _api_adapter(
            prompt, validator, key, schema=schema, schema_name=schema_name,
            cache_key=cache_key, max_output_tokens=max_output_tokens,
            plain_text=plain_text)
    return _cli_adapter(prompt, validator)


def _default_adapter(prompt, validator):
    return invoke_validator(prompt, validator)


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
    return invoke_validator(prompt, validator, adapter=adapter)


def _classify_output(raw, sources, sid, known_mechanisms):
    parsed, errors = _validate_detailed(raw, sources, sid, known_mechanisms)
    output = resolve_validator_output(
        raw, parsed, errors,
        lambda value, outcome: evidence_supports_verdict(value, outcome, sources))
    return parsed, errors, output


def review_prerequisites(build_id, sid, *, adapter=None):
    start, validator, prior, depth, mastery = _configuration(build_id)
    if start < 1:
        raise RuntimeError("section-quality audit cannot read the sealed starting level")
    if not validator.get("kind") or not validator.get("model"):
        raise RuntimeError("mandatory section audit has no Validator AI configuration")
    course = load_course_map(build_id)
    known_mechanisms = {
        item.get("id") for item in (course.get("mechanismContract") or {}).get(
            "mechanisms", []) if isinstance(item, dict) and item.get("id")}
    section = next(item for item in course["sections"] if item["id"] == sid)
    packet, sources = section_evidence_packet(build_id, section)
    packet += "\n\n===== OPTIONAL PRIOR-KNOWLEDGE DETAILS =====\n" + (prior or "Not specified")
    pacing_title, pacing_summary = pacing_contract(start)
    packet += (f"\n\n===== LESSON PACING =====\nStart {start}/10 — "
               f"{pacing_title}: {pacing_summary}")
    packet += (f"\n\n===== QUALITY CALIBRATION =====\nLesson depth {depth or 'unrecorded'}/10; "
               f"language mastery {mastery or 'unrecorded'}/5")
    fingerprint_input = json.dumps({
        "contract": AUDIT_CONTRACT_VERSION, "packet": packet,
        "validator": {key: validator.get(key) for key in ("kind", "model", "effort")},
    }, ensure_ascii=False, sort_keys=True)
    fingerprint = hashlib.sha256(fingerprint_input.encode("utf-8")).hexdigest()
    cached = _read(result_path(build_id, sid), {}) or {}
    if cached.get("fingerprint") == fingerprint and isinstance(cached.get("result"), dict):
        return {**cached["result"], "cached": True}
    prompt = _prompt(packet, sid, sources, prior, start, depth, mastery)
    audit_label = (f"section quality {sid} › "
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
    parsed, errors, output = _classify_output(raw, sources, sid, known_mechanisms)
    model = str(validator.get("model") or "")
    _append_call(
        build_id, sid, packet,
        output.result if output.recovered_verdict else parsed,
        meta, raw=raw, malformed=output.malformed)
    emit_status_line(
        f"AI VALIDATOR CALL COMPLETE [{time.time():.3f}] "
        f"({output.result['status']}) › {audit_label}",
        build_id, build_dir=BUILD_DIR)
    if output.unusable:
        retry_label = (f"section quality {sid} recovery-retry › "
                       f"{validator.get('kind')} {validator.get('model')}")
        emit_status_line(f"AI VALIDATOR CALL START [{time.time():.3f}] › {retry_label}",
                         build_id, build_dir=BUILD_DIR)
        try:
            repaired_raw, repair_meta = _invoke(
                _recovery_retry_prompt(prompt, raw, errors, known_mechanisms),
                validator, adapter)
        except Exception as exc:
            _append_infrastructure_failure(
                build_id, sid, packet, validator, exc, stage="recovery-retry")
            emit_status_line(
                f"AI VALIDATOR CALL FAILED [{time.time():.3f}] › {retry_label}",
                build_id, build_dir=BUILD_DIR)
        else:
            parsed, errors, output = _classify_output(
                repaired_raw, sources, sid, known_mechanisms)
            _append_call(
                build_id, sid, packet,
                output.result if output.recovered_verdict else parsed,
                repair_meta, raw=repaired_raw,
                stage="recovery-retry", malformed=output.malformed)
            emit_status_line(
                f"AI VALIDATOR CALL COMPLETE [{time.time():.3f}] "
                f"({output.result['status']}) › {retry_label}",
                build_id, build_dir=BUILD_DIR)
    result = output.result
    should_escalate = ("luna" in model.lower()
                       and (output.unusable or result["status"] == "UNCERTAIN"))
    if should_escalate:
        terra = {**validator, "model": re.sub("luna", "terra", model,
                                               flags=re.IGNORECASE),
                 "effort": validator.get("effort") or "medium"}
        escalation_label = (f"section quality {sid} escalation › {terra.get('kind')} "
                            f"{terra.get('model')}")
        emit_status_line(
            f"AI VALIDATOR CALL START [{time.time():.3f}] › {escalation_label}",
            build_id, build_dir=BUILD_DIR)
        try:
            raw, terra_meta = _invoke(prompt, terra, adapter)
        except Exception as exc:
            _append_infrastructure_failure(
                build_id, sid, packet, terra, exc, stage="escalation",
                escalated_from=model)
            emit_status_line(
                f"AI VALIDATOR CALL FAILED [{time.time():.3f}] › {escalation_label}", build_id,
                build_dir=BUILD_DIR)
            raise RuntimeError(f"section Validator AI escalation failed: {exc}") from exc
        parsed, _errors, output = _classify_output(
            raw, sources, sid, known_mechanisms)
        _append_call(
            build_id, sid, packet,
            output.result if output.recovered_verdict else parsed,
            terra_meta, raw=raw,
            stage="escalation", escalated_from=model, malformed=output.malformed)
        result = output.result
        emit_status_line(
            f"AI VALIDATOR CALL COMPLETE [{time.time():.3f}] ({result['status']}) › "
            f"{escalation_label}", build_id, build_dir=BUILD_DIR)
    if not output.unusable and result["status"] != "UNCERTAIN":
        _write(result_path(build_id, sid), {"fingerprint": fingerprint, "result": result})
    return {**result, "cached": False}
