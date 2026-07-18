"""Working and mastery-lab assessment use cases; HTTP-independent."""
from __future__ import annotations

import os

import tome_layout
from runtimes.validation_environment import ensure_validation_environment

from arcanum.ai import AiService
from arcanum.assessment.variants import VariantRepository, VariantUnavailable

from .catalog import authored_lab, load_variant_assessment, performance_for
from .lab_workspaces import LabWorkspaceStore
from .public import public_receipt
from ..contracts import load_working_contract
from ..grading.qualitative import AiQualitativeProvider
from ..receipts import ReceiptStore
from ..runner import AssessmentRequest, AssessmentService
from ..sandbox import SandboxPolicy


class AssessmentApplication:
    def __init__(self, *, ai: AiService, tome_root: str, save_root: str,
                 runtime, workspace: str, settings: dict, tome_id: str):
        self.ai, self.tome_root, self.save_root = ai, tome_root, save_root
        self.runtime, self.workspace = runtime, workspace
        self.settings, self.tome_id = settings, tome_id

    def _service(self) -> AssessmentService:
        ai_settings = self.settings.get("ai") or {}
        provider_id = str(ai_settings.get("graderKind") or "claude-cli")
        model = str(ai_settings.get("graderModel") or ai_settings.get("grader") or "")
        qualitative = AiQualitativeProvider(
            self.ai, provider_id, model, self.tome_root,
            api_key=str((ai_settings.get("keys") or {}).get(provider_id) or ""),
            custom_command=str(ai_settings.get("graderCommand") or ""))
        environment = ensure_validation_environment(self.tome_id)
        read_paths = []
        validation_root = os.path.realpath(os.path.join(
            os.path.dirname(os.path.dirname(self.tome_root)), ".tome-build", "validation-envs"))
        if os.path.isdir(validation_root):
            read_paths.append(validation_root)
        return AssessmentService(
            self.runtime, ReceiptStore(self.save_root), qualitative,
            sandbox_policy=SandboxPolicy(read_paths=tuple(read_paths)), environment=environment)

    def assess_working(self, section_id: str, rationale: str, learning_store) -> dict:
        node_id = f"{section_id}.working"
        evidence, performance = performance_for(self.tome_root, node_id)
        section = tome_layout.load_section(self.tome_root, section_id)
        contract = load_working_contract(
            self.tome_root, section_id, section.get("freestyle") or {})
        if performance.rationale_required and not rationale.strip():
            raise ValueError("this performance requires a learner rationale")
        request = AssessmentRequest(
            self.tome_id, evidence.level, node_id, performance.id, self.workspace,
            performance.aid_policy, learning_store.support_used(node_id),
            performance.capability_ids, rationale=rationale,
            language=getattr(self.runtime, "LANGUAGE", self.runtime.NAME))
        receipt = self._service().assess(request, contract)
        learning_store.record_receipt(receipt, tuple(row.id for row in evidence.performances))
        return public_receipt(receipt)

    def assess_lab(self, node_id: str, rationale: str, learning_store) -> dict:
        evidence, performance = performance_for(self.tome_root, node_id)
        _path, authored = authored_lab(self.tome_root, node_id)
        family = performance.variant_family_id
        repository = VariantRepository(self.tome_root, self.save_root)
        assignment = repository.assignment(family)
        if not assignment:
            raise VariantUnavailable("this mastery lab has no active assigned variant")
        item = next((row for row in repository.verified_variants(family)
                     if row["manifest"]["variantId"] == assignment["variantId"]), None)
        if not item:
            raise VariantUnavailable("the assigned mastery-lab variant is no longer verified")
        if performance.rationale_required and not rationale.strip():
            raise ValueError("this mastery lab requires a learner rationale")
        workspace = LabWorkspaceStore(self.save_root).path(family, assignment["variantId"])
        contract = load_variant_assessment(item["root"])
        request = AssessmentRequest(
            self.tome_id, evidence.level, node_id, performance.id, workspace,
            performance.aid_policy, learning_store.support_used(node_id),
            performance.capability_ids, assignment["variantId"], assignment["variantHash"],
            rationale, getattr(self.runtime, "LANGUAGE", self.runtime.NAME))
        receipt = self._service().assess(request, contract)
        learning_store.record_receipt(receipt, tuple(row.id for row in evidence.performances))
        if not receipt.get("independent"):
            repository.abandon(family)
        return public_receipt(receipt)


class MasteryLabApplication:
    def __init__(self, tome_root: str, save_root: str, runtime):
        self.tome_root, self.save_root, self.runtime = tome_root, save_root, runtime
        self.repository = VariantRepository(tome_root, save_root)
        self.workspaces = LabWorkspaceStore(save_root)

    def assignment(self, node_id: str) -> dict:
        _evidence, performance = performance_for(self.tome_root, node_id)
        _path, authored = authored_lab(self.tome_root, node_id)
        lab = authored["masteryLab"]
        assignment = self.repository.assign(performance.variant_family_id)
        package = self.repository.public_package(
            performance.variant_family_id, assignment["variantId"])
        workspace = self.workspaces.seed(
            performance.variant_family_id, assignment["variantId"], package.pop("files"))
        files = self.workspaces.files(
            performance.variant_family_id, assignment["variantId"], self.runtime)
        return {"lab": lab, "assignment": {
                    key: assignment[key] for key in
                    ("familyId", "variantId", "variantHash", "assignedAt", "attempt")},
                "challenge": package, "files": files,
                "workspaceKind": "isolated-mastery-lab", "refreshRerolls": False}

    def write(self, node_id: str, files: list[dict]) -> dict:
        _evidence, performance = performance_for(self.tome_root, node_id)
        assignment = self.repository.assignment(performance.variant_family_id)
        if not assignment:
            raise VariantUnavailable("this mastery lab has no active assignment")
        self.workspaces.write(performance.variant_family_id, assignment["variantId"], files)
        return {"ok": True}

    def retry(self, node_id: str) -> dict:
        _evidence, performance = performance_for(self.tome_root, node_id)
        current = self.repository.assignment(performance.variant_family_id)
        excluded = (current["variantId"],) if current else ()
        if current:
            self.repository.abandon(performance.variant_family_id)
        self.repository.assign(performance.variant_family_id, exclude=excluded)
        return self.assignment(node_id)
