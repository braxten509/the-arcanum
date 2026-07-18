"""Binder amendment job application service."""
from __future__ import annotations

import os
import signal
import threading
import time

from arcanum.config import CLI_EFFORTS

from ..amender import clear_amend_state, load_amend_state, run_amender, save_amend_state


class BinderService:
    def __init__(self, jobs, processes, ai):
        self.jobs = jobs
        self.processes = processes
        self.ai = ai

    def start(self, tome_id: str, body: dict) -> tuple[dict, int]:
        request_text = str(body.get("request") or "").strip()
        iterate, review = bool(body.get("iterate")), bool(body.get("review"))
        if not request_text and not iterate and not review:
            return {"ok": False, "error": "an amendment request is required"}, 400
        kind = str(body.get("kind") or "claude-cli")
        model, effort = str(body.get("model") or ""), str(body.get("effort") or "")
        broad, reset_ok = bool(body.get("broad")) or iterate, bool(body.get("resetOk"))
        review_path = str(body.get("reviewPath") or "")[:200]
        if effort and effort not in CLI_EFFORTS.get(kind, ()):
            effort = ""
        existing = self.jobs.find_running(kind="binder-amend", tome=tome_id)
        if existing:
            return {"ok": True, "jobId": existing["id"], "existing": True}, 200
        started = time.time()
        job_id = self.jobs.create(
            "binder-amend", tome=tome_id, request=request_text[:300], broad=broad,
            review=review, log=[], startedAt=started)["id"]
        save_amend_state({
            "id": job_id, "tome": tome_id, "request": request_text[:4000],
            "broad": broad, "iterate": iterate, "resetOk": reset_ok, "review": review,
            "kind": kind, "model": model, "effort": effort, "startedAt": started,
            "status": "running",
        })
        threading.Thread(
            target=run_amender,
            args=(job_id, tome_id, request_text, kind, model, effort, broad, iterate,
                  reset_ok, review, review_path, self.jobs, self.processes, self.ai),
            daemon=True).start()
        return {"ok": True, "jobId": job_id}, 200

    def cancel(self, job_id: str) -> tuple[dict, int]:
        job, process = self.jobs.status(job_id), self.processes.get(job_id)
        if not (job.get("kind") == "binder-amend" and job.get("status") == "running"):
            return {"ok": False, "error": "no running amendment with that id"}, 404
        self.jobs.cancel(job_id)
        if process:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                process.kill()
        return {"ok": True}, 200

    def dismiss(self, tome_id: str) -> tuple[dict, int]:
        state = load_amend_state(tome_id)
        live = self.jobs.status(state.get("id")) if state else None
        if live and live.get("status") == "running":
            return {"ok": False, "error": "that amendment is still running"}, 409
        clear_amend_state(tome_id)
        return {"ok": True}, 200

    def status(self, job_id: str) -> dict:
        job = self.jobs.status(job_id)
        if job.get("kind") != "binder-amend":
            return {"status": "unknown"}
        output = dict(job)
        if "log" in output:
            output["logtail"] = "\n".join(output.pop("log")[-200:])
        return output

    def current(self, tome_id: str) -> dict:
        for job in self.jobs.all(kind="binder-amend", status="running"):
            if job.get("tome") == tome_id:
                return {"jobId": job["id"], "request": job.get("request", ""),
                        "broad": bool(job.get("broad")),
                        "review": bool(job.get("review"))}
        return {}

    def resumable(self, tome_id: str) -> dict:
        state = load_amend_state(tome_id)
        if state and self.jobs.status(state.get("id")).get("status") == "running":
            state = None
        if not state:
            return {}
        return {"resumable": {
            "tome": tome_id, "request": state.get("request", ""),
            "broad": bool(state.get("broad")), "iterate": bool(state.get("iterate")),
            "resetOk": bool(state.get("resetOk")), "review": bool(state.get("review")),
            "status": state.get("status", "interrupted"),
            "startedAt": state.get("startedAt"),
        }}
