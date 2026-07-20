"""The [meta] table: required fields and shelf-copy tone."""
import re

from ... import META_REQUIRED, err, warn


def check_meta(m, label):
    meta = m.get("meta")
    if not isinstance(meta, dict):
        err(label, "[meta] table is missing")
        return None
    for key in META_REQUIRED:
        if not str(meta.get(key, "")).strip():
            err(label, f"[meta] {key} is required and must be non-empty")
    description = str(meta.get("description", ""))
    negative_scope = re.compile(
        r"\b(?:does not|doesn't|do not|don't)\s+(?:cover|include|teach)\b|"
        r"\b(?:deliberately\s+)?stops?\s+short\b|"
        r"\b(?:the\s+)?course\s+(?:deliberately\s+)?stops?\s+at\b|"
        r"\bnot\s+(?:covered|included|taught)\b|"
        r"\bscope\s+cuts?\b",
        re.IGNORECASE,
    )
    if negative_scope.search(description):
        warn(label, "[meta] description is public shelf copy: summarize the artifact and "
                    "capabilities positively; keep exclusions in the plan's Graduate ledger",
             phase=2)
    return meta
