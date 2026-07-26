#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""Phase 8 stays warm; an optional exhaustive reviewer starts only after it clears."""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.buildlib import single_author  # noqa: E402
from tools.buildlib.single_author import full_review  # noqa: E402
from tools.buildlib.single_author import review_session  # noqa: E402
from tools.buildlib.single_author import AuthorSession, _resume_command, author_prompt  # noqa: E402


prompt = author_prompt("example", "Teach a tool", "both", 8)
assert "active unit author" in prompt and "spawn another author or reviewer" in prompt
assert "harness will start it only after your final" in prompt
for kind, model in (("codex-cli", "gpt-5.6-sol"),
                    ("claude-cli", "claude-opus-4-8"),
                    ("opencode-cli", "opencode-go/minimax-m3"),
                    ("antigravity-cli", "Gemini 3.1 Pro (High)")):
    _display, command, _mode = _resume_command(kind, model, "", "session-123", "repair")
    assert "session-123" in command

with tempfile.TemporaryDirectory() as root:
    tome = os.path.join(root, "tomes", "demo")
    build = os.path.join(root, ".tome-build")
    os.makedirs(os.path.join(tome, "sections")); os.makedirs(build)
    for rel, content in (("tome.toml", "[meta]\nid='demo'\n"),
                         ("sections/s01.json", "{}\n")):
        with open(os.path.join(tome, rel), "w", encoding="utf-8") as handle:
            handle.write(content)
    old_repo, old_build, old_runtime = full_review.REPO, full_review.BUILD_DIR, full_review.selected_runtime_config
    try:
        full_review.REPO, full_review.BUILD_DIR = root, build
        full_review.selected_runtime_config = lambda _tid: None
        review_prompt = full_review.prompt("demo", "demo")
        assert "THOROUGH FULL-TOME REVIEW" in review_prompt
        assert "READ EVERYTHING" in review_prompt and "NO SAMPLING" in review_prompt
        assert "Seed only a blank editor file" in review_prompt
        assert "rename-equivalent solution is a blocking finding" in review_prompt
        files = full_review.inventory("demo")
        with open(full_review.evidence_path("demo"), "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "reviewMode": "thorough-full-tome", "sampling": False,
                       "filesReviewed": files, "findings": [], "unresolvedFindings": [],
                       "summary": "Every authored file was reviewed in full."}, handle)
        assert full_review.validate_report("demo", "demo")[0]
        report = json.load(open(full_review.evidence_path("demo"), encoding="utf-8"))
        report["filesReviewed"] = files[:-1]
        with open(full_review.evidence_path("demo"), "w", encoding="utf-8") as handle:
            json.dump(report, handle)
        assert not full_review.validate_report("demo", "demo")[0]
    finally:
        full_review.REPO, full_review.BUILD_DIR = old_repo, old_build
        full_review.selected_runtime_config = old_runtime

session = AuthorSession("demo", "claude-cli", "opus", "", "", "both",
                        reviewer=("codex-cli", "gpt-5.6-sol", "high"))
session._review_turn = lambda *_args, **_kwargs: ("complete", "")
session.state = lambda *_args, **_kwargs: None

# Every mechanical gate can be clean and the tome still not be fit for a stranger, so
# the build ends on an independent survey against publisher.md. These stand in for it.
survey_dir = tempfile.mkdtemp()
verdicts, survey_prompts, repair_prompts = [], [], []


def fake_report_path(tid):
    path = os.path.join(survey_dir, f"{tid}-{len(survey_prompts)}.md")
    open(path, "w", encoding="utf-8").close()
    return os.path.relpath(path, survey_dir), path


def fake_survey_turn(prompt, report_abs, _tid, _kind, _text):
    survey_prompts.append(prompt)
    with open(report_abs, "w", encoding="utf-8") as handle:
        handle.write(verdicts.pop(0))
    return "complete", ""


session._survey_turn = fake_survey_turn
old_report_path, old_metadata = review_session.report_path, review_session.save_review_metadata
review_session.report_path = fake_report_path
review_session.save_review_metadata = lambda *_args, **_kwargs: None
old_review_prompt = review_session.review_prompt


def spy_review_prompt(build_id, tid, repair_report=""):
    if repair_report:
        repair_prompts.append(repair_report)
    return old_review_prompt(build_id, tid, repair_report)


review_session.review_prompt = spy_review_prompt
old_report = full_review.validate_report
old_shipping, old_smoke, old_context = (review_session.validate_shipping,
                                        review_session.validate_live_smoke,
                                        review_session.context)
old_sections, old_append = (review_session.validate_every_section,
                            review_session.append_conversation)
old_adopt = review_session.adopt_build
try:
    full_review.validate_report = lambda *_args: (True, "complete inventory")
    review_session.validate_report = lambda *_args: (True, "complete inventory")
    review_session.validate_shipping = lambda *_args: (True, "strict clean")
    review_session.validate_every_section = lambda *_args: (True, "")
    review_session.validate_live_smoke = lambda *_args: (True, "smoke clean")
    review_session.context = lambda _bid: {"tooling": "both", "plan": ".tome-build/demo.plan.md"}
    review_session.append_conversation = lambda *_args, **_kwargs: None
    review_session.adopt_build = lambda *_args: []
    verdicts[:] = ["## Blockers\n\n- none\n\nPUBLISH VERDICT: READY\n"]
    assert session.run_reviewer() == 0
    assert (session.role, session.kind, session.model, session.session_id) == (
        "reviewer", "codex-cli", "gpt-5.6-sol", "")
    # A clean mechanical sweep must not be the last word: the survey ran, and it was
    # told the bar to measure against and the exact line it has to end on.
    assert len(survey_prompts) == 1 and "publisher.md" in survey_prompts[0]
    assert "PUBLISH VERDICT: READY" in survey_prompts[0]
    assert "SURVEY turn of round 1 of at most 3" in survey_prompts[0]

    # NOT READY hands the survey's blockers to the reviewer and buys another round;
    # a tome that never converges stops for a person instead of looping on the money.
    session.stop = False
    survey_prompts.clear()
    verdicts[:] = [f"## Blockers\n\n- s0{n} lesson {n} teaches nothing\n\n"
                   f"PUBLISH VERDICT: NOT READY\n" for n in (1, 2, 3)]
    assert session.run_reviewer() == 130
    assert len(survey_prompts) == review_session.PUBLICATION_PASSES
    assert len(repair_prompts) == review_session.PUBLICATION_PASSES - 1
    assert "s01 lesson 1 teaches nothing" in repair_prompts[0]
    assert "`## Polish (not blocking)` section is not" in repair_prompts[0]
    # Round 2's survey is told a repair pass already answered round 1, or it re-raises
    # everything the reviewer declined with a reason and the loop never ends.
    assert "settled" in survey_prompts[1]
    assert not verdicts, "every survey round must actually run"

    # The per-section sweep is a gate in its own right: a defect it alone can see --
    # answer-position clustering inside one section -- must block completion even
    # when the pooled tome-wide pass and every other check are clean. It fails before
    # the survey, so no survey turn is paid for.
    session.stop = False
    survey_prompts.clear()
    review_session.validate_every_section = lambda *_args: (
        False, "section s01:\nERROR anti-template: mc answers never land on index [3]")
    assert session.run_reviewer() == 130
    assert not survey_prompts, "a failing gate must not buy a publication survey"
finally:
    review_session.report_path, review_session.save_review_metadata = (
        old_report_path, old_metadata)
    review_session.review_prompt = old_review_prompt
    full_review.validate_report = old_report
    review_session.validate_report = old_report
    review_session.validate_shipping, review_session.validate_live_smoke = old_shipping, old_smoke
    review_session.validate_every_section = old_sections
    review_session.context = old_context
    review_session.append_conversation = old_append
    review_session.adopt_build = old_adopt
    # run_reviewer truncates its evidence packet in the real build dir; the demo
    # build id is not one, so take the file back off disk.
    try:
        os.remove(full_review.evidence_path("demo"))
    except OSError:
        pass


# The survey's verdict is only worth anything because it CANNOT touch what it grades:
# a fresh provider session, no read scope inherited from the author profile, and exactly
# one writable file. Anything less and the repairer is marking its own homework.
scoped = AuthorSession("demo", "claude-cli", "opus", "", "", "both")
scoped.session_id = "reviewer-session-1"
seen = {}
scoped_report = os.path.join(survey_dir, "scope.md")
open(scoped_report, "w", encoding="utf-8").close()


def capture_turn(*_args, **_kwargs):
    seen.update(writable=scoped._writable(), readonly=scoped._readonly(),
                session=scoped.session_id, write=scoped._permission_paths()["write"],
                read=scoped._permission_paths()["read"])
    return "complete", ""


scoped.run_turn = capture_turn
assert scoped._survey_turn("p", scoped_report, "demo", "harness", "") == ("complete", "")
assert seen["writable"] == [scoped_report] and seen["write"] == [scoped_report]
assert seen["readonly"] == [], "the survey must not inherit the author's read scope"
assert seen["session"] == "", "a survey continuing the repair session is not independent"
assert scoped.session_id == "reviewer-session-1", "the reviewer's own session must survive"
assert any(path.endswith("/publisher.md") for path in seen["read"]), \
    "a survey that cannot read the bar invents one"

shutil.rmtree(survey_dir, ignore_errors=True)
print("same-session Phase 8, exhaustive review, and publication survey: OK")
