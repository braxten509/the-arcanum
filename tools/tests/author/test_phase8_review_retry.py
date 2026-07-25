#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""Phase 8 stays warm; an optional exhaustive reviewer starts only after it clears."""
import json
import os
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
    assert session.run_reviewer() == 0
    assert (session.role, session.kind, session.model, session.session_id) == (
        "reviewer", "codex-cli", "gpt-5.6-sol", "")

    # The per-section sweep is a gate in its own right: a defect it alone can see --
    # answer-position clustering inside one section -- must block completion even
    # when the pooled tome-wide pass and every other check are clean.
    session.stop = False
    review_session.validate_every_section = lambda *_args: (
        False, "section s01:\nERROR anti-template: mc answers never land on index [3]")
    assert session.run_reviewer() == 130
finally:
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

print("same-session Phase 8 plus optional exhaustive review: OK")
