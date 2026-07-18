#!/usr/bin/env python3
"""Binder checkpoints, rollback, and AI invocation boundaries are recoverable."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from arcanum.authoring import amender
from arcanum.jobs import JobManager, ProcessStore


class FailingAi:
    def invocation(self, *_args, **_kwargs):
        raise RuntimeError("provider offline before invocation")


class CapturingAi:
    def __init__(self):
        self.request = None

    def invocation(self, _provider_id, request):
        self.request = request
        return SimpleNamespace(
            argv=("/usr/bin/true",), input_mode="none", environment={}, cwd=request.workspace)


with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    build_root = root / ".tome-build"
    tome = root / "tomes" / "demo"
    save = tome / "save"
    save.mkdir(parents=True)
    (tome / "tome.toml").write_text("version = 1\n", encoding="utf-8")
    (tome / "lesson.toml").write_text("original\n", encoding="utf-8")
    (save / "state.json").write_text('{"kept":true}\n', encoding="utf-8")

    with patch.object(amender, "ROOT", str(root)), \
            patch.object(amender, "BUILD_DIR", str(build_root)), \
            patch.object(amender, "notify", lambda *_args, **_kwargs: None):
        amender.checkpoint_tome("demo")
        assert not (build_root / "binder-checkpoints" / "demo" / "save").exists()
        (tome / "lesson.toml").write_text("partial edit\n", encoding="utf-8")
        (tome / "extra.toml").write_text("partial\n", encoding="utf-8")
        (save / "state.json").write_text('{"kept":"newer"}\n', encoding="utf-8")
        assert amender.tome_has_changes("demo")
        amender.rollback_tome("demo")
        assert (tome / "lesson.toml").read_text() == "original\n"
        assert not (tome / "extra.toml").exists()
        assert (save / "state.json").read_text() == '{"kept":"newer"}\n'
        assert not (build_root / "binder-checkpoints" / "demo").exists()

        jobs = JobManager()
        failed = jobs.create("binder-amend", tome="demo")
        amender.run_amender(
            failed["id"], "demo", "change it", "fixed", "model",
            job_manager=jobs, processes=ProcessStore(), ai=FailingAi())
        failure = jobs.status(failed["id"])
        assert failure["status"] == "error"
        assert "provider offline before invocation" in failure["error"]
        assert "checkpoint is missing" not in failure["error"]

        capturing = CapturingAi()
        complete = jobs.create("binder-amend", tome="demo")
        with patch.object(amender, "_run_agent_turn",
                          lambda *_args, **_kwargs: (0, False, ["no changes needed"])):
            amender.run_amender(
                complete["id"], "demo", "is it already correct?", "fixed", "model",
                job_manager=jobs, processes=ProcessStore(), ai=capturing)
        request = capturing.request
        assert request.role == "binder-amend" and request.workspace == str(tome)
        assert request.writable_paths == (str(tome),)
        assert request.web_allowed and {"read", "write", "shell"} <= set(request.allowed_tools)
        assert jobs.status(complete["id"])["status"] == "done"
        assert not (build_root / "binder-checkpoints" / "demo").exists()

print("Binder checkpoint, rollback, and invocation tests: OK")
