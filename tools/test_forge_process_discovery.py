#!/usr/bin/env python3
"""Durable discovery and status for one interactive tome author."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import arcanum.build_state as state  # noqa: E402
import arcanum.forge as forge  # noqa: E402
import arcanum.tomes as tomes  # noqa: E402
from arcanum.post_routes.builds import _author  # noqa: E402


def write_proc(root, pid, argv):
    directory = os.path.join(root, str(pid))
    os.makedirs(directory)
    with open(os.path.join(directory, "cmdline"), "wb") as handle:
        handle.write(b"\0".join(arg.encode() for arg in argv) + b"\0")


with tempfile.TemporaryDirectory() as temp:
    proc_root, build_root, tome_root = (os.path.join(temp, name)
                                        for name in ("proc", "build", "tomes"))
    os.makedirs(proc_root); os.makedirs(build_root)
    os.makedirs(os.path.join(tome_root, "rune-bound"))
    with open(os.path.join(tome_root, "rune-bound", "tome.toml"), "w", encoding="utf-8") as handle:
        handle.write('[meta]\nid = "rune-bound"\nname = "RuneBound"\n')
    plan = ("# BUILD PLAN — untitled-5\n\n## Concept\nA PyGame RPG.\n\n"
            "- **Tome id renamed by the harness:** `untitled-5` → `rune-bound`\n")
    with open(os.path.join(build_root, "untitled-5.plan.md"), "w", encoding="utf-8") as handle:
        handle.write(plan)
    with open(os.path.join(build_root, "untitled-5.progress"), "w", encoding="utf-8") as handle:
        json.dump({"phase": 4, "phaseTitle": "Minigames", "state": "working",
                   "phaseStartedAt": 100, "updatedAt": 101}, handle)
    with open(os.path.join(build_root, "untitled-5.session.json"), "w", encoding="utf-8") as handle:
        json.dump({"state": "paused", "sessionId": "abc", "kind": "codex-cli"}, handle)
    write_proc(proc_root, 111, ["/usr/bin/python3", "-u", "/repo/tools/build_tome.py",
                                "untitled-5", "--author", "codex-cli:gpt-5.6-sol"])
    write_proc(proc_root, 222, ["/bin/sh", "-c", "echo tools/build_tome.py untitled-5"])

    old = (forge.BUILD_DIR, state.BUILD_DIR, tomes.BUILD_DIR,
           forge.TOMES_DIR, tomes.TOMES_DIR)
    try:
        forge.BUILD_DIR = state.BUILD_DIR = tomes.BUILD_DIR = build_root
        forge.TOMES_DIR = tomes.TOMES_DIR = tome_root
        found = forge._live_build_processes(proc_root)
        assert [row["planid"] for row in found] == ["untitled-5"]
        assert state.BUILD_TOTAL_PHASES == 8
        assert state.load_build_progress("untitled-5")["phase"] == 4
        assert state.load_author_session("untitled-5")["state"] == "paused"
        active = forge.list_active_builds(proc_root)
        assert active[0]["tome"] == "rune-bound" and active[0]["phase"] == 4
        forge.jobs["local-job"] = {"kind": "build", "status": "running",
                                   "tome": "untitled-5", "slug": "untitled-5",
                                   "phase": 1, "phaseTitle": "starting"}
        active = forge.list_active_builds(proc_root)
        assert len(active) == 1 and not active[0]["external"]
        assert active[0]["tome"] == "rune-bound" and active[0]["phase"] == 4
        assert _author({"author": {"kind": "opencode-cli",
                                   "model": "ollama/llama3.2:3b"}})
    finally:
        forge.jobs.pop("local-job", None)
        (forge.BUILD_DIR, state.BUILD_DIR, tomes.BUILD_DIR,
         forge.TOMES_DIR, tomes.TOMES_DIR) = old

print("single-author process discovery: OK")
