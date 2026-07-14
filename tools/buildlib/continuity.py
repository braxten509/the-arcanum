"""Durable, machine-checked handoffs between bounded split-section workers.

The tome itself remains the source of teaching truth. These small build sidecars preserve
the exact cross-section contracts a later worker must verify against that truth: stable
names/APIs, deliberately temporary scaffolding, and promises aimed at a future section.
"""
import json
import os
import re
import shutil

from . import BUILD_DIR, REPO


HANDOFF_VERSION = 1
MAX_HANDOFF_BYTES = 6_000
OBLIGATION_ID = re.compile(r"s\d{2}-[a-z0-9][a-z0-9-]*\Z")
HANDOFF_KEYS = {
    "version", "section", "artifact_state", "public_contracts",
    "future_obligations", "temporary_artifacts", "fulfills",
}
ITEM_KEYS = {
    "public_contracts": {"name", "location", "promise"},
    "future_obligations": {"id", "target", "location", "requirement", "reason"},
    "temporary_artifacts": {"id", "target", "location", "artifact", "retirement"},
    "fulfills": {"id", "location", "evidence"},
}
ITEM_LIMITS = {"public_contracts": 12, "future_obligations": 10,
               "temporary_artifacts": 8, "fulfills": 20}


def handoff_dir(tid):
    return os.path.join(BUILD_DIR, f"{tid}.handoffs")


def handoff_path(tid, sid):
    return os.path.join(handoff_dir(tid), f"{sid}.json")


def handoffs_exist(tid):
    return os.path.isdir(handoff_dir(tid))


def reset_handoffs(tid):
    shutil.rmtree(handoff_dir(tid), ignore_errors=True)


def handoff_skeleton(sid, ids, plan_path=None):
    """Preseed deterministic structure and Phase-1 obligations for a section worker."""
    outgoing = []
    fulfills = []
    for edge in planned_edges(plan_path, ids) if plan_path else []:
        if edge["origin"] == sid:
            outgoing.append({
                "id": edge["id"],
                "target": edge["target"],
                "location": "",
                "requirement": edge["requirement"],
                "reason": "",
            })
        elif edge["target"] == sid:
            fulfills.append({
                "id": edge["id"],
                "location": "",
                "evidence": "",
            })
    return {
        "version": HANDOFF_VERSION,
        "section": sid,
        "artifact_state": "",
        "public_contracts": [],
        "future_obligations": outgoing,
        "temporary_artifacts": [],
        "fulfills": fulfills,
    }


def prepare_handoff(tid, sid, reset=False, ids=None, plan_path=None):
    """Create the writable sidecar, optionally with a deterministic handoff skeleton."""
    path = handoff_path(tid, sid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    initialize = reset or not os.path.exists(path)
    if not initialize:
        try:
            initialize = os.path.getsize(path) == 0
        except OSError:
            initialize = True
    if initialize:
        with open(path, "w", encoding="utf-8") as handle:
            if ids is not None:
                json.dump(handoff_skeleton(sid, ids, plan_path), handle, indent=2)
                handle.write("\n")
    return path


def _load(path):
    try:
        if os.path.getsize(path) > MAX_HANDOFF_BYTES:
            return None, f"handoff exceeds {MAX_HANDOFF_BYTES} bytes; keep it a compact contract"
        with open(path, encoding="utf-8") as f:
            value = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"handoff is missing or invalid JSON: {exc}"
    return value, ""


def _safe_location(tid, sid, raw):
    if not isinstance(raw, str) or not raw.strip():
        return False
    root = os.path.realpath(os.path.join(REPO, "tomes", tid, "sections", sid))
    target = os.path.realpath(os.path.join(root, raw))
    return target.startswith(root + os.sep) and os.path.isfile(target)


def planned_edges(plan_path, ids):
    """Parse Phase 1's one-line `sNN -> sMM: promise` continuity-map edges."""
    try:
        text = open(plan_path, encoding="utf-8").read()
    except OSError:
        return []
    match = re.search(r"(?i)\*\*Continuity map:\*\*", text)
    if not match:
        return []
    tail = text[match.end():]
    block = re.split(r"(?m)^\*\*[^\n]+:\*\*", tail, maxsplit=1)[0]
    parsed = []
    counts = {}
    positions = {section: i for i, section in enumerate(ids)}
    for origin, target, requirement in re.findall(
            r"(?im)^\s*(?:[-*]\s*)?(s\d{2})\s*->\s*(s\d{2})\s*:\s*(\S.*)$", block):
        key = (origin.lower(), target.lower())
        counts[key] = counts.get(key, 0) + 1
        origin, target = key
        parsed.append({
            "id": f"{origin}-plan-{target}-{counts[key]:02d}",
            "origin": origin,
            "target": target,
            "requirement": requirement.strip(),
            "valid_order": (origin in positions and target in positions
                            and positions[origin] < positions[target]),
        })
    return parsed


def _prior_obligations(tid, sid, ids, plan_path=None):
    """Return id -> (target, origin, requirement) for obligations written before sid."""
    out = {}
    stop = ids.index(sid)
    for edge in planned_edges(plan_path, ids) if plan_path else []:
        if edge["origin"] in ids[:stop]:
            out[edge["id"]] = (edge["target"], edge["origin"], edge["requirement"])
    for origin in ids[:stop]:
        data, _ = _load(handoff_path(tid, origin))
        if not isinstance(data, dict):
            continue
        for item in data.get("future_obligations", []):
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                out[item.get("id")] = (item.get("target"), origin,
                                        item.get("requirement", ""))
        for item in data.get("temporary_artifacts", []):
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                out[item.get("id")] = (item.get("target"), origin,
                                        item.get("retirement", ""))
    return out


def validate_handoff(tid, sid, ids, plan_path=None):
    """Validate one handoff and require exact evidence for every obligation due here."""
    path = handoff_path(tid, sid)
    data, problem = _load(path)
    if problem:
        return False, f"{os.path.relpath(path, REPO)}: {problem}"
    problems = []
    if not isinstance(data, dict):
        return False, f"{os.path.relpath(path, REPO)}: top level must be a JSON object"
    if set(data) != HANDOFF_KEYS:
        missing = sorted(HANDOFF_KEYS - set(data))
        extra = sorted(set(data) - HANDOFF_KEYS)
        if missing:
            problems.append("missing keys: " + ", ".join(missing))
        if extra:
            problems.append("unknown keys: " + ", ".join(extra))
    if data.get("version") != HANDOFF_VERSION:
        problems.append(f"version must be {HANDOFF_VERSION}")
    if data.get("section") != sid:
        problems.append(f"section must be {sid!r}")
    state = data.get("artifact_state")
    if not isinstance(state, str) or len(state.strip()) < 20:
        problems.append("artifact_state must compactly describe the cumulative learner artifact")
    elif len(state) > 1200:
        problems.append("artifact_state is over 1200 characters; keep the handoff compact")

    positions = {section: i for i, section in enumerate(ids)}
    introduced_ids = set()
    introduced = {}
    for list_name, expected_keys in ITEM_KEYS.items():
        items = data.get(list_name)
        if not isinstance(items, list):
            problems.append(f"{list_name} must be a JSON array")
            continue
        if len(items) > ITEM_LIMITS[list_name]:
            problems.append(f"{list_name} has over {ITEM_LIMITS[list_name]} items; "
                            "consolidate related contracts")
        if list_name == "public_contracts" and not items:
            problems.append("public_contracts needs at least one exact API/file/workflow contract")
        for n, item in enumerate(items):
            label = f"{list_name}[{n}]"
            if not isinstance(item, dict):
                problems.append(f"{label} must be an object")
                continue
            if set(item) != expected_keys:
                problems.append(f"{label} keys must be exactly {sorted(expected_keys)}")
                continue
            for key, value in item.items():
                if not isinstance(value, str) or not value.strip():
                    problems.append(f"{label}.{key} must be a non-empty string")
                elif len(value) > 800:
                    problems.append(f"{label}.{key} is over 800 characters")
            if not _safe_location(tid, sid, item.get("location")):
                problems.append(f"{label}.location must name an existing file inside section {sid}")
            if list_name in ("future_obligations", "temporary_artifacts"):
                oid = item.get("id", "")
                target = item.get("target")
                if (not isinstance(oid, str) or not OBLIGATION_ID.fullmatch(oid)
                        or not oid.startswith(sid + "-")):
                    problems.append(f"{label}.id must be a kebab id beginning {sid}-")
                if oid in introduced_ids:
                    problems.append(f"duplicate obligation id {oid!r} in section {sid}")
                introduced_ids.add(oid)
                introduced[oid] = item
                if target not in positions or positions.get(target, -1) <= positions.get(sid, -1):
                    problems.append(f"{label}.target must be a later section id")

    outgoing = [edge for edge in planned_edges(plan_path, ids)
                if edge["origin"] == sid] if plan_path else []
    for edge in outgoing:
        item = introduced.get(edge["id"])
        if not edge["valid_order"]:
            problems.append(f"Phase 1 Continuity-map edge {edge['id']} must point to a later section")
        elif item is None:
            problems.append(f"missing planned outgoing obligation {edge['id']} -> {edge['target']}")
        else:
            actual_text = item.get("requirement", item.get("retirement", "")).strip()
            if item.get("target") != edge["target"]:
                problems.append(f"planned obligation {edge['id']} target must be {edge['target']}")
            if actual_text != edge["requirement"]:
                problems.append(f"planned obligation {edge['id']} must copy its Phase 1 requirement exactly")

    prior = _prior_obligations(tid, sid, ids, plan_path)
    due = {oid for oid, (target, _, _) in prior.items() if target == sid}
    fulfills = data.get("fulfills") if isinstance(data.get("fulfills"), list) else []
    claimed = {item.get("id") for item in fulfills
               if isinstance(item, dict) and isinstance(item.get("id"), str)}
    missing_due = sorted(due - claimed)
    unknown = sorted(oid for oid in claimed if oid not in prior or prior[oid][0] != sid)
    if missing_due:
        problems.append("fulfills is missing obligations due now: " + ", ".join(missing_due))
    if unknown:
        problems.append("fulfills claims unknown or not-yet-due ids: " + ", ".join(unknown))
    if len(claimed) != len(fulfills):
        problems.append("fulfills contains a duplicate or malformed id")
    prefix = os.path.relpath(path, REPO)
    return (not problems, "" if not problems else prefix + ":\n- " + "\n- ".join(problems))


def validate_all_handoffs(tid, ids, plan_path=None):
    reports = []
    all_ids = set()
    for edge in planned_edges(plan_path, ids) if plan_path else []:
        if not edge["valid_order"]:
            reports.append(f"Phase 1 Continuity-map edge {edge['id']} must use real section "
                           "ids and point forward")
    for sid in ids:
        ok, report = validate_handoff(tid, sid, ids, plan_path)
        if not ok:
            reports.append(report)
            continue
        data, _ = _load(handoff_path(tid, sid))
        for kind in ("future_obligations", "temporary_artifacts"):
            for item in data[kind]:
                oid = item["id"]
                if oid in all_ids:
                    reports.append(f"duplicate obligation id across handoffs: {oid}")
                all_ids.add(oid)
    return (not reports, "\n".join(reports))


def _read_valid_prior(tid, sid, ids, plan_path=None):
    out = []
    for prior in ids[:ids.index(sid)]:
        data, _ = _load(handoff_path(tid, prior))
        valid, _ = validate_handoff(tid, prior, ids, plan_path)
        if valid and isinstance(data, dict):
            out.append(data)
    return out


def continuity_prompt(tid, sid, ids, plan_path=None):
    """Prompt block with a compact prior-contract index and current handoff protocol."""
    prior = _read_valid_prior(tid, sid, ids, plan_path)
    current_position = ids.index(sid)
    lines = []
    contracts = {}
    for data in prior:
        origin = data.get("section", "?")
        for item in data.get("public_contracts", []):
            contracts[item.get("name")] = (origin, item)
        for kind, text_key in (("future_obligations", "requirement"),
                               ("temporary_artifacts", "retirement")):
            for item in data.get(kind, []):
                target = item.get("target")
                if target in ids and ids.index(target) < current_position:
                    continue  # already closed by its target; the whole-tome audit retains it
                marker = "DUE NOW" if target == sid else f"due {target}"
                lines.append(f"- OBLIGATION [{marker}] {item.get('id')}: "
                             f"{item.get(text_key, '')}")
    if prior:
        latest = prior[-1]
        lines.insert(0, f"Latest cumulative state after {latest.get('section')}: "
                        f"{latest.get('artifact_state', '')}")
    contract_lines = [f"- CONTRACT INDEX {name} @ {origin}/{item.get('location')}"
                      for name, (origin, item) in contracts.items()]
    lines[1:1] = contract_lines
    ledger = "\n".join(lines).strip() or "(first section: no prior handoffs)"
    planned = []
    for edge in planned_edges(plan_path, ids) if plan_path else []:
        if edge["origin"] == sid:
            planned.append(f"- REQUIRED OUTGOING {edge['id']} -> {edge['target']}: "
                           f"{edge['requirement']}")
        elif edge["target"] == sid:
            planned.append(f"- DUE NOW {edge['id']} from {edge['origin']}: "
                           f"{edge['requirement']}")
    planned_block = "\n".join(planned) or "(no Phase 1 edge starts or ends here)"
    rel = os.path.relpath(handoff_path(tid, sid), REPO)
    later = ", ".join(ids[ids.index(sid) + 1:]) or "none (this is the final section)"
    return f"""

===== DURABLE CROSS-SECTION CONTINUITY =====
The Phase 1 `Continuity map` is the planned dependency graph. The block below is a
compact index of ACTUAL contracts emitted by finished workers. It is injected by the
harness; do not rely on only the immediately previous section. Promise prose is not
duplicated here: before reusing or changing any named contract, open its cited owner
file and compare the real lesson/code on disk. If the intended promise is unclear, open
`.tome-build/{tid}.handoffs/<origin>.json` for its exact text. The files are the source
of truth.

{ledger}

Phase 1 edges involving {sid} (these are deterministic requirements, not suggestions):
{planned_block}

Before stopping, write `{rel}` as strict JSON with EXACTLY this shape:
{{
  "version": 1,
  "section": "{sid}",
  "artifact_state": "compact description of the cumulative learner artifact after {sid}",
  "public_contracts": [{{"name": "exact API/file/data/workflow name", "location": "lessons/l01.toml", "promise": "what later sections must preserve or deliberately replace"}}],
  "future_obligations": [{{"id": "{sid}-specific-kebab-id", "target": "later section id", "location": "freestyle.toml", "requirement": "literal future requirement", "reason": "why it must survive"}}],
  "temporary_artifacts": [{{"id": "{sid}-specific-kebab-id", "target": "later section id", "location": "lessons/l01.toml", "artifact": "temporary scaffold/debug/demo", "retirement": "exact removal or replacement required"}}],
  "fulfills": [{{"id": "prior obligation marked DUE NOW", "location": "lessons/l02.toml", "evidence": "how this section actually satisfies it"}}]
}}
Locations are relative to `tomes/{tid}/sections/{sid}/` and must exist. Record exact
names, signatures, values, coordinate systems, state ownership, files, launch paths,
and learner-visible promises—not vague reminders to stay consistent. Every prior
obligation marked DUE NOW must appear in `fulfills` with real evidence. Create a future
obligation whenever a later section must honor something introduced here, especially a
non-adjacent reuse; every temporary artifact needs its retirement target. Every
REQUIRED OUTGOING edge must appear under `future_obligations` (or under
`temporary_artifacts` when it is specifically a retirement) with its displayed id,
target, and requirement/retirement text copied exactly. Allowed later
targets: {later}. Use [] where a list is genuinely empty. The final section may not leave
future obligations or temporary artifacts. Keep the entire handoff under
{MAX_HANDOFF_BYTES} bytes. This sidecar is build memory, not tome content.
"""


def reconciliation_prompt(tid, ids, plan_path=None):
    """Whole-tome audit block: all handoffs and their claimed evidence."""
    blocks = []
    for sid in ids:
        data, problem = _load(handoff_path(tid, sid))
        if problem:
            blocks.append(f"{sid}: INVALID HANDOFF — {problem}")
        else:
            outgoing = [item["id"] for kind in ("future_obligations", "temporary_artifacts")
                        for item in data[kind]]
            fulfilled = [item["id"] for item in data["fulfills"]]
            rel = os.path.relpath(handoff_path(tid, sid), REPO)
            blocks.append(f"- {sid} `{rel}`: {len(data['public_contracts'])} contracts; "
                          f"outgoing={outgoing or 'none'}; fulfills={fulfilled or 'none'}")
    ok, report = validate_all_handoffs(tid, ids, plan_path)
    status = "CLOSED" if ok else "BROKEN\n" + report
    return ("\n\n===== WHOLE-TOME CONTINUITY AUDIT =====\n"
            "These per-section handoffs are claims, not evidence. Verify every cited location, "
            "every fulfillment, every stable contract in the final cumulative artifact, and every "
            "temporary artifact's retirement against the tome files. Fix the TOME when a claim and "
            "the lesson disagree. If a legitimate repair relocates existing evidence, update the "
            "handoff's exact location only after verifying the new file. Never erase an obligation "
            "or rewrite a claim merely to paper over a teaching gap.\n"
            "Open EVERY indexed JSON file; the index intentionally stays compact so the reviewer "
            "spends context on the tome, not duplicated handoff text.\n"
            f"Deterministic handoff gate: {status}\n" + "\n".join(blocks))
