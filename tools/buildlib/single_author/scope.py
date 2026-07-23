"""Profile-driven project paths for the persistent tome author."""
import glob
import os
import tomllib

from .. import BUILD_DIR, REPO, VALIDATOR_FAILURE_DIR
from ..continuity import handoff_dir, handoff_path
from ..course_map import amendment_path, load_course_map, map_path, proposal_path, seed_path
from ..course_map.author_spec import spec_root
from ..phase2.research import ledger_path
from ..course.state import evidence_dir, failure_dir, state_path
from ..prerequisites.review import calls_path as prerequisite_calls_path


def _profile_name(phase):
    return "author-phase12" if phase <= 2 else "author-phase37" if phase <= 7 else "author-phase8"


def _profile_rows(name, phase):
    path = os.path.join(REPO, "global-configs", "permissions", f"{name}.toml")
    try:
        with open(path, "rb") as handle:
            value = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RuntimeError(f"invalid permission profile {name!r}: {exc}") from exc
    rows = [value.get("permissions") or {}]
    rows.extend(row for row in value.get("phase") or []
                if int(row.get("number") or -1) == phase)
    return rows, value.get("system") or {}


def profile_paths(name, *, build_id, tome_id, phase, section_id="", previous_section_id="",
                  section_index="", section_count="", tooling="", runtime_id=""):
    """Resolve a role profile into existing, repository-contained project paths.

    The profiles own role/phase access policy. This code only substitutes runtime values,
    expands a deliberately limited ``*`` glob, and rejects paths outside the repository.
    """
    values = {"build_id": str(build_id), "tome_id": str(tome_id), "phase": str(phase),
              "section_id": str(section_id), "previous_section_id": str(previous_section_id),
              "section_index": str(section_index), "section_count": str(section_count),
              "tooling": str(tooling), "runtime_id": str(runtime_id)}
    resolved = {key: [] for key in ("read", "write", "both", "execute")}
    resolved["execute_commands"] = []
    rows, system = _profile_rows(name, int(phase))
    for row in rows:
        for access in ("read", "write", "both", "execute"):
            for pattern in row.get(access) or []:
                if access == "execute" and isinstance(pattern, list):
                    if not pattern or any(not isinstance(arg, str) or not arg for arg in pattern):
                        raise RuntimeError(f"permission profile {name!r} has an invalid execute command")
                    try:
                        command = [arg.format_map(values) for arg in pattern]
                    except KeyError as exc:
                        raise RuntimeError(f"permission profile {name!r} has unknown placeholder {exc}") from exc
                    resolved["execute_commands"].append(command)
                    patterns = command
                else:
                    patterns = [pattern]
                for pattern in patterns:
                    if not isinstance(pattern, str):
                        raise RuntimeError(f"permission profile {name!r} has a non-text {access} path")
                    try:
                        relative = pattern.format_map(values)
                    except KeyError as exc:
                        raise RuntimeError(f"permission profile {name!r} has unknown placeholder {exc}") from exc
                    if os.path.isabs(relative) or ".." in relative.split("/"):
                        continue  # command executable/flag, not a repository mount
                    matches = glob.glob(os.path.join(REPO, relative))
                    for candidate in matches:
                        path = os.path.realpath(candidate)
                        if os.path.commonpath((path, REPO)) != REPO:
                            raise RuntimeError(f"permission profile {name!r} escapes the repository")
                        if path not in resolved[access]:
                            resolved[access].append(path)
    for access in ("read", "write", "both", "execute"):
        key = f"system_{access}"
        resolved[key] = []
        for pattern in system.get(access) or []:
            if not isinstance(pattern, str):
                raise RuntimeError(f"permission profile {name!r} has a non-text system path")
            try:
                path = pattern.format_map(values)
            except KeyError as exc:
                raise RuntimeError(f"permission profile {name!r} has unknown placeholder {exc}") from exc
            if not isinstance(path, str) or not os.path.isabs(path) or path in ("/", "/home"):
                raise RuntimeError(f"permission profile {name!r} has unsafe system path {path!r}")
            if path.startswith("/tmp/arcanum/") and access in ("write", "both"):
                from arcanum.platform.agent_scratch import prepare
                prepare(build_id)
            if os.path.exists(path) and path not in resolved[key]:
                resolved[key].append(path)
    return resolved


def previous_section_id(build_id, unit):
    """Return the immediate predecessor in the sealed map, or an empty value."""
    section = str((unit or {}).get("section") or "")
    if not section:
        return ""
    try:
        ids = [str(row["id"]) for row in load_course_map(build_id).get("sections") or []]
        position = ids.index(section)
    except (ValueError, KeyError, TypeError, OSError):
        return ""
    return ids[position - 1] if position else ""


def author_paths(build_id, from_phase, tid, unit):
    phase = int((unit or {}).get("phase") or from_phase)
    profile_file = os.path.join(REPO, "global-configs", "permissions",
                                f"{_profile_name(phase)}.toml")
    if os.path.isfile(profile_file):
        profile = profile_paths(_profile_name(phase), build_id=build_id, tome_id=tid,
                                phase=phase, section_id=str((unit or {}).get("section") or ""),
                                previous_section_id=previous_section_id(build_id, unit))
        writable = [*profile["write"], *profile["both"]]
    else:  # Isolated tests may replace REPO without copying its declarative profiles.
        progress = os.path.join(BUILD_DIR, f"{build_id}.progress")
        writable = [progress] if os.path.exists(progress) else []
        tome = os.path.join(REPO, "tomes", tid)
        if phase == 1:
            writable.append(os.path.join(BUILD_DIR, f"{build_id}.plan.md"))
        elif phase == 2:
            writable.extend((tome, spec_root(build_id), ledger_path(build_id),
                             os.path.join(REPO, "global-configs", "runtimes")))
        elif phase == 3 and (unit or {}).get("kind") == "section":
            writable.extend((os.path.join(tome, "sections", unit["section"]),
                             handoff_path(tid, unit["section"]),
                             os.path.join(BUILD_DIR, f"{build_id}.section-progress.json")))
        else:
            writable.append(tome)
            if phase >= 7:
                writable.append(BUILD_DIR)
    protected = [seed_path(build_id), map_path(build_id), state_path(build_id),
                 amendment_path(build_id), evidence_dir(build_id), failure_dir(build_id),
                 prerequisite_calls_path(build_id),
                 os.path.join(VALIDATOR_FAILURE_DIR, build_id),
                 os.path.join(BUILD_DIR, f"{build_id}.prerequisite-reviews"),
                 os.path.join(BUILD_DIR, f"{build_id}.phase-ai-reviews"),
                 os.path.join(BUILD_DIR, f"{build_id}.phase-snapshots"),
                 os.path.join(BUILD_DIR, f"{build_id}.course-control.log.jsonl")]
    if phase != 2:
        protected.extend((spec_root(build_id), ledger_path(build_id)))
    for suffix in ("launch.json", "session.json", "active.json", "result.json",
                   "cancelled.json", "conversation.jsonl", "status-log.jsonl"):
        protected.append(os.path.join(BUILD_DIR, f"{build_id}.{suffix}"))
    if phase != 1:
        protected.append(os.path.join(BUILD_DIR, f"{build_id}.plan.md"))
    # The proposal is always generated harness state. Phase 2 authors edit only
    # the compact spec; their mechanical check writes a disposable preview inside
    # that writable root, while only the harness publishes this protected file.
    protected.append(proposal_path(build_id))
    if phase == 3 and (unit or {}).get("kind") == "section":
        current = handoff_path(tid, unit["section"])
        root = handoff_dir(tid)
        if os.path.isdir(root):
            protected.extend(os.path.join(root, name) for name in os.listdir(root)
                             if os.path.join(root, name) != current)
    elif os.path.isdir(handoff_dir(tid)):
        protected.append(handoff_dir(tid))
    return ([path for path in writable if os.path.exists(path)],
            [path for path in protected if os.path.exists(path)])


def author_hidden_paths(build_id):
    """Historical attempt data that a restarted author must never inspect."""
    paths = [
        os.path.join(VALIDATOR_FAILURE_DIR, build_id),
        os.path.join(BUILD_DIR, f"{build_id}.phase-ai-reviews"),
        os.path.join(BUILD_DIR, f"{build_id}.prerequisite-reviews"),
        prerequisite_calls_path(build_id),
        os.path.join(BUILD_DIR, f"{build_id}.phase-snapshots"),
        os.path.join(BUILD_DIR, f"{build_id}.reset-stash"),
        os.path.join(BUILD_DIR, f"{build_id}.author-usage.jsonl"),
        os.path.join(BUILD_DIR, f"{build_id}.conversation.jsonl.bak"),
    ]
    return [path for path in paths if os.path.exists(path)]
