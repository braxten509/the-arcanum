"""Harness-owned between-phase gate evaluation.

This is the decision seam between a worker returning and the orchestrator deciding
whether that phase may advance: write/shrink contracts, dependency provisioning,
the ordinary validator, and Phase 3's independent cross-section quality gate.
"""
import os

from . import REPO
from .measure import (inventory, runtime_config_scope_violations,
                      selected_runtime_config, shrink_marks, shrinkage, validate,
                      validate_phase3, validate_shipping)
from .sections import section_ids
from .validation_env import (ValidationEnvironmentError, declared_dependencies,
                             ensure_validation_environment)


def evaluate_content_gate(tid, num, tooling, plan_rel, pre, marks, shrink_path,
                          runtime_pre, prevalidated, attempt):
    """Return ``(ok, report, contract_problems, remaining_prevalidated)``."""
    shrink_problems = shrinkage(pre, inventory(tid))
    if shrink_problems and shrink_marks(shrink_path) > marks:
        print(f"  · shrinkage justified in {os.path.relpath(shrink_path, REPO)}: "
              f"{len(shrink_problems)} change(s) accepted")
        shrink_problems = []
    problems = list(shrink_problems)
    if num in (2, 8):
        problems += runtime_config_scope_violations(
            runtime_pre, selected_runtime_config(tid))

    if not os.path.isdir(os.path.join(REPO, "tomes", tid)):
        return False, f"tomes/{tid}/ is missing — restore the scaffolded tome", problems, None
    if prevalidated is not None:
        ok, report = prevalidated
        return ok, report, problems, None

    if num >= 2:
        try:
            dependency_env = ensure_validation_environment(tid)
            dependencies = declared_dependencies(tid)
            if dependencies and attempt == 0:
                mode = "isolated environment" if dependency_env else "scratch projects"
                print(f"  · validation dependencies ready in {mode}: "
                      + ", ".join(dependencies))
        except ValidationEnvironmentError as exc:
            return False, f"ERROR validation dependencies: {exc}", problems, None

    if num == 3:
        ok, report = validate_phase3(tid, tooling, plan_rel, section_ids(tid))
    elif num >= 7:
        ok, report = validate_shipping(tid, tooling, plan_rel)
    else:
        ok, report = validate(tid, phase=num, tooling=tooling)
    return ok, report, problems, None
