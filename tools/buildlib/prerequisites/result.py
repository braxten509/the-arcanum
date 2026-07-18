"""Schema validation for prerequisite-review AI results."""
from __future__ import annotations

import json
import re


RESULT_KEYS = {"outcome", "citations", "reasons", "missingMechanisms"}
FINDING_KEYS = {"id", "label", "kind", "owner", "demands",
                "closestExisting", "semanticDelta"}


def extract_json(raw):
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


def validate_detailed(raw, sources, sid, known_mechanisms=()):
    value = extract_json(raw)
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
    known_mechanisms = set(known_mechanisms)
    cleaned = []
    for finding in findings:
        if not isinstance(finding, dict) or set(finding) != FINDING_KEYS:
            failures.append("each missing mechanism must contain id, label, kind, owner, demands, "
                            "closestExisting, semanticDelta")
            continue
        demands = finding.get("demands")
        closest = finding.get("closestExisting")
        delta = finding.get("semanticDelta")
        if (finding.get("owner") not in valid_lessons or not isinstance(demands, list)
                or not demands or any(not isinstance(demand, str)
                                      or demand not in valid_nodes for demand in demands)):
            failures.append("missing mechanism owner/demands must name current sealed nodes")
            continue
        if (not isinstance(closest, list) or not 1 <= len(closest) <= 3
                or any(not isinstance(item, str) or item not in known_mechanisms
                       for item in closest) or len(set(closest)) != len(closest)):
            failures.append("closestExisting must name one to three distinct sealed mechanisms")
            continue
        if (not all(isinstance(finding.get(key), str) and finding[key].strip()
                    for key in ("id", "label", "kind"))
                or finding["id"] in known_mechanisms):
            failures.append("a missing mechanism must have a new non-empty id, label, and kind")
            continue
        if not isinstance(delta, str) or len(delta.strip()) < 12:
            failures.append("semanticDelta must state the distinct non-spelling responsibility")
            continue
        cleaned.append(finding)
    if outcome == "PASS" and findings:
        failures.append("PASS cannot contain missing mechanisms")
    if failures:
        outcome = "FAIL"
        reasons = [*reasons, *failures]
    return ({"status": outcome, "citations": citations, "reasons": reasons,
             "missingMechanisms": cleaned}, failures)


def validate(raw, sources, sid, known_mechanisms=()):
    return validate_detailed(raw, sources, sid, known_mechanisms)[0]


def actionable_failure(raw, result, sources):
    """Keep a bounded FAIL readable when optional amendment metadata is invalid."""
    value = extract_json(raw)
    if not isinstance(value, dict) or value.get("outcome") != "FAIL":
        return None
    reasons, citations = value.get("reasons"), value.get("citations")
    expected = {(item["path"], item["node"]) for item in sources}
    if (not isinstance(reasons, list) or not reasons
            or any(not isinstance(reason, str) or not reason.strip() for reason in reasons)
            or not isinstance(citations, list) or not citations):
        return None
    if any(not isinstance(item, dict) or set(item) != {"path", "node"}
           or (item.get("path"), item.get("node")) not in expected for item in citations):
        return None
    return {**result, "status": "FAIL", "citations": citations, "reasons": reasons}
