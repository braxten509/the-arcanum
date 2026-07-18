"""AI application service and explicit default composition."""
from __future__ import annotations

from .models import AiRequest, AiResponse
from .providers import (AnthropicProvider, AntigravityCliProvider, ClaudeCliProvider,
                        CodexCliProvider, CustomCommandProvider, OllamaProvider,
                        OpenAiProvider, OpenCodeCliProvider)
from .registry import ProviderRegistry


class AiService:
    def __init__(self, providers: ProviderRegistry):
        self.providers = providers

    def complete(self, provider_id: str, request: AiRequest) -> AiResponse:
        return self.providers.complete(provider_id, request)


def build_default_ai_service() -> AiService:
    registry = ProviderRegistry()
    for provider in (ClaudeCliProvider(), AntigravityCliProvider(), CodexCliProvider(),
                     OpenCodeCliProvider(), OllamaProvider(), AnthropicProvider(),
                     OpenAiProvider(), CustomCommandProvider()):
        registry.register(provider)
    return AiService(registry)
