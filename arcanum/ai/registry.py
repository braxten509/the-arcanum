"""Validated explicit AI provider registry."""
from __future__ import annotations

from .models import AiRequest, AiResponse
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
        try:
            provider = self._providers[provider_id]
        except KeyError as exc:
            available = ", ".join(sorted(self._providers)) or "none"
            raise ValueError(
                f"unknown AI provider {provider_id!r}; configured providers: {available}") from exc
        return provider.complete(request)

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))
