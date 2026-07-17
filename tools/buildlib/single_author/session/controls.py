"""Pause, resume, message, and author-switch controls for an author session."""

from ..gate import ensure_unit, label, unit_prompt
from .support import author_prompt


class AuthorControlsMixin:
    def apply_author(self, control):
        """Adopt a replacement author sent through the control lane. A different CLI (or
        model) cannot resume the old session, so the switch starts a fresh one."""
        author = control.get("author") or {}
        kind, model = str(author.get("kind") or ""), str(author.get("model") or "")
        if not kind or not model or (kind, model) == (self.kind, self.model):
            return False
        self.kind, self.model, self.effort = kind, model, str(author.get("effort") or "")
        self.session_id = ""
        return True

    def await_controls(self, retrying=False):
        """Block until stop or a message/resume control. Returns the next
        (prompt, conversation_kind, conversation_text), or None on stop."""
        while True:
            control = self.controls.get()
            if control.get("type") == "stop":
                self.stop = True
                return None
            if control.get("type") not in ("message", "resume"):
                continue
            switched = self.apply_author(control)
            message = str(control.get("text") or "").strip()
            unit = ensure_unit(self.build_id, self.from_phase)
            prompt = ((message + "\n\n") if message else "") + unit_prompt(self.build_id, unit)
            if switched:
                prompt = author_prompt(self.build_id, self.concept, self.tooling,
                                       unit.get("phase", self.from_phase)) + "\n\n" + prompt
            verb = "Retrying" if retrying else "Resuming"
            text = message or (
                f"{verb} {label(unit)} with {self.kind} {self.model} in a fresh session."
                if switched else f"{verb} {label(unit)}.")
            return prompt, ("user" if message else "harness"), text

    def await_validation_controls(self):
        """Wait for a harness retry without starting or charging an author turn."""
        while True:
            control = self.controls.get()
            if control.get("type") == "stop":
                self.stop = True
                return None
            if control.get("type") not in ("message", "resume"):
                continue
            switched = self.apply_author(control)
            return str(control.get("text") or "").strip(), switched
