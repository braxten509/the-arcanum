"""Side-effect boundary implemented by every AI transport adapter."""
from __future__ import annotations

from typing import Protocol

from .models import AiRequest, AiResponse


class AiProvider(Protocol):
    provider_id: str
    version: int
    capabilities: tuple[str, ...]

    def complete(self, request: AiRequest) -> AiResponse: ...
