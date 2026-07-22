#!/usr/bin/env python3
"""Compatibility entrypoint for Phase-2 sessions created before the context move."""
import runpy
from pathlib import Path


if __name__ == "__main__":
    target = Path(__file__).with_name("context") / "render_phase2_context.py"
    runpy.run_path(str(target), run_name="__main__")
