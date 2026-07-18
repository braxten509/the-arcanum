"""Native-ES-module dependency graph and frontend boundary scans."""
from __future__ import annotations

import os
import re

from .models import Violation

IMPORT_RE = re.compile(
    r"(?:\bimport\s+(?:[^;'\"]*?\sfrom\s+)?|\bexport\s+[^;]*?\sfrom\s+)"
    r"['\"]([^'\"]+)['\"]")


def javascript_files(root: str, relative_root: str) -> tuple[str, ...]:
    base, output = os.path.join(root, relative_root), []
    for directory, dirnames, filenames in os.walk(base):
        dirnames[:] = [name for name in dirnames
                       if name not in {"node_modules", "generated"} and not name.startswith(".")]
        output.extend(os.path.join(directory, name) for name in filenames
                      if name.endswith((".js", ".mjs")))
    return tuple(sorted(output))


def build_graph(root: str, files: tuple[str, ...]):
    known = {os.path.realpath(path): os.path.relpath(path, root).replace(os.sep, "/")
             for path in files}
    graph, sources = {}, {}
    for path in files:
        relative = known[os.path.realpath(path)]
        try:
            source = open(path, encoding="utf-8").read()
        except OSError:
            continue
        sources[relative] = source
        edges = set()
        for specifier in IMPORT_RE.findall(source):
            if not specifier.startswith("."):
                continue
            target = os.path.realpath(os.path.join(os.path.dirname(path), specifier))
            candidates = (target, target + ".js", os.path.join(target, "index.js"))
            resolved = next((known[item] for item in candidates if item in known), None)
            if resolved:
                edges.add(resolved)
        graph[relative] = edges
    return graph, sources
