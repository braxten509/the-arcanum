"""Login-CLI and local-model transport adapters."""
from __future__ import annotations

import os
import subprocess

from arcanum.platform.agent_commands import scoped_runner_command

from ..access import ensure_cli_access, ensure_remote_access
from ..contracts.errors import ProviderConfigurationError
from ...config import (AGY_BIN, CLAUDE_BIN, CODEX_BIN, OPENCODE_BIN, ROOT,
                       agy_print_args, codex_no_mcp_args)
from ..models import AiInvocation, AiRequest, AiResponse


class _CliProvider:
    provider_id = ""
    version = 1
    capabilities = ("completion", "streaming-invocation", "tool-policy", "web-policy")

    def command(self, request: AiRequest) -> tuple[list[str], str]:
        raise NotImplementedError

    def invocation(self, request: AiRequest) -> AiInvocation:
        command, input_mode = self.command(request)
        workspace = os.path.realpath(request.workspace)
        tomes_root = os.path.join(ROOT, "tomes")
        if os.path.commonpath((workspace, tomes_root)) == tomes_root:
            raise ProviderConfigurationError(
                "generic CLI tome work has no declared permission profile; use the Forge role runner")
        command = scoped_runner_command(
            self.provider_id, command, request.workspace,
            list(request.writable_paths), ROOT,
            readonly_paths=request.readonly_paths, web_allowed=request.web_allowed)
        ensure_cli_access(
            f"{self.provider_id} {request.model}".strip(), command, input_mode)
        environment = {key: value for key, value in os.environ.items() if key != "CLAUDECODE"}
        environment.update(ARCANUM_REPO_ROOT=ROOT, ARCANUM_TOME_ROOT=request.workspace,
                           PYTHONDONTWRITEBYTECODE="1")
        return AiInvocation(tuple(command), input_mode, environment, request.workspace)

    def complete(self, request: AiRequest) -> AiResponse:
        invocation = self.invocation(request)
        command, input_mode = list(invocation.argv), invocation.input_mode
        process = subprocess.run(
            command + ([request.input] if input_mode == "arg" else []),
            input=request.input if input_mode == "stdin" else None,
            capture_output=True, text=True, timeout=request.timeout,
            env=invocation.environment, cwd=invocation.cwd)
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
        if request.effort:
            command += ["--effort", request.effort]
        return command, "arg"


class AntigravityCliProvider(_CliProvider):
    provider_id = "antigravity-cli"

    def command(self, request: AiRequest) -> tuple[list[str], str]:
        if request.model:
            from .discovery import agy_models
            if request.model not in agy_models():
                raise ProviderConfigurationError(
                    f"model {request.model!r} does not exist in agy; run `agy models`")
        command = [AGY_BIN, "--dangerously-skip-permissions",
                   *agy_print_args(request.timeout)]
        if request.model:
            command += ["--model", request.model]
        return [*command, "--print"], "arg"


class CodexCliProvider(_CliProvider):
    provider_id = "codex-cli"

    def command(self, request: AiRequest) -> tuple[list[str], str]:
        command = [CODEX_BIN, "exec", "--skip-git-repo-check",
                   "-s", "read-only", *codex_no_mcp_args()]
        if request.model:
            command += ["-m", request.model]
        if request.effort:
            command += ["-c", f"model_reasoning_effort={request.effort}"]
        return [*command, "-"], "stdin"


class OpenCodeCliProvider(_CliProvider):
    provider_id = "opencode-cli"

    def command(self, request: AiRequest) -> tuple[list[str], str]:
        command = [OPENCODE_BIN, "run", "--auto"]
        if request.model:
            command += ["-m", request.model]
        if request.effort:
            command += ["--variant", request.effort]
        return command, "arg"


class OllamaProvider:
    provider_id = "ollama"
    version = 1
    capabilities = ("completion", "local-model")

    def __init__(self, transport: _CliProvider | None = None):
        self.transport = transport or OpenCodeCliProvider()

    def complete(self, request: AiRequest) -> AiResponse:
        ensure_remote_access("ollama", request.model)
        model = request.model if request.model.startswith("ollama/") else "ollama/" + request.model
        response = self.transport.complete(AiRequest(
            role=request.role, model=model, input=request.input, timeout=request.timeout,
            workspace=request.workspace, response_schema=request.response_schema,
            allowed_tools=request.allowed_tools, web_allowed=request.web_allowed,
            effort=request.effort, trace=request.trace))
        return AiResponse(self.provider_id, request.model, response.text, response.trace)
