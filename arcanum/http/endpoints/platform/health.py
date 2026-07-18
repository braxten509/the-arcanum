"""Health and model-catalog HTTP translation."""
from __future__ import annotations

import os

from runtimes import get as get_runtime, names as runtime_names

from arcanum.ai.catalog import model_census
from arcanum.config import CLAUDE_BIN

from ...response import Response, ok


class HealthEndpoints:
    def __init__(self, services):
        self.services = services

    def health(self, _request) -> Response:
        available = {name: get_runtime(name).available() for name in runtime_names()}
        for tome in self.services.catalog.list():
            if tome.get("runtime") not in available:
                try:
                    available[tome["runtime"]] = self.services.catalog.runtime(
                        tome["id"]).available()
                except Exception:
                    available[tome["runtime"]] = False
        return ok({"claude": os.access(CLAUDE_BIN, os.X_OK), "runtimes": available})

    def models(self, _request) -> Response:
        return ok(model_census())
