"""Reproduce the exact command an author reported as blocked."""
import re
import shlex

from ..measure import ValidatorInfrastructureError, run_harness_command
from .gate import context, self_validation_argvs


def author_blocked_command(text):
    """Parse the exact command named by a structured HARNESS_BLOCKED report."""
    for line in str(text or "").splitlines():
        match = re.match(r"^\s*COMMAND:\s*(.*?)\s*$", line)
        if not match:
            continue
        rendered = match.group(1).strip()
        if len(rendered) >= 2 and rendered[0] == rendered[-1] == "`":
            rendered = rendered[1:-1]
        try:
            return shlex.split(rendered)
        except ValueError as exc:
            raise ValidatorInfrastructureError(
                "HARNESS_BLOCKED report",
                f"could not parse COMMAND line: {exc}") from exc
    raise ValidatorInfrastructureError(
        "HARNESS_BLOCKED report",
        "missing required `COMMAND: <exact command>` line")


def author_bootstrap_argv(build_id, unit):
    """Return the one bounded context command allowed before this unit's authoring."""
    if unit["kind"] == "section":
        return ["python3", "tools/workflow/context/render_section_context.py",
                build_id, unit["section"]]
    if int(unit.get("phase") or 0) == 2:
        return ["python3", "tools/workflow/context/render_phase2_context.py", build_id]
    return []


def validate_author_blocked_check(build_id, unit, claim):
    """Reproduce the command an author says was blocked.

    Returns ``("self-check", None, "")`` for an allowlisted unit validator or
    ``("bootstrap", True, report)`` for a clean bounded-context command.
    Unstructured command failures raise ``ValidatorInfrastructureError`` through
    ``run_harness_command`` and pause without substituting a different check.
    """
    command = author_blocked_command(claim)
    self_checks = self_validation_argvs(build_id, unit)
    if command in self_checks:
        # The orchestrator invokes its injected self-check dependency so tests,
        # alternate registries, and the complete multi-command aggregate retain
        # the same behavior as an ordinary handoff.
        return "self-check", None, ""
    bootstrap = author_bootstrap_argv(build_id, unit)
    if bootstrap and command == bootstrap:
        ctx = context(build_id)
        process = run_harness_command(command, ctx["tid"])
        report = ((process.stdout or "") + (process.stderr or "")).strip()
        return "bootstrap", True, report
    allowed = [shlex.join(item) for item in [*self_checks, *([bootstrap] if bootstrap else [])]]
    raise ValidatorInfrastructureError(
        shlex.join(command),
        "HARNESS_BLOCKED named a command outside the assigned exact command set; "
        f"allowed commands: {', '.join(allowed)}")
