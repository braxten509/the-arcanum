"""Forge HTTP translation."""
from __future__ import annotations

from ...response import Response, ok


class ForgeEndpoints:
    def __init__(self, services):
        self.forge = services.forge

    @staticmethod
    def _response(value) -> Response:
        body, status = value
        return Response(body, status)

    def start(self, request) -> Response:
        return self._response(self.forge.start(request.json()))

    def resume(self, request) -> Response:
        return self._response(self.forge.resume(request.json()))

    def reset(self, request) -> Response:
        return self._response(self.forge.reset(request.tome_id(), request.json()))

    def discard(self, request) -> Response:
        return self._response(self.forge.discard(request.json()))

    def cancel(self, request) -> Response:
        return self._response(self.forge.cancel(request.json()))

    def pause(self, request) -> Response:
        return self._response(self.forge.control("pause", request.json()))

    def message(self, request) -> Response:
        return self._response(self.forge.control("message", request.json()))

    def resume_author(self, request) -> Response:
        return self._response(self.forge.control("resume", request.json()))

    def runner(self, request) -> Response:
        return self._response(self.forge.runner(request.json()))

    def active(self, _request) -> Response:
        return ok(self.forge.active())

    def resumable(self, _request) -> Response:
        return ok(self.forge.resumable())

    def status(self, request) -> Response:
        return ok(self.forge.status(request.value("id")))
