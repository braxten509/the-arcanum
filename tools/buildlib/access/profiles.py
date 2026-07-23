"""TOML permission-profile resolution shared by authoring roles."""
from __future__ import annotations

import glob
import os
import tomllib

from ... import REPO


def profile_paths(name, *, build_id, tome_id, phase, section_id="", previous_section_id="",
                  section_index="", section_count="", tooling="", runtime_id=""):
    profile = os.path.join(REPO, "global-configs", "permissions", f"{name}.toml")
    try:
        with open(profile, "rb") as handle:
            value = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RuntimeError(f"invalid permission profile {name!r}: {exc}") from exc
    values = {"build_id": str(build_id), "tome_id": str(tome_id), "phase": str(phase),
              "section_id": str(section_id), "previous_section_id": str(previous_section_id),
              "section_index": str(section_index), "section_count": str(section_count),
              "tooling": str(tooling), "runtime_id": str(runtime_id)}
    rows = [value.get("permissions") or {}]
    rows.extend(row for row in value.get("phase") or []
                if int(row.get("number") or -1) == int(phase))
    resolved = {key: [] for key in ("read", "write", "both", "execute")}
    resolved["execute_commands"] = []
    for row in rows:
        for access in ("read", "write", "both", "execute"):
            for item in row.get(access) or []:
                command = item if access == "execute" and isinstance(item, list) else [item]
                if not command or any(not isinstance(part, str) or not part for part in command):
                    raise RuntimeError(f"permission profile {name!r} has an invalid {access} entry")
                try:
                    command = [part.format_map(values) for part in command]
                except KeyError as exc:
                    raise RuntimeError(f"permission profile {name!r} has unknown placeholder {exc}") from exc
                if isinstance(item, list):
                    resolved["execute_commands"].append(command)
                for relative in command:
                    if os.path.isabs(relative) or ".." in relative.split("/"):
                        continue
                    for candidate in glob.glob(os.path.join(REPO, relative)):
                        path = os.path.realpath(candidate)
                        if os.path.commonpath((path, REPO)) != REPO:
                            raise RuntimeError(f"permission profile {name!r} escapes the repository")
                        if path not in resolved[access]:
                            resolved[access].append(path)
    for access in ("read", "write", "both", "execute"):
        key = f"system_{access}"
        resolved[key] = []
        for item in (value.get("system") or {}).get(access) or []:
            if not isinstance(item, str):
                raise RuntimeError(f"permission profile {name!r} has a non-text system path")
            path = item.format_map(values)
            if not os.path.isabs(path) or path in ("/", "/home"):
                raise RuntimeError(f"permission profile {name!r} has unsafe system path {path!r}")
            if path.startswith("/tmp/arcanum/") and access in ("write", "both"):
                from arcanum.platform.agent_scratch import prepare
                prepare(build_id)
            if os.path.exists(path) and path not in resolved[key]:
                resolved[key].append(path)
    return resolved
