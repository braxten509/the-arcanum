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
        version = getattr(provider, "version", None)
        capabilities = getattr(provider, "capabilities", None)
        if not isinstance(version, int) or version < 1:
            raise ValueError(f"AI provider {provider_id!r} needs a positive version")
        if (not isinstance(capabilities, tuple) or not capabilities
                or any(not isinstance(item, str) or not item for item in capabilities)):
            raise ValueError(f"AI provider {provider_id!r} needs tuple capabilities")
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

    def entries(self) -> tuple[AiProvider, ...]:
        return tuple(self._providers[key] for key in sorted(self._providers))
