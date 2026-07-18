"""Compatibility application service for legacy Working grading and Oracle calls."""
from __future__ import annotations

import threading

from ..grader import ask_oracle, run_grader, start_grader_smoke


class LegacyGradingService:
    def __init__(self, jobs, catalog, workspaces, ai):
        self.jobs = jobs
        self.catalog = catalog
        self.workspaces = workspaces
        self.ai = ai

    def submit(self, tome_id: str, body: dict) -> tuple[dict, int]:
        if body.get("smoke") is True:
            return start_grader_smoke(tome_id, body, self.jobs, self.catalog)
        self.workspaces.write_files(tome_id, body.get("files") or [])
        section_id = str(body.get("sectionId") or "x")
        existing = self.jobs.find_running(
            kind="grade-working", section=section_id, tome=tome_id)
        if existing:
            return {"ok": True, "jobId": existing["id"], "existing": True}, 200
        job_id = self.jobs.create(
            "grade-working", section=section_id, tome=tome_id)["id"]
        threading.Thread(
            target=run_grader,
            args=(job_id, body, tome_id, self.jobs, self.catalog,
                  self.workspaces, self.ai), daemon=True).start()
        return {"ok": True, "jobId": job_id}, 200

    def status(self, job_id: str) -> dict:
        return self.jobs.status(job_id)

    def oracle(self, tome_id: str, body: dict) -> dict:
        runtime = self.catalog.manifest(tome_id).get("runtime") or {}
        language = body.get("language") or runtime.get("language") or "code"
        return ask_oracle(
            str(body.get("question") or ""), str(body.get("context") or ""),
            body.get("model"), language, body.get("kind") or "ollama", tome_id,
            ai=self.ai, catalog=self.catalog, key=str(body.get("key") or ""),
            effort=str(body.get("effort") or ""))
