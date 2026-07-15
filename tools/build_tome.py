#!/usr/bin/env python3
"""Run one resumable, interactive AI author through an entire tome."""
import argparse
import json
import os
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from buildlib import BUILD_DIR, REPO
from buildlib.author_gate import unit_prompt
from buildlib.checkpoints import ARC_PARTS
from buildlib.prompts import (TOOLING_POLICY, do_gate_json, gate_errors,
                              mastery_contract, write_plan)
from buildlib.phase_reset import capture_phase_snapshot
from buildlib import full_review
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
    assert "exact self-check command" in prompt and "progress marker to `validating`" in prompt
    _mastery_selftest()
    section = {"kind": "section", "phase": 3, "section": "s04", "index": 4, "total": 8}
    assignment = unit_prompt("sample", section)
    assert "Phase 3 section s04 (4/8)" in assignment
    assert "report_section_progress.py" in assignment
    assert "tools/validate_section.py tomes/sample s04" in assignment
    assert "--source-only" in assignment and "do not substitute ad-hoc" in assignment.lower()
    continuation = continuation_prompt("sample")
    assert continuation == "Continue."
    assert _author("codex-cli:gpt-5.6-sol@high") == (
        "codex-cli", "gpt-5.6-sol", "high")
    review = full_review.prompt("sample", "sample")
    assert "THOROUGH FULL-TOME REVIEW" in review
    assert "READ EVERYTHING" in review and "NO SAMPLING" in review
    session = AuthorSession("sample", "claude-cli", "opus", "", "", "both")
    session.session_id = "warm"
    assert not session.apply_author({"author": {"kind": "claude-cli", "model": "opus"}})
    assert session.session_id == "warm"  # same author keeps the resumable session
    assert session.apply_author({"author": {"kind": "codex-cli", "model": "gpt-5.6-sol",
                                            "effort": "high"}})
    assert (session.kind, session.model, session.effort, session.session_id) == (
        "codex-cli", "gpt-5.6-sol", "high", "")
    print("single-author build selftest: OK")


def _mastery_selftest():
    signatures = {
        1: ("safely modify the taught example", "Do not claim independent transfer"),
        2: ("complete familiar task or simple fault repair", "observable results"),
        3: ("at least two graded late transfer performances", "recorded rationale"),
        4: ("incomplete-but-fair requirements", "competing tradeoffs"),
        5: ("substantial architecture problem", "without implementation scaffolding"),
    }
    rendered = {}
    for level, required in signatures.items():
        contract = "\n".join(mastery_contract(level))
        assert f"Finish {level}/5" in contract
        assert f"Mastery evidence {level}/5" in contract
        assert all(text in contract for text in required)
        assert "not contain the exact implementation graded as mastery evidence" in contract
        rendered[level] = contract
    assert len(set(rendered.values())) == 5
    for level, contract in rendered.items():
        assert all(f"Mastery evidence {other}/5" not in contract
                   for other in signatures if other != level)
    assert "Mastery proof" in ARC_PARTS

    # Every legal value across all five dials and all tooling modes must pass the gate.
    for start in range(1, 11):
        for breadth in range(1, 11):
            for depth in range(1, 11):
                for mastery in range(1, 6):
                    for tooling in TOOLING_POLICY:
                        answers = [
                            ("Prior knowledge", "none"),
                            ("Starting level (1-10)", str(start)),
                            ("Breadth (1-10)", str(breadth)),
                            ("Lesson depth (1-10)", str(depth)),
                            ("Mastery (1-5)", str(mastery)),
                            ("Tooling", tooling),
                        ]
                        assert not gate_errors(answers)

    # Generate every Start x Mastery x Tooling plan and verify the selected mastery prompt
    # is present alone while the low-start first-use boundary remains independent of it.
    with tempfile.TemporaryDirectory() as root:
        for start in range(1, 11):
            for mastery in range(1, 6):
                for tooling in TOOLING_POLICY:
                    answers = [
                        ("Prior knowledge", "none"),
                        ("Starting level (1-10)", str(start)),
                        ("Breadth (1-10)", "5"),
                        ("Lesson depth (1-10)", "5"),
                        ("Mastery (1-5)", str(mastery)),
                        ("Tooling", tooling),
                    ]
                    path = os.path.join(root, f"s{start}-m{mastery}-{tooling}.md")
                    write_plan(path, "sample", answers, "Teach a tool")
                    with open(path, encoding="utf-8") as handle:
                        plan = handle.read()
                    assert rendered[mastery] in plan
                    assert all(f"Mastery evidence {other}/5" not in plan
                               for other in signatures if other != mastery)
                    assert ("First-use rule for Start 1–3" in plan) == (start <= 3)


def main():
    if "--selftest" in sys.argv[1:]:
        _selftest()
        return
    parser = argparse.ArgumentParser(description="Build one tome in one persistent AI session")
    parser.add_argument("tome_id")
    parser.add_argument("--author", required=True, type=_author,
                        help="KIND:MODEL[@EFFORT] for the sole author")
    parser.add_argument("--reviewer", type=_author,
                        help="optional KIND:MODEL[@EFFORT] for an exhaustive post-build reviewer")
    parser.add_argument("--gate-json")
    parser.add_argument("--concept", default="")
    parser.add_argument("--from-phase", type=int, default=1, choices=range(1, 9))
    parser.add_argument("--resume-session", default="")
    args = parser.parse_args()

    os.makedirs(BUILD_DIR, exist_ok=True)
    plan = os.path.join(BUILD_DIR, f"{args.tome_id}.plan.md")
    new_build = not os.path.exists(plan)
    if new_build:
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

    if new_build:
        try:
            capture_phase_snapshot(args.tome_id, 1)
        except Exception as exc:
            print(f"phase snapshot warning: {exc}", file=sys.stderr)

    kind, model, effort = args.author
    session = AuthorSession(args.tome_id, kind, model, effort, args.concept,
                            json.loads(args.gate_json).get("tooling", "")
                            if args.gate_json else _tooling(plan),
                            args.from_phase, args.resume_session, args.reviewer)
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
