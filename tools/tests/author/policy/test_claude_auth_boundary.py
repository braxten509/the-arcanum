#!/usr/bin/env python3
"""Claude gets headless auth without host session or persistent-memory state."""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from arcanum.platform import agent_scratch  # noqa: E402
from arcanum.platform.agent_commands import scoped_runner_command  # noqa: E402
from tools.buildlib.single_author.session.turn import (  # noqa: E402
    claude_headless_authentication_error,
    claude_headless_environment,
)


with tempfile.TemporaryDirectory() as root:
    fake_home = os.path.join(root, "home")
    scratch_root = os.path.join(root, "scratch")
    binary_dir = os.path.join(root, "bin")
    fake = os.path.join(binary_dir, "claude")
    os.makedirs(binary_dir)
    with open(fake, "w", encoding="utf-8") as handle:
        handle.write("#!/bin/sh\nexit 0\n")
    os.chmod(fake, 0o755)

    host_state = {
        "firstStartTime": 1234,
        "hasCompletedOnboarding": True,
        "projects": {"/secret/project": {"memory": "must not cross"}},
        "toolUsage": {"Read": 999},
    }
    os.makedirs(os.path.join(fake_home, ".claude"))
    with open(os.path.join(fake_home, ".claude.json"), "w", encoding="utf-8") as handle:
        json.dump(host_state, handle)
    with open(
            os.path.join(fake_home, ".claude", ".credentials.json"),
            "w", encoding="utf-8") as handle:
        json.dump({
            "claudeAiOauth": {
                "accessToken": "",
                "refreshToken": "",
            },
        }, handle)

    old_scratch_root = agent_scratch.ROOT
    try:
        agent_scratch.ROOT = scratch_root
        with patch.dict(os.environ, {"HOME": fake_home}, clear=True):
            build_scratch = agent_scratch.prepare("build")
            permissions = {
                "system_read": ["/usr", "/bin", "/lib", "/lib64", "/etc", "/proc"],
                "system_both": [build_scratch, "/dev"],
                "read": [],
                "write": [],
                "both": [],
                "execute": [],
            }
            scope = {
                "build_id": "build", "role": "author", "phase": 3, "section": "s01",
            }
            command = scoped_runner_command(
                "Claude isolated state", [fake, "-p", "hello"], root, [], root,
                permission_paths=permissions, state_scope=scope)
            s01_mounts = agent_scratch.provider_state_mounts(
                "claude", "build", "author", 3, "s01")
            repeated = agent_scratch.provider_state_mounts(
                "claude", "build", "author", 3, "s01")
            s02_mounts = agent_scratch.provider_state_mounts(
                "claude", "build", "author", 3, "s02")

            error = claude_headless_authentication_error("claude-cli")
            assert "claude setup-token" in error
            token_file = os.path.join(
                fake_home, ".config", "arcanum", "claude-oauth-token")
            os.makedirs(os.path.dirname(token_file))
            with open(token_file, "w", encoding="utf-8") as handle:
                handle.write("private-test-token\n")
            os.chmod(token_file, 0o600)
            additions, error = claude_headless_environment("claude-cli")
            assert error == ""
            assert additions == {"CLAUDE_CODE_OAUTH_TOKEN": "private-test-token"}
            os.chmod(token_file, 0o644)
            additions, error = claude_headless_environment("claude-cli")
            assert additions == {}
            assert "mode 0600" in error
            assert "private-test-token" not in error
            os.remove(token_file)
            with patch.dict(
                    os.environ, {"HOME": fake_home, "CLAUDE_CODE_OAUTH_TOKEN": "test"},
                    clear=True):
                assert claude_headless_authentication_error("claude-cli") == ""

            with open(
                    os.path.join(fake_home, ".claude", ".credentials.json"),
                    "w", encoding="utf-8") as handle:
                json.dump({
                    "claudeAiOauth": {
                        "accessToken": "test",
                        "refreshToken": "refresh",
                    },
                }, handle)
            assert claude_headless_authentication_error("claude-cli") == ""
    finally:
        agent_scratch.ROOT = old_scratch_root

    assert s01_mounts == repeated
    assert s01_mounts != s02_mounts
    by_target = {target: source for source, target in s01_mounts}
    host_credentials = os.path.join(fake_home, ".claude", ".credentials.json")
    assert by_target[host_credentials] == host_credentials
    isolated_root = by_target[os.path.join(fake_home, ".claude.json")]
    with open(isolated_root, encoding="utf-8") as handle:
        isolated_state = json.load(handle)
    assert isolated_state == {
        "firstStartTime": 1234,
        "hasCompletedOnboarding": True,
    }
    assert "projects" not in isolated_state
    assert "toolUsage" not in isolated_state

    bind_pairs = [
        (command[index + 1], command[index + 2])
        for index, item in enumerate(command[:-2]) if item == "--bind"
    ]
    assert all(pair in bind_pairs for pair in s01_mounts)

print("Claude headless authentication boundary: OK")
