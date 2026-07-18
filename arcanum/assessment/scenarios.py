"""Scenario-kind registry and deterministic expectation evaluation."""
from __future__ import annotations

import json
import os
import re
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


class ScenarioRegistry:
    def __init__(self):
        self._handlers: dict[str, Callable] = {}

    def register(self, kind: str, handler: Callable) -> None:
        if kind in self._handlers:
            raise ValueError(f"duplicate assessment scenario kind {kind!r}")
        self._handlers[kind] = handler

    def execute(self, scenario: Scenario, context: dict) -> dict:
        try:
            handler = self._handlers[scenario.kind]
        except KeyError as exc:
            raise ValueError(f"unregistered assessment scenario kind {scenario.kind!r}") from exc
        return handler(scenario, context)


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
    for kind in ("build", "run", "structured-output", "produced-file", "driver",
                 "package", "cold-launch"):
        registry.register(kind, command_scenario)
    registry.register("guided-observation", guided_scenario)
    return registry
