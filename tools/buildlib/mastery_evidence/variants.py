"""Hybrid blueprint expansion and harness-owned executable variant verification."""
from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import itertools
import json
import os
import re
import shutil
import tempfile
from typing import Protocol

from arcanum.assessment.receipts import canonical_hash
from arcanum.assessment.sandbox import (SandboxPolicy, SandboxRunner,
                                        environment_for_runtime, policy_for_runtime)
from arcanum.assessment.scenarios import default_registry
from arcanum.assessment.snapshot import create_snapshot
from arcanum.assessment.variants import _tree_hash
from arcanum_core.contracts.assessment import AssessmentContract

from .policy import load_policy


class VariantGenerationError(ValueError):
    pass


BLUEPRINT_KEYS = frozenset({
    "version", "id", "title", "brief", "difficulty", "starterBuildable",
    "axes", "publicFiles", "publicExamples", "hiddenFiles", "referenceFiles",
    "mutations", "dependencies", "assessment",
})


class SemanticReviewer(Protocol):
    def review(self, candidate: dict) -> dict: ...


@dataclass(frozen=True)
class GenerationResult:
    family_id: str
    generated: int
    reused: int
    variant_ids: tuple[str, ...]


def _render(value, slots: dict[str, str]):
    if isinstance(value, str):
        for key, replacement in slots.items():
            value = value.replace("{{" + key + "}}", replacement)
        if re.search(r"\{\{[a-zA-Z0-9_-]+\}\}", value):
            raise VariantGenerationError("blueprint contains an unfilled slot")
        return value
    if isinstance(value, list):
        return [_render(item, slots) for item in value]
    if isinstance(value, dict):
        return {key: _render(item, slots) for key, item in value.items()}
    return value


def _write_tree(root: str, files: dict[str, str]) -> None:
    for relative, content in sorted(files.items()):
        if (not isinstance(relative, str) or relative.startswith(("/", "\\"))
                or "\\" in relative or any(part in {"", ".", ".."} for part in relative.split("/"))):
            raise VariantGenerationError(f"unsafe generated path {relative!r}")
        target = os.path.realpath(os.path.join(root, *relative.split("/")))
        if not target.startswith(os.path.realpath(root) + os.sep):
            raise VariantGenerationError("generated path escapes its package")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(str(content))


def _overlay(source: str, overlay: str, target: str) -> None:
    shutil.copytree(source, target)
    if os.path.isdir(overlay):
        shutil.copytree(overlay, target, dirs_exist_ok=True)


def _run_contract(runtime, contract: AssessmentContract, workspace: str,
                  sandbox: SandboxRunner, policy: SandboxPolicy) -> dict:
    policy = policy_for_runtime(runtime, policy)
    with create_snapshot(workspace) as snapshot:
        context = {"runtime": runtime, "sandbox": sandbox, "sandboxPolicy": policy,
                   "work": snapshot.work, "home": snapshot.home,
                   "env": environment_for_runtime(runtime)}
        results = []
        for scenario in contract.scenarios:
            outcome = default_registry().execute(scenario, context)
            results.append({"id": scenario.id, "requirementIds": list(scenario.requirement_ids),
                            **outcome})
    essential = {item.id for item in contract.requirements if item.essential}
    relevant = [result for scenario, result in zip(contract.scenarios, results)
                if essential.intersection(scenario.requirement_ids)]
    return {"passed": bool(relevant) and all(item.get("passed") for item in relevant),
            "scenarios": results}


def _load_blueprints(family_root: str) -> list[dict]:
    root = os.path.join(family_root, "blueprints")
    blueprints = []
    try:
        names = sorted(name for name in os.listdir(root) if name.endswith(".json"))
    except OSError:
        names = []
    for name in names:
        with open(os.path.join(root, name), encoding="utf-8") as handle:
            value = json.load(handle)
        if set(value) != BLUEPRINT_KEYS or value.get("version") != 1 or not value.get("id"):
            raise VariantGenerationError(
                f"blueprint {name!r} must use exactly the version-1 candidate schema")
        if (not isinstance(value.get("starterBuildable"), bool)
                or not str(value.get("difficulty") or "").strip()
                or not isinstance(value.get("publicExamples"), list)):
            raise VariantGenerationError(
                f"blueprint {name!r} needs difficulty, starterBuildable, and publicExamples")
        blueprints.append(value)
    return blueprints


def _combinations(blueprint: dict, declared_axes: list[str]):
    axes = blueprint.get("axes")
    if not isinstance(axes, dict) or set(axes) != set(declared_axes):
        raise VariantGenerationError(
            f"blueprint {blueprint.get('id')!r} axes must exactly match the lab declaration")
    values = []
    for axis in declared_axes:
        choices = axes[axis]
        if not isinstance(choices, list) or len(choices) < 2 or len(set(choices)) != len(choices):
            raise VariantGenerationError(f"blueprint axis {axis!r} needs at least two unique values")
        values.append([str(item) for item in choices])
    yield from (dict(zip(declared_axes, row)) for row in itertools.product(*values))


class VariantGenerator:
    def __init__(self, runtime, reviewer: SemanticReviewer,
                 sandbox: SandboxRunner | None = None,
                 sandbox_policy: SandboxPolicy | None = None):
        self.runtime = runtime
        self.reviewer = reviewer
        self.sandbox = sandbox or SandboxRunner()
        self.sandbox_policy = sandbox_policy or SandboxPolicy()

    def generate(self, tome_root: str, lab_file: str, *, target_count: int | None = None) -> GenerationResult:
        import tomllib
        with open(lab_file, "rb") as handle:
            authored = tomllib.load(handle)
        lab, generator = authored.get("masteryLab") or {}, authored.get("generator") or {}
        try:
            with open(os.path.join(tome_root, "tome.toml"), "rb") as handle:
                manifest = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise VariantGenerationError(f"cannot load the tome mastery contract: {exc}") from exc
        level = int((manifest.get("mastery") or {}).get("level") or 0)
        if level not in range(1, 6):
            raise VariantGenerationError("lab must declare masteryLevel from 1 through 5")
        policy = load_policy().for_level(level)
        family_id = str(lab.get("variantFamilyId") or "")
        axes = list(generator.get("variationAxes") or [])
        family_root = os.path.splitext(lab_file)[0]
        blueprints = _load_blueprints(family_root)
        minimum_blueprints = max(policy.minimum_blueprints,
                                 int(generator.get("minimumBlueprints") or 0))
        if len(blueprints) < minimum_blueprints:
            raise VariantGenerationError(
                f"family needs {minimum_blueprints} blueprints; found {len(blueprints)}")
        wanted = target_count or max(policy.minimum_verified_variants,
                                     int(generator.get("minimumVerifiedVariants") or 0))
        candidates = []
        iterators = [(blueprint, iter(_combinations(blueprint, axes))) for blueprint in blueprints]
        while len(candidates) < wanted:
            progressed = False
            for blueprint, combinations in iterators:
                try:
                    slots = next(combinations)
                except StopIteration:
                    continue
                candidates.append((blueprint, slots))
                progressed = True
                if len(candidates) == wanted:
                    break
            if not progressed:
                raise VariantGenerationError("blueprints do not provide enough unique axis combinations")
        bank = os.path.join(tome_root, "generated", "mastery-labs", family_id)
        os.makedirs(bank, exist_ok=True)
        generated, reused, ids = 0, 0, []
        for blueprint, slots in candidates:
            variant_id = self._generate_one(bank, family_id, lab, blueprint, slots)
            ids.append(variant_id)
            if variant_id.startswith("reused:"):
                ids[-1] = variant_id.split(":", 1)[1]
                reused += 1
            else:
                generated += 1
        return GenerationResult(family_id, generated, reused, tuple(ids))

    def _generate_one(self, bank: str, family_id: str, lab: dict,
                      blueprint: dict, slots: dict[str, str]) -> str:
        rendered = _render(copy.deepcopy(blueprint), slots)
        identity = json.dumps({"blueprint": blueprint.get("id"), "slots": slots,
                               "source": blueprint}, sort_keys=True, separators=(",", ":"))
        short = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        variant_id = f"{blueprint['id']}-{short}"
        target = os.path.join(bank, variant_id)
        if os.path.isdir(target):
            try:
                manifest = json.load(open(os.path.join(target, "manifest.json"), encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raise VariantGenerationError(f"existing variant {variant_id!r} is corrupt")
            if manifest.get("verified") is True:
                return "reused:" + variant_id
            raise VariantGenerationError(f"refused to overwrite unverified variant {variant_id!r}")
        temporary = tempfile.mkdtemp(prefix=".candidate-", dir=bank)
        try:
            public = os.path.join(temporary, "public")
            hidden = os.path.join(temporary, "hidden")
            reference = os.path.join(temporary, "reference")
            mutations = os.path.join(temporary, "mutations")
            for path in (public, hidden, reference, mutations):
                os.makedirs(path)
            _write_tree(public, rendered.get("publicFiles") or {})
            _write_tree(hidden, rendered.get("hiddenFiles") or {})
            _write_tree(reference, rendered.get("referenceFiles") or {})
            mutation_rows = rendered.get("mutations") or {}
            if not isinstance(mutation_rows, dict) or len(mutation_rows) < 2:
                raise VariantGenerationError("every blueprint needs at least two deficient mutations")
            for mutation_id, files in mutation_rows.items():
                _write_tree(os.path.join(mutations, mutation_id), files)
            contract = AssessmentContract.from_dict(rendered.get("assessment"))
            with open(os.path.join(hidden, "assessment.json"), "w", encoding="utf-8") as handle:
                json.dump(rendered.get("assessment"), handle, indent=2, sort_keys=True)
            verification_root = tempfile.mkdtemp(prefix="arcanum-variant-proof-")
            try:
                starter_result = _run_contract(
                    self.runtime, contract, public, self.sandbox, self.sandbox_policy)
                reference_workspace = os.path.join(verification_root, "reference")
                _overlay(public, reference, reference_workspace)
                reference_result = _run_contract(
                    self.runtime, contract, reference_workspace, self.sandbox, self.sandbox_policy)
                mutation_results = []
                for mutation_id in sorted(mutation_rows):
                    workspace = os.path.join(verification_root, "mutation-" + mutation_id)
                    _overlay(public, os.path.join(mutations, mutation_id), workspace)
                    result = _run_contract(
                        self.runtime, contract, workspace, self.sandbox, self.sandbox_policy)
                    mutation_results.append({"id": mutation_id, "rejected": not result["passed"],
                                             "scenarios": result["scenarios"]})
            finally:
                shutil.rmtree(verification_root, ignore_errors=True)
            if starter_result["passed"]:
                raise VariantGenerationError("starter already passes the essential assessment")
            starter_build = next((row for row in starter_result["scenarios"]
                                  if row.get("id") and row.get("argv")
                                  and row.get("id") in {scenario.id for scenario in contract.scenarios
                                                       if scenario.kind == "build"}), None)
            if rendered.get("starterBuildable") and (
                    not starter_build or not starter_build.get("passed")):
                raise VariantGenerationError("blueprint promises a buildable starter, but it does not build")
            if not reference_result["passed"]:
                raise VariantGenerationError("reference solution fails its assessment")
            if not all(row["rejected"] for row in mutation_results):
                raise VariantGenerationError("a deliberately deficient mutation passed")
            semantic_input = {
                "familyId": family_id, "variantId": variant_id,
                "title": rendered.get("title"), "brief": rendered.get("brief"),
                "publicExamples": rendered.get("publicExamples") or [],
                "requirements": rendered.get("assessment", {}).get("requirements") or [],
                "capabilityIds": lab.get("capabilityIds") or [],
                "cognitiveTasks": lab.get("cognitiveTasks") or [],
                "contextRelation": lab.get("contextRelation"), "axes": slots,
                "publicFiles": rendered.get("publicFiles") or {},
            }
            semantic = self.reviewer.review(semantic_input)
            if semantic.get("passed") is not True or not semantic.get("evidenceHash"):
                raise VariantGenerationError("semantic reviewer rejected or failed to bind the candidate")
            verification = {
                "version": 1, "starterRejected": True, "starter": starter_result,
                "referencePassed": True, "reference": reference_result,
                "mutationsRejected": mutation_results, "semanticReview": semantic,
            }
            verification["receiptHash"] = canonical_hash(verification, omit=("receiptHash",))
            with open(os.path.join(temporary, "verification.json"), "w", encoding="utf-8") as handle:
                json.dump(verification, handle, indent=2, sort_keys=True)
            manifest = {
                "version": 1, "familyId": family_id, "variantId": variant_id,
                "blueprintId": blueprint["id"], "verified": True,
                "title": rendered.get("title", ""), "brief": rendered.get("brief", ""),
                "publicExamples": list(rendered.get("publicExamples") or []),
                "difficulty": rendered.get("difficulty"),
                "estimatedMinutes": lab.get("estimatedMinutes"),
                "rationalePrompt": lab.get("rationalePrompt") or (
                    "Explain the design, why it meets the requirements, and how you verified it."),
                "aidPolicy": lab.get("aidPolicy"),
                "requirements": rendered.get("assessment", {}).get("requirements") or [],
                "capabilityIds": list(lab.get("capabilityIds") or []),
                "cognitiveTasks": list(lab.get("cognitiveTasks") or []),
                "axes": slots, "dependencies": list(rendered.get("dependencies") or []),
                "structuralSignature": canonical_hash({
                    "blueprintId": blueprint["id"],
                    "publicExtensions": sorted({os.path.splitext(path)[1]
                                                for path in rendered.get("publicFiles") or {}}),
                    "scenarioKinds": [scenario.kind for scenario in contract.scenarios],
                    "requirementCount": len(contract.requirements),
                    "mutationCount": len(mutation_rows),
                }),
                "verificationHash": canonical_hash(verification, omit=("receiptHash",)),
            }
            manifest["contentHash"] = _tree_hash(temporary)
            with open(os.path.join(temporary, "manifest.json"), "w", encoding="utf-8") as handle:
                json.dump(manifest, handle, indent=2, sort_keys=True)
            os.replace(temporary, target)
            temporary = ""
            return variant_id
        finally:
            if temporary:
                shutil.rmtree(temporary, ignore_errors=True)
