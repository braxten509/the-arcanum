"""Explicit user-configured command transport."""
from __future__ import annotations

import subprocess

from tools.buildlib.runtime.agent_runtime import scoped_shell_command

from ...authoring.ai_access import ensure_command_access
from ..models import AiRequest, AiResponse


class CustomCommandProvider:
    provider_id = "other"

    def complete(self, request: AiRequest) -> AiResponse:
        if not request.custom_command.strip():
            raise ValueError("no custom AI command is configured")
        command = scoped_shell_command(request.custom_command, request.workspace)
        ensure_command_access(command, request.workspace)
        process = subprocess.run(command, input=request.input, capture_output=True,
                                 text=True, timeout=request.timeout, cwd=request.workspace)
        if process.returncode:
            raise RuntimeError(f"exit {process.returncode}: {process.stderr[:500]}")
        return AiResponse(self.provider_id, request.model, process.stdout,
                          {"role": request.role, **request.trace})
