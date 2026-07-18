"""Assessment request validation and background-job translation."""
from __future__ import annotations

from arcanum.app import AppServices

from ...response import Response, ok

ALLOWED_SUBMISSION_KEYS = frozenset({"sectionId", "nodeId", "rationale", "tome"})


class AssessmentEndpoints:
    def __init__(self, services: AppServices):
        self.services = services

    def submit(self, request) -> Response:
        body = request.json()
        extra = set(body) - ALLOWED_SUBMISSION_KEYS
        if extra:
            raise ValueError("assessment accepts only server-owned node identifiers and rationale; "
                             "remove: " + ", ".join(sorted(extra)))
        tome_id = request.tome_id()
        section_id, node_id = str(body.get("sectionId") or ""), str(body.get("nodeId") or "")
        if bool(section_id) == bool(node_id):
            raise ValueError("submit exactly one sectionId or mastery-lab nodeId")
        resolved_node = node_id or f"{section_id}.working"
        existing = self.services.jobs.find_running(
            kind="learner-assessment", tome=tome_id, node=resolved_node)
        if existing:
            return ok({"ok": True, "jobId": existing["id"], "existing": True})
        rationale = str(body.get("rationale") or "")[:20_000]

        def assess(_job_id: str) -> dict:
            app = self.services.assessment(tome_id)
            learning = self.services.learning(tome_id)
            return (app.assess_lab(node_id, rationale, learning) if node_id
                    else app.assess_working(section_id, rationale, learning))

        job = self.services.jobs.start(
            "learner-assessment", assess, tome=tome_id, node=resolved_node)
        return ok({"ok": True, "jobId": job["id"]})

    def status(self, request) -> Response:
        return ok(self.services.jobs.status(request.value("id")))
