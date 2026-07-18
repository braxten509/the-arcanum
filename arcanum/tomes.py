"""Tome discovery, assembly, and per-tome save/workspace paths."""
import glob
import os
import re
import tomllib

import tome_layout  # shared split-tome layout, kept in lockstep with tools/validate_tome.py
from tome_proof import public_section

from runtimes import common as rt_common, for_config as runtime_for_config, resolve_config as resolve_runtime_config
from runtimes.common import atomic_write

from .config import BUILD_DIR, CACHE_DIR, SKINS_DIR, TOMES_DIR, read_json, read_toml

_manifest_cache = {}  # jid -> (mtime, manifest dict)


def tome_dir(jid):
    jid = (jid or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", jid):
        raise ValueError("bad tome id")
    return os.path.join(TOMES_DIR, jid)


def load_manifest(jid):
    path = os.path.join(tome_dir(jid), "tome.toml")
    mt = os.path.getmtime(path)
    cached = _manifest_cache.get(jid)
    if not cached or cached[0] != mt:
        m = read_toml(path)
        _manifest_cache[jid] = (mt, m)
        return m
    return cached[1]


def plan_path(tid):
    return os.path.join(BUILD_DIR, f"{tid}.plan.md")


def resolve_working_tid(planid, text):
    """The tome-dir id a plan actually points at: a renamed tome keeps its plan under the
    ORIGINAL id, so follow the harness's rename note to whichever dir exists on disk."""
    tid = planid
    for m in re.finditer(r"renamed by the harness:\*\*\s*`[^`]+`\s*(?:→|->)\s*`([^`]+)`", text):
        if os.path.isdir(os.path.join(TOMES_DIR, m.group(1))):
            tid = m.group(1)
    return tid


def _draft_tids():
    """Tome ids with a terminal failed/cancelled result or no completion proof.

    Durable results are authoritative; Harness ground truth remains only as the legacy
    completion marker for builds that predate result sidecars.
    """
    out = set()
    for pp in glob.glob(os.path.join(BUILD_DIR, "*.plan.md")):
        planid = os.path.basename(pp)[:-len(".plan.md")]
        try:
            with open(pp, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        result = read_json(os.path.join(BUILD_DIR, f"{planid}.result.json"), {})
        if result.get("status") == "done":
            continue
        if result.get("status") in ("error", "cancelled") or "Harness ground truth" not in text:
            out.add(resolve_working_tid(planid, text))
    return out


def list_tomes():
    try:
        drafts = _draft_tids()
    except Exception:
        drafts = set()
    out = []
    for path in sorted(glob.glob(os.path.join(TOMES_DIR, "*", "tome.toml"))):
        jid = os.path.basename(os.path.dirname(path))
        try:
            m = read_toml(path)
        except Exception:
            continue
        meta = dict(m.get("meta", {}))
        meta.setdefault("id", jid)
        meta["id"] = jid
        meta["runtime"] = m.get("runtime", {}).get("name", "custom")
        meta["sectionCount"] = len(m.get("content", {}).get("sections", []))
        meta["draft"] = jid in drafts
        out.append(meta)
    return out


def list_skins():
    """skins/<id>/skin.toml → [{id, name, desc, vars, css}]. A skin is a global
    palette + optional structural CSS; assets beside it are served at /skins/<id>/."""
    out = []
    for path in sorted(glob.glob(os.path.join(SKINS_DIR, "*", "skin.toml"))):
        try:
            s = read_toml(path)
        except Exception:
            continue
        s["id"] = os.path.basename(os.path.dirname(path))
        out.append(s)
    return out


def resolve_tome(hint):
    """Return a valid tome id: the requested one if it exists, else the first installed."""
    try:
        if hint and os.path.isfile(os.path.join(tome_dir(hint), "tome.toml")):
            return hint
    except ValueError:
        pass
    js = list_tomes()
    return js[0]["id"] if js else "verisearch"


def assemble_tome(jid):
    """Manifest + ordered section TOMLs + attacks TOML → one JSON payload for the client."""
    m = load_manifest(jid)
    if not str(m.get("narrative", {}).get("objective", "")).strip():
        raise ValueError(f"tome {jid!r}: [narrative] objective is required — "
                         "state what the whole tome builds toward (shown on the Operative File)")
    jdir = tome_dir(jid)
    sections = []
    for sid in m.get("content", {}).get("sections", []):
        # Hidden capstone reference edits are validator inputs, never learner answers.
        sections.append(public_section(tome_layout.load_section(jdir, sid)))
    attacks = []
    ap = os.path.join(jdir, m.get("content", {}).get("attacks", "generated/attacks.toml"))
    if os.path.isfile(ap):
        attacks = read_toml(ap).get("tiers", [])
    payload = tome_layout.merge_banks(dict(m), jdir)  # fold in themes/shop/badges/intrusions siblings
    payload["runtime"] = resolve_runtime_config(m.get("runtime", {}))  # language-toml defaults merged in
    payload["sections"] = sections
    payload["masteryLabs"] = public_mastery_labs(jdir)
    payload["attacks"] = attacks
    payload["skins"] = list_skins()
    return payload


def public_mastery_labs(jdir):
    """Learner-safe authored lab metadata; generated hidden packages stay server-only."""
    labs = []
    for path in sorted(glob.glob(os.path.join(
            jdir, "sections", "*", "mastery-labs", "*.toml"))):
        try:
            with open(path, "rb") as handle:
                raw = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError):
            continue
        lab = dict(raw.get("masteryLab") or {})
        if not lab:
            continue
        labs.append({"masteryLab": lab,
                     "requirements": list(raw.get("requirements") or []),
                     "rubric": [{key: value for key, value in row.items()
                                 if key in {"id", "criterion", "weight", "kind"}}
                                for row in raw.get("rubric") or []]})
    return labs


def runtime_for(jid):
    return runtime_for_config(load_manifest(jid).get("runtime", {}))


def snippet_runtime_for(jid):
    from runtimes import for_snippets
    return for_snippets(load_manifest(jid).get("runtime", {}))


def project_name(jid):
    return load_manifest(jid).get("runtime", {}).get("project", "Project")


def save_dir(jid):
    """tomes/<jid>/save — ALL user progress for a tome. Recreated on demand,
    so deleting it (even while the server runs) resets that course. Never served."""
    d = os.path.join(tome_dir(jid), "save")
    os.makedirs(d, exist_ok=True)
    return d


def external_workspace(jid):
    """An ABSOLUTE path to a project the player manages with their OWN tools
    (IntelliJ, a Gradle mod project…). The location is ALWAYS the student's own
    choice, stored in state.json — a tome may REQUIRE external mode via [runtime]
    externalWorkspace = true, but never dictates WHERE the project lives. Runs,
    diagnostics and grading operate on it; the engine never scaffolds or resets
    it. Empty string = use the engine's scaffolded workspace."""
    # defensive: a bad saved path must not brick the tome, so a non-absolute or
    # missing directory silently falls back to the scaffolded one.
    ws = read_json(state_path(jid), {}).get("workspace") or {}
    if ws.get("enabled"):
        d = os.path.expanduser(ws.get("dir") or "")
        if os.path.isabs(d) and os.path.isdir(d):
            return d
    return ""


def project_dir(jid):
    return external_workspace(jid) or os.path.join(save_dir(jid), "workspace", project_name(jid))


def state_path(jid):
    return os.path.join(save_dir(jid), "state.json")


def has_progress(s):
    """True if a save holds real play, not just settings. `earned` is cumulative
    (never spent down), so it survives even a broke wizard; the collections cover
    a save that only read a chapter or graded a working."""
    if not isinstance(s, dict):
        return False
    if s.get("earned") or s.get("credits"):
        return True
    return any(s.get(k) for k in (
        "ex", "read", "badges", "fs", "exerciseEvidence", "capabilityEvidence",
        "masteryLabs", "assessmentReceipts",
    ))


def grades_dir(jid):
    d = os.path.join(save_dir(jid), "grades")
    os.makedirs(d, exist_ok=True)
    return d


def scratch_base(rt_name):
    return os.path.join(CACHE_DIR, "snippet", rt_name)


def write_files(jid, files):
    """Persist [{path,content}] into a tome's workspace project, refusing path escapes."""
    pdir = project_dir(jid)
    for f in files or []:
        full = rt_common.safe_join(pdir, f["path"])
        os.makedirs(os.path.dirname(full), exist_ok=True)
        atomic_write(full, f["content"])
