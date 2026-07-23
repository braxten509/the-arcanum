"""Private, disposable scratch directories for one authoring build."""
from __future__ import annotations

import os
import re
import shutil


ROOT = "/tmp/arcanum"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")


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


def provider_state(provider: str, build_id: str, role: str, phase: int,
                   section: str = "") -> tuple[str, str]:
    """Return an isolated provider-state source and its conventional home target.

    Only credential/configuration files are bootstrapped from the host. Session records,
    caches, and transcripts are never copied into a newly assigned unit.
    """
    provider = str(provider)
    layouts = {
        "codex": (".codex", ("auth.json", "config.toml")),
        "claude": (".claude", (".credentials.json", "credentials.json", "settings.json")),
        "opencode": (".config/opencode", ("auth.json", "config.json")),
    }
    if provider not in layouts:
        raise ValueError(f"provider {provider!r} has no isolated state layout")
    name, bootstrap = layouts[provider]
    unit = os.path.join(prepare(build_id), "provider-state", str(role),
                        f"phase-{int(phase)}", *( (f"section-{section}",) if section else () ),
                        provider)
    source = os.path.join(unit, name)
    if not os.path.isdir(source):
        os.makedirs(source, mode=0o700, exist_ok=True)
        host = os.path.join(os.path.expanduser("~"), name)
        for filename in bootstrap:
            original = os.path.join(host, filename)
            target = os.path.join(source, filename)
            if os.path.isfile(original):
                shutil.copy2(original, target)
    return source, os.path.join(os.path.expanduser("~"), name)
