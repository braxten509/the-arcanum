"""Cumulative coverage contracts: capability ledgers and C# type handoffs."""
import re

from .. import err, warn

_CAPABILITY_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_EXTERNAL_FIRST = {
    "tool-install", "tool-create-open", "tool-navigate", "tool-edit-save",
    "tool-run-test", "tool-diagnose",
}
_CLASS_DECL = re.compile(
    r"\b(?P<mods>(?:(?:public|internal|private|protected|static|sealed|abstract|partial)\s+)*)"
    r"class\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)[^\{]*\{")
_CS_MEMBER = re.compile(
    r"(?m)^\s*(?:\[[^\]\n]+\]\s*)*(?:public|private|protected|internal)\s+"
    r"(?:(?:static|readonly|virtual|override|sealed|abstract|async|const|event|new)\s+)*"
    r"(?:[A-Za-z_][A-Za-z0-9_<>,.\[\]?]*\s+)?"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*(?=\(|\{|=>|=|;)"
)


def _unescape(s):
    return s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def check_capability_ledger(m, sections_data, course_complete=True):
    """Machine-check the cumulative lesson -> capstone coverage contract.

    New scaffolds opt in with [content].capabilityLedger = true. Older installed
    tomes remain compatible until deliberately migrated. A ledger does not prove the
    prose is honest (Phase 8 reads it); it does make omissions, future dependencies,
    and spelling drift explicit enough to reject mechanically.
    """
    content = m.get("content", {}) or {}
    enabled = content.get("capabilityLedger")
    if enabled is None:
        return
    if enabled is not True:
        err("content", "[content].capabilityLedger must be true when present — remove neither "
            "the scaffolded contract nor its lesson/capstone coverage checks")
        return

    # Phase 2 deliberately leaves TODO bodies for Phase 3. Keep the ledger visible
    # there as guidance, but do not make an honest skeleton fail its non-strict gate.
    # Once the TODOs are gone, the same findings become shipping errors.
    work_in_progress = any(
        "TODO" in str(sd.get("brief") or "")
        or any("TODO" in str(les.get("body") or "")
               for les in (sd.get("lessons") or []) if isinstance(les, dict))
        for sd in sections_data
    )
    report = warn if work_in_progress else err

    taught = set()
    first_section_taught = set()
    final_requires = set()
    for index, sd in enumerate(sections_data):
        sid = sd.get("id") or f"section {index + 1}"
        for les in (sd.get("lessons") or []):
            if not isinstance(les, dict):
                continue
            lid = les.get("id") or "?"
            caps = les.get("teaches")
            if not isinstance(caps, list) or not caps:
                report("coverage", f"{lid}: capability ledger is enabled but `teaches` is not a "
                       "non-empty array — name the concrete abilities/API boundaries this lesson teaches")
                continue
            bad = [c for c in caps if not isinstance(c, str) or not _CAPABILITY_ID.fullmatch(c)]
            if bad:
                report("coverage", f"{lid}: teaches contains invalid capability id(s) {bad!r} — use "
                       "stable lowercase kebab-case ids such as `inventory-restore`")
            valid_list = [c for c in caps if isinstance(c, str) and _CAPABILITY_ID.fullmatch(c)]
            valid = set(valid_list)
            if len(valid) < len(valid_list):
                report("coverage", f"{lid}: teaches repeats a capability id")
            taught |= valid
            if index == 0:
                first_section_taught |= valid

        fs = sd.get("freestyle")
        if not isinstance(fs, dict):
            continue
        reqs = fs.get("requires")
        if not isinstance(reqs, list) or not reqs:
            report("coverage", f"{sid}: capability ledger is enabled but freestyle.requires is not "
                   "a non-empty array — trace every checklist/rubric requirement to taught ids")
            continue
        bad = [c for c in reqs if not isinstance(c, str) or not _CAPABILITY_ID.fullmatch(c)]
        if bad:
            report("coverage", f"{sid}: freestyle.requires contains invalid capability id(s) {bad!r} "
                   "— use the exact lowercase kebab-case ids from lesson teaches lists")
        valid_list = [c for c in reqs if isinstance(c, str) and _CAPABILITY_ID.fullmatch(c)]
        valid = set(valid_list)
        if len(valid) < len(valid_list):
            report("coverage", f"{sid}: freestyle.requires repeats a capability id")
        missing = sorted(valid - taught)
        if missing:
            report("coverage", f"{sid}: freestyle requires {', '.join(missing)} before any lesson "
                   "has taught those capability ids — teach them in this/earlier lessons or cut them")
        if index == len(sections_data) - 1:
            final_requires = valid

    if (m.get("runtime", {}) or {}).get("externalWorkspace") is True and sections_data:
        missing = sorted(_EXTERNAL_FIRST - first_section_taught)
        if missing:
            report("coverage", "externalWorkspace capability ledger: the first section does not teach "
                   f"{', '.join(missing)} — a beginner needs install, create/open, navigation, "
                   "edit/save, run/test, and diagnostics before domain work")
        if (course_complete
                and ("tool-deliver" not in taught or "tool-deliver" not in final_requires)):
            report("coverage", "externalWorkspace capability ledger: the final section must teach AND "
                   "require `tool-deliver` — package/export/apply and verify the finished artifact in "
                   "the real target, outside the authoring surface when applicable")


def _balanced_class_blocks(code):
    """Yield (name, body, partial) for brace-balanced class declarations in one block."""
    for match in _CLASS_DECL.finditer(code):
        start = match.end() - 1
        depth = 0
        quote = None
        escaped = False
        for pos in range(start, len(code)):
            ch = code[pos]
            if quote:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == quote:
                    quote = None
                continue
            if ch in ('"', "'"):
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    yield (match.group("name"), code[start + 1:pos],
                           "partial" in match.group("mods").split())
                    break


def check_canonical_type_regressions(m, sections_data):
    """Warn when a later complete-looking C# class silently drops taught members."""
    rt = m.get("runtime", {}) or {}
    language = " ".join(str(rt.get(k, "")) for k in ("language", "editorLang", "name")).lower()
    if "c#" not in language and "csharp" not in language:
        return
    latest = {}
    for sd in sections_data:
        for les in (sd.get("lessons") or []):
            if not isinstance(les, dict):
                continue
            lid = les.get("id") or "?"
            blocks = re.findall(r"<pre><code>(.*?)</code></pre>", str(les.get("body") or ""), re.S)
            lesson_classes = {}
            for raw in blocks:
                code = _unescape(re.sub(r"<[^>]+>", "", raw))
                for name, body, partial in _balanced_class_blocks(code):
                    if partial:
                        continue
                    members = set(_CS_MEMBER.findall(body)) - {name}
                    lesson_classes.setdefault(name, set()).update(members)
            for name, members in lesson_classes.items():
                if not members:
                    continue
                if name in latest:
                    prior, prior_lid = latest[name]
                    missing = sorted(prior - members)
                    if missing:
                        shown = ", ".join(missing[:8]) + ("..." if len(missing) > 8 else "")
                        warn("coverage", f"{lid}: later whole-class example for {name} drops "
                             f"member(s) taught in {prior_lid}: {shown}. Show a complete cumulative "
                             "replacement, or remove the class wrapper and present exact member-only "
                             "edits with an insertion point; beginners treat a class wrapper as the "
                             "whole file", phase=3)
                latest[name] = (members, lid)
