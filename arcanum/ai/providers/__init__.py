"""Concrete provider adapters; role prompts never live in this package."""

from .api import AnthropicProvider, OpenAiProvider
from .cli import (AntigravityCliProvider, ClaudeCliProvider, CodexCliProvider,
                  OllamaProvider, OpenCodeCliProvider)
from .custom_command import CustomCommandProvider

__all__ = ["AnthropicProvider", "OpenAiProvider", "AntigravityCliProvider",
           "ClaudeCliProvider", "CodexCliProvider", "OllamaProvider",
           "OpenCodeCliProvider", "CustomCommandProvider"]
