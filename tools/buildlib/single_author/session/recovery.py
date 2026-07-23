"""Narrow recovery policy for provider-side author tool failures."""
from __future__ import annotations


MAX_CODEX_PATCH_RECOVERIES = 2
MAX_CODEX_FRESH_SESSION_RECOVERIES = 1

_CODEX_PATCH_FAILURE = "apply_patch verification failed:"
_CODEX_PATCH_SAFETY = (
    "When editing with `apply_patch`, keep update patches small, begin every update hunk "
    "with an `@@` marker, and reread the live target before retrying a rejected patch."
)


def with_codex_patch_safety(kind, role, prompt):
    """Attach Codex-specific patch syntax guidance to every author turn."""
    text = str(prompt or "")
    if kind != "codex-cli" or role != "author" or _CODEX_PATCH_SAFETY in text:
        return text
    return f"{_CODEX_PATCH_SAFETY}\n\n{text}"


def recoverable_codex_patch_failure(kind, role, session_id, diagnostic):
    """Return true only when a resumable Codex author turn died on patch parsing."""
    return (
        kind == "codex-cli"
        and role == "author"
        and bool(str(session_id or "").strip())
        and _CODEX_PATCH_FAILURE in str(diagnostic or "").lower()
    )


def codex_patch_recovery_prompt(unit_label):
    """Tell the saved session how to recover without replaying the bad payload."""
    return (
        "The previous Codex turn ended because `apply_patch` rejected a malformed patch before "
        f"that patch was applied. Continue the same {unit_label}; do not restart discovery or "
        "repeat the rejected payload. Reread the current target around the intended edit, split "
        "the change into smaller patches, and ensure every update hunk begins with `@@`. Then "
        "finish the existing authoring, mechanical-validation, and handoff instructions."
    )


def recoverable_codex_resume_failure(kind, role, resumed_session_id, diagnostic):
    """Recognize a dead saved Codex thread without masking a real CLI diagnostic.

    Codex can occasionally reject an old, heavily compacted thread before it emits a
    structured event.  The only durable evidence is then exit 1 with no accompanying
    stderr/noise.  Retry that narrow case once in a fresh session; any real diagnostic,
    fresh-session failure, or repeat still pauses for the operator.
    """
    lines = [line.strip() for line in str(diagnostic or "").splitlines()
             if line.strip()]
    return (
        kind == "codex-cli"
        and role == "author"
        and bool(str(resumed_session_id or "").strip())
        and lines == ["exit code 1"]
    )


def codex_fresh_session_recovery_prompt(unit_label):
    return (
        f"The saved Codex thread for {unit_label} could not be resumed and exited before "
        "producing model output. Continue this exact unit in a fresh session from the files "
        "on disk and the complete assignment below. Preserve completed work, do not repeat "
        "initial discovery, and finish the existing repair, mechanical-validation, and "
        "handoff instructions."
    )
