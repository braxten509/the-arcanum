#!/usr/bin/env python3
"""Run resumable, phase-routed AI authors through one harness-owned tome build."""
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
from buildlib.single_author.gate import unit_prompt
from buildlib.workflow.checkpoints import ARC_PARTS
from buildlib.workflow.prompts import (MASTERY_DEPTH_FLOORS, START_PACING, TOOLING_POLICY,
                              calibration_contract, do_gate_json, gate_errors,
                              learner_construction_contract, mastery_contract, write_plan)
from buildlib.workflow.phase_reset import capture_phase_snapshot
from buildlib.single_author import full_review
from buildlib.single_author import AuthorSession, author_prompt, continuation_prompt


def _agent(value, allowed, role):
    kind, separator, rest = str(value or "").partition(":")
    model, effort_separator, effort = rest.rpartition("@")
    if not separator:
        raise argparse.ArgumentTypeError(f"{role} must be KIND:MODEL[@EFFORT]")
    if not effort_separator:
        model, effort = rest, ""
    if kind not in allowed or not model:
        raise argparse.ArgumentTypeError(
            f"{role} must use one of {', '.join(allowed)} and name a model")
    return kind, model, effort


def _author(value):
    return _agent(value, ("claude-cli", "codex-cli"), "author")


def _validator(value):
    return _agent(value, ("claude-cli", "codex-cli", "openai-api"), "validator")


def _persist_validator(build_id, spec, gate_json=None):
    """Keep direct CLI launches on the same Validator AI contract as the Bindery."""
    path = os.path.join(BUILD_DIR, f"{build_id}.launch.json")
    try:
        with open(path, encoding="utf-8") as handle:
            launch = json.load(handle)
    except (OSError, ValueError):
        launch = {}
    launch["validator"] = {"kind": spec[0], "model": spec[1], "effort": spec[2]}
    if gate_json and not launch.get("gate"):
        launch["gate"] = json.loads(gate_json)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(launch, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
    os.replace(temp, path)


def _selftest():
    prompt = author_prompt("sample", "Teach a tool", "both", 3)
    assert "active unit author" in prompt and "reaches Phase 8" in prompt
    assert "START OR RESUME AT PHASE: 3" in prompt
    assert "exact mechanical checks" in prompt and "progress marker to `validating`" in prompt
    assert "NON-NEGOTIABLE LEARNER CONSTRUCTION" in prompt
    assert "Every canonical project artifact must be created or assembled by the learner" in prompt
    _mastery_selftest()
    section = {"kind": "section", "phase": 3, "section": "s04", "index": 4, "total": 8}
    assignment = unit_prompt("sample", section)
    assert "Phase 3 section s04 (4/8)" in assignment
    assert "report_section_progress.py" in assignment
    assert "tools/validate_section.py" in assignment
    assert "ALWAYS run every listed command" in assignment
    assert "Make each section's learner-visible Working the canonical project assignment" in assignment
    assert "Omit lesson artifactSteps normally" in assignment
    continuation = continuation_prompt("sample")
    assert continuation == "Continue."
    assert _author("codex-cli:gpt-5.6-sol@high") == (
        "codex-cli", "gpt-5.6-sol", "high")
    assert _validator("openai-api:gpt-5.6-luna@medium") == (
        "openai-api", "gpt-5.6-luna", "medium")
    try:
        _author("opencode-cli:openrouter/example")
        raise AssertionError("OpenCode must not be accepted for tome authoring")
    except argparse.ArgumentTypeError:
        pass
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
    routed = AuthorSession("sample", "claude-cli", "arc", "high", "", "both", 1,
                           phase_authors={"phase12": ("claude-cli", "arc", "high"),
                                          "phase37": ("codex-cli", "sections", "medium"),
                                          "phase8": ("codex-cli", "review", "max")})
    assert routed.phase_author(2) == ("claude-cli", "arc", "high")
    assert routed.phase_author(3) == ("codex-cli", "sections", "medium")
    assert routed.phase_author(8) == ("codex-cli", "review", "max")
    routed.session_id = "phase-1-planning"
    assert not routed.activate_unit_author(
        {"kind": "phase", "phase": 1}, {"kind": "phase", "phase": 2})
    assert routed.session_id == "phase-1-planning"
    assert routed.activate_unit_author(
        {"kind": "phase", "phase": 2},
        {"kind": "section", "phase": 3, "section": "s01"})
    assert routed.session_id == ""
    print("single-author build selftest: OK")


def _mastery_selftest():
    signatures = {
        1: ("requested project from scratch", "Project completion alone is not evidence"),
        2: ("familiar language task", "language-level fault repair"),
        3: ("at least two graded late language-transfer performances", "language choice"),
        4: ("late language performances", "competing language tradeoffs"),
        5: ("substantial language architecture problem", "without implementation scaffolding"),
    }
    rendered = {}
    for level, required in signatures.items():
        contract = "\n".join(mastery_contract(level))
        assert f"Finish {level}/5" in contract
        assert f"Mastery evidence {level}/5" in contract
        assert all(text in contract for text in required)
        assert "Language mastery contract:** 1" in contract
        assert "Language practice contract:** 1" in contract
        assert "Language foundation contract:** 2" in contract
        assert all(role in contract for role in
                   ("data", "control", "decomposition", "failure handling", "verification"))
        if level == 1:
            assert "project is primary" in contract and "bare minimum" in contract
        elif level == 2:
            assert "project is primary" in contract and "general areas" in contract
        else:
            assert "Language mastery is the primary product" in contract
            assert "structured abstraction, modularity" in contract
        assert "Language-through-project rule" in contract
        assert "The learner creates or assembles every canonical project structure" in contract
        assert "Each section's learner-visible Working is the ordinary" in contract
        assert "never learner ownership of the canonical artifact" in contract
        rendered[level] = contract
    assert len(set(rendered.values())) == 5
    for level, contract in rendered.items():
        assert all(f"Mastery evidence {other}/5" not in contract
                   for other in signatures if other != level)
    assert "Mastery proof" in ARC_PARTS
    construction = "\n".join(learner_construction_contract())
    assert "blank editor file or unavoidable behavior-free tool metadata" in construction
    assert "production-ready stub" in construction
    assert "media remains learner-sourced rather than bundled" in construction
    assert "identifiers, values, and problem shape differ" in construction
    assert "complete replayable non-media answer only in hidden referenceSteps" in construction

    # Every legal value across all five dials and all tooling modes must pass the gate.
    for start in range(1, 11):
        for project_scope in range(1, 6):
            for mastery in range(1, 6):
                for depth in range(MASTERY_DEPTH_FLOORS[mastery], 11):
                    for tooling in TOOLING_POLICY:
                        answers = [
                            ("Prior knowledge", "none"),
                            ("Starting level (1-10)", str(start)),
                            ("Project scope (1-5)", str(project_scope)),
                            ("Lesson depth (1-10)", str(depth)),
                            ("Mastery (1-5)", str(mastery)),
                            ("Tooling", tooling),
                        ]
                        assert not gate_errors(answers)

    # The slider-selected Starting Level is sufficient; free-text prior knowledge is optional.
    blank_prior = [
        ("Prior knowledge", ""),
        ("Starting level (1-10)", "5"),
        ("Project scope (1-5)", "3"),
        ("Lesson depth (1-10)", "7"),
        ("Mastery (1-5)", "3"),
        ("Tooling", "internal"),
    ]
    assert not gate_errors(blank_prior)
    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, "blank-prior.md")
        write_plan(path, "blank-prior", blank_prior, "Teach a tool")
        with open(path, encoding="utf-8") as handle:
            plan = handle.read()
        assert "Prior knowledge:** Not specified; use Starting level as the sole entry baseline." in plan

    minimum_path = calibration_contract([
        ("Prior knowledge", ""),
        ("Starting level (1-10)", "1"),
        ("Project scope (1-5)", "3"),
        ("Lesson depth (1-10)", "5"),
        ("Mastery (1-5)", "1"),
        ("Tooling", "external"),
    ])
    assert "Mastery-1 minimum-path budget" in minimum_path
    assert "no more than 8 sections" in minimum_path
    assert "Starting Level alone never creates another project section" in minimum_path

    # Generate every Start x Mastery x Tooling plan and verify the selected mastery prompt
    # is present alone while the low-start first-use boundary remains independent of it.
    with tempfile.TemporaryDirectory() as root:
        for start in range(1, 11):
            for mastery in range(1, 6):
                for tooling in TOOLING_POLICY:
                    answers = [
                        ("Prior knowledge", "none"),
                        ("Starting level (1-10)", str(start)),
                        ("Project scope (1-5)", "3"),
                        ("Lesson depth (1-10)", str(MASTERY_DEPTH_FLOORS[mastery])),
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
                    assert ("Lesson pacing" in plan) == (start <= 3)
                    if start <= 3:
                        title, summary = START_PACING[start]
                        assert f"Lesson pacing {start}/3 — {title}" in plan
                        assert summary in plan
                        assert "Pacing/depth separation" in plan
                        assert all(START_PACING[other][1] not in plan
                                   for other in START_PACING if other != start)


def main():
    if "--selftest" in sys.argv[1:]:
        _selftest()
        return
    parser = argparse.ArgumentParser(
        description="Build one tome with persistent, phase-routed AI sessions")
    parser.add_argument("tome_id")
    parser.add_argument("--author", required=True, type=_author,
                        help="KIND:MODEL[@EFFORT] for the author active at launch")
    parser.add_argument("--phase-1-2-author", type=_author)
    parser.add_argument("--phase-3-7-author", type=_author)
    parser.add_argument("--phase-8-author", type=_author)
    parser.add_argument("--validator", required=True, type=_validator,
                        help="mandatory KIND:MODEL[@EFFORT] post-section validator AI")
    parser.add_argument("--reviewer", type=_author,
                        help="optional KIND:MODEL[@EFFORT] for an exhaustive post-build reviewer")
    parser.add_argument("--gate-json")
    parser.add_argument("--concept", default="")
    parser.add_argument("--from-phase", type=int, default=1, choices=range(1, 9))
    parser.add_argument("--resume-session", default="")
    args = parser.parse_args()
    # Child validators use this stable launch slug for their durable Forge history.
    os.environ["ARCANUM_BUILD_ID"] = args.tome_id

    os.makedirs(BUILD_DIR, exist_ok=True)
    plan = os.path.join(BUILD_DIR, f"{args.tome_id}.plan.md")
    new_build = not os.path.exists(plan)
    if new_build:
        if not args.gate_json:
            parser.error("a new tome needs --gate-json")
        do_gate_json(plan, args.tome_id, args.gate_json, args.concept)
        tome = os.path.join(REPO, "tomes", args.tome_id)
        if not os.path.isdir(tome):
            gate = json.loads(args.gate_json)
            result = subprocess.run(
                [sys.executable, os.path.join(REPO, "tools", "new_tome.py"), args.tome_id,
                 "--sections", "2", "--mastery", str(gate["mastery"])],
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

    _persist_validator(args.tome_id, args.validator, args.gate_json)
    kind, model, effort = args.author
    phase_authors = {
        "phase12": args.phase_1_2_author or args.author,
        "phase37": args.phase_3_7_author or args.author,
        "phase8": args.phase_8_author or args.author,
    }
    session = AuthorSession(args.tome_id, kind, model, effort, args.concept,
                            json.loads(args.gate_json).get("tooling", "")
                            if args.gate_json else _tooling(plan),
                            args.from_phase, args.resume_session, args.reviewer, phase_authors)
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
