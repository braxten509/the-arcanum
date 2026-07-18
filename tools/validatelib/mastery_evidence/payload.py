"""Central learner-payload leak checks."""
from __future__ import annotations

from arcanum_core.findings import Finding

from .schema import error

HIDDEN_KEYS = {"referenceSteps", "solution", "assessment", "scenarios", "hidden",
               "reference", "mutations", "expectRegex", "expectExact", "verificationReceipt"}


def evidence_payload_privacy_enabled(manifest: dict) -> bool:
    """Legacy payloads keep their historical shape; evidence contracts opt in."""
    mastery = manifest.get("mastery") if isinstance(manifest, dict) else None
    return isinstance(mastery, dict) and mastery.get("evidenceVersion") is not None


def payload_findings(payload: dict) -> list[Finding]:
    findings = []

    def walk(value, path="payload"):
        if isinstance(value, dict):
            for key, child in value.items():
                public_acceptance_ids = (
                    key == "scenarios" and path == "payload.acceptance"
                    and isinstance(child, list)
                    and all(isinstance(item, str) for item in child))
                if key in HIDDEN_KEYS and not public_acceptance_ids:
                    findings.append(error("mastery.payload.leak", path,
                                          f"learner payload exposes hidden key {key!r}", 7))
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(payload)
    return findings
