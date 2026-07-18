"""Explicit registration of the complete browser-facing HTTP API."""
from __future__ import annotations

from arcanum.app import AppServices

from .endpoints.authoring.binder import BinderEndpoints
from .endpoints.authoring.forge import ForgeEndpoints
from .endpoints.authoring.legacy_grading import LegacyGradingEndpoints
from .endpoints.learning.assessment import AssessmentEndpoints
from .endpoints.learning.mastery_labs import MasteryLabEndpoints
from .endpoints.learning.state import StateEndpoints
from .endpoints.platform.catalog import CatalogEndpoints
from .endpoints.platform.execution import ExecutionEndpoints
from .endpoints.platform.health import HealthEndpoints
from .endpoints.platform.workspaces import WorkspaceEndpoints
from .router import Router


def build_router(services: AppServices) -> Router:
    router = Router(services.catalog.resolve)
    state = StateEndpoints(services)
    catalog = CatalogEndpoints(services)
    workspaces = WorkspaceEndpoints(services)
    execution = ExecutionEndpoints(services)
    legacy_grading = LegacyGradingEndpoints(services)
    binder = BinderEndpoints(services)
    forge = ForgeEndpoints(services)
    assessments = AssessmentEndpoints(services)
    labs = MasteryLabEndpoints(services)

    router.get("/api/state", state.get)
    router.get("/api/tomes", catalog.list)
    router.get("/api/tome", catalog.current)
    router.get("/api/workspace", workspaces.get)
    router.get("/api/checkdir", workspaces.check_directory)
    router.get("/api/starterfile", workspaces.starter_file)
    router.get("/api/grade/status", legacy_grading.status)
    router.get("/api/amend/status", binder.status)
    router.get("/api/amend/current", binder.current)
    router.get("/api/amend/resumable", binder.resumable)
    router.get("/api/buildtome/status", forge.status)
    router.get("/api/buildtome/active", forge.active)
    router.get("/api/buildtome/resumable", forge.resumable)

    health = HealthEndpoints(services)
    router.get("/api/health", health.health)
    router.get("/api/models", health.models)

    router.post("/api/assessment", assessments.submit)
    router.get("/api/assessment/status", assessments.status)
    router.get("/api/mastery-lab", labs.get_assignment)
    router.post("/api/mastery-lab/workspace", labs.save_workspace)
    router.post("/api/mastery-lab/retry", labs.retry)
    router.post("/api/mastery/support", labs.support)
    router.get("/api/evidence/export", labs.evidence_export)

    router.post("/api/state", state.save)
    router.post("/api/state/reset", state.reset)
    router.post("/api/workspace", workspaces.save)
    router.post("/api/scaffold", workspaces.scaffold)
    router.post("/api/seedworkspace", workspaces.seed)
    router.post("/api/openpath", workspaces.open_path)
    router.post("/api/oracle", legacy_grading.oracle)
    router.post("/api/runsnippet", execution.run_snippet)
    router.post("/api/snippetdiag", execution.snippet_diagnostics)
    router.post("/api/run", execution.run_project)
    router.post("/api/runcancel", execution.cancel)
    router.post("/api/diagnostics", execution.diagnostics)
    router.post("/api/addpackage", execution.add_package)
    router.post("/api/grade", legacy_grading.submit)
    router.post("/api/amend", binder.start)
    router.post("/api/amend/cancel", binder.cancel)
    router.post("/api/amend/dismiss", binder.dismiss)
    router.post("/api/buildtome", forge.start)
    router.post("/api/buildtome/runner", forge.runner)
    router.post("/api/buildtome/pause", forge.pause)
    router.post("/api/buildtome/message", forge.message)
    router.post("/api/buildtome/continue", forge.resume_author)
    router.post("/api/buildtome/cancel", forge.cancel)
    router.post("/api/buildtome/resume", forge.resume)
    router.post("/api/buildtome/reset", forge.reset)
    router.post("/api/buildtome/discard", forge.discard)
    return router
