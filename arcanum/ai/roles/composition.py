"""The complete default AI-role composition root."""

from .registry import AiRoleRegistry, AiRoleSpec


def default_role_registry() -> AiRoleRegistry:
    registry = AiRoleRegistry()
    specs = (
        AiRoleSpec("oracle", 1, ("learning-support", "contextual-answer")),
        AiRoleSpec("legacy-working-grader", 1, ("legacy-grading", "structured-score")),
        AiRoleSpec("qualitative-grader", 1, ("qualitative-review", "structured-score")),
        AiRoleSpec("binder-amend", 1, ("repository-read", "scoped-write", "validation")),
        AiRoleSpec("binder-review", 1, ("repository-read", "review-report")),
        AiRoleSpec("challenge-generator", 1, ("blueprint-proposal", "structured-output")),
        AiRoleSpec("semantic-challenge-reviewer", 1,
                   ("semantic-congruence", "structured-findings")),
    )
    for spec in specs:
        registry.register(spec)
    return registry
