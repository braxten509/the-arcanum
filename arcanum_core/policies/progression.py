"""Legacy-independent progression rules for evidence-version tomes."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProgressionPolicy:
    required_lesson_completion: float = 1.0
    minimum_working_score: int = 80
    essential_checks_must_pass: bool = True
    supported_counts_resolved: bool = True
    supported_counts_independent: bool = False
    optional_counts_toward_completion: bool = False


@dataclass(frozen=True)
class ProgressionSnapshot:
    required_total: int
    required_resolved: int
    optional_total: int
    independent_total: int
    independent_demonstrated: int
    review_due: int
    working_total: int | None = None
    essential_passed: bool = False
    project_complete: bool = False
    provisional_mastery: bool = False
    retained_mastery: bool = False

    @property
    def lesson_fraction(self) -> float:
        return 1.0 if self.required_total == 0 else self.required_resolved / self.required_total

    def working_unlocked(self, policy: ProgressionPolicy) -> bool:
        return self.lesson_fraction >= policy.required_lesson_completion and self.review_due == 0

    def chapter_passed(self, policy: ProgressionPolicy) -> bool:
        return (self.working_total is not None
                and self.working_total >= policy.minimum_working_score
                and (self.essential_passed or not policy.essential_checks_must_pass))

    @property
    def mastery_status(self) -> str:
        if self.retained_mastery:
            return "retained"
        if self.provisional_mastery:
            return "provisional"
        return "learning"
