"""Phase-2 package, tool-action, command, and runtime reconciliation."""
from __future__ import annotations

import os
import re
import shlex


EXTERNAL_FIRST_CAPABILITIES = {
    "tool-install", "tool-create-open", "tool-navigate", "tool-edit-save",
    "tool-run-test", "tool-diagnose",
}

_CONCRETE_TOOL_RULES = {
    "tool-install": {
        "bootstrap", "environment", "install", "package-manager", "provision",
        "setup", "toolchain", "venv",
    },
    "tool-deliver": {
        "copy", "deliver", "dist", "export", "package", "publish", "release",
        "ship", "stage",
    },
}
_TARGET_COMMAND_KEYS = (
    "command", "runCommand", "buildCommand", "checkCommand", "deliveryBuildCommand",
)
_COMMAND_CODE = re.compile(r"`([^`\r\n]+)`")
_MAKE_OPTIONS_WITH_VALUES = {
    "-C", "--directory", "-f", "--file", "-I", "--include-dir", "-j", "--jobs",
    "-o", "--old-file", "-W", "--what-if",
}
_SHELLS = {"bash", "dash", "ksh", "sh", "zsh"}


def validation_dependency_alignment_problems(value, manifest):
    """Reconcile every node package while the tome manifest is still writable."""
    if not isinstance(value, dict) or value.get("version", 1) < 2:
        return []
    planned = {
        package
        for section in value.get("sections") or [] if isinstance(section, dict)
        for node in section.get("nodes") or [] if isinstance(node, dict)
        for package in node.get("validationDependencies") or []
        if isinstance(package, str) and package.strip()
    }
    runtime = manifest.get("runtime") if isinstance(manifest, dict) else {}
    declared_value = runtime.get("validationDependencies") if isinstance(runtime, dict) else []
    declared = {
        package for package in (declared_value or [])
        if isinstance(package, str) and package.strip()
    }
    problems = []
    missing = sorted(planned - declared)
    if missing:
        problems.append(
            "Phase-2 course-map nodes require validation packages absent from "
            "[runtime].validationDependencies: " + ", ".join(missing)
            + ". Phase 3 cannot edit tome.toml, so declare them before sealing the map")
    unowned = sorted(declared - planned)
    if unowned:
        problems.append(
            "[runtime].validationDependencies contains packages not assigned to any Phase-2 "
            "lesson or Working node: " + ", ".join(unowned))
    return problems


def external_workspace_capability_alignment_problems(value, manifest):
    """Keep Phase 3's external-workspace ledger achievable before map sealing."""
    runtime = manifest.get("runtime") if isinstance(manifest, dict) else {}
    if not isinstance(runtime, dict) or runtime.get("externalWorkspace") is not True:
        return []
    sections = value.get("sections") if isinstance(value, dict) else None
    if not isinstance(sections, list) or not sections:
        return ["externalWorkspace course map has no sections"]

    def taught(section):
        return {
            capability
            for node in section.get("nodes") or [] if isinstance(node, dict)
            and node.get("kind") == "lesson"
            for capability in node.get("teaches") or [] if isinstance(capability, str)
        }

    def working_requires(section):
        return {
            capability
            for node in section.get("nodes") or [] if isinstance(node, dict)
            and node.get("kind") == "working"
            for capability in node.get("requires") or [] if isinstance(capability, str)
        }

    problems = []
    first_missing = sorted(EXTERNAL_FIRST_CAPABILITIES - taught(sections[0]))
    if first_missing:
        problems.append(
            "externalWorkspace first-section map is missing required tool capabilities: "
            + ", ".join(first_missing)
            + ". Phase 3 cannot add them after the course map is sealed")
    if "tool-deliver" not in taught(sections[-1]):
        problems.append(
            "externalWorkspace final-section map must teach tool-deliver before sealing")
    if "tool-deliver" not in working_requires(sections[-1]):
        problems.append(
            "externalWorkspace final Working must require tool-deliver before sealing")
    return problems


def _map_positions(value):
    positions = {}
    for section_index, section in enumerate(value.get("sections") or []):
        if not isinstance(section, dict):
            continue
        for node_index, node in enumerate(section.get("nodes") or []):
            if isinstance(node, dict) and isinstance(node.get("id"), str):
                positions[node["id"]] = (section_index, node_index)
    return positions


def _mechanism_records(value):
    contract = value.get("mechanismContract") if isinstance(value, dict) else {}
    records = contract.get("mechanisms") if isinstance(contract, dict) else []
    return {
        record.get("id"): record for record in (records or [])
        if isinstance(record, dict) and isinstance(record.get("id"), str)
    }


def _record_words(record):
    return set(re.findall(
        r"[a-z0-9]+",
        f"{record.get('id', '')} {record.get('label', '')}".lower()))


def concrete_tool_mechanism_alignment_problems(value, manifest):
    """Require external setup/delivery capabilities to own a concrete tool action."""
    runtime = manifest.get("runtime") if isinstance(manifest, dict) else {}
    if (not isinstance(runtime, dict) or runtime.get("externalWorkspace") is not True
            or not isinstance(value, dict) or int(value.get("version") or 0) < 4):
        return []
    positions = _map_positions(value)
    records = _mechanism_records(value)
    if not positions or not records:
        return []  # The course-map schema reports the missing contract more precisely.

    problems = []
    for section in value.get("sections") or []:
        if not isinstance(section, dict):
            continue
        working = next((node for node in section.get("nodes") or []
                        if isinstance(node, dict) and node.get("kind") == "working"), {})
        working_mechanisms = set(working.get("mechanisms") or [])
        for node in section.get("nodes") or []:
            if not isinstance(node, dict) or node.get("kind") != "lesson":
                continue
            for capability in set(node.get("teaches") or []) & set(_CONCRETE_TOOL_RULES):
                terms = _CONCRETE_TOOL_RULES[capability]
                owned = []
                for mechanism_id in working_mechanisms:
                    record = records.get(mechanism_id)
                    if not record or record.get("kind") != "tool-action":
                        continue
                    owner = record.get("owner")
                    if (owner not in positions or node.get("id") not in positions
                            or positions[owner] > positions[node["id"]]):
                        continue
                    if _record_words(record) & terms:
                        owned.append(mechanism_id)
                if not owned:
                    problems.append(
                        f"{node.get('id')} teaches {capability} but its section Working has no "
                        "concrete matching tool-action mechanism owned by or before that lesson")
    return problems


def _runtime_target_tools(runtime):
    tools = {
        os.path.basename(item).lower()
        for item in (runtime.get("commandTargetTools") or [])
        if isinstance(item, str) and item.strip()
    }
    project_file = os.path.basename(str(runtime.get("projectFile") or "")).lower()
    if project_file in {"makefile", "gnumakefile"} or project_file.startswith("makefile."):
        tools.add("make")
    for key in _TARGET_COMMAND_KEYS:
        command = runtime.get(key)
        if (isinstance(command, (list, tuple)) and command
                and os.path.basename(str(command[0])).lower() == "make"):
            tools.add("make")
    return tools


def _shell_tokens(command):
    try:
        lexer = shlex.shlex(str(command), posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        lexer.commenters = ""
        return list(lexer)
    except ValueError:
        return []


def _targets_in_command(command, tools):
    tokens = _shell_tokens(command)
    found = []
    for index, token in enumerate(tokens):
        tool = os.path.basename(token).lower()
        if tool not in tools:
            continue
        skip_value = False
        for candidate in tokens[index + 1:]:
            if candidate in {";", "&&", "||", "|", "&"}:
                break
            if skip_value:
                skip_value = False
                continue
            if candidate in _MAKE_OPTIONS_WITH_VALUES and tool == "make":
                skip_value = True
                continue
            if candidate.startswith("-") or "=" in candidate:
                continue
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]*", candidate):
                found.append((tool, candidate))
    return found


def _record_owns_target(record, tool, target):
    words = _record_words(record)
    tool_owned = tool in words or any(word.startswith(tool) for word in words)
    target_words = set(re.findall(r"[a-z0-9]+", target.lower()))
    return tool_owned and bool(target_words) and target_words <= words


def literal_command_target_alignment_problems(value, runtime, proof_sections=None):
    """Bind literal target-style commands and direct package args to mechanism owners."""
    if not isinstance(value, dict) or int(value.get("version") or 0) < 4:
        return []
    tools = _runtime_target_tools(runtime or {})
    if not tools:
        return []
    positions = _map_positions(value)
    records = _mechanism_records(value)
    problems = []
    sections = [section for section in value.get("sections") or []
                if isinstance(section, dict)]
    for section in sections:
        working = next((node for node in section.get("nodes") or []
                        if isinstance(node, dict) and node.get("kind") == "working"), {})
        demand_id = working.get("id")
        demanded = set(working.get("mechanisms") or [])
        commands = set(_COMMAND_CODE.findall(str(section.get("projectMilestone") or "")))
        commands.update(_COMMAND_CODE.findall(str(working.get("projectMilestone") or "")))
        targets = {target for command in commands for target in _targets_in_command(command, tools)}
        if section is sections[-1] and proof_sections:
            proof = (proof_sections[-1].get("proof")
                     if isinstance(proof_sections[-1], dict) else {})
            build = (runtime or {}).get("deliveryBuildCommand") or []
            direct_tool = (os.path.basename(str(build[0])).lower()
                           if isinstance(build, (list, tuple)) and build else "")
            if direct_tool in tools and isinstance(proof, dict):
                appended = " ".join(
                    str(item) for item in (proof.get("packageArgs") or [])
                    if isinstance(item, str))
                targets.update(_targets_in_command(
                    " ".join([direct_tool, appended]).strip(), tools))
        for tool, target in sorted(targets):
            matching = []
            for mechanism_id in demanded:
                record = records.get(mechanism_id)
                if not record or not _record_owns_target(record, tool, target):
                    continue
                owner = record.get("owner")
                if (owner in positions and demand_id in positions
                        and positions[owner] <= positions[demand_id]):
                    matching.append(mechanism_id)
            if not matching:
                problems.append(
                    f"{demand_id} literally requires `{tool} {target}` but has no earlier "
                    "matching mechanism (for example, a concrete target/rule owner) in its "
                    "Working mechanism list")
    return problems


def _shell_changes_to_delivery_env(command):
    if not isinstance(command, (list, tuple)) or not command:
        return False
    direct = re.compile(r"\bcd\s+(?:--\s+)?[\"']?\{env\}(?=[/\"'\s;&|]|$)")
    if any(direct.search(str(argument)) for argument in command):
        return True
    if os.path.basename(str(command[0])).lower() not in _SHELLS:
        return False
    script_index = next((index + 1 for index, argument in enumerate(command[:-1])
                         if isinstance(argument, str) and argument.startswith("-")
                         and "c" in argument[1:]), None)
    if script_index is None or script_index >= len(command):
        return False
    script = str(command[script_index])
    for position, argument in enumerate(command[script_index + 1:]):
        if argument != "{env}":
            continue
        positional = re.compile(
            r"\bcd\s+(?:--\s+)?[\"']?\$(?:\{" + str(position) + r"\}|"
            + str(position) + r")(?=[/\"'\s;&|]|$)")
        if positional.search(script):
            return True
    return False


def delivery_build_cwd_problem(runtime):
    """Return the global delivery-cwd violation shared by all validation phases."""
    runtime = runtime if isinstance(runtime, dict) else {}
    if not _shell_changes_to_delivery_env(runtime.get("deliveryBuildCommand") or []):
        return ""
    return (
        "deliveryBuildCommand changes cwd to {env}; the delivery runner already executes "
        "from the learner project, while {env} contains fresh dependencies/staged output, "
        "not the learner's source tree. Build from project cwd and copy with explicit paths")


def runtime_delivery_alignment_problems(value, runtime):
    """Bind optional clean-staging declarations to the sealed package paths."""
    contract = value.get("artifactContract") if isinstance(value, dict) else {}
    delivery = contract.get("delivery") if isinstance(contract, dict) else {}
    if not isinstance(delivery, dict) or delivery.get("mode") != "package":
        return []
    runtime = runtime if isinstance(runtime, dict) else {}
    problems = []
    has_artifact = "deliveryArtifact" in runtime
    has_requirements = "deliveryRequirements" in runtime
    if has_artifact and runtime.get("deliveryArtifact") != delivery.get("artifact"):
        problems.append(
            "runtime deliveryArtifact must exactly equal the sealed package artifact path "
            f"{delivery.get('artifact')!r}")
    if has_requirements and runtime.get("deliveryRequirements") != delivery.get("requirements"):
        problems.append(
            "runtime deliveryRequirements must exactly equal the sealed requirements path "
            f"{delivery.get('requirements')!r}")
    return problems
