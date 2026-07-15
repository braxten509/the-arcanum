"""One persistent CLI author session for an entire Arcanum tome."""
from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time

from . import BUILD_DIR, REPO
from .agent_runtime import scoped_runner_command
from .author_gate import (PHASES, advance_unit, current_unit, ensure_unit, label,
                          next_prompt, repair_prompt, unit_prompt, validate_unit)
from .runners import author_runner
from arcanum.forge import notify
from arcanum.tomes import resolve_working_tid
from arcanum.tool_trace import _descendants, runner_session, trace_session_id


def _json_path(build_id, suffix):
    return os.path.join(BUILD_DIR, f"{build_id}.{suffix}.json")


def _read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
        return value
    except (OSError, ValueError):
        return default


def _write_json(path, value):
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
    os.replace(temp, path)


def append_conversation(build_id, kind, text, **extra):
    text = str(text or "").strip()
    if not text:
        return
    row = {"at": time.time(), "kind": kind, "text": text, **extra}
    with open(_json_path(build_id, "conversation") + "l", "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def load_conversation(build_id, limit=120):
    path = _json_path(build_id, "conversation") + "l"
    try:
        with open(path, encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
    except (OSError, ValueError):
        return []
    return rows[-max(1, int(limit)):]


def author_prompt(build_id, concept, tooling, from_phase=1):
    plan = f".tome-build/{build_id}.plan.md"
    return f"""You are the sole author of one complete Arcanum tome. This is one continuous,
interactive, resumable author session. Retain context across every harness checkpoint. The
operator may pause you and later send guidance in this same session.

BUILD ID: {build_id}
CURRENT TOME ID: {build_id} (Phase 2's transition command may rename it; follow its output.)
CONCEPT: {concept}
TOOLING: {tooling}
PLAN: {plan}
START OR RESUME AT PHASE: {from_phase}

Read `tome-workflow/single-author.md` now. At the start of each phase, read only that phase's
guide under `tome-workflow/` plus the references it explicitly names. Files on disk are truth.

Work on exactly the phase or Phase-3 section named in the final instruction. When it is authored,
set that unit's progress marker to `validating` and end your turn. Do not run validators and do
not begin the next unit. The harness independently validates while you are stopped, checkpoints
a clean unit, and resumes this same warm session with either the exact repair report or the exact
next unit. Preserve correct work already on disk.

Continue this checkpoint cycle through Phase 8. Do not spawn another author or reviewer. Do not
merely describe work: edit the tome, report `validating`, and stop at the assigned boundary.
"""


def continuation_prompt(_build_id):
    """A resumed CLI already owns the full author conversation and workflow contract."""
    return "Continue."


def _resume_command(kind, model, effort, session_id, prompt):
    if kind == "codex-cli":
        cmd = [os.path.expanduser("~/.local/bin/codex"), "--search", "exec", "resume",
               session_id, "--skip-git-repo-check", "--json"]
        if effort:
            cmd += ["-c", f"model_reasoning_effort={effort}"]
        cmd.append(prompt)
        return (f"{kind} {model}", cmd, "none")
    if kind == "claude-cli":
        cmd = ["claude", "--resume", session_id, "-p", "--permission-mode", "auto",
               "--model", model, "--output-format", "stream-json", "--verbose"]
        if effort:
            cmd += ["--effort", effort]
        cmd.append(prompt)
        return (f"{kind} {model}", cmd, "none")
    if kind == "opencode-cli":
        cmd = ["opencode", "run", "--auto", "--session", session_id,
               "--format", "json", "-m", model]
        if effort:
            cmd += ["--variant", effort]
        cmd.append(prompt)
        return (f"{kind} {model}", cmd, "none")
    cmd = ["agy", "--dangerously-skip-permissions", "--print-timeout", "4h",
           "--conversation", session_id, "--model", model, "--print", prompt]
    return (f"{kind} {model}", cmd, "none")


def _initial_runner(kind, model, effort):
    display, cmd, input_mode = author_runner(
        f"{kind}:{model}" + (f"@{effort}" if effort else ""), "--author")
    if kind == "codex-cli":
        cmd.insert(cmd.index("-") if "-" in cmd else len(cmd), "--json")
    elif kind == "claude-cli":
        cmd += ["--output-format", "stream-json", "--verbose"]
    elif kind == "opencode-cli":
        cmd[cmd.index("run") + 1:cmd.index("run") + 1] = ["--format", "json"]
    return display, cmd, input_mode


def _assistant_text(line):
    try:
        row = json.loads(line)
    except ValueError:
        return ""
    if row.get("type") == "item.completed" and (row.get("item") or {}).get("type") == "agent_message":
        return str(row["item"].get("text") or "")
    if row.get("type") == "assistant":
        content = (row.get("message") or {}).get("content") or []
        return "\n".join(str(block.get("text") or "") for block in content
                         if isinstance(block, dict) and block.get("type") == "text")
    part = row.get("part") or row.get("message") or {}
    if isinstance(part, dict) and part.get("type") in ("text", "assistant"):
        return str(part.get("text") or part.get("content") or "")
    return ""


class AuthorSession:
    def __init__(self, build_id, kind, model, effort, concept, tooling, from_phase=1,
                 resume_id=""):
        self.build_id, self.kind, self.model = build_id, kind, model
        self.effort, self.concept, self.tooling = effort, concept, tooling
        self.from_phase, self.session_id = from_phase, resume_id
        self.state_path = _json_path(build_id, "session")
        self.controls, self.child, self.stop = queue.Queue(), None, False

    def state(self, state, **extra):
        payload = {"buildId": self.build_id, "state": state, "kind": self.kind,
                   "model": self.model, "effort": self.effort,
                   "sessionId": self.session_id, "updatedAt": time.time(), **extra}
        _write_json(self.state_path, payload)
        print(f"AUTHOR SESSION {state}", flush=True)

    def read_controls(self):
        for line in sys.stdin:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            self.controls.put(row)

    def _writable(self):
        # The tome parent is writable because the deterministic Phase-2 transition renames
        # the launch slug to the project id while this same CLI process remains alive.
        return [BUILD_DIR, os.path.join(REPO, "tomes"),
                os.path.join(REPO, "global-configs", "runtimes")]

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
        runner = (_resume_command(self.kind, self.model, self.effort, self.session_id, prompt)
                  if self.session_id else _initial_runner(self.kind, self.model, self.effort))
        display, cmd, input_mode = runner
        if input_mode == "arg":
            cmd = [*cmd, prompt]
        wrapped = scoped_runner_command(display, cmd, REPO, self._writable(), REPO)
        append_conversation(self.build_id, conversation_kind,
                            conversation_text or prompt)
        self.child = subprocess.Popen(wrapped, cwd=REPO, stdin=subprocess.PIPE,
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
        self.state("running", pid=self.child.pid)
        source, plain = None, []
        while True:
            try:
                line = lines.get(timeout=.25)
                if line is None:
                    break
                print(line, flush=True)
                answer = _assistant_text(line)
                if answer:
                    append_conversation(self.build_id, "assistant", answer)
                elif self.kind == "antigravity-cli":
                    plain.append(line)
            except queue.Empty:
                pass
            if not source and self.child.poll() is None:
                source = runner_session(self.child.pid)
                if source:
                    self.session_id = trace_session_id(source)
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
                        return "stopped", ""
                    if action == "message":
                        return "message", str(control.get("text") or "").strip()
                    return "paused", ""
        rc = self.child.wait()
        if plain:
            append_conversation(self.build_id, "assistant", "\n".join(plain)[-20000:])
        if not self.session_id and source:
            self.session_id = trace_session_id(source)
        if self.kind == "antigravity-cli":
            # AGY is plain text; the raw turn remains visible even without structured events.
            pass
        return ("complete" if rc == 0 else "failed"), ""

    def apply_author(self, control):
        """Adopt a replacement author sent through the control lane. A different CLI (or
        model) cannot resume the old session, so the switch starts a fresh one."""
        author = control.get("author") or {}
        kind, model = str(author.get("kind") or ""), str(author.get("model") or "")
        if not kind or not model or (kind, model) == (self.kind, self.model):
            return False
        self.kind, self.model, self.effort = kind, model, str(author.get("effort") or "")
        self.session_id = ""
        return True

    def await_controls(self, retrying=False):
        """Block until stop or a message/resume control. Returns the next
        (prompt, conversation_kind, conversation_text), or None on stop."""
        while True:
            control = self.controls.get()
            if control.get("type") == "stop":
                self.stop = True
                return None
            if control.get("type") not in ("message", "resume"):
                continue
            switched = self.apply_author(control)
            message = str(control.get("text") or "").strip()
            unit = ensure_unit(self.build_id, self.from_phase)
            prompt = ((message + "\n\n") if message else "") + unit_prompt(unit)
            if switched:
                prompt = author_prompt(self.build_id, self.concept, self.tooling,
                                       unit.get("phase", self.from_phase)) + "\n\n" + prompt
            verb = "Retrying" if retrying else "Resuming"
            text = message or (
                f"{verb} {label(unit)} with {self.kind} {self.model} in a fresh session."
                if switched else f"{verb} {label(unit)}.")
            return prompt, ("user" if message else "harness"), text

    def run(self):
        threading.Thread(target=self.read_controls, daemon=True).start()
        unit = ensure_unit(self.build_id, self.from_phase)
        assignment = unit_prompt(unit)
        prompt = (assignment if self.session_id else
                  author_prompt(self.build_id, self.concept, self.tooling, self.from_phase)
                  + "\n\n" + assignment)
        conversation_kind = "harness"
        conversation_text = f"Assigned {label(unit)}. The harness will validate when the author stops."
        while not self.stop:
            outcome, message = self.run_turn(prompt, conversation_kind, conversation_text)
            if outcome == "stopped":
                break
            if outcome == "message":
                unit = ensure_unit(self.build_id, self.from_phase)
                prompt = message + "\n\n" + unit_prompt(unit)
                conversation_kind, conversation_text = "user", message
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
                          "set its progress marker to validating, and stop.\n\n" + unit_prompt(unit))
                conversation_kind, conversation_text = "harness", (
                    f"{label(unit)} was not marked validating; returning it to the same author session.")
                continue
            self.state("validating", unit=label(unit))
            ok, report = validate_unit(self.build_id, unit)
            if not ok:
                prompt = repair_prompt(unit, report)
                conversation_kind, conversation_text = "harness", (
                    f"Validation failed for {label(unit)}. The report was returned to the same author session.")
                continue
            next_unit = advance_unit(self.build_id, unit)
            if next_unit is None:
                append_conversation(self.build_id, "harness",
                                    f"Validation passed for {label(unit)}. All eight phases are clean.")
                self.state("complete")
                return 0
            prompt = next_prompt(unit, next_unit, report)
            conversation_kind, conversation_text = "harness", (
                f"Validation passed for {label(unit)}. Continuing with {label(next_unit)} in the same session.")
        self.state("stopped")
        return 130
