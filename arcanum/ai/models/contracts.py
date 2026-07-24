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
    writable_paths: tuple[str, ...] = ()
    readonly_paths: tuple[str, ...] = ()
    trace: dict = field(default_factory=dict)
    permission_paths: dict | None = None
    state_scope: dict | None = None
    stream_events: bool = False


@dataclass(frozen=True)
class AiResponse:
    provider: str
    model: str
    text: str
    trace: dict = field(default_factory=dict)


@dataclass(frozen=True)
class AiInvocation:
    argv: tuple[str, ...]
    input_mode: str
    environment: dict[str, str]
    cwd: str
