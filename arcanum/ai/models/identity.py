"""Conversation-session identity across model gateway routes."""
from __future__ import annotations


def canonical_model_name(model: str) -> str:
    """Return the provider-independent terminal model name."""
    return str(model or "").strip().casefold().rsplit("/", 1)[-1]


def session_models_compatible(previous_kind: str, previous_model: str,
                              next_kind: str, next_model: str) -> bool:
    """Whether two selections can safely use the same provider conversation.

    Exact kind/model matches retain their existing behavior. Cross-route reuse is
    limited to OpenCode because its hosted gateways share one session database and
    accept a new ``-m`` route while resuming that session.
    """
    previous_kind, next_kind = str(previous_kind or ""), str(next_kind or "")
    previous_model, next_model = str(previous_model or ""), str(next_model or "")
    if not previous_kind or previous_kind != next_kind or not previous_model or not next_model:
        return False
    if previous_model == next_model:
        return True
    return (previous_kind == "opencode-cli"
            and canonical_model_name(previous_model) == canonical_model_name(next_model))
