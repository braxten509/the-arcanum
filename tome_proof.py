"""Shared helpers for the future-tome executable proof and external-asset contract.

The validator, loader, and Phase-8 harness all read this module so that a tome cannot
mean three different things by "proved".  Version 1 is opt-in through the scaffolded
``[content].proofVersion`` key; older installed tomes keep their legacy behavior.
"""
import hashlib
import json
import os
import re


PROOF_VERSION = 1
STEP_MODES = frozenset(("write", "replace", "rewrite", "append", "delete"))
PROOF_MODES = frozenset(("run", "build", "guided", "package"))
ACCEPTANCE_MODES = frozenset(("run", "guided"))
ACCEPTANCE_ARTIFACTS = frozenset(("runtime", "package"))
ACCEPTANCE_CONTROLS = frozenset(("input", "clock", "seed", "frame-limit"))
CODE_KINDS = frozenset(("runnable", "replacement", "patch", "pseudocode", "terminal"))
MEDIA_EXTENSIONS = frozenset((
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tga", ".svg",
    ".ico", ".ase", ".aseprite", ".psd", ".kra",
    ".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".mid", ".midi",
    ".mp4", ".webm", ".mov", ".avi", ".mkv",
    ".ttf", ".otf", ".woff", ".woff2",
))

_MEDIA_TOKEN = re.compile(
    r"(?<![\w.-])(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+(?:"
    + "|".join(re.escape(ext) for ext in sorted(MEDIA_EXTENSIONS, key=len, reverse=True))
    + r")(?![\w.-])", re.I)


def proof_enabled(manifest):
    content = manifest.get("content") if isinstance(manifest, dict) else None
    return isinstance(content, dict) and content.get("proofVersion") == PROOF_VERSION


def safe_project_path(value):
    """Return a normalized relative POSIX path, or ``None`` for an escape/invalid path."""
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        return None
    raw = value.strip()
    if raw.startswith(("/", "\\")) or "\\" in raw or re.match(r"^[A-Za-z]:", raw):
        return None
    parts = raw.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return None
    return "/".join(parts)


def is_media_path(value):
    path = safe_project_path(value)
    return bool(path and os.path.splitext(path.lower())[1] in MEDIA_EXTENSIONS)


def iter_strings(value):
    """Yield authored strings from a nested TOML value."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from iter_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_strings(child)


def media_mentions(value):
    mentions = set()
    for text in iter_strings(value):
        # Source URLs are validated separately and are not learner project paths; keep
        # scanning the rest of a sentence that may also name the destination.
        authored = re.sub(r"https?://[^\s<>'\"]+", "", text)
        mentions.update(match.group(0) for match in _MEDIA_TOKEN.finditer(authored))
    return mentions


def lesson_capabilities(sections):
    out = []
    for section in sections:
        for lesson in section.get("lessons") or []:
            if not isinstance(lesson, dict):
                continue
            out.extend(str(item) for item in (lesson.get("teaches") or []))
    return out


def section_capabilities(section):
    """Capabilities introduced by one section, in stable authored order."""
    seen, out = set(), []
    for lesson in section.get("lessons") or []:
        if not isinstance(lesson, dict):
            continue
        for item in lesson.get("teaches") or []:
            capability = str(item)
            if capability not in seen:
                seen.add(capability)
                out.append(capability)
    return out


def active_proofs(sections):
    """Return the final active proof ledger for an authored section prefix.

    Every section proof persists by default. A later proof may explicitly supersede an
    earlier proof, but schema validation separately requires its ``protects`` list to carry
    every capability that the retired proof protected.
    """
    active = {}
    for section in sections:
        sid = str(section.get("id") or "")
        proof = section.get("proof") if isinstance(section.get("proof"), dict) else {}
        for retired in proof.get("supersedes") or []:
            active.pop(str(retired), None)
        introduced = section_capabilities(section)
        protects = proof.get("protects")
        active[sid] = {
            "section": sid,
            "mode": proof.get("mode"),
            "capabilities": list(protects) if isinstance(protects, list) else introduced,
            "expectedFiles": list(proof.get("expectedFiles") or []),
            "runArgs": list(proof.get("runArgs") or []),
        }
    return list(active.values())


def review_coverage(sections):
    """Exact machine-owned Phase-8 coverage lists."""
    return ([str(section.get("id")) for section in sections],
            sorted(set(lesson_capabilities(sections))))


def proof_fingerprint(manifest, sections, runtime_config=None):
    """Content fingerprint binding evidence to the exact reviewed artifact and runtime."""
    if runtime_config is None:
        try:
            from runtimes import resolve_config
            runtime_config = resolve_config(manifest.get("runtime") or {})
        except (ImportError, OSError, TypeError, ValueError):
            runtime_config = manifest.get("runtime") or {}
    payload = {
        "protocol": PROOF_VERSION,
        "manifest": {key: manifest.get(key) for key in
                     ("meta", "runtime", "content", "acceptance")},
        "resolvedRuntime": runtime_config,
        "sections": sections,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def proof_evidence_path(repo, tid):
    return os.path.join(repo, ".tome-build", f"{tid}.proof-evidence.json")


def learner_project_path(repo, tid):
    """Stable harness-owned reconstruction of the final learner project.

    Phase 8 reviews this exact directory instead of mentally composing dozens of
    lesson edits.  It is generated state under ``.tome-build``; learner workspaces
    and authored tome files are never used as the replay target.
    """
    return os.path.join(repo, ".tome-build", f"{tid}.learner-project")


def step_lists(section):
    """Yield visible lesson steps then the hidden capstone reference steps."""
    for lesson in section.get("lessons") or []:
        if isinstance(lesson, dict):
            yield str(lesson.get("id") or "lesson"), lesson.get("artifactSteps") or []
    freestyle = section.get("freestyle") or {}
    if isinstance(freestyle, dict):
        yield "freestyle reference", freestyle.get("referenceSteps") or []


def apply_step(project_dir, step):
    """Apply one declarative learner edit inside a disposable project.

    No shell commands are accepted.  ``replace`` must identify exactly one old region,
    which turns vague insertion-point prose into a deterministic validation failure.
    """
    path = safe_project_path(step.get("path")) if isinstance(step, dict) else None
    if not path:
        raise ValueError("step path is not a safe relative project path")
    if is_media_path(path):
        raise ValueError(f"step may not create or alter media asset {path!r}")
    full = os.path.realpath(os.path.join(project_dir, *path.split("/")))
    root = os.path.realpath(project_dir)
    if not full.startswith(root + os.sep):
        raise ValueError("step path escapes the disposable project")
    mode = step.get("mode")
    if mode not in STEP_MODES:
        raise ValueError(f"unknown step mode {mode!r}")
    if mode == "delete":
        if not os.path.isfile(full):
            raise ValueError(f"delete target {path!r} does not exist")
        os.remove(full)
        return
    os.makedirs(os.path.dirname(full), exist_ok=True)
    if mode == "write":
        if os.path.exists(full):
            raise ValueError(
                f"write target {path!r} already exists; use an exact replace or an explicit "
                "rewrite with preserves = 'all-active'")
        if not isinstance(step.get("content"), str):
            raise ValueError("write step needs string content")
        with open(full, "w", encoding="utf-8") as handle:
            handle.write(step["content"])
        return
    if mode == "append":
        if not os.path.isfile(full):
            raise ValueError(f"append target {path!r} does not exist")
        if not isinstance(step.get("content"), str):
            raise ValueError("append step needs string content")
        with open(full, "a", encoding="utf-8") as handle:
            handle.write(step["content"])
        return
    if not os.path.isfile(full):
        raise ValueError(f"{mode} target {path!r} does not exist")
    if mode == "rewrite":
        if step.get("preserves") != "all-active":
            raise ValueError("rewrite step must declare preserves = 'all-active'")
        if not isinstance(step.get("content"), str):
            raise ValueError("rewrite step needs string content")
        with open(full, "w", encoding="utf-8") as handle:
            handle.write(step["content"])
        return
    old, new = step.get("find"), step.get("content")
    if not isinstance(old, str) or not old or not isinstance(new, str):
        raise ValueError("replace step needs non-empty find and string content")
    with open(full, encoding="utf-8") as handle:
        current = handle.read()
    count = current.count(old)
    if count != 1:
        raise ValueError(f"replace find text occurs {count} times in {path!r}, expected 1")
    with open(full, "w", encoding="utf-8") as handle:
        handle.write(current.replace(old, new, 1))


def public_section(section):
    """Copy a loaded section while removing hidden answer material from HTTP payloads."""
    copied = dict(section)
    freestyle = copied.get("freestyle")
    if isinstance(freestyle, dict):
        freestyle = dict(freestyle)
        freestyle.pop("referenceSteps", None)
        copied["freestyle"] = freestyle
    return copied
