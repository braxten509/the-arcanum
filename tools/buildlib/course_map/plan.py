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


def lesson_counts(text, section_ids):
    """Parse the sealed Phase-1 lesson spine; return empty for pre-v6 plans."""
    raw = field(text, "Lesson counts")
    if not raw:
        return {}
    counts = {}
    for part in (item.strip() for item in raw.split(";") if item.strip()):
        match = re.fullmatch(r"(s\d{2})\s*=\s*(\d+)", part, re.I)
        if not match:
            raise ValueError(
                "**Lesson counts:** must use one physical line like `s01=5; s02=4`")
        sid, count = match.group(1).lower(), int(match.group(2))
        if sid in counts:
            raise ValueError(f"**Lesson counts:** repeats {sid}")
        if not 3 <= count <= 8:
            raise ValueError(f"**Lesson counts:** {sid} must be between 3 and 8")
        counts[sid] = count
    expected = list(section_ids)
    if list(counts) != expected:
        raise ValueError(
            "**Lesson counts:** must name every Section-list id once in the same order; "
            f"expected {'; '.join(f'{sid}=N' for sid in expected)}")
    return counts
