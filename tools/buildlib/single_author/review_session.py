"""Independent-review and publication lifecycle for a single-author session."""
import os
import time

from arcanum.authoring.amendment.prompts import publish_prompt
from arcanum.authoring.amendment.publish import report_path, verdict
from arcanum.authoring.amendment.storage import save_review_metadata

from .. import BUILD_DIR, REPO
from ..continuity import handoff_dir
from ..course_map.adopt import adopt_build
from ..measure import validate_every_section, validate_live_smoke, validate_shipping
from .full_review import evidence_path, prompt as review_prompt, validate_report
from .gate import context
from .scope import profile_paths
from .session.support import append_conversation as _append_conversation


# Two identical reports after the first mean two paid passes moved nothing. One
# repeat can be a reviewer that misread the report; three is just spending.
STALLED_REVIEW_PASSES = 2

# NOT-READY publication surveys before the build stops and asks for a person.
# publisher.md says a defect three repair turns could not clear is one someone
# should look at, and each pass here costs a survey turn plus a reviewer turn.
PUBLICATION_PASSES = 3


def append_conversation(build_id, kind, text, **extra):
    return _append_conversation(BUILD_DIR, build_id, kind, text, **extra)


class ReviewerSessionMixin:
    def _review_writable(self):
        tid = self.current_tome()
        from ..measure import selected_runtime_config
        runtime = selected_runtime_config(tid)
        profile = profile_paths("reviewer", build_id=self.build_id, tome_id=tid,
                                phase=8, runtime_id=runtime or "")
        return [*profile["write"], *profile["both"]]

    def _review_turn(self, prompt, conversation_kind="harness", conversation_text=""):
        original = self._writable
        original_permissions = self._permission_paths
        self._writable = self._review_writable
        self._permission_paths = self._review_permission_paths
        try:
            return self.run_turn(prompt, conversation_kind, conversation_text)
        finally:
            self._writable = original
            self._permission_paths = original_permissions

    def _review_permission_paths(self):
        tid = self.current_tome()
        from ..measure import selected_runtime_config
        return profile_paths("reviewer", build_id=self.build_id, tome_id=tid, phase=8,
                             runtime_id=selected_runtime_config(tid) or "")

    def _survey_turn(self, prompt, report_abs, tid, conversation_kind, conversation_text):
        """One publication survey: a fresh session that may write only its own report.

        Everything here is about independence. The survey is the last thing standing
        between a build and a learner, and a pass that can edit what it is grading, or
        that carries the repairing session's own context, is the author marking its own
        homework with extra steps.

        ponytail: the role stays "reviewer", so the survey shares the reviewer's provider
        state directory and could in principle read its session store. Clearing the session
        id is what actually keeps the context out of the survey's window; give the survey
        its own role if that store ever needs to be blind too.
        """
        from ..measure import selected_runtime_config
        runtime = selected_runtime_config(tid) or ""
        original = (self._writable, self._readonly, self._permission_paths, self.session_id)
        self._writable = lambda: [report_abs]
        self._readonly = lambda: []
        self._permission_paths = lambda: {
            **profile_paths("publisher", build_id=self.build_id, tome_id=tid, phase=8,
                            runtime_id=runtime),
            # The profile cannot name this: the report is per-pass and its name carries a
            # timestamp. It is the one path the survey may write, and it already exists,
            # because a mount with no file at it is dropped rather than created.
            "write": [report_abs]}
        self.session_id = ""
        try:
            return self.run_turn(prompt, conversation_kind, conversation_text)
        finally:
            (self._writable, self._readonly,
             self._permission_paths, self.session_id) = original

    def _survey_prompt(self, tid, report_rel, rnd, previous=""):
        plan = os.path.join(BUILD_DIR, f"{self.build_id}.plan.md")
        folder = handoff_dir(tid)
        return publish_prompt(
            tid, "", survey=True, report_rel=report_rel,
            plan_rel=(os.path.relpath(plan, REPO).replace(os.sep, "/")
                      if os.path.isfile(plan) else ""),
            handoffs=folder if os.path.isdir(folder) else "",
            rnd=rnd, rounds=PUBLICATION_PASSES, previous=previous)

    def run_publication_survey(self, tid, rnd, previous=""):
        """Judge the finished tome against publisher.md.

        Returns ``(ready, report_rel, report_text)``; ``ready`` is None when the operator
        stopped the build. Runs only after every mechanical gate is already clean, so a
        READY verdict means the judgement and the machine agree -- which is the whole
        publication bar, and the reason the survey is not asked to run first.
        """
        report_rel, report_abs = report_path(tid)
        prompt = self._survey_prompt(tid, report_rel, rnd, previous)
        conversation_kind, conversation_text = "harness", (
            f"Publication survey {rnd} of {PUBLICATION_PASSES}: every mechanical gate is "
            f"clean, so an independent read-only pass is now measuring the finished tome "
            f"against publisher.md and writing its verdict to {report_rel}.")
        while not self.stop:
            self.state("validating", stage="publication-survey")
            outcome, message = self._survey_turn(
                prompt, report_abs, tid, conversation_kind, conversation_text)
            if outcome == "stopped":
                return None, report_rel, ""
            if outcome == "message":
                prompt = message + "\n\n" + self._survey_prompt(tid, report_rel, rnd, previous)
                conversation_kind, conversation_text = "user", message
                continue
            report = ""
            if outcome == "complete":
                with open(report_abs, encoding="utf-8") as handle:
                    report = handle.read().strip()
                if report:
                    save_review_metadata(REPO, report_rel, {
                        "version": 1, "tome": tid, "path": report_rel,
                        "completedAt": time.time(), "providerKind": self.kind,
                        "providerModel": self.actual_model or self.model,
                        "effort": self.effort})
                    return verdict(report), report_rel, report
                # A turn that ended cleanly without writing a verdict has judged nothing.
                # Treating a blank file as NOT READY would buy a repair turn against an
                # empty findings list, so this waits for a person instead.
                message = ("The publication survey finished without writing a verdict to "
                           f"{report_rel}. Resume it, or pick another AI to survey the "
                           "tome in a fresh session.")
            error = message if outcome != "paused" else ""
            self.state("paused", **({"error": error} if error else {}))
            if error:
                append_conversation(self.build_id, "harness", error, role="reviewer")
            resumed = self._await_reviewer_controls(
                retrying=outcome != "paused",
                make_prompt=lambda: self._survey_prompt(tid, report_rel, rnd, previous),
                what=f"publication survey {rnd}")
            if resumed is None:
                return None, report_rel, ""
            prompt, conversation_kind, conversation_text = resumed
        return None, report_rel, ""

    def _await_reviewer_controls(self, retrying=False, make_prompt=None,
                                 what="thorough full-tome review"):
        while True:
            control = self.controls.get()
            if control.get("type") == "stop":
                self.stop = True
                return None
            if control.get("type") not in ("message", "resume"):
                continue
            switched = self.apply_author(control)
            message = str(control.get("text") or "").strip()
            prompt = (make_prompt() if make_prompt
                      else review_prompt(self.build_id, self.current_tome()))
            if message:
                prompt = message + "\n\n" + prompt
            verb = "Retrying" if retrying else "Resuming"
            text = message or (f"{verb} the {what}"
                               + (f" with {self.kind} {self.model} in a fresh session."
                                  if switched else "."))
            return prompt, ("user" if message else "harness"), text

    def run_reviewer(self):
        if not self.reviewer:
            return 0
        self.kind, self.model, self.effort = self.reviewer
        self.session_id = ""
        self.role = "reviewer"
        tid = self.current_tome()
        # Truncate rather than delete. The permission profile mounts named files, and
        # a path with nothing at it is dropped instead of mounted, so deleting the
        # packet is what stops the reviewer writing it. An empty object clears any
        # stale pass and still fails validate_report, so nothing is waved through.
        with open(evidence_path(self.build_id), "w", encoding="utf-8") as handle:
            handle.write("{}\n")
        # A build finished before the map and handoff contracts existed fails every
        # gate on missing files the reviewer is not allowed to create. Materialize
        # them first so the review is graded on the tome, not on the build's age.
        try:
            for note in adopt_build(self.build_id, tid):
                append_conversation(self.build_id, "harness",
                                    f"Adopted this pre-contract build: {note}", role="reviewer")
        except Exception as exc:
            append_conversation(
                self.build_id, "harness",
                f"This build is missing harness artifacts that could not be reconstructed "
                f"from the tome ({exc}). The review will run, but its mechanical "
                f"double-check cannot pass until that is resolved.", role="reviewer")
        prompt = review_prompt(self.build_id, tid)
        conversation_kind, conversation_text = "harness", (
            "The independent reviewer is starting a thorough full-tome review. "
            "It must read every authored file; sampling is forbidden. Once every "
            "mechanical gate is clean, a separate read-only survey decides whether the "
            "tome is fit to publish.")
        last_report, stalled, surveys, survey_notes = None, 0, 0, ""
        while not self.stop:
            outcome, message = self._review_turn(prompt, conversation_kind, conversation_text)
            if outcome == "stopped":
                break
            if outcome == "message":
                prompt = (
                    message
                    + "\n\nRespond to the operator, then continue the exact exhaustive review "
                    "that was interrupted in this same session. Preserve the existing review "
                    "packet and progress; do not restart discovery."
                )
                conversation_kind, conversation_text = "user", message
                continue
            if outcome in ("paused", "failed"):
                error = ("The reviewer CLI exited unexpectedly. Resume it, or pick another "
                         "AI to continue the exhaustive review in a fresh session.") \
                    if outcome == "failed" else ""
                self.state("paused", **({"error": error} if error else {}))
                if error:
                    append_conversation(self.build_id, "harness", "\n\n".join(
                        part for part in (error, message) if part))
                resumed = self._await_reviewer_controls(retrying=outcome == "failed")
                if resumed is None:
                    break
                prompt, conversation_kind, conversation_text = resumed
                continue
            self.state("validating", stage="full-review")
            tid = self.current_tome()
            evidence_ok, evidence_report = validate_report(self.build_id, tid)
            ctx = context(self.build_id)
            shipping_ok, shipping = validate_shipping(tid, ctx["tooling"], ctx["plan"])
            # Run the per-section sweep even when the tome-wide pass already failed.
            # Validators are cheap; a reviewer turn re-reads every authored file, so
            # handing back one complete report beats discovering the next defect a
            # turn later.
            sections_ok, sections = validate_every_section(tid, ctx["tooling"], ctx["plan"])
            smoke_ok, smoke = (validate_live_smoke(tid)
                               if shipping_ok and sections_ok else (False, ""))
            if evidence_ok and shipping_ok and sections_ok and smoke_ok:
                append_conversation(
                    self.build_id, "harness",
                    "The thorough full-tome review covered every authored file, and "
                    "strict shipping, every per-section gate, and live-smoke verification "
                    "all passed. The tome now goes to the publication survey.",
                    role="reviewer")
                surveys += 1
                ready, report_rel, survey = self.run_publication_survey(
                    tid, surveys, survey_notes)
                if ready is None:
                    break
                if ready:
                    append_conversation(
                        self.build_id, "harness",
                        f"Publication survey {surveys} of {PUBLICATION_PASSES} signed the "
                        f"tome off against publisher.md, and every mechanical gate agrees. "
                        f"It is ready to publish — the report is at {report_rel}.",
                        role="reviewer")
                    return 0
                if surveys >= PUBLICATION_PASSES:
                    self.state("paused", error=(
                        f"The tome passed every mechanical gate but {PUBLICATION_PASSES} "
                        f"publication surveys still found blockers, so it is not "
                        f"converging on the bar in publisher.md. Read {report_rel} and fix "
                        f"the outstanding findings by hand, or stop the build."))
                    append_conversation(self.build_id, "harness", "\n\n".join((
                        f"Stopping after {surveys} publication surveys.", survey)),
                        role="reviewer")
                    return 130
                # Feeds the NEXT survey, not this repair turn -- so a finding the reviewer
                # answered with a reason is settled instead of being raised again forever.
                survey_notes = (
                    "A previous publication survey found blockers and a repair pass "
                    "followed it. Anything that pass declined with a stated reason is "
                    "settled; do not raise it again unless you can say concretely why "
                    "the reason is wrong.\n\n")
                report = ("THE PUBLICATION SURVEY FOUND BLOCKERS. Every mechanical gate is "
                          "clean, so this is the only thing between the tome and a learner. "
                          "Its `## Blockers` section is your assignment; its `## Polish (not "
                          "blocking)` section is not. If a blocker is not real, say so in "
                          "your closing paragraph rather than manufacturing a change.\n\n"
                          + survey)
                prompt = review_prompt(self.build_id, tid, report)
                conversation_kind, conversation_text = "harness", (
                    f"Publication survey {surveys} of {PUBLICATION_PASSES} returned NOT "
                    f"READY. Its blockers went back to the same reviewer session.")
                continue
            report = "\n\n".join(part for part in (
                "REVIEW COVERAGE: " + evidence_report,
                "STRICT SHIPPING:\n" + shipping if not shipping_ok else "",
                "PER-SECTION GATES:\n" + sections if not sections_ok else "",
                "LIVE SMOKE:\n" + smoke if shipping_ok and sections_ok and not smoke_ok else "",
            ) if part)
            # Every retry costs a full read of every authored file. A report identical
            # to the last one means the pass changed nothing the gate can see, which is
            # what a defect outside the reviewer's reach looks like from in here --
            # so stop and say so, rather than buying the same turn until someone notices.
            stalled = stalled + 1 if report == last_report else 0
            last_report = report
            if stalled >= STALLED_REVIEW_PASSES:
                self.state("paused", error=(
                    f"The exhaustive review returned the same unresolved report "
                    f"{stalled + 1} times, so it is not converging. Read it below and "
                    f"fix the blocker outside the review, or stop the build."))
                append_conversation(self.build_id, "harness", "\n\n".join((
                    f"Stopping the review loop after {stalled + 1} identical failures.",
                    report)), role="reviewer")
                return 130
            prompt = review_prompt(self.build_id, tid, report)
            conversation_kind, conversation_text = "harness", (
                "The exhaustive reviewer pass did not clear its mechanical double-check. "
                "The exact report was returned to the same reviewer session.")
        return 130
