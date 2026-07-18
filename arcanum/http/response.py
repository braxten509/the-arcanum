"""HTTP-independent response DTO."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Response:
    body: dict
    status: int = 200


def ok(body: dict | None = None, status: int = 200) -> Response:
    return Response({"ok": True} if body is None else body, status)


def error(message: str, status: int = 400) -> Response:
    return Response({"ok": False, "error": message}, status)
