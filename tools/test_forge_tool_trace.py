#!/usr/bin/env python3
"""Focused checks for literal Codex/Claude tool extraction and the three-line cap."""
import json
import os
import tempfile
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arcanum.tool_trace import SessionFollower, codex_tool_events, claude_tool_events, format_tool_event


codex_record = {
    "timestamp": "2026-07-13T07:12:12.103Z",
    "type": "response_item",
    "payload": {
        "type": "custom_tool_call", "name": "exec",
        "input": 'const r = await tools.exec_command({cmd:"rg -n \\\"lesson\\\" tomes/rune-bound"}); text(r.output);',
    },
}
events = codex_tool_events(codex_record)
assert [(event["tool"], event["detail"]) for event in events] == [
    ("exec_command", 'rg -n "lesson" tomes/rune-bound')
], events
assert format_tool_event(events[0]).endswith('exec_command › rg -n "lesson" tomes/rune-bound')

patch_record = {
    "timestamp": "2026-07-13T07:13:19.854Z", "type": "response_item",
    "payload": {"type": "custom_tool_call", "name": "exec",
                "input": "text(await tools.apply_patch(patch.join(NL)));"},
}
assert codex_tool_events(patch_record)[0]["detail"] == "patch.join(NL)", codex_tool_events(patch_record)

claude_record = {
    "timestamp": "2026-07-13T06:21:09.661Z", "type": "assistant",
    "message": {"content": [{"type": "tool_use", "name": "Bash",
                               "input": {"command": "python3 tools/validate_tome.py tomes/rune-bound"}}]},
}
assert claude_tool_events(claude_record)[0]["detail"] == "python3 tools/validate_tome.py tomes/rune-bound"

with tempfile.NamedTemporaryFile("wb", delete=False) as handle:
    path = handle.name
    for number in range(5):
        row = dict(codex_record)
        row["payload"] = dict(codex_record["payload"], input=f'const r = await tools.exec_command({{cmd:"echo {number}"}});')
        handle.write(json.dumps(row).encode() + b"\n")
try:
    follower = SessionFollower("codex", path)
    assert [event["detail"] for event in follower.poll()] == ["echo 2", "echo 3", "echo 4"]
finally:
    os.unlink(path)

print("forge tool trace: OK")

