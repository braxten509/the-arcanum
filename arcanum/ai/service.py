"""AI application service and explicit default composition."""
from __future__ import annotations

from .models import AiInvocation, AiRequest, AiResponse
from .providers import (AnthropicProvider, AntigravityCliProvider, ClaudeCliProvider,
                        CodexCliProvider, CustomCommandProvider, OllamaProvider,
                        OpenAiProvider, OpenCodeCliProvider)
from .registry import ProviderRegistry
from .roles import AiRoleRegistry, default_role_registry


class AiService:
    def __init__(self, providers: ProviderRegistry, roles: AiRoleRegistry | None = None):
        self.providers = providers
        self.roles = roles or default_role_registry()

    def complete(self, provider_id: str, request: AiRequest) -> AiResponse:
        self.roles.get(request.role)
        return self.providers.complete(provider_id, request)

    def invocation(self, provider_id: str, request: AiRequest) -> AiInvocation:
        self.roles.get(request.role)
        return self.providers.invocation(provider_id, request)


def build_default_ai_service() -> AiService:
    registry = ProviderRegistry()
    for provider in (ClaudeCliProvider(), AntigravityCliProvider(), CodexCliProvider(),
                     OpenCodeCliProvider(), OllamaProvider(), AnthropicProvider(),
                     OpenAiProvider(), CustomCommandProvider()):
        registry.register(provider)
    return AiService(registry)
