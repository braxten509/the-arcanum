"""Phase-1 Arc fields converted into a sealed mastery-evidence contract."""
from __future__ import annotations

import re

from arcanum_core.contracts.mastery import MasteryEvidenceContract

from .map_contract import validate_map_contract
from .policy import load_policy

CONTRACT_MARKER = "Mastery evidence contract"
CONTRACT_VERSION = 1


def _field(text: str, label: str) -> str:
    match = re.search(rf"(?im)^\*\*{re.escape(label)}:\*\*\s*(\S.*)$", str(text or ""))
    return match.group(1).strip() if match else ""


def required_by_plan(text: str) -> bool:
    return bool(re.search(
        rf"(?im)^- \*\*{re.escape(CONTRACT_MARKER)}:\*\*\s*{CONTRACT_VERSION}\s*$",
        str(text or "")))


def _arrow_ids(text: str, label: str) -> list[str]:
    raw = _field(text, label)
    return [item.strip() for item in raw.split(" -> ") if item.strip()]


def _performances(text: str) -> tuple[list[dict], list[str]]:
    raw = _field(text, "Mastery evidence performances")
    if not raw:
        return [], ["**Mastery evidence performances:** is missing"]
    records, problems = [], []
    pattern = re.compile(
        r"([a-z0-9]+(?:-[a-z0-9]+)*)\s*@\s*(s\d{2}\.(?:working|lab\d{2}))\s*=\s*"
        r"(guided-modification|familiar-independent-task|novel-transfer|"
        r"unfamiliar-tradeoff|architecture-defense)\s*\|\s*"
        r"(project|different|unrelated|unfamiliar)\s*\|\s*"
        r"(learning|limited|documentation-only|cold)\s*\|\s*"
        r"(rationale|no-rationale)\s*\|\s*"
        r"([a-z0-9]+(?:-[a-z0-9]+)*|none)\s*\|\s*"
        r"([a-z0-9-]+(?:\s*,\s*[a-z0-9-]+)*)\Z")
    for clause in raw.split(";"):
        clause = clause.strip()
        match = pattern.fullmatch(clause)
        if not match:
            problems.append(
                "invalid mastery evidence performance clause " + repr(clause)
                + "; expected `id @ sNN.working|labNN = kind | context | aid | "
                  "rationale|no-rationale | family|none | capability-id, ...`")
            continue
        pid, node, kind, context, aid, rationale, family, capabilities = match.groups()
        if ".lab" in node and family == "none":
            problems.append(f"mastery lab {node} requires a stable variant family id")
        if ".working" in node and family != "none":
            problems.append(f"Working {node} must use `none` as its variant family")
        records.append({
            "id": pid, "nodeId": node, "kind": kind,
            "capabilityIds": [item.strip() for item in capabilities.split(",")],
            "contextRelation": context, "aidPolicy": aid,
            "rationaleRequired": rationale == "rationale",
            "variantFamilyId": "" if family == "none" else family,
        })
    return records, problems


def seed_contract(text: str, sections: list[dict], language_contract: object) -> dict | None:
    if not required_by_plan(text):
        return None
    if not isinstance(language_contract, dict):
        raise ValueError("mastery evidence requires the languageMastery contract")
    level = language_contract.get("level")
    policy = load_policy()
    row = policy.for_level(level)
    performances, problems = _performances(text)
    tasks = _arrow_ids(text, "Mastery cognitive tasks")
    retention = _arrow_ids(text, "Mastery retention")
    value = {
        "version": 1, "level": level,
        "capabilityIds": list(language_contract.get("capabilityIds") or []),
        "foundationCapabilities": dict(language_contract.get("foundationCapabilities") or {}),
        "cognitiveTasks": tasks,
        "requiredPerformanceCount": row.late_performances,
        "standaloneLabCount": row.standalone_labs,
        "rationaleCount": row.rationales,
        "performances": performances,
        "retentionCapabilityIds": retention,
    }
    try:
        MasteryEvidenceContract.from_dict(value)
    except ValueError as exc:
        problems.append(str(exc))
    problems += validate_map_contract(value, sections, detailed=False, policy=policy)
    if problems:
        raise ValueError("Phase 1 mastery evidence contract is invalid:\n- " + "\n- ".join(problems))
    return value
