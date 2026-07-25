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
from .gate import (advance_unit, continue_prompt, current_unit, ensure_unit, label,
                   mark_unit_validating, next_prompt, preflight_unit, repair_prompt,
                   report_completed_unit_cost, unit_prompt, validate_author_self_check,
                   validate_unit, validation_failure_message)
from .prompts.continuation import interrupted_prompt
from .validation_messages import validation_issue_count
from .blocked import validate_author_blocked_check
from . import full_review
from .scope import previous_section_id, profile_paths
from ..measure import ValidatorInfrastructureError
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
                              author_prompt, continuation_prompt, json_path,
                              load_conversation as _load_conversation)
# Re-exported for tools/build_tome.py --selftest and the author gate tests.
from .runtime import opencode_output_session_id as _opencode_output_session_id
from .runtime import resume_command as _resume_command
from .runtime import runner_stdin as _runner_stdin
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
                 resume_id="", reviewer=None, phase_authors=None, resumed_build=False):
        self.build_id, self.kind, self.model = build_id, kind, model
        self.effort, self.concept, self.tooling = effort, concept, tooling
        self.from_phase, self.session_id = from_phase, str(resume_id or "")
        self.resumed_build = bool(resumed_build)
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
        if self.session_id:
            conversation_text = f"Resuming {label(unit)} in the existing author session."
        elif self.resumed_build:
            conversation_text = f"Restarting {label(unit)} in a new author session."
        else:
            conversation_text = f"Assigned {label(unit)}."
        deferred_message, deferred_switch = "", False
        nonvalidating_states = {}
        section_repair_failures = {}
        section_budget_warned = set()
        section_budget_acked = {}
        planning_failure_states = {}
        codex_patch_recoveries = {}
        codex_fresh_session_recoveries = {}

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

        def enforce_section_budget(target_unit, report=""):
            """Stop a runaway section on money. Return true to end the run.

            Cost accrues on every author turn, but this used to be consulted
            only after a *failed* validation. A section that never reaches the
            gate -- a harness-blocked loop, a no-progress repair cycle -- spent
            past its limit unwatched. It is now checked before each author turn
            as well, and one acknowledged pause buys exactly one more turn.
            """
            nonlocal deferred_message, deferred_switch
            if target_unit.get("kind") != "section":
                return False
            unit_key = ("section", int(target_unit.get("phase") or 0),
                        str(target_unit.get("section") or ""))
            cost = api_equivalent_completion_cost(
                BUILD_DIR, self.build_id, phase=3,
                section=target_unit.get("section"))
            claude_author = self.kind == "claude-cli"
            hard_override = os.environ.get(
                "ARCANUM_CLAUDE_SECTION_COST_LIMIT_USD" if claude_author
                else "ARCANUM_SECTION_COST_LIMIT_USD")
            if hard_override is None:
                hard_cost = configured_section_cost_limit(self.build_id, claude_author)
            elif hard_override.strip().lower() in {
                    "unlimited", "no-limit", "no limit", "none"}:
                hard_cost = None
            else:
                hard_cost = float(hard_override)
            if hard_cost is None:
                return False
            spent = float((cost or {}).get("apiEquivalentUsd") or 0)
            warn_cost = float(os.environ.get(
                "ARCANUM_CLAUDE_SECTION_COST_WARN_USD" if claude_author
                else "ARCANUM_SECTION_COST_WARN_USD", str(hard_cost * 0.75)))
            if cost and spent >= warn_cost and unit_key not in section_budget_warned:
                section_budget_warned.add(unit_key)
                warning = (f"SECTION COST WARNING › {label(target_unit)} › "
                           f"${cost['displayUsd']:.2f} API-equivalent; this section "
                           f"pauses for an operator decision at ${hard_cost:.2f}.")
                print(warning, flush=True)
                append_conversation(self.build_id, "harness", warning)
            if not section_repair_limit_reached(cost, hard_cost=hard_cost):
                return False
            if spent <= section_budget_acked.get(unit_key, -1.0):
                return False    # already paid for: the operator bought this turn
            resumed = self.pause_for_section_repair_limit(
                target_unit, report, section_repair_failures.get(unit_key, 0), cost)
            if resumed is None:
                return True
            message, switched = resumed
            section_budget_acked[unit_key] = spent
            section_repair_failures[unit_key] = 0
            deferred_message = "\n\n".join(
                part for part in (deferred_message, message) if part)
            deferred_switch = deferred_switch or switched
            return False

        def pause_if_planning_stuck(target_unit, report):
            """Pause only a repeated no-progress planning loop; never enforce money limits."""
            nonlocal deferred_message, deferred_switch
            phase = int(target_unit.get("phase") or 0)
            if target_unit.get("kind") != "phase" or phase not in (1, 2):
                return False
            unit_key = ("phase", phase, "")
            fingerprint = _author_state_fingerprint(self._writable())
            report_text = str(report or "validator failed").strip()
            prior = planning_failure_states.get(unit_key, {})
            report_repeats = (int(prior.get("reportRepeats") or 0) + 1
                              if prior.get("report") == report_text else 1)
            unchanged = bool(prior and prior.get("fingerprint") == fingerprint)
            fingerprint_counts = dict(prior.get("fingerprintCounts") or {})
            fingerprint_counts[fingerprint] = fingerprint_counts.get(fingerprint, 0) + 1
            repeated_state = fingerprint_counts[fingerprint] >= 2
            planning_failure_states[unit_key] = {
                "fingerprint": fingerprint,
                "fingerprintCounts": fingerprint_counts,
                "report": report_text,
                "reportRepeats": report_repeats,
            }
            if unchanged or repeated_state or report_repeats >= 3:
                resumed = self.pause_for_planning_stall(target_unit, report)
                if resumed is None:
                    return True
                message, switched = resumed
                planning_failure_states.pop(unit_key, None)
                deferred_message = "\n\n".join(
                    part for part in (deferred_message, message) if part)
                deferred_switch = deferred_switch or switched
            return False

        while not self.stop:
            if not validate_first:
                unit = ensure_unit(self.build_id, self.from_phase)
                if enforce_section_budget(unit):
                    break
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
                resumed_session_id = self.session_id
                outcome, message = self.run_turn(prompt, conversation_kind, conversation_text)
                unit_key = (unit.get("kind"), int(unit.get("phase") or 0),
                            str(unit.get("section") or ""))
                patch_failure = recoverable_codex_patch_failure(
                    self.kind, self.role, self.session_id, message)
                resume_failure = recoverable_codex_resume_failure(
                    self.kind, self.role, resumed_session_id, message)
                if outcome == "failed" and patch_failure:
                    recoveries = codex_patch_recoveries.get(unit_key, 0) + 1
                    codex_patch_recoveries[unit_key] = recoveries
                    if recoveries <= MAX_CODEX_PATCH_RECOVERIES:
                        prompt = codex_patch_recovery_prompt(label(unit))
                        conversation_kind, conversation_text = "harness", (
                            f"Codex rejected a malformed author patch before applying it. "
                            f"Automatically resuming the same {label(unit)} author session "
                            f"(tool recovery {recoveries}/{MAX_CODEX_PATCH_RECOVERIES}).")
                        continue
                elif outcome == "failed" and resume_failure:
                    recoveries = codex_fresh_session_recoveries.get(unit_key, 0) + 1
                    codex_fresh_session_recoveries[unit_key] = recoveries
                    if recoveries <= MAX_CODEX_FRESH_SESSION_RECOVERIES:
                        self.session_id = ""
                        self.actual_model = ""
                        prompt = (
                            author_prompt(
                                self.build_id, self.concept, self.tooling,
                                unit.get("phase", self.from_phase))
                            + "\n\n"
                            + codex_fresh_session_recovery_prompt(label(unit))
                            + "\n\n"
                            + prompt
                        )
                        conversation_kind, conversation_text = "harness", (
                            f"The saved Codex author session exited before producing output. "
                            f"Automatically retrying the same {label(unit)} with {self.model} "
                            "in one fresh session; authored files and the complete repair packet "
                            "are preserved.")
                        continue
                elif outcome != "failed":
                    codex_patch_recoveries.pop(unit_key, None)
                    codex_fresh_session_recoveries.pop(unit_key, None)
                if outcome == "authentication-required":
                    auth_message = (
                        f"{label(unit)} paused before starting another author turn because "
                        f"{self.kind} has no usable headless credential.\n\n{message}"
                    )
                    append_conversation(self.build_id, "harness", auth_message)
                    self.state("paused", gate="author-authentication", error=auth_message)
                    notify(
                        "✗ Author authentication required",
                        f"{self.current_tome()}: configure {self.kind}, then resume.",
                        priority=1,
                    )
                    resumed = self.await_validation_controls()
                    if resumed is None:
                        break
                    resumed_message, switched = resumed
                    if resumed_message:
                        prompt = resumed_message + "\n\n" + prompt
                        conversation_kind, conversation_text = "user", resumed_message
                    else:
                        conversation_kind, conversation_text = "harness", (
                            f"Retrying {label(unit)} after author authentication was restored.")
                    if switched:
                        prompt = (
                            author_prompt(
                                self.build_id, self.concept, self.tooling,
                                unit.get("phase", self.from_phase))
                            + "\n\n" + prompt
                        )
                    continue
                if outcome == "stopped":
                    break
                if outcome == "message":
                    unit = ensure_unit(self.build_id, self.from_phase)
                    prompt = interrupted_prompt(message, unit)
                    conversation_kind, conversation_text = "user", message
                    continue
                if outcome in ("harness-blocked", "repair-required"):
                    unit = (current_unit(self.build_id, self.from_phase,
                                         require_gate=True)
                            or ensure_unit(self.build_id, self.from_phase))
                    self_check_ok = None
                    self_check_report = ""
                    ready_unit = None
                    # Never trust a provider-authored infrastructure label. HARNESS_BLOCKED
                    # must name its command, and the harness reproduces that exact command.
                    # HARNESS_REPAIR_REQUIRED remains the self-check-only compatibility path.
                    while self_check_ok is None and not self.stop:
                        try:
                            if outcome == "harness-blocked":
                                check_kind, self_check_ok, self_check_report = (
                                    validate_author_blocked_check(
                                        self.build_id, unit, message))
                                if check_kind == "self-check":
                                    self_check_ok, self_check_report = (
                                        validate_author_self_check(self.build_id, unit))
                            else:
                                check_kind = "self-check"
                                self_check_ok, self_check_report = validate_author_self_check(
                                    self.build_id, unit)
                            if check_kind == "bootstrap" and self_check_ok:
                                break
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
                    if check_kind == "bootstrap":
                        prompt = (
                            f"Continue the exact {label(unit)} assignment already active in this "
                            "session. The harness reproduced the named bootstrap command and it is "
                            "now clean. Preserve current work and context; do not rerun that bootstrap "
                            "command or restart discovery."
                        )
                        conversation_kind, conversation_text = "harness", (
                            f"The harness reproduced the exact author-reported bootstrap command "
                            f"for {label(unit)} and it is now clean. Continuing the same unit "
                            "without regenerating its initial context.")
                        prompt, conversation_kind, conversation_text = decorate_deferred(
                            prompt, unit, conversation_kind, conversation_text)
                        continue
                    if self_check_ok:
                        unit = ready_unit
                        append_conversation(
                            self.build_id, "harness",
                            f"The independently reproduced self-check for {label(unit)} is clean. "
                            "The harness marked it validating and will run the authoritative gate "
                            "without another author turn.")
                        validate_first = True
                        continue
                    if pause_if_planning_stuck(unit, self_check_report):
                        break
                    prompt = repair_prompt(self.build_id, unit, self_check_report)
                    claimed = ("reported HARNESS_REPAIR_REQUIRED"
                               if outcome == "repair-required" else
                               "reported HARNESS_BLOCKED; the exact named mechanical check "
                               "returned authored findings")
                    conversation_kind, conversation_text = "harness", (
                        f"The author {claimed} for {label(unit)}. Structured authored findings "
                        "were aggregated and returned to the same author session. "
                        f"({validation_issue_count(self_check_report)} issues found)")
                    prompt, conversation_kind, conversation_text = decorate_deferred(
                        prompt, unit, conversation_kind, conversation_text)
                    continue
                if outcome in ("paused", "failed"):
                    if outcome == "failed":
                        error = (
                            "The author CLI repeatedly emitted malformed patches and exhausted "
                            "automatic same-session recovery. Resume it, or pick another AI to "
                            "take over in a fresh session."
                            if patch_failure else
                            "The author CLI exited unexpectedly. Resume it, or pick another AI "
                            "to take over in a fresh session.")
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
                    # A section normally reaches here once between its all-lessons batch and its
                    # Working/assessment batch. The fingerprint check still catches an actual
                    # stall or an interrupted batch that makes no further progress.
                    prompt = continue_prompt(self.build_id, unit)
                    conversation_kind, conversation_text = "harness", (
                        f"{label(unit)} is not finished; returning it to the same author session."
                        if unit.get("kind") == "section" else
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
                unit_key = (unit.get("kind"), int(unit.get("phase") or 0),
                            str(unit.get("section") or ""))
                phase = int(unit.get("phase") or 0)
                if (unit.get("kind") == "phase" and phase in (1, 2)
                        and is_planning_contract_cycle_report(report)):
                    resumed = self.pause_for_planning_stall(unit, report)
                    if resumed is None:
                        break
                    message, switched = resumed
                    deferred_message = "\n\n".join(
                        part for part in (deferred_message, message) if part)
                    deferred_switch = deferred_switch or switched
                    validate_first = True
                    continue
                if (unit.get("kind") == "phase" and phase == 2
                        and is_contract_conflict_report(report)):
                    resumed = self.pause_for_planning_contract_conflict(unit, report)
                    if resumed is None:
                        break
                    message, switched = resumed
                    deferred_message = "\n\n".join(
                        part for part in (deferred_message, message) if part)
                    deferred_switch = deferred_switch or switched
                    validate_first = True
                    continue
                if pause_if_planning_stuck(unit, report):
                    break
                if unit.get("kind") == "section":
                    section_repair_failures[unit_key] = (
                        section_repair_failures.get(unit_key, 0) + 1)
                if enforce_section_budget(unit, report):
                    break
                prompt = repair_prompt(self.build_id, unit, report)
                conversation_kind, conversation_text = (
                    "harness", validation_failure_message(unit, report))
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
