"""Pure authoring phase and unit contracts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


Validation = Callable[[str, dict], tuple[bool, str]]
CommandFactory = Callable[[str, dict], list[list[str]]]
ExitHook = Callable[[str, dict], None]


@dataclass(frozen=True)
class PhaseDefinition:
    phase: int
    phase_id: str
    title: str
    validate: Validation
    self_checks: CommandFactory
    preflight_entrypoints: tuple[str, ...]
    unit_kind: str = "phase"
    transition_command: bool = False
    final: bool = False
    on_exit: ExitHook | None = None
