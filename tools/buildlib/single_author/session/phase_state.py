"""Persisted state and unit-scoped model selection for the author session."""
import json
import time

from .support import write_json


class PhaseAuthorStateMixin:
    def configure_phase_authors(self, kind, model, effort, phase_authors):
        fallback = (kind, model, effort)
        self.phase_authors = {key: tuple((phase_authors or {}).get(key) or fallback)
                              for key in ("phase12", "phase37", "phase8")}

    def phase_author(self, phase):
        key = "phase12" if int(phase) <= 2 else "phase37" if int(phase) <= 7 else "phase8"
        return self.phase_authors[key]

    def activate_unit_author(self, passed, next_unit):
        """Select the next unit's author and enforce a fresh validated-unit boundary.

        Phase 1 and Phase 2 intentionally share one warm planning session. Every
        later clean boundary starts a new provider session, even when the configured
        provider/model is unchanged. Failed validation never calls this method, so
        repairs remain in the current unit's warm session.
        """
        phase = int(next_unit.get("phase") or self.from_phase)
        kind, model, effort = self.phase_author(phase)
        identity_changed = (kind, model) != (self.kind, self.model)
        self.kind, self.model, self.effort = kind, model, effort
        passed_phase = int(passed.get("phase") or self.from_phase)
        validated_unit_boundary = not (passed_phase == 1 and phase == 2)
        reset = identity_changed or validated_unit_boundary
        if reset:
            self.session_id = ""
        return reset

    def activate_phase_author(self, phase):
        """Compatibility helper for direct callers that only switch phase routing."""
        kind, model, effort = self.phase_author(phase)
        identity_changed = (kind, model) != (self.kind, self.model)
        self.kind, self.model, self.effort = kind, model, effort
        if identity_changed:
            self.session_id = ""
        return identity_changed

    def state(self, state, **extra):
        payload = {"buildId": self.build_id, "state": state, "kind": self.kind,
                   "model": self.model, "effort": self.effort,
                   "role": self.role, "sessionId": self.session_id,
                   "updatedAt": time.time(), **extra}
        write_json(self.state_path, payload)
        print(f"AUTHOR SESSION {state}", flush=True)

    def read_controls(self):
        for line in self.control_input:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            self.controls.put(row)
