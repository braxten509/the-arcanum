"""Compose deterministic scenario ownership with bounded qualitative scores."""
from __future__ import annotations

from arcanum_core.contracts.assessment import AssessmentContract
from arcanum_core.policies.grading import GradeResult, compose_grade


def compose_assessment_grade(contract: AssessmentContract, scenario_results: list[dict],
                             qualitative_scores: list[dict]) -> GradeResult:
    by_scenario = {row["id"]: row for row in scenario_results}
    returned = []
    qualitative = {str(row.get("id") or ""): row for row in qualitative_scores}
    for criterion in contract.rubric:
        if criterion.kind == "deterministic":
            passed = all(by_scenario.get(sid, {}).get("passed") for sid in criterion.assessment_ids)
            returned.append({"id": criterion.id, "score": 10 if passed else 0,
                             "comment": "All linked deterministic checks passed." if passed
                             else "One or more linked deterministic checks failed."})
        else:
            if criterion.id not in qualitative:
                raise ValueError(f"qualitative grader omitted criterion {criterion.id!r}")
            returned.append(qualitative[criterion.id])
    essential_ids = {requirement.id for requirement in contract.requirements if requirement.essential}
    essential_scenarios = [row for scenario, row in zip(contract.scenarios, scenario_results)
                           if essential_ids.intersection(scenario.requirement_ids)]
    essential_passed = bool(essential_scenarios) and all(row.get("passed") for row in essential_scenarios)
    criteria = [{"id": item.id, "criterion": item.criterion, "weight": item.weight,
                 "kind": item.kind} for item in contract.rubric]
    return compose_grade(criteria, returned, essential_passed)
