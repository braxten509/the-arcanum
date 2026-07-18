"""Checked-in dependency, facade, registry, and frontend architecture rules."""
from __future__ import annotations

import ast
import os
import re

from .javascript_graph import build_graph as build_js_graph, javascript_files
from .models import Violation
from .python_graph import build_graph as build_python_graph, cycles, python_files


def _under(module: str, roots: list[str]) -> bool:
    return any(module == root or module.startswith(root + ".") for root in roots)


def _matches(imported: str, prefixes: list[str]) -> bool:
    return any(imported == prefix or imported.startswith(prefix + ".")
               for prefix in prefixes)


def _raw_imports(tree: ast.AST) -> tuple[str, ...]:
    values = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            values.append(node.module)
    return tuple(values)


def check_python(root: str, policy: dict) -> list[Violation]:
    config = policy["python"]
    files = python_files(root, config["scanRoots"])
    modules, graph, trees, violations = build_python_graph(root, files)
    for component in cycles(graph):
        path = os.path.relpath(modules[component[0]], root)
        violations.append(Violation(
            "python.cycle", path, "import cycle: " + " -> ".join(component)))
    deprecated = config.get("deprecatedModules") or []
    for module, tree in trees.items():
        path = os.path.relpath(modules[module], root)
        imports = _raw_imports(tree)
        if _under(module, config["pureRoots"]):
            for imported in imports:
                if _matches(imported, config["pureForbiddenImports"]):
                    violations.append(Violation(
                        "python.pure-import", path,
                        f"pure core imports forbidden dependency {imported!r}"))
        if _under(module, config["serverRoots"]):
            for imported in imports:
                if _matches(imported, config["serverForbiddenImports"]):
                    violations.append(Violation(
                        "python.server-authoring-import", path,
                        f"server runtime imports authoring implementation {imported!r}"))
        for imported in imports:
            if _matches(imported, deprecated):
                violations.append(Violation(
                    "python.deprecated-import", path,
                    f"imports removed compatibility module {imported!r}"))
        if module == "arcanum.config":
            assigned = {target.id for node in tree.body
                        if isinstance(node, (ast.Assign, ast.AnnAssign))
                        for target in ((node.targets if isinstance(node, ast.Assign)
                                        else [node.target])) if isinstance(target, ast.Name)}
            for name in config.get("configForbiddenNames") or []:
                if name in assigned:
                    violations.append(Violation(
                        "python.mutable-config", path,
                        f"configuration owns forbidden mutable registry {name!r}"))
    return violations


def check_javascript(root: str, policy: dict) -> list[Violation]:
    config = policy["javascript"]
    files = javascript_files(root, config["root"])
    graph, sources = build_js_graph(root, files)
    violations = []
    for component in cycles(graph):
        violations.append(Violation(
            "javascript.cycle", component[0],
            "import cycle: " + " -> ".join(component)))
    api_allowed = set(config.get("apiAdapters") or [])
    ambient_allowed = set(config.get("bootstrapAdapters") or [])
    state_allowed = set(config.get("stateAdapters") or []) | ambient_allowed
    domain_roots = tuple(path.rstrip("/") + "/" for path in config.get("domainRoots") or [])
    for path, source in sources.items():
        scrubbed = re.sub(r"(?s)/\*.*?\*/|//[^\n]*|(['\"])(?:\\.|(?!\1).)*\1", "", source)
        if re.search(r"\bfetch\s*\(", scrubbed) and path not in api_allowed:
            violations.append(Violation(
                "javascript.fetch-boundary", path,
                "fetch is allowed only in the API client adapter"))
        if (re.search(r"(?<![A-Za-z0-9_$])S\s*[.[]", scrubbed)
                and path not in state_allowed):
            violations.append(Violation(
                "javascript.ambient-state", path,
                "direct mutable S access is outside the store/bootstrap boundary"))
        for token in config.get("forbiddenGlobals") or []:
            if token in source and path not in ambient_allowed:
                violations.append(Violation(
                    "javascript.ambient-tome", path,
                    f"ambient global {token!r} is outside bootstrap"))
        if path.startswith(domain_roots):
            for token in config.get("domTokens") or []:
                if token in scrubbed:
                    violations.append(Violation(
                        "javascript.domain-dom", path,
                        f"frontend domain contains UI/platform token {token!r}"))
    return violations


def check_registries(root: str, policy: dict) -> list[Violation]:
    config, violations = policy["registries"], []
    composition_path = os.path.join(root, config["httpComposition"])
    composition = open(composition_path, encoding="utf-8").read()
    endpoint_root = os.path.join(root, config["endpointRoot"])
    for directory, _dirnames, filenames in os.walk(endpoint_root):
        for name in filenames:
            if not name.endswith(".py"):
                continue
            path = os.path.join(directory, name)
            source = open(path, encoding="utf-8").read()
            for class_name in re.findall(r"^class\s+(\w+Endpoints)\b", source, re.M):
                if class_name not in composition:
                    violations.append(Violation(
                        "registry.http", os.path.relpath(path, root),
                        f"endpoint family {class_name} is absent from HTTP composition"))
    provider_composition = open(os.path.join(root, config["aiComposition"]),
                                encoding="utf-8").read()
    provider_root = os.path.join(root, config["providerRoot"])
    for directory, _dirnames, filenames in os.walk(provider_root):
        for name in filenames:
            if not name.endswith(".py"):
                continue
            path = os.path.join(directory, name)
            source = open(path, encoding="utf-8").read()
            for class_name, provider_id in re.findall(
                    r"class\s+(\w+).*?:.*?provider_id\s*=\s*['\"]([^'\"]*)", source, re.S):
                if provider_id and class_name not in provider_composition:
                    violations.append(Violation(
                        "registry.ai", os.path.relpath(path, root),
                        f"provider {class_name} is absent from AI composition"))
    for key, needle in (("validatorComposition", "CheckSpec("),
                        ("authoringComposition", "PhaseDefinition("),
                        ("scenarioComposition", "ScenarioAdapter("),
                        ("interactionComposition", ".register("),
                        ("cognitiveComposition", ".register("),
                        ("routeComposition", "registerRoute(")):
        path = os.path.join(root, config[key])
        if needle not in open(path, encoding="utf-8").read():
            violations.append(Violation(
                "registry.missing", os.path.relpath(path, root),
                f"composition has no explicit {needle.rstrip('(')} entries"))
    return violations


def check_facades(root: str, policy: dict) -> list[Violation]:
    allowed = set(policy["facades"].get("allowed") or [])
    limit = int(policy["facades"].get("maxLines") or 120)
    violations = []
    for relative in allowed:
        path = os.path.join(root, relative)
        try:
            lines = sum(1 for _line in open(path, encoding="utf-8"))
        except OSError:
            violations.append(Violation(
                "facade.missing", relative, "declared facade does not exist"))
            continue
        if lines > limit:
            violations.append(Violation(
                "facade.size", relative, f"compatibility facade has {lines} lines; limit is {limit}"))
    return violations


def check_all(root: str, policy: dict) -> tuple[Violation, ...]:
    findings = [*check_python(root, policy), *check_javascript(root, policy),
                *check_registries(root, policy), *check_facades(root, policy)]
    return tuple(sorted(set(findings)))
