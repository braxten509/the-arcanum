"""One harness-owned author workflow with warm repairs and clean-unit session resets."""
from __future__ import annotations

import math
import os
import queue
import sys
import threading
import traceback

from .. import BUILD_DIR, REPO, brief_exception
from ..ai_costs import api_equivalent_completion_cost
from ..course.state import tree_digest
from .gate import (advance_unit, context, continue_prompt, current_unit, ensure_unit,
                          label, mark_unit_validating, next_prompt, preflight_unit,
                          repair_prompt, report_completed_unit_cost, unit_prompt,
                          validate_author_self_check, validate_unit,
                          validation_failure_message, validation_issue_count)
from . import full_review
from .scope import previous_section_id, profile_paths
from ..measure import (ValidatorInfrastructureError, validate_live_smoke,
                       validate_shipping)
from ..planning_review import (is_contract_conflict_report,
                               is_planning_contract_cycle_report)
from .review_session import ReviewerSessionMixin
from .scope import author_hidden_paths, author_paths
from .session.controls import AuthorControlsMixin
from .session.phase_state import PhaseAuthorStateMixin
from .session.recovery import (MAX_CODEX_FRESH_SESSION_RECOVERIES,
                               MAX_CODEX_PATCH_RECOVERIES,
                               codex_fresh_session_recovery_prompt,
                               codex_patch_recovery_prompt,
                               recoverable_codex_resume_failure,
                               recoverable_codex_patch_failure)
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


def section_repair_limit_reached(cost, *, hard_cost=2.0):
    """Return true only when a section reaches its configured dollar limit."""
    return bool(
        hard_cost is not None
        and cost
        and float(cost.get("apiEquivalentUsd") or 0) >= float(hard_cost)
    )


def configured_section_cost_limit(build_id, claude_author=False):
    """Read the Forge's persisted base limit; Claude receives the declared 2x allowance."""
    path = os.path.join(BUILD_DIR, f"{build_id}.launch.json")
    try:
        import json
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle).get("sectionCostLimitUsd", 2.0)
    except (OSError, ValueError):
        raw = 2.0
    if raw is None or (
            isinstance(raw, str)
            and raw.strip().lower() in {"unlimited", "no-limit", "no limit", "none"}):
        return None
    try:
        base = float(raw)
    except (TypeError, ValueError):
        base = 2.0
    if not math.isfinite(base) or base <= 0:
        base = 2.0
    return base * (2.0 if claude_author else 1.0)


class AuthorSession(AuthorControlsMixin, PhaseAuthorStateMixin,
                    ReviewerSessionMixin, AuthorTurnMixin):
    def __init__(self, build_id, kind, model, effort, concept, tooling, from_phase=1,
                 resume_id="", reviewer=None, phase_authors=None):
        self.build_id, self.kind, self.model = build_id, kind, model
        self.effort, self.concept, self.tooling = effort, concept, tooling
        self.from_phase, self.session_id = from_phase, str(resume_id or "")
        if self.kind == "opencode-cli" and self.session_id:
            # The lifecycle normally filters orphan IDs before launch, but a web server
            # that predates a sandbox migration can still pass one to a new worker.
            # Recheck against the actual unit database at the last responsible boundary.
            from arcanum.platform.agent_scratch import provider_session_exists
            unit = current_unit(self.build_id, self.from_phase) or {
                "kind": "phase", "phase": self.from_phase}
            if not provider_session_exists(
                    "opencode", self.build_id, "author",
                    int(unit.get("phase") or self.from_phase),
                    str(unit.get("section") or ""), self.session_id):
                self.session_id = ""
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

    def _hidden(self):
        return author_hidden_paths(self.build_id)

    def _permission_paths(self):
        unit = current_unit(self.build_id, self.from_phase) or {
            "kind": "phase", "phase": self.from_phase}
        phase = int(unit.get("phase") or self.from_phase)
        name = "author-phase12" if phase <= 2 else "author-phase37" if phase <= 7 else "author-phase8"
        return profile_paths(name, build_id=self.build_id, tome_id=self.current_tome(), phase=phase,
                             section_id=str(unit.get("section") or ""),
                             previous_section_id=previous_section_id(self.build_id, unit),
                             section_index=str(unit.get("index") or ""),
                             section_count=str(unit.get("total") or ""),
                             tooling=self.tooling)

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
            "validating handoff. This is a no-progress repair cycle. No further author turn was "
            "started. Reconcile "
            "the validator contract or authored state, then resume this same unit.")
        append_conversation(self.build_id, "harness", message)
        self.state("paused", gate="author-no-progress-cycle", error=message)
        notify("\u2717 Tome repair cycle paused",
               f"{self.current_tome()}: {label(unit)} repeated an authored state.",
               priority=1)
        return self.await_controls(retrying=True)

    def pause_for_section_repair_limit(self, unit, report, failures, cost):
        """Require an explicit operator decision before another runaway repair turn."""
        amount = (f"${cost['displayUsd']:.2f}" if cost else "unpriced/unknown")
        message = (f"{label(unit)} paused at {amount} after {failures} failed "
                   f"validation{'s' if failures != 1 else ''}. Choose an AI to retry.")
        append_conversation(
            self.build_id, "harness",
            message + "\n\nLatest validator report:\n\n"
            + str(report or "validator failed")[-12000:])
        self.state("paused", gate="section-repair-budget", error=message,
                   repairFailures=failures,
                   sectionCostUsd=(cost or {}).get("displayUsd"))
        notify("✗ Section repair budget paused",
               f"{self.current_tome()}: {label(unit)} needs an explicit repair decision.",
               priority=1)
        return self.await_validation_controls()

    def pause_for_planning_stall(self, unit, report):
        message = (
            f"{label(unit)} paused at a repeated planning-contract state. No author or "
            "alternate-AI retry was started. Reconcile the harness/validator contract, then "
            "resume this same validation gate without an author turn.")
        append_conversation(
            self.build_id, "harness", message + "\n\nLatest validator report:\n\n"
            + str(report or "validator failed")[-12000:])
        self.state("paused", gate="planning-contract-stall", error=message)
        notify("✗ Planning contract paused",
               f"{self.current_tome()}: {label(unit)} needs harness/validator reconciliation.",
               priority=1)
        return self.await_validation_controls()

    def pause_for_planning_contract_conflict(self, unit, report):
        """Keep an impossible sealed-plan finding away from the Phase-2 author."""
        message = (
            f"{label(unit)} paused because the Validator AI found an irreconcilable sealed "
            "Phase-1 contract. No author or alternate-AI retry was started. Repair or rewind "
            "the planning contract, then resume this same validation gate without an author turn.")
        append_conversation(
            self.build_id, "harness", message + "\n\nValidator report:\n\n"
            + str(report or "contract conflict")[-12000:])
        self.state("paused", gate="planning-contract-conflict", error=message)
        notify("✗ Sealed planning contract paused",
               f"{self.current_tome()}: {label(unit)} requires planning-contract repair.",
               priority=1)
        return self.await_validation_controls()


    def run(self):
        from .session.orchestration import run_author_session
        return run_author_session(self, globals())
