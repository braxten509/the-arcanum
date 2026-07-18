"""Validated tome and save path policy."""
from __future__ import annotations

from dataclasses import dataclass
import os
import re

from arcanum.settings import Settings


@dataclass(frozen=True)
class TomePaths:
    settings: Settings

    @staticmethod
    def validate_id(tome_id: str) -> str:
        value = str(tome_id or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("bad tome id")
        return value

    def tome(self, tome_id: str) -> str:
        return os.path.join(self.settings.tomes_root, self.validate_id(tome_id))

    def manifest(self, tome_id: str) -> str:
        return os.path.join(self.tome(tome_id), "tome.toml")

    def save(self, tome_id: str) -> str:
        return os.path.join(self.tome(tome_id), "save")

    def state(self, tome_id: str) -> str:
        return os.path.join(self.save(tome_id), "state.json")

    def grades(self, tome_id: str) -> str:
        return os.path.join(self.save(tome_id), "grades")

    def plan(self, build_id: str) -> str:
        return os.path.join(self.settings.build_root,
                            f"{self.validate_id(build_id)}.plan.md")

    def snippet(self, runtime_name: str) -> str:
        safe = self.validate_id(runtime_name)
        return os.path.join(self.settings.cache_root, "snippet", safe)
