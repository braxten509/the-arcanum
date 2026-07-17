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

from .. import BUILD_DIR, REPO
from ..runtime.agent_runtime import scoped_runner_command
from ..course.alignment import actual_lesson_id
from ..course_map import load_course_map
from .prompt import (DYNAMIC_MARKER,
                                  format_repair_prompt as _format_repair_prompt,
                                  prerequisite_prompt as _prompt,
                                  result_schema as _result_schema)
from ..workflow.prompts import START_PACING
from ..runtime.runners import author_runner
from arcanum.tomes import resolve_working_tid


RESULT_KEYS = {"outcome", "citations", "reasons", "missingMechanisms"}
FINDING_KEYS = {"id", "label", "kind", "owner", "demands"}
MAX_SECTION_PACKET_CHARS = 200_000
AUDIT_CONTRACT_VERSION = 3
RESPONSES_URL = "https://api.openai.com/v1/responses"
API_TIMEOUT_SECONDS = 900
API_MAX_OUTPUT_TOKENS = 2_500


def result_path(build_id, sid):
    return os.path.join(BUILD_DIR, f"{build_id}.prerequisite-reviews", f"{sid}.json")


def calls_path(build_id):
    return os.path.join(BUILD_DIR, f"{build_id}.prerequisite-review.calls.jsonl")


def review_call_count(build_id):
    try:
        with open(calls_path(build_id), encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())
    except OSError:
        return 0


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
    if isinstance(mechanism_contract, dict):
        section_order = {item.get("id"): index
                         for index, item in enumerate(course.get("sections") or [])}
        current_index = section_order.get(section.get("id"), -1)
        mechanism_contract = {
            **mechanism_contract,
            "mechanisms": [item for item in mechanism_contract.get("mechanisms") or []
                           if section_order.get(
                               str(item.get("owner") or "").split(".", 1)[0], 999)
                           <= current_index],
        }
    packet = json.dumps({
        "mapVersion": 1,
        "section": section,
        "languageMastery": ({**(course.get("languageMastery") or {}),
                              "performances": performances}
                             if course.get("languageMastery") else None),
        "mechanismContract": mechanism_contract,
        "sources": sources,
    }, ensure_ascii=False, sort_keys=True, indent=2)
    packet += "\n\n" + "\n\n".join(source_blocks)
    if len(packet) > MAX_SECTION_PACKET_CHARS:
        raise ValueError(
            f"validator evidence for {section.get('id')} is {len(packet)} characters; "
            f"the deterministic section budget is {MAX_SECTION_PACKET_CHARS}")
    return packet, sources


def _extract_json(raw):
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        matches = re.findall(r"\{(?:[^{}]|\{[^{}]*\})*\}", text, re.S)
        for candidate in reversed(matches):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
    return None


def _cli_adapter(prompt, validator):
    spec = f"{validator['kind']}:{validator['model']}" + (
        f"@{validator['effort']}" if validator.get("effort") else "")
    display, command, input_mode = author_runner(spec, "--validator-ai")
    if input_mode == "arg":
        command = [*command, prompt]
    wrapped = scoped_runner_command(display, command, REPO, [], REPO)
    process = subprocess.run(
        wrapped, cwd=REPO, input=prompt if input_mode == "stdin" else None,
        capture_output=True, text=True, timeout=900)
    if process.returncode:
        raise RuntimeError(f"validator process exited {process.returncode}")
    return process.stdout, {"transport": "cli", "model": validator["model"], "usage": None}


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
        "transport": "responses-api", "model": validator["model"], "usage": _usage(value),
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


def _validate_detailed(raw, sources, sid):
    value = _extract_json(raw)
    failures = []
    if not isinstance(value, dict) or set(value) != RESULT_KEYS:
        failures.append(f"response keys must be exactly {sorted(RESULT_KEYS)}")
        value = value if isinstance(value, dict) else {}
    outcome = value.get("outcome")
    if outcome not in ("PASS", "FAIL", "UNCERTAIN"):
        failures.append("outcome must be PASS, FAIL, or UNCERTAIN")
        outcome = "FAIL"
    expected = {(item["path"], item["node"]) for item in sources}
    citations, cited = value.get("citations"), set()
    if not isinstance(citations, list):
        failures.append("citations must be an array")
        citations = []
    for citation in citations:
        if not isinstance(citation, dict) or set(citation) != {"path", "node"}:
            failures.append("each citation must contain exactly path and node")
            continue
        pair = (citation.get("path"), citation.get("node"))
        if pair not in expected:
            failures.append("citation is outside the bounded section packet")
        else:
            cited.add(pair)
    if outcome == "PASS" and cited != expected:
        failures.append("PASS must cite every sealed section node")
    reasons = value.get("reasons")
    if (not isinstance(reasons, list) or not reasons
            or any(not isinstance(reason, str) or not reason.strip() for reason in reasons)):
        failures.append("reasons must be a non-empty string array")
        reasons = []
    findings = value.get("missingMechanisms")
    if not isinstance(findings, list):
        failures.append("missingMechanisms must be an array")
        findings = []
    valid_nodes = {item["node"] for item in sources}
    valid_lessons = {node for node in valid_nodes if ".l" in node}
    cleaned = []
    for finding in findings:
        if not isinstance(finding, dict) or set(finding) != FINDING_KEYS:
            failures.append("each missing mechanism must contain id, label, kind, owner, demands")
            continue
        demands = finding.get("demands")
        if (finding.get("owner") not in valid_lessons or not isinstance(demands, list)
                or not demands or any(demand not in valid_nodes for demand in demands)):
            failures.append("missing mechanism owner/demands must name current sealed nodes")
            continue
        cleaned.append(finding)
    if outcome == "PASS" and findings:
        failures.append("PASS cannot contain missing mechanisms")
    if failures:
        outcome = "FAIL"
        reasons = [*reasons, *failures]
    return ({"status": outcome, "citations": citations, "reasons": reasons,
             "missingMechanisms": cleaned}, bool(failures))


def _validate(raw, sources, sid):
    return _validate_detailed(raw, sources, sid)[0]


def _previous_nonpass(build_id, sid, model):
    count = 0
    try:
        with open(calls_path(build_id), encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                if (row.get("contract") == AUDIT_CONTRACT_VERSION
                        and row.get("section") == sid and row.get("model") == model
                        and not row.get("malformed")
                        and row.get("status") in ("FAIL", "UNCERTAIN")):
                    count += 1
    except (OSError, ValueError):
        pass
    return count


def _append_call(build_id, sid, packet, result, meta, *, escalated_from="",
                 malformed=False):
    row = {"at": time.time(), "contract": AUDIT_CONTRACT_VERSION,
           "section": sid, "packetChars": len(packet),
           "status": result["status"], "transport": meta.get("transport", "test-adapter"),
           "model": meta.get("model", ""), "usage": meta.get("usage")}
    if meta.get("responseId"):
        row["responseId"] = meta["responseId"]
    if escalated_from:
        row["escalatedFrom"] = escalated_from
    if malformed:
        row["malformed"] = True
    with open(calls_path(build_id), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, separators=(",", ":")) + "\n")


def review_usage_summary(build_id):
    totals = {"inputTokens": 0, "freshInputTokens": 0, "cachedInputTokens": 0,
              "cacheWriteTokens": 0, "outputTokens": 0, "reasoningTokens": 0,
              "totalTokens": 0}
    api_calls = 0
    try:
        with open(calls_path(build_id), encoding="utf-8") as handle:
            for line in handle:
                usage = json.loads(line).get("usage")
                if not isinstance(usage, dict):
                    continue
                api_calls += 1
                for key in totals:
                    totals[key] += int(usage.get(key) or 0)
    except (OSError, ValueError, TypeError):
        pass
    return {"apiCalls": api_calls, **totals}


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
    print(f"AI VALIDATOR CALL START [{time.time():.3f}] › {audit_label}", flush=True)
    try:
        raw, meta = _invoke(prompt, validator, adapter)
    except Exception as exc:
        print(f"AI VALIDATOR CALL FAILED [{time.time():.3f}] › {audit_label}", flush=True)
        raise RuntimeError(f"section Validator AI infrastructure failed: {exc}") from exc
    result, malformed = _validate_detailed(raw, sources, sid)
    print(f"AI VALIDATOR CALL COMPLETE [{time.time():.3f}] ({result['status']}) › "
          f"{audit_label}", flush=True)
    model = str(validator.get("model") or "")
    previous_nonpass = _previous_nonpass(build_id, sid, model)
    _append_call(build_id, sid, packet, result, meta, malformed=malformed)
    if malformed:
        repair_label = (f"prerequisite completeness {sid} format repair › "
                        f"{validator.get('kind')} {validator.get('model')}")
        print(f"AI VALIDATOR CALL START [{time.time():.3f}] › {repair_label}", flush=True)
        try:
            repaired_raw, repair_meta = _invoke(
                _format_repair_prompt(prompt, raw), validator, adapter)
        except Exception:
            print(f"AI VALIDATOR CALL FAILED [{time.time():.3f}] › {repair_label}",
                  flush=True)
        else:
            result, malformed = _validate_detailed(repaired_raw, sources, sid)
            print(f"AI VALIDATOR CALL COMPLETE [{time.time():.3f}] ({result['status']}) › "
                  f"{repair_label}", flush=True)
            _append_call(build_id, sid, packet, result, repair_meta,
                         malformed=malformed)
    should_escalate = ("luna" in model.lower() and (
        malformed or result["status"] == "UNCERTAIN"
        or (result["status"] == "FAIL" and previous_nonpass > 0)))
    if should_escalate:
        terra = {**validator, "model": re.sub("luna", "terra", model,
                                               flags=re.IGNORECASE),
                 "effort": validator.get("effort") or "medium"}
        terra_label = (f"prerequisite completeness {sid} escalation › "
                       f"{terra.get('kind')} {terra.get('model')}")
        print(f"AI VALIDATOR CALL START [{time.time():.3f}] › {terra_label}", flush=True)
        try:
            raw, terra_meta = _invoke(prompt, terra, adapter)
        except Exception as exc:
            print(f"AI VALIDATOR CALL FAILED [{time.time():.3f}] › {terra_label}", flush=True)
            raise RuntimeError(f"section Validator AI escalation failed: {exc}") from exc
        result, _malformed = _validate_detailed(raw, sources, sid)
        print(f"AI VALIDATOR CALL COMPLETE [{time.time():.3f}] ({result['status']}) › "
              f"{terra_label}", flush=True)
        _append_call(build_id, sid, packet, result, terra_meta, escalated_from=model)
    _write(result_path(build_id, sid), {"fingerprint": fingerprint, "result": result})
    return {**result, "cached": False}
