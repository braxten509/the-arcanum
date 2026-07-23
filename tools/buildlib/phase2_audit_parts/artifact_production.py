"""Artifact-production validation for the Phase-2 audit sidecar."""
from .contract import (
    ARTIFACT_INPUT_POLICIES, PRODUCTION_KEYS, PRODUCTION_MODES,
    _dependency_closure,
)


def append_artifact_production_problems(
            problems, audit, value, positions, production_graph, map_records, version):
    artifact_contract = value.get("artifactContract") or {}
    artifact_records = {
        item.get("artifact"): item
        for item in artifact_contract.get("artifacts") or []
        if isinstance(item, dict) and isinstance(item.get("artifact"), str)
    } if isinstance(artifact_contract, dict) else {}
    raw_production = audit.get("artifactProduction")
    if not isinstance(raw_production, list):
        return problems + ["audit.json.artifactProduction must be an array"]
    production, artifact_graph = {}, {}
    for index, item in enumerate(raw_production):
        label = f"audit.json.artifactProduction[{index}]"
        if not isinstance(item, dict):
            problems.append(f"{label} must be an object")
            continue
        if set(item) != PRODUCTION_KEYS:
            problems.append(f"{label} keys must be exactly {', '.join(sorted(PRODUCTION_KEYS))}")
        artifact = item.get("artifact")
        if artifact in production:
            problems.append(f"{label}.artifact repeats {artifact!r}")
        production[artifact] = item
        sealed = artifact_records.get(artifact)
        if sealed is None:
            problems.append(f"{label}.artifact names undeclared artifact {artifact!r}")
            continue
        owner = item.get("ownerWorking")
        if owner != sealed.get("ownerWorking"):
            problems.append(
                f"{label}.ownerWorking must preserve {sealed.get('ownerWorking')!r}")
        if item.get("mode") not in PRODUCTION_MODES:
            problems.append(f"{label}.mode must be one of {sorted(PRODUCTION_MODES)}")
        inputs = item.get("inputs")
        if not isinstance(inputs, list) or any(not isinstance(v, str) or not v for v in inputs):
            problems.append(f"{label}.inputs must be an array of artifact paths")
            inputs = []
        elif len(inputs) != len(set(inputs)):
            problems.append(f"{label}.inputs contains duplicates")
        if artifact in inputs:
            problems.append(f"{label}.inputs cannot contain its own artifact")
        input_policy = ARTIFACT_INPUT_POLICIES.get(item.get("mode"))
        if input_policy == "forbidden" and inputs:
            problems.append(f"{label}.mode authored must start without artifact inputs")
        if input_policy == "required" and not inputs:
            problems.append(f"{label}.mode {item.get('mode')} requires at least one input artifact")
        artifact_graph[artifact] = list(inputs)
        for input_artifact in inputs:
            source = artifact_records.get(input_artifact)
            if source is None:
                problems.append(f"{label}.inputs names undeclared artifact {input_artifact!r}")
            elif positions.get(source.get("ownerWorking"), (999, 999)) > positions.get(owner, (-1, -1)):
                problems.append(
                    f"{label}.inputs uses {input_artifact!r} before its owner Working")
        mechanism_ids = item.get("mechanisms")
        if (not isinstance(mechanism_ids, list) or not mechanism_ids
                or any(not isinstance(v, str) or not v for v in mechanism_ids)):
            problems.append(f"{label}.mechanisms must contain at least one mechanism id")
            mechanism_ids = []
        elif len(mechanism_ids) != len(set(mechanism_ids)):
            problems.append(f"{label}.mechanisms contains duplicates")
        working = next((node for section in value.get("sections") or []
                        if isinstance(section, dict)
                        for node in section.get("nodes") or []
                        if isinstance(node, dict) and node.get("id") == owner), {})
        unavailable = sorted(set(mechanism_ids) - set(working.get("mechanisms") or []))
        if unavailable:
            problems.append(
                f"{label}.mechanisms are absent from {owner}: " + ", ".join(unavailable))
        if version == 2:
            production_closure = _dependency_closure(mechanism_ids, production_graph)
            missing_production_dependencies = sorted(
                production_closure - set(mechanism_ids))
            if missing_production_dependencies:
                problems.append(
                    f"{label}.mechanisms is not closed over production prerequisites; add "
                    + ", ".join(missing_production_dependencies))
    missing_artifacts = sorted(set(artifact_records) - set(production))
    if missing_artifacts:
        problems.append("audit.json.artifactProduction is missing declared artifacts: "
                        + ", ".join(missing_artifacts))

    visiting, visited = set(), set()

    def visit_artifact(artifact):
        if artifact in visiting:
            problems.append(f"artifact production cycle reaches {artifact!r}")
            return
        if artifact in visited:
            return
        visiting.add(artifact)
        for input_artifact in artifact_graph.get(artifact, []):
            if input_artifact in artifact_graph:
                visit_artifact(input_artifact)
        visiting.remove(artifact)
        visited.add(artifact)

    for artifact in artifact_graph:
        visit_artifact(artifact)
    return problems
