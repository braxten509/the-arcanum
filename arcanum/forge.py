"""Tome-forge build jobs: launching/watching builds, Pushover pings, and
resuming abandoned builds. Build jobs live in the shared config.jobs registry
with "kind": "build"."""
import glob
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request

from .config import BUILD_DIR, CLI_EFFORTS, GLOBAL_SETTINGS, TOMES_DIR, jobs, jobs_lock, read_json
from .tomes import load_manifest, resolve_working_tid

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
            for k in ("prior_knowledge", "prior_level", "breadth", "depth", "mastery", "tooling")}
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
    for key, label in (("prior_knowledge", "Prior knowledge"), ("prior_level", "Starting level"),
                       ("breadth", "Breadth"),
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
        tid = resolve_working_tid(planid, text)
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
