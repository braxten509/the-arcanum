"""Explicit registration of all new evidence-engine routes."""
from __future__ import annotations

from arcanum.app import AppServices

from .endpoints.assessment import AssessmentEndpoints
from .endpoints.mastery_labs import MasteryLabEndpoints
from .router import Router


def build_evidence_router(services: AppServices) -> Router:
    router = Router()
    assessments = AssessmentEndpoints(services)
    labs = MasteryLabEndpoints(services)
    router.post("/api/assessment", assessments.submit)
    router.get("/api/assessment/status", assessments.status)
    router.get("/api/mastery-lab", labs.get_assignment)
    router.post("/api/mastery-lab/workspace", labs.save_workspace)
    router.post("/api/mastery-lab/retry", labs.retry)
    router.post("/api/mastery/support", labs.support)
    router.get("/api/evidence/export", labs.evidence_export)
    return router
