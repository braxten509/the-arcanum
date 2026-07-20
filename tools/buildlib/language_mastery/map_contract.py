"""Phase-2 map validation for language ownership, practice, and transfer."""
from __future__ import annotations

import math

from .coverage import coverage_problems
from .foundations import contract_problems as foundation_contract_problems
from .shared import (CONTRACT_KEYS, CONTRACT_VERSION, KINDS, LANGUAGE_CAPABILITY,
                     OPTIONAL_CONTRACT_KEYS, PERFORMANCE_ID, PERFORMANCE_KEYS, RULES,
                     WORKING_ID, _performance_rule_problems)

def _list_of_strings(value, label, *, allow_empty=False, maximum=500):
    if not isinstance(value, list):
        return [f"{label} must be an array"]
    problems = []
    if not value and not allow_empty:
        problems.append(f"{label} must not be empty")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            problems.append(f"{label}[{index}] must be a non-empty string")
        elif len(item) > maximum:
            problems.append(f"{label}[{index}] exceeds {maximum} characters")
    if len(value) != len(set(item for item in value if isinstance(item, str))):
        problems.append(f"{label} contains duplicates")
    return problems

def validate_map_contract(contract, sections, capability_owners, graduate_capabilities,
                          detailed, seed=None, expected_working_performances=None):
    """Validate language capability ownership, cumulative practice, and graded transfer."""
    if contract is None:
        return []
    if not isinstance(contract, dict):
        return ["languageMastery must be an object"]
    problems = []
    missing = CONTRACT_KEYS - set(contract)
    extra = set(contract) - CONTRACT_KEYS - OPTIONAL_CONTRACT_KEYS
    if missing:
        problems.append("languageMastery is missing keys: " + ", ".join(sorted(missing)))
    if extra:
        problems.append("languageMastery has unknown keys: " + ", ".join(sorted(extra)))
    if contract.get("version") != CONTRACT_VERSION:
        problems.append(f"languageMastery.version must be {CONTRACT_VERSION}")
    if not isinstance(contract.get("language"), str) or not contract["language"].strip():
        problems.append("languageMastery.language must name the implementation language")
    level = contract.get("level")
    if not isinstance(level, int) or isinstance(level, bool) or level not in RULES:
        problems.append("languageMastery.level must be a whole number from 1 through 5")
        level = 0
    capabilities = contract.get("capabilityIds")
    problems += _list_of_strings(capabilities, "languageMastery.capabilityIds")
    capabilities = capabilities if isinstance(capabilities, list) else []
    for item in capabilities:
        if not LANGUAGE_CAPABILITY.fullmatch(str(item)):
            problems.append(f"languageMastery capability {item!r} must use a `language-*` stable id")
    missing_graduate = sorted(set(capabilities) - set(graduate_capabilities or []))
    if detailed and missing_graduate:
        problems.append("language mastery capabilities must be graduateCapabilities: "
                        + ", ".join(missing_graduate))
    performances = contract.get("performances")
    if not isinstance(performances, list):
        problems.append("languageMastery.performances must be an array")
        performances = []
    performance_ids, working_ids = [], {}
    for index, item in enumerate(performances):
        label = f"languageMastery.performances[{index}]"
        if not isinstance(item, dict):
            problems.append(f"{label} must be an object")
            continue
        missing, extra = PERFORMANCE_KEYS - set(item), set(item) - PERFORMANCE_KEYS
        if missing:
            problems.append(f"{label} is missing keys: {', '.join(sorted(missing))}")
        if extra:
            problems.append(f"{label} has unknown keys: {', '.join(sorted(extra))}")
        if not PERFORMANCE_ID.fullmatch(str(item.get("id") or "")):
            problems.append(f"{label}.id must be a stable language-performance-sNN-NN id")
        performance_ids.append(item.get("id"))
        if not WORKING_ID.fullmatch(str(item.get("workingId") or "")):
            problems.append(f"{label}.workingId must be sNN.working")
        if item.get("kind") not in KINDS:
            problems.append(f"{label}.kind is invalid")
        if not isinstance(item.get("rationaleRequired"), bool):
            problems.append(f"{label}.rationaleRequired must be a boolean")
        description = item.get("description")
        if not isinstance(description, str) or not 20 <= len(description.strip()) <= 500:
            problems.append(f"{label}.description must be 20 through 500 characters")
        problems += _list_of_strings(
            item.get("capabilityIds"), f"{label}.capabilityIds", allow_empty=not detailed)
        cited = item.get("capabilityIds") if isinstance(item.get("capabilityIds"), list) else []
        unknown = sorted(set(cited) - set(capabilities))
        if unknown:
            problems.append(f"{label}.capabilityIds are outside the language spine: "
                            + ", ".join(unknown))
        working_ids.setdefault(item.get("workingId"), []).append(item)
    if len(performance_ids) != len(set(performance_ids)):
        problems.append("languageMastery performance ids contain duplicates")
    foundation_version = contract.get("foundationVersion", 1)
    if (not isinstance(foundation_version, int) or isinstance(foundation_version, bool)
            or foundation_version not in (1, 2)):
        problems.append("languageMastery.foundationVersion must be 1 or 2")
        foundation_version = 1
    if "foundationCapabilities" in contract:
        problems += foundation_contract_problems(
            contract["foundationCapabilities"], capabilities, performances, level, detailed,
            foundation_version=foundation_version, language=contract.get("language", ""))
    if "coverageProfileVersion" in contract or "coverageAreaIds" in contract:
        if contract.get("coverageProfileVersion") != 1:
            problems.append("languageMastery.coverageProfileVersion must be 1")
        area_ids = contract.get("coverageAreaIds")
        problems += _list_of_strings(
            area_ids, "languageMastery.coverageAreaIds", allow_empty=True)
        problems += coverage_problems(
            contract.get("language", ""), level, capabilities,
            expected_area_ids=area_ids if isinstance(area_ids, list) else [])
    section_ids = [item.get("id") for item in sections if isinstance(item, dict)]
    if level in RULES:
        problems += _performance_rule_problems(performances, level, section_ids)
    for section in sections:
        if not isinstance(section, dict):
            continue
        sid = section.get("id")
        practice = section.get("languagePractice")
        problems += _list_of_strings(
            practice, f"{sid}.languagePractice", allow_empty=not detailed)
        practice = practice if isinstance(practice, list) else []
        unknown = sorted(set(practice) - set(capabilities))
        if unknown:
            problems.append(f"{sid}.languagePractice is outside the language spine: "
                            + ", ".join(unknown))
        working = next((node for node in section.get("nodes") or []
                        if isinstance(node, dict) and node.get("kind") == "working"), None)
        if detailed and working:
            missing_practice = sorted(set(practice) - set(working.get("requires") or []))
            if missing_practice:
                problems.append(f"{working.get('id')} must require every languagePractice id: "
                                + ", ".join(missing_practice))
            expected = ([item.get("id") for item in working_ids.get(working.get("id"), [])]
                        if expected_working_performances is None else
                        list(expected_working_performances.get(working.get("id"), [])))
            if list(working.get("masteryPerformances") or []) != expected:
                problems.append(
                    f"{working.get('id')}.masteryPerformances must exactly match {expected}")
        for capability in practice:
            owner = capability_owners.get(capability)
            if detailed and owner is None:
                problems.append(f"{sid}.languagePractice cites untaught capability {capability!r}")
            elif detailed and owner[1] > section.get("ordinal", 0):
                problems.append(f"{sid}.languagePractice uses {capability!r} before it is taught")
    strict_language_primary = detailed and level >= 3 and foundation_version >= 2
    if strict_language_primary:
        foundation = (contract.get("foundationCapabilities")
                      if isinstance(contract.get("foundationCapabilities"), dict) else {})
        midpoint = math.ceil(len(sections) / 2) if sections else 0
        late_foundation_owners = []
        for role, capability in foundation.items():
            owner = capability_owners.get(capability)
            if owner is not None and owner[1] > midpoint:
                late_foundation_owners.append(
                    f"{role}={capability} is owned in section {owner[1]}")
        if late_foundation_owners:
            problems.append(
                f"Finish {level}/5 mapped language foundations must be owned by the course "
                f"midpoint (section {midpoint}): " + "; ".join(late_foundation_owners))
        decomposition_owner = capability_owners.get(foundation.get("decomposition"))
        verification_id = foundation.get("verification")
        verification_owner = capability_owners.get(verification_id)
        if (decomposition_owner is not None and verification_owner is not None
                and verification_owner[1] > decomposition_owner[1] + 1):
            problems.append(
                f"Finish {level}/5 verification capability {verification_id!r} must be owned "
                "no later than the section after decomposition becomes available")
        practice_counts = {
            capability: sum(
                capability in (section.get("languagePractice") or [])
                for section in sections if isinstance(section, dict))
            for capability in capabilities
        }
        under_practiced = sorted(
            capability for capability, count in practice_counts.items() if count < 2)
        if under_practiced:
            problems.append(
                "Finish 3–5 must practice every language capability in at least two Workings: "
                + ", ".join(under_practiced))
        if verification_id:
            verification_practice = [
                section.get("ordinal", 0) for section in sections if isinstance(section, dict)
                and verification_id in (section.get("languagePractice") or [])
            ]
            late_start = math.floor(2 * len(sections) / 3) + 1 if sections else 1
            owner_ordinal = verification_owner[1] if verification_owner is not None else 0
            if len(verification_practice) < 3:
                problems.append(
                    f"Finish {level}/5 learner-authored verification must be practiced in at "
                    f"least three Workings; found {len(verification_practice)}")
            if not any(owner_ordinal < ordinal < late_start
                       for ordinal in verification_practice):
                problems.append(
                    f"Finish {level}/5 learner-authored verification needs representative "
                    "practice after its owner and before the late-performance third")
        final_working = next(
            (node for node in ((sections[-1].get("nodes") or []) if sections else [])
             if isinstance(node, dict) and node.get("kind") == "working"), None)
        if final_working:
            omitted_final = sorted(
                set(capabilities) - set(final_working.get("requires") or []))
            if omitted_final:
                problems.append(
                    "Finish 3–5 final Working must require every declared language capability: "
                    + ", ".join(omitted_final))
        assessed = {capability for item in performances if isinstance(item, dict)
                    for capability in (item.get("capabilityIds") or [])}
        omitted_assessment = sorted(set(capabilities) - assessed)
        if omitted_assessment:
            problems.append(
                "Finish 3–5 late language performances must assess every declared language "
                "capability: " + ", ".join(omitted_assessment))
    if detailed:
        for capability in capabilities:
            if capability not in capability_owners:
                problems.append(f"language mastery capability {capability!r} has no teaching owner")
        nodes = {node.get("id"): node for section in sections if isinstance(section, dict)
                 for node in section.get("nodes") or [] if isinstance(node, dict)}
        for working_id, records in working_ids.items():
            working = nodes.get(working_id)
            if not working or working.get("kind") != "working":
                problems.append(f"language mastery performance names missing Working {working_id!r}")
                continue
            for item in records:
                missing_required = sorted(
                    set(item.get("capabilityIds") or []) - set(working.get("requires") or []))
                if missing_required:
                    problems.append(f"{working_id} must require performance capabilities: "
                                    + ", ".join(missing_required))
    if seed is not None:
        if not isinstance(seed, dict):
            problems.append("seed languageMastery contract is missing")
        else:
            for key in ("version", "language", "level", "capabilityIds"):
                if contract.get(key) != seed.get(key):
                    problems.append(f"Phase 2 may not alter seeded languageMastery.{key}")
            if contract.get("foundationVersion") != seed.get("foundationVersion"):
                problems.append("Phase 2 may not alter seeded languageMastery.foundationVersion")
            if contract.get("foundationCapabilities") != seed.get("foundationCapabilities"):
                problems.append("Phase 2 may not alter seeded "
                                "languageMastery.foundationCapabilities")
            if contract.get("coverageProfileVersion") != seed.get("coverageProfileVersion"):
                problems.append("Phase 2 may not alter seeded "
                                "languageMastery.coverageProfileVersion")
            if contract.get("coverageAreaIds") != seed.get("coverageAreaIds"):
                problems.append("Phase 2 may not alter seeded languageMastery.coverageAreaIds")
            old = seed.get("performances") or []
            if len(old) != len(performances):
                problems.append("Phase 2 may not add or remove seeded language performances")
            for index, original in enumerate(old):
                current = performances[index] if index < len(performances) else {}
                for key in PERFORMANCE_KEYS - {"capabilityIds"}:
                    if current.get(key) != original.get(key):
                        problems.append(
                            f"Phase 2 may not alter language performance {index + 1} field {key}")
    return problems
