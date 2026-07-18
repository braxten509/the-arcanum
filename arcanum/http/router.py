"""Exact method/path route registry and centralized error translation."""
from __future__ import annotations

import json

from .request import Request
from .response import Response


class Router:
    def __init__(self) -> None:
        self._routes: dict[tuple[str, str], object] = {}

    def register(self, method: str, path: str, endpoint) -> None:
        key = (method.upper(), path)
        if key in self._routes:
            raise ValueError(f"duplicate HTTP route {key[0]} {key[1]}")
        self._routes[key] = endpoint

    def get(self, path: str, endpoint) -> None:
        self.register("GET", path, endpoint)

    def post(self, path: str, endpoint) -> None:
        self.register("POST", path, endpoint)

    def dispatch(self, handler, method: str) -> bool:
        request = Request.from_handler(handler, method)
        endpoint = self._routes.get((method.upper(), request.path))
        if not endpoint:
            return False
        try:
            response = endpoint(request)
            if not isinstance(response, Response):
                raise TypeError("HTTP endpoint did not return a Response")
        except (ValueError, json.JSONDecodeError) as exc:
            response = Response({"ok": False, "error": str(exc)}, 400)
        except Exception as exc:
            response = Response({"ok": False, "error": str(exc)[:2_000]}, 500)
        handler.send_json(response.body, response.status)
        return True

    def routes(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(self._routes))
