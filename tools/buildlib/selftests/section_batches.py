"""Regression checks for split Phase-3 checkpoints and bounded batch stopping."""
import json
import os
import shutil
from unittest.mock import patch

from .. import BUILD_DIR, REPO
from .. import sections as sections_module
from ..sections import (_load_sections_done, _mark_section_done, _sections_done_path,
                        section_progress_path, section_progress_shell_command, wipe_sections)


def run():
    os.makedirs(BUILD_DIR, exist_ok=True)
    tid = "selftest-resume-xyz"
    try:
        os.remove(_sections_done_path(tid))
    except OSError:
        pass
    assert _load_sections_done(tid) == set()
    _mark_section_done(tid, "s01")
    _mark_section_done(tid, "s03")
    assert _load_sections_done(tid) == {"s01", "s03"}
    os.remove(_sections_done_path(tid))
    sec = os.path.join(REPO, "tomes", tid, "sections")
    os.makedirs(os.path.join(sec, "s01"))
    _mark_section_done(tid, "s01")
    assert wipe_sections(tid) == 1 and not os.path.exists(sec)
    assert _load_sections_done(tid) == set()
    os.rmdir(os.path.join(REPO, "tomes", tid))
    assert wipe_sections("no-such-tome-xyz") == 0

    # Split Phase 3 keeps one provider process warm across a bounded batch, then
    # checkpoints each section independently. This command shape is runner-neutral:
    # the provider adapter still receives one ordinary headless prompt.
    batch_tid = "selftest-warm-batches-xyz"
    batch_root = os.path.join(REPO, "tomes", batch_tid)
    batch_plan = os.path.join(BUILD_DIR, f"{batch_tid}.plan.md")
    batch_done = _sections_done_path(batch_tid)
    batch_progress = section_progress_path(batch_tid)
    os.makedirs(batch_root, exist_ok=True)
    with open(batch_plan, "w", encoding="utf-8") as handle:
        handle.write("**Artifact lifecycle:** none\n")
    handoff_paths = {sid: os.path.join(BUILD_DIR, f"{batch_tid}-{sid}.json")
                     for sid in ("s01", "s02", "s03", "s04", "s05")}
    for path in handoff_paths.values():
        open(path, "a", encoding="utf-8").close()
    try:
        with (patch.object(sections_module, "section_ids",
                           return_value=["s01", "s02", "s03", "s04", "s05"]),
              patch.object(sections_module, "read_tooling", return_value="internal"),
              patch.object(sections_module, "support_prompt", return_value="author contract"),
              patch.object(sections_module, "prepare_handoff",
                           side_effect=lambda _tid, sid, **_kwargs: handoff_paths[sid]),
              patch.object(sections_module, "validate_handoff", return_value=(False, "stub")),
              patch.object(sections_module, "continuity_prompt",
                           side_effect=lambda _tid, sid, *_args: f"\nCONTINUITY {sid}\n"),
              patch.object(sections_module, "section_validator_shell_command",
                           side_effect=lambda _tid, sid, *_args: f"validate-{sid}"),
              patch.object(sections_module, "section_window_validator_shell_command",
                           side_effect=lambda _tid, sid, *_args: f"window-{sid}"),
              patch.object(sections_module, "build_prompt",
                           side_effect=lambda *_args, validation_command=None, **_kwargs:
                           f"PROMPT {validation_command}\n"),
              patch.object(sections_module, "validate_section", return_value=(True, "clean")),
              patch.object(sections_module, "validate_section_window",
                           return_value=(True, "clean")),
              patch.object(sections_module, "_author_batch", return_value=(0, True)) as worker):
            sections_module.author_sections_split(
                batch_tid, 3, "Sections", [("fake", ["fake"], "stdin")],
                (os.path.relpath(batch_plan, REPO), "verdict", "findings"), {}, {},
                1, 1, None, batch_size=3)
        assert worker.call_count == 2
        assert worker.call_args_list[0].args[3] == ["s01", "s02", "s03"]
        assert worker.call_args_list[1].args[3] == ["s04", "s05"]
        first_prompt = worker.call_args_list[0].args[2]
        assert "(validate-s01) && (validate-s02) && (validate-s03) && (window-s03)" in first_prompt
        assert "CUMULATIVE QUALITY WINDOW THROUGH s03" in first_prompt
        assert "until it exits 0 BEFORE moving to the next section" in first_prompt
        assert "report_section_progress.py" in first_prompt
        assert ('cd "$ARCANUM_REPO_ROOT" && python3 tools/report_active_contract.py '
                'tomes/selftest-warm-batches-xyz --before s01') in first_prompt
        assert ('cd "$ARCANUM_REPO_ROOT" && python3 tools/report_active_contract.py '
                'tomes/selftest-warm-batches-xyz --before s02') in first_prompt
        assert "including an earlier section authored in this same warm batch" in first_prompt
        assert batch_progress in worker.call_args_list[0].args[10]
        assert _load_sections_done(batch_tid) == {"s01", "s02", "s03", "s04", "s05"}
        with open(batch_progress, encoding="utf-8") as handle:
            progress = json.load(handle)
        assert (progress["section"], progress["index"], progress["state"]) == (
            "s05", 5, "complete")
        command = section_progress_shell_command(batch_tid, "s03", 3, 5, "validating", 1, 2)
        assert "s03 3 5 validating --batch 1 --batches 2" in command

        # Clean individual files are not checkpointed and batch 2 is never launched
        # when the cumulative quality window still reports debt.
        os.remove(batch_done)
        with (patch.object(sections_module, "section_ids",
                           return_value=["s01", "s02", "s03", "s04", "s05"]),
              patch.object(sections_module, "read_tooling", return_value="internal"),
              patch.object(sections_module, "support_prompt", return_value="author contract"),
              patch.object(sections_module, "prepare_handoff",
                           side_effect=lambda _tid, sid, **_kwargs: handoff_paths[sid]),
              patch.object(sections_module, "validate_handoff", return_value=(False, "stub")),
              patch.object(sections_module, "continuity_prompt", return_value="\nCONTINUITY\n"),
              patch.object(sections_module, "section_validator_shell_command",
                           side_effect=lambda _tid, sid, *_args: f"validate-{sid}"),
              patch.object(sections_module, "section_window_validator_shell_command",
                           side_effect=lambda _tid, sid, *_args: f"window-{sid}"),
              patch.object(sections_module, "build_prompt", return_value="PROMPT\n"),
              patch.object(sections_module, "validate_section", return_value=(True, "clean")),
              patch.object(sections_module, "validate_section_window",
                           return_value=(False, "ERROR quality-window: thin prose")),
              patch.object(sections_module, "retries_for", return_value=0),
              patch.object(sections_module, "_author_batch", return_value=(0, True)) as blocked):
            try:
                sections_module.author_sections_split(
                    batch_tid, 3, "Sections", [("fake", ["fake"], "stdin")],
                    (os.path.relpath(batch_plan, REPO), "verdict", "findings"), {}, {},
                    1, 1, None, batch_size=3)
                assert False, "a failing quality window advanced to a later batch"
            except SystemExit as exc:
                assert "later batches were not started" in str(exc)
        assert blocked.call_count == 1
        assert _load_sections_done(batch_tid) == set()

        # An exhausted first batch must stop Phase 3 before a later batch starts.
        with (patch.object(sections_module, "section_ids",
                           return_value=["s01", "s02", "s03", "s04", "s05"]),
              patch.object(sections_module, "read_tooling", return_value="internal"),
              patch.object(sections_module, "support_prompt", return_value="author contract"),
              patch.object(sections_module, "prepare_handoff",
                           side_effect=lambda _tid, sid, **_kwargs: handoff_paths[sid]),
              patch.object(sections_module, "validate_handoff", return_value=(False, "stub")),
              patch.object(sections_module, "continuity_prompt", return_value="\nCONTINUITY\n"),
              patch.object(sections_module, "section_validator_shell_command",
                           side_effect=lambda _tid, sid, *_args: f"validate-{sid}"),
              patch.object(sections_module, "build_prompt", return_value="PROMPT\n"),
              patch.object(sections_module, "_author_batch", return_value=(0, False)) as failed):
            try:
                sections_module.author_sections_split(
                    batch_tid, 3, "Sections", [("fake", ["fake"], "stdin")],
                    (os.path.relpath(batch_plan, REPO), "verdict", "findings"), {}, {},
                    1, 1, None, batch_size=3)
                assert False, "an exhausted batch advanced instead of stopping Phase 3"
            except SystemExit as exc:
                assert "later batches were not started" in str(exc)
        assert failed.call_count == 1
    finally:
        shutil.rmtree(batch_root, ignore_errors=True)
        for path in (batch_plan, batch_done, batch_progress, *handoff_paths.values()):
            try:
                os.remove(path)
            except OSError:
                pass
