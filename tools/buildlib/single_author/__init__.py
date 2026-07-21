"""One harness-owned author workflow with warm repairs and clean-unit session resets."""
from __future__ import annotations

import os
import queue
import sys
import threading
import traceback

from .. import BUILD_DIR, REPO, brief_exception
from ..course.state import tree_digest
from .gate import (advance_unit, context, current_unit, ensure_unit, label,
                          mark_unit_validating, next_prompt, preflight_unit,
                          repair_prompt, report_completed_unit_cost, unit_prompt,
                          validate_author_self_check, validate_unit)
from . import full_review
from ..measure import (ValidatorInfrastructureError, validate_live_smoke,
                       validate_shipping)
from .review_session import ReviewerSessionMixin
from .scope import author_paths
from .session.controls import AuthorControlsMixin
from .session.phase_state import PhaseAuthorStateMixin
from .session.turn import AuthorTurnMixin
from .session.turn import authoritative_session_id as _authoritative_session_id
from .session.support import (append_conversation as _append_conversation,
                                     author_prompt, continuation_prompt,
                                     harness_blocked_message as _harness_blocked_message,
                                     json_path, load_conversation as _load_conversation)
from .runtime import assistant_text as _assistant_text
from .runtime import initial_runner as _initial_runner
from .runtime import opencode_output_session_id as _opencode_output_session_id
from .runtime import resume_command as _resume_command
from .runtime import runner_stdin as _runner_stdin
from .runtime import session_id_from_line as _session_id_from_line
from .runtime import usage_from_line as _usage_from_line
from arcanum.forge import notify
from arcanum.catalog.build_ids import resolve_working_id


def append_conversation(build_id, kind, text, **extra):
    return _append_conversation(BUILD_DIR, build_id, kind, text, **extra)


def load_conversation(build_id, limit=120):
    return _load_conversation(BUILD_DIR, build_id, limit)


def _author_state_fingerprint(paths):
    """Hash only author-writable content, excluding logs and session metadata."""
    return tuple(
        (os.path.abspath(path), tree_digest(path))
        for path in sorted(set(paths))
        if os.path.exists(path)
    )


class AuthorSession(AuthorControlsMixin, PhaseAuthorStateMixin,
                    ReviewerSessionMixin, AuthorTurnMixin):
    def __init__(self, build_id, kind, model, effort, concept, tooling, from_phase=1,
                 resume_id="", reviewer=None, phase_authors=None):
        self.build_id, self.kind, self.model = build_id, kind, model
        self.effort, self.concept, self.tooling = effort, concept, tooling
        self.from_phase, self.session_id = from_phase, resume_id
        self.configure_phase_authors(kind, model, effort, phase_authors)
        self.reviewer = reviewer
        self.role = "author"
        self.active_unit = None
        self.actual_model = ""
        self.state_path = json_path(BUILD_DIR, build_id, "session")
        self.control_input = sys.stdin
        self.controls, self.child, self.stop = queue.Queue(), None, False

    def _writable(self):
        unit = current_unit(self.build_id, self.from_phase) or {
            "kind": "phase", "phase": self.from_phase}
        return author_paths(self.build_id, self.from_phase, self.current_tome(), unit)[0]

    def _readonly(self):
        unit = current_unit(self.build_id, self.from_phase) or {
            "kind": "phase", "phase": self.from_phase}
        return author_paths(self.build_id, self.from_phase, self.current_tome(), unit)[1]

    def current_tome(self):
        try:
            with open(os.path.join(BUILD_DIR, f"{self.build_id}.plan.md"), encoding="utf-8") as handle:
                return resolve_working_id(
                    self.build_id, handle.read(), os.path.join(REPO, "tomes"))
        except OSError:
            return self.build_id

    def pause_for_validation_infrastructure(self, unit, exc):
        """Surface a harness-owned failure and wait; the author cannot repair it."""
        # subprocess errors stringify their whole argv, and the validator prompt is one of
        # those arguments: several KB of evidence packet burying the one useful clause.
        detail = brief_exception(exc)
        print("HARNESS VALIDATION INFRASTRUCTURE FAILURE", flush=True)
        if sys.exc_info()[0] is not None:
            traceback.print_exc()
        else:
            print(detail, flush=True)
        message = (
            f"Harness validation could not run for {label(unit)}. No author retry was "
            "started. Repair the validator infrastructure, then resume to retry the "
            f"same mechanical gate without an author turn.\n\n{detail[-6000:]}")
        append_conversation(self.build_id, "harness", message)
        self.state("paused", gate="validator-infrastructure", error=message)
        notify("\u2717 Tome validator needs repair",
               f"{self.current_tome()}: {label(unit)} is paused before another author call.",
               priority=1)
        return self.await_validation_controls()

    def pause_for_author_cycle(self, unit):
        """Stop a repeated no-handoff file state before paying for another turn."""
        message = (
            f"The harness detected a repeated authored-file state for {label(unit)} without a "
            "validating handoff. This is a no-progress repair cycle, commonly caused by "
            "contradictory self-check findings. No further author turn was started. Reconcile "
            "the validator contract or authored state, then resume this same unit.")
        append_conversation(self.build_id, "harness", message)
        self.state("paused", gate="author-no-progress-cycle", error=message)
        notify("\u2717 Tome repair cycle paused",
               f"{self.current_tome()}: {label(unit)} repeated an authored state.",
               priority=1)
        return self.await_controls(retrying=True)

    def run(self):
        threading.Thread(target=self.read_controls, daemon=True).start()
        unit = ensure_unit(self.build_id, self.from_phase)
        self.active_unit = unit
        # A restarted harness must honor a durable `validating` handoff before it
        # invokes the provider.  This recovers the current unit without paying the
        # author to repeat work that is already on disk.
        validate_first = current_unit(
            self.build_id, self.from_phase, require_gate=True) is not None
        assignment = unit_prompt(self.build_id, unit)
        prompt = (assignment if self.session_id else
                  author_prompt(self.build_id, self.concept, self.tooling, self.from_phase)
                  + "\n\n" + assignment)
        conversation_kind = "harness"
        conversation_text = f"Assigned {label(unit)}. The harness will validate when the author stops."
        deferred_message, deferred_switch = "", False
        nonvalidating_states = {}

        def decorate_deferred(base_prompt, target_unit, default_kind, default_text):
            nonlocal deferred_message, deferred_switch
            next_kind, next_text = default_kind, default_text
            if deferred_message:
                base_prompt = deferred_message + "\n\n" + base_prompt
                next_kind, next_text = "user", deferred_message
            if deferred_switch:
                base_prompt = (author_prompt(
                    self.build_id, self.concept, self.tooling,
                    target_unit.get("phase", self.from_phase))
                    + "\n\n" + base_prompt)
                if not deferred_message:
                    next_text = (f"Resuming {label(target_unit)} with {self.kind} "
                                 f"{self.model} in a fresh session.")
            deferred_message, deferred_switch = "", False
            return base_prompt, next_kind, next_text

        while not self.stop:
            if not validate_first:
                unit = ensure_unit(self.build_id, self.from_phase)
                try:
                    preflight_unit(self.build_id, unit)
                except Exception as exc:
                    resumed = self.pause_for_validation_infrastructure(unit, exc)
                    if resumed is None:
                        break
                    message, switched = resumed
                    deferred_message = "\n\n".join(
                        part for part in (deferred_message, message) if part)
                    deferred_switch = deferred_switch or switched
                    continue
                prompt, conversation_kind, conversation_text = decorate_deferred(
                    prompt, unit, conversation_kind, conversation_text)
                outcome, message = self.run_turn(prompt, conversation_kind, conversation_text)
                if outcome == "stopped":
                    break
                if outcome == "message":
                    unit = ensure_unit(self.build_id, self.from_phase)
                    prompt = message + "\n\n" + unit_prompt(self.build_id, unit)
                    conversation_kind, conversation_text = "user", message
                    continue
                if outcome == "harness-blocked":
                    unit = (current_unit(self.build_id, self.from_phase,
                                         require_gate=True)
                            or ensure_unit(self.build_id, self.from_phase))
                    self_check_ok = None
                    self_check_report = ""
                    ready_unit = None
                    # Never trust a provider-authored infrastructure label. Reproduce
                    # the exact deterministic self-check first; structured findings go
                    # back as authored repairs, while genuine crashes pause and re-probe
                    # mechanically after resume before any further paid author call.
                    while self_check_ok is None and not self.stop:
                        try:
                            self_check_ok, self_check_report = validate_author_self_check(
                                self.build_id, unit)
                            if self_check_ok:
                                ready_unit = mark_unit_validating(self.build_id, unit)
                                if not ready_unit:
                                    raise ValidatorInfrastructureError(
                                        "author self-check handoff",
                                        "clean self-check did not produce a validating marker")
                        except Exception as exc:
                            self_check_ok = None
                            resumed = self.pause_for_validation_infrastructure(unit, exc)
                            if resumed is None:
                                break
                            resumed_message, switched = resumed
                            deferred_message = "\n\n".join(
                                part for part in (deferred_message, resumed_message) if part)
                            deferred_switch = deferred_switch or switched
                    if self_check_ok is None:
                        break
                    if self_check_ok:
                        unit = ready_unit
                        append_conversation(
                            self.build_id, "harness",
                            f"The independently reproduced self-check for {label(unit)} is clean. "
                            "The harness marked it validating and will run the authoritative gate "
                            "without another author turn.")
                        validate_first = True
                        continue
                    prompt = repair_prompt(self.build_id, unit, self_check_report)
                    conversation_kind, conversation_text = "harness", (
                        f"The author reported HARNESS_BLOCKED for {label(unit)}, but the "
                        "independently reproduced self-check returned structured authored "
                        "findings. The report was returned to the same author session.")
                    prompt, conversation_kind, conversation_text = decorate_deferred(
                        prompt, unit, conversation_kind, conversation_text)
                    continue
                if outcome in ("paused", "failed"):
                    if outcome == "failed":
                        error = ("The author CLI exited unexpectedly. Resume it, or pick "
                                 "another AI to take over in a fresh session.")
                        self.state("paused", error=error)
                        # The recovery bar states the failure; the conversation is where the
                        # run is read back later, so the crash belongs in the transcript too —
                        # with whatever the CLI said on its way out.
                        append_conversation(self.build_id, "harness", "\n\n".join(
                            part for part in (error, message) if part))
                        notify("✗ Author AI failed",
                               f"{self.current_tome()}: {self.kind} {self.model} crashed. "
                               "Open its forge session to retry or switch AI.", priority=1)
                    else:
                        self.state("paused")
                    resumed = self.await_controls(retrying=outcome == "failed")
                    if resumed is None:
                        break
                    prompt, conversation_kind, conversation_text = resumed
                    continue
                unit = current_unit(self.build_id, self.from_phase, require_gate=True)
                if not unit:
                    unit = ensure_unit(self.build_id, self.from_phase)
                    unit_key = (unit.get("kind"), int(unit.get("phase") or 0),
                                str(unit.get("section") or ""))
                    fingerprint = _author_state_fingerprint(self._writable())
                    seen = nonvalidating_states.setdefault(unit_key, set())
                    if fingerprint in seen:
                        resumed = self.pause_for_author_cycle(unit)
                        seen.clear()
                        if resumed is None:
                            break
                        prompt, conversation_kind, conversation_text = resumed
                        continue
                    seen.add(fingerprint)
                    prompt = (f"You stopped before handing off {label(unit)}. Finish only that unit, "
                              "run its assigned exact self-check, set its progress marker to "
                              "validating, and stop.\n\n" + unit_prompt(self.build_id, unit))
                    conversation_kind, conversation_text = "harness", (
                        f"{label(unit)} was not marked validating; returning it to the same author session.")
                    continue
                nonvalidating_states.pop(
                    (unit.get("kind"), int(unit.get("phase") or 0),
                     str(unit.get("section") or "")), None)
            else:
                unit = current_unit(self.build_id, self.from_phase, require_gate=True)
                if not unit:
                    validate_first = False
                    continue
                validate_first = False
            self.state("validating", unit=label(unit))
            try:
                ok, report = validate_unit(self.build_id, unit)
            except Exception as exc:
                resumed = self.pause_for_validation_infrastructure(unit, exc)
                if resumed is None:
                    break
                message, switched = resumed
                deferred_message = "\n\n".join(
                    part for part in (deferred_message, message) if part)
                deferred_switch = deferred_switch or switched
                validate_first = True
                continue
            if not ok:
                prompt = repair_prompt(self.build_id, unit, report)
                conversation_kind, conversation_text = "harness", (
                    f"Validation failed for {label(unit)}. The report was returned to the same author session.")
                prompt, conversation_kind, conversation_text = decorate_deferred(
                    prompt, unit, conversation_kind, conversation_text)
                continue
            defer_phase8_cost = (unit.get("kind") == "phase"
                                 and int(unit.get("phase") or 0) == 8)
            if not defer_phase8_cost:
                # Report before advancing the durable marker. If the harness dies
                # on this boundary, resume revalidates and replaces the same scoped
                # line instead of permanently skipping the completed unit's cost.
                report_completed_unit_cost(self.build_id, unit)
            next_unit = advance_unit(self.build_id, unit)
            if next_unit is None:
                append_conversation(self.build_id, "harness",
                                    f"Validation passed for {label(unit)}. All eight phases are clean.")
                reviewer_result = self.run_reviewer()
                if reviewer_result:
                    self.state("stopped")
                    return reviewer_result
                report_completed_unit_cost(self.build_id, unit)
                self.state("complete")
                return 0
            prompt = next_prompt(self.build_id, unit, next_unit, report)
            reset = self.activate_unit_author(unit, next_unit)
            conversation_kind, conversation_text = "harness", (
                f"Validation passed for {label(unit)}. Continuing with {label(next_unit)}"
                + (f" using {self.kind} {self.model} in a fresh unit session."
                   if reset else " in the shared Phase 1–2 planning session."))
            unit = next_unit
            self.active_unit = next_unit
            if reset:
                # Persist the empty session id before launching the successor. A
                # harness crash in this narrow boundary must not let resume attach
                # the old unit's expensive context to the new unit.
                self.state("starting", unit=label(next_unit), boundary="fresh-unit")
                prompt = (author_prompt(self.build_id, self.concept, self.tooling,
                                        next_unit.get("phase", self.from_phase))
                          + "\n\n" + prompt)
            prompt, conversation_kind, conversation_text = decorate_deferred(
                prompt, unit, conversation_kind, conversation_text)
        self.state("stopped")
        return 130
