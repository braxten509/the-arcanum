"""Shared finding-buffer helpers for validatelib regression cases."""

from validatelib import clear_findings, legacy_current_findings


def findings():
    out = list(legacy_current_findings())
    clear_findings()
    return out
