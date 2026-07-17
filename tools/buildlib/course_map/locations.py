"""Section-relative planned-obligation references checked before map sealing."""
import os
import re


def section_reference_problem(raw, *, allow_fragment):
    if not isinstance(raw, str) or not raw.strip():
        return "must be a non-empty section-relative file reference"
    if "\\" in raw:
        return "must use forward slashes"
    path, marker, anchor = raw.partition("#")
    if marker and (not allow_fragment or not anchor.strip()):
        return ("must name a file without a fragment" if not allow_fragment
                else "has an empty evidence fragment")
    parts = path.split("/")
    if (not path or path.startswith("/") or any(part in ("", ".", "..") for part in parts)
            or parts[0] == "sections"):
        return "must be relative to its owning section, not a repository or section-directory path"
    return ""


def _working_tome_id(build_id, build_dir, repo):
    plan = os.path.join(build_dir, f"{build_id}.plan.md")
    try:
        with open(plan, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return str(build_id)
    tid = str(build_id)
    pattern = r"renamed by the harness:\*\*\s*`[^`]+`\s*(?:→|->)\s*`([^`]+)`"
    for match in re.finditer(pattern, text):
        candidate = match.group(1)
        if os.path.isdir(os.path.join(repo, "tomes", candidate)):
            tid = candidate
    return tid


def validate_locations(build_id, value, *, build_dir, repo):
    if not isinstance(value, dict) or int(value.get("version") or 0) < 3:
        return []
    tid = _working_tome_id(build_id, build_dir, repo)
    problems = []
    for index, item in enumerate(value.get("plannedObligations") or []):
        if not isinstance(item, dict):
            continue
        label = f"plannedObligations[{index}]"
        references = [
            (item.get("location"), item.get("origin"), "location", False),
            *[(raw, item.get("target"), f"doneWhen.evidenceLocations[{location_index}]", True)
              for location_index, raw in enumerate(
                  ((item.get("doneWhen") or {}).get("evidenceLocations") or []))],
        ]
        for raw, sid, field, allow_fragment in references:
            problem = section_reference_problem(raw, allow_fragment=allow_fragment)
            if problem:
                problems.append(f"{label}.{field} {problem}")
                continue
            path = str(raw).split("#", 1)[0]
            root = os.path.realpath(os.path.join(repo, "tomes", tid, "sections", str(sid)))
            target = os.path.realpath(os.path.join(root, path))
            if not target.startswith(root + os.sep) or not os.path.isfile(target):
                problems.append(
                    f"{label}.{field} does not name an existing {sid} file: {raw!r}")
    return problems
