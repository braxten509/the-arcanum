"""Authored TOML to strict shared assessment contracts."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
import tomllib

from arcanum_core.contracts.assessment import AssessmentContract


def _scenario(raw: dict) -> dict:
    kind = str(raw.get("kind") or "")
    expect = dict(raw.get("expect") or {})
    aliases = {
        "expectRegex": "regex", "expectExact": "exact", "expectJson": "json",
        "expectFile": "path", "expectFileRegex": "fileRegex",
    }
    for source, target in aliases.items():
        if source in raw:
            expect[target] = raw[source]
    if "exitCode" in raw:
        expect["exitCode"] = raw["exitCode"]
    return {
        "id": raw.get("id"), "kind": kind,
        "requirementIds": list(raw.get("requirementIds") or []),
        "capabilityIds": list(raw.get("capabilityIds") or []),
        "commandRef": raw.get("commandRef") or ("build" if kind == "build" else "run"),
        "args": list(raw.get("args") or []), "stdin": str(raw.get("stdin") or ""),
        "expect": expect, "timeout": int(raw.get("timeout") or 20),
        "public": bool(raw.get("public", False)),
    }


def _requirements(freestyle: dict) -> list[dict]:
    return [{
        "id": row.get("id"), "text": row.get("text"),
        "essential": row.get("essential"),
        "capabilityIds": list(row.get("capabilities") or row.get("capabilityIds") or []),
    } for row in freestyle.get("requirements") or []]


def _rubric(freestyle: dict) -> list[dict]:
    return [{
        "id": row.get("id"), "criterion": row.get("criterion"),
        "weight": row.get("weight"), "kind": row.get("kind"),
        "assessmentIds": list(row.get("assessmentIds") or []),
    } for row in freestyle.get("rubric") or []]


def load_working_contract(tome_root: str, section_id: str,
                          freestyle: dict | None = None) -> AssessmentContract:
    """Load one hidden section assessment and join its public requirement/rubric rows."""
    section_root = os.path.join(tome_root, "sections", section_id)
    if freestyle is None:
        with open(os.path.join(section_root, "freestyle.toml"), "rb") as handle:
            freestyle = tomllib.load(handle).get("freestyle") or {}
    with open(os.path.join(section_root, "assessment.toml"), "rb") as handle:
        hidden = tomllib.load(handle)
    value = {
        "version": hidden.get("version"),
        "requirements": _requirements(freestyle),
        "scenarios": [_scenario(row) for row in hidden.get("scenarios") or []],
        "rubric": _rubric(freestyle),
    }
    return AssessmentContract.from_dict(value)


def contract_dict(contract: AssessmentContract) -> dict:
    return {
        "version": contract.version,
        "requirements": [{
            "id": item.id, "text": item.text, "essential": item.essential,
            "capabilityIds": list(item.capability_ids),
        } for item in contract.requirements],
        "scenarios": [{
            "id": item.id, "kind": item.kind,
            "requirementIds": list(item.requirement_ids),
            "capabilityIds": list(item.capability_ids), "commandRef": item.command_ref,
            "args": list(item.args), "stdin": item.stdin, "expect": dict(item.expect),
            "timeout": item.timeout, "public": item.public,
        } for item in contract.scenarios],
        "rubric": [{
            "id": item.id, "criterion": item.criterion, "weight": item.weight,
            "kind": item.kind, "assessmentIds": list(item.assessment_ids),
        } for item in contract.rubric],
    }


def contract_digest(contract: AssessmentContract) -> str:
    payload = json.dumps(contract_dict(contract), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def public_requirements(contract: AssessmentContract) -> dict:
    """Learner payload excludes hidden argv, expectations, and scenario identities."""
    return {
        "version": contract.version,
        "requirements": [{"id": item.id, "text": item.text, "essential": item.essential,
                          "capabilityIds": list(item.capability_ids)}
                         for item in contract.requirements],
        "rubric": [{"id": item.id, "criterion": item.criterion, "weight": item.weight,
                    "kind": item.kind} for item in contract.rubric],
    }
