#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""Focused checks for literal provider extraction and the expanded session history."""
import json
import os
import sqlite3
import tempfile
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arcanum.forge.tool_trace import (_claude_session_from_processes,
                                _opencode_session_from_processes,
                                _trace_path_matches_session,
                                antigravity_tool_events, claude_tool_events,
                                codex_tool_events, format_tool_event,
                                opencode_tool_events, OpenCodeFollower,
                                SessionFollower, saved_session_source, trace_model,
                                trace_session_id, trace_usage, TraceSource)
import arcanum.forge.trace_sources.discovery as _discovery
import arcanum.platform.agent_scratch as _agent_scratch


assert _trace_path_matches_session(
    "codex", "/sessions/rollout-now-actual-thread.jsonl", "actual-thread")
assert not _trace_path_matches_session(
    "codex", "/sessions/rollout-now-stale-thread.jsonl", "actual-thread")


codex_record = {
    "timestamp": "2026-07-13T07:12:12.103Z",
    "type": "response_item",
    "payload": {
        "type": "custom_tool_call", "name": "exec",
        "input": 'const r = await tools.exec_command({"cmd":"rg -n \\\"lesson\\\" tomes/rune-bound"}); text(r.output);',
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

opencode_record = {"timestamp": "2026-07-13T10:30:14-06:00", "type": "tool", "tool": "read",
                   "state": {"input": {"filePath": "/repo/tome.toml", "offset": 12}}}
assert opencode_tool_events(opencode_record)[0]["detail"] == "/repo/tome.toml offset=12"

agy_record = {"created_at": "2026-07-13T16:32:47Z", "type": "PLANNER_RESPONSE",
              "tool_calls": [{"name": "run_command",
                              "args": {"CommandLine": "python3 tools/validate_tome.py tome"}}]}
assert antigravity_tool_events(agy_record)[0]["detail"] == "python3 tools/validate_tome.py tome"

with tempfile.NamedTemporaryFile("wb", delete=False) as handle:
    path = handle.name
    for number in range(5):
        row = dict(codex_record)
        row["payload"] = dict(codex_record["payload"], input=f'const r = await tools.exec_command({{cmd:"echo {number}"}});')
        handle.write(json.dumps(row).encode() + b"\n")
try:
    follower = SessionFollower("codex", path)
    assert [event["detail"] for event in follower.poll()] == [
        "echo 0", "echo 1", "echo 2", "echo 3", "echo 4"]
finally:
    os.unlink(path)

with tempfile.NamedTemporaryFile("w", delete=False) as handle:
    codex_session = handle.name
    handle.write(json.dumps({"type": "session_meta",
                             "payload": {"id": "019f-session-id"}}) + "\n")
try:
    assert trace_session_id(TraceSource("codex", codex_session)) == "019f-session-id"
finally:
    os.unlink(codex_session)

with tempfile.NamedTemporaryFile("w", delete=False) as handle:
    codex_models = handle.name
    handle.write(json.dumps({"type": "turn_context",
                             "payload": {"model": "gpt-5.6-terra"}}) + "\n")
    handle.write(json.dumps({"type": "event_msg", "payload": {
        "type": "thread_settings_applied",
        "thread_settings": {"model": "gpt-5.6-sol"}}}) + "\n")
try:
    assert trace_model(TraceSource("codex", codex_models)) == "gpt-5.6-sol"
    assert trace_model(TraceSource("claude", codex_models)) == ""
finally:
    os.unlink(codex_models)

with tempfile.NamedTemporaryFile("w", delete=False) as handle:
    codex_usage = handle.name
    handle.write(json.dumps({"type": "event_msg", "payload": {
        "type": "token_count", "info": {"total_token_usage": {
            "input_tokens": 1200, "cached_input_tokens": 800, "output_tokens": 30,
        }}}}) + "\n")
try:
    assert trace_usage(TraceSource("codex", codex_usage)) == {
        "inputTokens": 1200, "cachedInputTokens": 800, "outputTokens": 30,
        "freshInputTokens": 400,
    }
    assert trace_usage(TraceSource("codex", codex_usage), before=0) == {}
finally:
    os.unlink(codex_usage)

with tempfile.TemporaryDirectory() as tmp:
    proc_root = os.path.join(tmp, "proc")
    projects = os.path.join(tmp, "projects")
    cwd = "/repo/tomes/rune-bound"
    pdir = os.path.join(proc_root, "123")
    project = os.path.join(projects, cwd.replace(os.sep, "-"))
    os.makedirs(pdir)
    os.makedirs(project)
    with open(os.path.join(pdir, "cmdline"), "wb") as handle:
        handle.write(b"/home/user/.local/bin/claude\0-p\0")
    os.symlink(cwd, os.path.join(pdir, "cwd"))
    session = os.path.join(project, "session.jsonl")
    with open(session, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(claude_record) + "\n")
    assert _claude_session_from_processes([123], proc_root, projects) == TraceSource(
        "claude", session, "session")

with tempfile.TemporaryDirectory() as tmp:
    proc_root = os.path.join(tmp, "proc")
    pdir = os.path.join(proc_root, "321")
    os.makedirs(os.path.join(pdir, "fd"))
    os.makedirs(os.path.join(proc_root, "self"))
    with open(os.path.join(pdir, "cmdline"), "wb") as handle:
        handle.write(b"/home/user/.local/bin/opencode\0run\0")
    os.symlink("/repo/tomes/live", os.path.join(pdir, "cwd"))
    namespace_root = os.path.join(tmp, "namespace")
    conventional = "/home/user/.local/share/opencode/opencode.db"
    database = os.path.join(namespace_root, "private-state", "opencode.db")
    os.makedirs(os.path.dirname(database))
    with open(os.path.join(pdir, "mountinfo"), "w", encoding="utf-8") as handle:
        handle.write(
            "50 40 0:99 /private-state /home/user/.local/share/opencode "
            "rw - tmpfs tmpfs rw\n")
    with open(os.path.join(proc_root, "self", "mountinfo"), "w",
              encoding="utf-8") as handle:
        handle.write(f"60 40 0:99 / {namespace_root} rw - tmpfs tmpfs rw\n")
    now = int(time.time() * 1000)
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE session (id text, directory text, time_created integer, time_updated integer)")
        db.execute("CREATE TABLE part (id text, session_id text, time_created integer, data text)")
        db.execute("INSERT INTO session VALUES (?, ?, ?, ?)",
                   ("session-live", "/repo/tomes/live", now, now))
        for number in range(5):
            data = {"type": "tool", "tool": "bash",
                    "state": {"input": {"command": f"echo {number}"}}}
            db.execute("INSERT INTO part VALUES (?, ?, ?, ?)",
                       (f"part-{number}", "session-live", now + number, json.dumps(data)))
    os.symlink(conventional, os.path.join(pdir, "fd", "3"))
    found = _opencode_session_from_processes([321], proc_root)
    assert found and found[1] == TraceSource(
        "opencode", database, "session-live"), found
    assert _opencode_session_from_processes(
        [321], proc_root, session_id="session-live")[1] == TraceSource(
            "opencode", database, "session-live")
    assert _opencode_session_from_processes([321], proc_root, session_id="") is None
    follower = OpenCodeFollower(found[1])
    assert [event["detail"] for event in follower.poll()] == [
        "echo 0", "echo 1", "echo 2", "echo 3", "echo 4"]
    # This trace is a binary database. Reading it as text killed the mirror thread, which
    # left the tool-history pane empty for the whole build with nothing to say why.
    assert trace_usage(found[1]) == {}

# A sandboxed Claude author holds no fd on its JSONL; the saved-session fallback must still
# find it under the unit's private provider-state overlay (a dotdir os.walk descends, glob skips).
with tempfile.TemporaryDirectory() as tmp:
    build_dir = os.path.join(tmp, "build")
    os.makedirs(build_dir)
    with open(os.path.join(build_dir, "u7.session.json"), "w", encoding="utf-8") as handle:
        json.dump({"kind": "claude-cli", "phase": 3, "section": "s01",
                   "sessionId": "sid-xyz"}, handle)
    sess_dir = os.path.join(tmp, "scratch", "u7", "author", "phase-3", "section-s01",
                            "provider-state", "claude", ".claude", "projects", "-repo")
    os.makedirs(sess_dir)
    sess_file = os.path.join(sess_dir, "sid-xyz.jsonl")
    with open(sess_file, "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"type": "assistant", "timestamp": "2026-07-23T00:00:00Z",
                                 "message": {"content": [{"type": "tool_use", "name": "Bash",
                                                          "input": {"command": "ls"}}]}}) + "\n")
    old_bd, old_root = _discovery.BUILD_DIR, _agent_scratch.ROOT
    _discovery.BUILD_DIR, _agent_scratch.ROOT = build_dir, os.path.join(tmp, "scratch")
    try:
        found = saved_session_source("u7")
        assert found == TraceSource("claude", sess_file, "sid-xyz"), found
        assert saved_session_source("missing") is None
    finally:
        _discovery.BUILD_DIR, _agent_scratch.ROOT = old_bd, old_root
    assert [event["detail"] for event in SessionFollower(found).poll()] == ["ls"]


print("forge tool trace: OK")
