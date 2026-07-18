"""Boundary loader for the central, versioned evidence policy TOML."""
from __future__ import annotations

from dataclasses import dataclass
import os
import tomllib

from arcanum_core.contracts.mastery import COGNITIVE_TASKS, PERFORMANCE_KINDS

from .. import REPO

POLICY_PATH = os.path.join(REPO, "global-configs", "mastery-evidence.toml")


@dataclass(frozen=True)
class LevelPolicy:
    level: int
    name: str
    capability_floor: int
    foundation_roles: tuple[str, ...]
    late_performances: int
    standalone_labs: int
    rationales: int
    minimum_blueprints: int
    minimum_verified_variants: int
    minimum_variation_axes: int
    minimum_kind: str
    cognitive_tasks: tuple[str, ...]
    context_relations: tuple[str, ...]


@dataclass(frozen=True)
class EvidencePolicy:
    version: int
    required_lesson_completion: float
    minimum_working_score: int
    minimum_grade: str
    essential_failure_status: str
    levels: dict[int, LevelPolicy]

    def for_level(self, level: int) -> LevelPolicy:
        try:
            return self.levels[level]
        except KeyError as exc:
            raise ValueError("mastery level must be 1 through 5") from exc


def _positive(row: dict, key: str, *, allow_zero: bool = False) -> int:
    value = row.get(key)
    floor = 0 if allow_zero else 1
    if not isinstance(value, int) or isinstance(value, bool) or value < floor:
        raise ValueError(f"{key} must be an integer >= {floor}")
    return value


def load_policy(path: str = POLICY_PATH) -> EvidencePolicy:
    with open(path, "rb") as handle:
        raw = tomllib.load(handle)
    if raw.get("version") != 1:
        raise ValueError("mastery evidence policy version must be 1")
    progression, grading = raw.get("progression") or {}, raw.get("grading") or {}
    if progression.get("requiredLessonCompletion") != 1.0:
        raise ValueError("requiredLessonCompletion must remain 1.0")
    if progression.get("minimumWorkingScore") != 80:
        raise ValueError("minimumWorkingScore must remain 80")
    if progression.get("essentialChecksMustPass") is not True:
        raise ValueError("essential checks must remain mandatory")
    levels = {}
    for level in range(1, 6):
        row = (raw.get("levels") or {}).get(str(level))
        if not isinstance(row, dict):
            raise ValueError(f"missing central level {level} policy")
        tasks = tuple(row.get("cognitiveTasks") or ())
        if not tasks or any(item not in COGNITIVE_TASKS for item in tasks):
            raise ValueError(f"level {level} has unsupported cognitive tasks")
        kind = row.get("minimumKind")
        if kind not in PERFORMANCE_KINDS:
            raise ValueError(f"level {level} minimumKind is unsupported")
        levels[level] = LevelPolicy(
            level, str(row.get("name") or ""), _positive(row, "capabilityFloor"),
            tuple(row.get("foundationRoles") or ()), _positive(row, "latePerformances"),
            _positive(row, "standaloneLabs", allow_zero=True), _positive(row, "rationales"),
            _positive(row, "minimumBlueprints"), _positive(row, "minimumVerifiedVariants"),
            _positive(row, "minimumVariationAxes"), kind, tasks,
            tuple(row.get("contextRelations") or ()))
    return EvidencePolicy(1, 1.0, 80, str(grading.get("minimumGrade") or ""),
                          str(grading.get("essentialFailureStatus") or ""), levels)
