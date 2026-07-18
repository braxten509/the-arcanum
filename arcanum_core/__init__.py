"""Pure, stdlib-only contracts shared by Arcanum applications and tools."""

from .findings import Finding, Severity
from .result import Result

__all__ = ["Finding", "Result", "Severity"]
