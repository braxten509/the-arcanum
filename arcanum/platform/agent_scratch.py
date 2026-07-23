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
