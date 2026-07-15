"""Agent CLI command templates for the freely chosen single tome author."""
import os
import sys


def _codex_no_mcp():
    import tomllib
    try:
        with open(os.path.expanduser("~/.codex/config.toml"), "rb") as handle:
            servers = tomllib.load(handle).get("mcp_servers", {})
    except (OSError, tomllib.TOMLDecodeError):
        return []
    return [arg for name in servers for arg in
            ("-c", f"mcp_servers.{name}.enabled=false")]


CLI_RUNNERS = {
    "claude-cli": {
        "cmd": ["claude", "-p", "--permission-mode", "auto", "--model", "{model}"],
        "input": "arg", "efforts": ("low", "medium", "high", "xhigh", "max"),
        "effortArgs": ["--effort", "{effort}"],
    },
    "antigravity-cli": {
        "cmd": ["agy", "--dangerously-skip-permissions", "--print-timeout", "4h",
                "--model", "{model}", "--print"], "input": "arg",
    },
    "codex-cli": {
        "cmd": [os.path.expanduser("~/.local/bin/codex")
                if os.access(os.path.expanduser("~/.local/bin/codex"), os.X_OK) else "codex",
                "--search", "exec", "--skip-git-repo-check", "-s", "workspace-write",
                *_codex_no_mcp(), "-m", "{model}", "-"],
        "input": "stdin", "efforts": ("low", "medium", "high", "xhigh", "max", "ultra"),
        "effortArgs": ["-c", "model_reasoning_effort={effort}"],
    },
    "opencode-cli": {
        "cmd": ["opencode", "run", "--auto", "-m", "{model}"], "input": "arg",
        "efforts": ("none", "minimal", "low", "medium", "high", "max"),
        "effortArgs": ["--variant", "{effort}"],
    },
}


def author_runner(spec, context="--author"):
    """Convert ``KIND:MODEL[@EFFORT]`` to display, argv, and prompt-input mode."""
    kind, separator, model = str(spec).partition(":")
    model, effort_separator, effort = model.rpartition("@")
    if not effort_separator:
        model, effort = str(spec).partition(":")[2], ""
    template = CLI_RUNNERS.get(kind)
    if not separator or not template or not model:
        sys.exit(f"{context} wants <{'|'.join(CLI_RUNNERS)}>:<model>[@effort], got {spec!r}")
    command = [arg.replace("{model}", model) for arg in template["cmd"]]
    if effort:
        allowed = template.get("efforts", ())
        if effort not in allowed:
            sys.exit(f"{context}: {kind} does not support effort {effort!r}")
        extra = [arg.replace("{effort}", effort) for arg in template["effortArgs"]]
        position = len(command) - 1 if command[-1] == "-" else len(command)
        command[position:position] = extra
    display = f"{kind} {model}" + (f" @{effort}" if effort else "")
    return display, command, template["input"]


_spec_to_runner = author_runner  # compatibility for narrow local callers
