"""Verified generated-bank availability and executable proof receipts."""
from __future__ import annotations

import hashlib
import json
import os

from arcanum_core.findings import Finding, Severity

from arcanum.assessment.receipts import canonical_hash
from arcanum.assessment.variants import VariantRepository
from buildlib.mastery_evidence import load_policy
from .labs import load_labs
from .schema import error
from .semantics import diversity_problems, structural_signature_count


def gate(code: str, location: str, message: str) -> Finding:
    return Finding(Severity.WARNING, code, location, message, 7)


def variant_findings(tome_root: str, save_root: str, level: int) -> list[Finding]:
    policy = load_policy().for_level(level)
    repository = VariantRepository(tome_root, save_root)
    findings = []
    for lab_path, raw in load_labs(tome_root):
        lab, generator = raw.get("masteryLab") or {}, raw.get("generator") or {}
        family = lab.get("variantFamilyId")
        if not family:
            continue
        variants = repository.verified_variants(family)
        if len(variants) < policy.minimum_verified_variants:
            findings.append(gate("mastery.variant.pool", lab_path,
                                  f"family {family!r} has {len(variants)} verified variants; "
                                  f"central floor is {policy.minimum_verified_variants}"))
        summaries = []
        blueprints = set()
        for item in variants:
            manifest, root = item["manifest"], item["root"]
            summaries.append(manifest)
            blueprints.add(manifest.get("blueprintId"))
            receipt_path = os.path.join(root, "verification.json")
            try:
                receipt = json.load(open(receipt_path, encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                findings.append(gate("mastery.variant.receipt", root,
                                     "verified variant lacks a machine verification receipt"))
                continue
            if manifest.get("verificationHash") != canonical_hash(receipt, omit=("receiptHash",)):
                findings.append(gate("mastery.variant.receipt-hash", root,
                                     "variant verification receipt hash does not match"))
            if (receipt.get("referencePassed") is not True
                    or receipt.get("starterRejected") is not True
                    or len(receipt.get("mutationsRejected") or []) < 2
                    or not all(row.get("rejected") for row in receipt.get("mutationsRejected") or [])):
                findings.append(gate("mastery.variant.executable-proof", root,
                                     "reference/starter/mutation executable proof is incomplete"))
            semantic = receipt.get("semanticReview") or {}
            if semantic.get("passed") is not True or not semantic.get("evidenceHash"):
                findings.append(gate("mastery.variant.semantic-review", root,
                                     "variant lacks a content-bound semantic review"))
        if len(blueprints - {None}) < policy.minimum_blueprints:
            findings.append(gate("mastery.variant.blueprints", lab_path,
                                 f"family needs at least {policy.minimum_blueprints} distinct blueprints"))
        if structural_signature_count(summaries) < policy.minimum_blueprints:
            findings.append(gate(
                "mastery.variant.structural-diversity", lab_path,
                f"family needs at least {policy.minimum_blueprints} verified structural signatures"))
        for problem in diversity_problems(summaries, list(generator.get("variationAxes") or [])):
            findings.append(gate("mastery.variant.diversity", lab_path, problem))
    return findings
