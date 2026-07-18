"""Central learner-payload leak checks."""
from __future__ import annotations

from arcanum_core.findings import Finding

from .schema import error

HIDDEN_KEYS = {"referenceSteps", "solution", "assessment", "scenarios", "hidden",
               "reference", "mutations", "expectRegex", "expectExact", "verificationReceipt"}


def payload_findings(payload: dict) -> list[Finding]:
    findings = []

    def walk(value, path="payload"):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in HIDDEN_KEYS:
                    findings.append(error("mastery.payload.leak", path,
                                          f"learner payload exposes hidden key {key!r}", 7))
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(payload)
    return findings
