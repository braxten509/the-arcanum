#!/usr/bin/env python3
"""AI registry, jobs, learning store, router, and descriptor service fixtures."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from arcanum.ai import AiRequest, AiResponse, AiService, ProviderRegistry
from arcanum.ai.json_response import parse_json_object
from arcanum.assessment.grading.providers import QualitativeRequest
from arcanum.assessment.grading.qualitative import AiQualitativeProvider
from arcanum.http.router import Router
from arcanum.jobs import JobManager
from arcanum.learning import LearningStateStore
from tools.buildlib.mastery_evidence.delivery import export_mastery_contract


class FixedProvider:
    provider_id = "fixed"

    def complete(self, request: AiRequest) -> AiResponse:
        text = ('noise {"scores":[{"id":"design","score":12,'
                '"comment":"clear"}],"feedback":"sound"} tail')
        return AiResponse(self.provider_id, request.model, text, request.trace)


registry = ProviderRegistry()
registry.register(FixedProvider())
try:
    registry.register(FixedProvider())
except ValueError:
    pass
else:
    raise AssertionError("duplicate AI provider registration was accepted")
assert parse_json_object('{"message":"brace } in a string","ok":true}')["ok"]
qualitative = AiQualitativeProvider(AiService(registry), "fixed", "test-model", str(ROOT))
scored = qualitative.score(QualitativeRequest(
    "fixture", "s01.working", "Test", ({"id": "design", "criterion": "Design", "weight": 20},),
    ({"id": "check", "kind": "run", "passed": True},),
    ({"id": "result", "text": "Produce it", "essential": True},),
    (("main.txt", "learner choice"),), "because"))
assert scored.scores[0]["score"] == 10 and len(scored.evidence_hash) == 64

manager = JobManager()
release = threading.Event()
job = manager.start("fixture", lambda _job_id: (release.wait(2), {"value": 7})[1], node="x")
assert manager.find_running(kind="fixture", node="x")["id"] == job["id"]
release.set()
for _ in range(100):
    if manager.status(job["id"])["status"] == "done":
        break
    time.sleep(0.01)
assert manager.status(job["id"])["result"] == {"value": 7}
cancel_release = threading.Event()
cancelled = manager.start("fixture", lambda _job_id: (cancel_release.wait(2), {})[1])
manager.cancel(cancelled["id"])
cancel_release.set()
time.sleep(0.03)
assert manager.status(cancelled["id"])["status"] == "cancelled"

router = Router()
router.get("/x", lambda _request: None)
try:
    router.get("/x", lambda _request: None)
except ValueError:
    pass
else:
    raise AssertionError("duplicate HTTP route registration was accepted")

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    state_path, log_path = root / "state.json", root / "evidence.jsonl"
    store = LearningStateStore(str(state_path), str(log_path))
    receipt = {"version": 1, "performanceId": "final-proof", "nodeId": "s01.working",
               "receiptHash": "a" * 64, "capabilityIds": ["language-data"],
               "supportUsed": False, "independent": True, "essentialPassed": True,
               "weightedTotal": 80}
    store.record_receipt(receipt, ("final-proof",))
    merged = store.merge_client({"capabilityEvidence": {
        "language-data": {"independent": False, "taught": True},
        "invented": {"independent": True, "evidenceIds": ["fake"]}}})
    assert merged["capabilityEvidence"]["language-data"]["independent"] is True
    assert "independent" not in merged["capabilityEvidence"]["invented"]
    assert merged["assessmentReceipts"]["final-proof"]["receiptHash"] == "a" * 64
    store.record_support("s01.lab01", "oracle")
    assert store.support_used("s01.lab01") and log_path.is_file()

    evidence = {
        "version": 1, "level": 1, "capabilityIds": ["language-data"],
        "foundationCapabilities": {"data": "language-data"},
        "cognitiveTasks": ["build"], "requiredPerformanceCount": 1,
        "standaloneLabCount": 0, "rationaleCount": 0,
        "performances": [{"id": "final-proof", "nodeId": "s01.working",
                          "kind": "guided-modification", "capabilityIds": ["language-data"],
                          "contextRelation": "project", "aidPolicy": "limited",
                          "rationaleRequired": False, "variantFamilyId": ""}],
        "retentionCapabilityIds": ["language-data"],
    }
    course = {"masteryEvidence": evidence}
    path = export_mastery_contract(course, str(root / "tome"))
    assert json.loads(Path(path).read_text()) == evidence

print("mastery application-service tests: OK")
