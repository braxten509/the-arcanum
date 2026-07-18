"""Read-model assembly for one live or durable Forge build."""
from __future__ import annotations

import os

from arcanum.forge import forge_name, list_active_builds
from arcanum.forge.build_state import (build_result_status, cancelled_build_status,
                                       load_author_session, load_build_progress,
                                       load_section_progress)
from .durable_status import load_conversation, public_course_status
from ..adapters.status_log import load_status_lines


class ForgeStatusService:
    def __init__(self, settings, jobs, catalog):
        self.settings, self.jobs, self.catalog = settings, jobs, catalog

    def get(self, build_id: str) -> dict:
        job = self.jobs.status(build_id)
        live_lines = list(job.get("statusLog") or [])
        if job.get("kind") == "build":
            keys = ("status", "kind", "tome", "slug", "phase", "phaseTitle",
                    "totalPhases", "startedAt", "error", "phaseStartedAt",
                    "activityStartedAt", "runner", "sections", "interactionState",
                    "sessionAuthor", "sessionReviewer")
            output = {key: job[key] for key in keys if key in job}
            output["name"] = forge_name(job.get("tome"), self.catalog)
        else:
            output = next((row for row in list_active_builds(self.jobs, self.catalog)
                           if row.get("external") and row.get("id") == build_id), None)
        if output is None:
            output = (build_result_status(build_id) or cancelled_build_status(build_id)
                      or {"status": "unknown"})
        stable = output.get("slug") or build_id
        combined = []
        for line in [*load_status_lines(stable, build_dir=self.settings.build_root),
                     *live_lines]:
            if line not in combined:
                combined.append(line)
        output["logtail"] = "\n".join(combined[-500:])
        try:
            with open(self.catalog.paths.plan(stable), encoding="utf-8") as handle:
                current_tome = self.catalog.resolve_working_id(stable, handle.read())
            output["tome"] = current_tome
            output["name"] = forge_name(current_tome, self.catalog) or output.get("name")
        except OSError:
            pass
        progress = (load_build_progress(stable)
                    or load_build_progress(output.get("tome")))
        if progress:
            output.update(progress)
        session = (load_author_session(stable)
                   or load_author_session(output.get("tome")))
        if session:
            reported, pending = session.get("state"), output.get("interactionState")
            target = {"pausing": "paused", "resuming": "running"}.get(pending)
            if not target or reported == target:
                output["interactionState"] = reported
            if reported not in ("starting", "running", "resuming"):
                output["activityStartedAt"] = 0
            elif not output.get("activityStartedAt"):
                output["activityStartedAt"] = float(session.get("updatedAt") or 0)
            output["sessionId"] = session.get("sessionId")
            output["sessionError"] = str(session.get("error") or "")
            output["sessionAuthor"] = {
                "kind": session.get("kind"),
                "model": session.get("actualModel") or session.get("model"),
                "requestedModel": session.get("model"),
                "actualModel": session.get("actualModel"),
                "effort": session.get("effort"),
            }
            output["sessionRole"] = str(session.get("role") or "author")
        output["conversation"] = load_conversation(
            self.settings.build_root, stable, 120)
        try:
            output["courseControl"] = public_course_status(
                self.settings.build_root, stable)
        except (OSError, ValueError) as exc:
            output["courseControlError"] = str(exc)[-500:]
        if output.get("status") == "running" and int(output.get("phase") or 0) == 3:
            section = (load_section_progress(output.get("tome"))
                       or load_section_progress(output.get("slug"))
                       or load_section_progress(build_id))
            if section:
                output["sectionProgress"] = section
        return output
