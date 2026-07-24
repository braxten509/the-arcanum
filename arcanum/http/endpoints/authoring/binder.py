"""Binder HTTP translation."""
from __future__ import annotations

from ...response import Response, ok


class BinderEndpoints:
    def __init__(self, services):
        self.services = services

    def start(self, request) -> Response:
        payload, status = self.services.binder.start(request.tome_id(), request.json())
        return Response(payload, status)

    def cancel(self, request) -> Response:
        payload, status = self.services.binder.cancel(str(request.json().get("id") or ""))
        return Response(payload, status)

    def dismiss(self, request) -> Response:
        request.json()
        payload, status = self.services.binder.dismiss(request.tome_id())
        return Response(payload, status)

    def status(self, request) -> Response:
        return ok(self.services.binder.status(request.value("id")))

    def current(self, request) -> Response:
        return ok(self.services.binder.current(request.tome_id()))

    def resumable(self, request) -> Response:
        return ok(self.services.binder.resumable(request.tome_id()))

    def reviews(self, request) -> Response:
        return ok(self.services.binder.reviews(
            request.tome_id(), str(request.value("path") or "")))
