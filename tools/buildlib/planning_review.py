"""Mandatory bounded Validator AI reviews for the two planning phases."""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass

from . import BUILD_DIR, REPO, VALIDATOR_FAILURE_DIR
from .planning_review_parts import policy as _policy
from .prerequisites import records as _records
from .prerequisites.prompt import DYNAMIC_MARKER
from .prerequisites.review import invoke_validator
from .status_log import emit_status_line

AUDIT_CONTRACT_VERSION = _policy.AUDIT_CONTRACT_VERSION
MAX_PHASE_PACKET_CHARS = _policy.MAX_PHASE_PACKET_CHARS
MAX_OUTPUT_TOKENS = _policy.MAX_OUTPUT_TOKENS
MAX_PRIOR_REVIEW_REPORTS = _policy.MAX_PRIOR_REVIEW_REPORTS
MAX_PRIOR_REVIEW_CHARS = _policy.MAX_PRIOR_REVIEW_CHARS
MAX_EVIDENCE_HISTORY = _policy.MAX_EVIDENCE_HISTORY
PLANNING_CONTRACT_CYCLE_MARKER = _policy.PLANNING_CONTRACT_CYCLE_MARKER
PHASE_CRITERIA = _policy.PHASE_CRITERIA
SHARED_PLANNING_AUTHORITY_START = _policy.SHARED_PLANNING_AUTHORITY_START
SHARED_PLANNING_AUTHORITY_END = _policy.SHARED_PLANNING_AUTHORITY_END


def _sync_policy():
    _policy.BUILD_DIR = BUILD_DIR
    _policy.REPO = REPO
    _policy.DYNAMIC_MARKER = DYNAMIC_MARKER


def result_path(build_id, phase):
    _sync_policy()
    return _policy.result_path(build_id, phase)


def _read_json(path, default=None):
    return _policy._read_json(path, default)


def _write_json(path, value):
    return _policy._write_json(path, value)


def _launch_configuration(build_id, build_dir=None):
    _sync_policy()
    return _policy._launch_configuration(build_id, build_dir)


def _source(path, repairable):
    _sync_policy()
    return _policy._source(path, repairable)


def _runtime_profile_path(manifest):
    _sync_policy()
    return _policy._runtime_profile_path(manifest)


def _section_skeleton_paths(tome_root, manifest):
    _sync_policy()
    return _policy._section_skeleton_paths(tome_root, manifest)


def planning_dynamic_authority(build_id, phase, calibration=None, build_dir=None):
    _sync_policy()
    return _policy.planning_dynamic_authority(
        build_id, phase, calibration, build_dir)


def phase_evidence_packet(build_id, phase, tid, calibration=None):
    _sync_policy()
    return _policy.phase_evidence_packet(build_id, phase, tid, calibration)


def _prior_review_reports(prior_review=None, prior_reviews=None):
    return _policy._prior_review_reports(prior_review, prior_reviews)


def planning_prompt(phase, packet, sources, prior_review=None, prior_reviews=None):
    _sync_policy()
    return _policy.planning_prompt(
        phase, packet, sources, prior_review, prior_reviews)


def planning_authority(phase):
    _sync_policy()
    return _policy.planning_authority(phase)


def planning_policy_fingerprint(phase):
    _sync_policy()
    return _policy.planning_policy_fingerprint(phase)


def _review_text(raw):
    if isinstance(raw, str):
        return raw.strip()
    if raw is None:
        return ""
    return json.dumps(raw, ensure_ascii=False, indent=2, default=str).strip()


def _explicit_outcome(text):
    """Read semantic verdict words without depending on a response layout or field name."""
    patterns = (
        r"(?im)^\s*(?:#{1,6}\s*)?(?:\*\*|__)?(PASS|FAIL)"
        r"(?:\*\*|__)?(?:\s*(?:[.:—-]|$))",
        r"(?im)^\s*(?:#{1,6}\s*)?(?:\*\*|__)?(?:overall\s+)?"
        r"(?:verdict|assessment|conclusion)(?:\*\*|__)?\s*[:—=-]\s*"
        r"(?:\*\*|__)?(PASS|FAIL)\b",
        r'(?i)["\'](?:outcome|status|verdict)["\']\s*:\s*["\']'
        r"(PASS|FAIL)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).upper()
    return ""


def is_contract_conflict_report(report):
    """Recognize only the validator's explicit exceptional Phase-2 routing verdict."""
    return bool(re.search(
        r"(?im)^\s*#{1,6}\s+CONTRACT\s+CONFLICT\s*$", str(report or "")))


def is_planning_contract_cycle_report(report):
    """Recognize a harness marker, never ordinary validator prose."""
    return bool(re.search(
        rf"(?m)^\s*{PLANNING_CONTRACT_CYCLE_MARKER}\s*$", str(report or "")))


def _semantic_outcome(text):
    """Infer ordinary review prose without imposing headings, labels, or field names."""
    explicit = _explicit_outcome(text)
    if explicit:
        return explicit
    prose = " ".join(str(text or "").split()).casefold()
    negative_prose = re.sub(
        r"\bno\s+(?:material\s+)?(?:defects?|findings?|repairs?|blockers?|issues?|"
        r"missing\s+mechanisms?|omissions?)\b|\bdoes\s+not\s+fail\b", "", prose)
    if re.search(
            r"\b(?:fails?|failed|blocking|blocker|defect|missing|incomplete|incoherent|"
            r"contradict(?:s|ed|ion)|repair(?:s|ed)?|not\s+ready|does\s+not\s+pass|"
            r"cannot\s+pass)\b", negative_prose):
        return "FAIL"
    if re.search(
            r"\bno\s+(?:material\s+)?(?:defects?|findings?|repairs?|blockers?|issues?|"
            r"missing\s+mechanisms?|omissions?)\b|"
            r"\b(?:all|every)\s+(?:planning\s+)?criteria\s+"
            r"(?:pass|passes|are\s+(?:met|satisfied|supported))\b|"
            r"\b(?:ready|safe)\s+(?:for|to)\s+(?:the\s+)?(?:transition|seal|proceed)\b",
            prose):
        return "PASS"
    if re.search(
            r"\b(?:passes?|passed)\s+(?:the\s+)?(?:review|audit|gate|criteria)\b|"
            r"\b(?:coherent|feasible|complete)\b.{0,80}\b(?:evidence|route|arc|map)\b",
            prose):
        return "PASS"
    # Substantive but disposition-ambiguous prose is still useful to the author. Keep
    # the transition closed and pass the report through unchanged instead of buying a
    # second model call solely to label it.
    return "FAIL"


def _review_summary(text, outcome):
    lines = []
    for line in text.splitlines():
        cleaned = re.sub(r"^\s{0,3}#{1,6}\s*", "", line).strip()
        cleaned = cleaned.strip("*_` ")
        if not cleaned or cleaned.upper() == outcome:
            if lines:
                break
            continue
        lines.append(cleaned)
        if sum(len(item) for item in lines) >= 900:
            break
    return " ".join(lines)[:1200]


def validate_result(raw, phase, sources):
    """Accept any useful Markdown/prose report; formatting is never a validation defect."""
    del sources  # Evidence paths constrain the prompt, not response presentation.
    text = _review_text(raw)
    contract_conflict = int(phase) == 2 and is_contract_conflict_report(text)
    outcome = "FAIL" if contract_conflict else (_semantic_outcome(text) if text else "")
    errors = []
    if not text:
        errors.append("the response is empty")
    status = outcome if outcome and text else "FAIL"
    summary = _review_summary(text, outcome) if text else ""
    issue_match = re.search(
        r"(?im)^\s*issues?\s+found\s*[:=]\s*(\d+)\b", text)
    issue_count = (max(1, int(issue_match.group(1))) if issue_match
                   else (1 if status == "FAIL" else 0))
    return ({"status": status,
             "reasons": [summary] if summary else list(errors),
             "report": text,
             "issueCount": issue_count,
             "contractConflict": contract_conflict,
             "checks": [], "findings": []}, errors)


@dataclass(frozen=True)
class _PlanningOutput:
    result: dict
    unusable: bool
    malformed: bool = False
    recovered_verdict: bool = False


def _append_call(build_id, phase, packet, result, meta, *, raw=None, stage="audit",
                 escalated_from="", malformed=False):
    return _records.append_ai_call(
        BUILD_DIR, VALIDATOR_FAILURE_DIR, build_id, f"phase-{phase}", packet,
        result, meta, raw=raw, stage=stage, escalated_from=escalated_from,
        malformed=malformed, contract=AUDIT_CONTRACT_VERSION, phase=phase,
        unit_kind="phase", audit_kind="planning")


def _append_infrastructure_failure(build_id, phase, packet, validator, error, *,
                                   stage="audit", escalated_from=""):
    return _records.append_ai_infrastructure_failure(
        BUILD_DIR, VALIDATOR_FAILURE_DIR, build_id, f"phase-{phase}", packet,
        validator, error, stage=stage, contract=AUDIT_CONTRACT_VERSION,
        escalated_from=escalated_from, phase=phase, unit_kind="phase",
        audit_kind="planning")


def _invoke(prompt, validator, phase, adapter=None, live=None):
    return invoke_validator(
        prompt, validator, adapter=adapter, live=live,
        cache_key=f"arcanum-phase-{phase}-quality-v{AUDIT_CONTRACT_VERSION}",
        max_output_tokens=MAX_OUTPUT_TOKENS, plain_text=True)


def _classify_output(raw, phase, sources):
    parsed, errors = validate_result(raw, phase, sources)
    output = _PlanningOutput(result=parsed, unusable=bool(errors))
    return parsed, errors, output


def review_planning_phase(build_id, phase, tid, *, adapter=None):
    """Audit Phase 1 or 2 after its mechanical gate and before its transition."""
    phase = int(phase)
    if phase not in PHASE_CRITERIA:
        raise ValueError("planning Validator AI is defined only for Phase 1 and Phase 2")
    validator, calibration = _launch_configuration(build_id)
    if not validator.get("kind") or not validator.get("model"):
        raise RuntimeError(f"mandatory Phase {phase} audit has no Validator AI configuration")
    packet, sources = phase_evidence_packet(build_id, phase, tid, calibration)
    policy_fingerprint = planning_policy_fingerprint(phase)
    validator_identity = {
        key: validator.get(key) for key in ("kind", "model", "effort")}
    fingerprint = hashlib.sha256(json.dumps({
        "contract": AUDIT_CONTRACT_VERSION, "phase": phase, "packet": packet,
        "policyFingerprint": policy_fingerprint,
        "validator": validator_identity,
    }, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    cached = _read_json(result_path(build_id, phase), {}) or {}
    # A prompt/contract revision may explicitly invalidate an older finding. Feeding
    # reports from that older authority back to the model anchors it on requirements
    # the current gate no longer permits and can force an A -> B -> A repair loop.
    same_contract = (cached.get("contract") == AUDIT_CONTRACT_VERSION
                     and cached.get("policyFingerprint") == policy_fingerprint
                     and cached.get("validator") == validator_identity)
    evidence_history = ([item for item in cached.get("evidenceHistory", [])
                         if isinstance(item, dict)] if same_contract else [])
    current_result = cached.get("result") if isinstance(cached.get("result"), dict) else None
    current_fingerprint = str(cached.get("fingerprint") or "")
    if same_contract and current_fingerprint and current_result and not any(
            item.get("fingerprint") == current_fingerprint for item in evidence_history):
        evidence_history.append({
            "fingerprint": current_fingerprint,
            "result": current_result,
        })
    for item in reversed(evidence_history):
        previous = item.get("result") if isinstance(item.get("result"), dict) else None
        if item.get("fingerprint") == fingerprint and previous:
            return {
                **previous,
                "cached": True,
                "planningContractCycle": previous.get("status") == "FAIL",
            }
    history = ([item for item in cached.get("history", []) if isinstance(item, dict)]
               if same_contract else [])
    prior_review = (cached.get("result")
                    if same_contract and isinstance(cached.get("result"), dict) else None)
    if isinstance(prior_review, dict) and prior_review.get("status") == "FAIL":
        history.append(prior_review)
    history = history[-MAX_PRIOR_REVIEW_REPORTS:]
    prompt = planning_prompt(phase, packet, sources, prior_reviews=history)
    audit_name = f"phase {phase} {'arc' if phase == 1 else 'map'} quality"
    label = f"{audit_name} › {validator.get('kind')} {validator.get('model')}"
    emit_status_line(f"AI VALIDATOR CALL START [{time.time():.3f}] › {label}",
                     build_id, build_dir=BUILD_DIR)
    try:
        raw, meta = _invoke(prompt, validator, phase, adapter, (build_id, label))
    except Exception as exc:
        _append_infrastructure_failure(build_id, phase, packet, validator, exc)
        emit_status_line(f"AI VALIDATOR CALL FAILED [{time.time():.3f}] › {label}",
                         build_id, build_dir=BUILD_DIR)
        raise RuntimeError(f"Phase {phase} Validator AI infrastructure failed: {exc}") from exc
    parsed, errors, output = _classify_output(raw, phase, sources)
    _append_call(
        build_id, phase, packet,
        output.result if output.recovered_verdict else parsed,
        meta, raw=raw, malformed=output.malformed)
    emit_status_line(
        f"AI VALIDATOR CALL COMPLETE [{time.time():.3f}] "
        f"({output.result['status']}) › {label}", build_id, build_dir=BUILD_DIR)
    result = output.result
    if not output.unusable:
        evidence_history.append({"fingerprint": fingerprint, "result": result})
        _write_json(result_path(build_id, phase), {
            "contract": AUDIT_CONTRACT_VERSION,
            "policyFingerprint": policy_fingerprint,
            "validator": validator_identity,
            "fingerprint": fingerprint,
            "result": result,
            "history": history,
            "evidenceHistory": evidence_history[-MAX_EVIDENCE_HISTORY:],
        })
    return {**result, "cached": False}


def review_report(phase, result):
    """Return validator prose unchanged, prefixed only by a harness cycle signal."""
    del phase
    report = str(result.get("report") or "").strip()
    if result.get("planningContractCycle"):
        return (PLANNING_CONTRACT_CYCLE_MARKER
                + (("\n\n" + report) if report else ""))
    if report:
        return report
    reasons = "\n\n".join(str(reason) for reason in result.get("reasons") or [])
    return reasons or str(result.get("status") or "FAIL")
