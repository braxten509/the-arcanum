"""Regression checks for authored-completion and one-worker Phase-3 recovery."""
import os
import shutil
from unittest.mock import patch

from .. import BUILD_DIR
from .. import phase3_runtime as runtime
from .. import sections as sections_module
from ..sections import prepare_whole_tome_warm_worker, section_progress_path
from ..workflow import prepare_phase_writable_paths
from validatelib.phase3 import section_completion_problems


def _complete_section():
    lessons = []
    for number in range(1, 4):
        lessons.append({
            "id": f"s01-l{number:02d}",
            "body": " ".join(f"word{index}" for index in range(180)),
            "teaches": [f"capability-{number}"],
            "exercises": [{"id": f"e{number}-{exercise}"}
                          for exercise in range(1, 5)],
        })
    return {"lessons": lessons, "freestyle": {"requires": ["capability-3"]}}


def run():
    assert runtime.uses_whole_warm_worker(3, False, ["s01", "s02"])
    assert runtime.uses_whole_warm_worker(3, True, ["s01"])
    assert not runtime.uses_whole_warm_worker(3, True, ["s01", "s02"])
    assert not runtime.uses_whole_warm_worker(4, False, ["s01"])

    complete = _complete_section()
    assert not section_completion_problems(complete, "s01")
    thin = _complete_section()
    thin["lessons"] = thin["lessons"][:2]
    assert any("at least 3" in problem for problem in
               section_completion_problems(thin, "s01"))
    placeholder = _complete_section()
    placeholder["lessons"][0]["body"] = "TODO: replace this scaffold"
    assert any("placeholder text" in problem for problem in
               section_completion_problems(placeholder, "s01"))
    placeholder = _complete_section()
    placeholder["freestyle"]["requires"] = ["phase3-placeholder-s01"]
    assert any("Phase-2 placeholder capability" in problem for problem in
               section_completion_problems(placeholder, "s01"))

    # A replacement owns only independently incomplete sections; clean handoffs stay
    # readable through the repository but are not writable in its sandbox.
    tid = "selftest-warm-recovery-xyz"
    ids = ["s01", "s02", "s03", "s04", "s05"]
    handoffs = {sid: os.path.join(BUILD_DIR, f"{tid}-{sid}.json") for sid in ids}
    progress = section_progress_path(tid)
    try:
        with (patch.object(sections_module, "section_ids", return_value=ids),
              patch.object(sections_module, "prepare_handoff",
                           side_effect=lambda _tid, sid, **_kwargs: handoffs[sid]),
              patch.object(sections_module, "section_validator_shell_command",
                           side_effect=lambda _tid, sid, *_args: f"validate-{sid}"),
              patch.object(sections_module, "section_window_validator_shell_command",
                           side_effect=lambda _tid, sid, *_args: f"window-{sid}")):
            prompt, sidecars = prepare_whole_tome_warm_worker(
                tid, ".tome-build/plan.md", "internal", resume=True,
                pending_ids=["s03", "s05"])
        assert "Author or repair only: s03, s05" in prompt
        assert "validate-s03" in prompt and "validate-s05" in prompt
        assert "validate-s01" not in prompt and "validate-s04" not in prompt
        assert sidecars == [handoffs["s03"], handoffs["s05"], progress]
    finally:
        try:
            os.remove(progress)
        except OSError:
            pass

    refs = (".tome-build/plan.md", "verdict", "findings")
    prompt_stub = lambda *_args, repair_only=False, **_kwargs: (
        f"BASE repair_only={repair_only}\n")
    with (patch.object(runtime, "section_ids", return_value=ids),
          patch.object(runtime, "prepare_whole_tome_warm_worker",
                       return_value=("AUTHOR ALL", list(handoffs.values()))),
          patch.object(runtime, "build_prompt", side_effect=prompt_stub) as prompt_builder):
        state = runtime.prepare_warm_phase3_start(
            tid, "Sections", "PHASE BODY", refs, "internal", "ACCESS")
    assert state.pending == ids and state.gate is None and "AUTHOR ALL" in state.prompt
    assert prompt_builder.call_args.kwargs["validation_run"] is False

    with (patch.object(runtime, "section_ids", return_value=ids),
          patch.object(runtime, "phase3_pending_sections", return_value=([], {})),
          patch.object(runtime, "prepare_whole_tome_warm_worker",
                       return_value=("", list(handoffs.values()))),
          patch.object(runtime, "validate_phase3", return_value=(True, "clean")),
          patch.object(runtime, "build_prompt", side_effect=prompt_stub)):
        state = runtime.prepare_warm_phase3_start(
            tid, "Sections", "PHASE BODY", refs, "internal", "ACCESS", resume=True)
    assert state.gate == (True, "clean")
    assert "already clean" in state.notice and not state.pending

    with (patch.object(runtime, "section_ids", return_value=ids),
          patch.object(runtime, "phase3_pending_sections",
                       return_value=(["s03"], {"s03": "incomplete"})),
          patch.object(runtime, "prepare_whole_tome_warm_worker",
                       return_value=("AUTHOR s03", [handoffs["s03"]])),
          patch.object(runtime, "validate_phase3",
                       return_value=(False, "should not run")) as full_gate,
          patch.object(runtime, "build_prompt", side_effect=prompt_stub)):
        state = runtime.prepare_warm_phase3_start(
            tid, "Sections", "PHASE BODY", refs, "internal", "ACCESS", resume=True)
    assert state.pending == ["s03"] and "INCOMPLETE PHASE-3 RESUME" in state.prompt
    assert "repair_only=False" in state.prompt and "AUTHOR s03" in state.prompt
    full_gate.assert_not_called()

    with (patch.object(runtime, "section_ids", return_value=ids),
          patch.object(runtime, "phase3_pending_sections",
                       return_value=(["s03"], {"s03": "incomplete"})),
          patch.object(runtime, "prepare_whole_tome_warm_worker",
                       return_value=("AUTHOR s03", [handoffs["s03"]])),
          patch.object(runtime, "build_prompt", side_effect=prompt_stub)):
        state = runtime.prepare_warm_phase3_recovery(
            tid, "Sections", "PHASE BODY", refs, "internal", "ACCESS", "BLOCKER")
    assert state.pending == ["s03"] and state.body == "PHASE BODY"
    assert "repair_only=False" in state.prompt and "AUTHOR s03" in state.prompt

    with (patch.object(runtime, "section_ids", return_value=ids),
          patch.object(runtime, "phase3_pending_sections", return_value=([], {})),
          patch.object(runtime, "prepare_whole_tome_warm_worker",
                       return_value=("", list(handoffs.values()))),
          patch.object(runtime, "reconciliation_prompt", return_value="RECONCILE"),
          patch.object(runtime, "support_prompt", return_value="RECON BODY"),
          patch.object(runtime, "build_prompt", side_effect=prompt_stub) as prompt_builder):
        state = runtime.prepare_warm_phase3_recovery(
            tid, "Sections", "PHASE BODY", refs, "internal", "ACCESS", "BLOCKER")
    assert not state.pending and state.body == "RECON BODY"
    assert "repair_only=True" in state.prompt and "RECONCILE" in state.prompt
    assert prompt_builder.call_args.kwargs["validation_run"] is True

    scope_root = os.path.join(BUILD_DIR, "selftest-phase3-recovery-scope")
    try:
        for sid in ("s03", "s05"):
            os.makedirs(os.path.join(scope_root, "sections", sid), exist_ok=True)
        writable = prepare_phase_writable_paths(
            3, scope_root, ["handoff-s03.json"], phase3_sections=["s03"])
        assert scope_root not in writable
        assert os.path.join(scope_root, "sections", "s03") in writable
        assert os.path.join(scope_root, "sections", "s05") not in writable
    finally:
        shutil.rmtree(scope_root, ignore_errors=True)
