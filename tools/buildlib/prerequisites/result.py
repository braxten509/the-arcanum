"""Schema validation for mandatory section-quality AI results."""
from __future__ import annotations

from ..validator_policy import (extract_json, readable_line_ranges, readable_outcome,
                                recover_readable_failure)


RESULT_KEYS = {"outcome", "citations", "reasons", "missingMechanisms",
               "nodeReviews", "qualityFindings"}
FINDING_KEYS = {"id", "label", "kind", "owner", "demands",
                "closestExisting", "semanticDelta"}
NODE_REVIEW_KEYS = {"path", "node", "judgment", "evidenceLines", "evidence"}
QUALITY_FINDING_KEYS = {"path", "node", "category", "evidenceLines", "evidence",
                        "requiredRepair"}
QUALITY_CATEGORIES = {
    "teaching-depth", "technical-correctness", "practice-quality", "hint-leakage",
    "learner-independence", "working-quality", "continuity", "source-quality",
    "template-or-filler",
}


def _valid_line_range(value, line_count=0):
    if (not isinstance(value, list) or len(value) != 2
            or any(type(number) is not int or number < 1 for number in value)
            or value[0] > value[1]):
        return False
    return not line_count or value[1] <= line_count


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
    expected_order = [(item["path"], item["node"]) for item in sources]
    expected = set(expected_order)
    line_counts = {(item["path"], item["node"]): int(item.get("lineCount") or 0)
                   for item in sources}
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

    node_reviews = value.get("nodeReviews")
    cleaned_reviews = []
    if not isinstance(node_reviews, list):
        failures.append("nodeReviews must be an array")
        node_reviews = []
    if len(node_reviews) != len(expected_order):
        failures.append("nodeReviews must contain exactly one row per sealed section node")
    for index, review in enumerate(node_reviews):
        if not isinstance(review, dict) or set(review) != NODE_REVIEW_KEYS:
            failures.append("each node review must contain path, node, judgment, evidenceLines, evidence")
            continue
        pair = (review.get("path"), review.get("node"))
        if index >= len(expected_order) or pair != expected_order[index]:
            failures.append("nodeReviews must follow the exact bounded source order")
            continue
        if review.get("judgment") not in ("PASS", "FAIL", "UNCERTAIN"):
            failures.append("node review judgment must be PASS, FAIL, or UNCERTAIN")
            continue
        if not _valid_line_range(review.get("evidenceLines"), line_counts.get(pair, 0)):
            failures.append("node review evidenceLines must be an in-file inclusive line range")
            continue
        if not isinstance(review.get("evidence"), str) or len(review["evidence"].strip()) < 12:
            failures.append("node review evidence must name concrete source evidence")
            continue
        cleaned_reviews.append(review)
    if outcome == "PASS" and (len(cleaned_reviews) != len(expected_order)
                               or any(item["judgment"] != "PASS"
                                      for item in cleaned_reviews)):
        failures.append("PASS requires one valid PASS nodeReview for every sealed section node")

    quality_findings = value.get("qualityFindings")
    cleaned_quality = []
    if not isinstance(quality_findings, list):
        failures.append("qualityFindings must be an array")
        quality_findings = []
    for finding in quality_findings:
        if not isinstance(finding, dict) or set(finding) != QUALITY_FINDING_KEYS:
            failures.append("each quality finding must contain path, node, category, "
                            "evidenceLines, evidence, requiredRepair")
            continue
        pair = (finding.get("path"), finding.get("node"))
        if pair not in expected:
            failures.append("quality finding is outside the bounded section packet")
            continue
        if finding.get("category") not in QUALITY_CATEGORIES:
            failures.append("quality finding category is not part of the sealed quality taxonomy")
            continue
        if not _valid_line_range(finding.get("evidenceLines"), line_counts.get(pair, 0)):
            failures.append("quality finding evidenceLines must be an in-file inclusive line range")
            continue
        if (not isinstance(finding.get("evidence"), str)
                or len(finding["evidence"].strip()) < 12
                or not isinstance(finding.get("requiredRepair"), str)
                or len(finding["requiredRepair"].strip()) < 12):
            failures.append("quality finding evidence and requiredRepair must be actionable")
            continue
        cleaned_quality.append(finding)
    failed_pairs = {(item["path"], item["node"]) for item in cleaned_reviews
                    if item["judgment"] == "FAIL"}
    quality_pairs = {(item["path"], item["node"]) for item in cleaned_quality}
    if failed_pairs - quality_pairs:
        failures.append("each FAIL nodeReview must have an actionable qualityFinding")
    if quality_pairs - failed_pairs:
        failures.append("each qualityFinding must correspond to a FAIL nodeReview")
    if outcome == "PASS" and quality_findings:
        failures.append("PASS cannot contain quality findings")
    if failures:
        outcome = "FAIL"
        reasons = [*reasons, *failures]
    return ({"status": outcome, "citations": citations, "reasons": reasons,
             "missingMechanisms": cleaned, "nodeReviews": cleaned_reviews,
             "qualityFindings": cleaned_quality}, failures)


def validate(raw, sources, sid, known_mechanisms=()):
    return validate_detailed(raw, sources, sid, known_mechanisms)[0]


def _bounded_evidence_pairs(value, sources):
    expected = {(item["path"], item["node"]) for item in sources}
    by_path = {}
    line_counts = {}
    for item in sources:
        by_path.setdefault(item["path"], []).append(item["node"])
        line_counts[(item["path"], item["node"])] = int(item.get("lineCount") or 0)
    observed = set()
    for key in ("citations", "nodeReviews", "qualityFindings", "checks", "findings"):
        rows = value.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            path, node = row.get("path"), row.get("node")
            if not path and not node:
                continue
            if node is None:
                candidates = by_path.get(path) or []
                if len(candidates) != 1:
                    return None
                node = candidates[0]
            pair = (path, node)
            if pair not in expected:
                return None
            line_value = row.get("evidenceLines", row.get("lines"))
            if line_value is not None:
                ranges = readable_line_ranges(line_value)
                line_count = line_counts[pair]
                if (not ranges or any(start < 1 or start > end
                                      or (line_count and end > line_count)
                                      for start, end in ranges)):
                    return None
            observed.add(pair)
    return observed


def failure_evidence_is_bounded(value, sources):
    """Accept schema-drifted FAIL evidence only when every named source remains bounded."""
    return bool(_bounded_evidence_pairs(value, sources))


def evidence_supports_verdict(value, outcome, sources):
    """Prove a readable section verdict retains its bounded semantic evidence."""
    observed = _bounded_evidence_pairs(value, sources)
    if not observed:
        return False
    if outcome != "PASS":
        return True
    expected_order = [(item["path"], item["node"]) for item in sources]
    reviews = value.get("nodeReviews")
    if not isinstance(reviews, list):
        reviews = value.get("checks")
    if not isinstance(reviews, list) or len(reviews) != len(expected_order):
        return False
    for index, review in enumerate(reviews):
        if not isinstance(review, dict):
            return False
        pair = (review.get("path"), review.get("node"))
        if pair != expected_order[index] or readable_outcome(review) != "PASS":
            return False
        ranges = readable_line_ranges(
            review.get("evidenceLines", review.get("lines")))
        line_count = int(sources[index].get("lineCount") or 0)
        if (not ranges or any(start < 1 or start > end
                              or (line_count and end > line_count)
                              for start, end in ranges)):
            return False
    return not any(value.get(key) for key in (
        "missingMechanisms", "qualityFindings", "findings"))


def actionable_failure(raw, result, sources):
    """Keep a bounded FAIL readable when optional detail metadata is invalid."""
    return recover_readable_failure(
        raw, result, lambda value: failure_evidence_is_bounded(value, sources))
