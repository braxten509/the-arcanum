"""Reader marginalia HTTP translation."""
from __future__ import annotations

from ...response import Response, error, ok


class NotesEndpoints:
    def __init__(self, services):
        self.services = services

    def list(self, request) -> Response:
        return ok(self.services.notes.list(request.tome_id()))

    def add(self, request) -> Response:
        body = request.json()
        try:
            return ok(self.services.notes.add(
                request.tome_id(), str(body.get("text") or ""),
                str(body.get("where") or ""), str(body.get("quote") or "")))
        except ValueError as exc:
            return error(str(exc), 400)

    def remove(self, request) -> Response:
        body = request.json()
        if not self.services.notes.remove(
                request.tome_id(), str(body.get("id") or "")):
            return error("no note in this tome's margin has that id", 404)
        return ok()
