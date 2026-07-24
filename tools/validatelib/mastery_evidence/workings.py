"""Structured Working requirements, hidden scenarios, and rubric linkage."""
from __future__ import annotations

import os
import tomllib

from arcanum_core.findings import Finding
from arcanum_core.ids import is_stable_id

from arcanum.assessment.contracts import load_working_contract
from runtimes import resolve_config as resolve_runtime_config
from .schema import error

SCENARIO_KEYS = {"id", "kind", "requirementIds", "capabilityIds", "commandRef", "args",
                 "stdin", "expect", "expectRegex", "expectExact", "expectRaw", "expectJson",
                 "expectFile", "expectFileRegex", "exitCode", "timeout", "public"}


def _hardened(manifest: dict) -> bool:
    return (manifest.get("mastery") or {}).get("sourceEvidenceVersion") == 1


def _adversarial_requirement_findings(contract, location: str) -> list[Finding]:
    """Reject happy-path-only evidence without dictating a language or implementation.

    Two distinct non-build observations make a requirement survive more than a compilation
    check. Rubric linkage makes that evidence visible to grading instead of leaving it as an
    unscored private scenario.
    """
    findings = []
    deterministic = [row for row in contract.rubric if row.kind == "deterministic"]
    for requirement in contract.requirements:
        if not requirement.essential:
            continue
        scenarios = [row for row in contract.scenarios
                     if requirement.id in row.requirement_ids
                     and row.kind not in ("build", "guided-observation")]
        if len(scenarios) < 2:
            findings.append(error("mastery.assessment.varied-evidence", location,
                                  f"essential requirement {requirement.id!r} needs at least two "
                                  "non-build deterministic scenarios (ordinary plus boundary, "
                                  "failure, or alternate input)", 3))
            continue
        # A different expected answer is not a different test input. Requiring the
        # command, arguments, stdin, or scenario route to differ prevents two
        # contradictory expectations for one uncontrolled process invocation from
        # masquerading as ordinary-plus-failure evidence.
        stimuli = [(row.kind, row.command_ref, row.args, row.stdin)
                   for row in scenarios]
        signatures = set(stimuli)
        if len(signatures) < 2:
            findings.append(error("mastery.assessment.duplicate-evidence", location,
                                  f"essential requirement {requirement.id!r} repeats one "
                                  "uncontrolled command; vary input or command path", 3))
        elif len(signatures) != len(stimuli):
            findings.append(error("mastery.assessment.redundant-evidence", location,
                                  f"essential requirement {requirement.id!r} includes a duplicate "
                                  "scenario input; remove it or give it a distinct control", 3))
        uncovered = [row.id for row in scenarios
                     if not set(requirement.capability_ids).issubset(row.capability_ids)]
        if uncovered:
            findings.append(error("mastery.assessment.capability-trace", location,
                                  f"scenario(s) {', '.join(uncovered)} omit capability IDs declared "
                                  f"by essential requirement {requirement.id!r}", 3))
        linked = {scenario_id for rubric in deterministic for scenario_id in rubric.assessment_ids}
        missing_rubric = [row.id for row in scenarios if row.id not in linked]
        if missing_rubric:
            findings.append(error("mastery.assessment.rubric-trace", location,
                                  f"scenario(s) {', '.join(missing_rubric)} for essential requirement "
                                  f"{requirement.id!r} are not linked from a deterministic rubric row", 3))
    return findings


def _shape_findings(freestyle: dict, location: str) -> list[Finding]:
    findings = []
    requirements = freestyle.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        return [error("mastery.working.requirements", location,
                      "future Workings require structured [[freestyle.requirements]]", 3)]
    ids = []
    for index, row in enumerate(requirements):
        label = f"{location}:requirement[{index}]"
        if not isinstance(row, dict) or set(row) != {"id", "text", "essential", "capabilities"}:
            findings.append(error("mastery.working.requirement-shape", label,
                                  "requirement keys must be id, text, essential, capabilities", 3))
            continue
        ids.append(row.get("id"))
        if not is_stable_id(row.get("id")) or not str(row.get("text") or "").strip():
            findings.append(error("mastery.working.requirement-value", label,
                                  "requirement needs a stable id and visible text", 3))
        if not isinstance(row.get("essential"), bool):
            findings.append(error("mastery.working.requirement-essential", label,
                                  "requirement essential must be boolean", 3))
    if len(ids) != len(set(ids)):
        findings.append(error("mastery.working.requirement-duplicate", location,
                              "Working requirement IDs contain duplicates", 3))
    rubric = freestyle.get("rubric")
    if not isinstance(rubric, list) or not rubric:
        findings.append(error("mastery.working.rubric", location, "Working rubric is missing", 3))
    else:
        for index, row in enumerate(rubric):
            required = {"id", "criterion", "weight", "kind", "assessmentIds"}
            if not isinstance(row, dict) or required - set(row):
                findings.append(error("mastery.working.rubric-shape", f"{location}:rubric[{index}]",
                                      "rubric rows require id, criterion, weight, kind, assessmentIds", 3))
    return findings


def _final_section_id(manifest: dict, sections: list[dict]) -> str:
    """Resolve finality from the complete manifest, not a section-scoped packet.

    Phase-3 validation intentionally supplies only the authored prefix (and some
    execution paths narrow that further to the current section).  Treating the
    last loaded row as the course final therefore makes every partial gate demand
    final delivery evidence.  The manifest owns the complete section order; the
    loaded rows remain a compatibility fallback for older direct callers.
    """
    content = manifest.get("content") if isinstance(manifest, dict) else None
    declared = content.get("sections") if isinstance(content, dict) else None
    if (isinstance(declared, list) and declared
            and all(isinstance(item, str) and item for item in declared)):
        return declared[-1]
    for section in reversed(sections):
        if isinstance(section, dict) and section.get("id"):
            return str(section["id"])
    return ""


def working_findings(tome_root: str, manifest: dict, sections: list[dict]) -> list[Finding]:
    findings = []
    final_id = _final_section_id(manifest, sections)
    runtime = resolve_runtime_config(manifest.get("runtime") or {})
    registered = set((runtime.get("assessmentCommands") or {}).keys()) | {"run"}
    if runtime.get("buildCommand") or "build" in registered:
        registered.add("build")
    delivery = (manifest.get("acceptance") or {}).get("artifact")
    for section in sections:
        sid = str(section.get("id") or "?")
        location = f"sections/{sid}/freestyle.toml"
        freestyle = section.get("freestyle") or {}
        findings += _shape_findings(freestyle, location)
        path = os.path.join(tome_root, "sections", sid, "assessment.toml")
        try:
            with open(path, "rb") as handle:
                raw = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            findings.append(error("mastery.assessment.file", path,
                                  f"hidden assessment.toml is missing or invalid: {exc}", 3))
            continue
        if set(raw) != {"version", "scenarios"} or raw.get("version") != 1:
            findings.append(error("mastery.assessment.shape", path,
                                  "assessment keys must be exactly version=1 and scenarios", 3))
        scenarios = raw.get("scenarios") or []
        for index, scenario in enumerate(scenarios):
            label = f"{path}:scenario[{index}]"
            if not isinstance(scenario, dict) or set(scenario) - SCENARIO_KEYS:
                findings.append(error("mastery.assessment.scenario-shape", label,
                                      "scenario contains unsupported keys", 3))
                continue
            if scenario.get("commandRef") not in registered:
                findings.append(error("mastery.assessment.command", label,
                                      "commandRef is not registered by the generic runtime", 3))
            expectation = scenario.get("expect") or {}
            produced = scenario.get("expectFile") or expectation.get("path")
            if produced and not any(str(produced) in str(row.get("text") or "")
                                    for row in freestyle.get("requirements") or []):
                findings.append(error("mastery.assessment.hidden-requirement", label,
                                      "a produced-file path checked in secret must appear in a public requirement", 3))
        try:
            contract = load_working_contract(tome_root, sid, freestyle)
        except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
            findings.append(error("mastery.assessment.contract", path, str(exc), 3))
            continue
        if _hardened(manifest):
            findings += _adversarial_requirement_findings(contract, path)
        artifact = runtime.get("artifactPath")
        if artifact:
            build_scenarios = [scenario for scenario in contract.scenarios
                               if scenario.kind == "build"]
            declared_paths = [scenario.expect.get("path") for scenario in build_scenarios]
            if artifact not in declared_paths:
                findings.append(error(
                    "mastery.assessment.artifact", path,
                    f"a build scenario must declare expectFile = {artifact!r}, the runtime's "
                    "official executable path", 3))
        kinds = {scenario.kind for scenario in contract.scenarios}
        if "build" not in kinds:
            findings.append(error("mastery.assessment.build", path,
                                  "every Working assessment requires deterministic build/check evidence", 3))
        if sid == final_id and "cold-launch" not in kinds:
            findings.append(error("mastery.assessment.cold-launch", path,
                                  "the final Working requires an ordinary cold-launch scenario", 3))
        if sid == final_id and delivery == "package" and "package" not in kinds:
            findings.append(error("mastery.assessment.package", path,
                                  "promised package delivery requires a package scenario", 3))
    return findings
