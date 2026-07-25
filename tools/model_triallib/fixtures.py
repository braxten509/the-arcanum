"""Generate the tiny writable workspaces used by live model-role trials."""
import json
import os
from pathlib import Path

from .reviewer_fixture import (CANDIDATE_IDS, create_reviewer_fixture,
                               reviewer_protected_paths)


ROLE_ORDER = ("drafter", "writer", "sections", "reviewer")

TRIAL_MODELS = (
    {"id": "deepseek-v4-flash", "spec": "opencode-cli:opencode-go/deepseek-v4-flash@high",
     "roles": ("drafter",)},
    {"id": "minimax-m3", "spec": "opencode-cli:opencode-go/minimax-m3",
     "roles": ("writer", "sections", "reviewer")},
    {"id": "kimi-k2.6", "spec": "opencode-cli:opencode-go/kimi-k2.6",
     "roles": ("reviewer",)},
    {"id": "gpt-5.6-terra", "spec": "codex-cli:gpt-5.6-terra@medium",
     "roles": ("writer", "sections", "reviewer")},
    {"id": "qwen3.7-plus", "spec": "opencode-cli:opencode-go/qwen3.7-plus",
     "roles": ("writer",)},
    {"id": "deepseek-v4-pro", "spec": "opencode-cli:opencode-go/deepseek-v4-pro@high",
     "roles": ("sections",)},
    {"id": "glm-5.2", "spec": "opencode-cli:opencode-go/glm-5.2@high",
     "roles": ("reviewer",)},
    {"id": "gpt-5.6-luna", "spec": "codex-cli:gpt-5.6-luna@medium",
     "roles": ("drafter", "writer")},
    {"id": "claude-sonnet-5", "spec": "claude-cli:claude-sonnet-5@high",
     "roles": ("writer", "sections", "reviewer")},
    {"id": "gpt-5.6-sol", "spec": "codex-cli:gpt-5.6-sol@high",
     "roles": ("reviewer",)},
    {"id": "claude-opus-4.8", "spec": "claude-cli:claude-opus-4-8@high",
     "roles": ("writer", "reviewer")},
    # Sections too: Opus 5 is the candidate to supersede 4.8 outright at the same price,
    # so the trial must cover the hand 4.8 was never granted, not only the one it holds.
    {"id": "claude-opus-5", "spec": "claude-cli:claude-opus-5@high",
     "roles": ("writer", "sections", "reviewer")},
    {"id": "qwen3.7-max", "spec": "opencode-cli:opencode-go/qwen3.7-max",
     "roles": ("reviewer",)},
    {"id": "gemini-3.5-flash-high", "spec": "antigravity-cli:Gemini 3.5 Flash (High)",
     "roles": ROLE_ORDER, "experimental": True},
    {"id": "gemini-3.1-pro-high", "spec": "antigravity-cli:Gemini 3.1 Pro (High)",
     "roles": ROLE_ORDER, "experimental": True},
)


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _json(path, value):
    _write(path, json.dumps(value, indent=2) + "\n")


def _drafter(root):
    _json(root / "drafter" / "brief.json", {
        "audience": "No programming experience",
        "tooling": "external",
        "requiredConcepts": ["variables", "conditions", "loops", "functions", "classes",
                             "game-loop", "movement", "json-save-load"],
        "acceptance": ["launch-window", "move-player", "save-reload"],
    })
    _json(root / "drafter" / "plan.json", {
        "audienceAssumption": "Already knows Python basics",
        "tooling": "internal",
        "teachingOrder": ["classes", "game-loop", "variables", "movement"],
        "acceptance": ["launch-window", "move-player"],
        "verification": ["python3 -m py_compile main.py"],
    })


def _writer(root):
    _json(root / "writer" / "requirements.json", {
        "requiredConcepts": ["variables", "conditions", "loops", "functions", "classes",
                             "dictionaries", "json-files", "game-loop"],
        "scenarios": ["launch-window", "move-player", "save-reload"],
        "lessonLimit": [6, 9],
    })
    _json(root / "writer" / "arc.json", {"lessons": [
        {"id": "player", "teaches": ["classes"], "uses": ["functions", "variables"],
         "scenarios": ["move-player"], "why": "Make a player.", "observable": "It moves."},
        {"id": "loop", "teaches": ["game-loop"], "uses": ["loops", "conditions"],
         "scenarios": ["launch-window"], "why": "Run the game.", "observable": "Window."},
        {"id": "save", "teaches": ["json-files"], "uses": ["dictionaries", "functions"],
         "scenarios": [], "why": "Save it.", "observable": "File."},
    ]})


def _sections(root):
    _write(root / "sections" / "game.py", '''"""Broken miniature learner project."""
import json
import os

SCENARIOS = ("launch-window", "inventory-opens")


def visible_columns(viewport_width, tile_size):
    end = viewport_width / tile_size + 2
    return list(range(0, end))


def inventory_lines(items):
    return draw_inventory(items)


def acceptance():
    return {"version": 1, "status": "PASS",
            "scenarios": {"launch-window": True, "inventory-opens": True}}


if __name__ == "__main__":
    print(json.dumps(acceptance(), sort_keys=True))
''')
    _json(root / "sections" / "lesson.json", {
        "integerDivision": "Use division in the range.",
        "functionDefinition": "Call the helper.",
        "negativeControls": "Return failure for a challenge.",
    })


def _reviewer(root):
    create_reviewer_fixture(root)


def _task_text(roles):
    sections = []
    if "drafter" in roles:
        sections.append("""DRAFTER — repair drafter/plan.json from brief.json. Assume exactly the
stated prior knowledge, preserve the requested external tooling, order every required concept
before its dependents, bind the exact acceptance list, and include both an ordinary no-flag
`python3 main.py` launch and a pytest command in verification.""")
    if "writer" in roles:
        sections.append("""WRITER — replace writer/arc.json with a 6–9 lesson beginner arc.
Every required concept must be taught exactly once before any lesson uses it. Map each requested
scenario exactly once. Every lesson needs a concrete why (35+ chars) and observable (20+ chars).""")
    if "sections" in roles:
        sections.append("""SECTIONS — repair sections/game.py and lesson.json. The visible-column
rule is `range(0, viewport_width // tile_size + 2)`. Implement inventory lines as numbered strings.
Acceptance must exercise those functions, normally PASS both scenarios, and honor
ARCANUM_ACCEPTANCE_CHALLENGE by changing the relevant input so that scenario becomes false and
status becomes FAIL. Teach integer division, defining-before-calling, and negative controls in
clear beginner prose (80+ chars each).""")
    if "reviewer" in roles:
        sections.append("""REVIEWER — perform a production-shaped review-and-repair pass over every
directory under reviewer/candidates, then replace reviewer/findings.json. Each contract names an
authored source of truth, a derived learner project, and its complete command list. Prior green
evidence is untrusted. Inspect behind the first crash, repair every authored root cause, run
replay.py, and rerun every command after the final edit. Never edit a learner-project directly.
Never edit contracts, evidence, replay.py, or tests, and leave genuinely clean authored files
unchanged. Mark broken candidates REPAIRED and clean candidates CLEAN. Record exact command/exit
evidence plus one unique kebab-case repair per root cause with a real authored file, current line,
and causal explanation. Acceptance must exercise public behavior; a negative control changes input
and derives failure instead of assigning the promised result. Partial diagnosis is failure.""")
    return """# Compact Arcanum role trial

This is an editing/debugging task, not a prose questionnaire. Work only in this directory; do not
browse the web or inspect parent/repository files. Finish quickly and spend tokens on the edits.
Do not modify TASK.md, check.py, or any brief/requirements file. For Reviewer, only the authored
repair files permitted by each contract and reviewer/findings.json are writable work. Complete only
the assigned roles below, run `python3 check.py`, repair failures, and end with at most one short
sentence.

""" + "\n\n".join(sections) + "\n"


def _checker(roles):
    role_literal = repr(tuple(roles))
    return f'''#!/usr/bin/env python3
import importlib.util, json, os, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
ROLES = {role_literal}
problems = []
def load(rel):
    try:
        return json.load(open(os.path.join(ROOT, rel), encoding="utf-8"))
    except Exception as exc:
        problems.append(f"{{rel}}: {{exc}}")
        return {{}}
if "drafter" in ROLES:
    brief, plan = load("drafter/brief.json"), load("drafter/plan.json")
    if plan.get("tooling") != brief.get("tooling"): problems.append("drafter: tooling mismatch")
    if plan.get("acceptance") != brief.get("acceptance"): problems.append("drafter: acceptance mismatch")
    if plan.get("teachingOrder") != brief.get("requiredConcepts"): problems.append("drafter: teaching order")
if "writer" in ROLES:
    req, arc = load("writer/requirements.json"), load("writer/arc.json")
    lessons, seen, taught = arc.get("lessons", []), set(), []
    if not (6 <= len(lessons) <= 9): problems.append("writer: needs 6-9 lessons")
    for lesson in lessons:
        if set(lesson.get("uses", [])) - seen: problems.append(f"writer: {{lesson.get('id')}} uses before teaching")
        for concept in lesson.get("teaches", []): taught.append(concept); seen.add(concept)
    if sorted(taught) != sorted(req.get("requiredConcepts", [])): problems.append("writer: concepts missing/duplicated")
if "sections" in ROLES:
    try:
        spec = importlib.util.spec_from_file_location("trial_game", os.path.join(ROOT, "sections/game.py"))
        game = importlib.util.module_from_spec(spec); spec.loader.exec_module(game)
        if game.visible_columns(65, 16) != [0, 1, 2, 3, 4, 5]: problems.append("sections: visible columns")
        if game.inventory_lines(["key", "potion"]) != ["1. key", "2. potion"]: problems.append("sections: inventory")
        for challenge in (None, *game.SCENARIOS):
            if challenge: os.environ["ARCANUM_ACCEPTANCE_CHALLENGE"] = challenge
            else: os.environ.pop("ARCANUM_ACCEPTANCE_CHALLENGE", None)
            report = game.acceptance()
            expected = "FAIL" if challenge else "PASS"
            if report.get("status") != expected: problems.append(f"sections: {{challenge or 'normal'}} status")
            if challenge and report.get("scenarios", {{}}).get(challenge) is not False:
                problems.append(f"sections: {{challenge}} did not become false")
        os.environ.pop("ARCANUM_ACCEPTANCE_CHALLENGE", None)
    except Exception as exc: problems.append(f"sections: runtime {{type(exc).__name__}}: {{exc}}")
if "reviewer" in ROLES:
    report = load("reviewer/findings.json")
    candidates = report.get("candidates", [])
    expected = {repr(CANDIDATE_IDS)}
    if report.get("version") != 3: problems.append("reviewer: version must be 3")
    if [item.get("id") for item in candidates if isinstance(item, dict)] != list(expected):
        problems.append("reviewer: include each candidate once in contract order")
    for item in candidates:
        if not isinstance(item, dict): problems.append("reviewer: candidate entry must be an object"); continue
        if item.get("outcome") not in ("REPAIRED", "CLEAN"): problems.append("reviewer: invalid outcome")
        if not isinstance(item.get("commandsRun"), list): problems.append("reviewer: commandsRun must be a list")
        if not isinstance(item.get("repairs"), list): problems.append("reviewer: repairs must be a list")
        for command in item.get("commandsRun", []):
            if not isinstance(command, dict) or not isinstance(command.get("command"), str) or not isinstance(command.get("exitCode"), int) or not isinstance(command.get("observation"), str):
                problems.append("reviewer: malformed command evidence")
        for repair in item.get("repairs", []):
            if not isinstance(repair, dict) or not all(key in repair for key in ("id", "file", "line", "evidence")):
                problems.append("reviewer: malformed repair")
print("CHECK PASS" if not problems else "CHECK FAIL\\n" + "\\n".join(problems))
sys.exit(bool(problems))
'''


def create_workspace(root, roles):
    """Create one deliberately broken, role-filtered trial and return immutable paths."""
    root = Path(root)
    roles = tuple(role for role in ROLE_ORDER if role in roles)
    root.mkdir(parents=True, exist_ok=True)
    builders = {"drafter": _drafter, "writer": _writer,
                "sections": _sections, "reviewer": _reviewer}
    for role in roles:
        builders[role](root)
    _write(root / "TASK.md", _task_text(roles))
    _write(root / "check.py", _checker(roles))
    immutable = [root / "TASK.md", root / "check.py"]
    if "drafter" in roles:
        immutable.append(root / "drafter" / "brief.json")
    if "writer" in roles:
        immutable.append(root / "writer" / "requirements.json")
    if "reviewer" in roles:
        immutable.extend(reviewer_protected_paths(root))
    return immutable
