"""Immutable validation findings shared by authoring and runtime gates."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, order=True)
class Finding:
    severity: Severity
    code: str
    location: str
    message: str
    phase: int = 0
    advisory: bool = False

    def to_dict(self) -> dict:
        value = asdict(self)
        value["severity"] = self.severity.value
        return value
