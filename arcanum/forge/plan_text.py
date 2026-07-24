"""Parsers over the human-readable build plan markdown (concept, gate answers, tooling)."""
import re


def _plan_concept(text):
    m = re.search(r"(?ms)^## Concept\n(.+?)\n\n", text)
    return (m.group(1).strip().replace("\n", " ") if m else "")[:280]


def _plan_gate(text):
    """Gate answers parsed back out of a plan's '- **Label:** value' lines — the fallback
    for workings launched before launch.json carried them."""
    out = {}
    for key, label in (("prior_knowledge", "Prior knowledge"), ("prior_level", "Starting level"),
                       ("project_scope", "Project scope"),
                       ("depth", "(?:Lesson depth|Scope / depth)"), ("mastery", "Mastery"),
                       ("tooling", "Tooling")):
        m = re.search(rf"(?im)^- \*\*{label}[^:]*?:\*\*\s*(.+)$", text)
        if m:
            out[key] = m.group(1).strip()
    if "project_scope" not in out:
        legacy = re.search(r"(?im)^- \*\*Breadth[^:]*?:\*\*\s*([0-9]+)\s*$", text)
        if legacy:
            out["project_scope"] = str(max(1, min(5, (int(legacy.group(1)) + 1) // 2)))
    return out


def tooling_conflict_details(text, failure=""):
    """Structured Phase-1 conflict data for the approval UI and resume endpoint."""
    fit = re.search(
        r"(?im)^\*\*Tooling fit:\*\*\s*(internal|external|both)\s*[—-]\s*"
        r"BLOCKED\s*:\s*(.+)$", text)
    conflict = bool(fit or "TOOLING_CONFLICT:" in failure)
    if not conflict:
        return {"conflict": False, "current": "", "required": "", "reason": ""}
    current = (fit.group(1).lower() if fit
               else str(_plan_gate(text).get("tooling") or "").lower())
    detail = fit.group(2).strip() if fit else failure.split("TOOLING_CONFLICT:", 1)[-1].strip()
    required_match = re.search(
        r"(?i)(?:REQUIRED_TOOLING\s*=|REQUIRED\s*:)\s*(internal|external|both)",
        detail + " " + failure)
    required = required_match.group(1).lower() if required_match else ""
    reason = re.split(
        r"(?i)\s+(?:[—-]\s*)?(?:REQUIRED_TOOLING\s*=|REQUIRED\s*:)",
        detail, maxsplit=1)[0].strip().rstrip(".;")
    # Legacy conflicts predate the structured REQUIRED marker. BOTH is the safe widening
    # for an internal/external-only plan; new conflicts always carry the exact recommendation.
    if not required and current in ("internal", "external"):
        required = "both"
    return {"conflict": True, "current": current, "required": required,
            "reason": reason or "The selected Tooling cannot deliver the promised artifact."}


def replace_plan_tooling(text, tooling):
    """Apply a human tooling-conflict resolution without changing any other gate answer."""
    policies = {
        "internal": ("INTERNAL (in-browser only)",
                     "Use the browser workbench only; do not require downloads or set `externalWorkspace`."),
        "external": ("EXTERNAL (teach the real tools)",
                     "Teach the real toolchain from install through diagnostics and final delivery; use `externalWorkspace` when the real work cannot run in-browser."),
        "both": ("BOTH (internal + external available)",
                 "Support the browser workbench and teach the complete real-tool path through final delivery."),
    }
    if tooling not in policies:
        raise ValueError("tooling must be internal, external, or both")
    label, meaning = policies[tooling]
    updated, gate_count = re.subn(
        r"(?im)^- \*\*Tooling:\*\*\s*(?:internal|external|both)\s*$",
        f"- **Tooling:** {tooling}", text, count=1)
    updated, policy_count = re.subn(
        r"(?im)^- \*\*Tooling — .*?$",
        f"- **Tooling — {label}:** {meaning}", updated, count=1)
    if gate_count != 1 or policy_count != 1:
        raise ValueError("the build plan's Tooling gate or calibration line is missing")
    return updated
