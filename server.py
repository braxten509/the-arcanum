#!/usr/bin/env python3
"""ARCANUM server — stdlib only. Serves the game, discovers/assembles Tomes,
persists per-tome state, runs code via pluggable runtimes, grades via claude CLI."""
import difflib
import glob
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import tomllib
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import tome_layout  # shared split-tome layout, kept in lockstep with tools/validate_tome.py

from runtimes import (common as rt_common, for_config as runtime_for_config, get as get_runtime,
                      names as runtime_names, resolve_config as resolve_runtime_config)
from runtimes.common import atomic_write, clip

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")
TOMES_DIR = os.path.join(ROOT, "tomes")
SKINS_DIR = os.path.join(ROOT, "skins")          # global TOML-defined skins (tome-independent)
CACHE_DIR = os.path.join(ROOT, ".cache")         # ephemera only: snippet scratch, server.log
BUILD_DIR = os.path.join(ROOT, ".tome-build")    # build_tome cross-phase state + runner handshake
PORT = 8777

GRADER_MODELS = ["claude-opus-4-8", "opus"]  # first that works wins
CLAUDE_BIN = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
AGY_BIN = shutil.which("agy") or os.path.expanduser("~/.local/bin/agy")
CODEX_BIN = shutil.which("codex") or os.path.expanduser("~/.local/bin/codex")
GRADE_TIMEOUT = 420  # seconds for claude grading
ORACLE_TIMEOUT = 180  # seconds for one oracle question (any backend)

# Models the claude/codex CLIs accept but cannot enumerate (neither has a list
# command); antigravity (`agy models`) and ollama (/api/tags) are listed live in
# /api/models. One source of truth — the browser pickers fetch these.
CLI_MODELS = {
    "claude-cli": ["claude-opus-4-8", "claude-opus-4-7", "claude-sonnet-5", "claude-haiku-4-5", "claude-fable-5"],
    # gpt-5.4-mini is the cheap/fast coding model (supersedes gpt-4o-mini, which is not in the
    # 2026 codex lineup); gpt-5.3-codex stays available for the coding-optimized cost profile.
    "codex-cli": ["gpt-5.5", "gpt-5.4", "gpt-5.3-codex", "gpt-5.4-mini"],
    "anthropic": ["claude-opus-4-8", "claude-opus-4-7", "claude-sonnet-5", "claude-haiku-4-5", "claude-fable-5"],
    "openai": ["gpt-5.1", "gpt-5", "gpt-4.1", "o3"],
}
# Reasoning-effort levels each login CLI accepts (claude: `--effort`, per its own
# --help; codex: `-c model_reasoning_effort=`). agy takes none — its Gemini model
# names carry the effort (Low/Medium/High variants). Mirrored in build_tome.py's
# CLI_RUNNERS, which does the actual flag injection.
CLI_EFFORTS = {
    "claude-cli": ["low", "medium", "high", "xhigh", "max"],
    "codex-cli": ["minimal", "low", "medium", "high", "xhigh"],
    # opencode's --variant reasoning effort — a permissive ALLOWLIST here (the real per-model
    # values come from models.dev in the bindery). "none" appears on some models (e.g.
    # north-mini-code-free). Local ollama models take no variant.
    "opencode-cli": ["none", "minimal", "low", "medium", "high", "max"],
}

OPENCODE_BIN = shutil.which("opencode") or os.path.expanduser("~/.local/bin/opencode")
# OpenCode Go (opencode.ai/go) — the low-cost coding gateway. Its lineup rotates, so we
# list it live from `opencode models` (opencode-go/*), falling back to this snapshot when
# opencode is absent or slow. The FREE ids are opencode-hosted launch-window models at $0.
OPENCODE_GO_FALLBACK = [
    "opencode-go/glm-5.2", "opencode-go/glm-5.1", "opencode-go/kimi-k2.7-code",
    "opencode-go/kimi-k2.6", "opencode-go/mimo-v2.5", "opencode-go/mimo-v2.5-pro",
    "opencode-go/minimax-m3", "opencode-go/minimax-m2.7", "opencode-go/qwen3.7-max",
    "opencode-go/qwen3.7-plus", "opencode-go/qwen3.6-plus", "opencode-go/deepseek-v4-pro",
    "opencode-go/deepseek-v4-flash",
]
OPENCODE_FREE_IDS = [
    "opencode/big-pickle", "opencode/deepseek-v4-flash-free", "opencode/mimo-v2.5-free",
    "opencode/north-mini-code-free", "opencode/nemotron-3-ultra-free",
]


def models_dev_efforts():
    """'provider/model' -> [effort values] from opencode's models.dev cache. Reasoning effort
    is PER-MODEL and not uniform: some Go models expose ["high","max"], some a toggle only,
    many none — so the picker must offer the right values per model, not a blanket list."""
    out = {}
    try:
        with open(os.path.expanduser("~/.cache/opencode/models.json")) as f:
            d = json.load(f)
        for pid, prov in d.items():
            for mid, m in (prov.get("models") or {}).items():
                for ro in (m.get("reasoning_options") or []):
                    if isinstance(ro, dict) and ro.get("type") == "effort" and ro.get("values"):
                        out[f"{pid}/{mid}"] = list(ro["values"])
    except Exception:
        pass
    return out


def opencode_models():
    """OpenCode Go + free models as [id, label, tag, efforts] rows (tag "FREE" flags the $0
    ones; efforts is that model's reasoning-effort values, or [] if it has none). Live from
    `opencode models` when available, else the static snapshot. label = id sans prefix."""
    lines = []
    try:
        p = subprocess.run([OPENCODE_BIN, "models"], capture_output=True, text=True, timeout=20)
        lines = [ln.strip() for ln in p.stdout.splitlines() if ln.strip()]
    except Exception:
        pass
    go = [ln for ln in lines if ln.startswith("opencode-go/")] or list(OPENCODE_GO_FALLBACK)
    free = [i for i in OPENCODE_FREE_IDS if (not lines or i in lines)]
    eff = models_dev_efforts()
    short = lambda mid: mid.split("/", 1)[-1]
    return ([[m, short(m), "", eff.get(m, [])] for m in go]
            + [[m, short(m), "FREE", eff.get(m, [])] for m in free])


def ollama_bindery_models():
    """Local ollama models as [ollama/<name>, <name>, "local", []] rows — run THROUGH the
    opencode agent. Local models aren't in models.dev, so they carry no effort variant."""
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
            data = json.loads(r.read())
        return [["ollama/" + m["name"], m["name"], "local", []] for m in data.get("models", [])]
    except Exception:
        return []

os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(TOMES_DIR, exist_ok=True)

# ---------------------------------------------------------------- utilities


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def read_toml(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


# ---------------------------------------------------------------- tomes

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


def _draft_tids():
    """Tome ids whose build never completed — a plan file in .tome-build without the
    end-of-run 'Harness ground truth' append. The shelf shows these as DRAFTS."""
    out = set()
    for pp in glob.glob(os.path.join(BUILD_DIR, "*.plan.md")):
        planid = os.path.basename(pp)[:-len(".plan.md")]
        try:
            with open(pp, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        if "Harness ground truth" not in text:
            out.add(_resolve_working_tid(planid, text))
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
        sections.append(tome_layout.load_section(jdir, sid))  # folder or flat section
    attacks = []
    ap = os.path.join(jdir, m.get("content", {}).get("attacks", "generated/attacks.toml"))
    if os.path.isfile(ap):
        attacks = read_toml(ap).get("tiers", [])
    payload = tome_layout.merge_banks(dict(m), jdir)  # fold in themes/shop/badges/intrusions siblings
    payload["runtime"] = resolve_runtime_config(m.get("runtime", {}))  # language-toml defaults merged in
    payload["sections"] = sections
    payload["attacks"] = attacks
    payload["skins"] = list_skins()
    return payload


def runtime_for(jid):
    return runtime_for_config(load_manifest(jid).get("runtime", {}))


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


# Settings that follow the READER, not the tome — audio, pen (handwritten ink), and the
# ai grader/oracle config are the same across every tome; the palette (theme) and all
# progress stay per-tome. Stored beside the runtimes in global-configs/, split out of
# each POSTed save and merged back into each GET.
GLOBAL_STATE_KEYS = ("audio", "pen", "ai")
GLOBAL_SETTINGS = os.path.join(ROOT, "global-configs", "settings.json")


def has_progress(s):
    """True if a save holds real play, not just settings. `earned` is cumulative
    (never spent down), so it survives even a broke wizard; the collections cover
    a save that only read a chapter or graded a working."""
    if not isinstance(s, dict):
        return False
    if s.get("earned") or s.get("credits"):
        return True
    return any(s.get(k) for k in ("ex", "read", "badges", "fs"))


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


# ---------------------------------------------------------------- grading jobs

jobs = {}  # id -> {status, result, error}
jobs_lock = threading.Lock()
amend_procs = {}  # amend job id -> Popen, kept out of `jobs` so status stays JSON-safe


# ---------------------------------------------------------------- tome-forge build jobs
# (share the `jobs` registry above; build jobs carry "kind": "build")

# The harness's banner always starts "> Phase N — …"; the ">" is REQUIRED so a worker
# narrating "Phase 3 — s02 complete…" in its own output can't hijack the phase title.
BUILD_PHASE_RE = re.compile(r"^\s*>\s*Phase (\d+)\s*—\s*(.+?)(?:\s+\[runner|$)")
# Worker CLIs color their output; the browser log is plain text, where the ESC byte is
# invisible and leaves "[0m" litter. Strip CSI/OSC sequences and stray control chars.
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b.|[\x00-\x08\x0b-\x1f\x7f]")
# Phase 2 renames the tome folder from the launch slug to the themed kebab id
# (build_tome.py maybe_rename prints this). Track it or forge_name reads a dead folder.
BUILD_RENAME_RE = re.compile(r"renamed tomes/\S+ -> tomes/(\S+)")
# Split-sections progress: "· authoring s03 [3/8] on <runner>" / "· resuming s02 [2/8] …"
# / "· section s01 [1/8] already authored — skipping"
BUILD_SECTION_RE = re.compile(r"^\s*·\s+(?:authoring|resuming|section)\s+s\d+\s+\[(\d+)/(\d+)\]")
BUILD_RUNNER_RE = re.compile(r"\[runner: ([^\]]+)\]")
BUILD_TOTAL_PHASES = 9  # TOME-WORKFLOW.md phases 0..8


def fresh_tome_id(name):
    """Slugify a course name into an unused tomes/<id> — the harness's Phase 2 runs
    new_tome.py, which refuses an existing dir, so the id must be fresh (including
    ids claimed by builds still running that haven't scaffolded yet)."""
    s = re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9-]", "-", name.lower().strip())).strip("-")[:32].strip("-") or "tome"
    with jobs_lock:
        claimed = {j.get("tome") for j in jobs.values()
                   if j.get("kind") == "build" and j.get("status") == "running"}
    tid, n = s, 1  # untitled, then untitled-1, untitled-2, … on collision
    # A prior build's plan under this slug also blocks it: Phase 2 renames the tome dir
    # but leaves the plan under the launch slug, and reusing it would OVERWRITE that
    # record (this clobbered writforge's plan when a second "untitled" launch reused it).
    while (os.path.exists(os.path.join(TOMES_DIR, tid)) or tid in claimed
           or os.path.exists(os.path.join(BUILD_DIR, f"{tid}.plan.md"))):
        tid, n = f"{s}-{n}", n + 1
    return tid


def forge_name(tid):
    """The themed name the author-AI chose — meta.name, once Phase 2 has written
    tome.toml. None before that (the overlay then falls back to the folder id)."""
    try:
        return (load_manifest(tid).get("meta") or {}).get("name") or None
    except Exception:
        return None


# ---- Pushover: ping the operator when a build needs them or ends, so they can wander off
# mid-forge. Creds live in global-configs/settings.json {"pushover": {"token","user"}} — the
# same file as the AI API keys — or PUSHOVER_TOKEN/PUSHOVER_USER in the env. No creds → no-op.
def _pushover_creds():
    tok, usr = os.environ.get("PUSHOVER_TOKEN"), os.environ.get("PUSHOVER_USER")
    if not (tok and usr):
        p = read_json(GLOBAL_SETTINGS, {}).get("pushover") or {}
        tok, usr = tok or p.get("token"), usr or p.get("user")
    return (tok, usr) if tok and usr else None


def notify(title, message, priority=0):
    """Fire-and-forget Pushover push (own thread, so a slow/failed send never blocks or breaks
    a build). priority=1 bypasses the phone's quiet hours — use it for anything needing a hand."""
    creds = _pushover_creds()
    if not creds:
        return
    tok, usr = creds
    def _send():
        try:
            data = urllib.parse.urlencode({"token": tok, "user": usr, "title": title[:250],
                                           "message": message[:1024], "priority": priority}).encode()
            urllib.request.urlopen("https://api.pushover.net/1/messages.json", data=data, timeout=10)
        except Exception as e:
            print(f"pushover: {e}", file=sys.stderr)
    threading.Thread(target=_send, daemon=True).start()


def watch_build(gid, proc):
    """Reader thread: stream harness stdout into the job, tracking '> Phase N — title' lines."""
    for line in proc.stdout:
        line = ANSI_RE.sub("", line.rstrip("\n"))
        m = BUILD_PHASE_RE.match(line)
        with jobs_lock:
            job = jobs.get(gid)
            if not job:
                break
            job["log"].append(line)
            del job["log"][:-400]
            if m:
                job["phase"] = int(m.group(1))
                job["phaseTitle"] = m.group(2).strip()
                job["phaseStartedAt"] = time.time()   # the overlay shows time-in-phase from this
                job.pop("sections", None)             # per-phase; only phase 3 repopulates it
                r = BUILD_RUNNER_RE.search(line)
                if r:
                    job["runner"] = r.group(1)
                _write_progress(job.get("tome"), job["phase"])  # so a later resume restarts here
            sec = BUILD_SECTION_RE.match(line)
            if sec:
                job["sections"] = f"{sec.group(1)}/{sec.group(2)}"
                r = re.search(r"\bon (.+)$", line)    # split workers can differ from the phase runner
                if r:
                    job["runner"] = r.group(1)
            rn = BUILD_RENAME_RE.search(line)
            if rn:
                job["tome"] = rn.group(1)  # follow the Phase 2 rename so the UI picks up the themed meta.name
            pause = line.lstrip().startswith("⏸")  # request_runner blocked for a human pick (death/gate)
            tnow = job.get("tome")
        if pause:  # outside the lock — notify never blocks, forge_name reads a file
            notify(f"⏸ {forge_name(tnow) or tnow or 'A tome'} needs you", line.strip(), priority=1)
    rc = proc.wait()
    tome = tail = final = None
    with jobs_lock:
        job = jobs.get(gid)
        if job and job.get("status") == "running":  # cancel sets its own status first
            job["status"] = "done" if rc == 0 else "error"
            if rc != 0:
                job["error"] = "\n".join(job["log"][-30:])
        if job:
            final, tome, tail = job.get("status"), job.get("tome"), "\n".join(job.get("log", [])[-6:])
    nm = forge_name(tome) or tome or "The tome"
    if final == "done":
        notify("✓ Tome forged", f"{nm} finished — ready in the Bindery.")
    elif final == "error":  # a user cancel sets status 'cancelled', so this only fires on real failures
        notify("✗ Forge failed", f"{nm} stopped:\n{tail}", priority=1)


# ---------------------------------------------------------------- resuming abandoned builds
# A build writes its plan to .tome-build/<id>.plan.md and its tome to tomes/<id>/. A build
# that stopped before the end (crash, cancel, closed laptop) leaves both on disk; "resume"
# re-launches build_tome from where it left off. Two facts make the id bookkeeping fiddly:
# Phase 2 may RENAME the tome (untitled -> writforge) while leaving the plan under the old
# id, and the phase reached is only known from the live job — so we persist it to a sidecar.

def _plan_path(tid):
    return os.path.join(BUILD_DIR, f"{tid}.plan.md")


def _resolve_working_tid(planid, text):
    """The tome-dir id a plan actually points at: a renamed tome keeps its plan under the
    ORIGINAL id, so follow the harness's rename note to whichever dir exists on disk."""
    tid = planid
    for m in re.finditer(r"renamed by the harness:\*\*\s*`[^`]+`\s*(?:→|->)\s*`([^`]+)`", text):
        if os.path.isdir(os.path.join(TOMES_DIR, m.group(1))):
            tid = m.group(1)
    return tid


def _plan_concept(text):
    m = re.search(r"(?ms)^## Concept\n(.+?)\n\n", text)
    return (m.group(1).strip().replace("\n", " ") if m else "")[:280]


def _load_launch(*ids):
    for i in ids:
        try:
            with open(os.path.join(BUILD_DIR, f"{i}.launch.json"), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            continue
    return {}


def _save_launch(tid, body, concept):
    # gate answers ride along so a resume can DISPLAY them (they are fixed once Phase 0
    # ran); a resume POST carries none — keep the ones from the original launch then.
    gate = {k: str(body.get(k) or "").strip()
            for k in ("prior_knowledge", "breadth", "depth", "mastery", "tooling")}
    if not any(gate.values()):
        gate = _load_launch(tid).get("gate") or {}
    try:
        with open(os.path.join(BUILD_DIR, f"{tid}.launch.json"), "w", encoding="utf-8") as f:
            json.dump({"bindery": body.get("bindery") or {}, "concept": concept,
                       "sectionsSplit": bool(body.get("sectionsSplit")), "gate": gate}, f)
    except OSError:
        pass


def _plan_gate(text):
    """Gate answers parsed back out of a plan's '- **Label:** value' lines — the fallback
    for workings launched before launch.json carried them."""
    out = {}
    for key, label in (("prior_knowledge", "Prior knowledge"), ("breadth", "Breadth"),
                       ("depth", "(?:Lesson depth|Scope / depth)"), ("mastery", "Mastery"),
                       ("tooling", "Tooling")):
        m = re.search(rf"(?im)^- \*\*{label}[^:]*?:\*\*\s*(.+)$", text)
        if m:
            out[key] = m.group(1).strip()
    return out


def _write_progress(tome, phase):
    if not tome:
        return
    try:
        with open(os.path.join(BUILD_DIR, f"{tome}.progress"), "w", encoding="utf-8") as f:
            json.dump({"phase": phase}, f)
    except OSError:
        pass


def _resume_phase(planid, tid):
    """Which phase to restart at. Prefer the sidecar the live build wrote; for a legacy build
    with none, infer from disk (a scaffolded tome.toml means Phase 2 finished → resume Phase 3)."""
    for key in (tid, planid):
        try:
            with open(os.path.join(BUILD_DIR, f"{key}.progress"), encoding="utf-8") as f:
                return max(1, min(8, int(json.load(f).get("phase", 1))))
        except (OSError, ValueError):
            continue
    tdir = os.path.join(TOMES_DIR, tid)
    if os.path.isfile(os.path.join(tdir, "tome.toml")):
        return 3
    return 2 if os.path.isdir(tdir) else 1


def list_workings():
    """Abandoned builds worth resuming: a plan file whose build isn't running and never reached
    the end-of-run '## Harness ground truth' append (which only a completed build gets)."""
    with jobs_lock:
        active = {j.get("tome") for j in jobs.values()
                  if j.get("kind") == "build" and j.get("status") == "running"}
    out = []
    for pp in glob.glob(os.path.join(BUILD_DIR, "*.plan.md")):
        planid = os.path.basename(pp)[:-len(".plan.md")]
        try:
            with open(pp, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        if "Harness ground truth" in text:           # a completed run, not an abandoned one
            continue
        tid = _resolve_working_tid(planid, text)
        if tid in active or planid in active:         # currently being forged, not abandoned
            continue
        launch = _load_launch(tid, planid)
        out.append({"id": planid, "tome": tid, "name": forge_name(tid) or tid,
                    "concept": launch.get("concept") or _plan_concept(text),
                    "phase": _resume_phase(planid, tid),
                    "bindery": launch.get("bindery") or {},
                    "gate": launch.get("gate") or _plan_gate(text),
                    "sectionsSplit": bool(launch.get("sectionsSplit")),
                    "updated": os.path.getmtime(pp)})
    out.sort(key=lambda w: w["updated"], reverse=True)
    return out


def _runner_args(body):
    """The bindery's {phase: {kind, model, effort}} picks -> build_tome.py --runner flags
    (effort rides as an @suffix). Malformed entries are dropped rather than failing the build."""
    args = []
    for key, rv in (body.get("runners") or {}).items():
        kind = str((rv or {}).get("kind") or "")
        mdl = str((rv or {}).get("model") or "")
        eff = str((rv or {}).get("effort") or "")
        if eff and eff in CLI_EFFORTS.get(kind, ()):
            mdl += "@" + eff
        if re.fullmatch(r"default|\d", str(key)) and mdl and \
                kind in ("claude-cli", "antigravity-cli", "codex-cli", "opencode-cli"):
            args += ["--runner", f"{key}={kind}:{mdl}"]
    return args


def _clear_runner_handshake(tid):
    for stale in ("runner-request", "runner-reply"):
        try:
            os.remove(os.path.join(BUILD_DIR, f"{tid}.{stale}.json"))
        except OSError:
            pass


def extract_json(text):
    """Pull the first JSON object out of possibly-noisy LLM text."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in grader output")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("unbalanced JSON in grader output")


def build_grade_prompt(payload, files, prev, rt, pdir):
    section = payload.get("sectionTitle", "")
    brief = payload.get("brief", "")
    rubric = payload.get("rubric", [])
    language = payload.get("language") or getattr(rt, "LANGUAGE", None) or rt.NAME
    persona = payload.get("persona") or "THE MAGISTER"
    student = payload.get("studentTerm") or "apprentice"
    scale = payload.get("gradeScale") or "S|A|B|C|D|F"
    build_label = payload.get("buildLabel") or f"{rt.NAME} build"  # no per-language branch; the runtime names itself
    build_out = rt.try_build(pdir)

    parts = [
        f"You are the grader inside a {language} learning game. A student learning {language} submitted their "
        "freestyle project for the section below. Grade it strictly against the rubric.",
        "",
        f"SECTION: {section}",
        f"ASSIGNMENT BRIEF: {brief}",
        "",
        "HOW TO READ THE BRIEF: it is written in the game's in-world, themed voice. Grade every "
        "requirement by its INTENT, not its literal flavor wording. A requirement is a hard, exact "
        "spec ONLY when it is stated concretely — an exact output string in quotes or code font, a "
        "named command/token, or an explicit word like 'exactly'. Where wording is atmospheric or "
        "vague, accept any reasonable implementation and do NOT dock points for not matching the "
        "flavor. Resolve ambiguity in the student's favor and lean on the rubric below.",
        "",
    ]
    parts.append("RUBRIC (score each criterion 0-10; weights sum to 100):")
    for r in rubric:
        parts.append(f"- [{r['weight']}%] {r['criterion']}: {r['desc']}")
    parts.append("")
    parts.append(
        f"CONVENTIONS & IDIOM: where a criterion concerns style, readability, or craft, judge it against "
        f"real-world {language} conventions — idiomatic naming and casing, brace/layout style, consistent "
        "formatting, and idiomatic use of the constructs this section teaches. Anchor these judgments in "
        f"the language's official or de-facto community style guide (for example: Microsoft's C# Coding "
        "Conventions, PEP 8 for Python, gofmt for Go, the Ruby Style Guide) — recall that guide and apply "
        "it. Judge only conventions you are certain that guide states; never invent house rules or import "
        "another language's style. Name each convention breach concretely in that criterion's comment and "
        "state the pattern to follow, so the student learns the convention, not just the score. Expect "
        "only the conventions a learner at this section could know.")
    parts.append("")
    parts.append(f"COMPILER OUTPUT of `{build_label}`:\n{build_out[:4000]}")
    parts.append("")
    parts.append("STUDENT CODE (entire workspace):")
    for rel, content in files:
        parts.append(f"\n===== FILE: {rel} =====\n{content[:20000]}")
    if prev and prev.get("result", {}).get("scores"):
        parts.append("\nPREVIOUS SUBMISSION: this student already had this project graded. Previous scores:")
        for s in prev["result"]["scores"]:
            parts.append(f"- {s.get('criterion')}: {s.get('score')}/10 — {s.get('comment', '')}")
        old, cur = prev.get("files", {}), dict(files)
        diff = []
        for name in sorted(set(old) | set(cur)):
            if old.get(name, "") != cur.get(name, ""):
                diff += difflib.unified_diff(old.get(name, "").splitlines(), cur.get(name, "").splitlines(),
                                             fromfile="previous/" + name, tofile="current/" + name, lineterm="")
        parts.append("\nDIFF since the previously graded submission:")
        parts.append("\n".join(diff)[:20000] or "(no changes)")
        parts.append(
            "\nSCORE STABILITY RULE (mandatory): a criterion's score MUST be exactly the previous score "
            "unless the diff above changes code relevant to that criterion. Never raise or lower a criterion "
            "the diff does not touch. Only re-judge what actually changed.")
    parts.append("""
Respond with ONLY a JSON object, no prose before or after, exactly this shape:
{
  "scores": [{"criterion": "<name>", "score": <0-10>, "comment": "<1-2 sentences, direct, specific>"}],
  "total": <0-100 weighted total>,
  "grade": "<%SCALE%>",  // S=flawless+elegant, A>=90, B>=80, C>=70, D>=60, F<60
  "feedback": "<3-6 sentences of overall feedback in the voice of a gruff but fair ops mentor codenamed %PERSONA%. Address the student as '%STUDENT%'. Be specific about what to improve. No spoiler solutions.>",
  "bestLine": "<quote the single best line/idea in their code, or empty string>"
}
Grade honestly. A beginner who met every goal with working, readable code deserves an A.
Reserve S for code that would pass review from a senior %LANG% dev. Do not inflate.
Grade code and observable behavior ONLY. Do NOT deduct for tone, phrasing, verbosity, or stylistic
wording of the program's output text (e.g. a message feeling "redundant" or off-tone versus the brief) —
if the required output elements are present and correct, that aspect earns full marks. Deduct only for
missing or broken functionality, bugs, or code-quality issues the rubric explicitly names."""
                 .replace("%SCALE%", scale).replace("%PERSONA%", persona)
                 .replace("%STUDENT%", student).replace("%LANG%", language))
    return "\n".join(parts)


FALLBACK_GRADER = "qwen2.5:14b"  # strongest installed Ollama model; overridable per-request from settings


def grade_with_ollama(prompt, model):
    """Local grading fallback when the claude CLI is unavailable or out of usage."""
    body = json.dumps({
        "model": model,
        "prompt": prompt + "\n\nRespond with ONLY the JSON grade object — no prose before or after.",
        "stream": False, "keep_alive": 0,
        "options": {"temperature": 0.2, "num_ctx": 16384},
    }).encode()
    req = urllib.request.Request(ORACLE_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=GRADE_TIMEOUT) as r:
        data = json.loads(r.read())
    return extract_json(data.get("response", ""))


def grade_with_claude_cli(prompt, model):
    return extract_json(cli_text("claude-cli", prompt, model, GRADE_TIMEOUT))


class GraderConfigError(Exception):
    """A grader misconfiguration (e.g. a model that doesn't exist) — fatal, surfaced
    to the user as-is instead of silently retried on the local fallback grader."""


_agy_cache = {"t": 0.0, "models": []}


def agy_models():
    """Model display names `agy --model` accepts, one per line from `agy models`.
    Cached 10 min — the settings modal refetches on every open and the list is
    a subprocess away."""
    if time.time() - _agy_cache["t"] > 600:
        p = subprocess.run([AGY_BIN, "models"], capture_output=True, text=True, timeout=30)
        if p.returncode != 0:
            raise RuntimeError(f"`agy models` failed: {p.stderr[:300]}")
        # agy lists Claude models it won't actually serve on this plan — hide them
        _agy_cache.update(t=time.time(),
                          models=[ln.strip() for ln in p.stdout.splitlines()
                                  if ln.strip() and not ln.strip().startswith("Claude")])
    return _agy_cache["models"]


def cli_text(kind, prompt, model, timeout):
    """One prompt through a login-based CLI, plain text back. Shared by grading
    (which parses JSON out of it) and the oracle (which shows it as-is).
    - claude: prompt on stdin; CLAUDECODE is stripped so a nested CLI behaves.
    - agy: `-p` takes the prompt as an ARGUMENT (not stdin), and `--model` wants a
      display name from `agy models` (e.g. "Gemini 3.1 Pro (High)"). agy silently
      ignores an unknown model, so validate up front rather than answer under the
      wrong model.
    - codex: prompt on stdin; read-only sandbox so the agent can't touch the disk;
      empty model uses the user's ~/.codex config default."""
    if kind == "claude-cli":
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        p = subprocess.run([CLAUDE_BIN, "-p", "--model", model, "--tools", ""],
                           input=prompt, capture_output=True, text=True,
                           timeout=timeout, env=env, cwd=CACHE_DIR)
    elif kind == "antigravity-cli":
        if model and model not in agy_models():
            raise GraderConfigError(
                f"model {model!r} does not exist in agy — run `agy models` for valid names "
                "(agy would otherwise silently answer with its default)")
        p = subprocess.run([AGY_BIN, "-p", prompt] + (["--model", model] if model else []),
                           capture_output=True, text=True, timeout=timeout, cwd=CACHE_DIR)
    elif kind == "codex-cli":
        p = subprocess.run([CODEX_BIN, "exec", "--skip-git-repo-check", "-s", "read-only"]
                           + (["-m", model] if model else []) + ["-"],
                           input=prompt, capture_output=True, text=True,
                           timeout=timeout, cwd=CACHE_DIR)
    else:
        raise ValueError(f"unknown CLI kind {kind!r}")
    if p.returncode != 0:
        raise RuntimeError(f"exit {p.returncode}: {p.stderr[:500]}")
    return p.stdout


def grade_with_agy_cli(prompt, model):
    """Antigravity CLI (`agy`) print mode: one-shot, non-interactive, JSON from stdout.
    Uses the user's Google login — no API key, mirroring the claude CLI path."""
    return extract_json(cli_text("antigravity-cli", prompt, model, GRADE_TIMEOUT))


def grade_with_codex_cli(prompt, model):
    """Codex CLI (ChatGPT login) non-interactively: prompt on stdin, JSON from stdout."""
    return extract_json(cli_text("codex-cli", prompt, model, GRADE_TIMEOUT))


def grade_with_command(prompt, command):
    """Any AI CLI the user configures ('Other' provider): the grading prompt is piped
    to the command's stdin, the JSON grade is parsed from its stdout. Runs via the
    shell so the user can supply flags/pipes; cwd is the isolated cache dir."""
    if not command.strip():
        raise ValueError("no command configured")
    p = subprocess.run(command, shell=True, input=prompt, capture_output=True, text=True,
                       timeout=GRADE_TIMEOUT, cwd=CACHE_DIR)
    if p.returncode != 0:
        raise RuntimeError(f"exit {p.returncode}: {p.stderr[:500]}")
    return extract_json(p.stdout)


def grade_with_anthropic(prompt, model, key):
    body = json.dumps({"model": model, "max_tokens": 4096,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=GRADE_TIMEOUT) as r:
        data = json.loads(r.read())
    return extract_json("".join(b.get("text", "") for b in data.get("content", [])))


def grade_with_openai(prompt, model, key):
    body = json.dumps({"model": model,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=body, headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=GRADE_TIMEOUT) as r:
        data = json.loads(r.read())
    return extract_json(data["choices"][0]["message"]["content"])


def run_grader(job_id, payload, jid):
    # jid comes from the request handler (query param) — the body has no tome key,
    # so resolving here again would misroute grading to the first installed tome
    rt = runtime_for(jid)
    pdir = project_dir(jid)
    gdir = grades_dir(jid)
    sid = payload.get("sectionId", "x")
    files = rt.collect_code(pdir)
    ws_hash = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    last_path = os.path.join(gdir, f"last-{sid}.json")
    last = read_json(last_path, None)

    g = payload.get("grader") or {}
    kind, model, key = g.get("kind", "claude-cli"), g.get("model", ""), g.get("key", "")
    command = g.get("command", "")  # only used by the "other" (custom CLI) provider
    grader_sig = f"{kind}/{model}"  # recorded with the judgement; NOT part of the cache key

    # identical code to the last judged submission → the same grade stands, even if the
    # selected grader changed since: re-judging unchanged work would only churn scores.
    # (the card labels these "the prior judgement stands", naming the model that judged.
    # to force a second opinion, edit the code or delete save/grades/last-<sid>.json)
    if last and last.get("hash") == ws_hash and last.get("result"):
        result = dict(last["result"])
        result["cached"] = True
        with jobs_lock:
            jobs[job_id] = {"status": "done", "result": result}
        return

    prompt = build_grade_prompt(payload, files, last, rt, pdir)
    last_err = "no model attempted"

    def finish(result, model):
        result["model"] = model
        result["gradedAt"] = time.time()
        with jobs_lock:
            jobs[job_id] = {"status": "done", "result": result}
        atomic_write(os.path.join(gdir, f"{sid}-{int(time.time())}.json"),
                     json.dumps(result, indent=2))
        atomic_write(last_path, json.dumps(
            {"hash": ws_hash, "grader": grader_sig, "files": dict(files), "result": result}, indent=2))

    if kind == "claude-cli":
        attempts = [("claude-cli", m, "") for m in ([model] if model else GRADER_MODELS)]
    else:
        attempts = [(kind, model, key)]

    graders = {"claude-cli": lambda: grade_with_claude_cli(prompt, model),
               "antigravity-cli": lambda: grade_with_agy_cli(prompt, model),
               "codex-cli": lambda: grade_with_codex_cli(prompt, model),
               "anthropic": lambda: grade_with_anthropic(prompt, model, key),
               "openai": lambda: grade_with_openai(prompt, model, key),
               "ollama": lambda: grade_with_ollama(prompt, model),
               "other": lambda: grade_with_command(prompt, command)}
    for kind, model, key in attempts:
        try:
            if kind not in graders:
                raise ValueError(f"unknown grader kind {kind!r}")
            return finish(graders[kind](), model)
        except GraderConfigError as e:
            # a misconfiguration (e.g. a model that doesn't exist): surface it as-is
            # and STOP — silently grading with the local fallback would hide the mistake.
            with jobs_lock:
                jobs[job_id] = {"status": "error", "error": f"{kind}: {e}"}
            return
        except subprocess.TimeoutExpired:
            last_err = f"{kind}/{model}: timed out after {GRADE_TIMEOUT}s"
        except Exception as e:
            last_err = f"{kind}/{model}: {str(e)[:500]}"

    # main grader failed — fall back to the local model (unless that IS what just failed)
    fb = payload.get("fallbackModel") or FALLBACK_GRADER
    if not (kind == "ollama" and model == fb):
        try:
            return finish(grade_with_ollama(prompt, fb), fb + " (local fallback)")
        except Exception as e:
            last_err += f"; ollama {fb}: {str(e)[:300]}"
    with jobs_lock:
        jobs[job_id] = {"status": "error", "error": last_err}


# ---------------------------------------------------------------- oracle

ORACLE_MODEL = "llama3.1:8b"
ORACLE_URL = "http://localhost:11434/api/generate"


def ask_oracle(question, context, model=None, language="code", kind="ollama"):
    """One question to the selected oracle backend — a local Ollama model (default)
    or any of the login CLIs (claude/agy/codex). Returns text or a friendly error."""
    prompt = (
        f"You are the ORACLE, a terse mentor spirit dwelling in a crystal ball inside an arcane {language} learning game. "
        f"The student is learning {language} by building a CLI tool. Answer their question clearly and "
        "concisely (a few short paragraphs max, code snippets welcome). Do NOT write whole "
        "solutions to their assignments — explain concepts and point them the right way.\n"
        f"CURRENT LESSON CONTEXT: {context[:12000]}\n\nSTUDENT QUESTION (they are programming in {language}): {question[:2000]}"
    )
    if kind in ("claude-cli", "antigravity-cli", "codex-cli"):
        try:
            answer = cli_text(kind, prompt, model or "", ORACLE_TIMEOUT).strip()
            return {"ok": True, "answer": answer or "(the oracle said nothing)",
                    "model": model or kind}
        except Exception as e:
            return {"ok": False, "answer": f"THE ORB IS DARK — the {kind} spirit did not answer ({str(e)[:300]})"}
    model = model or ORACLE_MODEL
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "keep_alive": 0, "options": {"temperature": 0.4}}).encode()
    req = urllib.request.Request(ORACLE_URL, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=ORACLE_TIMEOUT) as r:
            data = json.loads(r.read())
        return {"ok": True, "answer": data.get("response", "").strip() or "(the oracle said nothing)",
                "model": model}
    except Exception as e:
        return {"ok": False, "answer": f"THE ORB IS DARK — is Ollama running? ({e})"}


# ---------------------------------------------------------------- the Binder (amend a tome)

AMEND_TIMEOUT = 900  # seconds for one small-change agent run


def run_amender(job_id, jid, request_text, kind, model, effort=""):
    """Background worker: ONE headless CLI agent makes a small edit to tomes/<jid>/
    guided by course-configuration-guide.md, then validate_tome.py checks the result.
    The agent gets edit permissions but no shell — the server runs the validator."""
    prompt = (
        "You are THE BINDER — a maintenance agent for the Arcanum course platform. "
        f"The player of the course (tome) at tomes/{jid}/ requests one small change:\n\n"
        f"REQUEST: {request_text[:4000]}\n\n"
        "FIRST read course-configuration-guide.md at the repo root — it maps every file and "
        "field you may touch and the rules that bind them. Then make the SMALLEST edit that "
        f"fulfils the request, only under tomes/{jid}/. Never rename ids or files, never "
        "touch engine code, skins/, or other tomes, never edit save/ or generated/. You "
        "cannot run shell commands — the server validates after you finish. End with one "
        "short paragraph naming exactly the file(s) and field(s) you changed.")
    # same headless postures + effort switches as tools/build_tome.py CLI_RUNNERS
    cmds = {
        "claude-cli": [CLAUDE_BIN, "-p", "--permission-mode", "acceptEdits"]
                      + (["--model", model] if model else [])
                      + (["--effort", effort] if effort else []),
        "antigravity-cli": [AGY_BIN, "--print", "--dangerously-skip-permissions"]
                           + (["--model", model] if model else []),  # agy: model name carries effort
        "codex-cli": [CODEX_BIN, "exec", "--skip-git-repo-check", "-s", "workspace-write"]
                     + (["-m", model] if model else [])
                     + (["-c", f"model_reasoning_effort={effort}"] if effort else []) + ["-"],
        "opencode-cli": [OPENCODE_BIN, "run", "--dangerously-skip-permissions"]
                        + (["-m", model] if model else [])
                        + (["--variant", effort] if effort else []) + [prompt],
    }
    try:
        cmd = cmds.get(kind)
        if not cmd:
            raise ValueError(f"unknown binder kind {kind!r}")
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        stdin_data = None if kind == "opencode-cli" else prompt
        p = subprocess.Popen(cmd, stdin=(subprocess.DEVNULL if stdin_data is None else subprocess.PIPE),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             env=env, cwd=ROOT, start_new_session=True)  # own group, so cancel kills CLI children too
        with jobs_lock:
            amend_procs[job_id] = p
        try:
            stdout, stderr = p.communicate(input=stdin_data, timeout=AMEND_TIMEOUT)
        finally:
            with jobs_lock:
                amend_procs.pop(job_id, None)
        with jobs_lock:
            if jobs.get(job_id, {}).get("status") == "cancelled":
                return  # the player stayed the quill; the kill is not an error
        if p.returncode != 0:
            raise RuntimeError(f"exit {p.returncode}: {(stderr or stdout)[:500]}")
        summary = stdout.strip()[-2000:]
        v = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "validate_tome.py"),
                            os.path.join("tomes", jid)], capture_output=True, text=True,
                           timeout=300, cwd=ROOT)
        with jobs_lock:
            job = jobs.get(job_id)
            if job:
                job.update(status="done", summary=summary,
                           validator=v.stdout.strip()[-2000:], validatorOk=v.returncode == 0)
    except Exception as e:
        with jobs_lock:
            job = jobs.get(job_id)
            if job and job.get("status") == "running":
                job.update(status="error", error=str(e)[:800])


# ---------------------------------------------------------------- HTTP

MIME = {".html": "text/html", ".js": "text/javascript", ".css": "text/css",
        ".json": "application/json", ".svg": "image/svg+xml", ".woff2": "font/woff2",
        ".ttf": "font/ttf", ".map": "application/json", ".png": "image/png", ".toml": "text/plain"}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if "/api/state" not in (args[0] if args else ""):
            sys.stderr.write("%s\n" % (fmt % args))

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def query_tome(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        return resolve_tome((q.get("tome") or [""])[0])

    # ---- GET
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/state":
            data = read_json(state_path(self.query_tome()), {})
            g = read_json(GLOBAL_SETTINGS, {})
            for k in GLOBAL_STATE_KEYS:   # reader-wide settings override the tome's copy
                if k in g:
                    data[k] = g[k]
            return self.send_json(data)
        if path == "/api/tomes":
            return self.send_json({"tomes": list_tomes()})
        if path == "/api/tome":
            jid = self.query_tome()
            try:
                return self.send_json(assemble_tome(jid))
            except Exception as e:
                return self.send_json({"error": f"failed to load tome {jid!r}: {e}"}, 500)
        if path == "/api/workspace":
            jid = self.query_tome()
            rt, pdir = runtime_for(jid), project_dir(jid)
            files = []
            if os.path.isdir(pdir):
                for rel, content in rt.collect_code(pdir):
                    files.append({"path": rel, "content": content})
            exists = os.path.isfile(os.path.join(pdir, rt.project_file(project_name(jid))))
            return self.send_json({"files": files, "exists": exists})
        if path == "/api/checkdir":
            # validate a student-supplied external-editor folder before they enable it
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            p = os.path.expanduser((q.get("path") or [""])[0])
            return self.send_json({"abs": os.path.isabs(p), "exists": os.path.exists(p),
                                   "isdir": os.path.isdir(p)})
        if path == "/api/starterfile":
            # the starter contents of one required file, for previewing/copying into an external editor
            jid = self.query_tome()
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            rel = (q.get("path") or [""])[0]
            rt = runtime_for(jid)
            if not rt.available():
                return self.send_json({"ok": False, "error": f"{rt.LANGUAGE} toolchain not found on this machine"}, 400)
            try:
                return self.send_json({"ok": True, "path": rel,
                                       "content": rt.starter_content(project_name(jid), rel)})
            except Exception as e:
                return self.send_json({"ok": False, "error": str(e)[-500:]}, 500)
        if path.startswith("/api/grade/status"):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            jid = (q.get("id") or [""])[0]
            with jobs_lock:
                job = jobs.get(jid)
            return self.send_json(job or {"status": "unknown"})
        if path.startswith("/api/buildtome/status"):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            bid = (q.get("id") or [""])[0]
            with jobs_lock:
                job = jobs.get(bid)
                if not job or job.get("kind") != "build":
                    out = {"status": "unknown"}
                else:
                    out = {k: job[k] for k in ("status", "kind", "tome", "phase", "phaseTitle",
                                               "totalPhases", "startedAt", "error",
                                               "phaseStartedAt", "runner", "sections") if k in job}
                    out["name"] = forge_name(job.get("tome"))
                    out["logtail"] = "\n".join(job.get("log", [])[-40:])
                    req = os.path.join(BUILD_DIR, f"{job.get('slug') or job.get('tome')}.runner-request.json")
                    if os.path.exists(req):  # a worker died; the harness is waiting for a pick
                        try:
                            with open(req, encoding="utf-8") as f:
                                out["awaitingRunner"] = json.load(f)
                        except (OSError, ValueError):
                            pass
            return self.send_json(out)
        if path.startswith("/api/amend/status"):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            aid = (q.get("id") or [""])[0]
            with jobs_lock:
                job = jobs.get(aid)
                out = dict(job) if job and job.get("kind") == "amend" else {"status": "unknown"}
            return self.send_json(out)
        if path == "/api/amend/current":
            # the running amend job for this tome, if any — lets the Binder's bench reattach
            jid = self.query_tome()
            with jobs_lock:
                for aid0, j in jobs.items():
                    if j.get("kind") == "amend" and j.get("status") == "running" and j.get("tome") == jid:
                        return self.send_json({"jobId": aid0, "request": j.get("request", "")})
            return self.send_json({})
        if path == "/api/buildtome/active":
            with jobs_lock:
                act = [{"id": bid, "tome": j.get("tome"), "name": forge_name(j.get("tome")), "phase": j.get("phase"),
                        "phaseTitle": j.get("phaseTitle"), "status": j.get("status")}
                       for bid, j in jobs.items()
                       if j.get("kind") == "build" and j.get("status") == "running"]
            return self.send_json({"jobs": act})
        if path == "/api/buildtome/resumable":
            return self.send_json({"workings": list_workings()})
        if path == "/api/health":
            avail = {n: get_runtime(n).available() for n in runtime_names()}
            for j in list_tomes():  # tomes may declare custom command runtimes
                if j.get("runtime") not in avail:
                    try:
                        avail[j["runtime"]] = runtime_for(j["id"]).available()
                    except Exception:
                        avail[j["runtime"]] = False
            return self.send_json({
                "claude": os.access(CLAUDE_BIN, os.X_OK),
                "runtimes": avail,
            })
        if path == "/api/models":
            # the full model census the browser pickers are built from: ollama live,
            # agy live (it can enumerate), claude/codex from the curated CLI_MODELS
            # lists (they can't). `installed` says which login CLIs exist on this rig.
            installed = {"claude-cli": os.access(CLAUDE_BIN, os.X_OK),
                         "antigravity-cli": os.access(AGY_BIN, os.X_OK),
                         "codex-cli": os.access(CODEX_BIN, os.X_OK)}
            providers = {k: list(v) for k, v in CLI_MODELS.items()}
            if installed["antigravity-cli"]:
                try:
                    providers["antigravity-cli"] = agy_models()
                except Exception:
                    providers["antigravity-cli"] = []
            else:
                providers["antigravity-cli"] = []
            out = {"ok": True, "models": [], "providers": providers, "installed": installed,
                   "efforts": CLI_EFFORTS}
            try:
                with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
                    data = json.loads(r.read())
                out["models"] = sorted(({"name": m["name"], "gb": round(m.get("size", 0) / 1e9, 1)}
                                        for m in data.get("models", [])), key=lambda m: -m["gb"])
            except Exception as e:
                out["ok"] = False
                out["error"] = str(e)
            # `bindery`: the ordered provider list the FORGE-A-TOME pickers build from — each a
            # [PROVIDER][MODEL][EFFORT] triple-box. models are [id, label, tag] triples. Separate
            # from `providers`/`models` above (which the settings grader/oracle pickers still use),
            # so this can carry opencode + local without polluting the grader backends.
            oc_ok = os.access(OPENCODE_BIN, os.X_OK)
            oc_models = opencode_models() if oc_ok else []
            local_models = ollama_bindery_models() if oc_ok else []  # local runs THROUGH opencode
            # each model row is [id, label, tag, efforts]. effort is PER-MODEL: claude/codex
            # take their CLI's effort list on every model; opencode is per-model from
            # models.dev; antigravity/local take none.
            rows = lambda ms, ef: [[m, m, "", list(ef)] for m in ms]
            out["bindery"] = [
                {"id": "claude-cli", "label": "Claude CLI", "kind": "claude-cli",
                 "models": rows(CLI_MODELS["claude-cli"], CLI_EFFORTS["claude-cli"]),
                 "installed": installed["claude-cli"]},
                {"id": "antigravity-cli", "label": "Antigravity CLI", "kind": "antigravity-cli",
                 "models": rows(providers["antigravity-cli"], []),
                 "installed": installed["antigravity-cli"]},
                {"id": "codex-cli", "label": "Codex CLI", "kind": "codex-cli",
                 "models": rows(CLI_MODELS["codex-cli"], CLI_EFFORTS["codex-cli"]),
                 "installed": installed["codex-cli"]},
                {"id": "opencode-cli", "label": "OpenCode CLI", "kind": "opencode-cli",
                 "models": oc_models, "installed": oc_ok},
                {"id": "local", "label": "Local", "kind": "opencode-cli",
                 "models": local_models, "installed": oc_ok and bool(local_models)},
            ]
            # `quality`: the CHEAP<->QUALITY slider tiers from harness.toml [quality.q1..q5],
            # ordered cheapest first. Each carries a per-phase runner map the browser applies
            # to the hand knobs; missing/broken TOML just hides the slider.
            try:
                q = read_toml(os.path.join(ROOT, "harness.toml")).get("quality") or {}
                out["quality"] = [dict(q[k], id=k) for k in sorted(q)]
            except Exception:
                out["quality"] = []
            return self.send_json(out)
        # static files
        if path == "/":
            path = "/index.html"
        rel = path.lstrip("/")
        if rel.startswith("tomes/"):
            base, rel = TOMES_DIR, rel[len("tomes/"):]
        elif rel.startswith("monaco/") or rel.startswith("skins/") or rel.startswith("sounds/") or rel.startswith("global-configs/"):
            base = ROOT
        else:
            base = WEB
        full = os.path.realpath(os.path.join(base, rel))
        jr = os.path.realpath(TOMES_DIR)
        if full.startswith(jr + os.sep):
            parts = full[len(jr) + 1:].split(os.sep)
            if len(parts) > 1 and parts[1] == "save":  # tomes/<jid>/save/** is user data — never serve
                return self.send_json({"error": "not found"}, 404)
        allowed = [os.path.realpath(x) for x in (WEB, TOMES_DIR, os.path.join(ROOT, "monaco"), SKINS_DIR,
                                                 os.path.join(ROOT, "sounds"), os.path.join(ROOT, "global-configs"))]
        if not any(full.startswith(a + os.sep) or full == a for a in allowed) or not os.path.isfile(full):
            self.send_json({"error": "not found"}, 404)
            return
        ext = os.path.splitext(full)[1]
        with open(full, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache" if ext in (".html", ".js", ".css", ".mp3") else "max-age=86400")
        self.end_headers()
        self.wfile.write(body)

    # ---- POST
    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            body = self.read_body()
        except (ValueError, json.JSONDecodeError):
            return self.send_json({"error": "bad json"}, 400)
        # tome scoping: prefer the ?tome= query param (added by the client fetch shim),
        # fall back to a "tome" key in the body (used by tools like gen_attacks.py)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        hint = (q.get("tome") or [None])[0] or (body.get("tome") if isinstance(body, dict) else None)
        jid = resolve_tome(hint)
        try:
            if path == "/api/state":
                # peel the reader-wide settings off into global-configs/settings.json;
                # the tome's save keeps only what is truly its own (palette + progress)
                if isinstance(body, dict):
                    g = read_json(GLOBAL_SETTINGS, {})
                    took = {k: body.pop(k) for k in GLOBAL_STATE_KEYS if k in body}
                    if took:
                        g.update(took)
                        os.makedirs(os.path.dirname(GLOBAL_SETTINGS), exist_ok=True)
                        atomic_write(GLOBAL_SETTINGS, json.dumps(g, indent=1))
                p = state_path(jid)
                # never let a fresh default silently erase real progress. if the
                # save on disk has progress and the incoming one doesn't, refuse
                # (a genuine reset deletes the save dir, it doesn't POST empty).
                # otherwise keep the last progress-bearing save as state.json.bak.
                old = None
                if os.path.exists(p):
                    try:
                        with open(p, encoding="utf-8") as f: old = json.load(f)
                    except (OSError, json.JSONDecodeError): old = None
                if has_progress(old) and not has_progress(body):
                    return self.send_json({"ok": False, "error": "refused: would erase progress", "kept": True}, 409)
                if has_progress(old):
                    atomic_write(p + ".bak", json.dumps(old, indent=1))
                atomic_write(p, json.dumps(body, indent=1))
                return self.send_json({"ok": True, "savedAt": time.time()})
            if path == "/api/workspace":
                write_files(jid, body.get("files", []))
                return self.send_json({"ok": True})
            if path == "/api/scaffold":
                if external_workspace(jid):  # the player's own tools own that directory
                    return self.send_json({"ok": True, "result": "external workspace — managed by your own tools"})
                pdir = project_dir(jid)
                os.makedirs(os.path.dirname(pdir), exist_ok=True)
                return self.send_json({"ok": True, "result": runtime_for(jid).scaffold(pdir, project_name(jid))})
            if path == "/api/seedworkspace":
                # place the tome's starter files into a student's OWN external folder
                # (explicit action). Non-destructive unless force; refuses a bad path.
                d = os.path.expanduser(body.get("dir", ""))
                if not (os.path.isabs(d) and os.path.isdir(d)):
                    return self.send_json({"ok": False, "error": "not an existing absolute folder"}, 400)
                rt = runtime_for(jid)
                if not rt.available():
                    return self.send_json({"ok": False, "error": f"{rt.LANGUAGE} toolchain not found on this machine"}, 400)
                mode = body.get("mode", "")  # "" = check, "missing" = add absent only, "force" = overwrite
                try:
                    return self.send_json(rt.seed_workspace(d, project_name(jid),
                                                            force=(mode == "force"), only_missing=(mode == "missing")))
                except Exception as e:
                    return self.send_json({"ok": False, "error": str(e)[-500:]}, 500)
            if path == "/api/openpath":
                # open the student's external project folder in their OS file explorer
                # (server shares their machine — localhost single-user tool)
                d = os.path.expanduser(body.get("dir", ""))
                if not (os.path.isabs(d) and os.path.isdir(d)):
                    return self.send_json({"ok": False, "error": "not an existing absolute folder"}, 400)
                try:
                    if sys.platform == "win32":
                        os.startfile(d)  # type: ignore[attr-defined]  # noqa: only exists on Windows
                    else:
                        opener = "open" if sys.platform == "darwin" else "xdg-open"
                        subprocess.Popen([opener, d], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return self.send_json({"ok": True})
                except Exception as e:
                    return self.send_json({"ok": False, "error": str(e)}, 500)
            if path == "/api/oracle":
                lang = body.get("language") or load_manifest(jid).get("runtime", {}).get("language") or "code"
                return self.send_json(ask_oracle(body.get("question", ""), body.get("context", ""),
                                                 body.get("model"), lang,
                                                 body.get("kind") or "ollama"))
            if path == "/api/runsnippet":
                rt = runtime_for(jid)
                return self.send_json(rt.run_snippet(scratch_base(rt.NAME), body.get("code", ""), body.get("stdin", "")))
            if path == "/api/snippetdiag":
                rt = runtime_for(jid)
                return self.send_json(rt.snippet_diagnostics(scratch_base(rt.NAME), body.get("code", "")))
            if path == "/api/run":
                write_files(jid, body.get("files", []))
                return self.send_json(runtime_for(jid).run_project(project_dir(jid), body.get("stdin", "")))
            if path == "/api/runcancel":
                return self.send_json({"ok": True, "cancelled": rt_common.cancel_current()})
            if path == "/api/diagnostics":
                write_files(jid, body.get("files", []))
                return self.send_json(runtime_for(jid).build_diagnostics(project_dir(jid)))
            if path == "/api/addpackage":
                return self.send_json(runtime_for(jid).add_package(project_dir(jid), body.get("package", "")))
            if path == "/api/grade":
                write_files(jid, body.get("files", []))
                sid = body.get("sectionId", "x")
                with jobs_lock:
                    for jid0, j in jobs.items():
                        if j.get("status") == "running" and j.get("section") == sid and j.get("tome") == jid:
                            return self.send_json({"ok": True, "jobId": jid0, "existing": True})
                    gid = uuid.uuid4().hex[:12]
                    jobs[gid] = {"status": "running", "section": sid, "tome": jid}
                threading.Thread(target=run_grader, args=(gid, body, jid), daemon=True).start()
                return self.send_json({"ok": True, "jobId": gid})
            if path == "/api/amend":
                req_text = str(body.get("request") or "").strip()
                if not req_text:
                    return self.send_json({"ok": False, "error": "an amendment request is required"}, 400)
                kind = str(body.get("kind") or "claude-cli")
                model = str(body.get("model") or "")
                effort = str(body.get("effort") or "")
                if effort and effort not in CLI_EFFORTS.get(kind, ()):
                    effort = ""  # drop an effort this kind doesn't accept rather than fail
                with jobs_lock:
                    for aid0, j in jobs.items():
                        if j.get("kind") == "amend" and j.get("status") == "running" and j.get("tome") == jid:
                            return self.send_json({"ok": True, "jobId": aid0, "existing": True})
                    aid = uuid.uuid4().hex[:12]
                    jobs[aid] = {"status": "running", "kind": "amend", "tome": jid,
                                 "request": req_text[:300], "startedAt": time.time()}
                threading.Thread(target=run_amender, args=(aid, jid, req_text, kind, model, effort),
                                 daemon=True).start()
                return self.send_json({"ok": True, "jobId": aid})
            if path == "/api/amend/cancel":
                aid = str(body.get("id") or "")
                with jobs_lock:
                    job = jobs.get(aid)
                    proc = amend_procs.get(aid)
                    if not (job and job.get("kind") == "amend" and job.get("status") == "running"):
                        return self.send_json({"ok": False, "error": "no running amendment with that id"}, 404)
                    job["status"] = "cancelled"
                if proc:
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)  # the CLI and every child it spawned
                    except (ProcessLookupError, PermissionError):
                        proc.kill()
                return self.send_json({"ok": True})
            if path == "/api/buildtome":
                concept = str(body.get("concept") or "").strip()
                if not concept:
                    return self.send_json({"ok": False, "error": "a course concept is required"}, 400)
                # The harness owns the folder name: it launches as untitled[-N] and
                # build_tome.py scaffolds tomes/<tid>/ after Phase 0; Phase 2 renames it
                # from the [runtime] project the author-AI chooses.
                tid = fresh_tome_id("untitled")
                # a prior failed run of this slug may have left a runner-request behind;
                # stale files would make the new job's status report the old pause
                _clear_runner_handshake(tid)
                tooling = str(body.get("tooling") or "").strip().lower()
                if tooling not in ("internal", "external", "both"):
                    return self.send_json({"ok": False, "error": "tooling must be internal, external, or both"}, 400)
                gate = json.dumps({"prior_knowledge": str(body.get("prior_knowledge") or "").strip(),
                                   "breadth": str(body.get("breadth") or "").strip(),
                                   "depth": str(body.get("depth") or "").strip(),
                                   "mastery": str(body.get("mastery") or "").strip(),
                                   "tooling": tooling})
                # optional per-agent AI picks from the bindery modal: {"default": {kind,
                # model, effort?}, "8": {kind, model, effort?}} → build_tome.py --runner overrides.
                runner_args = _runner_args(body)
                _save_launch(tid, body, concept)  # so a later resume can pre-fill the pickers
                # -u: unbuffered, so phase lines reach the reader as they happen.
                # start_new_session=True: its own process group, so cancel can kill
                # the harness AND the agent children it spawns.
                split_args = ["--split-sections"] if body.get("sectionsSplit") else []
                proc = subprocess.Popen([sys.executable, "-u", os.path.join(ROOT, "tools", "build_tome.py"),
                                         tid, "--gate-json", gate, "--concept", concept,
                                         "--ask-on-death"] + split_args + runner_args,
                                        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, start_new_session=True)
                gid = uuid.uuid4().hex[:12]
                with jobs_lock:
                    # slug: the launch id build_tome keys its .tome-build sidecars on. Phase 2
                    # renames the tome dir and we follow it in "tome" (for forge_name), but the
                    # runner handshake files stay under this slug — never mutate it.
                    jobs[gid] = {"status": "running", "kind": "build", "tome": tid, "slug": tid,
                                 "phase": 0, "phaseTitle": "starting", "totalPhases": BUILD_TOTAL_PHASES,
                                 "log": [], "pid": proc.pid, "startedAt": time.time()}
                threading.Thread(target=watch_build, args=(gid, proc), daemon=True).start()
                return self.send_json({"ok": True, "jobId": gid, "tome": tid})
            if path == "/api/buildtome/runner":
                # Answer a build pause: write the reply file build_tome.py is polling. Two pauses:
                # a dead runner (pick a new one) and a phase that exhausted its gate retries (switch
                # model and/or grant `retries` more tries). Empty kind+model keeps the current model;
                # for a death that means abort, for a gate pause it means "same model, N more tries".
                bid = str(body.get("id") or "")
                with jobs_lock:
                    job = jobs.get(bid)
                    # reply under the launch slug build_tome polls, not the renamed tome dir
                    tome = (job.get("slug") or job.get("tome")) if job and job.get("kind") == "build" else None
                if not tome:
                    return self.send_json({"ok": False, "error": "no such build"}, 404)
                kind = str(body.get("kind") or "")
                mdl = str(body.get("model") or "")
                eff = str(body.get("effort") or "")
                if mdl and kind not in ("claude-cli", "antigravity-cli", "codex-cli", "opencode-cli"):
                    return self.send_json({"ok": False, "error": "unknown runner kind"}, 400)
                if eff and eff not in CLI_EFFORTS.get(kind, ()):
                    eff = ""  # drop an effort this kind doesn't accept rather than fail
                try:
                    retries = max(0, int(body.get("retries") or 0))
                except (TypeError, ValueError):
                    retries = 0
                with open(os.path.join(BUILD_DIR, f"{tome}.runner-reply.json"), "w", encoding="utf-8") as f:
                    json.dump({"kind": kind, "model": mdl, "effort": eff, "retries": retries}, f)
                if mdl:  # reflect the pick now: mid-phase the harness re-emits [runner: …] only at
                    with jobs_lock:  # the next phase banner, so the overlay would keep the dead model.
                        j = jobs.get(bid)  # matches build_tome _spec_to_runner display; app.js strips the -cli prefix
                        if j:
                            j["runner"] = f"{kind} {mdl}" + (f" @{eff}" if eff else "")
                return self.send_json({"ok": True})
            if path == "/api/buildtome/cancel":
                bid = str(body.get("id") or "")
                with jobs_lock:
                    job = jobs.get(bid)
                    is_build = bool(job) and job.get("kind") == "build"
                    running = is_build and job.get("status") == "running"
                    pid = job.get("pid") if is_build else None
                    if running:
                        job["status"] = "cancelled"  # before the kill, so watch_build won't flag "error"
                if not is_build:
                    return self.send_json({"ok": False, "error": "no such build"}, 404)
                if running and pid:
                    try:
                        if hasattr(os, "killpg"):
                            os.killpg(os.getpgid(pid), signal.SIGTERM)
                        else:  # windows: no process groups — best effort on the harness itself
                            os.kill(pid, signal.SIGTERM)
                    except (ProcessLookupError, PermissionError, OSError):
                        pass  # already exited
                return self.send_json({"ok": True, "status": "cancelled" if running else job.get("status")})
            if path == "/api/buildtome/resume":
                rid = str(body.get("id") or "")
                pp = _plan_path(rid)
                if not os.path.exists(pp):
                    return self.send_json({"ok": False, "error": "no such working"}, 404)
                with open(pp, encoding="utf-8") as f:
                    text = f.read()
                tid = _resolve_working_tid(rid, text)
                with jobs_lock:
                    busy = any(j.get("kind") == "build" and j.get("status") == "running"
                               and j.get("tome") in (tid, rid) for j in jobs.values())
                if busy:
                    return self.send_json({"ok": False, "error": "that working is already being forged"}, 409)
                frm = _resume_phase(rid, tid)
                # optional operator override: the resume modal's "restart from" picker forces a
                # phase instead of the auto-detected one. Phase 3 skips sections in the done-set,
                # so a forced restart at/before it must drop that set to re-author every section
                # (e.g. section 2 failed but got recorded done — this is how you redo it).
                try:
                    forced = int(body.get("fromPhase"))
                except (TypeError, ValueError):
                    forced = 0
                if 1 <= forced <= 8:
                    frm = forced
                    _write_progress(tid, frm)
                    if frm <= 3:
                        for k in {rid, tid}:
                            try:
                                os.remove(os.path.join(BUILD_DIR, f"{k}.sections-done"))
                            except OSError:
                                pass
                # A renamed tome kept its plan under the old id; build_tome wants both under the
                # id it's launched with, so align the plan file name to the current tome id.
                if tid != rid and not os.path.exists(_plan_path(tid)):
                    try:
                        os.rename(pp, _plan_path(tid))
                    except OSError:
                        pass
                # Died before Phase 2 scaffolded the folder (--from-phase >0 skips Phase 0's
                # scaffold step): create it, then resume from the first content phase.
                if not os.path.isdir(os.path.join(TOMES_DIR, tid)):
                    subprocess.call([sys.executable, os.path.join(ROOT, "tools", "new_tome.py"), tid])
                    frm = 1
                _clear_runner_handshake(tid)
                _save_launch(tid, body, _plan_concept(text))
                split_args = ["--split-sections"] if body.get("sectionsSplit") else []
                proc = subprocess.Popen([sys.executable, "-u", os.path.join(ROOT, "tools", "build_tome.py"),
                                         tid, "--from-phase", str(frm), "--ask-on-death"]
                                        + split_args + _runner_args(body),
                                        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, start_new_session=True)
                gid = uuid.uuid4().hex[:12]
                with jobs_lock:
                    jobs[gid] = {"status": "running", "kind": "build", "tome": tid, "slug": tid,
                                 "phase": frm, "phaseTitle": "resuming", "totalPhases": BUILD_TOTAL_PHASES,
                                 "log": [], "pid": proc.pid, "startedAt": time.time()}
                threading.Thread(target=watch_build, args=(gid, proc), daemon=True).start()
                return self.send_json({"ok": True, "jobId": gid, "tome": tid})
            if path == "/api/buildtome/discard":
                rid = str(body.get("id") or "")
                pp = _plan_path(rid)
                if not os.path.exists(pp):
                    return self.send_json({"ok": False, "error": "no such working"}, 404)
                with open(pp, encoding="utf-8") as f:
                    text = f.read()
                tid = _resolve_working_tid(rid, text)
                with jobs_lock:
                    busy = any(j.get("kind") == "build" and j.get("status") == "running"
                               and j.get("tome") in (tid, rid) for j in jobs.values())
                if busy:
                    return self.send_json({"ok": False, "error": "cancel the running forge before discarding it"}, 409)
                for key in {rid, tid}:  # plan + every per-build sidecar, both ids if renamed
                    for suff in ("plan.md", "launch.json", "progress", "sections-done", "verdict",
                                 "findings.json", "runner-request.json", "runner-reply.json"):
                        try:
                            os.remove(os.path.join(BUILD_DIR, f"{key}.{suff}"))
                        except OSError:
                            pass
                # the partial tome itself — only when incomplete, and only if the path really is a
                # direct child of tomes/ (never let a crafted id escape the folder)
                tdir = os.path.realpath(os.path.join(TOMES_DIR, tid))
                if (tid and "Harness ground truth" not in text
                        and os.path.dirname(tdir) == os.path.realpath(TOMES_DIR)
                        and os.path.isdir(tdir)):
                    shutil.rmtree(tdir, ignore_errors=True)
                return self.send_json({"ok": True})
        except Exception as e:  # surface errors to the UI rather than 500-ing silently
            return self.send_json({"ok": False, "error": str(e)}, 500)
        self.send_json({"error": "unknown endpoint"}, 404)


if __name__ == "__main__":
    try:  # mirror locally-pulled ollama models into opencode's config so new ones are runnable
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "sync_ollama.py")], timeout=30)
    except Exception as e:  # never let a config-sync hiccup block the server
        print(f"sync-ollama: skipped ({e})")
    for j in list_tomes():
        save_dir(j["id"])  # regenerate any deleted save/ dir → fresh course
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://localhost:{port}"
    print(f"The candle is lit → {url}")
    if os.environ.get("ARCANUM_NO_OPEN") != "1":  # cross-platform auto-open; set =1 to suppress
        import webbrowser
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
