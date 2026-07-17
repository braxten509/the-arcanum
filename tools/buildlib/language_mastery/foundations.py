"""Language-neutral foundation coverage for mastery-bearing course maps."""
from __future__ import annotations

import os
import re
import tomllib


CONTRACT_MARKER = "Language foundation contract"
CONTRACT_VERSION = 2
SUPPORTED_VERSIONS = (1, 2)
BASE_ROLES = ("data", "control", "decomposition", "failure", "verification")
CAPABLE_ROLES = ("data", "control", "decomposition", "abstraction", "modularity",
                 "failure", "verification")
CAPABILITY = re.compile(r"language-[a-z0-9]+(?:-[a-z0-9]+)*\Z")
VERIFICATION_WORD = re.compile(
    r"(?:^|-)(?:verif(?:y|ication)?|test(?:ing)?|check(?:ing)?|assert(?:ion)?|"
    r"validat(?:e|ion)?|debug(?:ging)?|diagnos(?:e|is|tic)?|inspect(?:ion)?|"
    r"proof|quality)(?:-|$)", re.I)
VERIFICATION_EVIDENCE = re.compile(
    r"\b(?:verif(?:y|ies|ied|ication)|test(?:s|ed|ing)?|check(?:s|ed|ing)?|"
    r"assert(?:s|ed|ion)?|validat(?:e|es|ed|ion)|debug(?:s|ged|ging)?|"
    r"diagnos(?:e|es|ed|is|tic)|inspect(?:s|ed|ion)?|proof|observable)\b", re.I)
ABSTRACTION_WORD = re.compile(
    r"(?:^|-)(?:class(?:es)?|object(?:s)?|struct(?:s)?|trait(?:s)?|interface(?:s)?|"
    r"protocol(?:s)?|record(?:s)?|encapsulation|composition|type-model(?:ing)?|"
    r"sum-type|product-type|algebraic-data)(?:-|$)", re.I)
MODULARITY_WORD = re.compile(
    r"(?:^|-)(?:module(?:s)?|package(?:s)?|namespace(?:s)?|component(?:s)?|"
    r"layer(?:s)?|import(?:s)?|dependency|dependencies|boundary|boundaries)(?:-|$)", re.I)
PROFILE_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "global-configs", "language-mastery.toml"))


def _profile_abstraction_tokens(language):
    """Load an extensible language policy without putting language cases in the engine."""
    key = re.sub(r"[^a-z0-9]+", "-", str(language or "").casefold()).strip("-")
    try:
        with open(PROFILE_PATH, "rb") as handle:
            profiles = tomllib.load(handle).get("languages") or {}
    except (OSError, tomllib.TOMLDecodeError):
        return []
    profile = profiles.get(key) if isinstance(profiles, dict) else None
    tokens = profile.get("requiredAbstractionTokens") if isinstance(profile, dict) else []
    return [token.casefold() for token in tokens
            if isinstance(token, str) and re.fullmatch(r"[a-z0-9]+", token)]


def _has_capability_token(capability, tokens):
    parts = str(capability or "").removeprefix("language-").casefold().split("-")
    return any(token in parts for token in tokens)


def line_field(text, label):
    match = re.search(rf"(?im)^\*\*{re.escape(label)}:\*\*\s*(\S.*)$", str(text or ""))
    return match.group(1).strip() if match else ""


def block_field(text, label):
    """Read a bold Arc field through its next bold field, including wrapped prose."""
    text = str(text or "")
    match = re.search(rf"(?im)^\*\*{re.escape(label)}:\*\*\s*(.*)$", text)
    if not match:
        return ""
    tail = re.split(r"(?m)^\*\*[^\n]+:\*\*", text[match.end():], 1)[0]
    return " ".join((match.group(1) + "\n" + tail).split())


def contract_version(text):
    match = re.search(
        rf"(?im)^- \*\*{re.escape(CONTRACT_MARKER)}:\*\*\s*([0-9]+)\s*$",
        str(text or ""))
    return int(match.group(1)) if match and int(match.group(1)) in SUPPORTED_VERSIONS else 0


def required_by_plan(text):
    return bool(contract_version(text))


def roles_for(version, level):
    """Return the language-neutral foundation packet for this sealed contract."""
    return CAPABLE_ROLES if version >= 2 and level >= 3 else BASE_ROLES


def coverage(text, *, version=None, level=0):
    """Parse `role = language-capability` clauses without guessing synonyms."""
    version = version or contract_version(text) or CONTRACT_VERSION
    roles = roles_for(version, level)
    raw = line_field(text, "Language foundation coverage")
    if not raw:
        return {}, ["**Language foundation coverage:** is missing"]
    values, problems = {}, []
    for raw_clause in raw.split(";"):
        clause = raw_clause.strip()
        match = re.fullmatch(r"([a-z]+)\s*=\s*(language-[a-z0-9-]+)", clause)
        if not match:
            problems.append(
                f"invalid language foundation clause {clause!r}; expected "
                "`role = language-capability`")
            continue
        role, capability = match.groups()
        if role in values:
            problems.append(f"duplicate language foundation role {role!r}")
        values[role] = capability
    missing, extra = set(roles) - set(values), set(values) - set(roles)
    if missing:
        problems.append("language foundation coverage is missing roles: "
                        + ", ".join(sorted(missing)))
    if extra:
        problems.append("language foundation coverage has unknown roles: "
                        + ", ".join(sorted(extra)))
    invalid = [value for value in values.values() if not CAPABILITY.fullmatch(value)]
    if invalid:
        problems.append("language foundation coverage has invalid capability ids: "
                        + ", ".join(invalid))
    if len(values.values()) != len(set(values.values())):
        problems.append("each language foundation role must map to a distinct capability")
    return values, problems


def phase1_problems(text, body, level, capabilities):
    if not required_by_plan(text):
        return []
    version = contract_version(text)
    mapped, problems = coverage(body, version=version, level=level)
    unknown = sorted(set(mapped.values()) - set(capabilities))
    if unknown:
        problems.append("language foundation coverage must use capability-spine ids: "
                        + ", ".join(unknown))
    verification = mapped.get("verification", "")
    if verification and not VERIFICATION_WORD.search(verification.removeprefix("language-")):
        problems.append(
            "verification must map to an explicitly verification-oriented language capability "
            "id (for example language-verification, language-testing, or language-diagnostics); "
            f"{verification!r} does not establish verification")
    abstraction = mapped.get("abstraction", "")
    if abstraction and not ABSTRACTION_WORD.search(abstraction.removeprefix("language-")):
        problems.append(
            "Finish 3–5 abstraction must map to a concrete structured-abstraction idiom "
            "(for example classes/objects, structs/traits, interfaces/protocols, records, "
            f"or algebraic data types); {abstraction!r} is too generic")
    language = line_field(body, "Language")
    required_abstraction = _profile_abstraction_tokens(language)
    if abstraction and required_abstraction and not _has_capability_token(
            abstraction, required_abstraction):
        problems.append(
            f"{language} Finish 3–5 structured abstraction requires a capability naming "
            + " or ".join(required_abstraction) + f"; got {abstraction!r}")
    modularity = mapped.get("modularity", "")
    if modularity and not MODULARITY_WORD.search(modularity.removeprefix("language-")):
        problems.append(
            "Finish 3–5 modularity must map to an explicit module, package, namespace, "
            f"component, layer, import, dependency, or boundary capability; {modularity!r} "
            "does not establish modularity")
    if level >= 3 and not re.search(r"\berrors\s*=\s*CAN\b", body, re.I):
        problems.append("Finish 3–5 requires **Daily drivers:** `errors = CAN`; "
                        "routine failure handling and diagnosis cannot be scoped out")
    performances = line_field(body, "Language performances")
    if level >= 3 and performances and not VERIFICATION_EVIDENCE.search(performances):
        problems.append(
            "Finish 3–5 **Language performances:** must include a late observable "
            "verification, test, check, diagnosis, or inspection action before Phase 1 "
            "seals their descriptions")
    return problems


def contract_problems(mapped, capabilities, performances, level, detailed,
                      foundation_version=1, language=""):
    """Validate the sealed mapping and require late evidence at capable finishes."""
    if not isinstance(mapped, dict):
        return ["languageMastery.foundationCapabilities must be an object"]
    problems = []
    roles = roles_for(foundation_version, level)
    missing, extra = set(roles) - set(mapped), set(mapped) - set(roles)
    if missing:
        problems.append("languageMastery.foundationCapabilities is missing: "
                        + ", ".join(sorted(missing)))
    if extra:
        problems.append("languageMastery.foundationCapabilities has unknown keys: "
                        + ", ".join(sorted(extra)))
    values = list(mapped.values())
    invalid = [value for value in values
               if not isinstance(value, str) or not CAPABILITY.fullmatch(value)]
    if invalid:
        problems.append("languageMastery.foundationCapabilities values must be `language-*` ids")
    if len(values) != len(set(values)):
        problems.append("languageMastery foundation roles must map to distinct capabilities")
    unknown = sorted(set(value for value in values if isinstance(value, str))
                     - set(capabilities))
    if unknown:
        problems.append("languageMastery foundation capabilities are outside the spine: "
                        + ", ".join(unknown))
    verification = mapped.get("verification")
    if (isinstance(verification, str)
            and not VERIFICATION_WORD.search(verification.removeprefix("language-"))):
        problems.append(
            "languageMastery.foundationCapabilities.verification must name an explicitly "
            "verification-oriented language capability")
    abstraction = mapped.get("abstraction")
    if (isinstance(abstraction, str)
            and not ABSTRACTION_WORD.search(abstraction.removeprefix("language-"))):
        problems.append(
            "languageMastery.foundationCapabilities.abstraction must name a concrete "
            "structured-abstraction idiom")
    required_abstraction = _profile_abstraction_tokens(language)
    if (isinstance(abstraction, str) and required_abstraction
            and not _has_capability_token(abstraction, required_abstraction)):
        problems.append(
            f"{language} Finish 3–5 structured abstraction requires a capability naming "
            + " or ".join(required_abstraction))
    modularity = mapped.get("modularity")
    if (isinstance(modularity, str)
            and not MODULARITY_WORD.search(modularity.removeprefix("language-"))):
        problems.append(
            "languageMastery.foundationCapabilities.modularity must explicitly name modularity")
    if detailed and level >= 3:
        assessed = {capability for item in performances if isinstance(item, dict)
                    for capability in (item.get("capabilityIds") or [])}
        omitted = sorted(set(value for value in values if isinstance(value, str)) - assessed)
        if omitted:
            problems.append("Finish 3–5 late language performances must assess every "
                            "foundation capability: " + ", ".join(omitted))
        verification_evidence = [
            item for item in performances if isinstance(item, dict)
            and verification in (item.get("capabilityIds") or [])]
        if verification and verification_evidence and not any(
                VERIFICATION_EVIDENCE.search(str(item.get("description") or ""))
                for item in verification_evidence):
            problems.append(
                "a late performance assessing verification must describe an observable "
                "verification, test, check, diagnosis, or inspection action")
    return problems
