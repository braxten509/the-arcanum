"""Phase-1 language-mastery planning and seed validation."""
from __future__ import annotations

import math
import re

from .coverage import phase1_problems as coverage_phase1_problems
from .coverage import required_by_plan as coverage_required
from .coverage import seed_fields as coverage_seed_fields
from .foundations import block_field
from .foundations import contract_version as foundation_contract_version
from .foundations import coverage as foundation_coverage
from .foundations import phase1_problems as foundation_phase1_problems
from .foundations import required_by_plan as foundations_required
from .practice import practice_allocations
from .shared import (CONTRACT_VERSION, LANGUAGE_CAPABILITY, _field, _gate_int,
                     _performance_rule_problems, capability_spine, performance_specs,
                     required_by_plan)

def _first_capability_mention(capability, promises):
    pattern = re.compile(
        rf"(?<![a-z0-9-]){re.escape(str(capability or '').casefold())}(?![a-z0-9-])")
    return next((index for index, promise in enumerate(promises, 1)
                 if pattern.search(str(promise or "").casefold())), None)


def _phase1_cadence_problems(text, body, level, capabilities, section_promises):
    if level < 3 or not section_promises:
        return []
    problems = []
    mentions = {capability: _first_capability_mention(capability, section_promises)
                for capability in capabilities}
    unplaced = [capability for capability, ordinal in mentions.items() if ordinal is None]
    if unplaced:
        problems.append(
            "every language capability must appear in a Section-list promise so its Arc owner "
            "boundary is auditable before Phase 2: " + ", ".join(unplaced))
    if not foundations_required(text):
        return problems
    mapped, mapping_problems = foundation_coverage(
        body, version=foundation_contract_version(text), level=level)
    if mapping_problems:
        return problems
    midpoint = math.ceil(len(section_promises) / 2)
    late_foundations = []
    for role, capability in mapped.items():
        ordinal = mentions.get(capability)
        if ordinal is None:
            continue
        if ordinal > midpoint:
            late_foundations.append(f"{role}={capability} first appears in section {ordinal}")
    if late_foundations:
        problems.append(
            f"Finish {level}/5 must establish every mapped language foundation by the Arc "
            f"midpoint (section {midpoint}) before dependent integration: "
            + "; ".join(late_foundations))
    decomposition = mentions.get(mapped.get("decomposition"))
    verification = mentions.get(mapped.get("verification"))
    if (decomposition is not None and verification is not None
            and verification > decomposition + 1):
        problems.append(
            f"Finish {level}/5 verification cadence is too late: the verification capability "
            f"first appears in section {verification}, but decomposition first appears in "
            f"section {decomposition}; establish learner-authored verification no later than "
            "the following section")
    return problems


def phase1_contract_problems(text, body, section_ids, section_promises=None):
    """Validate that a new Arc makes language—not the project—the mastery target."""
    if not required_by_plan(text):
        return []
    problems = []
    language = _field(body, "Language")
    level = _gate_int(text, "Mastery (1-5)")
    declared = _field(body, "Language mastery")
    match = re.fullmatch(r"(.+?)\s+[—-]\s+Finish\s+([1-5])/5\s*:\s*(\S.+)", declared)
    if not language:
        problems.append("**Language:** must name the implementation language")
    if not match:
        problems.append(
            "**Language mastery:** must use `<Language> — Finish N/5: language exit ability`")
    else:
        named, declared_level, _ability = match.groups()
        if language and named.strip().casefold() != language.casefold():
            problems.append("**Language mastery:** must repeat **Language:** exactly")
        if int(declared_level) != level:
            problems.append("**Language mastery:** Finish level must match the Phase-0 Mastery answer")
    capabilities = capability_spine(body)
    if len(capabilities) < 4:
        problems.append(
            "**Language capability spine:** needs at least four distinct `language-*` "
            "capabilities so language fluency is not reduced to one project behavior")
    invalid = [item for item in capabilities if not LANGUAGE_CAPABILITY.fullmatch(item)]
    if invalid:
        problems.append("language capability ids must be lowercase `language-*` stable ids: "
                        + ", ".join(invalid))
    if len(capabilities) != len(set(capabilities)):
        problems.append("**Language capability spine:** contains duplicate capability ids")
    problems.extend(coverage_phase1_problems(text, body, level, capabilities))
    problems.extend(foundation_phase1_problems(text, body, level, capabilities))
    problems.extend(_phase1_cadence_problems(
        text, body, level, capabilities, section_promises or []))
    _allocations, allocation_problems = practice_allocations(
        text, section_ids, capabilities)
    problems.extend(allocation_problems)
    records, parse_problems = performance_specs(body)
    problems.extend(parse_problems)
    if not parse_problems:
        problems.extend(_performance_rule_problems(records, level, section_ids))
    mastery_proof = _field(body, "Mastery proof")
    if language and language.casefold() not in mastery_proof.casefold():
        problems.append(
            "**Mastery proof:** must explicitly name the language whose independence is graded")
    graduate = block_field(body, "Graduate ledger")
    language_named = bool(language and re.search(
        rf"(?<![\w-]){re.escape(language)}(?![\w-])", graduate, re.I))
    if language and not language_named:
        problems.append(
            "**Graduate ledger:** must repeat the exact **Language:** value "
            f"`{language}` so the graduate boundary is language-specific")
    if not re.search(r"\bCAN\b", graduate) or not re.search(r"\bCANNOT\b", graduate):
        problems.append(
            "**Graduate ledger:** must contain separate uppercase `CAN` and `CANNOT` clauses")
    return problems


def seed_contract(text, section_ids):
    if not required_by_plan(text):
        return None
    records, problems = performance_specs(text)
    if problems:
        raise ValueError("invalid Phase-1 language performances: " + "; ".join(problems))
    contract = {
        "version": CONTRACT_VERSION,
        "language": _field(text, "Language"),
        "level": _gate_int(text, "Mastery (1-5)"),
        "capabilityIds": capability_spine(text),
        "performances": records,
    }
    foundation_gate = foundation_phase1_problems(
        text, text, contract["level"], contract["capabilityIds"])
    if foundation_gate:
        raise ValueError("invalid Phase-1 language foundation evidence: "
                         + "; ".join(foundation_gate))
    if foundations_required(text):
        foundation_version = foundation_contract_version(text)
        mapped, problems = foundation_coverage(
            text, version=foundation_version, level=contract["level"])
        if problems:
            raise ValueError("invalid language foundation coverage: " + "; ".join(problems))
        contract["foundationVersion"] = foundation_version
        contract["foundationCapabilities"] = mapped
    if coverage_required(text):
        contract.update(coverage_seed_fields(contract["language"], contract["level"]))
    return contract
