#!/usr/bin/env python3
"""OpenCode can persist its own unit while remaining blind to every other unit."""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from arcanum.platform import agent_scratch  # noqa: E402
from arcanum.platform.agent_commands import scoped_runner_command  # noqa: E402


with tempfile.TemporaryDirectory() as root:
    fake_home = os.path.join(root, "home")
    scratch_root = os.path.join(root, "scratch")
    binary_dir = os.path.join(root, "bin")
    fake = os.path.join(binary_dir, "opencode")
    os.makedirs(binary_dir)
    with open(fake, "w", encoding="utf-8") as handle:
        handle.write("#!/bin/sh\nexit 0\n")
    os.chmod(fake, 0o755)

    host_config = os.path.join(fake_home, ".config", "opencode")
    host_share = os.path.join(fake_home, ".local", "share", "opencode")
    host_cache = os.path.join(fake_home, ".cache", "opencode")
    host_state = os.path.join(fake_home, ".local", "state", "opencode")
    for directory in (host_config, host_share, host_cache, host_state):
        os.makedirs(directory, exist_ok=True)
    with open(os.path.join(host_config, "opencode.jsonc"), "w", encoding="utf-8") as handle:
        handle.write('{"provider":"openrouter"}\n')
    with open(os.path.join(host_share, "auth.json"), "w", encoding="utf-8") as handle:
        handle.write('{"credential":"test-only"}\n')
    forbidden = (
        os.path.join(host_share, "opencode.db"),
        os.path.join(host_share, "opencode.log"),
        os.path.join(host_share, "storage", "session_diff", "old.json"),
        os.path.join(host_cache, "old-tool-output"),
        os.path.join(host_state, "old-session"),
    )
    for filename in forbidden:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, "w", encoding="utf-8") as handle:
            handle.write("prior unit secret\n")

    old_scratch_root = agent_scratch.ROOT
    try:
        agent_scratch.ROOT = scratch_root
        with patch.dict(os.environ, {"HOME": fake_home}):
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
                "OpenCode isolated state", [fake, "run"], root, [], root,
                permission_paths=permissions, state_scope=scope)
            s01_mounts = agent_scratch.provider_state_mounts(
                "opencode", "build", "author", 3, "s01")
            repeated_mounts = agent_scratch.provider_state_mounts(
                "opencode", "build", "author", 3, "s01")
            s02_mounts = agent_scratch.provider_state_mounts(
                "opencode", "build", "author", 3, "s02")
            s01_temp = agent_scratch.unit_temp("build", "author", 3, "s01")
            s02_temp = agent_scratch.unit_temp("build", "author", 3, "s02")
    finally:
        agent_scratch.ROOT = old_scratch_root

    assert s01_mounts == repeated_mounts
    assert s01_mounts != s02_mounts
    assert s01_temp != s02_temp
    bind_pairs = [
        (command[index + 1], command[index + 2])
        for index, item in enumerate(command[:-2]) if item == "--bind"
    ]
    assert (s01_temp, "/tmp") in bind_pairs
    assert (build_scratch, "/tmp") not in bind_pairs
    assert all(pair in bind_pairs for pair in s01_mounts)
    assert all(not source.startswith(s01_temp + os.sep) for source, _target in s01_mounts)

    by_target = {target: source for source, target in s01_mounts}
    isolated_config = by_target[host_config]
    isolated_share = by_target[host_share]
    isolated_cache = by_target[host_cache]
    isolated_state = by_target[host_state]
    assert os.path.isfile(os.path.join(isolated_config, "opencode.jsonc"))
    assert os.path.isfile(os.path.join(isolated_share, "auth.json"))
    assert not os.path.exists(os.path.join(isolated_share, "opencode.db"))
    assert not os.path.exists(os.path.join(isolated_share, "opencode.log"))
    assert not os.path.exists(os.path.join(
        isolated_share, "storage", "session_diff", "old.json"))
    assert not os.path.exists(os.path.join(isolated_cache, "old-tool-output"))
    assert not os.path.exists(os.path.join(isolated_state, "old-session"))
    assert all(not os.path.exists(os.path.join(
        source, "opencode.db")) for source, _target in s02_mounts)
    with patch.object(agent_scratch, "ROOT", scratch_root):
        assert not agent_scratch.provider_session_exists(
            "opencode", "build", "author", 3, "s01", "ses_current")
        with sqlite3.connect(os.path.join(isolated_share, "opencode.db")) as connection:
            connection.execute("CREATE TABLE session (id text PRIMARY KEY)")
            connection.execute("INSERT INTO session (id) VALUES (?)", ("ses_current",))
        assert agent_scratch.provider_session_exists(
            "opencode", "build", "author", 3, "s01", "ses_current")
        assert not agent_scratch.provider_session_exists(
            "opencode", "build", "author", 3, "s02", "ses_current")

print("OpenCode isolated state boundary: OK")
