#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools")]

"""Durable discovery and status for one interactive tome author."""
import json
import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import arcanum.forge.build_state as state  # noqa: E402
import arcanum.forge as forge  # noqa: E402
import arcanum.authoring.adapters.forge_lifecycle as build_routes  # noqa: E402
from arcanum.catalog import ManifestRepository, TomeCatalogService, TomePaths  # noqa: E402
from arcanum.jobs import JobManager, ProcessStore  # noqa: E402
from arcanum.settings import Settings  # noqa: E402
from runtimes import RuntimeRegistry  # noqa: E402
from arcanum.authoring.adapters.forge_lifecycle import (  # noqa: E402
    _author, _authors, _phase_author, _resume_session_id, _validator)
from arcanum.authoring.read_models.forge_status import ForgeStatusService  # noqa: E402


class JsonHandler:
    def send_json(self, payload, status=200):
        return payload, status


old_active_builds = build_routes.list_active_builds
services = SimpleNamespace(jobs=JobManager(), processes=ProcessStore(), catalog=None)
try:
    build_routes.list_active_builds = lambda _jobs, _catalog: [{"id": "live"}]
    payload, status = build_routes.start_build(JsonHandler(), {}, services)
    assert status == 409 and "abandon the active tome" in payload["error"]
finally:
    build_routes.list_active_builds = old_active_builds

payload, status = build_routes.discard_build(
    JsonHandler(), {"id": "draft-one"}, services)
assert status == 400 and "confirmation is required" in payload["error"]

current = {"role": "author", "kind": "codex-cli", "model": "terra",
           "phase": 3, "section": "s05", "sessionId": "same-unit"}
assert _resume_session_id(current, {"kind": "codex-cli", "model": "terra"},
                          3, "s05") == "same-unit"
assert not _resume_session_id(current, {"kind": "codex-cli", "model": "terra"},
                              3, "s06")
assert not _resume_session_id(current, {"kind": "codex-cli", "model": "sol"},
                              3, "s05")
assert not _resume_session_id({**current, "actualModel": "sol"},
                              {"kind": "codex-cli", "model": "terra"}, 3, "s05")
assert _resume_session_id({**current, "actualModel": "terra"},
                          {"kind": "codex-cli", "model": "terra"}, 3, "s05") == "same-unit"
assert not _resume_session_id({"kind": "codex-cli", "model": "terra",
                               "sessionId": "legacy-no-scope"},
                              {"kind": "codex-cli", "model": "terra"}, 3, "s05")


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

    settings = Settings(temp, os.path.join(temp, "web"), tome_root,
                        os.path.join(temp, "cache"), build_root,
                        os.path.join(temp, "skins"),
                        os.path.join(temp, "settings.toml"), 8777)
    paths = TomePaths(settings)
    catalog = TomeCatalogService(paths, ManifestRepository(paths),
                                 RuntimeRegistry.from_root(temp))
    old = (forge.BUILD_DIR, state.BUILD_DIR)
    try:
        job_manager = JobManager()
        forge.BUILD_DIR = state.BUILD_DIR = build_root
        found = forge._live_build_processes(proc_root)
        assert [row["planid"] for row in found] == ["untitled-5"]
        assert state.BUILD_TOTAL_PHASES == 8
        assert state.load_build_progress("untitled-5")["phase"] == 4
        assert state.load_author_session("untitled-5")["state"] == "paused"
        active = forge.list_active_builds(job_manager, catalog, proc_root)
        assert active[0]["tome"] == "rune-bound" and active[0]["phase"] == 4
        job_manager.create("build", job_id="local-job", tome="untitled-5",
                           slug="untitled-5", phase=1, phaseTitle="starting")
        active = forge.list_active_builds(job_manager, catalog, proc_root)
        assert len(active) == 1 and not active[0]["external"]
        assert active[0]["tome"] == "rune-bound" and active[0]["phase"] == 4
        assert _author({"author": {"kind": "opencode-cli",
                                   "model": "ollama/llama3.2:3b"}})
        routed = _authors({"authors": {
            "phase12": {"kind": "codex-cli", "model": "arc"},
            "phase37": {"kind": "claude-cli", "model": "build", "effort": "high"},
            "phase8": {"kind": "opencode-cli", "model": "finish"},
        }})
        assert _phase_author(routed, 2)["model"] == "arc"
        assert _phase_author(routed, 3)["model"] == "build"
        assert _phase_author(routed, 8)["model"] == "finish"
        legacy = _authors({"author": {"kind": "codex-cli", "model": "one"}})
        assert {row["model"] for row in legacy.values()} == {"one"}
        assert _validator({"validator": {"kind": "claude-cli",
                                          "model": "section-audit"}})["model"] == "section-audit"

        # A validator-infrastructure pause retries the VALIDATOR, not the author: the swap
        # rewrites the launch record the gate re-reads and leaves the author session alone.
        with open(os.path.join(build_root, "untitled-5.launch.json"), "w",
                  encoding="utf-8") as handle:
            json.dump({"author": {"kind": "codex-cli", "model": "sol"},
                       "validator": {"kind": "codex-cli", "model": "old-judge"},
                       "concept": "A PyGame RPG.", "gate": {"depth": "3"}}, handle)
        sent = []
        services.jobs = job_manager
        services.processes.put("local-job", SimpleNamespace(
            stdin=SimpleNamespace(write=sent.append, flush=lambda: None)))
        payload, code = build_routes.control_author(
            JsonHandler(), {"id": "local-job",
                            "validator": {"kind": "claude-cli", "model": "new-judge"}},
            "resume", services)
        assert code == 200 and payload["ok"], payload
        assert json.loads(sent[0]) == {"type": "resume"}
        saved = forge._load_launch("untitled-5")
        assert saved["validator"] == {"kind": "claude-cli", "model": "new-judge",
                                      "effort": ""}
        assert saved["author"]["model"] == "sol" and saved["gate"]["depth"] == "3"
        # The status read model reports the swapped validator straight from the launch
        # record, so it is right after a server restart and for reattached builds too.
        status_reader = ForgeStatusService(settings, job_manager, catalog)
        live = status_reader.get("local-job")
        assert live["sessionValidator"]["model"] == "new-judge"
        assert live["sessionGate"] == "" and live["sessionRole"] == "author"

        # The visible timer measures only the current author work interval.
        assert forge.author_activity_started_at("paused", "starting", 55, now=100) == 100
        assert forge.author_activity_started_at("starting", "running", 100, now=101) == 100
        assert forge.author_activity_started_at("running", "validating", 100, now=102) == 0
        assert forge.author_activity_started_at("running", "starting", 100, now=103) == 103

        # Discard/reuse cleanup owns the complete build namespace, including sealed maps,
        # snapshots, course evidence, and future sidecars unknown to older cleanup lists.
        stale = os.path.join(build_root, "untitled-6.course-map.json")
        unrelated = os.path.join(build_root, "untitled-60.course-map.json")
        with open(stale, "w", encoding="utf-8") as handle:
            handle.write("{}")
        with open(unrelated, "w", encoding="utf-8") as handle:
            handle.write("{}")
        evidence = os.path.join(build_root, "untitled-6.course-evidence")
        os.makedirs(evidence)
        with open(os.path.join(evidence, "s01.json"), "w", encoding="utf-8") as handle:
            handle.write("{}")
        forge._clear_build_terminal_state("untitled-6")
        assert not os.path.exists(stale) and not os.path.exists(evidence)
        assert os.path.exists(unrelated)
    finally:
        forge.BUILD_DIR, state.BUILD_DIR = old

print("single-author process discovery: OK")
