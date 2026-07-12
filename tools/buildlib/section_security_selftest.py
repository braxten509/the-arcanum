"""Regression checks for every split-section runner security boundary."""
import json
import os
import tempfile

from .agent_runtime import section_runner_command


def run(spec_to_runner):
    root = os.path.join(tempfile.gettempdir(), "arcanum-section-security-selftest")
    os.makedirs(root, exist_ok=True)
    _, claude_cmd, _ = spec_to_runner("claude-cli:claude-sonnet-5@medium", "--runner")
    assert claude_cmd[claude_cmd.index("--permission-mode") + 1] == "auto", claude_cmd
    guarded = section_runner_command("claude-cli claude-sonnet-5 @medium", claude_cmd, root, "/repo")
    settings = json.loads(guarded[guarded.index("--settings") + 1])
    assert settings["sandbox"]["enabled"] is False, settings
    assert "WebSearch" in settings["permissions"]["allow"], settings
    _, codex_cmd, _ = spec_to_runner("codex-cli:gpt-5.5@high", "--runner")
    assert "--search" in codex_cmd and "workspace-write" in codex_cmd, codex_cmd
    codex_scoped = section_runner_command("codex alias", codex_cmd, root, "/repo")
    assert "--search" in codex_scoped and "danger-full-access" in codex_scoped, codex_scoped
    assert ["--bind", "/tmp", "/tmp"] == codex_scoped[
        codex_scoped.index("/tmp") - 1:codex_scoped.index("/tmp") + 2], codex_scoped
    for spec, prefix in (("antigravity-cli:Gemini 3.1 Pro (High)", "antigravity-cli "),
                         ("opencode-cli:opencode-go/deepseek-v4-pro", "opencode-cli ")):
        name, cmd, _ = spec_to_runner(spec, "--runner")
        wrapped = section_runner_command(name, cmd, root, "/repo")
        assert os.path.basename(wrapped[0]) == "bwrap", wrapped
        assert ["--ro-bind", "/", "/"] == wrapped[wrapped.index("--ro-bind"):wrapped.index("--ro-bind") + 3]
        assert root in wrapped and prefix in name, wrapped
    try:
        section_runner_command("future alias", ["unknown-agent"], root, "/repo")
    except RuntimeError as exc:
        assert "has no Arcanum access policy" in str(exc), exc
    else:
        raise AssertionError("unknown split-section runners must fail closed")
