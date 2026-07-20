"""Subprocess adapter for the destructive authoring-harness phase reset."""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys


class PhaseResetService:
    def __init__(self, settings, catalog) -> None:
        self.settings, self.catalog = settings, catalog

    def find_plan_for_tome(self, tome_id: str) -> tuple[str, str, str]:
        tome_id = self.catalog.paths.validate_id(tome_id)
        matches = []
        for path in glob.glob(os.path.join(self.settings.build_root, "*.plan.md")):
            build_id = os.path.basename(path)[:-len(".plan.md")]
            try:
                build_id = self.catalog.paths.validate_id(build_id)
                with open(path, encoding="utf-8") as handle:
                    text = handle.read()
                if (build_id == tome_id
                        or self.catalog.resolve_working_id(build_id, text) == tome_id):
                    matches.append((os.path.getmtime(path), build_id, path, text))
            except (OSError, ValueError):
                continue
        if not matches:
            raise ValueError(
                "this tome has no Bindery build plan, so it cannot be reset by phase")
        _modified, build_id, path, text = max(matches)
        return build_id, path, text

    def reset(self, tome_id: str, phase: int, section: str = "") -> dict:
        command = [sys.executable, os.path.join(
            self.settings.root, "tools", "workflow", "reset_tome_phase.py"),
                   tome_id, str(phase), *([section] if section else [])]
        completed = subprocess.run(command, cwd=self.settings.root, capture_output=True,
                                   text=True, timeout=300)
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        try:
            result = json.loads(lines[-1]) if lines else {}
        except json.JSONDecodeError:
            result = {}
        if completed.returncode or not result.get("ok"):
            detail = (result.get("error") or completed.stderr or completed.stdout
                      or "phase reset failed")
            raise RuntimeError(str(detail)[-2000:])
        return dict(result.get("result") or {})
