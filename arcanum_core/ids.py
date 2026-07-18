"""Stable identifier policies used by versioned contracts."""
from __future__ import annotations

import re

STABLE_ID = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*\Z")
CAPABILITY_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
NODE_ID = re.compile(r"s\d{2}\.(?:l\d{2}|working|lab\d{2})\Z")


def is_stable_id(value: object) -> bool:
    return isinstance(value, str) and bool(STABLE_ID.fullmatch(value))


def is_capability_id(value: object) -> bool:
    return isinstance(value, str) and bool(CAPABILITY_ID.fullmatch(value))


def is_node_id(value: object) -> bool:
    return isinstance(value, str) and bool(NODE_ID.fullmatch(value))
