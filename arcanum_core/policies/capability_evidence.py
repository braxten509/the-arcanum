"""Capability-ledger projection from immutable evidence events."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CapabilityStatus:
    id: str
    taught: bool
    practiced: bool
    supported: bool
    independent: bool
    due: bool
    retained: bool

    @property
    def state(self) -> str:
        if self.retained:
            return "retained"
        if self.independent:
            return "independent"
        if self.supported:
            return "supported"
        if self.practiced:
            return "practiced"
        if self.taught:
            return "taught"
        return "unseen"


def capability_ledger(capability_ids: Iterable[str], events: Iterable[dict]) -> tuple[CapabilityStatus, ...]:
    rows = {item: {"taught": False, "practiced": False, "supported": False,
                   "independent": False, "due": False, "retained": False}
            for item in capability_ids}
    for event in events:
        for capability in event.get("capabilityIds") or ():
            if capability not in rows:
                continue
            row = rows[capability]
            kind = event.get("kind")
            if kind == "taught":
                row["taught"] = True
            elif kind in ("practice", "resolved"):
                row["practiced"] = True
            if event.get("supportUsed"):
                row["supported"] = True
            if event.get("independent"):
                row["independent"] = True
            if event.get("due"):
                row["due"] = True
            if event.get("retained"):
                row["retained"] = True
                row["due"] = False
    return tuple(CapabilityStatus(item, **rows[item]) for item in rows)
