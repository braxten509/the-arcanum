"""Immutable receipt persistence, lookup, and hash validation."""
from __future__ import annotations

import hashlib
import json
import os

from runtimes.common import atomic_write


def canonical_hash(value: dict, *, omit: tuple[str, ...] = ()) -> str:
    payload = {key: item for key, item in value.items() if key not in omit}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ReceiptStore:
    def __init__(self, save_root: str):
        self.root = os.path.join(save_root, "assessment-receipts")
        self.index_path = os.path.join(self.root, "index.json")

    def _index(self) -> dict:
        try:
            with open(self.index_path, encoding="utf-8") as handle:
                value = json.load(handle)
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def find(self, cache_key: str) -> dict | None:
        receipt_hash = self._index().get(cache_key)
        if not isinstance(receipt_hash, str):
            return None
        try:
            with open(os.path.join(self.root, receipt_hash + ".json"), encoding="utf-8") as handle:
                receipt = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return None
        expected = canonical_hash(receipt, omit=("receiptHash",))
        return receipt if receipt.get("receiptHash") == expected == receipt_hash else None

    def write(self, cache_key: str, receipt: dict) -> dict:
        os.makedirs(self.root, exist_ok=True)
        value = dict(receipt)
        value["receiptHash"] = canonical_hash(value, omit=("receiptHash",))
        path = os.path.join(self.root, value["receiptHash"] + ".json")
        encoded = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if not os.path.exists(path):
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
            except FileExistsError:
                pass
        index = self._index()
        index[cache_key] = value["receiptHash"]
        atomic_write(self.index_path, json.dumps(index, ensure_ascii=False,
                                                 indent=2, sort_keys=True) + "\n")
        return value


def receipt_matches(receipt: dict, *, workspace_hash: str, contract_hash: str,
                    variant_hash: str, grader_evidence_hash: str) -> bool:
    return (receipt.get("workspaceHash") == workspace_hash
            and receipt.get("contractHash") == contract_hash
            and receipt.get("variantHash", "") == variant_hash
            and receipt.get("metadata", {}).get("graderEvidenceHash", "") == grader_evidence_hash)
