#!/usr/bin/env python3
"""Run one resumable, interactive AI author through an entire tome."""
import argparse
import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from buildlib import BUILD_DIR, REPO
from buildlib.author_gate import unit_prompt
from buildlib.prompts import do_gate_json
from buildlib.single_author import AuthorSession, author_prompt, continuation_prompt


def _author(value):
    kind, separator, rest = str(value or "").partition(":")
    model, effort_separator, effort = rest.rpartition("@")
    if not separator:
        raise argparse.ArgumentTypeError("author must be KIND:MODEL[@EFFORT]")
    if not effort_separator:
        model, effort = rest, ""
    if kind not in ("claude-cli", "antigravity-cli", "codex-cli", "opencode-cli") or not model:
        raise argparse.ArgumentTypeError("author must name one defined agent CLI and model")
    return kind, model, effort


def _selftest():
    prompt = author_prompt("sample", "Teach a tool", "both", 3)
    assert "sole author" in prompt and "through Phase 8" in prompt
    assert "START OR RESUME AT PHASE: 3" in prompt
    assert "Do not run validators" in prompt and "progress marker to `validating`" in prompt
    section = {"kind": "section", "phase": 3, "section": "s04", "index": 4, "total": 8}
    assert "Phase 3 section s04 (4/8)" in unit_prompt(section)
    assert "report_section_progress.py" in unit_prompt(section)
    continuation = continuation_prompt("sample")
    assert continuation == "Continue."
    assert _author("codex-cli:gpt-5.6-sol@high") == (
        "codex-cli", "gpt-5.6-sol", "high")
    print("single-author build selftest: OK")


def main():
    if "--selftest" in sys.argv[1:]:
        _selftest()
        return
    parser = argparse.ArgumentParser(description="Build one tome in one persistent AI session")
    parser.add_argument("tome_id")
    parser.add_argument("--author", required=True, type=_author,
                        help="KIND:MODEL[@EFFORT] for the sole author")
    parser.add_argument("--gate-json")
    parser.add_argument("--concept", default="")
    parser.add_argument("--from-phase", type=int, default=1, choices=range(1, 9))
    parser.add_argument("--resume-session", default="")
    args = parser.parse_args()

    os.makedirs(BUILD_DIR, exist_ok=True)
    plan = os.path.join(BUILD_DIR, f"{args.tome_id}.plan.md")
    if not os.path.exists(plan):
        if not args.gate_json:
            parser.error("a new tome needs --gate-json")
        do_gate_json(plan, args.tome_id, args.gate_json, args.concept)
        tome = os.path.join(REPO, "tomes", args.tome_id)
        if not os.path.isdir(tome):
            result = subprocess.run(
                [sys.executable, os.path.join(REPO, "tools", "new_tome.py"), args.tome_id],
                cwd=REPO)
            if result.returncode:
                raise SystemExit("could not create the initial tome scaffold")
    elif not args.concept:
        try:
            launch = json.load(open(os.path.join(BUILD_DIR, f"{args.tome_id}.launch.json"),
                                    encoding="utf-8"))
            args.concept = str(launch.get("concept") or "")
        except (OSError, ValueError):
            pass

    kind, model, effort = args.author
    session = AuthorSession(args.tome_id, kind, model, effort, args.concept,
                            json.loads(args.gate_json).get("tooling", "")
                            if args.gate_json else _tooling(plan),
                            args.from_phase, args.resume_session)
    raise SystemExit(session.run())


def _tooling(plan):
    import re
    try:
        text = open(plan, encoding="utf-8").read()
    except OSError:
        return ""
    match = re.search(r"(?im)^- \*\*Tooling:\*\*\s*(internal|external|both)\s*$", text)
    return match.group(1).lower() if match else ""


if __name__ == "__main__":
    main()
