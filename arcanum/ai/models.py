"""Immutable provider-neutral AI request and response contracts."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AiRequest:
    role: str
    model: str
    input: str
    timeout: int
    workspace: str
    response_schema: dict | None = None
    allowed_tools: tuple[str, ...] = ()
    web_allowed: bool = False
    effort: str = ""
    api_key: str = ""
    custom_command: str = ""
    trace: dict = field(default_factory=dict)


@dataclass(frozen=True)
class AiResponse:
    provider: str
    model: str
    text: str
    trace: dict = field(default_factory=dict)
