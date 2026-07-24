"""Private, disposable scratch directories for one authoring build."""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import time


ROOT = "/tmp/arcanum"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
_STATE_LAYOUT_VERSION = 2


def path(build_id: str) -> str:
    value = str(build_id or "")
    if not _ID.fullmatch(value):
        raise ValueError(f"unsafe scratch build id {build_id!r}")
    return os.path.join(ROOT, value)


def prepare(build_id: str) -> str:
    target = path(build_id)
    os.makedirs(target, mode=0o700, exist_ok=True)
    os.chmod(target, 0o700)
    return target


def _component(value: str, label: str) -> str:
    value = str(value or "")
    if not _ID.fullmatch(value):
        raise ValueError(f"unsafe scratch {label} {value!r}")
    return value


def _unit_root(build_id: str, role: str, phase: int, section: str = "") -> str:
    parts = [path(build_id), _component(role, "role"), f"phase-{int(phase)}"]
    if section:
        parts.append("section-" + _component(section, "section"))
    return os.path.join(*parts)


def unit_temp(build_id: str, role: str, phase: int, section: str = "") -> str:
    """Return private ordinary temporary space for exactly one authoring unit."""
    prepare(build_id)
    target = os.path.join(_unit_root(build_id, role, phase, section), "tmp")
    os.makedirs(target, mode=0o700, exist_ok=True)
    os.chmod(target, 0o700)
    return target


def clear(*build_ids: str) -> None:
    """Remove old scratch contents while retaining an empty private directory."""
    for build_id in dict.fromkeys(str(value) for value in build_ids if value):
        target = path(build_id)
        if os.path.isdir(target):
            shutil.rmtree(target)
        prepare(build_id)


def remove(*build_ids: str) -> None:
    """Remove a permanently abandoned build's scratch directory."""
    for build_id in dict.fromkeys(str(value) for value in build_ids if value):
        target = path(build_id)
        if os.path.isdir(target):
            shutil.rmtree(target)


def provider_state_mounts(provider: str, build_id: str, role: str, phase: int,
                          section: str = "") -> list[tuple[str, str]]:
    """Return every writable provider-state overlay for one isolated unit.

    The bootstrap lists are deliberately narrow. In particular, OpenCode's host database,
    logs, tool outputs, transcripts, and session diffs never cross this boundary. Its new
    per-unit database is created inside scratch and remains available only for same-unit
    continuation.
    """
    provider = str(provider)
    layouts = {
        "codex": ((".codex", ("auth.json", "config.toml")),),
        "claude": ((".claude", (
            ".credentials.json", "credentials.json", "settings.json")),),
        "opencode": (
            (".config/opencode", (
                ".gitignore", "auth.json", "config.json", "opencode.json",
                "opencode.jsonc")),
            (".cache/opencode", ()),
            (".local/share/opencode", ("auth.json", "account.json")),
            (".local/state/opencode", ()),
        ),
        "antigravity": ((".gemini", (
            "google_accounts.json", "installation_id", "oauth_creds.json",
            "settings.json",
        )),),
    }
    if provider not in layouts:
        raise ValueError(f"provider {provider!r} has no isolated state layout")
    prepare(build_id)
    unit = os.path.join(_unit_root(build_id, role, phase, section),
                        "provider-state", provider)
    marker = os.path.join(unit, f".arcanum-state-v{_STATE_LAYOUT_VERSION}")
    initialize = not os.path.isfile(marker)
    mounts = []
    home = os.path.expanduser("~")
    for relative, bootstrap in layouts[provider]:
        source = os.path.join(unit, relative)
        os.makedirs(source, mode=0o700, exist_ok=True)
        os.chmod(source, 0o700)
        if initialize:
            host = os.path.join(home, relative)
            for filename in bootstrap:
                original = os.path.join(host, filename)
                target = os.path.join(source, filename)
                if os.path.isfile(original):
                    shutil.copy2(original, target)
        mounts.append((source, os.path.join(home, relative)))
    if provider == "claude":
        # Claude Code 2.1.x keeps mutable installation/account metadata in the
        # sibling ~/.claude.json file. The directory-only overlay made that file
        # disappear, so an expired OAuth session produced a misleading restore
        # warning before the harness could explain that it lacked headless auth.
        #
        # Do not copy the host file wholesale: it contains unrelated project and
        # usage history. A minimal unit-local file satisfies Claude's configuration
        # lifecycle while session history and persistent memory remain isolated.
        source = os.path.join(unit, ".claude.json")
        if initialize or not os.path.isfile(source):
            first_start = int(time.time() * 1000)
            host_file = os.path.join(home, ".claude.json")
            try:
                with open(host_file, encoding="utf-8") as handle:
                    host_state = json.load(handle)
                if isinstance(host_state.get("firstStartTime"), (int, float)):
                    first_start = host_state["firstStartTime"]
            except (OSError, ValueError, TypeError):
                pass
            with open(source, "w", encoding="utf-8") as handle:
                json.dump({
                    "firstStartTime": first_start,
                    "hasCompletedOnboarding": True,
                }, handle, separators=(",", ":"))
                handle.write("\n")
            os.chmod(source, 0o600)
        mounts.append((source, os.path.join(home, ".claude.json")))
        # Share only Claude's dedicated credential file so a refresh performed by
        # either the terminal or a harness unit is immediately visible to the other.
        # The surrounding ~/.claude directory remains unit-local, keeping projects,
        # transcripts, plugins, sessions, and persistent memory outside the boundary.
        host_credentials = os.path.join(home, ".claude", ".credentials.json")
        if os.path.isfile(host_credentials):
            mounts.append((host_credentials, host_credentials))
    if initialize:
        os.makedirs(unit, mode=0o700, exist_ok=True)
        with open(marker, "w", encoding="utf-8") as handle:
            handle.write("isolated provider state; no host session history\n")
    return mounts


def provider_state(provider: str, build_id: str, role: str, phase: int,
                   section: str = "") -> tuple[str, str]:
    """Compatibility wrapper returning the provider's primary configuration mount."""
    return provider_state_mounts(provider, build_id, role, phase, section)[0]


def provider_session_exists(provider: str, build_id: str, role: str, phase: int,
                            section: str, session_id: str) -> bool:
    """Return whether this exact isolated unit can resume a provider session."""
    if provider != "opencode" or not str(session_id or "").strip():
        return False
    try:
        unit = os.path.join(_unit_root(build_id, role, phase, section),
                            "provider-state", provider)
    except (TypeError, ValueError):
        return False
    marker = os.path.join(unit, f".arcanum-state-v{_STATE_LAYOUT_VERSION}")
    database = os.path.join(unit, ".local", "share", "opencode", "opencode.db")
    if not os.path.isfile(marker) or not os.path.isfile(database):
        return False
    try:
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
            return connection.execute(
                "SELECT 1 FROM session WHERE id=? LIMIT 1", (str(session_id),)
            ).fetchone() is not None
    except sqlite3.Error:
        return False
