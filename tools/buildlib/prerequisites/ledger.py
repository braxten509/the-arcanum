"""Cross-pass finding ledger: stable identity, persistence, and stuck-finding detection.

Each mandatory section audit is stateless and content-cached, so the harness otherwise
cannot tell a recurring defect from a fresh one — every pass reads as N novel blockers even
when the same defect was reworded. This gives each finding a stable identity across passes,
credits the ones that disappear, and reports which repeats have survived an author edit.
That last signal is what `review_prerequisites` uses to escalate a stuck finding to the
stronger tiebreak validator.
"""
from __future__ import annotations

import hashlib
import json
import os


# ponytail: coarse line buckets so a few-line citation drift stays one identity; tighten to
# the enclosing TOML table only if two distinct defects in one node start merging.
LINE_BUCKET = 40


def _bucket(lines):
    try:
        return int(lines[0]) // LINE_BUCKET
    except (TypeError, ValueError, IndexError):
        return 0


def _fingerprint(kind, key):
    return hashlib.sha256(f"{kind}\x00{key}".encode("utf-8")).hexdigest()[:16]


def _quality_fpr(finding):
    return _fingerprint("quality", f"{finding.get('node')}|{finding.get('path')}"
                                   f"|{_bucket(finding.get('evidenceLines'))}")


def _mechanism_fpr(finding):
    return _fingerprint("mechanism", str(finding["id"]))


def finding_fingerprints(result):
    """Stable identity per blocking finding, independent of the model's wording.

    Quality findings key on (node, path, coarse line bucket) — never the prose evidence or
    category, which the model rewrites and re-labels between passes. Missing mechanisms key
    on their proposed id.
    """
    prints = {}
    for finding in result.get("qualityFindings") or []:
        if not isinstance(finding, dict):
            continue
        prints[_quality_fpr(finding)] = {
            "kind": "quality", "node": finding.get("node"), "path": finding.get("path"),
            "category": finding.get("category"), "repair": finding.get("requiredRepair"),
            "evidence": finding.get("evidence")}
    for finding in result.get("missingMechanisms") or []:
        if not isinstance(finding, dict) or not finding.get("id"):
            continue
        prints[_mechanism_fpr(finding)] = {
            "kind": "mechanism", "node": finding.get("owner"), "id": finding.get("id"),
            "repair": finding.get("label")}
    return prints


def restrict(result, keep):
    """Return a copy of `result` keeping only findings whose fingerprint is in `keep`.

    The Single-Gate verify pass uses this: the second audit may surface fresh issues, but the
    gate only re-checks the first pass's findings, so anything not in `keep` is dropped. With no
    gated finding left, the section is resolved and the verdict flips to PASS.
    """
    quality = [f for f in result.get("qualityFindings") or []
               if isinstance(f, dict) and _quality_fpr(f) in keep]
    mechanisms = [f for f in result.get("missingMechanisms") or []
                  if isinstance(f, dict) and f.get("id") and _mechanism_fpr(f) in keep]
    out = {**result, "qualityFindings": quality, "missingMechanisms": mechanisms}
    if not quality and not mechanisms:
        out["status"] = "PASS"
        out["reasons"] = ["Verification pass: every previously cited finding is resolved."]
    return out


def ledger_path(build_dir, build_id, sid):
    return os.path.join(build_dir, f"{build_id}.section-findings", f"{sid}.json")


def load_ledger(build_dir, build_id, sid):
    try:
        with open(ledger_path(build_dir, build_id, sid), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        data = {}
    data.setdefault("pass", 0)
    data.setdefault("findings", {})
    return data


def _save(build_dir, build_id, sid, ledger):
    path = ledger_path(build_dir, build_id, sid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(ledger, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temp, path)


def open_fingerprints(ledger):
    return {fpr for fpr, entry in ledger.get("findings", {}).items()
            if entry.get("status") == "open"}


def has_repeat(ledger, result):
    """True when a still-open ledger finding reappears in this result: a defect that has
    survived at least one author edit, i.e. the audit is stuck on it."""
    return bool(open_fingerprints(ledger) & set(finding_fingerprints(result)))


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def tiebreak_validator(build_dir, build_id, primary):
    """The stronger auditor that adjudicates a finding the primary keeps re-raising.

    Absent config (or the same model as the primary) means no escalation: the ledger still
    tracks persistence, the section just never gets a second opinion.
    """
    launch = _read_json(os.path.join(build_dir, f"{build_id}.launch.json"))
    bindery = launch.get("bindery") or {}
    tiebreak = launch.get("tiebreakValidator") or bindery.get("tiebreakValidator") or {}
    if not tiebreak.get("kind") or not tiebreak.get("model"):
        return None
    if (tiebreak.get("kind"), tiebreak.get("model")) == (
            primary.get("kind"), primary.get("model")):
        return None
    return tiebreak


def run_with_escalation(build_dir, build_id, sid, primary, audit_fn):
    """Run the primary audit; if it re-raises a still-open ledger finding, adjudicate with the
    stronger tiebreak validator and adopt its verdict, then reconcile the adopted result.

    ``audit_fn(validator, escalated_from) -> output`` performs one real model call. Returns
    ``(output, diff)`` where diff is the new/persisting/resolved reconciliation.
    """
    output = audit_fn(primary, "")
    result = output.result
    escalated = False
    tiebreak = tiebreak_validator(build_dir, build_id, primary)
    if (tiebreak and result.get("status") != "PASS"
            and has_repeat(load_ledger(build_dir, build_id, sid), result)):
        output = audit_fn(tiebreak, str(primary.get("model") or ""))
        result, escalated = output.result, True
    diff = reconcile(build_dir, build_id, sid, result, escalated=escalated)
    return output, diff


def finding_progress(diff):
    """One line crediting the author: which cited defects persisted vs. cleared since last pass."""
    if not diff:
        return ""
    parts = []
    persisting = diff.get("persisting") or []
    if persisting:
        parts.append("still open: " + "; ".join(
            f"{item.get('node', '?')} ×{item.get('occurrences')}"
            + (" (tiebreak-confirmed)" if item.get("escalated") else "")
            for item in persisting))
    if diff.get("resolved"):
        parts.append(f"{len(diff['resolved'])} resolved since last pass")
    return ("Progress — " + " | ".join(parts) + ".") if parts else ""


def reconcile(build_dir, build_id, sid, result, *, escalated=False):
    """Fold one audit pass into the ledger; return a new/persisting/resolved diff."""
    ledger = load_ledger(build_dir, build_id, sid)
    pass_no = ledger["pass"] + 1
    current = finding_fingerprints(result)
    findings = ledger["findings"]
    new, persisting = [], []
    for fpr, summary in current.items():
        entry = findings.get(fpr) or {}
        occurrences = int(entry.get("occurrences") or 0) + 1
        row = {**summary, "occurrences": occurrences,
               "firstPass": entry.get("firstPass") or pass_no, "lastPass": pass_no,
               "status": "open", "escalated": bool(entry.get("escalated")) or escalated}
        findings[fpr] = row
        (persisting if occurrences >= 2 else new).append({"fingerprint": fpr, **row})
    resolved = []
    for fpr, entry in findings.items():
        if fpr not in current and entry.get("status") == "open":
            entry["status"] = "resolved"
            entry["resolvedPass"] = pass_no
            resolved.append({"fingerprint": fpr, **entry})
    ledger["pass"] = pass_no
    _save(build_dir, build_id, sid, ledger)
    return {"pass": pass_no, "openCount": len(current),
            "new": new, "persisting": persisting, "resolved": resolved}


if __name__ == "__main__":
    import tempfile

    quality = lambda node, lines, evid: {  # noqa: E731
        "path": f"tomes/t/sections/s01/{node}.toml", "node": f"s01.{node}",
        "category": "technical-correctness", "evidenceLines": lines,
        "evidence": evid, "requiredRepair": "fix it"}

    # Identity is stable across small line drift and reworded prose, distinct across nodes.
    a = finding_fingerprints({"qualityFindings": [quality("l07", [117, 123], "wrong const")]})
    b = finding_fingerprints({"qualityFindings": [quality("l07", [115, 125], "bad position")]})
    c = finding_fingerprints({"qualityFindings": [quality("l02", [10, 12], "unexplained")]})
    assert set(a) == set(b), "line drift within a bucket must keep one identity"
    assert set(a).isdisjoint(c), "different nodes must differ"

    with tempfile.TemporaryDirectory() as root:
        r_open = {"qualityFindings": [quality("l07", [117, 123], "wrong const")]}
        d1 = reconcile(root, "demo", "s01", r_open)
        assert d1["pass"] == 1 and len(d1["new"]) == 1 and not d1["persisting"]

        # Same defect after an author edit -> persisting, and detectable as a repeat.
        led = load_ledger(root, "demo", "s01")
        assert has_repeat(led, {"qualityFindings": [quality("l07", [119, 124], "x")]})
        d2 = reconcile(root, "demo", "s01", r_open)
        assert not d2["new"] and d2["persisting"][0]["occurrences"] == 2

        # Absent next pass -> resolved, and no longer a repeat.
        d3 = reconcile(root, "demo", "s01", {"qualityFindings": []})
        assert len(d3["resolved"]) == 1 and d3["openCount"] == 0
        assert not has_repeat(load_ledger(root, "demo", "s01"), r_open)

    # Verify-only restrict: a fresh finding is dropped; only the gated fingerprint gates.
    gated = finding_fingerprints(r_open)
    two = {"status": "FAIL", "qualityFindings": [
        quality("l07", [117, 123], "still wrong"), quality("l09", [5, 8], "brand new")]}
    kept = restrict(two, set(gated))
    assert len(kept["qualityFindings"]) == 1 and kept["status"] == "FAIL"
    cleared = restrict({"status": "FAIL", "qualityFindings": [quality("l09", [5, 8], "new")]},
                       set(gated))
    assert not cleared["qualityFindings"] and cleared["status"] == "PASS"
    print("ledger self-check ok")
