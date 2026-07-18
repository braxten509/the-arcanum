"""Server-side adapter for the interactive authoring lifecycle."""
from __future__ import annotations

import os
import signal
from types import SimpleNamespace

from arcanum.forge import (_resume_phase, external_build_process, forge_name,
                           list_active_builds, list_workings)
from arcanum.forge.build_state import record_cancelled_build
from arcanum.authoring.adapters import forge_lifecycle as builds
from ..adapters.phase_reset import PhaseResetService
from ..read_models.forge_status import ForgeStatusService


class _Capture:
    def send_json(self, body, status=200):
        return body, status


class ForgeService:
    def __init__(self, settings, jobs, processes, catalog):
        self.settings, self.jobs = settings, jobs
        self.processes, self.catalog = processes, catalog
        self.phase_reset = PhaseResetService(settings, catalog)
        self.context = SimpleNamespace(settings=settings, jobs=jobs, processes=processes,
                                       catalog=catalog, phase_reset=self.phase_reset)
        self.status_reader = ForgeStatusService(settings, jobs, catalog)

    def _call(self, function, *args) -> tuple[dict, int]:
        return function(_Capture(), *args)

    def start(self, body: dict) -> tuple[dict, int]:
        return self._call(builds.start_build, body, self.context)

    def resume(self, body: dict) -> tuple[dict, int]:
        return self._call(builds.resume_build, body, self.context)

    def reset(self, tome_id: str, body: dict) -> tuple[dict, int]:
        return self._call(builds.reset_build, body, tome_id, self.context)

    def discard(self, body: dict) -> tuple[dict, int]:
        return self._call(builds.discard_build, body, self.context)

    def control(self, action: str, body: dict) -> tuple[dict, int]:
        return self._call(builds.control_author, body, action, self.context)

    def runner(self, body: dict) -> tuple[dict, int]:
        return self._call(builds.answer_runner_pause, body)

    def cancel(self, body: dict) -> tuple[dict, int]:
        build_id = str(body.get("id") or "")
        job = self.jobs.status(build_id)
        is_build = job.get("kind") == "build"
        running = is_build and job.get("status") == "running"
        pid = job.get("pid") if is_build else None
        slug = (job.get("slug") or job.get("tome")) if is_build else build_id
        tome = job.get("tome") if is_build else None
        phase = job.get("phase", 0) if is_build else 0
        if running:
            self.jobs.cancel(build_id)
            self.processes.pop(build_id)
        if not is_build:
            process = external_build_process(build_id)
            if not process:
                return {"ok": False, "error": "no such build"}, 404
            pid, running = process["pid"], True
            try:
                with open(self.catalog.paths.plan(build_id), encoding="utf-8") as handle:
                    text = handle.read()
                tome = self.catalog.resolve_working_id(build_id, text)
            except OSError:
                tome = build_id
            phase = _resume_phase(build_id, tome, self.catalog)
        if running:
            record_cancelled_build(
                slug, tome, phase, forge_name(tome, self.catalog) or tome)
        if running and pid:
            try:
                if hasattr(os, "killpg"):
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                else:
                    os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        status = "cancelled" if running else job.get("status")
        return {"ok": True, "status": status}, 200

    def active(self) -> dict:
        return {"jobs": list_active_builds(self.jobs, self.catalog)}

    def resumable(self) -> dict:
        return {"workings": list_workings(self.jobs, self.catalog)}

    def status(self, build_id: str) -> dict:
        return self.status_reader.get(build_id)
