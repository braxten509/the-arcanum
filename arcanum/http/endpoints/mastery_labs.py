"""Mastery-lab assignment, isolated workspace, retry, and support endpoints."""
from __future__ import annotations

import json

from arcanum.app import AppServices
from arcanum.assessment.use_cases.public import public_receipt

from ..response import Response, ok


class MasteryLabEndpoints:
    def __init__(self, services: AppServices):
        self.services = services

    def get_assignment(self, request) -> Response:
        return ok(self.services.mastery_labs(request.tome_id()).assignment(
            request.value("nodeId")))

    def save_workspace(self, request) -> Response:
        body = request.json()
        if set(body) - {"nodeId", "files", "tome"}:
            raise ValueError("mastery-lab workspace request has unsupported fields")
        return ok(self.services.mastery_labs(request.tome_id()).write(
            str(body.get("nodeId") or ""), body.get("files") or []))

    def retry(self, request) -> Response:
        body = request.json()
        if set(body) - {"nodeId", "tome"}:
            raise ValueError("mastery-lab retry request has unsupported fields")
        return ok(self.services.mastery_labs(request.tome_id()).retry(
            str(body.get("nodeId") or "")))

    def support(self, request) -> Response:
        body = request.json()
        if set(body) - {"nodeId", "kind", "tome"}:
            raise ValueError("support event has unsupported fields")
        kind = str(body.get("kind") or "")
        if kind not in {"hint", "scroll", "oracle", "revealed-solution"}:
            raise ValueError("unsupported assistance kind")
        row = self.services.learning(request.tome_id()).record_support(
            str(body.get("nodeId") or ""), kind)
        return ok({"ok": True, "support": row})

    def evidence_export(self, request) -> Response:
        state = self.services.learning(request.tome_id()).read()
        receipts = {key: public_receipt(value) for key, value in
                    (state.get("assessmentReceipts") or {}).items()
                    if isinstance(value, dict)}
        return ok({"version": 1, "masteryStatus": state.get("masteryStatus", "learning"),
                   "capabilityEvidence": state.get("capabilityEvidence") or {},
                   "assessmentReceipts": receipts})
