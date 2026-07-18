"""Reader-wide settings persistence adapter."""
from __future__ import annotations

import json
import os
import tomllib

from runtimes.common import atomic_write


GLOBAL_STATE_KEYS = ("audio", "pen", "ai")
HEADER = ("# global-configs/settings.toml — reader-wide audio, pen, AI, and notification "
          "settings.\n")


def _value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_value(item) for item in value) + "]"
    return json.dumps(str(value))


def _dump(data: dict, prefix: str = "") -> str:
    output = "".join(f"{key} = {_value(value)}\n" for key, value in data.items()
                     if not isinstance(value, dict))
    for key, value in data.items():
        if isinstance(value, dict):
            output += f"\n[{prefix}{key}]\n" + _dump(value, f"{prefix}{key}.")
    return output


class UserSettingsStore:
    def __init__(self, path: str):
        self.path = path

    def read(self) -> dict:
        try:
            with open(self.path, "rb") as handle:
                value = tomllib.load(handle)
            return value if isinstance(value, dict) else {}
        except (OSError, tomllib.TOMLDecodeError):
            return {}

    def write(self, value: dict) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        atomic_write(self.path, HEADER + _dump(value))

    def merge(self, values: dict) -> dict:
        current = self.read()
        current.update(values)
        self.write(current)
        return current
