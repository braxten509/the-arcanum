"""Architecture policy and violation data contracts."""
from __future__ import annotations

from dataclasses import dataclass
import os
import tomllib


@dataclass(frozen=True, order=True)
class Violation:
    code: str
    path: str
    message: str

    def render(self) -> str:
        return f"ERROR {self.path}: [{self.code}] {self.message}"


def load_policy(path: str) -> dict:
    with open(path, "rb") as handle:
        policy = tomllib.load(handle)
    if policy.get("version") != 1:
        raise ValueError("architecture policy version must be 1")
    for section in ("python", "javascript", "registries", "facades"):
        if not isinstance(policy.get(section), dict):
            raise ValueError(f"architecture policy is missing [{section}]")
    policy["_path"] = os.path.realpath(path)
    return policy
