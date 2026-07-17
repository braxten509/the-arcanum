"""Phase-1 lifecycle facts converted into durable planned obligations."""
import re


RETIREMENT_WORDS = re.compile(
    r"\b(?:temporary|prototype|debug|fixture|placeholder|demo|mock|replace|remove|retire|"
    r"isolate|clean)\w*\b", re.I)


def _block(text, label):
    text = str(text or "")
    match = re.search(rf"(?im)^\*\*{re.escape(label)}:\*\*\s*(.*)$", text)
    if not match:
        return ""
    tail = re.split(r"(?m)^\*\*[^\n]+:\*\*", text[match.end():], 1)[0]
    return (match.group(1) + "\n" + tail).strip()


def continuity_obligations(text, section_ids):
    """Accept both legacy semicolon-separated and physical-line Arc edges."""
    block = _block(text, "Continuity map")
    pattern = re.compile(
        r"(?is)(?:^|[;\n])\s*(?:[-*]\s*)?(s\d{2})\s*->\s*(s\d{2})\s*:\s*"
        r"(.+?)(?=(?:[;\n]\s*(?:[-*]\s*)?s\d{2}\s*->\s*s\d{2}\s*:)|\Z)")
    counts, out = {}, []
    for origin, target, requirement in pattern.findall(block):
        origin, target = origin.lower(), target.lower()
        key = (origin, target)
        counts[key] = counts.get(key, 0) + 1
        requirement = " ".join(requirement.strip().split())
        out.append({
            "id": f"{origin}-plan-{target}-{counts[key]:02d}",
            "origin": origin, "target": target, "kind": "contract-preservation",
            "owner": "approved continuity contract", "location": "section.toml",
            "requirement": requirement,
            "reason": f"The approved Arc requires {target} to preserve this contract.",
            "doneWhen": {"evidenceLocations": [], "capabilityIds": [], "proofIds": [],
                         "acceptanceIds": [],
                         "observedResult": f"Evidence demonstrates: {requirement}"},
        })
    return out


def artifact_lifecycle_obligations(text, section_ids):
    """Parse cross-section retirement clauses without inventing lifecycle claims.

    Arc authors name section IDs in physical semicolon-separated clauses. A clause
    becomes a planned obligation only when it names an earlier origin, a later target,
    and retirement language. Same-section cleanup and deliberately shipped artifacts
    stay in the readable Arc but do not become cross-section todos.
    """
    block = _block(text, "Artifact lifecycle")
    if not block:
        return []
    positions = {sid: index for index, sid in enumerate(section_ids)}
    counts, obligations = {}, []
    for raw in re.split(r"\s*(?:;|\n)\s*", block):
        clause = raw.strip()
        mentioned = []
        for sid in re.findall(r"\bs\d{2}\b", clause, re.I):
            sid = sid.lower()
            if sid in positions and sid not in mentioned:
                mentioned.append(sid)
        if len(mentioned) < 2 or not RETIREMENT_WORDS.search(clause):
            continue
        origin, target = mentioned[0], mentioned[-1]
        if positions[origin] >= positions[target]:
            continue
        key = (origin, target)
        counts[key] = counts.get(key, 0) + 1
        obligations.append({
            "id": f"{origin}-retire-{target}-{counts[key]:02d}",
            "origin": origin, "target": target, "kind": "temporary-retirement",
            "owner": "approved temporary artifact",
            "location": "section.toml", "requirement": clause,
            "reason": f"The approved lifecycle requires retirement by {target}.",
            "doneWhen": {"evidenceLocations": [], "capabilityIds": [],
                         "proofIds": [], "acceptanceIds": [],
                         "observedResult": f"Evidence demonstrates retirement: {clause}"},
        })
    return obligations
