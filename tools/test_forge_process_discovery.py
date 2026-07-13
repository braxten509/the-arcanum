#!/usr/bin/env python3
"""Regression checks for cross-server discovery of live tome builds."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import arcanum.forge as forge
import arcanum.build_state as state
import arcanum.tomes as tomes


def write_proc(root, pid, argv):
    pdir = os.path.join(root, str(pid))
    os.makedirs(pdir)
    with open(os.path.join(pdir, "cmdline"), "wb") as f:
        f.write(b"\0".join(a.encode() for a in argv) + b"\0")


with tempfile.TemporaryDirectory() as tmp:
    proc = os.path.join(tmp, "proc")
    build = os.path.join(tmp, "build")
    tome_root = os.path.join(tmp, "tomes")
    os.makedirs(proc)
    os.makedirs(build)
    os.makedirs(os.path.join(tome_root, "rune-bound"))
    with open(os.path.join(tome_root, "rune-bound", "tome.toml"), "w", encoding="utf-8") as f:
        f.write('[meta]\nid = "rune-bound"\nname = "RuneBound"\n')
    plan = ("# BUILD PLAN — untitled-5\n\n## Concept\nA PyGame RPG.\n\n"
            "- **Tome id renamed by the harness:** `untitled-5` → `rune-bound`\n")
    with open(os.path.join(build, "untitled-5.plan.md"), "w", encoding="utf-8") as f:
        f.write(plan)
    with open(os.path.join(build, "rune-bound.progress"), "w", encoding="utf-8") as f:
        json.dump({"phase": 4}, f)

    write_proc(proc, 111, ["/usr/bin/python3", "-u", "/repo/tools/build_tome.py",
                           "untitled-5", "--ask-on-death"])
    write_proc(proc, 333, ["/usr/bin/python3", "/repo/tools/forge_tool_trace.py",
                           "--job", "owner-job-1", "--pid", "111"])
    # Mentioning build_tome.py inside an unrelated shell argument must not count.
    write_proc(proc, 222, ["/bin/sh", "-c", "echo tools/build_tome.py untitled-5"])

    old_build, old_state_build, old_tomes_build = forge.BUILD_DIR, state.BUILD_DIR, tomes.BUILD_DIR
    old_forge_tomes, old_tomes_tomes = forge.TOMES_DIR, tomes.TOMES_DIR
    old_jobs = dict(forge.jobs)
    original = forge.list_active_builds
    try:
        forge.BUILD_DIR = state.BUILD_DIR = tomes.BUILD_DIR = build
        forge.TOMES_DIR, tomes.TOMES_DIR = tome_root, tome_root
        forge.jobs.clear()
        found = forge._live_build_processes(proc)
        assert [p["planid"] for p in found] == ["untitled-5"], found
        assert forge._live_trace_jobs(proc) == {111: "owner-job-1"}
        active = forge.list_active_builds(proc)
        assert len(active) == 1, active
        assert active[0]["tome"] == "rune-bound", active
        assert active[0]["phase"] == 4 and active[0]["phaseTitle"] == "Minigames", active
        assert active[0]["external"] is True, active
        assert active[0]["traceId"] == "owner-job-1", active

        cancelled = state.record_cancelled_build("untitled-5", "rune-bound", 4)
        assert state.cancelled_build_status("untitled-5") == cancelled
        assert state.build_result_status("untitled-5")["status"] == "cancelled"
        assert tomes._draft_tids() == {"rune-bound"}

        # A second server must not offer a live harness as resumable.
        forge.list_active_builds = lambda proc_root="/proc": active
        assert forge.list_workings() == [], forge.list_workings()

        # Once the process is gone, a failed/cancelled result is resumable even if a
        # premature legacy ground-truth heading exists; a durable done result is not.
        forge.list_active_builds = lambda proc_root="/proc": []
        with open(os.path.join(build, "untitled-5.plan.md"), "a", encoding="utf-8") as f:
            f.write("\n## Harness ground truth\n")
        workings = forge.list_workings()
        assert len(workings) == 1 and workings[0]["tome"] == "rune-bound", workings
        state.record_build_result("untitled-5", "rune-bound", "done", 8)
        assert tomes._draft_tids() == set()
        assert forge.list_workings() == []
    finally:
        forge.list_active_builds = original
        forge.jobs.clear()
        forge.jobs.update(old_jobs)
        forge.BUILD_DIR, state.BUILD_DIR, tomes.BUILD_DIR = old_build, old_state_build, old_tomes_build
        forge.TOMES_DIR, tomes.TOMES_DIR = old_forge_tomes, old_tomes_tomes

print("forge process discovery: OK")
