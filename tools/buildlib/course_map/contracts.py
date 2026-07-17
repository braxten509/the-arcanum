"""Cross-field proof contracts kept separate from the core map schema."""
import re


STABLE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def validate_semantic_contracts(value, capability_owners, section_ids, detailed):
    problems = []
    acceptance = set(value.get("acceptanceScenarios") or [])
    capabilities = set(capability_owners)
    for label, values in (("graduateCapabilities", value.get("graduateCapabilities") or []),
                          ("acceptanceScenarios", value.get("acceptanceScenarios") or [])):
        for item in values:
            if not STABLE_ID.fullmatch(str(item)):
                problems.append(f"{label} has invalid stable id {item!r}")
    if detailed:
        for section in value.get("sections") or []:
            if not isinstance(section, dict):
                continue
            for node in section.get("nodes") or []:
                if not isinstance(node, dict):
                    continue
                checks = set((node.get("doneWhen") or {}).get("checks") or [])
                required = ({"lesson-source", "learner-construction"}
                            if node.get("kind") == "lesson" else
                            {"working-replay", "learner-construction"})
                if checks != required:
                    problems.append(f"{node.get('id')}.doneWhen.checks must be exactly "
                                    f"{sorted(required)}")
    for index, obligation in enumerate(value.get("plannedObligations") or []):
        if not isinstance(obligation, dict):
            continue
        done = obligation.get("doneWhen") or {}
        label = f"plannedObligations[{index}].doneWhen"
        if detailed and not done.get("evidenceLocations"):
            problems.append(f"{label}.evidenceLocations must not be empty")
        for key, known in (("capabilityIds", capabilities),
                           ("proofIds", set(section_ids)),
                           ("acceptanceIds", acceptance)):
            for item in done.get(key) or []:
                if item not in known:
                    problems.append(f"{label}.{key} cites nonexistent id {item!r}")
    return problems
