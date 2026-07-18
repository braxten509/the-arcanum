"""Provider-neutral AI role contracts and explicit default composition."""

from .composition import default_role_registry
from .registry import AiRoleRegistry, AiRoleSpec

__all__ = ["AiRoleRegistry", "AiRoleSpec", "default_role_registry"]
