"""Login-CLI and local-model transport adapters."""
from __future__ import annotations

import os
import subprocess

from tools.buildlib.runtime.agent_runtime import scoped_runner_command

from ...authoring.ai_access import ensure_cli_access, ensure_remote_access
from ...config import (AGY_BIN, CLAUDE_BIN, CODEX_BIN, OPENCODE_BIN, ROOT,
                       agy_print_args, codex_no_mcp_args)
from ..models import AiRequest, AiResponse


class _CliProvider:
    provider_id = ""

    def command(self, request: AiRequest) -> tuple[list[str], str]:
        raise NotImplementedError

    def complete(self, request: AiRequest) -> AiResponse:
        command, input_mode = self.command(request)
        command = scoped_runner_command(
            self.provider_id, command, request.workspace, [], ROOT)
        ensure_cli_access(
            f"{self.provider_id} {request.model}".strip(), command, input_mode)
        environment = {key: value for key, value in os.environ.items() if key != "CLAUDECODE"}
        environment.update(ARCANUM_REPO_ROOT=ROOT, ARCANUM_TOME_ROOT=request.workspace,
                           PYTHONDONTWRITEBYTECODE="1")
        process = subprocess.run(
            command + ([request.input] if input_mode == "arg" else []),
            input=request.input if input_mode == "stdin" else None,
            capture_output=True, text=True, timeout=request.timeout,
            env=environment, cwd=request.workspace)
        if process.returncode:
            raise RuntimeError(f"exit {process.returncode}: {process.stderr[:500]}")
        return AiResponse(self.provider_id, request.model, process.stdout,
                          {"role": request.role, **request.trace})


class ClaudeCliProvider(_CliProvider):
    provider_id = "claude-cli"

    def command(self, request: AiRequest) -> tuple[list[str], str]:
        command = [CLAUDE_BIN, "-p", "--permission-mode", "auto"]
        if request.model:
            command += ["--model", request.model]
        return command, "arg"


class AntigravityCliProvider(_CliProvider):
    provider_id = "antigravity-cli"

    def command(self, request: AiRequest) -> tuple[list[str], str]:
        if request.model:
            from ...models import GraderConfigError, agy_models
            if request.model not in agy_models():
                raise GraderConfigError(
                    f"model {request.model!r} does not exist in agy; run `agy models`")
        command = [AGY_BIN, "--dangerously-skip-permissions",
                   *agy_print_args(request.timeout)]
        if request.model:
            command += ["--model", request.model]
        return [*command, "--print"], "arg"


class CodexCliProvider(_CliProvider):
    provider_id = "codex-cli"

    def command(self, request: AiRequest) -> tuple[list[str], str]:
        command = [CODEX_BIN, "--search", "exec", "--skip-git-repo-check",
                   "-s", "read-only", *codex_no_mcp_args()]
        if request.model:
            command += ["-m", request.model]
        return [*command, "-"], "stdin"


class OpenCodeCliProvider(_CliProvider):
    provider_id = "opencode-cli"

    def command(self, request: AiRequest) -> tuple[list[str], str]:
        command = [OPENCODE_BIN, "run", "--auto"]
        if request.model:
            command += ["-m", request.model]
        return command, "arg"


class OllamaProvider:
    provider_id = "ollama"

    def __init__(self, transport: _CliProvider | None = None):
        self.transport = transport or OpenCodeCliProvider()

    def complete(self, request: AiRequest) -> AiResponse:
        ensure_remote_access("ollama", request.model)
        model = request.model if request.model.startswith("ollama/") else "ollama/" + request.model
        response = self.transport.complete(AiRequest(
            role=request.role, model=model, input=request.input, timeout=request.timeout,
            workspace=request.workspace, response_schema=request.response_schema,
            allowed_tools=request.allowed_tools, web_allowed=request.web_allowed,
            trace=request.trace))
        return AiResponse(self.provider_id, request.model, response.text, response.trace)
