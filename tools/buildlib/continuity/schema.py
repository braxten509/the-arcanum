"""Pure schema constants and validators for versioned Phase-3 handoffs."""

HANDOFF_VERSION = 3
SUPPORTED_HANDOFF_VERSIONS = (2, 3)
MAX_HANDOFF_BYTES = 128_000
MAX_DISCOVERED_OBLIGATIONS = 24
HANDOFF_KEYS = {
    "version", "section", "artifact_state", "public_contracts", "discoveries",
    "fulfillments",
}
HANDOFF_V2_KEYS = {
    "version", "section", "artifact_state", "public_contracts", "obligations",
    "fulfillments",
}
CONTRACT_KEYS = {"name", "location", "promise"}
FULFILLMENT_KEYS = {
    "id", "evidence_locations", "capability_ids", "proof_ids", "acceptance_ids",
    "observed_result",
}
LEGACY_KEYS = {
    "version", "section", "artifact_state", "public_contracts", "future_obligations",
    "temporary_artifacts", "fulfills",
}


def exact_keys(value, expected, label, optional=()):
    if not isinstance(value, dict):
        return [f"{label} must be an object"]
    problems = []
    if expected - set(value):
        problems.append(f"{label} is missing keys: {sorted(expected - set(value))}")
    if set(value) - expected - set(optional):
        problems.append(f"{label} has unknown keys: {sorted(set(value) - expected - set(optional))}")
    return problems


def strings(value, label, allow_empty=True, maximum=300):
    if not isinstance(value, list):
        return [f"{label} must be an array"]
    problems = []
    if not allow_empty and not value:
        problems.append(f"{label} must not be empty")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            problems.append(f"{label}[{index}] must be a non-empty string")
        elif len(item) > maximum:
            problems.append(f"{label}[{index}] exceeds {maximum} characters")
    if len(value) != len(set(item for item in value if isinstance(item, str))):
        problems.append(f"{label} contains duplicates")
    return problems


def has_completion_key(value):
    if isinstance(value, dict):
        return (any(str(key).lower() in ("complete", "completed", "verified") for key in value)
                or any(has_completion_key(item) for item in value.values()))
    if isinstance(value, list):
        return any(has_completion_key(item) for item in value)
    return False
