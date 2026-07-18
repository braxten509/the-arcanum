"""Tome catalog and learner-safe payload HTTP translation."""
from __future__ import annotations

from ...response import Response, error, ok


class CatalogEndpoints:
    def __init__(self, services):
        self.services = services

    def list(self, _request) -> Response:
        return ok({"tomes": self.services.catalog.list()})

    def current(self, request) -> Response:
        tome_id = request.tome_id()
        try:
            return ok(self.services.catalog.assemble(tome_id))
        except Exception as exc:
            return error(f"failed to load tome {tome_id!r}: {exc}", 500)
