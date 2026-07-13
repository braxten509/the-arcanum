"""Regression checks for every split-section runner security boundary."""
import atexit
import json
import os
import shutil
import subprocess

from . import BUILD_DIR, REPO
from .agent_runtime import section_runner_command


def run(spec_to_runner):
    root = os.path.join(REPO, ".ai-runtime-probe-section")
    sidecar = os.path.join(BUILD_DIR, "section-security-selftest-handoff.json")
    readonly = os.path.join(REPO, ".ai-runtime-probe-readonly")

    def cleanup():
        shutil.rmtree(root, ignore_errors=True)
        for path in (sidecar, readonly):
            try:
                os.remove(path)
            except OSError:
                pass

    cleanup()
    atexit.register(cleanup)
    os.makedirs(root, exist_ok=True)
    with open(sidecar, "w", encoding="utf-8"):
        pass
    with open(readonly, "w", encoding="utf-8") as f:
        f.write("original")
    _, claude_cmd, _ = spec_to_runner("claude-cli:claude-sonnet-5@medium", "--runner")
    assert claude_cmd[claude_cmd.index("--permission-mode") + 1] == "auto", claude_cmd
    guarded = section_runner_command("claude-cli claude-sonnet-5 @medium", claude_cmd, root, "/repo")
    settings = json.loads(guarded[guarded.index("--settings") + 1])
    assert settings["sandbox"]["enabled"] is False, settings
    assert "WebSearch" in settings["permissions"]["allow"], settings
    with_sidecar = section_runner_command("claude sidecar", claude_cmd, root, "/repo",
                                          writable_sidecars=[sidecar])
    assert ["--bind", sidecar, sidecar] == with_sidecar[
        with_sidecar.index(sidecar) - 1:with_sidecar.index(sidecar) + 2], with_sidecar
    # Execute the exact bwrap prefix with a plain shell in place of the AI binary. The
    # assigned section and exact handoff must be writable; an adjacent repo file must not.
    agent_i = next(i for i, value in enumerate(with_sidecar)
                   if os.path.basename(value) == "claude" and os.path.isfile(value)
                   and os.access(value, os.X_OK))
    probe = [*with_sidecar[:agent_i], "/bin/sh", "-c",
             'set -eu; printf section > inside.txt; printf handoff > "$SIDECAR"; '
             'if (printf forbidden > "$READONLY") 2>/dev/null; then exit 9; fi']
    env = os.environ.copy()
    env.update(SIDECAR=sidecar, READONLY=readonly)
    ran = subprocess.run(probe, env=env, capture_output=True, text=True, timeout=10)
    assert ran.returncode == 0, (ran.stdout, ran.stderr)
    assert open(os.path.join(root, "inside.txt"), encoding="utf-8").read() == "section"
    assert open(sidecar, encoding="utf-8").read() == "handoff"
    assert open(readonly, encoding="utf-8").read() == "original"
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
    cleanup()
    atexit.unregister(cleanup)
