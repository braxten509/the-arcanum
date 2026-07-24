"""Compatibility application service for legacy Working grading and Oracle calls."""
from __future__ import annotations

import threading
import re

from ..grader import (ask_oracle, collect_grading_disclosure, run_grader,
                      start_grader_smoke, verification_specs)


class LegacyGradingService:
    def __init__(self, jobs, catalog, workspaces, ai):
        self.jobs = jobs
        self.catalog = catalog
        self.workspaces = workspaces
        self.ai = ai

    def _authoritative_payload(self, tome_id: str, body: dict) -> dict:
        payload = dict(body)
        course = self.catalog.assemble(tome_id)
        section_id = str(body.get("sectionId") or "")
        section = next((
            item for item in (course.get("sections") or [])
            if str(item.get("id") or "") == section_id
        ), None)
        if not section:
            raise ValueError(f"unknown grading section {section_id!r}")
        freestyle = section.get("freestyle") or {}
        narrative = course.get("narrative") or {}
        runtime_manifest = course.get("runtime") or {}
        payload.update({
            "sectionId": section_id,
            "sectionTitle": f"{section.get('codename', '')} — {section.get('title', '')}",
            "brief": re.sub(r"<[^>]+>", "", str(freestyle.get("brief") or "")),
            "rubric": freestyle.get("rubric") or [],
            "verification": freestyle.get("verification") or [],
            "language": runtime_manifest.get("language") or runtime_manifest.get("name") or "code",
            "persona": narrative.get("graderPersona") or "PATCH",
            "studentTerm": narrative.get("studentTerm") or "recruit",
            "gradeScale": narrative.get("gradeScale") or "S|A|B|C|D|F",
        })
        # Bind the effective checks—including the implicit build check—to the
        # disclosure token before the learner grants remote-grading consent.
        payload["verification"] = verification_specs(
            payload, self.catalog.runtime(tome_id))
        return payload

    def submit(self, tome_id: str, body: dict) -> tuple[dict, int]:
        if body.get("smoke") is True:
            return start_grader_smoke(tome_id, body, self.jobs, self.catalog)
        self.workspaces.write_files(tome_id, body.get("files") or [])
        body = self._authoritative_payload(tome_id, body)
        disclosure = collect_grading_disclosure(
            body, tome_id, self.catalog, self.workspaces)
        if not disclosure["complete"]:
            return {
                "ok": False,
                "error": "grading scope contains unsafe or unreadable paths; preview for details",
                "disclosure": disclosure,
            }, 409
        if (disclosure["remote"]
                and body.get("consentToken") != disclosure["consentToken"]):
            return {
                "ok": False,
                "error": "explicit consent for these exact files and grader is required",
                "disclosure": disclosure,
            }, 409
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

    def preview(self, tome_id: str, body: dict) -> dict:
        body = self._authoritative_payload(tome_id, body)
        return collect_grading_disclosure(
            body, tome_id, self.catalog, self.workspaces)

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
