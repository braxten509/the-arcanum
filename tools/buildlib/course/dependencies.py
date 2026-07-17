"""Phase-2 package ownership and manifest reconciliation."""


EXTERNAL_FIRST_CAPABILITIES = {
    "tool-install", "tool-create-open", "tool-navigate", "tool-edit-save",
    "tool-run-test", "tool-diagnose",
}


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
