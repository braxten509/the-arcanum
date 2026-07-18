#!/usr/bin/env python3
"""The composition root owns one exact, duplicate-free API route table."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from arcanum.app import create_app_services
from arcanum.http.composition import build_router
from arcanum.settings import load_settings


GET_ROUTES = {
    "/api/amend/current", "/api/amend/resumable", "/api/amend/status",
    "/api/assessment/status", "/api/buildtome/active",
    "/api/buildtome/resumable", "/api/buildtome/status", "/api/checkdir",
    "/api/evidence/export", "/api/grade/status", "/api/health",
    "/api/mastery-lab", "/api/models", "/api/starterfile", "/api/state",
    "/api/tome", "/api/tomes", "/api/workspace",
}
POST_ROUTES = {
    "/api/addpackage", "/api/amend", "/api/amend/cancel", "/api/amend/dismiss",
    "/api/assessment", "/api/buildtome", "/api/buildtome/cancel",
    "/api/buildtome/continue", "/api/buildtome/discard", "/api/buildtome/message",
    "/api/buildtome/pause", "/api/buildtome/reset", "/api/buildtome/resume",
    "/api/buildtome/runner", "/api/diagnostics", "/api/grade",
    "/api/mastery-lab/retry", "/api/mastery-lab/run", "/api/mastery-lab/workspace",
    "/api/mastery/support",
    "/api/openpath", "/api/oracle", "/api/run", "/api/runcancel",
    "/api/runsnippet", "/api/scaffold", "/api/seedworkspace", "/api/snippetdiag",
    "/api/state", "/api/state/reset", "/api/workspace",
}


with tempfile.TemporaryDirectory() as temp:
    services = create_app_services(load_settings(temp))
    routes = set(build_router(services).routes())
assert routes == ({("GET", path) for path in GET_ROUTES}
                  | {("POST", path) for path in POST_ROUTES})
assert len(routes) == len(GET_ROUTES) + len(POST_ROUTES)
print("explicit API route contract: OK")
