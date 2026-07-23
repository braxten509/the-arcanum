"""Provider process lifecycle for one warm single-author turn."""
from __future__ import annotations

import os
import queue
import signal
import subprocess
import threading
import time

from ... import BUILD_DIR, REPO
from ...ai_costs import ensure_cost_totals, record_ai_turn
from arcanum.platform.agent_commands import scoped_runner_command
from ..gate import current_unit
from ..runtime import assistant_text
from ..runtime import initial_runner
from ..runtime import opencode_output_session_id
from ..runtime import resume_command
from ..runtime import runner_stdin
from ..runtime import session_id_from_line
from ..runtime import usage_from_line
from .recovery import with_codex_patch_safety
from .support import append_conversation as _append_conversation
from .support import harness_blocked_message, repair_required_message
from arcanum.forge.tool_trace import (_descendants, runner_session, trace_model,
                                      trace_session_id)
from arcanum.forge.trace_metadata import trace_usage
from arcanum.jobs.stall import StallWatch

# Idle means no CPU anywhere in the tree and no established provider connection, so this
# is not a patience budget: a thinking model and a running tool both keep the clock at 0.
STALL_SECONDS = float(os.environ.get("ARCANUM_STALL_SECONDS", "10"))
STALL_POLL_SECONDS = 2.0


def authoritative_session_id(current, line):
    """Prefer the thread id emitted by this CLI invocation over a requested resume id."""
    return session_id_from_line(line) or current


def append_conversation(build_id, kind, text, **extra):
    return _append_conversation(BUILD_DIR, build_id, kind, text, **extra)


class AuthorTurnMixin:
    """Launch, observe, interrupt, and account for one provider turn."""

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
        prompt = with_codex_patch_safety(self.kind, self.role, prompt)
        self.actual_model = ""
        started_at = time.time()
        cost_unit = current_unit(self.build_id, self.from_phase) or {
            "kind": "phase", "phase": self.from_phase}
        self.active_unit = cost_unit
        runner = (resume_command(self.kind, self.model, self.effort, self.session_id, prompt)
                  if self.session_id else initial_runner(self.kind, self.model, self.effort))
        display, cmd, input_mode = runner
        if input_mode == "arg":
            cmd = [*cmd, prompt]
        wrapped = scoped_runner_command(display, cmd, REPO, self._writable(), REPO,
                                        readonly_paths=self._readonly(),
                                        hidden_paths=self._hidden(),
                                        permission_paths=self._permission_paths(),
                                        state_scope={"build_id": self.build_id, "role": self.role,
                                                     "phase": int(cost_unit.get("phase") or self.from_phase),
                                                     "section": str(cost_unit.get("section") or "")})
        append_conversation(self.build_id, conversation_kind,
                            conversation_text or prompt)
        self.child = subprocess.Popen(wrapped, cwd=REPO, stdin=runner_stdin(input_mode),
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
        source, plain, harness_blocked, repair_required, usage = None, [], "", "", None
        # stderr is folded into stdout, so a crashing CLI's complaint arrives as plain
        # text among the structured events. Keep the last few for the failure report.
        # ponytail: "not JSON" is the whole test; providers that emit prose on success
        # only cost a slightly noisier message on a turn that already failed.
        noise = []
        output_session_id, trace_baseline = "", None
        stall = StallWatch(self.child.pid, STALL_SECONDS)
        next_stall_poll = time.monotonic() + STALL_POLL_SECONDS

        def finish_cost(status):
            try:
                cost_usage, usage_mode, usage_baseline = usage, "turn", None
                if self.kind == "codex-cli" and source and source.provider == "codex":
                    cumulative = trace_usage(source)
                    if cumulative:
                        cost_usage = cumulative
                        usage_mode = "cumulative"
                        usage_baseline = trace_baseline
                record_ai_turn(
                    BUILD_DIR, self.build_id,
                    phase=int(cost_unit.get("phase") or self.from_phase),
                    section=cost_unit.get("section"), role=self.role,
                    stage=("full-review" if self.role == "reviewer" else "author-turn"),
                    kind=self.kind, model=self.actual_model or self.model, effort=self.effort,
                    transport="cli", status=status, session_id=self.session_id,
                    usage=cost_usage, usage_mode=usage_mode,
                    usage_baseline=usage_baseline, started_at=started_at)
            except Exception as exc:
                print(f"AI cost logging warning: {exc}", flush=True)

        while True:
            try:
                line = lines.get(timeout=.25)
                if line is None:
                    break
                print(line, flush=True)
                stall.poke()
                if line.strip() and not line.lstrip().startswith("{"):
                    noise = [*noise, line.strip()][-5:]
                observed_usage = usage_from_line(line)
                if observed_usage:
                    usage = observed_usage
                emitted_session_id = session_id_from_line(line)
                if emitted_session_id:
                    output_session_id = emitted_session_id
                    self.session_id = authoritative_session_id(self.session_id, line)
                    if source and trace_session_id(source) != output_session_id:
                        source, trace_baseline = None, None
                if self.kind == "opencode-cli" and not self.session_id:
                    self.session_id = opencode_output_session_id(line)
                answer = assistant_text(line)
                if answer:
                    append_conversation(self.build_id, "assistant", answer, role=self.role)
                    if harness_blocked_message(answer):
                        harness_blocked = answer
                    if repair_required_message(answer):
                        repair_required = answer
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
                elif self.kind in ("codex-cli", "claude-cli"):
                    if output_session_id:
                        source = runner_session(self.child.pid, output_session_id)
                else:
                    source = runner_session(self.child.pid)
                if source:
                    self.session_id = output_session_id or trace_session_id(source)
                    self.actual_model = trace_model(source)
                    if source.provider == "codex":
                        trace_baseline = trace_usage(source, before=started_at)
                    self.state("running", pid=self.child.pid)
            # Scanning /proc costs a directory walk, so sample it on its own cadence
            # rather than on every 250ms queue poll.
            if time.monotonic() >= next_stall_poll:
                next_stall_poll = time.monotonic() + STALL_POLL_SECONDS
                if self.child.poll() is None and stall.wedged():
                    self.interrupt()
                    finish_cost("failed")
                    return "failed", (
                        f"The author CLI stopped responding: no CPU anywhere in its "
                        f"process tree and no open connection to the provider for "
                        f"{STALL_SECONDS:.0f}s. The harness ended the turn rather than "
                        "wait on a process that had nothing left to do.")
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
        if not output_session_id and source:
            self.session_id = trace_session_id(source) or self.session_id
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
        if repair_required:
            finish_cost("repair-required")
            return "repair-required", repair_required
        if harness_blocked:
            finish_cost("harness-blocked")
            return "harness-blocked", harness_blocked
        status = "complete" if rc == 0 else "failed"
        finish_cost(status)
        if status == "failed":
            return status, "\n".join([f"exit code {rc}", *noise])
        return status, ""
