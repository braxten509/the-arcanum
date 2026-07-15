#!/usr/bin/env python3
"""Phase 8 repairs resume the same author session instead of spawning a reviewer."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.buildlib.single_author import _resume_command, author_prompt  # noqa: E402


prompt = author_prompt("example", "Teach a tool", "both", 8)
assert "sole author" in prompt and "spawn another author or reviewer" in prompt
for kind, model in (("codex-cli", "gpt-5.6-sol"),
                    ("claude-cli", "claude-opus-4-8"),
                    ("opencode-cli", "opencode-go/minimax-m3"),
                    ("antigravity-cli", "Gemini 3.1 Pro (High)")):
    _display, command, _mode = _resume_command(kind, model, "", "session-123", "repair")
    assert "session-123" in command
print("same-session Phase 8 repair: OK")
