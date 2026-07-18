"""Learner-workspace request validation and response translation."""
from __future__ import annotations

from ...response import Response, error, ok


class WorkspaceEndpoints:
    def __init__(self, services):
        self.services = services

    def get(self, request) -> Response:
        return ok(self.services.workspaces.snapshot_files(request.tome_id()))

    def save(self, request) -> Response:
        body = request.json()
        self.services.workspaces.write_files(request.tome_id(), body.get("files") or [])
        return ok()

    def check_directory(self, request) -> Response:
        return ok(self.services.workspaces.check_directory(request.value("path")))

    def starter_file(self, request) -> Response:
        try:
            return ok(self.services.workspaces.starter_file(
                request.tome_id(), request.value("path")))
        except RuntimeError as exc:
            return error(str(exc), 400)

    def scaffold(self, request) -> Response:
        request.json()
        return ok(self.services.workspaces.scaffold(request.tome_id()))

    def seed(self, request) -> Response:
        body = request.json()
        try:
            return ok(self.services.workspaces.seed_external(
                request.tome_id(), str(body.get("dir") or ""),
                str(body.get("mode") or "")))
        except ValueError as exc:
            return error(str(exc), 400)
        except RuntimeError as exc:
            return error(str(exc), 400)

    def open_path(self, request) -> Response:
        try:
            return ok(self.services.workspaces.open_directory(
                str(request.json().get("dir") or "")))
        except ValueError as exc:
            return error(str(exc), 400)
