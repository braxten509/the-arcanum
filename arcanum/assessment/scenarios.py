"""Scenario-kind registry and deterministic expectation evaluation."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Callable

from arcanum_core.contracts.assessment import Scenario

from .sandbox import SandboxPolicy, SandboxRunner


def _contains(actual, expected) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(key in actual and _contains(actual[key], value)
                                                for key, value in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            _contains(left, right) for left, right in zip(actual, expected))
    return actual == expected


def evaluate_expectation(expect: dict, result: dict, work_root: str) -> tuple[bool, list[str]]:
    problems = []
    output = str(result.get("output") or "")
    if "exitCode" in expect and result.get("exitCode") != expect["exitCode"]:
        problems.append(f"exit code was {result.get('exitCode')}, expected {expect['exitCode']}")
    if "exact" in expect and output.strip() != str(expect["exact"]).strip():
        problems.append("output did not match the declared exact result")
    if "regex" in expect:
        try:
            matched = re.search(str(expect["regex"]), output, re.MULTILINE) is not None
        except re.error as exc:
            problems.append(f"invalid authored expectation regex: {exc}")
        else:
            if not matched:
                problems.append("output did not match the declared pattern")
    if "json" in expect:
        try:
            parsed = json.loads(output)
        except (TypeError, json.JSONDecodeError):
            problems.append("output was not valid JSON")
        else:
            if not _contains(parsed, expect["json"]):
                problems.append("structured output did not contain the declared values")
    if "path" in expect:
        relative = str(expect["path"])
        full = os.path.realpath(os.path.join(work_root, relative))
        root = os.path.realpath(work_root)
        if not full.startswith(root + os.sep) or not os.path.isfile(full):
            problems.append("declared produced file was missing")
        elif "fileRegex" in expect:
            try:
                content = open(full, encoding="utf-8", errors="replace").read(1_000_000)
                if re.search(str(expect["fileRegex"]), content, re.MULTILINE) is None:
                    problems.append("produced file did not match the declared pattern")
            except (OSError, re.error) as exc:
                problems.append(f"could not inspect produced file: {exc}")
    return not problems, problems


@dataclass(frozen=True)
class ScenarioAdapter:
    """One explicitly versioned assessment scenario implementation."""

    kind: str
    handler: Callable
    version: int
    capabilities: tuple[str, ...]


class ScenarioRegistry:
    def __init__(self):
        self._entries: dict[str, ScenarioAdapter] = {}

    def register(self, adapter: ScenarioAdapter) -> None:
        if not isinstance(adapter, ScenarioAdapter):
            raise TypeError("scenario registration requires a ScenarioAdapter")
        if not adapter.kind:
            raise ValueError("assessment scenario kind cannot be empty")
        if adapter.kind in self._entries:
            raise ValueError(f"duplicate assessment scenario kind {adapter.kind!r}")
        if adapter.version < 1:
            raise ValueError(f"assessment scenario {adapter.kind!r} needs a positive version")
        if not adapter.capabilities or any(not item for item in adapter.capabilities):
            raise ValueError(f"assessment scenario {adapter.kind!r} needs capabilities")
        if not callable(adapter.handler):
            raise TypeError(f"assessment scenario {adapter.kind!r} needs a handler")
        self._entries[adapter.kind] = adapter

    def get(self, kind: str) -> ScenarioAdapter:
        try:
            return self._entries[kind]
        except KeyError as exc:
            available = ", ".join(sorted(self._entries)) or "none"
            raise ValueError(
                f"unregistered assessment scenario kind {kind!r}; available: {available}"
            ) from exc

    def entries(self) -> tuple[ScenarioAdapter, ...]:
        return tuple(self._entries[key] for key in sorted(self._entries))

    def validate_references(self, kinds: list[str] | tuple[str, ...]) -> None:
        missing = sorted(set(kinds).difference(self._entries))
        if missing:
            raise ValueError(
                "unregistered assessment scenario references: " + ", ".join(missing)
            )

    def execute(self, scenario: Scenario, context: dict) -> dict:
        return self.get(scenario.kind).handler(scenario, context)


def command_scenario(scenario: Scenario, context: dict) -> dict:
    command = context["runtime"].assessment_command(
        scenario.command_ref, context["work"], scenario.args)
    result = context["sandbox"].run(
        command, cwd=context["work"], stdin=scenario.stdin, timeout=scenario.timeout,
        policy=context.get("sandboxPolicy"), env=context.get("env"))
    passed, problems = evaluate_expectation(scenario.expect, result, context["work"])
    return {**result, "passed": bool(result.get("passed")) and passed, "problems": problems}


def guided_scenario(_scenario: Scenario, _context: dict) -> dict:
    return {"passed": False, "awaitingObservation": True, "argv": [], "exitCode": None,
            "output": "A guided observation must be recorded through the declared adapter.",
            "problems": ["guided observation has not been recorded"]}


def default_registry() -> ScenarioRegistry:
    registry = ScenarioRegistry()
    command_capabilities = {
        "build": ("process", "exit-code"),
        "run": ("process", "stdout", "stdin"),
        "structured-output": ("process", "json-output"),
        "produced-file": ("process", "filesystem-output"),
        "driver": ("process", "runtime-driver"),
        "package": ("process", "package-output"),
        "cold-launch": ("process", "cold-launch"),
    }
    for kind, capabilities in command_capabilities.items():
        registry.register(ScenarioAdapter(kind, command_scenario, 1, capabilities))
    registry.register(ScenarioAdapter(
        "guided-observation", guided_scenario, 1, ("human-observation",)))
    return registry
