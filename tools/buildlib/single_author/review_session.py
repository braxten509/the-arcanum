"""Independent-review lifecycle for a single-author session."""
import os

from .. import BUILD_DIR
from ..course_map.adopt import adopt_build
from ..measure import validate_every_section, validate_live_smoke, validate_shipping
from .full_review import evidence_path, prompt as review_prompt, validate_report
from .gate import context
from .scope import profile_paths
from .session.support import append_conversation as _append_conversation


# Two identical reports after the first mean two paid passes moved nothing. One
# repeat can be a reviewer that misread the report; three is just spending.
STALLED_REVIEW_PASSES = 2


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

    def _await_reviewer_controls(self, retrying=False):
        while True:
            control = self.controls.get()
            if control.get("type") == "stop":
                self.stop = True
                return None
            if control.get("type") not in ("message", "resume"):
                continue
            switched = self.apply_author(control)
            message = str(control.get("text") or "").strip()
            prompt = review_prompt(self.build_id, self.current_tome())
            if message:
                prompt = message + "\n\n" + prompt
            verb = "Retrying" if retrying else "Resuming"
            text = message or (f"{verb} the thorough full-tome review"
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
            "The optional independent reviewer is starting a thorough full-tome review. "
            "It must read every authored file; sampling is forbidden.")
        last_report, stalled = None, 0
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
                    "all passed.",
                    role="reviewer")
                return 0
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
