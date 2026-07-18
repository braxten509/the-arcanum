"""Snapshot -> deterministic scenarios -> qualitative review -> immutable receipt."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json

from arcanum_core.contracts.assessment import AssessmentContract

from .contracts import contract_digest
from .grading.providers import (MissingQualitativeProvider, QualitativeProvider,
                                QualitativeRequest)
from .receipts import ReceiptStore, canonical_hash
from .sandbox import (SandboxPolicy, SandboxRunner, environment_for_runtime,
                      policy_for_runtime)
from .scenarios import ScenarioRegistry, default_registry
from .grading.score import compose_assessment_grade
from .snapshot import SnapshotLimits, create_snapshot


@dataclass(frozen=True)
class AssessmentRequest:
    tome_id: str
    mastery_level: int
    node_id: str
    performance_id: str
    workspace: str
    aid_policy: str
    support_used: bool
    capability_ids: tuple[str, ...]
    variant_id: str = ""
    variant_hash: str = ""
    rationale: str = ""
    language: str = "code"


class AssessmentService:
    def __init__(self, runtime, receipt_store: ReceiptStore,
                 qualitative: QualitativeProvider | None = None,
                 sandbox: SandboxRunner | None = None,
                 scenarios: ScenarioRegistry | None = None,
                 snapshot_limits: SnapshotLimits | None = None,
                 sandbox_policy: SandboxPolicy | None = None,
                 environment: dict[str, str] | None = None):
        self.runtime = runtime
        self.receipts = receipt_store
        self.qualitative = qualitative or MissingQualitativeProvider()
        self.sandbox = sandbox or SandboxRunner()
        self.scenarios = scenarios or default_registry()
        self.snapshot_limits = snapshot_limits or SnapshotLimits()
        self.sandbox_policy = policy_for_runtime(runtime, sandbox_policy)
        self.environment = environment_for_runtime(runtime, environment)

    def assess(self, request: AssessmentRequest, contract: AssessmentContract) -> dict:
        contract_hash = contract_digest(contract)
        with create_snapshot(request.workspace, limits=self.snapshot_limits) as snapshot:
            prepare = getattr(self.runtime, "prepare_assessment_dependencies", None)
            if prepare:
                prepare(snapshot.work)
            qualitative_rows = [item for item in contract.rubric if item.kind == "qualitative"]
            grader_key = self.qualitative.__class__.__name__ if qualitative_rows else "deterministic-only"
            cache_material = {
                "workspaceHash": snapshot.workspace_hash, "contractHash": contract_hash,
                "variantHash": request.variant_hash, "supportUsed": request.support_used,
                "aidPolicy": request.aid_policy, "rationale": request.rationale,
                "grader": grader_key,
            }
            cache_key = canonical_hash(cache_material)
            cached = self.receipts.find(cache_key)
            if cached:
                return {**cached, "cached": True}
            context = {"runtime": self.runtime, "sandbox": self.sandbox,
                       "sandboxPolicy": self.sandbox_policy, "work": snapshot.work,
                       "home": snapshot.home, "env": self.environment}
            deterministic = []
            for scenario in contract.scenarios:
                outcome = self.scenarios.execute(scenario, context)
                deterministic.append({
                    "id": scenario.id, "kind": scenario.kind,
                    "requirementIds": list(scenario.requirement_ids),
                    "capabilityIds": list(scenario.capability_ids),
                    "public": scenario.public, **outcome,
                })
            qualitative_scores, provider, model, grader_evidence, feedback = [], "", "", "", ""
            essential_ids = {item.id for item in contract.requirements if item.essential}
            essential_results = [row for scenario, row in zip(contract.scenarios, deterministic)
                                 if essential_ids.intersection(scenario.requirement_ids)]
            essentials_green = bool(essential_results) and all(
                row.get("passed") for row in essential_results)
            if qualitative_rows and essentials_green:
                response = self.qualitative.score(QualitativeRequest(
                    request.tome_id, request.node_id, request.language,
                    tuple({"id": item.id, "criterion": item.criterion, "weight": item.weight}
                          for item in qualitative_rows), tuple(deterministic),
                    tuple({"id": item.id, "text": item.text, "essential": item.essential}
                          for item in contract.requirements),
                    tuple(snapshot.safe_text_files()), request.rationale))
                qualitative_scores = list(response.scores)
                provider, model = response.provider, response.model
                grader_evidence, feedback = response.evidence_hash, response.feedback
            elif qualitative_rows:
                qualitative_scores = [{"id": item.id, "score": 0,
                                       "comment": "Not scored until essential behavior passes."}
                                      for item in qualitative_rows]
                feedback = "Qualitative review was deferred because essential behavior is incomplete."
            grade = compose_assessment_grade(contract, deterministic, qualitative_scores)
            independent = (not request.support_used and grade.essential_passed
                           and grade.total >= 80)
            receipt = {
                "version": 1, "tomeId": request.tome_id,
                "masteryLevel": request.mastery_level, "nodeId": request.node_id,
                "performanceId": request.performance_id,
                "workspaceHash": snapshot.workspace_hash, "contractHash": contract_hash,
                "variantId": request.variant_id, "variantHash": request.variant_hash,
                "aidPolicy": request.aid_policy, "supportUsed": request.support_used,
                "build": next((row for row in deterministic if row["kind"] == "build"),
                              {"passed": True, "argv": [], "exitCode": 0}),
                "scenarios": deterministic, "qualitativeScores": qualitative_scores,
                "weightedTotal": grade.total, "grade": grade.grade,
                "essentialPassed": grade.essential_passed, "independent": independent,
                "capabilityIds": list(request.capability_ids),
                "createdAt": datetime.now(timezone.utc).isoformat(),
                "feedback": feedback, "scores": list(grade.scores),
                "rationale": request.rationale,
                "metadata": {"provider": provider, "model": model,
                             "graderEvidenceHash": grader_evidence},
            }
            return self.receipts.write(cache_key, receipt)
