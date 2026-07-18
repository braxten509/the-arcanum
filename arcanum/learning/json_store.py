"""Atomic learner-state adapter with protected assessment evidence fields."""
from __future__ import annotations

import json
import os
import threading
from time import time

from runtimes.common import atomic_write

SERVER_FIELDS = frozenset({"assessmentReceipts", "masteryLabs", "masteryStatus"})


class LearningStateStore:
    def __init__(self, state_path: str, evidence_log_path: str):
        self.path = state_path
        self.log_path = evidence_log_path
        self._lock = threading.RLock()

    def read(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as handle:
                value = json.load(handle)
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def merge_client(self, incoming: dict) -> dict:
        if not isinstance(incoming, dict):
            raise ValueError("learner state must be an object")
        with self._lock:
            current = self.read()
            value = dict(incoming)
            for key in SERVER_FIELDS:
                if key in current:
                    value[key] = current[key]
            server_capabilities = current.get("capabilityEvidence") or {}
            client_capabilities = value.get("capabilityEvidence") or {}
            merged = {key: dict(row) for key, row in client_capabilities.items()
                      if isinstance(row, dict)}
            for row in merged.values():
                for field in ("independent", "retained", "due", "evidenceIds"):
                    row.pop(field, None)
            for capability_id, row in server_capabilities.items():
                if not isinstance(row, dict):
                    continue
                target = merged.setdefault(capability_id, {})
                for field in ("independent", "retained", "due", "evidenceIds"):
                    if field in row:
                        target[field] = row[field]
            value["capabilityEvidence"] = merged
            return value

    def write(self, value: dict) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        atomic_write(self.path, json.dumps(value, ensure_ascii=False, indent=1))

    def support_used(self, node_id: str) -> bool:
        row = (self.read().get("masteryLabs") or {}).get(node_id) or {}
        return bool(row.get("supportUsed"))

    def record_support(self, node_id: str, kind: str) -> dict:
        with self._lock:
            state = self.read()
            labs = state.setdefault("masteryLabs", {})
            row = labs.setdefault(node_id, {})
            row["supportUsed"] = True
            kinds = row.setdefault("supportKinds", [])
            if kind not in kinds:
                kinds.append(kind)
            self.write(state)
            self._append({"event": "support-used", "nodeId": node_id, "kind": kind})
            return dict(row)

    def record_receipt(self, receipt: dict, required_performances: tuple[str, ...]) -> dict:
        with self._lock:
            state = self.read()
            receipts = state.setdefault("assessmentReceipts", {})
            receipts[receipt["performanceId"]] = receipt
            for capability_id in receipt.get("capabilityIds") or []:
                row = state.setdefault("capabilityEvidence", {}).setdefault(capability_id, {})
                row["practiced"] = True
                row["supported"] = bool(row.get("supported") or receipt.get("supportUsed"))
                if (receipt.get("independent") and receipt.get("essentialPassed")
                        and int(receipt.get("weightedTotal") or 0) >= 80):
                    row["independent"] = True
                    row["due"] = True
                    evidence = row.setdefault("evidenceIds", [])
                    if receipt["receiptHash"] not in evidence:
                        evidence.append(receipt["receiptHash"])
            completed = all((receipts.get(performance) or {}).get("independent")
                            for performance in required_performances)
            retained = completed and bool(state.get("capabilityEvidence")) and all(
                row.get("retained") for row in state["capabilityEvidence"].values()
                if row.get("independent"))
            state["masteryStatus"] = "retained" if retained else (
                "provisional" if completed else "learning")
            self.write(state)
            self._append({"event": "assessment-receipt", "nodeId": receipt["nodeId"],
                          "performanceId": receipt["performanceId"],
                          "receiptHash": receipt["receiptHash"],
                          "independent": receipt["independent"],
                          "weightedTotal": receipt["weightedTotal"]})
            return state

    def _append(self, event: dict) -> None:
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        value = {"at": time(), **event}
        with open(self.log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
