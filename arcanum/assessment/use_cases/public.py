"""Project full receipts into learner-safe assessment results."""
from __future__ import annotations


def public_receipt(receipt: dict) -> dict:
    checks = []
    private_index = 0
    for row in receipt.get("scenarios") or []:
        if row.get("public"):
            check_id = row.get("id")
        else:
            private_index += 1
            check_id = f"private-behavior-{private_index}"
        checks.append({
            "id": check_id, "kind": row.get("kind"), "passed": bool(row.get("passed")),
            "requirementIds": list(row.get("requirementIds") or []),
            "problems": list(row.get("problems") or []),
            "timedOut": bool(row.get("timedOut")),
        })
    return {
        "version": receipt.get("version"), "receiptHash": receipt.get("receiptHash"),
        "nodeId": receipt.get("nodeId"), "performanceId": receipt.get("performanceId"),
        "variantId": receipt.get("variantId"), "variantHash": receipt.get("variantHash"),
        "aidPolicy": receipt.get("aidPolicy"), "supportUsed": receipt.get("supportUsed"),
        "checks": checks, "scores": list(receipt.get("scores") or []),
        "weightedTotal": receipt.get("weightedTotal"), "grade": receipt.get("grade"),
        "essentialPassed": receipt.get("essentialPassed"),
        "independent": receipt.get("independent"),
        "capabilityIds": list(receipt.get("capabilityIds") or []),
        "feedback": receipt.get("feedback", ""), "createdAt": receipt.get("createdAt"),
        "cached": bool(receipt.get("cached")),
        "model": (receipt.get("metadata") or {}).get("model", ""),
    }
