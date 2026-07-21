"""Fake AuthorSession subclasses driving the single-author gate tests.

Each class stands in for one provider behaviour — a clean warm turn, a routed
phase author, an unlimited repair loop, a no-progress oscillation, and the two
HARNESS_BLOCKED variants. They patch nothing themselves; the assertions in
test_single_author_gate.py own the temp dirs and the patching.
"""
from __future__ import annotations

import os

from tools.buildlib import single_author
from tools.buildlib.single_author import gate


class FakeWarmSession(single_author.AuthorSession):
    def __init__(self):
        super().__init__("warm", "codex-cli", "test", "", "", "external", 7, "warm-session")
        self.prompts = []
        self.states = []

    def read_controls(self):
        return

    def state(self, state, **extra):
        self.states.append((state, extra))

    def run_turn(self, prompt, conversation_kind="system", conversation_text=""):
        self.prompts.append(prompt)
        active = gate.current_unit("warm", 7)
        gate._write_phase("warm", active["phase"], "validating")
        return "complete", ""


class RoutedWarmSession(FakeWarmSession):
    def __init__(self):
        single_author.AuthorSession.__init__(
            self, "routed", "codex-cli", "sections", "high", "", "external", 7,
            "sections-warm", phase_authors={
                "phase12": ("claude-cli", "arc", "high"),
                "phase37": ("codex-cli", "sections", "high"),
                "phase8": ("opencode-cli", "student-review", "max"),
            })
        self.prompts = []
        self.states = []

    def run_turn(self, prompt, conversation_kind="system", conversation_text=""):
        self.prompts.append(prompt)
        active = gate.current_unit("routed", 7)
        gate._write_phase("routed", active["phase"], "validating")
        return "complete", ""


class UnlimitedRepairSession(FakeWarmSession):
    def __init__(self):
        super().__init__()
        self.from_phase = 8


class OscillatingNoHandoffSession(single_author.AuthorSession):
    def __init__(self, authored_path):
        super().__init__(
            "cycle", "codex-cli", "test", "", "", "external", 2, "warm-session")
        self.authored_path = authored_path
        self.prompts = []
        self.states = []

    def read_controls(self):
        return

    def state(self, state, **extra):
        self.states.append((state, extra))

    def run_turn(self, prompt, conversation_kind="system", conversation_text=""):
        self.prompts.append(prompt)
        value = "A\n" if len(self.prompts) % 2 else "B\n"
        with open(self.authored_path, "w", encoding="utf-8") as handle:
            handle.write(value)
        return "complete", ""


class ExplicitBlockedSession(UnlimitedRepairSession):
    def run_turn(self, prompt, conversation_kind="system", conversation_text=""):
        self.prompts.append(prompt)
        return "harness-blocked", "HARNESS_BLOCKED: validator import failed"


# A provider cannot turn structured authored findings into an infrastructure pause
# merely by prefixing its answer with HARNESS_BLOCKED.
class BlockedThenHandoffSession(ExplicitBlockedSession):
    def run_turn(self, prompt, conversation_kind="system", conversation_text=""):
        self.prompts.append(prompt)
        if len(self.prompts) == 1:
            return "harness-blocked", "HARNESS_BLOCKED: claimed infrastructure failure"
        gate._write_phase("warm", 8, "validating")
        return "complete", ""
