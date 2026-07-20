#!/usr/bin/env python3
import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath

_BOOTSTRAP_REPO = _BootstrapPath(__file__).resolve().parents[3]
_bootstrap_sys.path[:0] = [str(_BOOTSTRAP_REPO), str(_BOOTSTRAP_REPO / "tools"),
                           str(_BootstrapPath(__file__).resolve().parent)]

"""Self-check for validatelib's language-agnostic enforcement.

    python3 tools/tests/validation/test_validatelib.py

Needs python3 on PATH (it is the toolchain for the synthetic runtime cases).
"""

from validatelib_cases.content import run_content_cases  # noqa: E402
from validatelib_cases.contracts import run_contract_cases  # noqa: E402
from validatelib_cases.runtime import run_runtime_cases  # noqa: E402
from validatelib_cases.themes import run_theme_cases  # noqa: E402


def main():
    run_content_cases()
    run_runtime_cases()
    run_theme_cases()
    run_contract_cases()
    print("ok: schema, runtime proof, prose/theme guards, capability ledger and cumulative types")


if __name__ == "__main__":
    main()
