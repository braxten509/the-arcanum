"""Authored mastery-lab family schema and sealed-node alignment."""
from __future__ import annotations

import glob
import os
import tomllib

from arcanum_core.contracts.mastery import AID_POLICIES, COGNITIVE_TASKS, PERFORMANCE_KINDS
from arcanum_core.findings import Finding

from buildlib.mastery_evidence import load_policy
from .schema import error


def load_labs(tome_root: str) -> list[tuple[str, dict]]:
    out = []
    for path in sorted(glob.glob(os.path.join(
            tome_root, "sections", "*", "mastery-labs", "*.toml"))):
        try:
            with open(path, "rb") as handle:
                out.append((path, tomllib.load(handle)))
        except (OSError, tomllib.TOMLDecodeError):
            out.append((path, {}))
    return out


def lab_findings(tome_root: str, level: int, course_map: dict | None) -> list[Finding]:
    policy = load_policy().for_level(level)
    performances = {item.get("nodeId"): item for item in
                    ((course_map or {}).get("masteryEvidence") or {}).get("performances") or []
                    if isinstance(item, dict) and ".lab" in str(item.get("nodeId"))}
    authored = load_labs(tome_root)
    findings = []
    if len(authored) < policy.standalone_labs:
        findings.append(error("mastery.lab.count", tome_root,
                              f"Mastery {level} requires {policy.standalone_labs} authored standalone labs", 3))
    seen_nodes = set()
    for path, raw in authored:
        lab, generator = raw.get("masteryLab"), raw.get("generator")
        if not isinstance(lab, dict) or not isinstance(generator, dict):
            findings.append(error("mastery.lab.shape", path,
                                  "lab needs [masteryLab] and [generator] tables", 3))
            continue
        required = {"version", "id", "nodeId", "performanceId", "title", "performanceKind",
                    "capabilityIds", "cognitiveTasks", "contextFamily", "contextRelation",
                    "aidPolicy", "estimatedMinutes", "rationaleRequired", "variantFamilyId"}
        missing = sorted(required - set(lab))
        if missing:
            findings.append(error("mastery.lab.fields", path,
                                  "masteryLab is missing: " + ", ".join(missing), 3))
            continue
        node_id = lab.get("nodeId")
        seen_nodes.add(node_id)
        performance = performances.get(node_id)
        if not performance:
            findings.append(error("mastery.lab.node", path,
                                  "lab does not match a sealed mastery-lab performance", 3))
        else:
            expected = {"id": "performanceId", "kind": "performanceKind",
                        "capabilityIds": "capabilityIds", "contextRelation": "contextRelation",
                        "aidPolicy": "aidPolicy", "rationaleRequired": "rationaleRequired",
                        "variantFamilyId": "variantFamilyId"}
            for source, target in expected.items():
                if lab.get(target) != performance.get(source):
                    findings.append(error("mastery.lab.alignment", path,
                                          f"masteryLab.{target} differs from the sealed performance", 3))
        if lab.get("performanceKind") not in PERFORMANCE_KINDS:
            findings.append(error("mastery.lab.kind", path, "unsupported performanceKind", 3))
        tasks = lab.get("cognitiveTasks") or []
        if any(task not in COGNITIVE_TASKS for task in tasks) or not tasks:
            findings.append(error("mastery.lab.tasks", path, "cognitiveTasks are missing or unsupported", 3))
        if lab.get("aidPolicy") not in AID_POLICIES:
            findings.append(error("mastery.lab.aid", path, "unsupported aidPolicy", 3))
        floors = {"minimumBlueprints": policy.minimum_blueprints,
                  "minimumVerifiedVariants": policy.minimum_verified_variants,
                  "variationAxes": policy.minimum_variation_axes}
        for key, floor in floors.items():
            value = generator.get(key)
            count = len(value) if key == "variationAxes" and isinstance(value, list) else value
            if not isinstance(count, int) or count < floor:
                findings.append(error("mastery.lab.generator-floor", path,
                                      f"generator.{key} must meet central floor {floor}", 3))
        if generator.get("mode") != "hybrid-ai-verified" or generator.get("newVariantOnRetry") is not True:
            findings.append(error("mastery.lab.generator-mode", path,
                                  "generator must be hybrid-ai-verified with newVariantOnRetry=true", 3))
        family_root = os.path.splitext(path)[0]
        for name in ("public", "hidden"):
            if not os.path.isdir(os.path.join(family_root, name)):
                findings.append(error("mastery.lab.layout", path,
                                      f"lab family is missing its {name}/ directory", 3))
    missing_nodes = set(performances) - seen_nodes
    if missing_nodes:
        findings.append(error("mastery.lab.missing", tome_root,
                              "sealed lab nodes lack authored families: " + ", ".join(sorted(missing_nodes)), 3))
    return findings
