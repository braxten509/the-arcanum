"""Validated explicit AI provider registry."""
from __future__ import annotations

from .models import AiInvocation, AiRequest, AiResponse
from .ports import AiProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, AiProvider] = {}

    def register(self, provider: AiProvider) -> None:
        provider_id = str(getattr(provider, "provider_id", "") or "")
        if not provider_id:
            raise ValueError("AI provider needs a stable provider_id")
        if provider_id in self._providers:
            raise ValueError(f"duplicate AI provider {provider_id!r}")
        self._providers[provider_id] = provider

    def complete(self, provider_id: str, request: AiRequest) -> AiResponse:
        return self._provider(provider_id).complete(request)

    def invocation(self, provider_id: str, request: AiRequest) -> AiInvocation:
        provider = self._provider(provider_id)
        factory = getattr(provider, "invocation", None)
        if not callable(factory):
            raise ValueError(f"AI provider {provider_id!r} has no streaming CLI invocation")
        return factory(request)

    def _provider(self, provider_id: str):
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            available = ", ".join(sorted(self._providers)) or "none"
            raise ValueError(
                f"unknown AI provider {provider_id!r}; configured providers: {available}") from exc

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))
