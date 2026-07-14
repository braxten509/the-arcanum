"""Harness-generated active behavior contract for Phase-3 workers."""
import os
import shlex
import tomllib

from . import REPO

import tome_layout
from tome_proof import active_proofs


def contract(tid, before=None):
    root = os.path.join(REPO, "tomes", tid)
    try:
        with open(os.path.join(root, "tome.toml"), "rb") as handle:
            manifest = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return {"proofs": [], "acceptance": [],
                "error": f"cannot read tomes/{tid}/tome.toml: {exc}"}
    ids = [str(item) for item in ((manifest.get("content") or {}).get("sections") or [])]
    if before and before not in ids:
        return {"proofs": [], "acceptance": [],
                "error": f"section {before!r} is not listed by tomes/{tid}/tome.toml"}
    if before:
        ids = ids[:ids.index(before)]
    sections = []
    for sid in ids:
        try:
            sections.append(tome_layout.load_section(root, sid))
        except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
            return {"proofs": [], "acceptance": [],
                    "error": f"cannot load earlier section {sid}: {exc}"}
    return {"proofs": active_proofs(sections),
            "acceptance": list((manifest.get("acceptance") or {}).get("scenarios") or []),
            "error": None}


def render(tid, before=None, data=None):
    data = data or contract(tid, before)
    lines = ["ACTIVE BEHAVIOR CONTRACT (harness-generated; persists through shipping)"]
    if data.get("error"):
        lines.append("ERROR: " + data["error"])
        return "\n".join(lines)
    if not data["proofs"]:
        lines.append("- no earlier authored proof yet; the runtime scaffold still cannot be "
                     "overwritten with mode=write")
    for item in data["proofs"]:
        command = " ".join(shlex.quote(arg) for arg in item.get("runArgs") or [])
        caps = ", ".join(item.get("capabilities") or []) or "build/file contract"
        lines.append(f"- {item['section']} [{item.get('mode')}]: {caps}; args: {command or '(none)'}")
    if data["acceptance"]:
        lines.append("- final acceptance: " + " -> ".join(data["acceptance"]))
    lines += [
        "A later edit may not remove any item above. The section validator reconstructs the",
        "project and reruns every still-active proof after this section. Existing files require",
        "an exact replace, or mode=rewrite with preserves=all-active; preservation prose is not evidence.",
    ]
    return "\n".join(lines)


def prompt(tid, sid):
    command = ('cd "$ARCANUM_REPO_ROOT" && ' + shlex.join(
        ["python3", "tools/report_active_contract.py", f"tomes/{tid}", "--before", sid]))
    return ("\n\n===== ACTIVE BEHAVIOR CONTRACT =====\n"
            f"Immediately before editing {sid}, run and read:\n  {command}\n\n"
            "That command reads the current disk checkpoint, including an earlier section authored "
            "in this same warm batch. Treat every listed proof/capability as immutable unless this "
            "section declares a valid proof supersession. The section gate reruns the entire active "
            "set; a handoff claim cannot replace a green execution result.\n")
