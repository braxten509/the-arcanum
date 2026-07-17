"""Canonical encoding and digest helpers for sealed course maps."""
import hashlib
import json


def canonical_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def digest(value):
    unsigned = {key: val for key, val in value.items() if key != "digest"}
    return hashlib.sha256(canonical_bytes(unsigned)).hexdigest()
