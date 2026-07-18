"""Pure path-shape checks; filesystem resolution belongs to adapters."""
from __future__ import annotations

import pathlib


def safe_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("path must be a non-empty string")
    normalized = value.replace("\\", "/")
    path = pathlib.PurePosixPath(normalized)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"unsafe relative path {value!r}")
    return path.as_posix()
