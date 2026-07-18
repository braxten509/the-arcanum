"""Public requirements, deterministic scenarios, and rubric contracts."""
from __future__ import annotations

from dataclasses import dataclass

from ..ids import is_capability_id, is_stable_id
from ..paths import safe_relative_path

SCENARIO_KINDS = frozenset({
    "build", "run", "structured-output", "produced-file", "driver", "package",
    "cold-launch", "guided-observation",
})
RUBRIC_KINDS = frozenset({"deterministic", "qualitative"})


def _tuple(value: object, label: str, *, empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (not empty and not value):
        raise ValueError(f"{label} must be a non-empty array")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{label} entries must be non-empty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{label} contains duplicates")
    return tuple(value)


@dataclass(frozen=True)
class Requirement:
    id: str
    text: str
    essential: bool
    capability_ids: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: object, label: str) -> "Requirement":
        if not isinstance(value, dict) or set(value) != {"id", "text", "essential", "capabilityIds"}:
            raise ValueError(f"{label} has an invalid requirement shape")
        if not is_stable_id(value.get("id")):
            raise ValueError(f"{label}.id must be stable")
        if not isinstance(value.get("text"), str) or not value["text"].strip():
            raise ValueError(f"{label}.text is required")
        if not isinstance(value.get("essential"), bool):
            raise ValueError(f"{label}.essential must be boolean")
        capabilities = _tuple(value.get("capabilityIds"), f"{label}.capabilityIds", empty=True)
        if any(not is_capability_id(item) for item in capabilities):
            raise ValueError(f"{label}.capabilityIds contains an invalid id")
        return cls(value["id"], value["text"].strip(), value["essential"], capabilities)


@dataclass(frozen=True)
class Scenario:
    id: str
    kind: str
    requirement_ids: tuple[str, ...]
    capability_ids: tuple[str, ...]
    command_ref: str
    args: tuple[str, ...]
    stdin: str
    expect: dict
    timeout: int
    public: bool

    @classmethod
    def from_dict(cls, value: object, label: str) -> "Scenario":
        if not isinstance(value, dict):
            raise ValueError(f"{label} must be an object")
        expected = {"id", "kind", "requirementIds", "capabilityIds", "commandRef",
                    "args", "stdin", "expect", "timeout", "public"}
        if set(value) != expected:
            raise ValueError(f"{label} keys must be exactly {sorted(expected)}")
        if not is_stable_id(value.get("id")) or value.get("kind") not in SCENARIO_KINDS:
            raise ValueError(f"{label} has an invalid id or kind")
        requirements = _tuple(value.get("requirementIds"), f"{label}.requirementIds")
        capabilities = _tuple(value.get("capabilityIds"), f"{label}.capabilityIds", empty=True)
        if not is_stable_id(value.get("commandRef")):
            raise ValueError(f"{label}.commandRef must name a registered runtime command")
        args = _tuple(value.get("args"), f"{label}.args", empty=True)
        if not isinstance(value.get("stdin"), str) or not isinstance(value.get("expect"), dict):
            raise ValueError(f"{label} stdin/expect are invalid")
        timeout = value.get("timeout")
        if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 300:
            raise ValueError(f"{label}.timeout must be 1 through 300")
        if not isinstance(value.get("public"), bool):
            raise ValueError(f"{label}.public must be boolean")
        return cls(value["id"], value["kind"], requirements, capabilities,
                   value["commandRef"], args, value["stdin"], dict(value["expect"]),
                   timeout, value["public"])


@dataclass(frozen=True)
class RubricCriterion:
    id: str
    criterion: str
    weight: int
    kind: str
    assessment_ids: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: object, label: str) -> "RubricCriterion":
        if not isinstance(value, dict):
            raise ValueError(f"{label} must be an object")
        expected = {"id", "criterion", "weight", "kind", "assessmentIds"}
        if set(value) != expected:
            raise ValueError(f"{label} keys must be exactly {sorted(expected)}")
        if not is_stable_id(value.get("id")) or value.get("kind") not in RUBRIC_KINDS:
            raise ValueError(f"{label} has an invalid id or kind")
        if not isinstance(value.get("criterion"), str) or not value["criterion"].strip():
            raise ValueError(f"{label}.criterion is required")
        weight = value.get("weight")
        if not isinstance(weight, int) or isinstance(weight, bool) or not 1 <= weight <= 100:
            raise ValueError(f"{label}.weight must be 1 through 100")
        assessments = _tuple(value.get("assessmentIds"), f"{label}.assessmentIds",
                             empty=value["kind"] == "qualitative")
        return cls(value["id"], value["criterion"], weight, value["kind"], assessments)


@dataclass(frozen=True)
class AssessmentContract:
    version: int
    requirements: tuple[Requirement, ...]
    scenarios: tuple[Scenario, ...]
    rubric: tuple[RubricCriterion, ...]

    @classmethod
    def from_dict(cls, value: object) -> "AssessmentContract":
        if not isinstance(value, dict) or set(value) != {"version", "requirements", "scenarios", "rubric"}:
            raise ValueError("assessment has an invalid top-level shape")
        if value.get("version") != 1:
            raise ValueError("assessment.version must be 1")
        groups = []
        for key, parser in (("requirements", Requirement), ("scenarios", Scenario),
                            ("rubric", RubricCriterion)):
            raw = value.get(key)
            if not isinstance(raw, list):
                raise ValueError(f"assessment.{key} must be an array")
            groups.append(tuple(parser.from_dict(item, f"{key}[{index}]")
                                for index, item in enumerate(raw)))
        contract = cls(1, groups[0], groups[1], groups[2])
        contract.validate_links()
        return contract

    def validate_links(self) -> None:
        requirement_ids = {item.id for item in self.requirements}
        scenario_ids = {item.id for item in self.scenarios}
        if len(requirement_ids) != len(self.requirements) or len(scenario_ids) != len(self.scenarios):
            raise ValueError("assessment IDs must be unique")
        for scenario in self.scenarios:
            if set(scenario.requirement_ids) - requirement_ids:
                raise ValueError(f"scenario {scenario.id} cites an unknown public requirement")
        if sum(item.weight for item in self.rubric) != 100:
            raise ValueError("rubric weights must total 100")
        for criterion in self.rubric:
            if set(criterion.assessment_ids) - scenario_ids:
                raise ValueError(f"rubric {criterion.id} cites an unknown assessment")
        covered = {rid for scenario in self.scenarios for rid in scenario.requirement_ids}
        missing = {item.id for item in self.requirements if item.essential} - covered
        if missing:
            raise ValueError("essential requirements lack deterministic evidence: " + ", ".join(sorted(missing)))
