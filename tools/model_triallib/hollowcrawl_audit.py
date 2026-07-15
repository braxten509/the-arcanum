"""Blind, token-small review case taken from HollowCrawl's real Phase 8 false pass."""
import hashlib
import json
import os
import re
import shutil
from pathlib import Path


CASE_ROOT = Path(__file__).parent / "case_data" / "hollowcrawl_phase8_false_pass"
ORDINARY_COMMAND = "timeout 4s python3 project/main.py"
ACCEPTANCE_COMMAND = "python3 project/main.py --arcanum-acceptance"
COMMANDS = (
    ("ordinary-cold-start", ORDINARY_COMMAND),
    ("acceptance-integrity", ACCEPTANCE_COMMAND),
)

AUDIT_MODELS = (
    {"id": "kimi-k2.6", "spec": "opencode-cli:opencode-go/kimi-k2.6"},
    {"id": "glm-5.2", "spec": "opencode-cli:opencode-go/glm-5.2@high"},
    {"id": "gpt-5.6-terra", "spec": "codex-cli:gpt-5.6-terra@high"},
    {"id": "gpt-5.6-sol", "spec": "codex-cli:gpt-5.6-sol@high"},
    {"id": "gemini-3.5-flash-high", "spec": "antigravity-cli:Gemini 3.5 Flash (High)",
     "comparison": True},
    {"id": "gemini-3.1-pro-high", "spec": "antigravity-cli:Gemini 3.1 Pro (High)",
     "comparison": True},
)


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def baseline_hashes(paths):
    return {str(Path(path).resolve()): _hash(path) for path in paths}


def task_text():
    return f"""# HollowCrawl blind Phase 8 review

This is one brief independent review of the exact learner project from a real completed tome.
The previous reviewer claimed it was clean in `prior-review.json`; that claim is untrusted. Work
only in this directory and do not inspect parent/repository files. Do not browse. Do not repair or
edit the project. Visual styling and the later manual theme redesign are outside this test and
must not be reported.

Review exactly two shipping contracts:

1. An ordinary no-flag cold start must reach usable game behavior without crashing. Run:
   `{ORDINARY_COMMAND}`
2. Acceptance must derive every scenario from the same public/domain behavior the game uses. It
   may inject input, but it may not print or assign promised success. Run:
   `{ACCEPTANCE_COMMAND}`

Inspect the source behind both observations, including beyond the first symptom. Replace
`review.json` with exactly this shape and no extra keys:

```json
{{"version": 1, "outcome": "BLOCKED or CLEAN",
 "commandsRun": [
   {{"id": "ordinary-cold-start", "command": "{ORDINARY_COMMAND}",
    "exitCode": 0, "observation": "what actually happened"}},
   {{"id": "acceptance-integrity", "command": "{ACCEPTANCE_COMMAND}",
    "exitCode": 0, "observation": "what actually happened"}}
 ],
 "findings": [
   {{"id": "unique-kebab-case-root-cause", "file": "project/path.py", "line": 12,
    "commandId": "the affected command id", "evidence": "specific causal explanation"}}
 ]}}
```

Use one finding per independently repairable root cause, cite the causal source line rather than a
downstream stack-frame symptom, and do not duplicate a cause. CLEAN requires zero findings. Run
both commands yourself; supplied exit codes are schema examples, not expected results. Finish
quickly and return at most one short sentence after writing the file.
"""


def create_workspace(root):
    """Copy the frozen real artifact and return every immutable trial input."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(CASE_ROOT / "project", root / "project", dirs_exist_ok=True)
    shutil.copy2(CASE_ROOT / "prior-review.json", root / "prior-review.json")
    shutil.copy2(CASE_ROOT / "ORIGIN.md", root / "ORIGIN.md")
    _write(root / "TASK.md", task_text())
    _write(root / "review.json", "{}\n")
    return immutable_paths(root)


def immutable_paths(root):
    root = Path(root)
    paths = [root / "TASK.md", root / "prior-review.json", root / "ORIGIN.md"]
    paths.extend(sorted((root / "project").rglob("*.py")))
    return paths


def _read_report(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(value, dict):
            return value, None
        return {}, "report is not an object"
    except (OSError, ValueError) as exc:
        return {}, str(exc)


def _immutable(baseline):
    changed = [raw for raw, digest in baseline.items()
               if not Path(raw).is_file() or _hash(raw) != digest]
    return not changed, ", ".join(Path(item).name for item in changed) or "unchanged"


def _finding_shape(item):
    return (isinstance(item, dict)
            and set(item) == {"id", "file", "line", "commandId", "evidence"}
            and isinstance(item.get("id"), str)
            and bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", item["id"]))
            and isinstance(item.get("file"), str)
            and isinstance(item.get("line"), int) and not isinstance(item.get("line"), bool)
            and isinstance(item.get("commandId"), str)
            and isinstance(item.get("evidence"), str)
            and len(item["evidence"].strip()) >= 35)


def _has_crash_finding(findings):
    for item in findings:
        text = str(item.get("evidence") or "").lower()
        source = ((item.get("file") == "project/game/tilemap.py"
                   and 64 <= item.get("line", 0) <= 76)
                  or (item.get("file") == "project/game/camera.py"
                      and 10 <= item.get("line", 0) <= 14)
                  or (item.get("file") == "project/game/player.py"
                      and 39 <= item.get("line", 0) <= 45))
        if (source
                and item.get("commandId") == "ordinary-cold-start"
                and "range" in text
                and any(word in text for word in ("float", "integer", "typeerror"))
                and any(word in text for word in ("camera", "bound", "start_", "end_"))):
            return True
    return False


def _has_acceptance_finding(findings):
    for item in findings:
        text = str(item.get("evidence") or "").lower()
        if (item.get("file") == "project/main.py"
                and 18 <= item.get("line", 0) <= 20
                and item.get("commandId") == "acceptance-integrity"
                and any(word in text for word in (
                    "constant", "hard-coded", "hardcoded", "literal", "unconditional",
                    "assigned", "promised success", "prints a full pass"))
                and any(word in text for word in (
                    "derive", "exercise", "behavior", "execute", "testing", "game logic",
                    "scenario", "running"))):
            return True
    return False


def _has_missing_import_finding(findings):
    for item in findings:
        text = str(item.get("evidence") or "").lower()
        if (item.get("file") == "project/main.py"
                and item.get("line") in (10, 329)
                and item.get("commandId") == "ordinary-cold-start"
                and "draw_inventory" in text
                and any(word in text for word in ("import", "nameerror", "undefined", "not defined"))):
            return True
    return False


def grade_workspace(root, baseline):
    root = Path(root)
    report, report_error = _read_report(root / "review.json")
    commands = report.get("commandsRun") if isinstance(report, dict) else None
    commands = commands if isinstance(commands, list) else []
    findings = report.get("findings") if isinstance(report, dict) else None
    findings = findings if isinstance(findings, list) else []
    expected_commands = [
        {"id": item_id, "command": command}
        for item_id, command in COMMANDS
    ]
    command_shape = (len(commands) == 2 and all(
        isinstance(item, dict)
        and set(item) == {"id", "command", "exitCode", "observation"}
        and item.get("id") == expected["id"]
        and item.get("command") == expected["command"]
        and isinstance(item.get("exitCode"), int) and not isinstance(item.get("exitCode"), bool)
        and isinstance(item.get("observation"), str)
        and len(item["observation"].strip()) >= 8
        for item, expected in zip(commands, expected_commands)))
    truthful_commands = (command_shape and commands[0]["exitCode"] == 1
                         and commands[1]["exitCode"] == 0
                         and "typeerror" in commands[0]["observation"].lower()
                         and "pass" in commands[1]["observation"].lower())
    finding_shape = (len(findings) == 3 and len({item.get("id") for item in findings
                                                 if isinstance(item, dict)}) == 3
                     and all(_finding_shape(item) for item in findings))
    all_text = json.dumps(report, sort_keys=True).lower()
    checks = [
        ("protected real artifact", *_immutable(baseline)),
        ("exact report schema", not report_error and set(report) == {
            "version", "outcome", "commandsRun", "findings"} and report.get("version") == 1,
         report_error or repr(sorted(report))),
        ("truthful two-command ledger", truthful_commands, repr(commands)),
        ("blocked with three unique root causes", report.get("outcome") == "BLOCKED"
         and finding_shape, repr([item.get("id") for item in findings
                                  if isinstance(item, dict)])),
        ("ordinary cold-start root cause", _has_crash_finding(findings),
         "tilemap float bounds passed to range"),
        ("counterfeit acceptance root cause", _has_acceptance_finding(findings),
         "main.py literal PASS does not execute behavior"),
        ("latent missing inventory renderer import", _has_missing_import_finding(findings),
         "main.py calls draw_inventory without importing it"),
        ("no out-of-scope theme finding", not any(word in all_text for word in (
            "theme", "parchment", "paper", "skin", "visual styling")),
         "theme excluded from model and harness evidence"),
    ]
    passed = sum(bool(item[1]) for item in checks)
    return {"passed": passed == len(checks), "score": passed, "maximum": len(checks),
            "criticalFailures": [name for name, ok, _ in checks if not ok],
            "checks": [{"name": name, "passed": bool(ok), "detail": detail}
                       for name, ok, detail in checks]}
