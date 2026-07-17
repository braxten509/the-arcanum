"""Phase-1 plan fields consumed by the sealed course-map lifecycle."""
import hashlib
import re


def plan_contract_sha256(text):
    """Hash authored plan facts while ignoring later harness-only appendices."""
    text = re.split(r"(?m)^- \*\*Tome id renamed by the harness:", str(text), 1)[0]
    text = re.split(r"(?m)^## Harness ground truth\b", text, 1)[0]
    return hashlib.sha256(text.rstrip().encode("utf-8")).hexdigest()


def field(text, label):
    match = re.search(rf"(?im)^\*\*{re.escape(label)}:\*\*\s*(\S.*)$", text)
    return match.group(1).strip() if match else ""


def acceptance(text):
    raw = field(text, "Acceptance scenarios")
    return [item.strip() for item in raw.split(" -> ") if item.strip()]
