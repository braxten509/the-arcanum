"""Internal modules grouped by responsibility.

The lazy attributes preserve the historical ``buildlib.course.state`` patch seam
without forcing the state repository (and its server adapters) into pure map imports.
"""
from __future__ import annotations

import importlib


def __getattr__(name):
    if name in {"state", "amend", "alignment", "control", "dependencies", "limits"}:
        module = importlib.import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    raise AttributeError(name)
