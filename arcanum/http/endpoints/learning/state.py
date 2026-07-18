"""Learner-state HTTP translation."""
from __future__ import annotations

from ...response import Response, error, ok


class StateEndpoints:
    def __init__(self, services):
        self.services = services

    def get(self, request) -> Response:
        return ok(self.services.states.read(request.tome_id()))

    def save(self, request) -> Response:
        try:
            return ok(self.services.states.save(request.tome_id(), request.json()))
        except ValueError as exc:
            status = 409 if "erase progress" in str(exc) else 400
            return error(str(exc), status)

    def reset(self, request) -> Response:
        body = request.json()
        try:
            return ok(self.services.states.reset(
                request.tome_id(), str(body.get("confirm") or "")))
        except RuntimeError as exc:
            return error(str(exc), 409)
        except ValueError as exc:
            return error(str(exc), 400)
