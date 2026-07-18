"""A small typed result primitive for application boundaries."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Result(Generic[T]):
    value: T | None = None
    error: str = ""
    code: str = ""

    @property
    def ok(self) -> bool:
        return not self.error

    @classmethod
    def success(cls, value: T) -> "Result[T]":
        return cls(value=value)

    @classmethod
    def failure(cls, error: str, code: str = "error") -> "Result[T]":
        return cls(error=error, code=code)
