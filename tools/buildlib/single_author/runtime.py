"""Provider CLI setup and structured-output parsing for the single author."""
import os
import subprocess

from ..runtime.events import (assistant_text, error_text, opencode_output_session_id,
                              session_id_from_line, usage_from_line)
from ..runtime.runners import author_runner


AUTHOR_COMPACT_TOKEN_LIMIT = 80_000


def _codex_context_limit_args():
    return ["-c", f"model_auto_compact_token_limit={AUTHOR_COMPACT_TOKEN_LIMIT}"]


def resume_command(kind, model, effort, session_id, prompt):
    if kind == "codex-cli":
        cmd = [os.path.expanduser("~/.local/bin/codex"), "--search", "exec", "resume",
               session_id, "--skip-git-repo-check", "--json",
               "-m", model, *_codex_context_limit_args()]
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


def runner_stdin(input_mode):
    """Argument-mode CLIs must see EOF instead of an unused, permanently open pipe."""
    return subprocess.PIPE if input_mode == "stdin" else subprocess.DEVNULL
