"""Course-map schema constants and small shape validators."""
from __future__ import annotations

import re

MAP_VERSION = 5
SUPPORTED_MAP_VERSIONS = (1, 2, 3, 4, 5)
MIN_PLANNED_LESSONS = 3
MAX_PLANNED_LESSONS = 8
ID_RE = re.compile(r"[A-Za-z0-9_-]+\Z")
CAPABILITY_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
LESSON_RE = re.compile(r"(s\d{2})\.l(\d{2})\Z")
LAB_RE = re.compile(r"(s\d{2})\.lab(\d{2})\Z")
OBLIGATION_RE = re.compile(r"s\d{2}-[a-z0-9][a-z0-9-]*\Z")
OBLIGATION_KINDS = {
    "future-requirement", "temporary-retirement", "contract-preservation", "plan-item",
}
SECTION_CHECKS = {"section-source", "section-replay", "continuity"}
TOP_KEYS = {
    "version", "revision", "buildId", "planSha256", "bounds", "graduateContract",
    "graduateCapabilities", "masteryPerformances", "acceptanceScenarios", "sections",
    "plannedObligations",
}
SECTION_KEYS = {
    "id", "ordinal", "title", "promise", "capabilities", "dependsOn", "nodes",
    "projectMilestone", "doneWhen",
}
LESSON_KEYS = {"id", "kind", "title", "teaches", "dependsOn", "doneWhen"}
WORKING_KEYS = {
    "id", "kind", "title", "requires", "dependsOn", "projectMilestone",
    "learnerOwnedArtifacts", "doneWhen",
}
LAB_KEYS = {
    "id", "kind", "title", "performanceKind", "capabilityIds", "cognitiveTasks",
    "contextRelation", "aidPolicy", "variantFamilyId", "rationaleRequired", "dependsOn",
    "doneWhen",
}
OBLIGATION_KEYS = {
    "id", "origin", "target", "kind", "owner", "location", "requirement", "reason",
    "doneWhen",
}
OBLIGATION_OPTIONAL_KEYS = {"supersedes", "revisionReason"}
OBLIGATION_DONE_KEYS = {
    "evidenceLocations", "capabilityIds", "proofIds", "acceptanceIds", "observedResult",
}


def keys(value, expected, label, optional=()):
    if not isinstance(value, dict):
        return [f"{label} must be an object"]
    missing = expected - set(value)
    extra = set(value) - expected - set(optional)
    out = []
    if missing:
        out.append(f"{label} is missing keys: {', '.join(sorted(missing))}")
    if extra:
        out.append(f"{label} has unknown keys: {', '.join(sorted(extra))}")
    return out


def strings(values, label, *, allow_empty=False, maximum=160):
    if not isinstance(values, list):
        return [f"{label} must be an array"]
    out = []
    if not values and not allow_empty:
        out.append(f"{label} must not be empty")
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value.strip():
            out.append(f"{label}[{index}] must be a non-empty string")
        elif len(value) > maximum:
            out.append(f"{label}[{index}] exceeds {maximum} characters")
    if len(values) != len(set(v for v in values if isinstance(v, str))):
        out.append(f"{label} contains duplicates")
    return out


def done_when(value, label):
    out = keys(value, {"checks"}, label)
    if isinstance(value, dict):
        out += strings(value.get("checks"), f"{label}.checks", maximum=80)
    return out


def obligation_done(value, label):
    out = keys(value, OBLIGATION_DONE_KEYS, label)
    if not isinstance(value, dict):
        return out
    for key in ("evidenceLocations", "capabilityIds", "proofIds", "acceptanceIds"):
        out += strings(value.get(key), f"{label}.{key}", allow_empty=True, maximum=240)
    observed = value.get("observedResult")
    if not isinstance(observed, str) or len(observed.strip()) < 8:
        out.append(f"{label}.observedResult must state the required observable result")
    elif len(observed) > 500:
        out.append(f"{label}.observedResult exceeds 500 characters")
    return out
