"""Typed request parsing around the stdlib HTTP handler."""
from __future__ import annotations

from dataclasses import dataclass
import json
import urllib.parse


@dataclass
class Request:
    handler: object
    method: str
    path: str
    query: dict[str, list[str]]
    tome_resolver: object | None = None
    _body: dict | None = None

    @classmethod
    def from_handler(cls, handler, method: str, tome_resolver=None) -> "Request":
        parsed = urllib.parse.urlparse(handler.path)
        return cls(handler, method, parsed.path, urllib.parse.parse_qs(parsed.query),
                   tome_resolver)

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
        if not callable(self.tome_resolver):
            raise RuntimeError("request has no configured tome resolver")
        body_hint = None
        if self.method.upper() == "POST" and not self.value("tome"):
            body_hint = self.json().get("tome")
        elif isinstance(self._body, dict):
            body_hint = self._body.get("tome")
        return self.tome_resolver(self.value("tome") or body_hint)
