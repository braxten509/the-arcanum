#!/usr/bin/env python3
"""Binder checkpoints, rollback, and AI invocation boundaries are recoverable."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from arcanum.authoring import amender
from arcanum.authoring.amendment import gate, prompts
from arcanum.authoring.services import binder as binder_service
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


class DeferredThread:
    instances = []

    def __init__(self, target, args, daemon):
        self.target, self.args, self.daemon = target, args, daemon
        self.instances.append(self)

    def start(self):
        pass


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
            patch.object(gate, "ROOT", str(root)), \
            patch.object(gate, "BUILD_DIR", str(build_root)), \
            patch.object(prompts, "ROOT", str(root)), \
            patch.object(amender, "notify", lambda *_args, **_kwargs: None):
        validator_commands = []
        with patch.object(
                gate.subprocess, "run",
                lambda command, **_kwargs: (
                    validator_commands.append(command)
                    or SimpleNamespace(args=command, returncode=0, stdout="", stderr=""))):
            amender._validate_amendment("demo", strict=True)
        # This build has no sealed plan, so it has no map or continuity contract to be
        # measured against — and must not be failed for lacking one.
        assert validator_commands == [[
            sys.executable, str(root / "tools" / "validate_tome.py"),
            "tomes/demo", "--strict",
        ]]

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

        # A build that does carry a plan has contracts to keep: its continuity handoffs are
        # mounted writable, because the strict gate blocks on a blank one and only whoever
        # edits the sections can know what it should say.
        (build_root / "demo.plan.md").write_text("# BUILD PLAN — demo\n", encoding="utf-8")
        (build_root / "demo.handoffs").mkdir()

        capturing = CapturingAi()
        complete = jobs.create("binder-amend", tome="demo")
        validation_calls = []
        with patch.object(amender, "_run_agent_turn",
                          lambda *_args, **_kwargs: (0, False, ["no changes needed"])), \
                patch.object(
                    amender, "_validate_amendment",
                    lambda jid, strict=False: (
                        validation_calls.append((jid, strict))
                        or SimpleNamespace(returncode=0, stdout="", stderr=""))):
            amender.run_amender(
                complete["id"], "demo", "is it already correct?", "fixed", "model",
                broad=True, update_standard=True,
                job_manager=jobs, processes=ProcessStore(), ai=capturing)
        request = capturing.request
        assert request.role == "binder-amend" and request.workspace == str(tome)
        assert request.writable_paths == (str(tome), str(build_root / "demo.handoffs"))
        assert request.permission_paths is not None
        assert request.state_scope == {
            "build_id": complete["id"], "role": "binder-amend",
            "phase": 7, "section": "",
        }
        assert request.web_allowed and {"read", "write", "shell"} <= set(request.allowed_tools)
        assert "STANDARD UPDATE" in request.input
        assert "current validator and current Markdown instructions as authoritative" in request.input
        assert "if the tome is already current" in request.input
        assert "Never add or partially imitate an opt-in contract" in request.input
        assert "trusted repository generator may update its own generated output" in request.input
        assert "`python3 tools/validate_tome.py tomes/demo --strict`" in request.input
        # validate_tome does no sealed-map alignment and pools every section, so naming only
        # it taught the Binder to certify its work against a gate blind to half the contract.
        assert "validate_phase3.py tomes/demo" in request.input
        assert "validate_section.py tomes/demo sNN" in request.input
        assert "CONTINUITY HANDOFFS" in request.input
        assert "artifact_state" in request.input
        assert "sealed course map is mounted read-only" in request.input
        assert validation_calls == [("demo", True)]
        assert jobs.status(complete["id"])["status"] == "done"
        assert not (build_root / "binder-checkpoints" / "demo").exists()

        # The job store is in memory, so what a run did is written where a restart cannot
        # take it: twice now "did it retry, and what did it cost?" has been unanswerable.
        ledger = json.loads((build_root / "demo.amend-log.json").read_text(encoding="utf-8"))
        assert [row["jobId"] for row in ledger] == [failed["id"], complete["id"]], ledger
        assert ledger[0]["status"] == "error" and ledger[1]["status"] == "done", ledger
        assert ledger[1]["mode"] == "broad" and ledger[1]["continuations"] == 0, ledger[1]
        assert ledger[1]["finishedAt"] >= ledger[1]["startedAt"] > 0, ledger[1]

        review_ai = CapturingAi()
        review_job = jobs.create("binder-amend", tome="demo", review=True)
        with patch.object(
                amender, "_run_agent_turn",
                lambda *_args, **_kwargs: (0, False, ["review complete"])):
            amender.run_amender(
                review_job["id"], "demo", "", "fixed", "model", review=True,
                job_manager=jobs, processes=ProcessStore(), ai=review_ai)
        review_prompt = review_ai.request.input
        assert review_ai.request.role == "binder-review"
        assert "FIRST substantive section MUST be `## Recommendation and implementation order`" \
            in review_prompt
        assert "EVERY material recommended workstream" in review_prompt
        assert "Rank learner privacy, correctness, teaching integrity" in review_prompt
        assert "Recommend broad correction when the evidence warrants it" in review_prompt
        assert "label finding-specific actions `Remediation`" in review_prompt
        assert "End with one short paragraph" not in review_prompt
        # A review may only read -- so it must read the gate's verdict too. Naming no gate
        # is how a survey reports "validator clean" on a tome the shipping gate rejects.
        assert "MEASURE the tome" in review_prompt
        assert "validate_phase3.py tomes/demo" in review_prompt
        assert "validate_section.py tomes/demo sNN" in review_prompt
        history = amender.review_history("demo")
        assert len(history["reviews"]) == 1, history
        historical = history["reviews"][0]
        assert historical["providerKind"] == "fixed"
        assert historical["providerModel"] == "model"
        report_file = root / historical["path"]
        report_file.write_text(
            "# Demo review\n\n## Recommendation and implementation order\n\n"
            "Repair the boundary first.\n\n## Findings\n\nDetails.\n",
            encoding="utf-8")
        detail = amender.review_history("demo", historical["path"])
        assert detail["content"].startswith("# Demo review"), detail
        assert "Repair the boundary first." in detail["summary"], detail
        assert amender.review_history("demo", "../reviews/not-demo.md") == {}

        strict_failures = []
        failed_standard = jobs.create("binder-amend", tome="demo")
        with patch.object(
                amender, "_run_agent_turn",
                lambda *_args, **_kwargs: (0, False, ["repair attempted"])), \
                patch.object(
                    amender, "_validate_amendment",
                    lambda jid, strict=False: (
                        strict_failures.append((jid, strict))
                        or SimpleNamespace(
                            returncode=1, stdout="-- demo: 0 error(s), 1 warning(s)",
                            stderr=""))):
            amender.run_amender(
                failed_standard["id"], "demo", "", "fixed", "model",
                broad=True, update_standard=True,
                job_manager=jobs, processes=ProcessStore(), ai=CapturingAi())
        failed_status = jobs.status(failed_standard["id"])
        assert failed_status["status"] == "error"
        assert "strict standard validator still fails" in failed_status["error"]
        assert strict_failures == [("demo", True), ("demo", True)]
        assert not (build_root / "binder-checkpoints" / "demo").exists()

        states = []
        with patch.object(binder_service, "save_amend_state", states.append), \
                patch.object(binder_service.threading, "Thread", DeferredThread):
            service = binder_service.BinderService(JobManager(), ProcessStore(), CapturingAi())
            refused, status = service.start("demo", {
                "request": "", "broad": False, "updateStandard": True,
            })
            assert status == 400 and not refused["ok"]
            accepted, status = service.start("demo", {
                "request": "", "kind": "fixed", "model": "model",
                "broad": True, "updateStandard": True,
            })
            assert status == 200 and accepted["ok"]
            assert states[-1]["updateStandard"] is True
            assert DeferredThread.instances[-1].args[11] is True

            review_service = binder_service.BinderService(
                JobManager(), ProcessStore(), CapturingAi())
            refused_review, status = review_service.start("demo", {
                "request": "apply it", "kind": "fixed", "model": "model",
                "reviewPath": "reviews/another-tome-20260724-000000.md",
            })
            assert status == 400 and not refused_review["ok"]
            applied, status = review_service.start("demo", {
                "request": "apply it", "kind": "fixed", "model": "model",
                "reviewPath": historical["path"],
                "broad": False, "updateStandard": False, "iterate": True,
            })
            assert status == 200 and applied["ok"]
            application_args = DeferredThread.instances[-1].args
            assert application_args[6] is True       # broad
            assert application_args[7] is False      # iterate
            assert application_args[10] == historical["path"]
            assert application_args[11] is True      # update standard

print("Binder checkpoint, rollback, and invocation tests: OK")
