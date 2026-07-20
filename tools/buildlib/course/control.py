"""Deterministic bounded final prompt projection for every Phase-3 assignment."""
from __future__ import annotations

import json
import os

from .. import BUILD_DIR, REPO
from ..course_map import load_course_map
from .state import derive_course_state, state_path


START_MARKER = "===== HARNESS COURSE CONTROL"
END_MARKER = "===== END HARNESS COURSE CONTROL ====="
MAX_CONTROL_CHARS = 28_000


class CourseControlBudgetError(ValueError):
    pass


def _actual_path(tid, node):
    sid = node["id"].split(".", 1)[0]
    if node["kind"] == "working":
        return f"tomes/{tid}/sections/{sid}/freestyle.toml"
    lesson = node["id"].split(".", 1)[1]
    return f"tomes/{tid}/sections/{sid}/lessons/{lesson}.toml"


def _done(value):
    return ", ".join((value or {}).get("checks") or [])


def _obligation_done(value):
    value = value or {}
    parts = []
    for label, key in (("locations", "evidenceLocations"), ("capabilities", "capabilityIds"),
                       ("proofs", "proofIds"), ("acceptance", "acceptanceIds")):
        if value.get(key):
            parts.append(f"{label}={','.join(value[key])}")
    parts.append("observed=" + str(value.get("observedResult") or ""))
    return "; ".join(parts)


def _contributors(entries, budget):
    largest = sorted(entries, key=lambda item: len(item[1]), reverse=True)[:12]
    detail = "; ".join(f"{label}={len(text)} chars" for label, text in largest)
    return (f"course-control projection exceeds {budget} characters; no item was hidden. "
            f"Largest source items: {detail}")


def _log_metrics(build_id, payload):
    path = os.path.join(BUILD_DIR, f"{build_id}.course-control.log.jsonl")
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":")) + "\n")
    except OSError:
        pass


def prompt_tail(build_id, section_id=None, *, state=None, log=True):
    course = load_course_map(build_id)
    state = state or derive_course_state(build_id)
    tid = state["tomeId"]
    section_id = section_id or state["currentSection"]
    section = next((item for item in course["sections"] if item["id"] == section_id), None)
    if not section:
        raise ValueError(f"course-control current section {section_id!r} is not in the map")
    status = {row["id"]: row for row in state["sections"]}
    entries = []
    def add(label, text=""):
        entries.append((label, str(text)))

    add("header", f"===== HARNESS COURSE CONTROL — MAP v{course['version']} {course['digest']} =====")
    language = course.get("languageMastery")
    if isinstance(language, dict):
        objective = ("project-first / minimum language" if language["level"] == 1 else
                     "project-first / general language breadth" if language["level"] == 2 else
                     "language-first / project as practice-proof")
        add("language-mastery",
            f"LANGUAGE MASTERY — {language['language']} Finish {language['level']}/5 | "
            f"{objective} | capabilities "
            f"{', '.join(language['capabilityIds'])}")
    add("spine-heading", "")
    add("spine-heading", "COURSE SPINE (all sections, one line each)")
    for item in course["sections"]:
        row = status[item["id"]]
        current = " | current" if item["id"] == section_id else ""
        add(f"spine:{item['id']}",
            f"{row['mark']} {item['id']} — {item['title']} | milestone {item['projectMilestone']}{current}")

    add("current-gap", "")
    add("current-heading", "CURRENT SECTION (expanded)")
    for node in section["nodes"]:
        row = next(item for item in status[section_id]["nodes"] if item["id"] == node["id"])
        if node["kind"] == "lesson":
            detail = f"teaches {', '.join(node['teaches'])}"
        else:
            detail = (f"learner creates {', '.join(node['learnerOwnedArtifacts'])} | "
                      f"requires {', '.join(node['requires'])}")
            if node.get("masteryPerformances"):
                detail += " | mastery performances " + ", ".join(node["masteryPerformances"])
        add(f"node:{node['id']}",
            f"{row['mark']} {node['id']} — {node['title']} | {detail} | done when {_done(node['doneWhen'])}")

    add("owners-gap", "")
    add("owners-heading", "REQUIRED PRIOR OWNERS")
    owners = {}
    for planned_section in course["sections"]:
        for node in planned_section["nodes"]:
            for capability in node.get("teaches", []):
                owners[capability] = node
    required = set(section.get("dependsOn") or [])
    for node in section["nodes"]:
        required.update(node.get("dependsOn") or [])
        required.update(node.get("requires") or [])
    owner_lines = []
    by_node = {node["id"]: node for item in course["sections"] for node in item["nodes"]}
    by_section = {
        item["id"]: next(node for node in item["nodes"] if node["kind"] == "working")
        for item in course["sections"]
    }
    for requirement in sorted(required):
        owner = owners.get(requirement) or by_node.get(requirement) or by_section.get(requirement)
        if not owner or owner["id"].startswith(section_id + "."):
            continue
        owner_lines.append((requirement, owner))
    if not owner_lines:
        add("owners:none", "- none; this section owns the first required capabilities")
    for requirement, owner in owner_lines:
        add(f"owner:{requirement}",
            f"- {requirement} -> {owner['id']} @ {_actual_path(tid, owner)}")

    add("obligations-gap", "")
    add("obligations-heading", "ACTIVE OBLIGATIONS")
    active = state["activeObligations"]
    due = [item for item in active if item.get("dueNow") or item.get("overdue")]
    later = [item for item in active if item not in due]
    if not active:
        add("obligations:none", "- none; the active ledger is empty")
    for item in due:
        timing = "OVERDUE" if item.get("overdue") else "DUE NOW"
        add(f"obligation:{item['id']}",
            f"- {timing} {item['id']} [{item['kind']}] owner={item['owner']} "
            f"origin={item['origin']} target={item['target']} location={item['location']}\n"
            f"  REQUIREMENT: {item['requirement']}\n  WHY: {item['reason']}\n"
            f"  DONE WHEN: {_obligation_done(item['doneWhen'])}")
    grouped = {}
    for item in later:
        grouped.setdefault(item["target"], []).append(item)
    for target in sorted(grouped):
        for item in grouped[target]:
            add(f"obligation:{item['id']}",
                f"- LATER {target} — {item['id']} [{item['kind']}] {item['requirement']}")
    add("obligation-source", f"Full records: {os.path.relpath(state_path(build_id), REPO)}")

    add("before-gap", "")
    add("before-heading", "BEFORE STOPPING")
    add("before:1", "1. Complete only the assigned section.")
    add("before:2", "2. Write the exact current handoff proposal.")
    add("before:3", "3. Run the assigned self-check and repair failures.")
    add("before:4", "4. Mark the real section validating and stop.")
    add("truth", "The AI cannot award checkmarks; the harness validates after it stops.")
    add("footer", END_MARKER)
    rendered = "\n".join(text for _label, text in entries)
    if len(rendered) > MAX_CONTROL_CHARS:
        raise CourseControlBudgetError(_contributors(entries, MAX_CONTROL_CHARS))
    if log:
        _log_metrics(build_id, {"characters": len(rendered),
                                "sectionCount": len(course["sections"]),
                                "openObligations": len(active), "dueObligations": len(due),
                                "section": section_id, "mapDigest": course["digest"]})
    return rendered


def append_course_control(prompt, build_id, section_id, *, log=True):
    """Replace any stale copy and guarantee that generated control is the final bytes."""
    text = str(prompt or "")
    marker = text.find(START_MARKER)
    if marker >= 0:
        text = text[:marker]
    return text.rstrip() + "\n\n" + prompt_tail(build_id, section_id, log=log)
