"""Context-local validation findings and phase severity policy."""
from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
import re

from arcanum_core.findings import Finding, Severity


_CURRENT: ContextVar[tuple[Finding, ...]] = ContextVar(
    "arcanum_validation_findings", default=())
_BUILD_PHASE: ContextVar[int | None] = ContextVar(
    "arcanum_validation_build_phase", default=None)


def _code(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", ".", str(label).lower()).strip(".")
    return "legacy." + (slug or "validation")


def clear_findings() -> None:
    _CURRENT.set(())


def current_findings() -> tuple[Finding, ...]:
    return _CURRENT.get()


@contextmanager
def finding_scope(phase: int | None = None):
    """Capture one check's findings without leaking into another validation run."""
    findings_token = _CURRENT.set(())
    phase_token = _BUILD_PHASE.set(int(phase) if phase is not None else None)
    capture = []
    try:
        yield capture
    finally:
        capture.extend(_CURRENT.get())
        _BUILD_PHASE.reset(phase_token)
        _CURRENT.reset(findings_token)


def replace_findings(findings: Sequence[Finding]) -> None:
    _CURRENT.set(tuple(findings))


def set_build_phase(phase: int | None = None) -> None:
    _BUILD_PHASE.set(int(phase) if phase is not None else None)


def add_error(location: str, message: str, *, code: str = "", phase: int = 0) -> None:
    owner = int(phase or 0)
    build_phase = _BUILD_PHASE.get()
    # Standalone/full validation keeps errors hard. During an incremental build,
    # an explicitly later-owned error is deferred until its authoring phase instead
    # of deadlocking an earlier worker that cannot legally edit the owning files.
    severity = (Severity.WARNING if owner and build_phase is not None
                and owner > int(build_phase) else Severity.ERROR)
    finding = Finding(severity, code or _code(location), str(location),
                      str(message), owner, False)
    _CURRENT.set((*_CURRENT.get(), finding))


def add_warning(location: str, message: str, *, phase: int = 7,
                code: str = "") -> None:
    owned = (location != "advisory" and _BUILD_PHASE.get() is not None
             and int(phase) <= int(_BUILD_PHASE.get() or 0))
    severity = Severity.ERROR if owned else Severity.WARNING
    finding = Finding(severity, code or _code(location), str(location), str(message),
                      int(phase), location == "advisory")
    _CURRENT.set((*_CURRENT.get(), finding))


def legacy_tuple(finding: Finding) -> tuple[str, str, str]:
    level = "ERROR" if finding.severity is Severity.ERROR else "WARN"
    return level, finding.location, finding.message


def legacy_current_findings() -> tuple[tuple[str, str, str], ...]:
    return tuple(legacy_tuple(item) for item in _CURRENT.get())


class LegacyFindingView(Sequence[tuple[str, str, str]]):
    """Temporary test-only sequence view; production code consumes typed findings."""

    def __iter__(self) -> Iterator[tuple[str, str, str]]:
        return iter(tuple(legacy_tuple(item) for item in _CURRENT.get()))

    def __len__(self) -> int:
        return len(_CURRENT.get())

    def __getitem__(self, index):
        values = tuple(legacy_tuple(item) for item in _CURRENT.get())
        return values[index]

    def __setitem__(self, index, value) -> None:
        if isinstance(index, slice) and not value:
            clear_findings()
            return
        raise TypeError("legacy finding view supports only clearing slice assignment")

    def clear(self) -> None:
        clear_findings()

    def append(self, value: tuple[str, str, str]) -> None:
        level, location, message = value
        if level == "ERROR":
            add_error(location, message)
        else:
            add_warning(location, message)


legacy_findings = LegacyFindingView()
