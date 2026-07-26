#!/usr/bin/env python3
"""Binder checkpoints, rollback, and AI invocation boundaries are recoverable."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json
import re
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from arcanum.authoring import amender
from arcanum.authoring.amendment import gate, prompts
from arcanum.authoring.amendment import publish as publish_mod
from arcanum.authoring.services import binder as binder_service
from arcanum.jobs import JobManager, ProcessStore


class FailingAi:
    def invocation(self, *_args, **_kwargs):
        raise RuntimeError("provider offline before invocation")


class CapturingAi:
    def __init__(self):
        self.request = None
        self.requests = []   # a run may take more than one turn, each with its own mounts

    def invocation(self, _provider_id, request):
        self.request = request
        self.requests.append(request)
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

        # A note's own detail list stays attached to it. The plan refusal names its first
        # blockers; split apart they reach the feed as eight near-identical cards, and the
        # prompt as "First blockers:" with nothing after it.
        with patch.object(gate, "_run", lambda *_args, **_kwargs: SimpleNamespace(
                returncode=0, stdout="refused because:\n- one\n- two\nadopted nothing\n",
                stderr="")):
            folded, folded_error = gate.sync_contracts("plan", "demo")
        assert folded == ["refused because:\n- one\n- two", "adopted nothing"], folded
        assert not folded_error

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
        # Two rules used to contradict each other: never renumber existing ids, and change
        # the tome when it disagrees with the map. A run followed the second and renumbered
        # a section's lessons. Alignment must now lose, with one narrow, checkable escape.
        assert "OUTRANKS sealed-map alignment" in request.input
        assert "which outrank alignment" in request.input
        assert "tomes/demo/save/ records no progress against the exact ids" in request.input
        assert "never spend a player's progress to make a gate pass" in request.input
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

        # The past-builds panel reads that ledger back, newest first, and leaves the
        # validator dump behind on a clean run -- it is only worth its size on a failure.
        builds = amender.amend_history("demo")
        assert [row["jobId"] for row in builds] == [complete["id"], failed["id"]], builds
        assert builds[0]["status"] == "done" and builds[0]["validator"] == "", builds[0]
        assert amender.amend_history("../demo") == [] == amender.amend_history("absent")
        merged = binder_service.BinderService(
            jobs, ProcessStore(), CapturingAi()).reviews("demo")
        assert merged["builds"] == builds and isinstance(merged["reviews"], list), merged

        # Staying the quill mid-stroke is exactly when the same request is wanted again, so
        # a cancel keeps the resume record instead of deleting it. The tome still rolls back.
        stayed = jobs.create("binder-amend", tome="demo")
        amender.save_amend_state({
            "id": stayed["id"], "tome": "demo", "request": "deepen section two",
            "broad": True, "iterate": True, "status": "running",
        })
        with patch.object(
                amender, "_run_agent_turn",
                lambda *_args, **_kwargs: (
                    jobs.cancel(stayed["id"]) and None) or (0, False, ["stopped"])):
            amender.run_amender(
                stayed["id"], "demo", "deepen section two", "fixed", "model",
                broad=True, iterate=True,
                job_manager=jobs, processes=ProcessStore(), ai=CapturingAi())
        kept = amender.load_amend_state("demo")
        assert kept and kept["status"] == "cancelled", kept
        assert not (build_root / "binder-checkpoints" / "demo").exists()
        offered = binder_service.BinderService(
            jobs, ProcessStore(), CapturingAi()).resumable("demo")["resumable"]
        # The live job knows it was cancelled before the runner writes that to disk, and the
        # bench asks the instant you stop it -- so the job's word wins over the file's.
        assert offered["status"] == "cancelled", offered
        assert offered["request"] == "deepen section two" and offered["iterate"], offered
        amender.clear_amend_state("demo")

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

        # A tome whose own content blocks its plan gets the cause handed to it as work, not
        # reported as an excuse: the refusal reaches the prompt, and the plan is asked for
        # again on the way out — after the validator, because the plan lives outside the
        # rollback checkpoint and must never promise anything about a tome that was undone.
        planless = root / "tomes" / "planless"
        planless.mkdir()
        (planless / "tome.toml").write_text("version = 1\n", encoding="utf-8")
        contract_calls = []

        def fake_sync(action, tome, reason=""):
            contract_calls.append((action, tome))
            if action != "plan":
                return [], ""
            if sum(call[0] == "plan" for call in contract_calls) == 1:
                return ([f"this tome {gate.PLAN_REFUSED}, so it keeps the gate it already "
                         "had: 53 lessons re-teach a capability another lesson introduces"], "")
            # Sealing the plan is what creates the handoffs, and adoption leaves every
            # artifact_state blank rather than inventing an author's prose.
            (build_root / "planless.plan.md").write_text("# BUILD PLAN\n", encoding="utf-8")
            folder = build_root / "planless.handoffs"
            folder.mkdir(exist_ok=True)
            for sid in ("s01", "s02"):
                (folder / f"{sid}.json").write_text(
                    json.dumps({"version": 3, "section": sid, "artifact_state": ""}),
                    encoding="utf-8")
            return ["wrote an adopted build plan at .tome-build/planless.plan.md"], ""

        def fake_turn(_job, _cmd, prompt, *_args, **_kwargs):
            # The scoped fill turn is the only one told to write artifact_state.
            if "artifact_state" in prompt and "CHANGE NOTHING ELSE" in prompt:
                for path in sorted((build_root / "planless.handoffs").glob("*.json")):
                    data = json.loads(path.read_text(encoding="utf-8"))
                    data["artifact_state"] = "The learner's project runs and keeps its report."
                    path.write_text(json.dumps(data), encoding="utf-8")
                fill_prompts.append(prompt)
            return 0, False, ["ids made concrete"]

        fill_prompts = []
        validations = []
        planless_ai = CapturingAi()
        planless_job = jobs.create("binder-amend", tome="planless")
        def fake_validate(jid, strict=False):
            validations.append((bool(gate.plan_rel("planless")),
                                gate.blank_handoffs("planless")))
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch.object(gate, "sync_contracts", fake_sync), \
                patch.object(amender, "_run_agent_turn", fake_turn), \
                patch.object(amender, "_validate_amendment", fake_validate):
            amender.run_amender(
                planless_job["id"], "planless", "", "fixed", "model",
                broad=True, update_standard=True,
                job_manager=jobs, processes=ProcessStore(), ai=planless_ai)
        assert jobs.status(planless_job["id"])["status"] == "done"
        assert contract_calls == [
            ("plan", "planless"), ("reseal", "planless"), ("plan", "planless")], contract_calls
        blocked = planless_ai.requests[0].input
        assert "THIS TOME HAS NO BUILD PLAN" in blocked
        assert "53 lessons re-teach a capability another lesson introduces" in blocked
        assert f"this tome {gate.PLAN_REFUSED}" not in blocked  # the cause, not the excuse
        assert "Capability ids are not progress keys" in blocked
        assert "never by renumbering, merging, or removing lessons" in blocked
        assert "Never write under .tome-build/ yourself" in blocked
        # A tome that already has its plan is not told any of this.
        assert "THIS TOME HAS NO BUILD PLAN" not in request.input
        # The handoffs the seal just created cannot be written by a sandbox that ended
        # before they existed, so one scoped turn writes them and only them.
        assert len(fill_prompts) == 1, fill_prompts
        assert "s01, s02" in fill_prompts[0]
        assert "Do not edit any file under tomes/" in fill_prompts[0]
        assert not gate.blank_handoffs("planless")
        assert planless_ai.requests[-1].writable_paths == (str(build_root / "planless.handoffs"),), \
            "the fill turn must mount the handoffs and nothing else"
        # And the tome is re-measured afterwards. The first pass graded it before it had a
        # plan at all -- reporting THAT as the verdict would call it clean against a
        # contract it was never held to.
        assert validations == [(False, []), (True, [])], validations

        # PUBLISH MODE. Two turns per round with different mounts, because one turn that both
        # judged a tome and repaired it would be grading its own homework. The harness re-runs
        # the gate itself after every survey and OUTRANKS the verdict: round one signs the tome
        # off while the gate is still failing, and the loop must refuse to publish it.
        publish_rounds = []

        def publish_turn(_job, _cmd, prompt, *_args, **_kwargs):
            found = re.search(r"reviews/demo-\d{8}-\d{6}\.md", prompt)
            publish_rounds.append(prompt)
            if "SURVEY turn" in prompt:
                (root / found.group(0)).write_text(
                    "## Blockers\n\n- none seen\n\nPUBLISH VERDICT: READY\n", encoding="utf-8")
            else:
                (tome / "lesson.toml").write_text(
                    f"mended {len(publish_rounds)}\n", encoding="utf-8")
            return 0, False, ["turn complete"]

        publish_ai = CapturingAi()
        publish_job = jobs.create("binder-amend", tome="demo")
        publish_gates = [SimpleNamespace(returncode=1, stdout="s03 answers cluster on index 1",
                                         stderr=""),
                         SimpleNamespace(returncode=0, stdout="", stderr="")]

        def fake_publish_gate(_tome, strict=False, on_step=None):
            # The gate takes minutes. Whatever it reports as it goes has to reach the feed,
            # or the pane goes dark between the survey's verdict and the harness's and the
            # run is indistinguishable from a hang.
            on_step("re-checking section 3 of 13 (s03)")
            return publish_gates.pop(0)
        with patch.object(publish_mod, "ROOT", str(root)), \
                patch.object(publish_mod, "BUILD_DIR", str(build_root)), \
                patch.object(gate, "sync_contracts", lambda *_a, **_k: ([], "")), \
                patch.object(gate, "validate_amendment", fake_publish_gate), \
                patch.object(amender, "_run_agent_turn", publish_turn):
            amender.run_amender(
                publish_job["id"], "demo", "", "fixed", "model", publish=True,
                job_manager=jobs, processes=ProcessStore(), ai=publish_ai)
        published = jobs.status(publish_job["id"])
        assert published["status"] == "done" and published["validatorOk"] is True, published
        assert "ready to publish" in published["summary"], published["summary"]
        assert any("re-checking section 3 of 13" in line for line in published["log"]), \
            published["log"]
        assert [request.role for request in publish_ai.requests] == [
            "binder-publish-survey", "binder-publish-mend", "binder-publish-survey"], publish_ai.requests
        # A survey that can edit the tome is not a survey. A mend turn that can rewrite its
        # own report card is not a repair. The mounts are what make the split real.
        first_report = re.search(r"reviews/demo-\d{8}-\d{6}\.md", publish_rounds[0]).group(0)
        assert publish_ai.requests[0].writable_paths == (str(root / first_report),), \
            publish_ai.requests[0].writable_paths
        assert publish_ai.requests[1].writable_paths == (
            str(tome), str(build_root / "demo.handoffs")), publish_ai.requests[1].writable_paths
        assert "SURVEY turn of round 1 of at most 4" in publish_rounds[0]
        assert "publisher.md" in publish_rounds[0] and "PUBLISH VERDICT: READY" in publish_rounds[0]
        assert "MEND turn of round 1 of at most 4" in publish_rounds[1]
        # The gate's own words reach the turn that has to act on them, and publish is never
        # allowed the progress-resetting mandate no matter what the survey asks for.
        assert "s03 answers cluster on index 1" in publish_rounds[1]
        assert "never rename, renumber, remove, or reorder EXISTING ids" in publish_rounds[1]
        assert "AUTHORIZED a progress-resetting rework" not in publish_rounds[1]
        assert not publish_gates, "both gate verdicts must have been consumed"
        assert not (build_root / "binder-checkpoints" / "demo").exists()
        assert amender.amend_history("demo")[0]["mode"] == "publish", amender.amend_history("demo")[0]

        # Only a stopped run can be struck from the ledger: a finished run's row is the sole
        # surviving proof of what it changed and what it cost. Each stopped row also carries
        # the request that started it, because the one-per-tome state file only holds the last.
        forgetter = binder_service.BinderService(jobs, ProcessStore(), CapturingAi())
        stopped = [row for row in amender.amend_history("demo") if row["unfinished"]]
        assert [row["jobId"] for row in stopped] == [
            failed_standard["id"], stayed["id"], failed["id"]], stopped
        assert stopped[1]["setup"]["request"] == "deepen section two", stopped[1]
        assert stopped[1]["setup"]["iterate"] is True, stopped[1]
        refused_forget, code = forgetter.forget("demo", complete["id"])
        assert code == 404 and not refused_forget["ok"], refused_forget
        assert [row["jobId"] for row in amender.amend_history("demo")].count(complete["id"]) == 1
        amender.save_amend_state({"id": stayed["id"], "tome": "demo", "status": "cancelled"})
        dropped, code = forgetter.forget("demo", stayed["id"])
        assert code == 200 and dropped["ok"], dropped
        # The state file pointed at the deleted run; leaving it would offer the row back.
        assert not amender.load_amend_state("demo")
        assert stayed["id"] not in [row["jobId"] for row in amender.amend_history("demo")]

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
            assert application_args[12] is False     # publish

            # Publish is a loop of its own, not a modifier, and the bench hides every other
            # box while it is ticked. The server clears them anyway rather than trusting a
            # body that arrives with a stale one -- including the box that wipes progress.
            publish_service = binder_service.BinderService(
                JobManager(), ProcessStore(), CapturingAi())
            queued, status = publish_service.start("demo", {
                "request": "", "kind": "fixed", "model": "model", "publish": True,
                "iterate": True, "resetOk": True, "updateStandard": True,
            })
            assert status == 200 and queued["ok"], queued
            publish_args = DeferredThread.instances[-1].args
            assert publish_args[6] is True           # broad: a publish run reaches the tome
            assert publish_args[7] is False          # iterate
            assert publish_args[8] is False          # reset ok -- never, in publish
            assert publish_args[11] is False         # update standard
            assert publish_args[12] is True          # publish
            assert states[-1]["publish"] is True and states[-1]["resetOk"] is False, states[-1]


# An Update to Standard run is allowed to carry no request at all. When it does, the prompt
# must not narrate one: an empty "REQUEST:" line plus the is-this-a-question clause reads as
# input that never arrived, and the Binder stops to ask for it instead of doing the work.
_mandate = dict(review=False, iterate=False, broad=True, reset_ok=False, update_standard=True,
                review_path="", report_rel="reviews/x.md", plan_rel="", handoffs="")
_blank = prompts.amend_prompt("demo", "", **_mandate)
assert "REQUEST:" not in _blank, _blank[:400]
assert "actually a QUESTION" not in _blank, _blank[:400]
assert "nothing to ask the player for" in _blank
assert "STANDARD UPDATE" in _blank
_typed = prompts.amend_prompt("demo", "fix the s02 typo", **_mandate)
assert "REQUEST: fix the s02 typo" in _typed
assert "actually a QUESTION" in _typed   # a real request may still turn out to be a question

print("Binder checkpoint, rollback, and invocation tests: OK")
