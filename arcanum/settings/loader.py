"""Side-effect-free settings loader."""
from __future__ import annotations

import os

from .models import Settings


def load_settings(root: str | None = None, *, port: int = 8777) -> Settings:
    root = os.path.realpath(root or os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    return Settings(root, os.path.join(root, "web"), os.path.join(root, "tomes"),
                    os.path.join(root, ".cache"), os.path.join(root, ".tome-build"), port)
