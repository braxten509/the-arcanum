"""Cross-field proof contracts kept separate from the core map schema."""
import re

from .schema import check_set


STABLE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def validate_semantic_contracts(value, capability_owners, section_ids, detailed):
    problems = []
    acceptance_values = value.get("acceptanceScenarios")
    acceptance = ({item for item in acceptance_values if isinstance(item, str)}
                  if isinstance(acceptance_values, list) else set())
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
                checks = check_set(node.get("doneWhen"))
                if checks is None:
                    # The schema layer already emitted the precise authored finding.
                    continue
                required = ({"lesson-source", "learner-construction"}
                            if node.get("kind") == "lesson" else
                            {"learner-evidence", "variant-proof"}
                            if node.get("kind") == "mastery-lab" else
                            {"working-replay", "learner-construction"})
                if checks != required:
                    problems.append(f"{node.get('id')}.doneWhen.checks must be exactly "
                                    f"{sorted(required)}")
    for index, obligation in enumerate(value.get("plannedObligations") or []):
        if not isinstance(obligation, dict):
            continue
        done = obligation.get("doneWhen")
        label = f"plannedObligations[{index}].doneWhen"
        if not isinstance(done, dict):
            # The schema layer already emitted the precise authored finding.
            continue
        if detailed and not done.get("evidenceLocations"):
            problems.append(f"{label}.evidenceLocations must not be empty")
        for key, known in (("capabilityIds", capabilities),
                           ("proofIds", set(section_ids)),
                           ("acceptanceIds", acceptance)):
            values = done.get(key)
            if not isinstance(values, list):
                continue
            for item in values:
                if not isinstance(item, str):
                    continue
                if item not in known:
                    problems.append(f"{label}.{key} cites nonexistent id {item!r}")
    return problems
