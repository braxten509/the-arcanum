"""Legacy grade and Oracle request translation."""
from __future__ import annotations

from ...response import Response, ok


class LegacyGradingEndpoints:
    def __init__(self, services):
        self.services = services

    def submit(self, request) -> Response:
        body, tome_id = request.json(), request.tome_id()
        payload, status = self.services.legacy_grading.submit(tome_id, body)
        return Response(payload, status)

    def status(self, request) -> Response:
        return ok(self.services.legacy_grading.status(request.value("id")))

    def oracle(self, request) -> Response:
        body = request.json()
        return ok(self.services.legacy_grading.oracle(request.tome_id(), body))
