"""Typed request parsing around the stdlib HTTP handler."""
from __future__ import annotations

from dataclasses import dataclass
import json
import urllib.parse

from arcanum.tomes import resolve_tome


@dataclass
class Request:
    handler: object
    method: str
    path: str
    query: dict[str, list[str]]
    _body: dict | None = None

    @classmethod
    def from_handler(cls, handler, method: str) -> "Request":
        parsed = urllib.parse.urlparse(handler.path)
        return cls(handler, method, parsed.path, urllib.parse.parse_qs(parsed.query))

    def json(self) -> dict:
        if self._body is None:
            length = int(self.handler.headers.get("Content-Length", 0))
            value = json.loads(self.handler.rfile.read(length) or b"{}")
            if not isinstance(value, dict):
                raise ValueError("JSON body must be an object")
            self._body = value
        return self._body

    def value(self, name: str, default: str = "") -> str:
        return str((self.query.get(name) or [default])[0])

    def tome_id(self) -> str:
        body_hint = self._body.get("tome") if isinstance(self._body, dict) else None
        return resolve_tome(self.value("tome") or body_hint)
