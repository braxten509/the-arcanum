"""Static Python import graph construction and cycle detection."""
from __future__ import annotations

import ast
import os

from .models import Violation


def python_files(root: str, scan_roots: list[str]) -> tuple[str, ...]:
    paths = []
    for relative in scan_roots:
        base = os.path.join(root, relative)
        if os.path.isfile(base) and base.endswith(".py"):
            paths.append(base)
            continue
        for directory, dirnames, filenames in os.walk(base):
            dirnames[:] = [name for name in dirnames
                          if name != "__pycache__" and not name.startswith(".")]
            paths.extend(os.path.join(directory, name) for name in filenames
                         if name.endswith(".py"))
    return tuple(sorted(set(paths)))


def module_name(root: str, path: str) -> str:
    relative = os.path.relpath(path, root).replace(os.sep, "/")
    parts = relative[:-3].split("/")
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(tree: ast.AST, module: str, is_package: bool) -> set[str]:
    output = set()
    package = module if is_package else module.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            output.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if not node.level:
                if node.module:
                    output.add(node.module)
                continue
            parts = package.split(".") if package else []
            climb = max(0, node.level - 1)
            base = parts[:max(0, len(parts) - climb)]
            if node.module:
                base.extend(node.module.split("."))
            if base:
                output.add(".".join(base))
    return output


def build_graph(root: str, files: tuple[str, ...]):
    modules = {module_name(root, path): path for path in files}
    graph, trees, violations = {}, {}, []
    for module, path in modules.items():
        relative = os.path.relpath(path, root)
        try:
            tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
        except (OSError, SyntaxError) as exc:
            violations.append(Violation("python.parse", relative, str(exc)))
            continue
        trees[module] = tree
        edges = set()
        for imported in _imports(tree, module, os.path.basename(path) == "__init__.py"):
            candidate = imported
            while candidate and candidate not in modules:
                candidate = candidate.rpartition(".")[0]
            if candidate and candidate != module:
                edges.add(candidate)
        graph[module] = edges
    return modules, graph, trees, violations


def cycles(graph: dict[str, set[str]]) -> tuple[tuple[str, ...], ...]:
    index, stack, on_stack = 0, [], set()
    indices, low, found = {}, {}, []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = low[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in graph.get(node, ()):
            if target not in indices:
                visit(target)
                low[node] = min(low[node], low[target])
            elif target in on_stack:
                low[node] = min(low[node], indices[target])
        if low[node] == indices[node]:
            component = []
            while stack:
                item = stack.pop()
                on_stack.remove(item)
                component.append(item)
                if item == node:
                    break
            if len(component) > 1:
                found.append(tuple(sorted(component)))

    for node in sorted(graph):
        if node not in indices:
            visit(node)
    return tuple(sorted(found))
