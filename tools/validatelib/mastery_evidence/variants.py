"""Verified generated-bank availability and executable proof receipts."""
from __future__ import annotations

import hashlib
import json
import os

from arcanum_core.findings import Finding

from arcanum.assessment.receipts import canonical_hash
from arcanum.assessment.variants import VariantRepository
from buildlib.mastery_evidence import load_policy
from .labs import load_labs
from .schema import error
from .semantics import diversity_problems


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
            findings.append(error("mastery.variant.pool", lab_path,
                                  f"family {family!r} has {len(variants)} verified variants; "
                                  f"central floor is {policy.minimum_verified_variants}", 4))
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
                findings.append(error("mastery.variant.receipt", root,
                                      "verified variant lacks a machine verification receipt", 4))
                continue
            if manifest.get("verificationHash") != canonical_hash(receipt, omit=("receiptHash",)):
                findings.append(error("mastery.variant.receipt-hash", root,
                                      "variant verification receipt hash does not match", 4))
            if (receipt.get("referencePassed") is not True
                    or receipt.get("starterRejected") is not True
                    or len(receipt.get("mutationsRejected") or []) < 2
                    or not all(row.get("rejected") for row in receipt.get("mutationsRejected") or [])):
                findings.append(error("mastery.variant.executable-proof", root,
                                      "reference/starter/mutation executable proof is incomplete", 4))
            semantic = receipt.get("semanticReview") or {}
            if semantic.get("passed") is not True or not semantic.get("evidenceHash"):
                findings.append(error("mastery.variant.semantic-review", root,
                                      "variant lacks a content-bound semantic review", 4))
        if len(blueprints - {None}) < policy.minimum_blueprints:
            findings.append(error("mastery.variant.blueprints", lab_path,
                                  f"family needs at least {policy.minimum_blueprints} distinct blueprints", 4))
        for problem in diversity_problems(summaries, list(generator.get("variationAxes") or [])):
            findings.append(error("mastery.variant.diversity", lab_path, problem, 4))
    return findings
