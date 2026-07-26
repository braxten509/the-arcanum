"""Binder amendment job application service."""
from __future__ import annotations

import signal
import threading
import time

from arcanum.config import CLI_EFFORTS

from ..amender import (amend_history, clear_amend_state, forget_amend_record,
                       load_amend_state, review_history, run_amender, save_amend_state)


class BinderService:
    def __init__(self, jobs, processes, ai):
        self.jobs = jobs
        self.processes = processes
        self.ai = ai

    def start(self, tome_id: str, body: dict) -> tuple[dict, int]:
        request_text = str(body.get("request") or "").strip()
        iterate, review = bool(body.get("iterate")), bool(body.get("review"))
        kind = str(body.get("kind") or "claude-cli")
        model, effort = str(body.get("model") or ""), str(body.get("effort") or "")
        review_path = str(body.get("reviewPath") or "")[:200]
        applying_review = bool(review_path and not review)
        if applying_review and not review_history(tome_id, review_path).get("content"):
            return {"ok": False, "error": "the selected review does not belong to this tome"}, 400
        # Publish is its own loop, not a modifier. Every other flag is cleared here rather
        # than trusted from the body: the bench hides them, and a stale checkbox arriving
        # with a publish run must not quietly authorise a progress wipe.
        publish = bool(body.get("publish")) and not review and not applying_review
        iterate = iterate and not applying_review and not publish
        broad = applying_review or bool(body.get("broad")) or iterate or publish
        reset_ok = bool(body.get("resetOk")) and not publish
        update_standard = broad and not review and not publish and (
            applying_review or bool(body.get("updateStandard")))
        if not request_text and not update_standard and not iterate and not review \
                and not publish:
            return {"ok": False, "error": "an amendment request is required"}, 400
        if effort and effort not in CLI_EFFORTS.get(kind, ()):
            effort = ""
        existing = self.jobs.find_running(kind="binder-amend", tome=tome_id)
        if existing:
            return {"ok": True, "jobId": existing["id"], "existing": True}, 200
        started = time.time()
        job_id = self.jobs.create(
            "binder-amend", tome=tome_id, request=request_text[:300], broad=broad,
            review=review, providerKind=kind, providerModel=model,
            log=[], activity=[], startedAt=started)["id"]
        save_amend_state({
            "id": job_id, "tome": tome_id, "request": request_text[:4000],
            "broad": broad, "updateStandard": update_standard, "iterate": iterate,
            "resetOk": reset_ok, "review": review, "publish": publish,
            "kind": kind, "model": model, "effort": effort, "startedAt": started,
            "status": "running",
        })
        threading.Thread(
            target=run_amender,
            args=(job_id, tome_id, request_text, kind, model, effort, broad, iterate,
                  reset_ok, review, review_path, update_standard, publish,
                  self.jobs, self.processes, self.ai),
            daemon=True).start()
        return {"ok": True, "jobId": job_id}, 200

    def cancel(self, job_id: str) -> tuple[dict, int]:
        job = self.jobs.status(job_id)
        if not (job.get("kind") == "binder-amend" and job.get("status") == "running"):
            return {"ok": False, "error": "no running amendment with that id"}, 404
        self.jobs.cancel(job_id)
        self.processes.terminate(job_id, signal.SIGKILL)
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
        # Raw CLI stdout contains tool results and transport JSON. Keep it in the
        # server-side job for diagnostics, but never send it to the live Binder UI.
        output.pop("log", None)
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
        live = self.jobs.status(state.get("id")) if state else {}
        if live.get("status") == "running":
            state = None
        if not state:
            return {}
        return {"resumable": {
            "tome": tome_id, "request": state.get("request", ""),
            "broad": bool(state.get("broad")), "iterate": bool(state.get("iterate")),
            "updateStandard": bool(state.get("updateStandard")),
            "resetOk": bool(state.get("resetOk")), "review": bool(state.get("review")),
            "publish": bool(state.get("publish")),
            # The live job knows it was cancelled before the runner can write that to disk,
            # and the bench asks the instant you stop it. Prefer the job, fall back to the
            # file for a run whose server is gone.
            "status": live.get("status") or state.get("status") or "interrupted",
            "startedAt": state.get("startedAt"),
        }}

    def forget(self, tome_id: str, job_id: str) -> tuple[dict, int]:
        """Remove one unfinished run from the ledger, once it is certainly not running."""
        job = self.jobs.status(job_id) or {}
        if job.get("status") == "running":
            return {"ok": False, "error": "that amendment is still running"}, 409
        if not forget_amend_record(tome_id, job_id):
            return {"ok": False,
                    "error": "no unfinished run with that id is in this tome's ledger"}, 404
        # The one-per-tome state file may still be pointing at the run just deleted, which
        # would otherwise make the bench offer it back on the next open.
        state = load_amend_state(tome_id)
        if state and str(state.get("id")) == str(job_id):
            clear_amend_state(tome_id)
        return {"ok": True}, 200

    def reviews(self, tome_id: str, report_path: str = "") -> dict:
        if report_path:
            return review_history(tome_id, report_path)
        return {**review_history(tome_id), "builds": amend_history(tome_id)}
