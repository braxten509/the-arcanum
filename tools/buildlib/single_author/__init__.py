"""One harness-owned author workflow with warm repairs and clean-unit session resets."""
from __future__ import annotations

import os
import queue
import signal
import subprocess
import sys
import threading
import time
import traceback

from .. import BUILD_DIR, REPO
from ..ai_costs import ensure_cost_totals, record_ai_turn
from ..runtime.agent_runtime import scoped_runner_command
from .gate import (advance_unit, context, current_unit, ensure_unit, label,
                          next_prompt, preflight_unit, repair_prompt, unit_prompt,
                          validate_unit)
from . import full_review
from ..measure import (ValidatorInfrastructureError, validate_live_smoke,
                       validate_shipping)
from .review_session import ReviewerSessionMixin
from .scope import author_paths
from .session.controls import AuthorControlsMixin
from .session.phase_state import PhaseAuthorStateMixin
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
from arcanum.tomes import resolve_working_tid
from arcanum.forge.tool_trace import (_descendants, runner_session, trace_model,
                                      trace_session_id)


def append_conversation(build_id, kind, text, **extra):
    return _append_conversation(BUILD_DIR, build_id, kind, text, **extra)


def load_conversation(build_id, limit=120):
    return _load_conversation(BUILD_DIR, build_id, limit)


class AuthorSession(AuthorControlsMixin, PhaseAuthorStateMixin, ReviewerSessionMixin):
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
                return resolve_working_tid(self.build_id, handle.read())
        except OSError:
            return self.build_id

    def interrupt(self):
        child = self.child
        if not child or child.poll() is not None:
            return
        pids = _descendants(child.pid)
        groups = set()
        for pid in pids:
            try:
                groups.add(os.getpgid(pid))
            except OSError:
                pass
        for sig, grace in ((signal.SIGINT, 8), (signal.SIGTERM, 3), (signal.SIGKILL, 0)):
            for group in groups:
                try:
                    os.killpg(group, sig)
                except OSError:
                    pass
            deadline = time.monotonic() + grace
            while grace and time.monotonic() < deadline:
                if not any(os.path.exists(f"/proc/{pid}") for pid in pids):
                    break
                time.sleep(.1)
            if not any(os.path.exists(f"/proc/{pid}") for pid in pids):
                break
        try:
            child.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass

    def run_turn(self, prompt, conversation_kind="system", conversation_text=""):
        ensure_cost_totals(BUILD_DIR, self.build_id)
        self.actual_model = ""
        started_at = time.time()
        cost_unit = current_unit(self.build_id, self.from_phase) or {
            "kind": "phase", "phase": self.from_phase}
        self.active_unit = cost_unit
        runner = (_resume_command(self.kind, self.model, self.effort, self.session_id, prompt)
                  if self.session_id else _initial_runner(self.kind, self.model, self.effort))
        display, cmd, input_mode = runner
        if input_mode == "arg":
            cmd = [*cmd, prompt]
        wrapped = scoped_runner_command(display, cmd, REPO, self._writable(), REPO,
                                        readonly_paths=self._readonly())
        append_conversation(self.build_id, conversation_kind,
                            conversation_text or prompt)
        self.child = subprocess.Popen(wrapped, cwd=REPO, stdin=_runner_stdin(input_mode),
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, bufsize=1, start_new_session=True)
        if input_mode == "stdin":
            self.child.stdin.write(prompt)
            self.child.stdin.close()
        lines = queue.Queue()
        def reader():
            for raw in self.child.stdout:
                lines.put(raw.rstrip("\n"))
            lines.put(None)
        threading.Thread(target=reader, daemon=True).start()
        # Popen only proves the provider process exists. Do not claim the author is
        # running until its durable session store is discoverable by the trace follower.
        self.state("starting", pid=self.child.pid)
        source, plain, harness_blocked, usage = None, [], "", None

        def finish_cost(status):
            try:
                record_ai_turn(
                    BUILD_DIR, self.build_id,
                    phase=int(cost_unit.get("phase") or self.from_phase),
                    section=cost_unit.get("section"), role=self.role,
                    stage=("full-review" if self.role == "reviewer" else "author-turn"),
                    kind=self.kind, model=self.actual_model or self.model, effort=self.effort,
                    transport="cli", status=status, session_id=self.session_id,
                    usage=usage,
                    usage_mode=("cumulative" if self.kind == "codex-cli" else "turn"),
                    started_at=started_at)
            except Exception as exc:
                print(f"AI cost logging warning: {exc}", flush=True)

        while True:
            try:
                line = lines.get(timeout=.25)
                if line is None:
                    break
                print(line, flush=True)
                observed_usage = _usage_from_line(line)
                if observed_usage:
                    usage = observed_usage
                if not self.session_id:
                    self.session_id = _session_id_from_line(line)
                if self.kind == "opencode-cli" and not self.session_id:
                    self.session_id = _opencode_output_session_id(line)
                answer = _assistant_text(line)
                if answer:
                    append_conversation(self.build_id, "assistant", answer, role=self.role)
                    if _harness_blocked_message(answer):
                        harness_blocked = answer
                elif self.kind == "antigravity-cli":
                    plain.append(line)
            except queue.Empty:
                pass
            if not source and self.child.poll() is None:
                # OpenCode stores every process in one SQLite database. Its structured
                # stdout is the only authoritative process-to-session association; a
                # newest-session-by-directory guess can attach another terminal's work.
                if self.kind == "opencode-cli":
                    if self.session_id:
                        source = runner_session(self.child.pid, self.session_id)
                else:
                    source = runner_session(self.child.pid)
                if source:
                    self.session_id = trace_session_id(source)
                    self.actual_model = trace_model(source)
                    self.state("running", pid=self.child.pid)
            try:
                control = self.controls.get_nowait()
            except queue.Empty:
                control = None
            if control:
                action = control.get("type")
                if action in ("pause", "message", "stop"):
                    self.interrupt()
                    if action == "stop":
                        self.stop = True
                        finish_cost("stopped")
                        return "stopped", ""
                    if action == "message":
                        finish_cost("interrupted-for-message")
                        return "message", str(control.get("text") or "").strip()
                    finish_cost("paused")
                    return "paused", ""
        rc = self.child.wait()
        if plain:
            append_conversation(self.build_id, "assistant", "\n".join(plain)[-20000:],
                                role=self.role)
        if not self.session_id and source:
            self.session_id = trace_session_id(source)
        if source:
            self.actual_model = trace_model(source) or self.actual_model
        if usage:
            path = os.path.join(BUILD_DIR, f"{self.build_id}.author-usage.jsonl")
            with open(path, "a", encoding="utf-8") as handle:
                import json
                handle.write(json.dumps({
                    "at": time.time(), "role": self.role, "kind": self.kind,
                    "model": self.actual_model or self.model,
                    "requestedModel": self.model,
                    "effort": self.effort, "usage": usage,
                }, separators=(",", ":")) + "\n")
        if self.kind == "antigravity-cli":
            # AGY is plain text; the raw turn remains visible even without structured events.
            pass
        if harness_blocked:
            finish_cost("harness-blocked")
            return "harness-blocked", harness_blocked
        status = "complete" if rc == 0 else "failed"
        finish_cost(status)
        return status, ""


    def pause_for_validation_infrastructure(self, unit, exc):
        """Surface a harness-owned failure and wait; the author cannot repair it."""
        detail = f"{type(exc).__name__}: {exc}"
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
                    resumed = self.pause_for_validation_infrastructure(
                        unit, ValidatorInfrastructureError("author self-check", message))
                    if resumed is None:
                        break
                    message, switched = resumed
                    deferred_message = "\n\n".join(
                        part for part in (deferred_message, message) if part)
                    deferred_switch = deferred_switch or switched
                    validate_first = current_unit(
                        self.build_id, self.from_phase, require_gate=True) is not None
                    continue
                if outcome in ("paused", "failed"):
                    if outcome == "failed":
                        self.state("paused", error=(
                            "The author CLI exited unexpectedly. Resume it, or pick "
                            "another AI to take over in a fresh session."))
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
                    prompt = (f"You stopped before handing off {label(unit)}. Finish only that unit, "
                              "run its assigned exact self-check, set its progress marker to "
                              "validating, and stop.\n\n" + unit_prompt(self.build_id, unit))
                    conversation_kind, conversation_text = "harness", (
                        f"{label(unit)} was not marked validating; returning it to the same author session.")
                    continue
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
            next_unit = advance_unit(self.build_id, unit)
            if next_unit is None:
                append_conversation(self.build_id, "harness",
                                    f"Validation passed for {label(unit)}. All eight phases are clean.")
                reviewer_result = self.run_reviewer()
                if reviewer_result:
                    self.state("stopped")
                    return reviewer_result
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
