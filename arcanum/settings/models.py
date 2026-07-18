"""Path and server settings selected at the composition root."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    root: str
    web_root: str
    tomes_root: str
    cache_root: str
    build_root: str
    skins_root: str
    user_settings_path: str
    port: int
