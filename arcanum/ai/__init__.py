"""Role-neutral AI transport ports, registry, and composition helpers."""

NO_TOME_MEMORY_POLICY = """PERSISTENT MEMORY PROHIBITION
Do not create, edit, append, or request storage of ANY information about tomes in Claude,
Codex, or another provider's persistent memory. This prohibition includes both specific and
generalized information: tome identities or concepts, authored content, build/run state, phase or
section outcomes, validator findings, costs, model choices, workflow lessons, reusable summaries,
and preferences inferred from tome work. Do not put such information in provider memory folders,
auto-memory, profile notes, global instruction files, skills, or user-memory features.

Tome state belongs only in the authorized repository and harness artifacts for the current job.
Provider-managed session transcripts may exist for resume/accounting, but they are not permission
to create or update persistent memory, including a supposedly generic lesson distilled from this
work."""

from .models import AiInvocation, AiRequest, AiResponse
from .registry import ProviderRegistry
from .roles import AiRoleRegistry, AiRoleSpec
from .service import AiService, build_default_ai_service

__all__ = ["AiInvocation", "AiRequest", "AiResponse", "AiRoleRegistry", "AiRoleSpec",
           "AiService", "NO_TOME_MEMORY_POLICY", "ProviderRegistry",
           "build_default_ai_service"]
