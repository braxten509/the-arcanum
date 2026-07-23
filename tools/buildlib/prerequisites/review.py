"""Mandatory, cached teaching-quality and first-use completeness audit."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time

from .. import BUILD_DIR, REPO, VALIDATOR_FAILURE_DIR, brief_exception
from ..status_log import emit_status_line
from arcanum.platform.agent_commands import scoped_runner_command
from arcanum.jobs.stall import StalledProcess, run_watched
from ..runtime.events import assistant_text, session_id_from_line, usage_from_line
from arcanum.ai.events import step_tokens_from_line
from arcanum.authoring.adapters import validator_live
from ..course.alignment import actual_lesson_id
from ..course_map import load_course_map
from ..section_quality_contract import pacing_contract, section_quality_settings
from ..validator_policy import (ValidatorOutput, extract_json, readable_guidance,
                                readable_outcome, readable_reasons)
from .prompt import DYNAMIC_MARKER, prerequisite_prompt as _prompt
from . import records as _records
from .result import validate_detailed as _validate_detailed
from . import transport
# Re-exported so callers and tests keep addressing these through this module; the
# call sites below go through `transport.` so patching the transport module works.
from .transport import (API_MAX_OUTPUT_TOKENS, API_TIMEOUT_SECONDS,
                        AUDIT_CONTRACT_VERSION, RESPONSES_URL,
                        _api_adapter, _openai_key)
from ..runtime.runners import author_runner
from arcanum.catalog.build_ids import resolve_working_id


MAX_SECTION_PACKET_CHARS = 200_000
# Idle means no CPU anywhere in the tree and no established provider connection, so this
# is not a patience budget: a thinking model and a running tool both keep the clock at 0.
STALL_SECONDS = float(os.environ.get("ARCANUM_STALL_SECONDS", "10"))
# Short provider throttles should not strand a mechanically clean unit. These retries stay
# bounded so an account/session quota still returns control to the operator promptly.
TRANSIENT_VALIDATOR_RETRY_DELAYS = (2.0, 8.0, 20.0)


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
    settings = section_quality_settings(BUILD_DIR, build_id)
    bindery = launch.get("bindery") or {}
    validator = launch.get("validator") or bindery.get("validator") or {}
    return (settings["start"], validator, settings["prior"], settings["depth"],
            settings["mastery"])


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


# The pane rebuilds its whole conversation whenever any row's text changes, which drops
# a live text selection. Sampling stays per-second for an honest CPU average; only the
# published row is throttled, so the operator keeps a usable pane during a long gate.
LIVE_PUBLISH_SECONDS = 5.0


def _live_tick(build_id, label, started):
    """Publish CPU and tokens-so-far for the call in flight, a few seconds apart."""
    seen, totals, samples, published = 0, {}, [], 0.0

    def tick(cpu, output):
        nonlocal seen, totals, samples, published
        cut = output.rfind("\n", seen) + 1  # never parse a half-written line
        for line in output[seen:cut].splitlines():
            step = step_tokens_from_line(line)
            if step:
                totals = {key: totals.get(key, 0) + value
                          for key, value in step.items()}
        seen = max(seen, cut)
        samples.append(max(0.0, float(cpu)))
        if time.time() - published < LIVE_PUBLISH_SECONDS:
            return
        published = time.time()
        validator_live.publish(BUILD_DIR, build_id, label=label, started=started,
                               cpu=sum(samples) / len(samples), tokens=totals)
        samples.clear()
    return tick


def _cli_failure_detail(output):
    """Recover the provider's useful failure text from a structured CLI stream."""
    messages = []
    for line in str(output or "").splitlines():
        try:
            row = json.loads(line)
        except (TypeError, ValueError):
            continue
        if not isinstance(row, dict):
            continue
        values = []
        if row.get("type") == "error":
            values.append(row.get("message"))
        error = row.get("error")
        if isinstance(error, dict):
            values.append(error.get("message"))
        elif isinstance(error, str):
            values.append(error)
        payload = row.get("payload")
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                values.append(error.get("message"))
            elif isinstance(error, str):
                values.append(error)
        for value in values:
            text = re.sub(r"\s+", " ", str(value or "")).strip()
            if text and text not in messages:
                messages.append(text)
    if messages:
        return messages[-1][:1200]
    # Some CLIs still fail with plain stderr. Preserve a bounded tail instead of
    # collapsing every provider/auth/quota error to an unactionable exit code.
    tail = [re.sub(r"\s+", " ", line).strip()
            for line in str(output or "").splitlines() if line.strip()]
    return " | ".join(tail[-4:])[-1200:]


def _transient_cli_failure(detail):
    """Distinguish short provider throttles from quotas that require operator action."""
    normalized = re.sub(r"\s+", " ", str(detail or "")).strip().lower()
    if not normalized:
        return False
    if any(marker in normalized for marker in (
            "usage limit", "session limit", "weekly limit", "monthly limit",
            "billing limit", "credit balance", "resets at", "resets ")):
        return False
    return any(marker in normalized for marker in (
        "rate_limit", "rate limit", "too many requests", "http 429", "status 429",
        "resource_exhausted", "resource exhausted", "temporarily unavailable",
        "server overloaded", "overloaded_error", "capacity temporarily",
    ))


def _cli_adapter(prompt, validator, live=None):
    spec = f"{validator['kind']}:{validator['model']}" + (
        f"@{validator['effort']}" if validator.get("effort") else "")
    display, command, input_mode = author_runner(spec, "--validator-ai")
    kind = str(validator.get("kind") or "")
    if kind == "codex-cli":
        position = command.index("-") if "-" in command else len(command)
        command[position:position] = ["--json"]
    elif kind == "claude-cli":
        command += ["--safe-mode", "--output-format", "stream-json", "--verbose"]
        # Claude's ordinary author runner accepts the prompt as argv. A complete
        # section-audit packet can exceed Linux/bwrap's per-argument limit, while
        # print mode supports the same text over stdin without changing semantics.
        # Safe mode also disables user hooks and memory customizations: a read-only
        # validator must return after its report instead of entering an unrelated
        # repository stop-hook loop.
        input_mode = "stdin"
    elif kind == "opencode-cli":
        position = command.index("run") + 1
        command[position:position] = ["--format", "json"]
    if input_mode == "arg":
        command = [*command, prompt]
    wrapped = scoped_runner_command(display, command, REPO, [], REPO)
    build_id, label = live if live else ("", "")
    try:
        for attempt in range(len(TRANSIENT_VALIDATOR_RETRY_DELAYS) + 1):
            returncode, stdout, stalled = run_watched(
                wrapped, cwd=REPO, stdin_text=prompt if input_mode == "stdin" else None,
                seconds=STALL_SECONDS, timeout=900,
                on_tick=_live_tick(build_id, label, time.time()) if build_id else None)
            # A stall that arrives after readable output is the CLI failing to exit, not failing
            # to answer. Keep that output; only an empty stall is an infrastructure failure.
            if stalled and not stdout.strip():
                raise StalledProcess(STALL_SECONDS)
            if returncode and not stalled:
                detail = _cli_failure_detail(stdout)
                if (_transient_cli_failure(detail)
                        and attempt < len(TRANSIENT_VALIDATOR_RETRY_DELAYS)):
                    delay = TRANSIENT_VALIDATOR_RETRY_DELAYS[attempt]
                    print(
                        f"AI VALIDATOR TRANSIENT RETRY {attempt + 1}/"
                        f"{len(TRANSIENT_VALIDATOR_RETRY_DELAYS)} in {delay:g}s › "
                        f"{detail[:240]}", flush=True)
                    time.sleep(delay)
                    continue
                raise RuntimeError(
                    f"validator process exited {returncode}"
                    + (f": {detail}" if detail else ""))
            break
    finally:
        # The row describes a call in flight; every exit path must retire it.
        if build_id:
            validator_live.clear(BUILD_DIR, build_id)
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
    return ("\n".join(answers) if answers else stdout), {
        "transport": "cli", "kind": kind, "model": validator["model"],
        "effort": validator.get("effort", ""), "usage": usage,
        "sessionId": session_id,
    }


def invoke_validator(prompt, validator, *, adapter=None, schema=None,
                     schema_name="arcanum_section_quality_audit", cache_key=None,
                     max_output_tokens=API_MAX_OUTPUT_TOKENS, plain_text=False,
                     live=None):
    """Run one configured, read-only Validator AI call with an optional strict schema."""
    if adapter:
        return adapter(prompt, validator), {
            "transport": "test-adapter", "model": validator.get("model", ""), "usage": None}
    # CLI and API are deliberately separate Forge choices. Never turn a Codex CLI
    # selection into billable API traffic merely because a key happens to exist.
    if validator.get("kind") == "openai-api":
        key = transport._openai_key()
        if not str(validator.get("model") or "").startswith("gpt-"):
            raise RuntimeError("Codex API validators require a gpt- model")
        return transport._api_adapter(
            prompt, validator, key, schema=schema, schema_name=schema_name,
            cache_key=cache_key, max_output_tokens=max_output_tokens,
            plain_text=plain_text)
    return _cli_adapter(prompt, validator, live)


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


def _invoke(prompt, validator, adapter, live=None):
    return invoke_validator(
        prompt, validator, adapter=adapter, live=live, plain_text=True)


def section_policy_fingerprint(start, prior, depth, mastery):
    """Invalidate cached judgments whenever shared or role-specific prompt policy changes."""
    stable = _prompt("", "", [], prior, start, depth, mastery).split(
        DYNAMIC_MARKER, 1)[0]
    material = f"{AUDIT_CONTRACT_VERSION}\n{stable}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _classify_output(raw, sources, sid, known_mechanisms):
    parsed, errors = _validate_detailed(raw, sources, sid, known_mechanisms)
    text = (raw.strip() if isinstance(raw, str)
            else json.dumps(raw, ensure_ascii=False, default=str).strip()
            if raw is not None else "")
    value = extract_json(raw)
    outcome = readable_outcome(value)
    if outcome not in ("PASS", "FAIL"):
        explicit = re.search(
            r"(?im)^\s*(?:#{1,6}\s*)?(?:\*\*|__)?(?:overall\s+)?"
            r"(?:(?:verdict|assessment|conclusion)\s*[:=—-]\s*)?"
            r"(?:\*\*|__)?(PASS|FAIL)\b", text)
        if explicit:
            outcome = explicit.group(1).upper()
        elif re.search(
                r"(?i)\b(?:passes?|passed)\s+(?:the\s+)?(?:review|audit|gate|criteria)\b|"
                r"\bno\s+(?:material\s+)?(?:defects?|findings?|repairs?|blockers?|issues?)\b",
                text):
            outcome = "PASS"
        else:
            outcome = "FAIL"
    guidance = readable_guidance(raw)
    reasons = readable_reasons(value)
    if not reasons:
        reasons = [text[:12000]] if text else ["Validator AI returned no readable response."]
    # Preserve optional structured findings when present, but never reject readable prose or
    # spend another call merely because it did not follow the suggested JSON shape.
    result = {**parsed, "status": outcome, "reasons": reasons}
    if guidance:
        result["guidance"] = guidance
    if outcome == "PASS" and (result.get("missingMechanisms")
                               or result.get("qualityFindings")):
        result["status"] = "FAIL"
    output = ValidatorOutput(
        result=result, malformed=False, unusable=not bool(text), recovered_verdict=True)
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
        "policyFingerprint": section_policy_fingerprint(start, prior, depth, mastery),
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
        raw, meta = _invoke(prompt, validator, adapter, (build_id, audit_label))
    except Exception as exc:
        _append_infrastructure_failure(build_id, sid, packet, validator, exc)
        emit_status_line(f"AI VALIDATOR CALL FAILED [{time.time():.3f}] › {audit_label}",
                         build_id, build_dir=BUILD_DIR)
        raise RuntimeError(
            f"section Validator AI infrastructure failed: {brief_exception(exc)}") from exc
    parsed, errors, output = _classify_output(raw, sources, sid, known_mechanisms)
    _append_call(
        build_id, sid, packet,
        output.result if output.recovered_verdict else parsed,
        meta, raw=raw, malformed=output.malformed)
    emit_status_line(
        f"AI VALIDATOR CALL COMPLETE [{time.time():.3f}] "
        f"({output.result['status']}) › {audit_label}",
        build_id, build_dir=BUILD_DIR)
    result = output.result
    if not output.unusable:
        _write(result_path(build_id, sid), {"fingerprint": fingerprint, "result": result})
    return {**result, "cached": False}
