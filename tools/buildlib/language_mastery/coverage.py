"""Versioned, mastery-owned language breadth profiles.

Project scope never enters this module.  A selected language finish determines the
minimum capability count and, when a language profile exists, concrete idiomatic
coverage areas which must be visible in stable capability ids.
"""
from __future__ import annotations

import os
import re
import tomllib


CONTRACT_MARKER = "Language coverage profile"
CONTRACT_VERSION = 1
PROFILE_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "global-configs", "language-mastery.toml"))
DEFAULT_MINIMUMS = {1: 5, 2: 7, 3: 12, 4: 15, 5: 18}


def required_by_plan(text):
    return bool(re.search(
        rf"(?im)^- \*\*{re.escape(CONTRACT_MARKER)}:\*\*\s*{CONTRACT_VERSION}\s*$",
        str(text or "")))


def _language_key(language):
    return re.sub(r"[^a-z0-9]+", "-", str(language or "").casefold()).strip("-")


def _config():
    try:
        with open(PROFILE_PATH, "rb") as handle:
            value = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return {"_profileError": f"cannot load {PROFILE_PATH}: {exc}"}
    return value if isinstance(value, dict) else {}


def profile_for(language, level):
    """Return the cumulative coverage profile for a language and Finish level."""
    try:
        level = int(level)
    except (TypeError, ValueError):
        level = 0
    config = _config()
    defaults = config.get("defaults") if isinstance(config.get("defaults"), dict) else {}
    raw_mins = defaults.get("minimumCapabilities") or []
    minimum = (raw_mins[level - 1] if level in range(1, 6)
               and len(raw_mins) >= level and isinstance(raw_mins[level - 1], int)
               else DEFAULT_MINIMUMS.get(level, 0))
    languages = config.get("languages") if isinstance(config.get("languages"), dict) else {}
    language_profile = languages.get(_language_key(language))
    levels = language_profile.get("levels") if isinstance(language_profile, dict) else {}
    areas = []
    for current in range(1, level + 1):
        row = levels.get(str(current)) if isinstance(levels, dict) else None
        if not isinstance(row, dict):
            continue
        row_minimum = row.get("minimumCapabilities")
        if isinstance(row_minimum, int) and not isinstance(row_minimum, bool):
            minimum = max(minimum, row_minimum)
        for area in row.get("areas") or []:
            if not isinstance(area, dict) or not isinstance(area.get("id"), str):
                continue
            areas.append({
                "id": area["id"],
                "description": str(area.get("description") or area["id"]),
                "tokenGroups": area.get("tokenGroups") or [],
                "distinctCapabilityGroups": area.get("distinctCapabilityGroups") is True,
            })
    return {
        "version": int(config.get("version") or CONTRACT_VERSION),
        "error": str(config.get("_profileError") or ""),
        "language": _language_key(language),
        "level": level,
        "minimumCapabilities": minimum,
        "areas": areas,
    }


def _capability_has_token(capability, token):
    body = str(capability or "").casefold().removeprefix("language-")
    token = str(token or "").casefold().strip("-")
    # Stable ids naturally use inflections (`collections`, `testing`, `debugging`).
    # Match only from a kebab-token boundary while allowing an alphanumeric suffix.
    return bool(token and re.search(
        rf"(?:^|-){re.escape(token)}[a-z0-9]*(?:-|$)", body))


def _distinct_group_matches(groups, capabilities):
    """Return whether token groups can be assigned to different capability ids."""
    candidates = []
    for group in groups:
        tokens = group if isinstance(group, list) else []
        candidates.append([
            capability for capability in capabilities
            if any(_capability_has_token(capability, token) for token in tokens)
        ])
    assigned = {}

    def place(group_index, visited):
        for capability in candidates[group_index]:
            if capability in visited:
                continue
            visited.add(capability)
            prior = assigned.get(capability)
            if prior is None or place(prior, visited):
                assigned[capability] = group_index
                return True
        return False

    return all(place(index, set()) for index in range(len(candidates)))


def coverage_problems(language, level, capabilities, *, expected_area_ids=None,
                      require_distinct_groups=False):
    """Check the generic floor plus every concrete area in a matching profile."""
    profile = profile_for(language, level)
    capabilities = capabilities if isinstance(capabilities, list) else []
    problems = []
    if profile["error"]:
        problems.append("language coverage profile infrastructure is unavailable: "
                        + profile["error"])
    if profile["version"] != CONTRACT_VERSION:
        problems.append(
            f"language coverage profile version must be {CONTRACT_VERSION}; "
            f"found {profile['version']}")
    if len(capabilities) < profile["minimumCapabilities"]:
        problems.append(
            f"{language or 'the declared language'} Finish {level}/5 needs at least "
            f"{profile['minimumCapabilities']} distinct language capabilities; found "
            f"{len(capabilities)}")
    area_ids = [area["id"] for area in profile["areas"]]
    if expected_area_ids is not None and list(expected_area_ids) != area_ids:
        problems.append(
            "languageMastery.coverageAreaIds must exactly match the selected versioned "
            f"profile: {area_ids}")
    for area in profile["areas"]:
        groups = area["tokenGroups"] if isinstance(area["tokenGroups"], list) else []
        missing_groups = []
        for group in groups:
            tokens = group if isinstance(group, list) else []
            if not any(_capability_has_token(capability, token)
                       for capability in capabilities for token in tokens):
                missing_groups.append("/".join(str(token) for token in tokens))
        if missing_groups:
            problems.append(
                f"{language} Finish {level}/5 coverage area {area['id']!r} "
                f"({area['description']}) is missing capability-id evidence for: "
                + ", ".join(missing_groups))
        elif (require_distinct_groups and area["distinctCapabilityGroups"]
              and len(groups) > 1 and not _distinct_group_matches(groups, capabilities)):
            labels = ["/".join(str(token) for token in group)
                      for group in groups if isinstance(group, list)]
            problems.append(
                f"{language} Finish {level}/5 coverage area {area['id']!r} "
                "must map its independently teachable token groups to distinct capability "
                "ids instead of one umbrella id: " + ", ".join(labels))
    return problems


def phase1_problems(plan, body, level, capabilities):
    if not required_by_plan(plan):
        return []
    language = re.search(r"(?im)^\*\*Language:\*\*\s*(\S.*)$", str(body or ""))
    return coverage_problems(
        language.group(1).strip() if language else "", level, capabilities,
        require_distinct_groups=True)


def seed_fields(language, level):
    profile = profile_for(language, level)
    return {
        "coverageProfileVersion": profile["version"],
        "coverageAreaIds": [area["id"] for area in profile["areas"]],
    }
