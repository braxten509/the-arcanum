"""Runtime execution HTTP translation."""
from __future__ import annotations

from ...response import Response, ok


class ExecutionEndpoints:
    def __init__(self, services):
        self.services = services

    def run_snippet(self, request) -> Response:
        body = request.json()
        return ok(self.services.execution.run_snippet(
            request.tome_id(), str(body.get("code") or ""),
            str(body.get("stdin") or "")))

    def snippet_diagnostics(self, request) -> Response:
        body = request.json()
        return ok(self.services.execution.snippet_diagnostics(
            request.tome_id(), str(body.get("code") or "")))

    def run_project(self, request) -> Response:
        body = request.json()
        return ok(self.services.execution.run_project(
            request.tome_id(), body.get("files") or [],
            str(body.get("stdin") or "")))

    def cancel(self, _request) -> Response:
        return ok(self.services.execution.cancel_current())

    def diagnostics(self, request) -> Response:
        body = request.json()
        return ok(self.services.execution.diagnostics(
            request.tome_id(), body.get("files") or []))

    def add_package(self, request) -> Response:
        body = request.json()
        return ok(self.services.execution.add_package(
            request.tome_id(), str(body.get("package") or "")))
