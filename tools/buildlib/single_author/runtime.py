"""Provider CLI setup and structured-output parsing for the single author."""
import json
import os
import subprocess

from ..runtime.runners import author_runner


AUTHOR_COMPACT_TOKEN_LIMIT = 80_000


def _codex_context_limit_args():
    return ["-c", f"model_auto_compact_token_limit={AUTHOR_COMPACT_TOKEN_LIMIT}"]


def resume_command(kind, model, effort, session_id, prompt):
    if kind == "codex-cli":
        cmd = [os.path.expanduser("~/.local/bin/codex"), "--search", "exec", "resume",
               session_id, "--skip-git-repo-check", "--json",
               *_codex_context_limit_args()]
        if effort:
            cmd += ["-c", f"model_reasoning_effort={effort}"]
        cmd.append(prompt)
        return (f"{kind} {model}", cmd, "none")
    if kind == "claude-cli":
        cmd = ["claude", "--resume", session_id, "-p", "--permission-mode", "auto",
               "--model", model, "--output-format", "stream-json", "--verbose"]
        if effort:
            cmd += ["--effort", effort]
        cmd.append(prompt)
        return (f"{kind} {model}", cmd, "none")
    if kind == "opencode-cli":
        cmd = ["opencode", "run", "--auto", "--session", session_id,
               "--format", "json", "-m", model]
        if effort:
            cmd += ["--variant", effort]
        cmd.append(prompt)
        return (f"{kind} {model}", cmd, "none")
    cmd = ["agy", "--dangerously-skip-permissions", "--print-timeout", "4h",
           "--conversation", session_id, "--model", model, "--print", prompt]
    return (f"{kind} {model}", cmd, "none")


def initial_runner(kind, model, effort):
    display, cmd, input_mode = author_runner(
        f"{kind}:{model}" + (f"@{effort}" if effort else ""), "--author")
    if kind == "codex-cli":
        position = cmd.index("-") if "-" in cmd else len(cmd)
        cmd[position:position] = ["--json", *_codex_context_limit_args()]
    elif kind == "claude-cli":
        cmd += ["--output-format", "stream-json", "--verbose"]
    elif kind == "opencode-cli":
        cmd[cmd.index("run") + 1:cmd.index("run") + 1] = ["--format", "json"]
    return display, cmd, input_mode


def assistant_text(line):
    try:
        row = json.loads(line)
    except ValueError:
        return ""
    if not isinstance(row, dict):
        return ""
    item = row.get("item")
    if (row.get("type") == "item.completed" and isinstance(item, dict)
            and item.get("type") == "agent_message"):
        return str(item.get("text") or "")
    if row.get("type") == "assistant":
        message = row.get("message")
        content = (message.get("content") or []) if isinstance(message, dict) else []
        if not isinstance(content, list):
            return ""
        return "\n".join(str(block.get("text") or "") for block in content
                         if isinstance(block, dict) and block.get("type") == "text")
    part = row.get("part") or row.get("message") or {}
    if isinstance(part, dict) and part.get("type") in ("text", "assistant"):
        return str(part.get("text") or part.get("content") or "")
    return ""


def usage_from_line(line):
    """Normalize provider turn-usage rows without assuming one CLI schema."""
    try:
        row = json.loads(line)
    except ValueError:
        return None
    if not isinstance(row, dict):
        return None
    usage = row.get("usage") or row.get("token_usage")
    if not isinstance(usage, dict):
        item = row.get("item")
        usage = item.get("usage") if isinstance(item, dict) else None
    if not isinstance(usage, dict):
        return None
    input_details = usage.get("input_tokens_details") or {}
    output_details = usage.get("output_tokens_details") or {}
    if isinstance(input_details, dict):
        usage = {**input_details, **usage}
    if isinstance(output_details, dict):
        usage = {**output_details, **usage}
    aliases = {
        "inputTokens": ("input_tokens", "inputTokens"),
        "cachedInputTokens": ("cached_input_tokens", "cachedInputTokens", "cached_tokens"),
        "cacheWriteTokens": ("cache_write_tokens", "cacheWriteTokens"),
        "outputTokens": ("output_tokens", "outputTokens"),
        "reasoningTokens": ("reasoning_tokens", "reasoningTokens"),
        "totalTokens": ("total_tokens", "totalTokens"),
    }
    normalized = {}
    for target, names in aliases.items():
        value = next((usage.get(name) for name in names if usage.get(name) is not None), None)
        if isinstance(value, (int, float)):
            normalized[target] = int(value)
    if "inputTokens" in normalized:
        normalized["freshInputTokens"] = max(
            0, normalized["inputTokens"] - normalized.get("cachedInputTokens", 0)
            - normalized.get("cacheWriteTokens", 0))
    return normalized or None


def opencode_output_session_id(line):
    """Read the exact session id OpenCode emits on its own structured stream."""
    try:
        row = json.loads(line)
    except ValueError:
        return ""
    if not isinstance(row, dict):
        return ""
    part = row.get("part")
    return str(row.get("sessionID") or (
        part.get("sessionID") if isinstance(part, dict) else "") or "")


def runner_stdin(input_mode):
    """Argument-mode CLIs must see EOF instead of an unused, permanently open pipe."""
    return subprocess.PIPE if input_mode == "stdin" else subprocess.DEVNULL
